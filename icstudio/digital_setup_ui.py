"""Nonblocking setup and repair for the included digital engines."""
import json
import os
from pathlib import Path
import sys

from PySide6.QtCore import QProcess, QTimer, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QPushButton, QHBoxLayout

from . import digital_runtime


class DigitalSetupDialog(QDialog):
    ready = Signal()

    def __init__(self, parent=None, custom=None, automatic=False):
        super().__init__(parent)
        self.setWindowTitle('Digital tool setup'); self.resize(690,510)
        layout=QVBoxLayout(self)
        title=QLabel('Digital tools, ready inside Studio'); title.setStyleSheet('font-size:20px;font-weight:600'); layout.addWidget(title)
        note=QLabel('Includes Icarus, Verilator and C++ build tools, Yosys/ABC, EQY/SBY/Bitwuzla, OpenROAD/OpenSTA, KLayout, flow scripts and SKY130 HD.\n\n'
                    'The first setup unpacks the included package and runs simulation, coverage, synthesis, proof, timing and a small RTL-to-GDS design. This can take several minutes and several GB of disk space.')
        note.setWordWrap(True); layout.addWidget(note)
        self.status=QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.log=QPlainTextEdit(); self.log.setReadOnly(True); self.log.setAccessibleName('Digital installation log'); layout.addWidget(self.log,1)
        buttons=QHBoxLayout(); layout.addLayout(buttons)
        self.start=QPushButton('Set up and verify'); self.start.clicked.connect(self.setup); buttons.addWidget(self.start)
        self.enable=QPushButton('Enable Windows Linux support'); self.enable.clicked.connect(self.enable_wsl); self.enable.setVisible(os.name=='nt'); buttons.addWidget(self.enable)
        if custom:
            button=QPushButton('Custom tool paths…'); button.clicked.connect(custom); buttons.addWidget(button)
        self.close_button=QPushButton('Close'); self.close_button.clicked.connect(self.close); buttons.addWidget(self.close_button)
        self.process=None; self.buffer=''; self.refresh()
        if automatic and digital_runtime.status()['state']=='setup': QTimer.singleShot(100,self.setup)

    def refresh(self):
        info=digital_runtime.status(); self.status.setText(info['message'])
        self.start.setEnabled(info['state']!='unavailable' and self.process is None)
        self.start.setText('Verify again' if info['state']=='ready' else 'Set up and verify')

    def setup(self):
        if self.process: return
        self.log.clear(); self.status.setText('Preparing the digital runtime…'); self.start.setEnabled(False); self.enable.setEnabled(False)
        self.close_button.setText('Stop setup')
        self.process=QProcess(self); self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(lambda error:self.failed_start() if error==QProcess.FailedToStart else None)
        args=['--digital-setup']
        if not getattr(sys,'frozen',False): args.insert(0,str(Path(__file__).resolve().parents[1]/'main.py'))
        self.process.start(sys.executable,args)

    def read(self):
        if not self.process: return
        self.buffer+=bytes(self.process.readAllStandardOutput()).decode('utf-8',errors='replace')
        while '\n' in self.buffer:
            line,self.buffer=self.buffer.split('\n',1)
            try:
                data=json.loads(line); line=data.get('message',data.get('error',line))
            except ValueError: pass
            self.log.appendPlainText(line)
        self.log.document().setMaximumBlockCount(1500)

    def failed_start(self):
        self.log.appendPlainText('The setup worker could not start. Repair the application installation.'); self.finished(1)

    def finished(self, code, *_):
        if not self.process: return
        self.read(); self.process.deleteLater(); self.process=None
        self.enable.setEnabled(True); self.close_button.setText('Close'); self.refresh()
        if code==0 and digital_runtime.status()['state']=='ready': self.ready.emit()
        elif code: self.status.setText('Setup did not complete. The log below explains the failure. Retry setup after correcting it.')

    def enable_wsl(self):
        if os.name!='nt': return
        import ctypes
        import shutil
        executable=shutil.which('wsl.exe')
        if not executable:
            self.status.setText('wsl.exe is unavailable. Install Windows Subsystem for Linux through Windows Features, then retry.'); return
        code=ctypes.windll.shell32.ShellExecuteW(None,'runas',executable,'--install --no-distribution',None,1)
        self.status.setText('Windows will request administrator approval to enable Linux support. Restart Windows if requested, then reopen Studio and retry setup.' if code>32 else 'Windows Linux support was not enabled. You can retry this action.')

    def closeEvent(self, event):
        if self.process:
            from .digital_backend import cancel
            active=digital_runtime.state_root()/'active-check.json'
            try:
                folder=Path(json.loads(active.read_text())['directory']); cancel(folder)
            except (OSError,ValueError,KeyError): pass
            self.process.kill(); event.ignore(); return
        super().closeEvent(event)


def show(studio, automatic=False, custom=None):
    dialog=getattr(studio,'_digital_setup_dialog',None)
    if dialog is None:
        dialog=DigitalSetupDialog(studio,custom,automatic); studio._digital_setup_dialog=dialog
        dialog.ready.connect(lambda:apply_defaults(studio))
    dialog.refresh(); dialog.show(); dialog.raise_(); return dialog


def apply_defaults(studio):
    from .digital_design import config
    window=getattr(studio,'_digital_window',None)
    if window and window.project_id!=studio.project['id']: window=None
    if window and window.dirty and not window.attempt(window.apply): return
    cid=window.cell_id if window else studio.project.get('digital_cell',studio.project['top'])
    value=config(studio.project,cid)
    if value and 'platform' not in value:
        studio.commit(lambda p:digital_runtime.defaults(p,cid),'Configure included SKY130 digital platform')
        if window: window.load_sources()
