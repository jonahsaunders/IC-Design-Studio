"""Editors and captured results for the paired native testbench lessons."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel,
                               QPlainTextEdit, QTabWidget, QVBoxLayout)

from . import student_opamp_verification as verification, student_testbench as lessons, testbench_ui
from .model import io_path
from .plot import WavePlot


def _label(text=''):
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    widget.setWordWrap(True)
    return widget


def _code(name, read_only=False):
    edit = QPlainTextEdit()
    edit.setAccessibleName(name)
    edit.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
    edit.setLineWrapMode(QPlainTextEdit.NoWrap)
    edit.setTabChangesFocus(True)
    edit.setReadOnly(read_only)
    return edit


def program_editor(guide, preview=False):
    studio = guide.studio
    key = lessons.checkpoint_key(guide.lesson, guide.active_step['id'])
    project = studio.project
    lesson = guide.lesson
    cid = lessons.fixture(project, key)
    name = next(c['name'] for c in project['cells'] if c['id']==cid)
    dialog = QDialog(studio)
    dialog.setAttribute(Qt.WA_DeleteOnClose)
    dialog.setWindowTitle('Edit SPICE program')
    dialog.setWindowModality(Qt.WindowModal)
    dialog.resize(640, 440)
    layout = QVBoxLayout(dialog)
    layout.addWidget(_label('Fixture schematic · ' + name))
    layout.addWidget(_label('Enter ngspice control commands. Studio adds the fixture netlist and wraps this program in .control and .endc.'))
    dialog.code = _code('ngspice control commands')
    layout.addWidget(dialog.code, 1)
    saved = project['student_bench']['programs'].get(key, '')
    dialog.code.setPlainText(lessons.program(lessons.course()[key]) if preview else saved)
    dialog.code.setPlaceholderText('Enter your analysis and lesson_value measurement.')
    error = _label()
    error.setProperty('role', 'error')
    layout.addWidget(error)
    dialog.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    layout.addWidget(dialog.buttons)

    def save():
        try:
            guide.flush()
            guide.require_idle()
            if guide.lesson != lesson or studio.project['id'] != project['id']:
                raise ValueError('Resume this lesson before saving its program.')
            text = dialog.code.toPlainText().strip()
            if len(text) > 4096:
                raise ValueError('Use at most 4,096 characters for the lesson program.')
            if text != saved:
                def install(p):
                    p['student_bench']['programs'][key] = text
                studio.commit(install, 'Save lesson SPICE program')
            dialog.accept()
        except ValueError as exc:
            error.setText(str(exc))

    if not preview:
        dialog.buttons.accepted.connect(save)
        dialog.buttons.rejected.connect(dialog.reject)
        dialog.show()
        dialog.code.setFocus()
    return dialog


def editor(guide):
    if guide.bench_workflow.currentData()=='spice':
        return program_editor(guide)
    project = guide.studio.project
    key = lessons.checkpoint_key(guide.lesson, guide.active_step['id'])
    return testbench_ui.editor(guide.studio, lessons.saved_bench(project, key),
                               fixture_id=lessons.fixture(project, key))


def previews(guide):
    if guide.bench_workflow.currentData()=='spice':
        return [('SPICE program', 'Enter the analysis and the lesson_value measurement in the program editor.',
                 program_editor(guide, preview=True), 435)]
    studio = guide.studio
    key = lessons.checkpoint_key(guide.lesson, guide.active_step['id'])
    project, unit = studio.project, lessons.course()[key]
    cid = lessons.fixture(project, key)
    bench = lessons.solution_bench(project, cid, unit)
    items = []
    for index, title, caption in (
        (0, 'Analysis and fixture', 'Select the analysis and enter the settings for the current fixture.'),
        (4, 'Probes and startup', f'Check {", ".join(lessons.probes(unit))} in the net list.'),
        (5, 'Measurements', 'Add the measurement and enter the target limits.'),
    ):
        dialog = testbench_ui.editor(studio, bench, fixture_id=cid, preview=True)
        dialog.pages.setCurrentIndex(index)
        items.append((title, caption, dialog, 520))
    if unit['analysis']['type']=='noise':
        dialog = testbench_ui.editor(studio, bench, fixture_id=cid, preview=True)
        dialog.pages.setCurrentIndex(3)
        items.insert(1, ('Diagnostics', 'Enable input and output noise spectra.', dialog, 520))
    return items


class BenchResults(QDialog):
    def __init__(self, studio, rows, workflow):
        super().__init__(studio)
        self.rows = rows
        self.setWindowTitle('Testbench results')
        self.resize(760, 495)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.runs = QComboBox()
        self.runs.setAccessibleName('Captured testbench run')
        chosen = len(rows)-1
        for index, row in enumerate(rows):
            name = lessons.WORKFLOWS[row['result']['student_bench']['workflow']]
            self.runs.addItem(f'{index+1}. {name}')
            if row['result']['student_bench']['workflow']==workflow:
                chosen = index
        form.addRow('&Run', self.runs)
        layout.addLayout(form)
        self.reading = _label()
        self.reading.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.reading)
        self.target = _label()
        layout.addWidget(self.target)
        tabs = self.tabs = QTabWidget()
        self.plot = WavePlot()
        self.plot.dark = studio.dark
        self.phase = WavePlot()
        self.phase.dark = studio.dark
        log = self.log = _code('Native ngspice log', read_only=True)
        tabs.addTab(self.plot, 'Waveform')
        self.phase_tab = tabs.addTab(self.phase, 'Loop phase')
        tabs.addTab(self.log, 'Simulation log')
        layout.addWidget(tabs, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.save = buttons.addButton('Save plot…', QDialogButtonBox.ActionRole)
        self.save.clicked.connect(self.save_plot)
        self.plot_status = _label()
        layout.addWidget(self.plot_status)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.runs.setCurrentIndex(chosen)
        self.runs.currentIndexChanged.connect(self.show_run)
        self.show_run(chosen)

    def show_run(self, index):
        row = self.rows[index]
        result = row['result']
        captured = result['student_bench']
        key = captured.get('checkpoint',captured['lesson'])
        check = captured['check']
        value = check.get('value')
        reading = f'{value:.5g} {check.get("unit","V")}' if value is not None else 'No reading'
        status = 'Passed' if check['status']=='passed' else 'Review measurement'
        unit = lessons.course()[key]
        spec = lessons.measurement(unit)
        quantity = (f'I({spec["source"]})' if spec['kind']=='current' else 'Input RMS noise' if spec['kind']=='input_noise'
                    else ' − '.join(n for n in (spec['node'], spec.get('reference')) if n))
        metrics = {}
        reason = ''
        try:
            metrics = lessons.waveform_figures(key,result)
            lessons.waveform_figures(key,result,verify=True)
        except ValueError as exc:
            status, reason = 'Review waveform', str(exc)
        extra = ' · '.join(f'{key} {value:.3g}' if value is not None else f'{key} unavailable' for key,value in metrics.items())
        self.reading.setText(' · '.join(filter(None,(f'{status} · {quantity} = {reading}',extra))))
        self.target.setText(' '.join(filter(None,(lessons.target(unit),reason))))
        show = lessons.probes(unit)
        wave = result
        self.tabs.setTabVisible(self.phase_tab, unit.get('metric')=='loop')
        self.tabs.setTabText(0, 'Loop gain' if unit.get('metric')=='loop' else 'Waveform')
        if unit.get('metric')=='loop':
            gain, phase = verification.loop_trace(result)
            wave = {**result,'traces':{'Loop gain':gain},'plot_unit':'dB'}
            show = ['Loop gain']
            self.phase.set_result({**result,'traces':{'Loop phase':phase},'plot_unit':'°'}, ['Loop phase'])
        elif unit['analysis']['type']=='noise':
            wave = {**result,'traces':{'Input-referred':result['traces']['inoise_spectrum'],
                                       'Output':result['traces']['onoise_spectrum']}}
            show = list(wave['traces'])
        elif unit.get('reference') and len(show)==2:
            a,b = (result['traces'][n] for n in show)
            extra_traces = {'Common mode':[(x+y)/2 for x,y in zip(a,b)],
                            'Differential':[x-y for x,y in zip(a,b)]}
            wave = {**result,'traces':{**result['traces'],**extra_traces}}
            show += list(extra_traces)
        self.plot.set_result(wave,show)
        self.plot_status.clear()
        path = io_path(row['path']/'engine.log')
        try:
            self.log.setPlainText(path.read_text(encoding='utf-8', errors='replace'))
        except OSError:
            self.log.setPlainText('The saved ngspice log is unavailable.')

    def save_plot(self):
        plot = self.phase if self.tabs.currentWidget() is self.phase else self.plot
        captured = self.rows[self.runs.currentIndex()]['result']['student_bench']
        name = captured.get('checkpoint',captured['lesson'])
        path, _ = QFileDialog.getSaveFileName(self, 'Save testbench plot', name+'.png', 'PNG image (*.png)')
        if path:
            suffix = '' if path.lower().endswith('.png') else '.png'
            if plot is not self.tabs.currentWidget():
                self.tabs.setCurrentWidget(plot)
            saved = plot.grab().save(path+suffix, 'PNG')
            self.plot_status.setText('Plot saved.' if saved else 'Could not save the plot.')
