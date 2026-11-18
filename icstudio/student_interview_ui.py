"""Interview comparisons presented beside their saved simulations."""

import math

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHeaderView, QLabel, QVBoxLayout

from .analog_widgets import fill, table
from .model import design_digest
from .plot import WavePlot
from .student_interview import READOUTS, collect, offset_samples


class InterviewResults(QDialog):
    def __init__(self,studio,project,step,rows):
        super().__init__(studio)
        self.step = step
        self.project = project
        self.runs,_ = collect(project,step,rows)
        self.setWindowTitle('Interview lab results')
        self.resize(940,725)
        outer = QVBoxLayout(self)
        self.note = QLabel('Saved experiment' if design_digest(studio.project)==design_digest(project)
                           else 'Saved experiment · the current design has changed')
        self.note.setWordWrap(True)
        outer.addWidget(self.note)
        self.readings = table(['Case','Measurement','Value'])
        header = self.readings.horizontalHeader()
        header.setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        self.readings.setAccessibleName('Measured values for the saved test conditions')
        outer.addWidget(self.readings,1)
        try:
            measures = READOUTS[step](project,self.runs)
            fill(self.readings, [[self.title(group),name,'Did not settle' if value is None else f'{value:.5g}']
                                 for group,values in measures.items() for name,value in values.items()])
        except (ValueError,KeyError) as error:
            self.note.setText(str(error))
        selectors = QFormLayout()
        self.case = QComboBox()
        self.trace = QComboBox()
        for title,widget in [('Test case',self.case),('Signal',self.trace)]:
            label = QLabel(title)
            label.setBuddy(widget)
            selectors.addRow(label,widget)
        for name in self.runs:
            self.case.addItem(self.title(name),name)
        outer.addLayout(selectors)
        self.plot = WavePlot()
        self.plot.dark = studio.dark
        self.plot.setAccessibleName('Waveform for the selected interview case and signal')
        outer.addWidget(self.plot,1)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        outer.addWidget(self.detail)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        outer.addWidget(buttons)
        self.case.currentIndexChanged.connect(self.select_case)
        self.trace.currentIndexChanged.connect(self.show_wave)
        self.select_case()

    @staticmethod
    def title(name):
        return name.replace('_',' ').replace('esr','ESR')

    def select_case(self,*_):
        name = self.case.currentData()
        wave = self.runs[name]
        self.trace.blockSignals(True)
        self.trace.clear()
        if self.step=='mismatch' and name.endswith('_trials'):
            self.trace.addItem('Input-referred offset distribution',('histogram',name))
        elif self.step.startswith('route-'):
            self.trace.addItem('Output before and after extraction',('route','vout'))
        else:
            for signal in wave['traces']:
                if signal!='v-sweep':
                    self.trace.addItem(signal,('voltage',signal))
            for signal in wave.get('currents',{}):
                self.trace.addItem('I('+signal+')',('current',signal))
            preferred = {'differential':'left','input-pairs':'left','slew':'out','noise':'out',
                         'comparator':'outp','sar-fault':'hold','sar-repair':'hold','ldo':'out'}.get(self.step)
            index = self.trace.findData(('current','vd') if self.step=='gain' else ('voltage',preferred))
            if index>=0:
                self.trace.setCurrentIndex(index)
        self.trace.blockSignals(False)
        self.show_wave()

    def show_wave(self,*_):
        data = self.trace.currentData()
        if not data:
            self.plot.set_result(None)
            return
        kind,signal = data
        wave = self.runs[self.case.currentData()]
        other = None
        detail = ''
        if kind=='histogram':
            try:
                _,samples = offset_samples(self.project,self.runs,signal.split('_',1)[0])
                all_offsets = [sample for label in ('small','large') for sample in offset_samples(self.project,self.runs,label)[1]]
            except (ValueError,KeyError) as error:
                self.detail.setText(str(error))
                self.plot.set_result(None)
                return
            limit = max(10,math.ceil(max(abs(v) for v in all_offsets)/2)*2)
            width = 2*limit/16
            counts = [0]*16
            for sample in samples:
                counts[min(15,int((sample+limit)/width))] += 1
            xs = [x for i in range(16) for x in (i*width-limit,(i+1)*width-limit)]
            signal = 'trials in bin'
            wave = dict(settings={'type':'dc'},x=xs,x_label='Input-referred offset (mV)',plot_unit=' trials',
                        traces={signal:[count for count in counts for _ in range(2)]})
            detail = 'Both device areas use the same bin boundaries and random seed.'
        elif kind=='route':
            other = wave['before_waveform']
            wave = wave['after_waveform']
            detail = 'Solid line is extracted interconnect. Dashed line is schematic.'
        elif kind=='current':
            wave = {**wave,'traces':wave['currents'],'plot_unit':'A'}
        elif self.step=='noise':
            noise = wave.get('diagnostics',{})
            sources = [r['vector'] for r in noise.get('contributors',[]) if not r['subtotal']]
            if sources:
                detail = 'Largest individual output noise contributions: '+', '.join(sources[:3])
        self.detail.setText(detail)
        self.plot.set_result(wave,[signal],compare=other)
