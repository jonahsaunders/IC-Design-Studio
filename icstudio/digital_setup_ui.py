"""Nonblocking setup and repair for the included digital engines."""
import json
import os
from pathlib import Path
import sys

from PySide6.QtCore import QProcess, QTimer, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                              QHBoxLayout, QComboBox, QProgressBar, QToolButton,
                              QFormLayout, QLineEdit, QDialogButtonBox)

from . import digital_runtime


class DigitalSetupDialog(QDialog):
    ready = Signal()
    changed = Signal()

    def __init__(self, parent=None, custom=None, automatic=False):
        super().__init__(parent)
        self.setWindowTitle('Digital tools'); self.resize(690,440)
        self.custom = custom; self.pending = None; self.process = None; self.buffer = ''
        layout=QVBoxLayout(self)
        title=QLabel('Everything you need for digital design'); title.setStyleSheet('font-size:20px;font-weight:600'); layout.addWidget(title)
        note=QLabel('Studio includes tools for simulation, synthesis and chip layout, plus the SKY130 HD platform. '
                    'First setup takes several minutes and several GB of disk space. You can keep editing while it runs.')
        note.setWordWrap(True); layout.addWidget(note)
        self.mode=QComboBox(); self.mode.setAccessibleName('Digital toolchain')
        self.mode.addItem('Included tools (recommended)', 'included'); self.mode.addItem('Custom tools', 'custom')
        from .digital_tools import selection
        settings=getattr(parent,'settings',None)
        self.mode.setCurrentIndex(1 if settings and selection(settings)['toolchain']=='custom' else 0)
        self.mode.currentIndexChanged.connect(self.select_mode); layout.addWidget(self.mode)
        self.status=QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.next_action=QLabel(); self.next_action.setWordWrap(True); layout.addWidget(self.next_action)
        self.progress=QProgressBar(); self.progress.setRange(0,0); self.progress.setVisible(False); layout.addWidget(self.progress)
        self.details=QToolButton(); self.details.setText('Show setup details'); self.details.setCheckable(True)
        self.details.toggled.connect(self.toggle_details); layout.addWidget(self.details)
        self.log=QPlainTextEdit(); self.log.setReadOnly(True); self.log.setAccessibleName('Digital installation log'); layout.addWidget(self.log,1)
        self.log.hide()
        buttons=QHBoxLayout(); layout.addLayout(buttons)
        self.start=QPushButton('Set up and verify'); self.start.clicked.connect(self.setup); buttons.addWidget(self.start)
        self.enable=QPushButton('Enable Windows Linux support'); self.enable.clicked.connect(self.enable_wsl); self.enable.setVisible(os.name=='nt'); buttons.addWidget(self.enable)
        self.custom_button=QPushButton('Configure custom tools…'); self.custom_button.clicked.connect(self.configure_custom); buttons.addWidget(self.custom_button)
        self.close_button=QPushButton('Close'); self.close_button.clicked.connect(self.close); buttons.addWidget(self.close_button)
        links=QHBoxLayout(); layout.addLayout(links)
        self.download=QPushButton('Get the desktop package'); self.download.clicked.connect(lambda:QDesktopServices.openUrl(QUrl('https://github.com/jonahsaunders/IC-Design-Studio/releases'))); links.addWidget(self.download)
        self.preview=QPushButton('Experimental desktop builds'); self.preview.clicked.connect(lambda:QDesktopServices.openUrl(QUrl('https://github.com/jonahsaunders/IC-Design-Studio/actions/workflows/build-desktop.yml?query=branch%3Aexperimental'))); links.addWidget(self.preview)
        self.logs=QPushButton('Open setup logs'); self.logs.clicked.connect(self.open_logs); links.addWidget(self.logs)
        self.refresh()
        if automatic and digital_runtime.status()['state']=='setup': QTimer.singleShot(100,self.setup)

    def toggle_details(self, visible):
        self.log.setVisible(visible); self.details.setText('Hide setup details' if visible else 'Show setup details')

    def select_mode(self):
        settings=getattr(self.parent(),'settings',None)
        if settings: settings.setValue('digital/toolchain',self.mode.currentData())
        self.pending=None; self.next_action.clear(); self.refresh(); self.changed.emit()

    def configure_custom(self):
        if self.custom: self.custom()
        self.refresh()

    def open_logs(self):
        folder=digital_runtime.state_root(); folder.mkdir(parents=True,exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def refresh(self):
        info=digital_runtime.status(); custom=self.mode.currentData()=='custom'
        if not self.process:
            self.status.setText('Using custom tools. Configure your executable paths below; other tools are discovered on PATH.' if custom else info['message'])
        available=info['state']!='unavailable' and info.get('reason')!='package_missing'
        self.start.setVisible(not custom and available); self.start.setEnabled(available and self.process is None)
        self.start.setText('Verify again' if info['state']=='ready' else 'Set up and continue' if self.pending else 'Set up and verify')
        self.enable.setVisible(os.name=='nt' and not custom and info['state']!='ready')
        self.enable.setEnabled(self.process is None)
        self.mode.setEnabled(self.process is None)
        self.custom_button.setVisible(custom); self.custom_button.setEnabled(self.custom is not None and self.process is None)
        self.download.setVisible(not custom and info['state'] in ('unavailable','error'))
        self.preview.setVisible(not custom and info['state'] in ('unavailable','error'))
        self.logs.setEnabled(digital_runtime.state_root().is_dir())

    def setup(self):
        if self.process or self.mode.currentData()=='custom': return
        manager=getattr(self.parent(),'run_manager',None)
        if manager and manager.busy:
            self.status.setText('Finish or stop the active jobs before verifying the runtime.'); return
        self.buffer=''; self.log.clear(); self.status.setText('Preparing the included tools…'); self.progress.show()
        self.close_button.setText('Stop setup')
        self.process=QProcess(self); self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(lambda error:self.failed_start() if error==QProcess.FailedToStart else None)
        args=['--digital-setup']
        if not getattr(sys,'frozen',False): args.insert(0,str(Path(__file__).resolve().parents[1]/'main.py'))
        self.refresh()
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
            self.status.setText(line[:350])
        self.log.document().setMaximumBlockCount(1500)

    def failed_start(self):
        self.log.appendPlainText('The setup worker could not start. Repair the application installation.'); self.process_finished(1)

    def process_finished(self, code, *_):
        if not self.process: return
        self.read(); self.process.deleteLater(); self.process=None
        try:
            from .model import atomic_write
            folder=digital_runtime.state_root(); folder.mkdir(parents=True,exist_ok=True)
            atomic_write(folder/'last-setup.log',self.log.toPlainText())
        except OSError:
            self.log.appendPlainText('The setup log could not be saved. Copy the details from this window before closing it.')
        self.progress.hide(); self.close_button.setText('Close'); self.refresh()
        if code==0 and digital_runtime.status()['state']=='ready':
            pending=self.pending; self.pending=None; self.next_action.clear()
            self.ready.emit(); self.changed.emit()
            if pending: QTimer.singleShot(0,pending)
        else:
            self.details.setChecked(True)
            self.status.setText('Setup did not complete. See the details below. On Windows, enable Windows Linux support if requested, then retry setup.')
        self.start.setText('Verify again' if digital_runtime.status()['state']=='ready' else 'Retry setup' if self.log.toPlainText() else 'Set up and verify')

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
        self.pending=None; self.next_action.clear()
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
        dialog=DigitalSetupDialog(studio,custom); studio._digital_setup_dialog=dialog
        dialog.ready.connect(lambda:apply_defaults(studio))
        def refresh_workspace():
            window=getattr(studio,'_digital_window',None)
            if window and window.project_id==studio.project['id']: window.shell.refresh()
        dialog.changed.connect(refresh_workspace)
    dialog.custom=custom or (lambda:configure_custom_tools(studio,dialog))
    dialog.refresh(); dialog.show(); dialog.raise_()
    if automatic and digital_runtime.status()['state']=='setup': dialog.setup()
    return dialog


def configure_custom_tools(studio, parent=None):
    dialog=QDialog(parent or studio); dialog.setWindowTitle('Custom digital tools')
    layout=QVBoxLayout(dialog)
    note=QLabel('Use your own installed tools. Empty paths are discovered on PATH. '
                'Verilator also needs a C++ compiler and make. Your paths are saved when you switch back to Included tools.')
    note.setWordWrap(True); layout.addWidget(note)
    form=QFormLayout(); layout.addLayout(form); edits={}
    for name in digital_runtime.TOOLS:
        edit=QLineEdit(studio.settings.value('engine/'+name,'')); edit.setAccessibleName(name+' executable')
        form.addRow(name,edit); edits[name]=edit
    buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel); layout.addWidget(buttons)
    buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
    if dialog.exec():
        for name,edit in edits.items(): studio.settings.setValue('engine/'+name,edit.text().strip())
        studio.settings.setValue('digital/toolchain','custom')


