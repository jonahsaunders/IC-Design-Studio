"""Desktop-owned loopback server with durable identity and asynchronous startup."""
import json
from pathlib import Path
import socket
import ssl

from PySide6.QtCore import QObject, QThread, QLockFile, Signal
from PySide6.QtWidgets import QApplication

from .live_server import Server, load_creation_key
from .live_store import Store
from .model import atomic_write


def saved_port(directory):
    path = Path(directory) / 'server.json'
    if not path.exists():
        return 0
    record = json.loads(path.read_text(encoding='utf-8'))
    port = record.get('port')
    if record.get('version') != 1 or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('The saved local server address is invalid. Restore server.json from your server backup.')
    return port


class LocalServer(Server):
    def server_bind(self):
        # Windows REUSEADDR can share an occupied port instead of rejecting it.
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class NetworkServer(LocalServer):
    def __init__(self, address, store, context):
        self.context = context
        super().__init__(address, store)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(10)
        try:
            return self.context.wrap_socket(connection, server_side=True, do_handshake_on_connect=False), address
        except Exception:
            connection.close()
            raise

    def handle_error(self, request, client_address):
        # Failed handshakes carry no request and are expected for stale invites.
        import sys
        if not isinstance(sys.exception(), (ssl.SSLError, ConnectionError, TimeoutError)):
            super().handle_error(request, client_address)


class LocalServerWorker(QThread):
    ready = Signal(str, str)
    failed = Signal(str)

    def __init__(self, directory, parent, address='127.0.0.1', encrypted=False):
        super().__init__(parent)
        self.directory = Path(directory)
        self.address, self.encrypted = address, encrypted
        self.certificate = ''

    def run(self):
        lock = None
        store = server = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.directory.chmod(0o700)
            lock = QLockFile(str(self.directory / 'server.lock'))
            lock.setStaleLockTime(0)
            if not lock.tryLock(0):
                raise RuntimeError('The local server is already open in another IC Design Studio instance, or its folder is not writable. Use Join a workspace in this window, or close the other host and retry.')
            key = load_creation_key(self.directory)
            port = saved_port(self.directory)
            store = Store(self.directory / 'collaboration.sqlite3', key)
            context = None
            if self.encrypted:
                from .network_tls import host_certificates
                path, self.certificate = host_certificates(self.directory, self.address)
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                context.load_cert_chain(path)
            try:
                server = NetworkServer((self.address, port), store, context) if context else LocalServer((self.address, port), store)
            except OSError as exc:
                message = ('The saved local server address is unavailable. Close the application using port ' + str(port) + ' and retry. Your workspaces are retained.'
                           if port else 'No local listening address is available. Check whether your system permits local server connections, then retry.')
                raise RuntimeError(message) from exc
            # Finish accepted requests before closing their database, including
            # on Windows where an open connection prevents file cleanup.
            server.daemon_threads = False
            server.timeout = 0.1
            record = dict(version=1, port=server.server_port)
            if context:
                old_path = self.directory / 'server.json'
                old = json.loads(old_path.read_text(encoding='utf-8')) if old_path.exists() else {}
                record.update(address=self.address, addresses=list(dict.fromkeys([self.address, *old.get('addresses', [])]))[:16])
            atomic_write(self.directory / 'server.json', json.dumps(record))
            self.ready.emit(('https://' if context else 'http://') + self.address + ':' + str(server.server_port), key)
            while not self.isInterruptionRequested():
                server.handle_request()
        except Exception as exc:
            self.failed.emit('Could not start the local server. ' + str(exc))
        finally:
            if server:
                server.server_close()
            if store:
                store.close()
            if lock and lock.isLocked():
                lock.unlock()


class LocalCollaborationHost(QObject):
    changed = Signal()

    def __init__(self, directory, parent):
        super().__init__(parent)
        self.directory = Path(directory)
        self.worker = None
        self.state = 'stopped'
        self.url = self.key = self.error = ''
        self.certificate = ''
        self.worker_options = {}
        self.callbacks = []

    def owns_url(self, url):
        try:
            port = saved_port(self.directory)
            return bool(port) and url == 'http://127.0.0.1:' + str(port)
        except (OSError, ValueError, TypeError, AttributeError):
            return False

    def start(self, callback=None):
        if self.state == 'running':
            if callback:
                callback()
            return
        if self.state == 'stopping':
            return
        if callback:
            self.callbacks.append(callback)
        if self.state == 'starting':
            return
        self.state, self.error = 'starting', ''
        self.worker = LocalServerWorker(self.directory, self, **self.worker_options)
        self.worker.ready.connect(self._ready)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._finished)
        self.changed.emit()
        self.worker.start()

    def _ready(self, url, key):
        if self.state != 'starting':
            return
        self.url, self.key, self.state = url, key, 'running'
        self.certificate = self.worker.certificate
        callbacks, self.callbacks = self.callbacks, []
        self.changed.emit()
        for callback in callbacks:
            callback()

    def _failed(self, message):
        self.error = message
        self.callbacks.clear()

    def _finished(self):
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        self.url = self.key = ''
        self.certificate = ''
        self.callbacks.clear()
        self.state = 'stopped'
        self.changed.emit()

    def stop(self):
        self.callbacks.clear()
        if self.worker and self.worker.isRunning():
            self.state = 'stopping'
            self.worker.requestInterruption()
            self.changed.emit()

    def shutdown(self):
        self.stop()
        if self.worker:
            self.worker.wait()
        self.url = self.key = ''
        self.certificate = ''
        self.state = 'stopped'


def local_host(studio):
    """One host per application/data folder, surviving dashboard/window closure."""
    app = QApplication.instance()
    if not hasattr(app, '_local_collaboration_hosts'):
        app._local_collaboration_hosts = {}
    directory = (studio.data_dir / 'local-collaboration').resolve()
    if directory not in app._local_collaboration_hosts:
        host = LocalCollaborationHost(directory, app)
        app.aboutToQuit.connect(host.shutdown)
        app._local_collaboration_hosts[directory] = host
    return app._local_collaboration_hosts[directory]
