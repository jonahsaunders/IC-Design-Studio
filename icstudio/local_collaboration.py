"""Desktop-owned loopback server with durable identity and asynchronous startup."""
import json
from pathlib import Path
import socket

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


class LocalServerWorker(QThread):
    ready = Signal(str, str)
    failed = Signal(str)

    def __init__(self, directory, parent):
        super().__init__(parent)
        self.directory = Path(directory)

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
            try:
                server = LocalServer(('127.0.0.1', port), store)
            except OSError as exc:
                message = ('The saved local server address is unavailable. Close the application using port ' + str(port) + ' and retry. Your workspaces are retained.'
                           if port else 'No local listening address is available. Check whether your system permits local server connections, then retry.')
                raise RuntimeError(message) from exc
            # Finish accepted requests before closing their database, including
            # on Windows where an open connection prevents file cleanup.
            server.daemon_threads = False
            server.timeout = 0.1
            atomic_write(self.directory / 'server.json', json.dumps(dict(version=1, port=server.server_port)))
            self.ready.emit('http://127.0.0.1:' + str(server.server_port), key)
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
        self.worker = LocalServerWorker(self.directory, self)
        self.worker.ready.connect(self._ready)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._finished)
        self.changed.emit()
        self.worker.start()

    def _ready(self, url, key):
        if self.state != 'starting':
            return
        self.url, self.key, self.state = url, key, 'running'
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
