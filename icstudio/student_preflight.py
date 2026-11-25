"""Short prediction exercises before the new measured analog lessons."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QScrollArea, QVBoxLayout, QWidget)

from .annotations import region
from .model import design_digest, scalar
from .student_workspace import _read, _save

# The paths describe the conduction branch being studied, rather than every
# auxiliary source in the fixture. A DC capacitor is an open circuit.
DC_PATHS = {
    'output-resistance': (('VDRAIN → M1 drain/source → ground','VDRAIN → M1 gate → ground','VGATE → body → ground'),
                          ('VDRAIN','M1')),
    'body-effect': (('VDRAIN → M1 drain/source → ground','VGATE → M1 gate → ground','VSB → M1 gate → ground'),
                    ('VDRAIN','M1')),
    'active-load': (('VDD → RLOAD → MNR drain/source → ground','VDD → VIN → MNR gate → ground','VDD → RLOAD → MOS gate → ground'),
                    ('VDD','RLOAD','MNR')),
    'transmission-gate': (('VTG → MN or MP channel → VCM return','VEN → MOS gate → VCM return','VTG → VEN → ground'),
                           ('VTG','MN','MP','VCM')),
    'noise-spectrum': (('VDD → RFULL → MFULL drain/source → ground','VIN → MFULL gate → ground','VDD → VIN → ground'),
                       ('VDD','RFULL','MFULL')),
    'bias-leakage': (('VREF → RBIAS → reverse-biased DLEAK → ground','VREF → RBIAS → an open probe','Ground → RBIAS via the VIN source'),
                    ('VREF','RBIAS','DLEAK')),
    'common-mode-feedback': (('BERR drives RFILT; CFILT is open at DC','Steady current flows through CFILT',
                             'The differential input is the return path for CFILT'),('BERR','RFILT','CFILT')),
    'switch-pedestal': (('VIN charges CHOLD through SSAMPLE while the switch conducts',
                         'VIN charges CHOLD through COV at DC','DC gate current charges CHOLD through IINJ'),
                        ('VIN','SSAMPLE','CHOLD')),
}

ESTIMATE = {
    'output-resistance': (None,'Output resistance (kΩ)'),
    'body-effect': (None,'Threshold shift (mV)'),
    'active-load': ('resistor','Gain magnitude (V/V)'),
    'transmission-gate': ('0.9 V','Transmission-gate resistance (Ω)'),
    'noise-spectrum': ('100 Hz','Total density (nV/√Hz)'),
    'bias-leakage': ('hot','Bias voltage (V)'),
    'common-mode-feedback': ('closed-loop','Common-mode error (mV)'),
    'switch-pedestal': ('combined','Held voltage step (mV)'),
}

REGION_DEVICE = {'output-resistance':'M1','body-effect':'M1','active-load':'MNR'}
REGION_CHOICES = ('Cutoff','Linear','Saturation')


def current_row(guide):
    from .student_signal_labs import focus
    studio=guide.studio
    lab=guide.lesson['signal_lab']
    cell=focus(studio.project,lab,guide.active_step['id'])
    stamp=design_digest(studio.project)
    return next((row for row in reversed(guide.step_run_rows(guide.lesson_rows()))
                 if row['job']['cell']==cell and row.get('result',{}).get('design_hash')==stamp
                 and row['result'].get('student_signal')),None)


class AnalysisWarmup(QDialog):
    def __init__(self, guide):
        super().__init__(guide)
        from .analog_widgets import FlowActions
        from .student_hub_ui import button, label

        self.guide=guide
        self.studio=guide.studio
        self.lab=guide.lesson['signal_lab']
        self.step=guide.active_step['id']
        self.identity=(self.studio.project['id'],guide.lesson['id'],self.step)
        self.key='warmup/'+self.step
        self.entry=_read(guide,self.key,{})
        self.op=None
        self.setWindowTitle('Analyze Before Running')
        self.setStyleSheet(guide.styleSheet())
        self.resize(570,570)

        outer=QVBoxLayout(self)
        self.scroll=QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAccessibleName('Analysis warm-up')
        outer.addWidget(self.scroll,1)
        body=QWidget()
        self.scroll.setWidget(body)
        layout=QVBoxLayout(body)
        layout.addWidget(label(guide.active_step['title'],'subtitle'))
        heading=label('Find the DC or charging path')
        layout.addWidget(heading)
        self.path=QListWidget()
        self.path.setAccessibleName(heading.text())
        self.path.setWordWrap(True)
        self.path.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.path.setMinimumHeight(126)
        prompt=QListWidgetItem('Choose a path')
        prompt.setData(Qt.UserRole,-1)
        self.path.addItem(prompt)
        self.path.setCurrentItem(prompt)
        choices,_=DC_PATHS[self.lab]
        for index in (1,0,2):
            choice=QListWidgetItem(choices[index])
            choice.setData(Qt.UserRole,index)
            self.path.addItem(choice)
            if self.entry.get('path')==index:
                self.path.setCurrentItem(choice)
        layout.addWidget(self.path)
        heading.setBuddy(self.path)
        self.check_path_button=button('Check Path',self.check_path)
        layout.addWidget(self.check_path_button,0,Qt.AlignLeft)
        self.path_feedback=label('')
        layout.addWidget(self.path_feedback)

        _,metric=ESTIMATE[self.lab]
        self.estimate=QLineEdit(self.entry.get('estimate',''))
        self.estimate.setAccessibleName(f'Estimate {metric}')
        estimate_label=label(f'Estimate {metric}')
        estimate_label.setBuddy(self.estimate)
        layout.addWidget(estimate_label)
        layout.addWidget(self.estimate)
        self.region_choice=QComboBox()
        self.device=REGION_DEVICE.get(self.lab)
        if self.device:
            self.region_choice.addItem('Choose a region (optional)')
            self.region_choice.addItems(REGION_CHOICES)
            self.region_choice.setCurrentIndex(self.entry.get('region',0))
            self.region_choice.setAccessibleName(f'Predicted operating region of {self.device}')
            region_label=label(f'Predict operating region of {self.device}')
            region_label.setBuddy(self.region_choice)
            layout.addWidget(region_label)
            layout.addWidget(self.region_choice)
        self.save_button=button('Save Prediction',self.save_prediction,'primary')
        self.compare_button=button('Compare Results',self.compare_readings)
        actions=FlowActions()
        actions.addWidget(self.save_button)
        actions.addWidget(self.compare_button)
        layout.addLayout(actions)
        self.availability=label('','muted')
        layout.addWidget(self.availability)

        self.report=label('')
        self.report.setTextInteractionFlags(Qt.TextSelectableByMouse|Qt.TextSelectableByKeyboard)
        layout.addWidget(self.report)
        self.annotate_button=button('Show Region on Schematic',self.show_region)
        self.annotate_button.hide()
        layout.addWidget(self.annotate_button,0,Qt.AlignLeft)
        layout.addStretch()
        buttons=QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Close).setAutoDefault(False)
        outer.addWidget(buttons)
        self.path.currentRowChanged.connect(self.update_controls)
        self.estimate.textChanged.connect(self.update_controls)
        self.estimate.returnPressed.connect(self.save_prediction)
        self.region_choice.currentIndexChanged.connect(self.update_controls)
        self.update_controls()
        self.path.setFocus()

    def matches_context(self):
        guide=self.guide
        return self.identity==(self.studio.project['id'],(guide.lesson or {}).get('id'),
                               (guide.active_step or {}).get('id'))

    def update_controls(self,*_):
        valid=self.matches_context()
        choice=self.path.currentItem()
        self.check_path_button.setEnabled(valid and choice is not None and choice.data(Qt.UserRole)>=0)
        text=self.estimate.text().strip()
        self.save_button.setEnabled(valid and bool(text))
        row=current_row(self.guide) if valid else None
        saved=bool(self.entry.get('estimate') and self.entry['estimate']==text and
                   self.entry.get('region',0)==max(0,self.region_choice.currentIndex()))
        self.compare_button.setEnabled(saved and row is not None)
        if not saved:
            self.availability.setText('Save your prediction to compare it with measurements.')
        elif row is None:
            self.availability.setText('Run this checkpoint on the current design to compare your prediction.')
        else:
            self.availability.setText('Measurements are available for the current design.')
        if self.op and (row is None or row['result']['design_hash']!=self.op['design_hash']):
            self.op=None
            self.annotate_button.hide()

    def check_path(self):
        from .student_hub_ui import feedback
        if not self.check_path_button.isEnabled() or not self.matches_context():
            return
        index=self.path.currentItem().data(Qt.UserRole)
        self.entry['path']=index
        _save(self.guide,self.key,self.entry)
        if index!=0:
            feedback(self.path_feedback,'Try again. Look for a source and a return path. Consider the role of insulated gates and capacitors.',True)
            return
        studio=self.studio
        if studio.activate_circuit_view(0):
            studio.cid=studio.project['top']
            studio.refresh()
            _,parts=DC_PATHS[self.lab]
            studio.select([d['id'] for d in studio.cell['devices'] if d['name'] in parts],'schematic')
        feedback(self.path_feedback,'Path confirmed. The related devices are selected on the schematic.',role='correct')

    def save_prediction(self):
        from .student_hub_ui import feedback
        if not self.matches_context():
            return
        text=self.estimate.text().strip()
        try:
            scalar(text)
        except ValueError:
            feedback(self.report,'Enter a number in the unit shown above.',True)
            self.estimate.setFocus()
            return
        self.entry.update(estimate=text,region=max(0,self.region_choice.currentIndex()))
        _save(self.guide,self.key,self.entry)
        feedback(self.report,'Prediction saved.')
        self.op=None
        self.annotate_button.hide()
        self.update_controls()

    def compare_readings(self):
        from .student_hub_ui import feedback
        if not self.matches_context():
            return
        self.op=None
        self.annotate_button.hide()
        try:
            row=current_row(self.guide)
            if row is None:
                raise ValueError('Run this checkpoint on the current design.')
            record=row['result']['student_signal']
            if record['issue']:
                raise ValueError(record['issue'])
            measured=record['measurements']
            group,metric=ESTIMATE[self.lab]
            value=(measured[group] if group else measured)[metric]
            guess=scalar(self.entry['estimate'])
            report=[metric,f'Estimate {guess:.4g} · Measured {value:.4g} · Difference {abs(value-guess):.4g}']
            if self.device:
                from .student_signal_labs import read_cases
                cases=read_cases(row['job']['project'],self.lab,self.step,row['result'],row['path'])
                op=cases.get('dc-bias')
                if op:
                    point=next((point for name,point in op['device_operating_point'].items()
                                if name.casefold()==self.device.casefold()),{})
                    if observed:=region(point):
                        prediction=self.entry['region']
                        report.append(f'{self.device} observed region · {observed}')
                        if prediction:
                            report.append(f'Your region prediction · {REGION_CHOICES[prediction-1]}')
                        self.op=op
                        self.annotate_button.show()
            feedback(self.report,'\n'.join(report))
        except (ValueError,KeyError,OSError) as exc:
            feedback(self.report,str(exc),True)

    def show_region(self):
        if not self.matches_context() or self.op is None or self.op['design_hash']!=design_digest(self.studio.project):
            self.update_controls()
            return
        studio=self.studio
        if not studio.activate_circuit_view(0):
            return
        studio.cid=self.op['cell_id']
        studio.refresh()
        if self.op in studio.jobs:
            studio.run_combo.setCurrentIndex(studio.jobs.index(self.op))
        else:
            studio.add_result(self.op)
        from .annotations import DEFAULT_FIELDS
        fields=studio.settings.value('view/deviceFields',sorted(DEFAULT_FIELDS),list)
        studio.settings.setValue('view/deviceFields',sorted(set(fields)|{'region'}))
        studio.annotate_check.setChecked(True)
        studio.select([d['id'] for d in studio.cell['devices'] if d['name']==self.device],'schematic')
        studio.update_annotations()


def show(guide):
    guide.require_project()
    if guide.lesson.get('signal_lab') not in DC_PATHS or guide.active_step['kind']!='check':
        raise ValueError('Open a measured checkpoint to analyze it before running.')
    guide.warmup=AnalysisWarmup(guide)
    guide.warmup.show()
    return guide.warmup
