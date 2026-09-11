"""Self-hosted collaboration HTTP API. Run behind HTTPS or supply a TLS certificate."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import re
import secrets
import ssl
import threading

from .live_protocol import LiveError, MAX_BYTES
from .live_store import Store, encode


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, store):
        self.store = store
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(address, Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = 'ICStudioLive/1'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(10)
        if isinstance(self.connection, ssl.SSLSocket):
            self.connection.do_handshake()

    def log_message(self, *args):
        # Invitations and credentials must not enter request logs.
        pass

    def reply(self, status, value, content_type='application/json', nonce=None):
        data = value.encode() if isinstance(value, str) else encode(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        if nonce:
            self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-" + nonce + "'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (OSError, TimeoutError):
            pass  # A committed operation can be retried with the same request ID.

    def do_GET(self):
        if self.path == '/health':
            return self.reply(200, {'service': 'IC Design Studio live layout', 'protocol': 1})
        if self.path != '/join':
            return self.reply(404, {'error': 'Unknown endpoint.'})
        nonce = secrets.token_urlsafe(24)
        page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
        <title>Join IC Design Studio</title><style>body{font:18px system-ui;background:#101b27;color:#e8eef5;max-width:620px;margin:12vh auto;padding:28px}h1{font-size:32px}a{display:inline-block;background:#8de0c8;color:#102b2b;padding:14px 24px;border-radius:8px;font-weight:600;text-decoration:none}p{line-height:1.6}small{color:#abbccc}</style>
        <h1>Work on a layout together</h1><p>This invitation opens IC Design Studio on your computer.</p>
        <a id="join" hidden>Open IC Design Studio</a><p id="message"></p>
        <small>If the app does not open, copy the full invitation link and choose Tools → Collaboration → Join a workspace in the app. An installed desktop app is required.</small>
        <script nonce="NONCE">const p=new URLSearchParams(location.hash.slice(1));
        if (/^[A-Za-z0-9_-]{1,80}$/.test(p.get('workspace')||'') && /^[A-Za-z0-9_-]{32,100}$/.test(p.get('invite')||'') && [...p.keys()].length===2) {
          const a=document.getElementById('join'); a.href='icstudio://join?server='+encodeURIComponent(location.origin)+location.hash; a.hidden=false;
          document.getElementById('message').textContent='Your browser may ask permission to open the installed app.';
        } else {document.getElementById('message').textContent='This invitation is incomplete. Ask the owner for a new link.';}
        </script></html>'''.replace('NONCE', nonce)
        return self.reply(200, page, 'text/html', nonce)

    def do_POST(self):
        try:
            if self.headers.get('Transfer-Encoding'):
                raise LiveError('Use the desktop client for this API.', 403)
            length = int(self.headers.get('Content-Length', '-1'))
            if not 0 <= length <= MAX_BYTES:
                raise LiveError('Request exceeds the 16 MiB limit.', 413)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise LiveError('Incomplete request.', 400)
            # Consume the bounded, framed body before closing a rejected POST.
            # Closing with unread bytes can reset TCP and erase the response on
            # Windows (RFC 9112 section 9.6). Never decode or authorize it first.
            if self.headers.get('Origin'):
                raise LiveError('Use the desktop client for this API.', 403)
            if self.headers.get_content_type() != 'application/json':
                raise LiveError('JSON is required.', 415)
            def invalid_constant(value):
                raise ValueError('Non-finite JSON number')
            body = json.loads(raw, parse_constant=invalid_constant)
            if not isinstance(body, dict):
                raise LiveError('Expected a JSON object.', 400)
            if self.path == '/v2/check':
                from .live_protocol import PROTOCOL
                return self.reply(200, {'service': 'IC Design Studio', 'protocol': PROTOCOL})
            header = self.headers.get('Authorization', '')
            token = header[7:] if header.startswith('Bearer ') and len(header) < 256 else ''
            store = self.server.store
            if self.path.startswith('/v1/'):
                raise LiveError('Update IC Design Studio on all clients for schematic and layout collaboration (protocol 2). Your workspace is retained.', 426)
            if self.path == '/v2/workspaces':
                result = store.create(token, body['project'], body['name'])
            else:
                match = re.fullmatch(r'/v2/workspaces/([A-Za-z0-9_-]{1,80})/(join|sync|edit|invite|revoke|leave|recover-owner|delete|review)', self.path)
                if not match:
                    raise LiveError('Unknown endpoint.', 404)
                wid, action = match.groups()
                if action == 'join':
                    result = store.join(wid, body['invite'], body['name'])
                elif action == 'sync':
                    result = store.sync(wid, token, body.get('revision', -1), body.get('presence'))
                elif action == 'edit':
                    result = store.edit(wid, token, body)
                elif action == 'invite':
                    result = store.invite(wid, token, body['role'], body.get('days', 7))
                elif action == 'revoke':
                    result = store.revoke(wid, token, body['invitation'])
                elif action == 'recover-owner':
                    result = store.recover_owner(wid, token, body['actor'])
                elif action == 'delete':
                    result = store.delete_workspace(wid, token, body['revision'])
                elif action == 'review':
                    result = store.review(wid,token,body)
                else:
                    result = store.leave(wid, token)
            self.reply(200, result)
        except LiveError as exc:
            self.reply(exc.status, {'error': str(exc)})
        except (KeyError, TypeError, ValueError, UnicodeError, RecursionError):
            self.reply(400, {'error': 'Invalid request or project data.'})
        except (OSError, TimeoutError):
            self.close_connection = True
        except Exception:
            self.reply(500, {'error': 'The server could not complete this request. Retry with the same edit ID.'})


def load_creation_key(directory):
    """Create the host credential once, shared by command-line and desktop hosts."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    key_path = directory / 'creation-key.txt'
    try:
        with key_path.open('x', encoding='utf-8') as f:
            key_path.chmod(0o600)
            f.write(secrets.token_urlsafe(32) + '\n')
    except FileExistsError:
        pass
    key = key_path.read_text(encoding='utf-8').strip()
    if not 32 <= len(key) <= 128 or not key.isascii() or not key.isprintable():
        raise ValueError('The saved server key is invalid. Restore creation-key.txt from your server backup.')
    return key


def main(argv=None):
    parser = argparse.ArgumentParser(description='Host IC Design Studio live layout collaboration')
    parser.add_argument('--data', type=Path, required=True, help='Private directory for the database and creation key')
    parser.add_argument('--listen', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--certfile', type=Path)
    parser.add_argument('--keyfile', type=Path)
    args = parser.parse_args(argv)
    if bool(args.certfile) != bool(args.keyfile):
        parser.error('Supply both --certfile and --keyfile for TLS.')
    try:
        local = args.listen == 'localhost' or ipaddress.ip_address(args.listen).is_loopback
    except ValueError:
        local = False
    if not local and not args.certfile:
        parser.error('Non-loopback listeners require TLS. A reverse proxy can connect to the loopback listener.')
    key_path = args.data / 'creation-key.txt'
    store = Store(args.data / 'collaboration.sqlite3', load_creation_key(args.data))
    server = Server((args.listen, args.port), store)
    if args.certfile:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.certfile, args.keyfile)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    print('IC Design Studio collaboration listening on ' + str(server.server_address), flush=True)
    print('Workspace creation key: ' + str(key_path.resolve()) + ' (keep private)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        store.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