def startup(studio):
    from .digital_tools import selection
    if selection(studio.settings)['toolchain']=='custom': return
    info=digital_runtime.status()
    if info['state'] in ('setup','error'):
        dialog=show(studio)
        if info['state']=='setup': dialog.setup()


def ensure(window, continuation, description='your run'):
    """Defer one user request; never run a changed or closed design after setup."""
    from .digital_tools import selection
    from .model import clone
    if selection(window.studio.settings)['toolchain']=='custom' or digital_runtime.status()['state']=='ready':
        return True
    studio=window.studio; project_id=window.project_id; cid=window.cell_id
    captured=clone(window.config)
    stage=window.stage.currentData(); simulator=window.simulator.currentData()
    def resume():
        from shiboken6 import isValid
        if (not isValid(studio) or not isValid(window) or not studio.isVisible()
                or studio.project['id']!=project_id or getattr(studio,'_digital_window',None) is not window):
            return
        expected=clone(captured)
        if 'platform' not in expected:
            runtime=digital_runtime.installed()
            if runtime: expected['platform']=digital_runtime.platform(runtime)
        if (window.cell_id!=cid or window.dirty or window.config!=expected
                or window.stage.currentData()!=stage or window.simulator.currentData()!=simulator):
            window.message.setText('Digital tools are ready. Your design or run selection changed during setup; click Run when you are ready.')
            return
        window.attempt(continuation)
    dialog=show(studio,custom=window.configure_custom_tools)
    info=digital_runtime.status()
    if info['state']!='unavailable' and info.get('reason')!='package_missing':
        dialog.pending=resume; dialog.next_action.setText('After setup, Studio will continue '+description+'.')
    else:
        dialog.pending=None; dialog.next_action.clear()
    dialog.refresh()
    window.message.setText('Preparing the included digital tools. Your run will continue after setup.' if info['state']=='setup' else info['message'])
    if info['state']=='setup': dialog.setup()
    return False


def apply_defaults(studio):
    from .digital_tools import selection
    if selection(studio.settings)['toolchain']=='custom': return
    from .digital_design import config
    window=getattr(studio,'_digital_window',None)
    if window and window.project_id!=studio.project['id']: window=None
    if window and window.dirty and not window.attempt(window.apply): return
    cid=window.cell_id if window else studio.project.get('digital_cell',studio.project['top'])
    value=config(studio.project,cid)
    if value and 'platform' not in value:
        studio.commit(lambda p:digital_runtime.defaults(p,cid),'Configure included SKY130 digital platform')
        if window: window.load_sources()
