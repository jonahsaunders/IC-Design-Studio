"""Keep the pinned library repair visible and cancellable during GUI imports."""
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout

from .xschem_libraries import repair_gf180


class RepairThread(QThread):
    progress = Signal(float, str)
    error = ''

    def run(self):
        def report(fraction, message):
            if self.isInterruptionRequested():
                raise ValueError('Library download cancelled.')
            self.progress.emit(fraction, message)
        try:
            repair_gf180(report)
        except Exception as exc:
            self.error = str(exc)


class RepairDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('Restore GF180 library')
        self.resize(480, 130)
        layout = QVBoxLayout(self)
        self.label = QLabel('Checking library files…')
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.bar = QProgressBar()
        self.bar.setFormat('%p% of library files')
        layout.addWidget(self.bar)
        self.cancel = QPushButton('Cancel download')
        self.cancel.clicked.connect(self.reject)
        layout.addWidget(self.cancel)
        self.worker = RepairThread(self)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.accept)

    def update_progress(self, fraction, message):
        if not self.worker.isInterruptionRequested():
            self.bar.setValue(int(fraction * 100))
            self.label.setText(message)

    def reject(self):
        self.worker.requestInterruption()
        self.cancel.setEnabled(False)
        self.label.setText('Stopping download…')


def restore(parent):
    dialog = RepairDialog(parent)
    dialog.worker.start()
    dialog.exec()
    dialog.worker.wait()
    if dialog.worker.error:
        raise ValueError(dialog.worker.error)
