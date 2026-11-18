"""Keyboard-selectable results and waveforms for transistor bandgap sweeps."""

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHeaderView, QLabel, QVBoxLayout

from .analog_widgets import fill, table
from .plot import WavePlot
from .student_bandgap_lab import read_wave

BENCH_LABELS = {'bandgap_accuracy':'Temperature', 'bandgap_fast_startup':'100 ns startup',
                'bandgap_slow_startup':'100 µs startup'}


class BandgapLabResults(QDialog):
    def __init__(self, studio, result):
        super().__init__(studio)
        self.result = result
        self.rows = result['bandgap_rows']
        self.setWindowTitle('Bandgap lab results')
        self.resize(1040,680)
        outer = QVBoxLayout(self)
        target = result['requirements']['target']
        summary = QLabel(f'{sum(row["status"]=="passed" for row in self.rows)} of {len(self.rows)} conditions passed. '
                         f'Nominal design target {target:g} V.')
        if result.get('extraction'):
            summary.setText(summary.text()+f' Magic extracted {result["extraction"]["capacitors"]} capacitances.')
        summary.setWordWrap(True)
        outer.addWidget(summary)
        self.cases = table(['Test', 'Process', 'Temp. (°C)', 'Supply (V)', 'Final (V)', 'Peak (V)',
                            'Settled (µs)', 'Layout Δ (mV)', 'Status'])
        self.cases.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.cases.horizontalHeader().setStretchLastSection(True)
        self.cases.setAccessibleName('Bandgap test results. Select a row to show its measurements and waveform.')
        outer.addWidget(self.cases,1)

        def formatted(value, multiplier=1):
            return '—' if value is None else f'{value*multiplier:.4g}'

        values = []
        for row in self.rows:
            stage = row.get('extracted',row.get('schematic',{}))
            measured = stage.get('values',{})
            values.append([BENCH_LABELS[row['bench']],row['corner'],row['temperature'],row['supply_V'],
                           formatted(measured.get('voltage_V')), formatted(measured.get('peak_V')),
                           formatted(measured.get('settled_s'),1e6), formatted(row.get('delta_V'),1000),
                           'Meets case limits' if row['status']=='passed' else 'Needs review'])
        fill(self.cases,values)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        outer.addWidget(self.detail)
        self.wave = WavePlot()
        self.wave.dark = studio.dark
        self.wave.setAccessibleName('Selected bandgap startup waveform or reference voltage versus temperature')
        outer.addWidget(self.wave,1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.close)
        outer.addWidget(close)
        self.cases.currentCellChanged.connect(self.show_case)
        if self.rows:
            self.cases.setCurrentCell(next((i for i,r in enumerate(self.rows) if r['status']!='passed'),0),0)

    def show_case(self, index, *_):
        if not 0<=index<len(self.rows):
            return
        row = self.rows[index]
        self.wave.set_result(None)
        try:
            if 'schematic' not in row:
                self.detail.setText(', '.join(row['errors']))
                return
            extracted = 'extracted' in row
            if row['bench']=='bandgap_accuracy':
                points = [r for r in self.rows if r['bench']==row['bench'] and 'schematic' in r]
                def series(stage):
                    selected = [r for r in points if stage in r]
                    return dict(settings={'type':'dc'},x=[r['temperature'] for r in selected],
                                x_label='Temperature (°C)',
                                traces={'vref':[r[stage]['values']['voltage_V'] for r in selected]})
                self.wave.set_result(series('schematic'),['vref'],compare=series('extracted') if extracted else None)
                span = self.result.get('schematic_temperature_span_V')
                limit = self.result['requirements']['temperature_span']*1000
                detail = f'Schematic temperature span {span*1000:.1f} mV. Limit {limit:g} mV.' if span is not None else ''
                if extracted and 'extracted_temperature_span_V' in self.result:
                    detail+=f' Extracted span {self.result["extracted_temperature_span_V"]*1000:.1f} mV.'
            else:
                wave = read_wave(self.result,row,'schematic')
                physical = read_wave(self.result,row,'extracted') if extracted else None
                self.wave.set_result(wave,['vref'],compare=physical)
                detail = 'VREF during the 500 µs observation window.'
            measured = row['extracted' if extracted else 'schematic']['values']
            detail+=f' Supply current {measured["current_A"]*1e6:.2f} µA.'
            if 'ripple_V' in measured:
                detail+=f' Final-window ripple {measured["ripple_V"]*1000:.3f} mV.'
            if extracted:
                detail+=' Solid line is schematic. Dashed line is extracted.'
            if row['errors']:
                detail+=' '+', '.join(row['errors'])
            self.detail.setText(detail.strip())
        except (OSError, KeyError, ValueError) as error:
            self.detail.setText(str(error))
