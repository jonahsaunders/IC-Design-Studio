"""Bounded Qt workers: no widget access and no mutation of the live project."""
import threading

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from . import inductor
from .inductor_synthesis import search, Cancelled

_pool = None


class Signals(QObject):
    geometry = Signal(int, object)
    finished = Signal(int, object, object)


class Job(QRunnable):
    def __init__(self, token, kind, args):
        super().__init__()
        self.token=token;self.kind=kind;self.args=args
        self.signals=Signals();self.cancelled=threading.Event()

    def cancel(self):
        self.cancelled.set()

    def run(self):
        result=None;error=None
        try:
            if self.cancelled.is_set():raise Cancelled('Cancelled.')
            if self.kind=='search':
                result=search(**self.args,cancel=self.cancelled.is_set)
            else:
                args=self.args
                data=inductor.geometry(args['p']['pdk'],args['spec'])
                if self.cancelled.is_set():raise Cancelled('Cancelled.')
                self.signals.geometry.emit(self.token,{**data,'pdk':args['p']['pdk']})
                result=inductor.plan(**args)
        except Exception as exc:
            # Deliver unexpected worker failures too; never leave Apply enabled
            # with a proposal from an earlier input revision.
            error=exc
        if self.cancelled.is_set():result=None;error=Cancelled('Cancelled.')
        self.signals.finished.emit(self.token,result,error)


def start(job):
    global _pool
    if _pool is None:
        _pool=QThreadPool();_pool.setMaxThreadCount(2)
    _pool.start(job)
