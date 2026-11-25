"""Short prediction exercises before the new measured analog lessons."""

from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

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


def show(guide):
    guide.require_project()
    lab=guide.lesson.get('signal_lab')
    if lab not in DC_PATHS:
        raise ValueError('This lesson has no analysis warm-up.')
    window=QDialog(guide)
    window.setWindowTitle('Analyze before running')
    window.resize(600,360)
    layout=QVBoxLayout(window)
    layout.addWidget(QLabel('Trace the branch and save a hand estimate before running the bench.'))
    form=QFormLayout()
    layout.addLayout(form)
    path=QComboBox()
    choices, parts=DC_PATHS[lab]
    path.addItem('Choose the conduction or charging path',-1)
    for index in (1,0,2):
        path.addItem(choices[index],index)
    form.addRow('Find the DC path first',path)
    group,metric=ESTIMATE[lab]
    estimate=QLineEdit()
    form.addRow(f'Estimate {metric}',estimate)
    step=guide.active_step['id']
    if guide.active_step['kind']!='check':
        step=next(s['id'] for s in guide.lesson['steps'] if s['kind']=='check')
    key='warmup/'+step
    answer=_read(guide,key,{})
    estimate.setText(answer.get('estimate',''))
    if answer.get('path') is not None:
        path.setCurrentIndex(path.findData(answer['path']))
    prediction=QComboBox()
    device=REGION_DEVICE.get(lab)
    if device:
        prediction.addItem('Choose a region')
        prediction.addItems(REGION_CHOICES)
        prediction.setCurrentIndex(answer.get('region',0))
        form.addRow(f'Predict region of {device}',prediction)
    output=QLabel()
    output.setWordWrap(True)
    layout.addWidget(output)
    save=QPushButton('Save prediction and check the path')
    layout.addWidget(save)
    compare=QPushButton('Compare with captured results')
    layout.addWidget(compare)
    close=QPushButton('Close')
    layout.addWidget(close)
    close.clicked.connect(window.close)
    identity=(guide.studio.project['id'],guide.lesson['id'])
    def require_context():
        if (guide.studio.project['id'],(guide.lesson or {}).get('id'))!=identity:
            raise ValueError('Reopen the warm-up in its lesson workspace.')
        guide.require_project()
    def save_prediction():
        try:
            require_context()
            if path.currentData()==-1:
                raise ValueError('Choose a path before checking it.')
            scalar(estimate.text())
            entry=dict(path=path.currentData(),estimate=estimate.text(),region=prediction.currentIndex())
            _save(guide,key,entry)
            if path.currentData()!=0:
                output.setText('Look for the branch with a source and a return. Check whether an insulated gate or capacitor carries steady current.')
                return
            studio=guide.studio
            studio.select([d['id'] for d in studio.cell['devices'] if d['name'] in parts],'schematic')
            output.setText('Path identified. The relevant devices are highlighted. Your estimate is saved.')
        except ValueError as exc:
            output.setText(str(exc))
    def compare_readings():
        try:
            require_context()
            entry=_read(guide,key,{})
            if not entry.get('estimate'):
                raise ValueError('Save an estimate to compare.')
            if guide.active_step['id']!=step:
                index=next(i for i,item in enumerate(guide.lesson['steps']) if item['id']==step)
                guide.steps.setCurrentIndex(index)
            row=current_row(guide)
            if not row:
                raise ValueError('Run this checkpoint on the current design and try again.')
            record=row['result']['student_signal']
            if record['issue']:
                raise ValueError(record['issue'])
            measured=record['measurements']
            value=(measured[group] if group else measured)[metric]
            guess=scalar(entry['estimate'])
            text=f'Estimate {guess:.4g} · Measured {value:.4g} · Difference {abs(value-guess):.4g}'
            if device:
                from .student_signal_labs import read_cases
                cases=read_cases(row['job']['project'],lab,step,row['result'],row['path'])
                op=cases.get('dc-bias')
                if op:
                    point=next((point for name,point in op['device_operating_point'].items()
                                if name.casefold()==device.casefold()),{})
                    observed=region(point)
                    if observed:
                        guessed=REGION_CHOICES[entry['region']-1] if entry.get('region') else 'unset'
                        text+=f'\n{device} region · Predicted {guessed} · Observed {observed}'
                        studio=guide.studio
                        if op in studio.jobs:
                            studio.run_combo.setCurrentIndex(studio.jobs.index(op))
                        else:
                            studio.add_result(op)
                        fields=studio.settings.value('view/deviceFields',[],list)
                        studio.settings.setValue('view/deviceFields',sorted(set(fields)|{'region','vgs','vds'}))
                        studio.annotate_check.setChecked(True)
                        studio.update_annotations()
            output.setText(text)
        except (ValueError,KeyError,OSError) as exc:
            output.setText(str(exc))
    save.clicked.connect(save_prediction)
    compare.clicked.connect(compare_readings)
    guide.warmup=window
    window.show()
