"""Cancellable optional external solver, with no application-thread FDTD work."""
import json
import os
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import (QObject, Signal, QRunnable, QThreadPool, QProcess,
                            QProcessEnvironment, QTimer, QUrl, QCoreApplication)
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QDoubleSpinBox, QSpinBox,
    QCheckBox, QPlainTextEdit, QScrollArea, QWidget)

from . import openems_backend as backend, inductor_em
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
        environment = QProcessEnvironment.systemEnvironment()
        # A frozen application's Python/Qt variables must not contaminate an
        # independently installed solver environment.
        if getattr(sys, 'frozen', False):
            for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
                environment.remove(key)
            if environment.contains('LD_LIBRARY_PATH_ORIG'):
                environment.insert('LD_LIBRARY_PATH', environment.value('LD_LIBRARY_PATH_ORIG'))
            else: environment.remove('LD_LIBRARY_PATH')
        environment.insert('PYTHONUNBUFFERED', '1'); environment.insert('MPLBACKEND', 'Agg')
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
        self.setWindowTitle('Run openEMS — inductor characterization'); self.resize(760, 760)
        layout = QVBoxLayout(self)
        note = QLabel('Simulate P and N using two ports to a common top reference plane. Results include the fixture; no de-embedding is applied. A verified physical PDK profile is required.')
        note.setWordWrap(True); layout.addWidget(note)
        row = QHBoxLayout(); self.python = QLineEdit(str(self.owner.settings.value('engine/openems_python', os.environ.get('ICSTUDIO_OPENEMS_PYTHON', ''))))
        self.python.setPlaceholderText('Python executable with openEMS + CSXCAD installed'); self.python.setAccessibleName('openEMS Python executable')
        row.addWidget(self.python); browse = QPushButton('Browse…'); browse.clicked.connect(self.browse); row.addWidget(browse)
        self.check = QPushButton('Check installation'); self.check.clicked.connect(lambda: self.start(True)); row.addWidget(self.check); layout.addLayout(row)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); form_widget = QWidget(); form = QFormLayout(form_widget); scroll.setWidget(form_widget); layout.addWidget(scroll, 2)
        self.fields = {}
        fields = [('f_start_hz', 'Start frequency (GHz)', 1e-9, .000001, 1000), ('f_stop_hz', 'Stop frequency (GHz)', 1e-9, .000001, 1000),
                  ('samples', 'Frequency samples', 1, 2, 10000), ('mesh_um', 'Metal-area cell size (µm)', 1, .001, 1000),
                  ('margin_um', 'Side and bottom margin (µm)', 1, 1, 10000), ('reference_clearance_um', 'Top reference clearance (µm)', 1, 1, 10000),
                  ('end_db', 'Energy decay target (dB)', 1, -100, -20), ('max_steps', 'Maximum time steps', 1, 100, 100000000),
                  ('max_cells', 'Maximum mesh cells', 1, 1000, 20000000), ('timeout_s', 'Total time limit (seconds)', 1, 1, 86400),
                  ('threads', 'Solver threads', 1, 1, 64), ('mesh_tolerance', 'Maximum Z and R mesh change (%)', 100, .1, 50)]
        for key, label, scale, low, high in fields:
            field = QSpinBox() if type(backend.DEFAULTS[key]) is int else QDoubleSpinBox()
            if isinstance(field, QDoubleSpinBox): field.setDecimals(6 if scale == 1e-9 else 3)
            field.setRange(low, high); field.setValue(backend.DEFAULTS[key]*scale); field.setAccessibleName(label)
            self.fields[key] = (field, scale); form.addRow(label, field)
        self.mesh_check = QCheckBox('Verify with a finer mesh (four solver runs)'); self.mesh_check.setChecked(True); layout.addWidget(self.mesh_check)
        loss_note = QLabel('Dielectric loss tangent uses equivalent constant conductivity at the band centre. Mesh agreement does not establish boundary or fixture independence. Memory grows with mesh cells; 2 million cells may need several hundred MB.')
        loss_note.setWordWrap(True); form.addRow(loss_note)
        self.status = QLabel('Choose a solver Python environment, then check installation or run.'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(1000); self.log.setAccessibleName('openEMS progress log'); layout.addWidget(self.log, 1)
        row = QHBoxLayout(); self.run = QPushButton('Run openEMS'); self.run.clicked.connect(lambda: self.start(False)); row.addWidget(self.run)
        self.cancel_button = QPushButton('Cancel run'); self.cancel_button.setEnabled(False); self.cancel_button.clicked.connect(lambda: self.job.cancel()); row.addWidget(self.cancel_button)
        self.folder = QPushButton('Open run folder'); self.folder.setEnabled(False); self.folder.clicked.connect(self.open_folder); row.addWidget(self.folder)
        close = QPushButton('Close'); close.clicked.connect(self.reject); row.addWidget(close); layout.addLayout(row)
        self.job = OpenEMSJob(); self.job.changed.connect(self.status.setText); self.job.output.connect(self.append_log); self.job.completed.connect(self.completed)
        self.resize(min(self.width(), self.screen().availableGeometry().width()-40), min(self.height(), self.screen().availableGeometry().height()-60))

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select solver Python executable', self.python.text())
        if path: self.python.setText(path)

    def start(self, probe):
        if self.closed: return
        try:
            values = {key: field.value()/scale if type(backend.DEFAULTS[key]) is float else field.value() for key, (field, scale) in self.fields.items()}
            values['mesh_check'] = self.mesh_check.isChecked()
            self.log.clear()
            c = self.characterization
            self.job.start(self.python.text(), None if probe else c.project(), c.cid, c.did,
                           c.scope.currentData(), values, self.owner.jobs_dir)
            self.owner.settings.setValue('engine/openems_python', self.python.text())
            self.run.setEnabled(False); self.check.setEnabled(False); self.cancel_button.setEnabled(True)
        except (ValueError, OSError, KeyError, TypeError) as exc: self.status.setText(str(exc))

    def append_log(self, text):
        if not self.closed:
            self.log.moveCursor(self.log.textCursor().End); self.log.insertPlainText(text[-20000:]); self.log.ensureCursorVisible()

    def completed(self, result, error):
        if self.closed: return
        self.run.setEnabled(True); self.check.setEnabled(True); self.cancel_button.setEnabled(False)
        self.folder.setEnabled(self.job.directory is not None and self.job.directory.exists())
        if error: self.status.setText(error); return
        if 'installation' in result:
            self.status.setText('Installation ready: '+', '.join(k+' '+v for k, v in result['installation'].items())); return
        try:
            c = self.characterization; c.project()
            # install_results rechecks geometry, scope, PDK revision and physical
            # materials inside the undoable edit. No stale attachment is allowed.
            if not self.owner.idle_edit(): raise ValueError('The project is busy. Import results.json from the run folder when ready.')
            self.owner.commit(lambda p: inductor_em.install_results(p, c.cid, c.did, result), 'Run openEMS inductor characterization')
            c.refresh(); self.status.setText('Results attached: fixture-inclusive L(f), R(f), Q(f) and any bracketed resonance. Full model and logs are in the run folder.')
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.status.setText('Simulation finished; results were not attached. '+str(exc)+' Files remain in the run folder.')

    def open_folder(self):
        if self.job.directory: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.job.directory)))

    def done(self, result):
        self.closed = True; self.job.cancel(); super().done(result)
