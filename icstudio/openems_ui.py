"""Cancellable optional external solver, with no application-thread FDTD work."""
import json
import os
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import (QObject, Signal, QRunnable, QThreadPool, QProcess,
                            QProcessEnvironment, QTimer, QUrl, QCoreApplication)
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QDoubleSpinBox, QSpinBox,
    QCheckBox, QPlainTextEdit, QScrollArea, QWidget, QComboBox, QProgressBar)

from . import openems_backend as backend, inductor_em, openems_runtime
from .model import clone, uid, atomic_write


class Prepared(QObject):
    ready = Signal(object, str)


class Preparation(QRunnable):
    def __init__(self, args, cancelled):
        super().__init__(); self.args = args; self.cancelled = cancelled; self.signals = Prepared()

    def run(self):
        try: self.signals.ready.emit(backend.prepare(*self.args, self.cancelled.is_set), '')
        except Exception as exc: self.signals.ready.emit(None, str(exc))


class OpenEMSJob(QObject):
    changed = Signal(str)
    output = Signal(str)
    completed = Signal(object, str)
    _active = None

    def __init__(self, parent=None):
        super().__init__(parent or QCoreApplication.instance())
        self.process = QProcess(self); self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.timer = QTimer(self); self.timer.setInterval(200); self.timer.timeout.connect(self.check_time)
        self.cancelled = threading.Event(); self.running = False; self.directory = None
        self.worker = None; self.prepared = None; self.pending = []; self.columns = {}
        self.log = ''; self.log_file = None; self.log_size = 0; self.mode = ''; self.failure = ''
        self.ready_probe = False; self.started = 0.; self.deadline = 0.; self.kill_at = None
        QCoreApplication.instance().aboutToQuit.connect(self.shutdown)

    def start(self, executable, project=None, cid=None, did=None, scope='context', values=None, root=None):
        if self.running: raise ValueError('An openEMS operation is already running.')
        if OpenEMSJob._active is not None: raise ValueError('Another openEMS operation is active. Cancel it or wait for completion.')
        if not executable.strip() or not Path(executable).is_file():
            raise ValueError('Choose the Python executable from an environment with openEMS and CSXCAD installed.')
        # Keep the venv path: resolving a Python symlink can select the base
        # interpreter and silently lose the solver environment's packages.
        self.opts = backend.settings(values or {}); self.executable = str(Path(executable).absolute())
        self.running = True; OpenEMSJob._active = self; self.cancelled.clear(); self.failure = ''
        self.columns = {}; self.prepared = None; self.directory = None; self.probe_only = project is None
        self.mode = ''; self.pending = []
        self.started = time.monotonic(); self.deadline = self.started+(30 if self.probe_only else self.opts['timeout_s'])
        self.kill_at = None; self.timer.start()
        if self.probe_only: self.launch_probe(); return
        self.directory = Path(root)/project['id']/('openems_'+uid())
        self.status('Preparing physical geometry…')
        self.worker = Preparation((clone(project), cid, did, scope, self.opts, self.directory), self.cancelled)
        self.worker.signals.ready.connect(self.preparation_finished)
        QThreadPool.globalInstance().start(self.worker)

    def status(self, text):
        self.changed.emit(text)
        if self.directory is not None and self.directory.exists():
            try: atomic_write(self.directory/'status.json', json.dumps(dict(status=text, elapsed_s=time.monotonic()-self.started)))
            except OSError as exc: self.output.emit('Could not save job status: '+str(exc))

    def preparation_finished(self, data, error):
        self.worker = None
        if not self.running: return
        if self.cancelled.is_set(): self.finish(None, self.failure or 'Cancelled.'); return
        if error: self.finish(None, error); return
        self.prepared = data; self.pending = backend.stages(self.opts); self.launch_probe()

    def launch_probe(self):
        self.mode = 'probe'; self.ready_probe = False; self.probe_versions = None
        self.probe_deadline = time.monotonic()+30
        self.status('Checking openEMS Python installation…')
        self.launch(['--probe'])

    def launch(self, args):
        if self.cancelled.is_set(): self.finish(None, self.failure or 'Cancelled.'); return
        self.log = ''; self.line_buffer = ''; self.log_size = 0
        if self.directory:
            self.log_file = (self.directory/(self.mode+'.log')).open('w', encoding='utf-8')
        driver = self.directory/'driver.py' if self.directory else backend.DRIVER
        environment = QProcessEnvironment()
        for key, value in openems_runtime.environment(self.executable).items():
            environment.insert(key, value)
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(str(self.directory or backend.DRIVER.parent))
        self.process.start(self.executable, ['-u', str(driver), *args])

    def read_output(self):
        text = bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        self.log_size += len(text)
        if self.log_size > 100_000_000:
            self.cancel('Solver output exceeded the 100 MB per-stage limit.'); return
        if self.log_file: self.log_file.write(text); self.log_file.flush()
        self.log = (self.log+text)[-200000:]; self.output.emit(text)
        self.line_buffer += text
        while '\n' in self.line_buffer:
            line, self.line_buffer = self.line_buffer.split('\n', 1)
            if line.startswith('ICSTUDIO_EM:'):
                try: event = json.loads(line[len('ICSTUDIO_EM:'):])
                except (ValueError, TypeError): continue
                if event.get('state') == 'ready':
                    self.ready_probe = True; self.probe_versions = event.get('versions', {})
                elif event.get('state') == 'mesh':
                    self.status(f'{self.mode}: {event.get("cells", 0):,} cells. Running solver…')
        if len(self.line_buffer) > 200000: self.line_buffer = self.line_buffer[-200000:]

    def process_error(self, error):
        if error == QProcess.FailedToStart and self.running:
            self.finish(None, 'Could not start solver Python: '+self.process.errorString())

    def process_finished(self, code, status):
        self.read_output()
        if self.log_file: self.log_file.close(); self.log_file = None
        if not self.running: return
        if self.cancelled.is_set(): self.finish(None, self.failure or 'Cancelled.'); return
        if status != QProcess.NormalExit or code != 0:
            self.finish(None, f'{self.mode} failed (exit {code}). Inspect the log below and the run folder.'); return
        if self.mode == 'probe':
            if not self.ready_probe: self.finish(None, 'Python did not confirm a usable openEMS installation.'); return
            if self.probe_only:
                self.finish(dict(installation=self.probe_versions), ''); return
        else:
            try:
                scale, port = self.current
                self.columns[self.mode] = backend.check_completion(self.log, self.directory, self.prepared, scale, port)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                self.finish(None, str(exc)); return
        if self.pending:
            self.current = self.pending.pop(0); scale, port = self.current
            self.mode = backend.stage_name(scale, port)
            self.status(self.mode+': building mesh and exciting terminal '+('P' if port == 1 else 'N')+'…')
            self.launch(['--model', str(self.directory/'model.json'), '--scale', str(scale), '--port', str(port)])
        else:
            try: result = backend.finish(self.directory, self.prepared, self.columns)
            except (ValueError, OSError, KeyError, TypeError, OverflowError) as exc: self.finish(None, str(exc)); return
            self.finish(result, '')

    def check_time(self):
        if not self.running: return
        now = time.monotonic()
        if not self.cancelled.is_set() and (now > self.deadline or self.mode == 'probe' and now > self.probe_deadline):
            self.cancel('Solver time limit exceeded. No results were attached.')
        if self.kill_at is not None and now >= self.kill_at:
            self.kill_at = None
            if self.process.state() != QProcess.NotRunning: self.process.kill()

    def cancel(self, reason='Cancelled. No results were attached.'):
        if not self.running: return
        self.failure = reason; self.cancelled.set(); self.pending = []; self.status('Stopping openEMS…')
        if self.process.state() != QProcess.NotRunning:
            self.process.terminate(); self.kill_at = time.monotonic()+2
        elif self.worker is None: self.finish(None, reason)

    def finish(self, result, error):
        if not self.running: return
        if self.log_file: self.log_file.close(); self.log_file = None
        self.timer.stop(); self.running = False
        if OpenEMSJob._active is self: OpenEMSJob._active = None
        self.status(error or ('Installation ready.' if self.probe_only else 'Simulation completed.'))
        self.completed.emit(result, error)

    def shutdown(self):
        self.cancel()
        if self.process.state() != QProcess.NotRunning:
            self.process.kill(); self.process.waitForFinished(2000)


