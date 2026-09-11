"""Asynchronous Qt transport and recoverable desktop live-session state."""
import json
from pathlib import Path
import uuid

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest, QSslCertificate, QSslSocket, QSsl

from .live_protocol import ID, MAX_BYTES, PROTOCOL, LiveError, bounded_project, changes, server_url
from .model import atomic_write, clone, validate


def check_session(workspace, token, snapshot):
    if snapshot.get('protocol') != PROTOCOL:
        raise LiveError('Update the collaboration server and all desktop clients for schematic and layout collaboration (protocol 2).')
    if any(not isinstance(value, str) or not ID.fullmatch(value) for value in (workspace, token, snapshot.get('actor'))):
        raise LiveError('Invalid server session identity.')
    if snapshot.get('role') not in ('owner', 'view', 'review', 'edit') or type(snapshot.get('revision')) is not int or snapshot['revision'] < 0:
        raise LiveError('Invalid server session state.')
    if any(type(snapshot.get(k, 0)) is not int or not 0 <= snapshot.get(k, 0) <= 100 for k in ('undo', 'redo')):
        raise LiveError('Invalid server history state.')


class Transport(QObject):
    def __init__(self, parent=None, certificate='', origin=''):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.certificate, self.origin = certificate, origin

    def post(self, server, path, token, data, callback, certificate=None):
        server = server_url(server)
        if certificate is None:
            if self.certificate and server != self.origin:
                raise LiveError('This session certificate belongs to a different server.')
            certificate = self.certificate
        request = QNetworkRequest(QUrl(server_url(server) + path))
        if certificate:
            if not server.startswith('https://'):
                raise LiveError('A trusted host certificate requires HTTPS.')
            from .network_tls import certificate_pem
            config = request.sslConfiguration()
            config.setCaCertificates(QSslCertificate.fromData(certificate_pem(certificate)))
            config.setPeerVerifyMode(QSslSocket.VerifyPeer)
            config.setProtocol(QSsl.TlsV1_2OrLater)
            request.setSslConfiguration(config)
        request.setHeader(QNetworkRequest.ContentTypeHeader, 'application/json')
        request.setRawHeader(b'Authorization', ('Bearer ' + token).encode('ascii'))
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.ManualRedirectPolicy)
        request.setTransferTimeout(10000)
        payload = json.dumps(data, allow_nan=False, separators=(',', ':')).encode()
        if len(payload) > MAX_BYTES:
            raise LiveError('This edit exceeds the 16 MiB live request limit.')
        # A setup/join request with new trust must not reuse another invitation's
        # cached TLS connection. Session transports retain one fixed authority.
        manager = QNetworkAccessManager(self) if certificate and certificate != self.certificate else self.manager
        reply = manager.post(request, payload)
        if manager is not self.manager:
            reply.finished.connect(manager.deleteLater)
        chunks = bytearray()
        oversized = False

        def read():
            nonlocal oversized
            chunks.extend(bytes(reply.readAll()))
            if len(chunks) > MAX_BYTES:
                oversized = True
                reply.abort()

        def finished():
            read()
            status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0
            network_error = reply.error()
            reply.deleteLater()
            if oversized:
                callback(413, {'error': 'The server response exceeded the live-project limit.'})
                return
            if not status or (network_error != QNetworkReply.NoError and status < 400):
                message = ('The secure connection could not be verified. Check the computer clock and ask the host for a fresh invitation; certificate checks remain enabled.'
                           if network_error == QNetworkReply.SslHandshakeFailedError else 'Connection unavailable. Check that the host is running, both computers can reach the same network or VPN, and the host firewall allows the displayed port. Your pending edit is retained.')
                callback(0, {'error': message})
                return
            try:
                result = json.loads(chunks)
                if not isinstance(result, dict):
                    raise ValueError()
            except (ValueError, UnicodeError):
                result = {'error': 'The server returned an invalid response.'}
                status = status if status >= 400 else 502
            callback(status, result)

        reply.readyRead.connect(read)
        reply.finished.connect(finished)
        return reply


