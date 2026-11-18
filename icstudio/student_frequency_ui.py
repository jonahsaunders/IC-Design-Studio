"""Frequency-domain teaching plots backed by the existing keyboard-aware plot."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from . import student_ahuja, student_filters
from .plot import WavePlot, engineering, trace_colors


def _wave(xs, traces, units, ticks, reference=None):
    return dict(settings={'type': 'ac'}, x=xs, traces=traces, x_label='Frequency (Hz)',
                plot_unit=units, frequency_ticks=ticks, y_reference=reference)


class FrequencyDialog(QDialog):
    def __init__(self, studio, title, description, columns):
        super().__init__(studio)
        self.setWindowTitle(title)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(790, 740)
        self.setMinimumWidth(520)
        self.dark = studio.dark
        layout = QVBoxLayout(self)
        self.description = QLabel(description)
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        self.form = QFormLayout()
        layout.addLayout(self.form)
        self.legend = QLabel()
        self.legend.setWordWrap(True)
        layout.addWidget(self.legend)
        self.gain = WavePlot()
        self.phase = WavePlot()
        self.cursor = QLabel()
        self.cursor.setAccessibleName('Plot cursor values')
        self.cursor.setWordWrap(True)
        for plot, name in ((self.gain, 'Magnitude in decibels'), (self.phase, 'Phase in degrees')):
            plot.dark = self.dark
            plot.setAccessibleName(name + ' versus logarithmic frequency')
            plot.cursor_changed.connect(self.cursor.setText)
            layout.addWidget(plot, 1)
        layout.addWidget(self.cursor)
        self.values = QTableWidget(0, len(columns))
        self.values.setAccessibleName('Frequency measurements')
        self.values.setHorizontalHeaderLabels(columns)
        self.values.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.values.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.values.verticalHeader().hide()
        layout.addWidget(self.values)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def table(self, values):
        self.values.setRowCount(len(values))
        for i, row in enumerate(values):
            for j, value in enumerate(row):
                self.values.setItem(i, j, QTableWidgetItem(value))
        self.values.setFixedHeight(self.values.horizontalHeader().height()
                                   + sum(self.values.rowHeight(i) for i in range(len(values))) + 4)
        self.cursor.setText('Click a plot to read its frequency and value.')


class FilterDialog(FrequencyDialog):
    def __init__(self, studio, project, result):
        super().__init__(studio, 'LC filter Bode plots',
                         'Compare your hand sketch with the AC run. The magnitude display uses a −100 dB floor.',
                         ('Frequency (Hz)', 'Hand estimate (dB)', 'Measured (dB)', 'Phase (°)'))
        self.project, self.result = project, result
        self.output = QComboBox()
        for key, name in student_filters.OUTPUTS.items():
            self.output.addItem(name, key)
        title = QLabel('Filter &output')
        title.setBuddy(self.output)
        self.form.addRow(title, self.output)
        self.guide = QCheckBox('Show straight-line hand sketch')
        self.guide.setChecked(True)
        self.form.addRow(self.guide)
        self.output.currentIndexChanged.connect(self.refresh)
        self.guide.toggled.connect(self.refresh)
        self.refresh()

    def refresh(self):
        f = student_filters
        output = self.output.currentData()
        name = f.OUTPUTS[output]
        try:
            center, q = f.parameters(self.project, output)
            response = f.series(self.result, output)
        except ValueError as error:
            self.legend.setText(str(error))
            self.gain.set_result(None)
            self.phase.set_result(None)
            self.table([])
            return
        xs = self.result['x']
        ratios = (.01, .1, 1, 10, 100)
        ticks = [min(max(center*ratio, xs[0]), xs[-1]) for ratio in ratios
                 if xs[0]*(1-1e-12) <= center*ratio <= xs[-1]*(1+1e-12)]
        solid = _wave(xs, {name: [f.gain_db(v, 1e-5) for v in response]}, 'dB', ticks)
        dashed = _wave(xs, {name: [f.asymptote(output, x/center, q) for x in xs]}, 'dB', ticks)
        self.gain.set_result(solid, compare=dashed if self.guide.isChecked() else None)
        phase = [f.phase_deg(v) for v in response]
        gaps = [i for i, value in enumerate(phase) if value is None]
        wave = _wave(xs, {name: [value if value is not None else 0 for value in phase]}, '°', ticks)
        wave['trace_gaps'] = {name: gaps}
        self.phase.empty_message = 'Phase is undefined below the display floor.'
        self.phase.set_result(wave if len(gaps) < len(phase) else None)
        note = ' The hand sketch shows the notch’s flat tails. The exact zero creates the dip and phase is undefined there.' if output == 'bs' else ''
        mode = 'solid measured · dashed asymptote' if self.guide.isChecked() else 'measured response'
        self.legend.setText(f'f₀ {center/1000:.3g} kHz · Q {q:.3g} · {mode}.' + note)
        values = []
        for ratio in ratios:
            frequency = center * ratio
            if not xs[0] * (1 - 1e-12) <= frequency <= xs[-1] * (1 + 1e-12):
                continue
            actual = f.sample(xs, response, min(max(frequency, xs[0]), xs[-1]))
            angle = f.phase_deg(actual)
            estimate = 'Null' if output == 'bs' and ratio == 1 else f'{f.asymptote(output, ratio, q):.1f}'
            values.append((engineering(frequency), estimate, f'{f.gain_db(actual):.2f}',
                           f'{angle:.1f}' if angle is not None else 'Undefined'))
        self.table(values)


class AhujaDialog(FrequencyDialog):
    def __init__(self, studio):
        super().__init__(studio, 'Ahuja compensation study',
                         'The same small-signal stages and compensation capacitor drive all three curves in unity feedback.',
                         ('Model', 'First unity (MHz)', 'Phase margin (°)', '60° target'))
        self.load = self._number('Output &load (pF)', 1, 100, 5, 20)
        self.buffer = self._number('&Buffer pole (MHz)', 5, 500, 5, 50)
        self.load.valueChanged.connect(self.refresh)
        self.buffer.valueChanged.connect(self.refresh)
        self.refresh()

    def _number(self, name, low, high, step, value):
        number = QDoubleSpinBox()
        number.setRange(low, high)
        number.setDecimals(1)
        number.setSingleStep(step)
        number.setValue(value)
        label = QLabel(name)
        label.setBuddy(number)
        self.form.addRow(label, number)
        return number

    def refresh(self):
        xs, data = student_ahuja.study(self.load.value(), self.buffer.value())
        ticks = [10**power for power in range(1,10)]
        for plot, field, unit, reference in ((self.gain, 'gain', 'dB', 0),
                                              (self.phase, 'phase', '°', student_ahuja.TARGET_PM-180)):
            plot.set_result(_wave(xs, {name: row[field] for name, row in data.items()}, unit, ticks, reference=reference))
        colors = trace_colors(self.dark)
        self.legend.setText(' &nbsp; '.join(f'<span style="color:{colors[i]}">■</span> {name}'
                                           for i, name in enumerate(data)) +
                            f'<br>Direct Miller RHP zero ≈ {student_ahuja.MILLER_ZERO_HZ/1e6:.1f} MHz. '
                            'The dashed levels mark 0 dB and −120°.')
        self.table([(name, f'{row["unity_Hz"]/1e6:.3g}', f'{row["phase_margin_deg"]:.1f}',
                     'Meets target' if row['phase_margin_deg'] >= student_ahuja.TARGET_PM else 'Below target')
                    for name, row in data.items()])
