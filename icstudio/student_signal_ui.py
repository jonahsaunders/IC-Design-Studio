"""Lesson controls and accessible comparisons of captured signal measurements."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHeaderView, QLabel, QVBoxLayout)

from . import student_signal_circuits as circuits
from . import student_signal_labs as labs, student_circuit_challenges as challenges
from .student_device_labs import CONTROLS as DEVICE_CONTROLS
from .analog_widgets import fill, table
from .model import design_digest, scalar
from .plot import WavePlot


TUNING = {
    ('linearity', 'repair'): ('Edit source degeneration', ('RS', 'value', 'RS resistance (Ω)'),
                              ('VBIAS', 'value', 'VBIAS (V)')),
    ('rejection', 'repair'): ('Edit rejection circuit', ('RTAIL', 'value', 'RTAIL resistance (Ω)'),
                              ('CDEC', 'value', 'CDEC capacitance (F)')),
    ('load', 'repair'): ('Edit compensation', ('CDOM', 'value', 'CDOM capacitance (F)')),
    ('adc-ramp', 'repair'): ('Edit ladder section', ('R4', 'value', 'R4 resistance (Ω)')),
    ('chopper', 'repair'): ('Edit demodulator and filter', ('VDEMOD', 'source.delay', 'VDEMOD delay (s)'),
                            ('CLP', 'value', 'CLP capacitance (F)')),
    ('relaxation', 'corners'): ('Edit timing components', ('RT', 'native_spice.parameters.r', 'RT resistance (Ω)'),
                                ('CT', 'value', 'CT capacitance (F)')),
    ('pll', 'repair'): ('Tune the loop filter', ('RFILT', 'value', 'RFILT resistance (Ω)'),
                        ('CFILT', 'value', 'CFILT capacitance (F)')),
    ('pga', 'repair'): ('Edit gain resistors', *((f'RG{i}', 'value', f'RG{i} resistance (Ω)') for i in range(1, 4))),
    ('temperature', 'anchor'): ('Edit sensor divider', ('RFIX', 'value', 'RFIX resistance (Ω)')),
}
TUNING.update({(lab,'repair'): fields for lab,fields in challenges.CONTROLS.items()})
TUNING.update({(lab,'repair'): fields for lab,fields in DEVICE_CONTROLS.items()})
ACTIONS = {key: value[0] for key, value in TUNING.items()}
ACTIONS['temperature', 'validate'] = 'Edit calibration registers'


def _field(p, cid, name, field):
    c = next(c for c in p['cells'] if c['id'] == cid)
    device = circuits.named(c, name)
    *parents, leaf = field.split('.')
    for key in parents:
        device = device[key]
    return device, leaf


def form_fields(p, lab, step, cid):
    if (lab, step) == ('temperature', 'validate'):
        gain, offset = labs.calibration(p)
        return ([('gain', 'Gain (m°C/count)', gain), ('offset', 'Signed offset (m°C)', offset)],
                'Enter the integer coefficients calculated from the cold and hot anchor codes.')
    fields = []
    for name, field, label in TUNING[lab, step][1:]:
        part, key = _field(p, cid, name, field)
        fields.append((name, label, [part[key], 'lo' if part[key]=='0' else '0'] if field=='nets.ref' else part[key]))
    return fields, 'Enter circuit values using SI suffixes such as 4k, 330p and 10n.'


def open_form(guide, lab, step):
    studio = guide.studio
    p = studio.project
    cid = labs.focus(p, lab, step)
    identity = (p['id'], p['revision'], guide.lesson['id'], step)
    title = ACTIONS[lab, step]

    def guard():
        current = studio.project
        visible = (current['id'], current['revision'], (guide.lesson or {}).get('id'),
                   (guide.active_step or {}).get('id'))
        if visible != identity:
            raise ValueError('The project or lesson step changed. Reopen this control.')
        guide.require_idle()

    if (lab, step) == ('temperature', 'validate'):
        def apply(project, values):
            labs.set_calibration(project, int(values['gain']), int(values['offset']))
    else:
        _, *specs = TUNING[lab, step]

        def apply(project, values):
            for name, field, label in specs:
                value = values[name].strip()
                if field == 'nets.ref':
                    if value not in {'0','lo'}:
                        raise ValueError('Choose ground or the measured node lo.')
                    part, key = _field(project,cid,name,field)
                    part[key] = value
                    from .example_schematics import arrange
                    cell = next(c for c in project['cells'] if c['id']==cid)
                    for component in ('wires','labels','junctions','example_drawing'):
                        cell.pop(component,None)
                    arrange(project)
                    continue
                numeric = scalar(value)
                if numeric < 0 or (numeric == 0 and name != 'VDEMOD'):
                    raise ValueError(f'Enter a valid positive value for {label}. Clock delay can be zero.')
                part, key = _field(project, cid, name, field)
                part[key] = value

    def submit(values):
        studio.commit(lambda project: apply(project, values), title)
        guide.workspace()

    fields, note = form_fields(p, lab, step, cid)
    return studio.workflow_form(title, fields, submit, note, context_guard=guard)


ADC_CHARTS = {
    'Code counts': (0, 'ADC code', 'samples'),
    'DNL by code (LSB)': (0, 'ADC code', 'LSB'),
    'INL by transition (LSB)': (1, 'Transition index', 'LSB'),
}


def adc_wave(measurements, signal):
    start, label, unit = ADC_CHARTS[signal]
    y = measurements[signal]
    x = list(range(start, start + len(y)))
    if signal == 'Code counts':
        x = [i + edge for i in x for edge in (-.45, .45)]
        y = [count for count in y for _ in range(2)]
    return dict(settings={'type': 'dc'}, x=x, x_label=label, plot_unit=unit, traces={signal: y})


def temperature_wave(measurements, supply, signal):
    trial = sorted((r['Temperature (°C)'], r[signal]) for r in measurements.values() if r['Supply (V)'] == supply)
    return dict(settings={'type': 'dc'}, x=[t for t, _ in trial], x_label='Reference temperature (°C)',
                plot_unit='°C', traces={signal: [value for _, value in trial]})


def _format(value):
    if value is None:
        return 'Outside measurement window'
    if isinstance(value, list):
        return ', '.join(_format(item) for item in value) or 'None'
    return f'{value:.5g}' if isinstance(value, float) else str(value)


def _label(name):
    return name.replace('1p6v', '1.6 V').replace('1p8v', '1.8 V').replace('2p0v', '2.0 V').replace('-', ' ')


DEVICE_SWEEP_AXES = {'output-resistance':'Drain voltage (V)', 'body-effect':'Gate voltage (V)',
                     'transmission-gate':'Signal common-mode voltage (V)'}

CASE_LABELS = {'dc-bias':'Operating Point', 'sweep':'DC Sweep', 'body-tied':'Body Tied to Source',
               'reverse-bias':'Reverse Body Bias', 'thermal-only':'Thermal Only',
               'with-flicker':'Thermal and Flicker', 'open-loop':'Open Loop', 'closed-loop':'Closed Loop',
               'clock-feedthrough':'Clock Feedthrough', 'charge-injection':'Charge Injection', 'combined':'Combined'}


def case_label(name):
    return CASE_LABELS.get(name,_label(name))


class SignalResults(QDialog):
    def __init__(self, studio, row):
        super().__init__(studio)
        self.studio=studio
        self.setWindowTitle(row.get('name','Signal Experiment').removeprefix('Student · ')+' Results')
        self.run_path = str(row['path'])
        self.resize(910, 690)
        p, result = row['job']['project'], row['result']
        settings = row['job']['settings']
        self.lab, step = settings['lab'], settings['step']
        self.waves = labs.read_cases(p, self.lab, step, result, row['path'])
        self.measurements = result['student_signal']['measurements']
        layout = QVBoxLayout(self)
        status=f'Captured revision {result["revision"]} · {result["engine"]}'
        if design_digest(studio.project)!=design_digest(p):
            status+=' · Earlier design'
        note = QLabel(status)
        note.setTextFormat(Qt.PlainText)
        note.setWordWrap(True)
        layout.addWidget(note)
        if issue:=result['student_signal']['issue']:
            question=QLabel(issue)
            question.setTextFormat(Qt.PlainText)
            question.setWordWrap(True)
            layout.addWidget(question)
        self.readings = table(['Case', 'Measurement', 'Value'])
        self.readings.setAccessibleName('Saved signal experiment measurements')
        header = self.readings.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        grouped = self.measurements if all(isinstance(v, dict) for v in self.measurements.values()) else {
            'summary': self.measurements}
        fill(self.readings, [[case_label(case), name, _format(value)] for case, readings in grouped.items()
                             for name, value in readings.items()])
        self.readings.setWordWrap(True)
        self.readings.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.readings, 2)
        self.case, self.trace = QComboBox(), QComboBox()
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        for name, widget in [('Test Case', self.case), ('Trace', self.trace)]:
            label = QLabel(name)
            label.setBuddy(widget)
            widget.setAccessibleName(name)
            widget.setMinimumContentsLength(12)
            widget.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            form.addRow(label, widget)
        if self.lab == 'adc-ramp' and self.measurements:
            self.case.addItem('Code density', ('adc', None))
        if self.lab == 'temperature' and step == 'validate' and self.measurements:
            for supply in labs.SUPPLY_TRIALS:
                self.case.addItem(f'Calibration at {supply} V', ('temperature', float(supply)))
        for name in self.waves:
            label = case_label(name)
            if self.lab == 'temperature' and name in self.measurements:
                reading = self.measurements[name]
                label = f'{reading["Temperature (°C)"]:g} °C at {reading["Supply (V)"]:g} V'
            self.case.addItem(label, ('wave', name))
        layout.addLayout(form)
        self.plot = WavePlot()
        self.plot.dark = studio.dark
        self.plot.setAccessibleName('Plot for the selected test case and signal')
        layout.addWidget(self.plot, 3)
        self.trace_summary=QLabel()
        self.trace_summary.setTextFormat(Qt.PlainText)
        self.trace_summary.setWordWrap(True)
        self.trace_summary.setTextInteractionFlags(Qt.TextSelectableByMouse|Qt.TextSelectableByKeyboard)
        layout.addWidget(self.trace_summary)
        self.copy_confirmation=QLabel('Measurements copied.')
        self.copy_confirmation.hide()
        layout.addWidget(self.copy_confirmation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.copy_button=buttons.addButton('Copy Measurements',QDialogButtonBox.ActionRole)
        self.copy_button.setEnabled(self.readings.rowCount()>0)
        self.copy_button.clicked.connect(self.copy_measurements)
        self.copy_button.setAutoDefault(False)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.case.currentIndexChanged.connect(self.select_case)
        self.trace.currentIndexChanged.connect(self.show_plot)
        self.apply_presentation_style()
        self.select_case()
        self.case.setFocus()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'readings'):
            self.reflow_readings()

    def reflow_readings(self):
        table=self.readings
        width=table.viewport().width()
        for column, fraction in ((0,.28),(2,.22)):
            text=table.horizontalHeaderItem(column).text()
            preferred=max(table.fontMetrics().horizontalAdvance(text)+22,table.sizeHintForColumn(column))
            table.setColumnWidth(column,min(preferred,max(45,int(width*fraction))))

    def apply_presentation_style(self):
        from .student_hub_ui import student_style
        hub=getattr(self.studio,'_student_hub',None)
        action=getattr(self.studio,'study_share_action',None)
        sharing=bool(action and action.isChecked())
        scale=hub.text_scale if hub else 100
        self.setStyleSheet(student_style(self.studio.dark,max(150,scale) if sharing else scale))
        self.plot.share_text_scale=1.25 if sharing else 1
        self.plot.update()
        QTimer.singleShot(0,self.reflow_readings)

    def copy_measurements(self):
        table=self.readings
        lines=['\t'.join(table.horizontalHeaderItem(j).text() for j in range(table.columnCount()))]
        for i in range(table.rowCount()):
            lines.append('\t'.join(table.item(i,j).text() for j in range(table.columnCount())))
        QApplication.clipboard().setText('\n'.join(lines))
        self.copy_confirmation.show()

    def select_case(self):
        kind, name = self.case.currentData()
        self.trace.blockSignals(True)
        self.trace.clear()
        if kind == 'adc':
            for signal in ADC_CHARTS:
                self.trace.addItem(signal, ('derived', signal))
        elif kind == 'temperature':
            self.trace.addItem('Temperature error (°C)', ('derived', 'Error (°C)'))
            self.trace.addItem('Estimated temperature (°C)', ('derived', 'Estimate (°C)'))
        else:
            wave = self.waves[name]
            signals = list(wave['traces'])
            for signal in signals:
                self.trace.addItem(signal, ('voltage', signal))
            for signal in wave.get('currents', {}):
                self.trace.addItem(f'I({signal})', ('current', signal))
            for preferred in ('vco_hz', 'out', 'sensor', 'vin'):
                if preferred in signals:
                    self.trace.setCurrentIndex(signals.index(preferred))
                    break
            current_name = {'output-resistance':'vdrain','body-effect':'vdrain','transmission-gate':'vtg'}.get(self.lab)
            if wave['settings']['type']=='dc' and current_name:
                current_keys=list(wave.get('currents',{}))
                index=next((i for i,key in enumerate(current_keys) if key.casefold()==current_name),None)
                if index is not None:
                    self.trace.setCurrentIndex(len(signals)+index)
        self.trace.blockSignals(False)
        self.show_plot()

    def show_plot(self):
        data = self.trace.currentData()
        if not data:
            self.plot.set_result(None)
            self.trace_summary.clear()
            return
        kind, name = self.case.currentData()
        mode, signal = data
        if kind == 'adc':
            wave = adc_wave(self.measurements, signal)
        elif kind == 'temperature':
            wave = temperature_wave(self.measurements, name, signal)
        else:
            wave = self.waves[name]
            if mode == 'current':
                wave = {**wave, 'traces': wave['currents'], 'plot_unit': 'A'}
            elif self.lab == 'pll':
                if signal == 'vco_hz':
                    target = self.measurements.get(name, {}).get('Frequency target (Hz)')
                    wave = {**wave, 'plot_unit': 'Hz', 'plot_include_zero': False, 'y_reference': target}
                elif signal in ('ref_phase', 'vco_phase', 'phase_error'):
                    wave = {**wave, 'plot_unit': 'cycles'}
            if wave['settings']['type']=='dc' and self.lab in DEVICE_SWEEP_AXES:
                wave={**wave,'x_label':DEVICE_SWEEP_AXES[self.lab]}
        self.plot.set_result(wave, [signal])
        values=wave['traces'][signal]
        if values:
            unit=wave.get('plot_unit','V/√Hz' if wave['settings']['type']=='noise' else 'V')
            self.trace_summary.setText(f'{self.trace.currentText()} · {len(values)} samples · '
                                       f'Minimum {min(values):.4g} {unit} · Maximum {max(values):.4g} {unit}')
