"""Lesson controls and accessible comparisons of captured signal measurements."""

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHeaderView, QLabel, QVBoxLayout

from . import student_signal_circuits as circuits
from . import student_signal_labs as labs, student_circuit_challenges as challenges
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
    ('pga', 'repair'): ('Edit gain resistors', *((f'RG{i}', 'value', f'RG{i} resistance (Ω)') for i in range(1, 4))),
    ('temperature', 'anchor'): ('Edit sensor divider', ('RFIX', 'value', 'RFIX resistance (Ω)')),
}
TUNING.update({(lab,'repair'): fields for lab,fields in challenges.CONTROLS.items()})
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


class SignalResults(QDialog):
    def __init__(self, studio, row):
        super().__init__(studio)
        self.setWindowTitle('Signal experiment results')
        self.resize(910, 690)
        p, result = row['job']['project'], row['result']
        settings = row['job']['settings']
        self.lab, step = settings['lab'], settings['step']
        self.waves = labs.read_cases(p, self.lab, step, result, row['path'])
        self.measurements = result['student_signal']['measurements']
        layout = QVBoxLayout(self)
        status = ('Saved experiment' if design_digest(studio.project) == design_digest(p)
                  else 'Saved experiment from an earlier design revision')
        note = QLabel(status + '. ' + result['student_signal']['issue'])
        note.setWordWrap(True)
        layout.addWidget(note)
        self.readings = table(['Case', 'Measurement', 'Value'])
        self.readings.setAccessibleName('Saved signal experiment measurements')
        header = self.readings.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        grouped = self.measurements if all(isinstance(v, dict) for v in self.measurements.values()) else {
            'summary': self.measurements}
        fill(self.readings, [[_label(case), name, _format(value)] for case, readings in grouped.items()
                             for name, value in readings.items()])
        layout.addWidget(self.readings, 2)
        self.case, self.trace = QComboBox(), QComboBox()
        form = QFormLayout()
        for name, widget in [('Test case', self.case), ('Plot', self.trace)]:
            label = QLabel(name)
            label.setBuddy(widget)
            widget.setAccessibleName(name)
            form.addRow(label, widget)
        if self.lab == 'adc-ramp' and self.measurements:
            self.case.addItem('Code density', ('adc', None))
        if self.lab == 'temperature' and step == 'validate' and self.measurements:
            for supply in labs.SUPPLY_TRIALS:
                self.case.addItem(f'Calibration at {supply} V', ('temperature', float(supply)))
        for name in self.waves:
            label = _label(name)
            if self.lab == 'temperature' and name in self.measurements:
                reading = self.measurements[name]
                label = f'{reading["Temperature (°C)"]:g} °C at {reading["Supply (V)"]:g} V'
            self.case.addItem(label, ('wave', name))
        layout.addLayout(form)
        self.plot = WavePlot()
        self.plot.dark = studio.dark
        self.plot.setAccessibleName('Plot for the selected test case and signal')
        layout.addWidget(self.plot, 3)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.case.currentIndexChanged.connect(self.select_case)
        self.trace.currentIndexChanged.connect(self.show_plot)
        self.select_case()

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
            for signal in wave['traces']:
                self.trace.addItem(signal, ('voltage', signal))
            for signal in wave.get('currents', {}):
                self.trace.addItem(f'I({signal})', ('current', signal))
            for preferred in ('out', 'sensor', 'vin'):
                index = self.trace.findData(('voltage', preferred))
                if index >= 0:
                    self.trace.setCurrentIndex(index)
                    break
        self.trace.blockSignals(False)
        self.show_plot()

    def show_plot(self):
        data = self.trace.currentData()
        if not data:
            self.plot.set_result(None)
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
        self.plot.set_result(wave, [signal])
