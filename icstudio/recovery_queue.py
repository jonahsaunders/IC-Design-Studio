"""One ordered recovery writer with coalescing and a synchronous lifecycle fence."""
from concurrent.futures import ThreadPoolExecutor
from time import monotonic
from PySide6.QtCore import QObject, QTimer, Signal
from .model import clone, digest
from . import recovery


def write_snapshot(project, directory, source, validated):
    recovery.write(project, directory, source, validated=validated)
    return digest(project)


class RecoveryQueue(QObject):
    completed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='studio-recovery')
        self.pending = self.active = None
        self.first_pending = None
        self.last_error = None
        self.closed = False
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.tick)

    @property
    def busy(self):
        return self.pending is not None or self.active is not None

    def request(self, project, directory, source, epoch, validated=False):
        if self.closed:
            raise RuntimeError('Recovery writer is closed.')
        now = monotonic()
        self.first_pending = self.first_pending or now
        self.pending = (project, directory, source, epoch, validated, now)
        self.timer.start()

    def dispatch(self):
        project, directory, source, epoch, validated, _ = self.pending
        # UI callers may still own mutable metadata. Only an isolated snapshot
        # crosses the thread boundary; serialization, validation and fsync do not.
        snapshot = clone(project)
        future = self.executor.submit(write_snapshot, snapshot, directory, source, validated)
        self.active = (future, dict(project_id=project['id'], revision=project['revision'],
                                    directory=str(directory), epoch=epoch))
        self.pending = self.first_pending = None

    def collect(self, wait=False):
        if self.active is None:
            return True
        future, metadata = self.active
        if not wait and not future.done():
            return False
        try:
            fingerprint = future.result(timeout=10 if wait else 0)
            result = dict(metadata, hash=fingerprint, error=None)
        except TimeoutError:
            raise RuntimeError('Recovery is still writing. Wait before closing or changing projects.')
        except Exception as exc:
            result = dict(metadata, hash=None, error=str(exc))
        self.active = None
        self.last_error = result['error']
        self.completed.emit(result)
        return True

    def tick(self):
        if not self.collect():
            return
        if self.pending:
            now = monotonic()
            if now - self.pending[-1] >= .15 or now - self.first_pending >= 1:
                self.dispatch()
        if not self.busy:
            self.timer.stop()

    def flush(self, discard=False):
        self.timer.stop()
        self.collect(wait=True)
        if discard:
            self.pending = self.first_pending = None
        elif self.pending:
            self.dispatch()
            self.collect(wait=True)
        return self.last_error is None

    def shutdown(self):
        self.flush()
        self.executor.shutdown(wait=True)
        self.closed = True
