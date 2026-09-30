"""Native mixed-signal experiment setup and captured edge inspection."""
import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QFormLayout, QLineEdit, QFileDialog, QPlainTextEdit,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)

from .model import clone, digest
from .mixed_signal import prepare, validate_project


class MixedSignalDialog(QDialog):
    def __init__(self, studio):
        super().__init__(studio); self.studio = studio; self.project_id = studio.project['id']
        self.base_config = clone(studio.project['mixed_signal']); self.revision_key = None
        self.setWindowTitle('Mixed-signal experiment'); self.resize(1100, 800)
        root = QVBoxLayout(self)
        note = QLabel('Run the native analog circuit and RTL controller together. Inspect voltages in Waveforms and clock decisions below.')
        note.setWordWrap(True); root.addWidget(note)
        tabs = QTabWidget(); root.addWidget(tabs)
        setup = QWidget(); form = QFormLayout(setup); tabs.addTab(setup, 'Experiment')
        tool_page = QWidget(); tool_form = QFormLayout(tool_page); tabs.addTab(tool_page, 'Local engines')
        self.paths = {}
        for name in ('ngspice', 'iverilog', 'vvp'):
            row = QHBoxLayout(); edit = QLineEdit(studio.settings.value('mixed_signal/'+name, ''))
            edit.setPlaceholderText('Find '+name+' on PATH'); edit.setAccessibleName(name+' executable')
            row.addWidget(edit); button = QPushButton('Browse…'); row.addWidget(button)
            def browse(_=False, edit=edit, name=name):
                path, _ = QFileDialog.getOpenFileName(self, 'Select '+name)
                if path: edit.setText(path)
            button.clicked.connect(browse); tool_form.addRow(name, row); self.paths[name] = edit
        self.voltage = QLineEdit(); self.voltage.setAccessibleName('ADC input voltage')
        self.period = QLineEdit(); self.period.setAccessibleName('Clock period in seconds')
        form.addRow('Input voltage (V)', self.voltage); form.addRow('Clock period (s, e.g. 1u)', self.period)
        scope = QLabel('This clocked flow uses local ngspice and Icarus executables. The SAR example has a behavioral comparator, sampling switch, hold capacitor and resistor DAC. It is an educational circuit, not a process-qualified ADC.')
        scope.setWordWrap(True); form.addRow(scope)
        self.config = QPlainTextEdit(); self.config.setAccessibleName('Mixed-signal bridge configuration')
        tabs.addTab(self.config, 'Bridge configuration')
        tabs.currentChanged.connect(lambda index: tabs.setFixedHeight((185,205,285)[index]))
        tabs.setFixedHeight(185)
        self.config.textChanged.connect(self.read_controls)
        row = QHBoxLayout(); root.addLayout(row)
        for title, fn in [('Analog circuit', self.analog), ('RTL controller', self.digital),
                          ('Apply configuration', self.apply), ('Run coupled simulation', self.run),
                          ('Open walkthrough', lambda: studio.open_editor_doc('MIXED_SIGNAL_SAR.md'))]:
            button = QPushButton(title)
            if title == 'Run coupled simulation': button.setProperty('role', 'primary')
            button.clicked.connect(lambda _=False, fn=fn: self.call(fn)); row.addWidget(button)
        self.runs = QComboBox(); self.runs.setAccessibleName('Mixed-signal runs'); root.addWidget(self.runs)
        self.runs.currentIndexChanged.connect(self.result)
        self.status = QLabel(); self.status.setWordWrap(True); root.addWidget(self.status)
        self.edges = QTableWidget(); self.edges.setAccessibleName('Captured mixed-signal edges')
        self.edges.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.edges.verticalHeader().hide()
        self.edges.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.edges.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel); root.addWidget(self.edges, 1)
        row = QHBoxLayout(); root.addLayout(row)
        for title, fn in [('Show analog waveforms', self.waveforms), ('Cancel selected run', self.cancel), ('Close', self.close)]:
            button = QPushButton(title); button.clicked.connect(lambda _=False, fn=fn: self.call(fn)); row.addWidget(button)
        self.config.setPlainText(json.dumps(studio.project['mixed_signal'], indent=2))
        studio.run_manager.changed.connect(self.refresh_runs); self.refresh_runs()
        self.revision_timer = QTimer(self); self.revision_timer.setInterval(300)
        self.revision_timer.timeout.connect(self.check_revision); self.revision_timer.start()

    def check_revision(self):
        if not self.isVisible(): return
        if self.studio.project['id'] != self.project_id:
            self.close(); return
        key = (id(self.studio.project), self.studio.project['revision'])
        if key != self.revision_key:
            self.revision_key = key; self.refresh_runs()

    def call(self, fn):
        try:
            if self.studio.project['id'] != self.project_id:
                raise ValueError('The project changed. Reopen Mixed-signal experiment for the current project.')
            return fn()
        except Exception as exc: self.status.setText(str(exc))

    def read_controls(self):
        try:
            c = json.loads(self.config.toPlainText()); points = c.get('stimuli', {}).get('vin')
            self.voltage.setEnabled(bool(points and len(points)==1))
            self.voltage.setText(str(points[0][1]) if points and len(points)==1 else '')
            self.period.setText(str(c['period']))
        except (ValueError, KeyError, TypeError): pass

    def apply(self):
        from .model import scalar
        s = self.studio; window = getattr(s, '_digital_window', None)
        if self.base_config != s.project.get('mixed_signal'):
            raise ValueError('The saved bridge configuration changed. Reopen the experiment before applying these fields.')
        if window and window.dirty and not window.attempt(window.apply):
            raise ValueError('Apply or correct the RTL source edits before running.')
        if not s.flush_inspector(): raise ValueError('Correct the current property edit first.')
        c = json.loads(self.config.toPlainText()); c['period'] = scalar(self.period.text())
        if self.voltage.isEnabled(): c['stimuli']['vin'] = [[0., scalar(self.voltage.text())]]
        proposal = clone(s.project); proposal['mixed_signal'] = c; validate_project(proposal)
        if c != s.project['mixed_signal']:
            s.commit(lambda p: p.update(mixed_signal=clone(c)), 'Mixed-signal configuration')
        self.base_config = clone(c)
        self.config.setPlainText(json.dumps(c, indent=2))
        for name, edit in self.paths.items(): s.settings.setValue('mixed_signal/'+name, edit.text().strip())

    def run(self):
        self.apply(); s = self.studio
        job = prepare(s.project, {name: edit.text().strip() for name, edit in self.paths.items()})
        row = s.run_manager.enqueue(job, s.jobs_dir, 'Mixed-signal conversion')
        self.refresh_runs(); self.runs.setCurrentIndex(self.runs.findData(row['id']))

    def selected(self):
        return next((r for r in self.studio.run_manager.rows if r['id']==self.runs.currentData()), None)

    def refresh_runs(self):
        if self.studio.project['id'] != self.project_id:
            self.status.setText('Project changed. Close and reopen this experiment.'); return
        selected = self.runs.currentData(); self.runs.blockSignals(True); self.runs.clear()
        for row in self.studio.run_manager.rows:
            if (row['job']['settings'].get('type') == 'mixed_signal' and
                    row['job']['project']['id'] == self.project_id):
                self.runs.addItem(row['name']+' · '+row['state'], row['id'])
        self.runs.setCurrentIndex(max(0, self.runs.findData(selected))); self.runs.blockSignals(False); self.result()

    def result(self):
        row = self.selected(); self.edges.clear(); self.edges.setRowCount(0)
        if not row:
            self.status.setText('Set the input and clock, then run. Default: 0.93 V → code 8.'); return
        result = row.get('result')
        if not result:
            self.status.setText(row['state']+' · '+str(row.get('progress', 0))+'%\n'+row.get('log','')[-1500:]); return
        from .model import design_digest
        current = result['design_hash'] == design_digest(self.studio.project)
        rows = result['mixed_signal']['samples']; outputs = row['job']['project']['mixed_signal']['outputs']
        input_ports = row['job']['project']['mixed_signal']['inputs']
        headers = ['Edge', 'Time (µs)']+[p['port'] for p in input_ports]+[o['port'] for o in outputs]
        self.edges.setColumnCount(len(headers)); self.edges.setHorizontalHeaderLabels(headers); self.edges.setRowCount(len(rows))
        for i, sample in enumerate(rows):
            inputs = [str(sample['inputs'][p['port']]) if sample['sampled'].get(p['port'],True) else '—' for p in input_ports]
            values = [str(sample['edge']), f'{sample["time"]*1e6:.3f}']+inputs+[str(sample['outputs'][o['port']]) for o in outputs]
            for j, text in enumerate(values): self.edges.setItem(i,j,QTableWidgetItem(text))
        text = ('Current design' if current else 'Captured earlier design — rerun after edits')+' · conversion trace retained.'
        verification = result['mixed_signal'].get('verification')
        if verification:
            text += ' SAR checks: '+verification['status']+' · code '+str(verification['code'])
            failures = [v['name'] for v in verification['checks'] if not v['passed']]
            if failures: text += ' · '+', '.join(failures)
        self.status.setText(text)

    def waveforms(self):
        row = self.selected()
        if row and row.get('result'):
            index = next((i for i,r in enumerate(self.studio.jobs) if r==row['result']), None)
            if index is None: self.studio.add_result(row['result'])
            else: self.studio.run_combo.setCurrentIndex(index)
            self.studio.results_dock.show(); self.studio.results_tabs.setCurrentIndex(0)

    def cancel(self):
        row = self.selected()
        if row: self.studio.run_manager.cancel([row])

    def analog(self):
        s = self.studio; s.leave_digital_workspace(); s.cid = s.project['mixed_signal']['analog_cell']; s.mode_combo.setCurrentIndex(0); s.refresh(True); self.hide()

    def digital(self):
        s = self.studio; s.cid = s.project['mixed_signal']['digital_cell']; s.digital_window().workspace.switch_cell(s.cid); self.hide()


def show(studio):
    if 'mixed_signal' not in studio.project:
        raise ValueError('Open the SAR ADC example or a project with a mixed-signal configuration.')
    old = getattr(studio, '_mixed_signal_dialog', None)
    if old is not None:
        old.close(); old.deleteLater()
    dialog = MixedSignalDialog(studio); studio._mixed_signal_dialog = dialog; dialog.show(); return dialog


def new_sar(studio):
    from .sar_example import sar_project
    if not studio.idle_edit() or not studio.maybe_save(): return
    studio.set_project(sar_project()); studio.refresh(True); return show(studio)


def install(studio):
    menu = studio.task_menus['Simulate'].addMenu('Mixed signal')
    studio.action(menu, 'New SAR ADC example', lambda: new_sar(studio))
    studio.action(menu, 'Mixed-signal experiment…', lambda: show(studio))
    studio.action(menu, 'SAR ADC walkthrough', lambda: studio.open_editor_doc('MIXED_SIGNAL_SAR.md'))
