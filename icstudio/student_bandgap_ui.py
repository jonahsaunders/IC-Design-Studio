"""Topology-specific temperature controls and measured-in-model readouts."""

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QVBoxLayout,
)

from .analog_workspace_ui import fill, table
from .plot import WavePlot, trace_colors
from . import student_bandgap as bandgap


class BandgapDialog(QDialog):
    def __init__(self, studio, kind):
        super().__init__(studio)
        self.kind = kind
        self.dark = studio.dark
        self.setWindowTitle(bandgap.NAMES[kind] + ' temperature study')
        self.resize(780, 720)
        layout = QVBoxLayout(self)
        note = QLabel('Adjust the resistor ratios and compare first-order cancellation with the remaining curvature.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.form = QFormLayout()
        layout.addLayout(self.form)
        ratio, weight, auxiliary = bandgap.defaults(kind)
        self.ratio = self.number(bandgap.RATIO_LABELS[kind], 2, 32, 1, ratio)
        self.weight = self.number(bandgap.WEIGHT_LABELS[kind], 1, 30, .1, weight)
        self.extra = None
        if kind == 'kuijk':
            self.extra = self.number('Current-setting ratio R₂/R₁', .5, 3, .1, auxiliary)
        if kind == 'banba':
            self.extra = self.number('Output scale R₄/R₂', .25, 1, .05, auxiliary)
        self.legend = QLabel()
        self.legend.setWordWrap(True)
        layout.addWidget(self.legend)
        self.volts = WavePlot()
        self.drift = WavePlot()
        for plot, name in ((self.volts, 'CTAT, PTAT and total output in volts'),
                           (self.drift, 'Output change from 27 degrees Celsius in millivolts')):
            plot.dark = self.dark
            plot.setAccessibleName(name)
            layout.addWidget(plot, 1)
        self.values = table(['Temperature (°C)', 'CTAT term (V)', 'PTAT term (V)', 'Reference (V)', 'Change (mV)'])
        self.values.setMaximumHeight(148)
        layout.addWidget(self.values)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.refresh()

    def number(self, name, low, high, step, value):
        number = QDoubleSpinBox()
        number.setDecimals(3)
        number.setRange(low, high)
        number.setSingleStep(step)
        number.setValue(value)
        label = QLabel(name)
        label.setBuddy(number)
        self.form.addRow(label, number)
        number.valueChanged.connect(self.refresh)
        return number

    def refresh(self):
        extra = self.extra.value() if self.extra is not None else 1
        data = bandgap.study(self.kind, self.ratio.value(), self.weight.value(), extra)
        temps = data['x']
        traces = {'CTAT': data['ct'], 'PTAT': data['pt'], 'Reference': data['output']}
        plot = dict(settings={'type':'dc'}, x=temps, x_label='Temperature (°C)')
        self.volts.set_result({**plot, 'traces': traces, 'plot_unit':'V'})
        self.drift.set_result({**plot, 'traces': {'Reference drift': [v*1000 for v in data['drift']]}, 'plot_unit':'mV'})
        colors = trace_colors(self.dark)
        legend = ' &nbsp; '.join(f'<span style="color:{colors[i]}">■</span> {name}' for i,name in enumerate(traces))
        self.legend.setText(legend + '<br>' +
                            f'At 27 °C, ΔV<sub>BE</sub> = {data["delta_room"]*1000:.2f} mV, '
                            f'output slope = {data["slope27"]*1e6:+.1f} µV/°C. '
                            f'Peak-to-peak drift = {data["span"]*1000:.2f} mV.' +
                            (f' Mirrored sum at 27 °C = {data["i_ctat_uA"]:.2f} + {data["i_ptat_uA"]:.2f} µA.'
                             if self.kind=='banba' else ''))
        fill(self.values, [[temp, f'{data["ct"][i]:.5f}', f'{data["pt"][i]:.5f}',
                            f'{data["output"][i]:.5f}', f'{data["drift"][i]*1000:+.2f}']
                           for temp in (-40, 27, 85, 125) for i in (temps.index(temp),)])