class LiveClient(QObject):
    changed = Signal()
    status_changed = Signal(str)

    def __init__(self, server, workspace, token, snapshot, journal, parent=None, server_certificate=''):
        super().__init__(parent)
        check_session(workspace, token, snapshot)
        self.server, self.workspace, self.token = server_url(server), workspace, token
        self.journal = Path(journal)
        self.server_certificate = server_certificate
        if server_certificate:
            from .network_tls import decode_certificate
            decode_certificate(server_certificate)
            if not self.server.startswith('https://'):
                raise LiveError('A saved host certificate requires HTTPS.')
        self.transport = Transport(self, certificate=server_certificate, origin=self.server)
        self.project = bounded_project(clone(snapshot['project']))
        self.revision = snapshot['revision']
        self.info = {k: v for k, v in snapshot.items() if k not in ('project', 'token')}
        self.pending = None
        self.conflict = None
        self.active = True
        self.connected = True
        self.busy = False
        self.managing = False
        self.message = 'Live · ' + self.info['role']
        self.presence = lambda: {}
        self.can_install = lambda: True
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.tick)
        self.save_journal()

    @property
    def path(self):
        return '/v2/workspaces/' + self.workspace

    def save_journal(self):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        self.journal.parent.chmod(0o700)
        state = dict(schema=2, server=self.server, workspace=self.workspace, token=self.token,
                     project=self.project, revision=self.revision, info=self.info,
                     pending=self.pending, conflict=self.conflict, server_certificate=self.server_certificate)
        atomic_write(self.journal, json.dumps(state, allow_nan=False))
        self.journal.chmod(0o600)

    @classmethod
    def resume(cls, path, parent=None):
        path = Path(path)
        if path.stat().st_size > 64 * 1024 * 1024:
            raise LiveError('Recovery file exceeds 64 MiB.')
        state = json.loads(path.read_text(encoding='utf-8'))
        if state.get('schema') not in (1, 2):
            raise LiveError('Unsupported live-session recovery file.')
        # Do not overwrite the existing journal until the complete state has loaded.
        snapshot = dict(state['info'], project=state['project'], revision=state['revision'])
        if state['schema'] == 1:
            snapshot['protocol'] = PROTOCOL  # Legacy requests keep their IDs on the upgraded server.
        # Construction writes a new journal: use a separate path until pending data is restored.
        obj = cls(state['server'], state['workspace'], state['token'], snapshot,
                  path.with_suffix('.loading'), parent, server_certificate=state.get('server_certificate', ''))
        obj.journal.unlink(missing_ok=True)
        obj.journal = path
        obj.pending, obj.conflict = state.get('pending'), state.get('conflict')
        if obj.pending and obj.pending.get('proposed'):
            obj.project = bounded_project(clone(obj.pending['proposed']))
        obj.connected = False
        obj.save_journal()
        return obj

    def start(self):
        self.timer.start()
        QTimer.singleShot(0, self.tick)

    def say(self, text):
        self.message = text
        self.status_changed.emit(text)

    def editable(self):
        if self.managing:
            raise LiveError('Workspace management is in progress. Please wait before editing.')
        if self.info['role'] not in ('owner', 'edit'):
            raise LiveError('This session cannot edit the design. Ask the owner for an edit invitation.')
        if self.conflict:
            raise LiveError('Save or discard the retained conflicting edit in the live session panel first.')
        if self.pending:
            raise LiveError('The previous edit is still syncing. Wait for its acknowledgement.')
        if not self.connected:
            raise LiveError('Reconnecting. Save a local copy to continue editing independently.')

    def submit(self, project, label):
        self.editable()
        self._submit(project, label)

    def _submit(self, project, label, resolves_conflict=False):
        rows = changes(self.project, project)
        if not rows:
            return
        bounded_project(project)
        request = dict(id=uuid.uuid4().hex, revision=self.revision, changes=rows, label=label[:160], action='edit')
        pending = dict(request=request, before=clone(self.project), proposed=clone(project),
                       resolves_conflict=resolves_conflict)
        self.pending = pending
        try:
            self.save_journal()  # Persist the request ID before any network mutation.
        except Exception:
            self.pending = None
            raise
        self.project = clone(project)
        self.say('Syncing design edit…')
        self.changed.emit()
        self.tick()

    def reapply(self, revision):
        from .live_review import reapply_conflict
        if not self.conflict or self.pending or not self.connected or self.info['role'] not in ('owner', 'edit'):
            raise LiveError('Reconnect and wait for synchronization before reapplying this edit.')
        if self.revision != revision:
            raise LiveError('The shared design changed. Refresh the comparison before reapplying.')
        proposed = reapply_conflict(self.conflict, self.project)
        if not changes(self.project, proposed):
            raise LiveError('These changes are already in the shared design. Choose Use shared version.')
        self._submit(proposed, 'Reapply reviewed edit', resolves_conflict=True)

    def history_action(self, action):
        self.editable()
        if not self.info.get(action):
            return
        self.pending = dict(request=dict(id=uuid.uuid4().hex, action=action), before=clone(self.project), proposed=None)
        try:
            self.save_journal()
        except Exception:
            self.pending = None
            raise
        self.say('Syncing personal ' + action + '…')
        self.tick()

    def tick(self):
        if not self.active or self.busy:
            return
        editing = self.pending is not None
        body = self.pending['request'] if editing else dict(revision=self.revision, presence=self.presence())
        self.busy = True

        def complete(status, result):
            self.busy = False
            if not self.active:
                return
            if status == 0 or status >= 500 or status in (408, 429):
                self.connected = False
                self.timer.setInterval(min(8000, max(1000, self.timer.interval() * 2)))
                self.say('Reconnecting · pending work is saved locally')
                return
            self.connected = status == 200
            self.timer.setInterval(500)
            if status != 200:
                if editing and self.pending:
                    self.conflict = self.pending
                    self.project = self.pending['before']
                    self.pending = None
                try:
                    self.save_journal()
                except OSError:
                    self.say('Recovery storage failed. Save a local copy before closing the app.')
                    self.timer.stop()
                    self.changed.emit()
                    return
                self.say(result.get('error', 'The server rejected the request.'))
                if status in (401, 403, 426) or (not editing and status in (404, 409)):
                    self.timer.stop()
                self.changed.emit()
                return
            try:
                old_info = {k: v for k, v in self.info.items() if k not in ('participants', 'leases', 'history', 'reservation_denied')}
                check_session(self.workspace, self.token, result)
                if result['actor'] != self.info['actor']:
                    raise LiveError('The server returned a different session identity.')
                if result['revision'] < self.revision:
                    raise LiveError('Server revision moved backwards; leave and keep a local copy.')
                if editing and result.get('acknowledged') != body['id']:
                    raise LiveError('Missing edit acknowledgement; retrying the saved request.')
                # A poll already in flight when an edit starts must never replace that edit.
                install = editing or (self.pending is None and self.can_install())
                changed = False
                if install and 'project' in result:
                    self.project = bounded_project(result['project'])
                    self.revision = result['revision']
                    changed = True
                self.info.update({k: v for k, v in result.items() if k not in ('project', 'token', 'revision')})
                if editing:
                    if self.pending and self.pending.get('resolves_conflict'):
                        self.conflict = None
                    self.pending = None
                new_info = {k: v for k, v in self.info.items() if k not in ('participants', 'leases', 'history', 'reservation_denied')}
                if changed or editing or old_info != new_info:
                    self.save_journal()
                if self.conflict:
                    self.say('Conflict retained locally · save or discard it to continue')
                elif self.pending:
                    self.say('Syncing design edit…')
                elif result.get('reservation_denied'):
                    self.say('Selection reserved by another editor · choose other objects')
                else:
                    self.say('Live · ' + self.info['role'] + ' · revision ' + str(self.revision))
                # Presence also updates the canvas, without resetting the editor document.
                if changed:
                    self.changed.emit()
            except (ValueError, KeyError, TypeError, OSError) as exc:
                self.connected = False
                self.say('Live session paused: ' + str(exc))
                self.timer.setInterval(8000)

        try:
            self.transport.post(self.server, self.path + ('/edit' if editing else '/sync'), self.token, body, complete)
        except Exception:
            self.busy = False
            raise

    def stop(self):
        self.active = False
        self.timer.stop()
        self.save_journal()
        self.transport.post(self.server, self.path + '/leave', self.token, {}, lambda *_: None)


class LiveHistory:
    """The existing editor's transaction interface, backed by personal server history."""
    def __init__(self, client):
        self.client = client

    @property
    def project(self):
        return self.client.project

    @property
    def undo_stack(self):
        return [None] * self.client.info.get('undo', 0)

    @property
    def redo_stack(self):
        return [None] * self.client.info.get('redo', 0)

    def commit(self, fn, label='Edit'):
        self.client.editable()
        q = clone(self.project)
        fn(q)
        validate(q)
        self.client.submit(q, label)

    def commit_layout_move(self, *args, **kwargs):
        return False  # Use the normal validated connected-edit transaction.

    def commit_layout_arrange(self, *args, **kwargs):
        return False

    def undo(self):
        self.client.history_action('undo')

    def redo(self):
        self.client.history_action('redo')