class OpenEMSDialog(QDialog):
    def __init__(self, characterization):
        super().__init__(characterization); self.characterization = characterization
        self.owner = characterization.owner; self.closed = False
        self.setWindowTitle('Simulate inductor with openEMS'); self.resize(720, 650)
        layout = QVBoxLayout(self)
        title = QLabel('Simulate your inductor'); title.setStyleSheet('font-size: 20px; font-weight: 600')
        layout.addWidget(title)
        note = QLabel('Choose a frequency range and run. Studio checks the solver, builds the model, and adds the results to your inductor.')
        note.setWordWrap(True); layout.addWidget(note)
        self.setup_status = QLabel(); self.setup_status.setWordWrap(True); layout.addWidget(self.setup_status)
        self.profile_status = QLabel(); self.profile_status.setWordWrap(True); layout.addWidget(self.profile_status)
        self.profile_button = QPushButton('Set up physical layers…'); self.profile_button.clicked.connect(self.edit_profile)
        layout.addWidget(self.profile_button)
        self.download = QPushButton('Get the ready-to-run desktop app')
        self.download.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://github.com/jonahsaunders/IC-Design-Studio/releases')))
        layout.addWidget(self.download)
        form = QFormLayout(); layout.addLayout(form)
        self.fields = {}
        try:
            saved = json.loads(str(self.owner.settings.value('engine/openems_settings', '{}')))
            saved = backend.settings(saved)
        except (ValueError, TypeError): saved = backend.settings({})
        def field(key, label, scale, low, high, target):
            widget = QSpinBox() if type(backend.DEFAULTS[key]) is int else QDoubleSpinBox()
            if isinstance(widget, QDoubleSpinBox): widget.setDecimals(6 if scale == 1e-9 else 3)
            widget.setRange(low, high); widget.setValue(saved[key]*scale); widget.setAccessibleName(label)
            self.fields[key] = (widget, scale); target.addRow(label, widget)
        field('f_start_hz', 'From (GHz)', 1e-9, .000001, 1000, form)
        field('f_stop_hz', 'To (GHz)', 1e-9, .000001, 1000, form)
        self.quality = QComboBox(); self.quality.addItems(['Verified result — compare two meshes', 'Quick preview — one mesh'])
        self.quality.setAccessibleName('Simulation quality'); form.addRow('Quality', self.quality)
        self.quality_note = QLabel(); self.quality_note.setWordWrap(True); layout.addWidget(self.quality_note)
        fixture = QLabel('Results include the two terminal ports and a common top reference plane. Use physical layer data for your process.')
        fixture.setWordWrap(True); layout.addWidget(fixture)
        self.advanced_toggle = QPushButton('Advanced settings'); self.advanced_toggle.setCheckable(True)
        layout.addWidget(self.advanced_toggle)
        self.advanced = QScrollArea(); self.advanced.setWidgetResizable(True); self.advanced.setMinimumHeight(170)
        advanced_widget = QWidget(); advanced_form = QFormLayout(advanced_widget); self.advanced.setWidget(advanced_widget)
        layout.addWidget(self.advanced); self.advanced.hide(); self.advanced_toggle.toggled.connect(self.advanced.setVisible)
        executable, _ = openems_runtime.discover(str(self.owner.settings.value('engine/openems_python', '')))
        self.python = QLineEdit(executable); self.python.setAccessibleName('openEMS Python executable')
        self.python.setPlaceholderText('Detected automatically in desktop downloads')
        row = QHBoxLayout(); row.addWidget(self.python)
        browse = QPushButton('Browse…'); browse.clicked.connect(self.browse); row.addWidget(browse)
        self.check = QPushButton('Check installation'); self.check.clicked.connect(lambda: self.start(True)); row.addWidget(self.check)
        advanced_form.addRow('Solver Python', row)
        included = QPushButton('Use included solver'); included.clicked.connect(self.use_included); advanced_form.addRow(included)
        fields = [('samples', 'Frequency samples', 1, 2, 10000), ('mesh_um', 'Metal-area cell size (µm)', 1, .001, 1000),
                  ('margin_um', 'Side and bottom margin (µm)', 1, 1, 10000), ('reference_clearance_um', 'Top reference clearance (µm)', 1, 1, 10000),
                  ('end_db', 'Energy decay target (dB)', 1, -100, -20), ('max_steps', 'Maximum time steps', 1, 100, 100000000),
                  ('max_cells', 'Maximum mesh cells', 1, 1000, 20000000), ('timeout_s', 'Total time limit (seconds)', 1, 1, 86400),
                  ('threads', 'Solver threads', 1, 1, 64), ('mesh_tolerance', 'Maximum Z and R mesh change (%)', 100, .1, 50)]
        for args in fields: field(*args, advanced_form)
        self.mesh_check = QCheckBox('Verify with a finer mesh (four solver runs)'); self.mesh_check.setChecked(saved['mesh_check'])
        advanced_form.addRow(self.mesh_check)
        self.quality.setCurrentIndex(0 if saved['mesh_check'] else 1)
        self.quality.currentIndexChanged.connect(lambda index: self.mesh_check.setChecked(index == 0))
        self.mesh_check.toggled.connect(lambda checked: self.quality.setCurrentIndex(0 if checked else 1))
        self.quality.currentIndexChanged.connect(self.update_quality); self.update_quality()
        self.status = QLabel('Ready when you are.'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.progress = QProgressBar(); self.progress.hide(); layout.addWidget(self.progress)
        self.log_toggle = QPushButton('Show run details'); self.log_toggle.setCheckable(True); layout.addWidget(self.log_toggle)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(1000)
        self.log.setAccessibleName('openEMS progress log'); self.log.setMinimumHeight(120); layout.addWidget(self.log)
        self.log.hide(); self.log_toggle.toggled.connect(self.log.setVisible)
        row = QHBoxLayout(); self.run = QPushButton('Run simulation'); self.run.setDefault(True)
        self.run.clicked.connect(lambda: self.start(False)); row.addWidget(self.run)
        self.cancel_button = QPushButton('Cancel run'); self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(lambda: self.job.cancel()); row.addWidget(self.cancel_button)
        self.folder = QPushButton('Open run folder'); self.folder.setEnabled(False); self.folder.clicked.connect(self.open_folder); row.addWidget(self.folder)
        close = QPushButton('Close'); close.clicked.connect(self.reject); row.addWidget(close); layout.addLayout(row)
        self.job = OpenEMSJob(); self.job.changed.connect(self.changed); self.job.output.connect(self.append_log); self.job.completed.connect(self.completed)
        self.python.textChanged.connect(self.refresh_setup); self.refresh_setup()
        self.resize(min(self.width(), self.screen().availableGeometry().width()-40), min(self.height(), self.screen().availableGeometry().height()-60))

    def update_quality(self):
        self.quality_note.setText('Checks both terminal excitations at two mesh sizes before attaching results.' if self.quality.currentIndex() == 0 else
                                 'Faster exploration. Mesh convergence is not checked; use Verified result before relying on the model.')

    def refresh_setup(self):
        self.setup_status.setText(openems_runtime.describe(self.python.text().strip()))
        self.download.setVisible(not self.python.text().strip())
        problems = getattr(self.characterization, 'solver_problems', [])
        self.profile_status.setText('Physical layers need attention: '+('; '.join(problems[:2])) if problems else 'Physical layers are ready for the selected geometry.')
        self.profile_button.setText('Set up physical layers…' if problems else 'Review physical layers…')

    def edit_profile(self):
        self.characterization.edit_profile()
        profile = getattr(self.characterization, '_profile', None)
        if profile:
            profile.finished.connect(self.refresh_setup)

    def use_included(self):
        executable = openems_runtime.python_path(openems_runtime.bundled_root())
        if executable.is_file(): self.python.setText(str(executable))
        else: self.status.setText('This source checkout has no bundled solver. Use a desktop download, or select an existing solver Python.')

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select solver Python executable', self.python.text())
        if path: self.python.setText(path)

    def changed(self, text):
        self.status.setText(text)
        if self.job.running:
            self.progress.show()
            if self.job.mode.startswith(('base-', 'fine-')):
                stages = [backend.stage_name(s, p) for s, p in backend.stages(self.job.opts)]
                self.progress.setRange(0, len(stages)); self.progress.setValue(stages.index(self.job.mode))
                self.progress.setFormat('Excitation '+str(stages.index(self.job.mode)+1)+' of '+str(len(stages)))
            else: self.progress.setRange(0, 0)

    def start(self, probe):
        if self.closed: return
        try:
            values = {key: widget.value()/scale if type(backend.DEFAULTS[key]) is float else widget.value() for key, (widget, scale) in self.fields.items()}
            values['mesh_check'] = self.mesh_check.isChecked()
            self.log.clear()
            c = self.characterization
            self.job.start(self.python.text(), None if probe else c.project(), c.cid, c.did,
                           c.scope.currentData(), values, self.owner.jobs_dir)
            self.owner.settings.setValue('engine/openems_python', self.python.text())
            self.owner.settings.setValue('engine/openems_settings', json.dumps(values))
            self.run.setEnabled(False); self.check.setEnabled(False); self.cancel_button.setEnabled(True)
            self.profile_button.setEnabled(False); self.advanced.setEnabled(False); self.quality.setEnabled(False)
            for key in ('f_start_hz', 'f_stop_hz'): self.fields[key][0].setEnabled(False)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.status.setText(str(exc)); self.refresh_setup()

    def append_log(self, text):
        if not self.closed:
            self.log.moveCursor(QTextCursor.End); self.log.insertPlainText(text[-20000:]); self.log.ensureCursorVisible()

    def completed(self, result, error):
        if self.closed: return
        self.run.setEnabled(True); self.check.setEnabled(True); self.cancel_button.setEnabled(False)
        self.profile_button.setEnabled(True); self.advanced.setEnabled(True); self.quality.setEnabled(True)
        for key in ('f_start_hz', 'f_stop_hz'): self.fields[key][0].setEnabled(True)
        self.progress.setRange(0, 1); self.progress.setValue(0 if error else 1)
        self.progress.setFormat('Stopped' if error else 'Complete')
        self.folder.setEnabled(self.job.directory is not None and self.job.directory.exists())
        if error:
            self.status.setText(error); self.log_toggle.setChecked(True); return
        if 'installation' in result:
            self.status.setText('Installation ready: '+', '.join(k+' '+v for k, v in result['installation'].items())); return
        try:
            c = self.characterization; c.project()
            if not self.owner.idle_edit(): raise ValueError('The project is busy. Import results.json from the run folder when ready.')
            self.owner.commit(lambda p: inductor_em.install_results(p, c.cid, c.did, result), 'Run openEMS inductor characterization')
            c.refresh(); self.refresh_setup()
            self.status.setText('Results added to your inductor. Close this window to see inductance, resistance and Q versus frequency.')
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.status.setText('Simulation finished; results were not attached. '+str(exc)+' Files remain in the run folder.')

    def open_folder(self):
        if self.job.directory: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.job.directory)))

    def done(self, result):
        self.closed = True; self.job.cancel(); super().done(result)
