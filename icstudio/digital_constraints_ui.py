"""Editable clock/I/O tables, synthesis controls and explicit SDC ownership."""
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTabWidget,QWidget,
    QTableWidget,QTableWidgetItem,QHeaderView,QPushButton,QFormLayout,QDoubleSpinBox,
    QLineEdit,QComboBox,QCheckBox,QPlainTextEdit,QDialogButtonBox)
from .model import clone
from . import digital_constraints as constraints


class ConstraintEditor(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent); self.config=clone(config); self.value=None
        self.setWindowTitle('Digital design constraints'); self.resize(900,670)
        root=QVBoxLayout(self); note=QLabel('Define clock and I/O intent, then review the SDC and synthesis budget before applying.'); note.setWordWrap(True);root.addWidget(note)
        self.tabs=QTabWidget();root.addWidget(self.tabs,1)
        intent=clone(config.get('constraints') or constraints.default_intent());self.intent=intent
        self.clocks=self.grid('Clocks',['Name','Port expression','Period (ns)','Uncertainty (ns)','Transition (ns)'],
            [[c['name'],c['port'],c['period_ns'],c.get('uncertainty_ns',0),c.get('transition_ns',0)] for c in intent['clocks']])
        self.io=self.grid('I/O timing',['Direction','Port expression','Clock','Minimum (ns)','Maximum (ns)'],
            [[direction,c['ports'],c['clock'],c['min_ns'],c['max_ns']] for direction,key in [('input','inputs'),('output','outputs')] for c in intent.get(key,[])])
        page=QWidget();form=QFormLayout(page);self.tabs.addTab(page,'Electrical & synthesis')
        self.driver=QLineEdit(intent.get('driving_cell',''));self.driver.setAccessibleName('Input driving Liberty cell');form.addRow('Input driving cell',self.driver)
        self.load=QDoubleSpinBox();self.load.setRange(0,1000);self.load.setDecimals(6);self.load.setSuffix(' pF');self.load.setValue(intent.get('load_pf',0));form.addRow('Output load',self.load)
        self.derive=QCheckBox('Derive synthesis delay budget from the clock and I/O constraints');self.derive.setChecked(bool(config.get('constraints')));form.addRow(self.derive)
        self.delay=QDoubleSpinBox();self.delay.setRange(.000001,1e6);self.delay.setDecimals(6);self.delay.setSuffix(' ns');self.delay.setValue(config.get('synthesis',{}).get('delay_ns',8));form.addRow('Explicit synthesis budget',self.delay)
        self.frontend=QComboBox();self.frontend.addItem('Yosys Verilog frontend','verilog');self.frontend.addItem('slang SystemVerilog frontend','slang');self.frontend.setCurrentIndex(self.frontend.findData(config.get('synthesis',{}).get('frontend','verilog')));form.addRow('Synthesis frontend',self.frontend)
        note=QLabel('The synthesis budget is a conservative mapping target. Full clock groups and exceptions are evaluated by static timing analysis. The slang option requires the matching Yosys plugin.');note.setWordWrap(True);form.addRow(note)
        self.corner_checks=[]
        for name in config.get('platform',{}).get('corners',{}):
            check=QCheckBox(name);check.setChecked(name in config.get('timing_corners',[config['platform']['corner']]));form.addRow('Timing corner',check);self.corner_checks.append((name,check))
        sdcpage=QWidget();layout=QVBoxLayout(sdcpage);self.tabs.addTab(sdcpage,'SDC preview')
        self.generate=QCheckBox('Generate SDC from the structured fields');self.generate.setChecked(bool(config.get('constraints')));layout.addWidget(self.generate)
        self.preview=QPlainTextEdit();self.preview.setAccessibleName('Editable timing SDC')
        self.preview.setPlainText('\n'.join(f['text'] for f in config['files'] if f['role']=='constraint'));layout.addWidget(self.preview,1)
        refresh=QPushButton('Preview generated SDC');refresh.clicked.connect(self.refresh_preview);layout.addWidget(refresh)
        self.error=QLabel();self.error.setWordWrap(True);root.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Apply|QDialogButtonBox.Cancel);root.addWidget(buttons)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply);buttons.rejected.connect(self.reject)

    def grid(self,title,columns,rows):
        page=QWidget();layout=QVBoxLayout(page);grid=QTableWidget(0,len(columns));grid.setHorizontalHeaderLabels(columns);grid.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);layout.addWidget(grid)
        def add(values=None):
            row=grid.rowCount();grid.insertRow(row)
            for i,value in enumerate(values or ['']*len(columns)):grid.setItem(row,i,QTableWidgetItem(str(value)))
        for row in rows:add(row)
        bar=QHBoxLayout();layout.addLayout(bar);button=QPushButton('Add row');button.clicked.connect(lambda:add());bar.addWidget(button);button=QPushButton('Remove selected');button.clicked.connect(lambda:grid.removeRow(grid.currentRow()));bar.addWidget(button);bar.addStretch();self.tabs.addTab(page,title);return grid

    def read_intent(self):
        def row(grid,i):return [grid.item(i,j).text().strip() if grid.item(i,j) else '' for j in range(grid.columnCount())]
        value={'version':1,'clocks':[],'inputs':[],'outputs':[],'driving_cell':self.driver.text().strip(),'load_pf':self.load.value()}
        for i in range(self.clocks.rowCount()):
            name,port,period,uncertainty,transition=row(self.clocks,i);value['clocks'].append({'name':name,'port':port,'period_ns':float(period),'uncertainty_ns':float(uncertainty or 0),'transition_ns':float(transition or 0)})
        for i in range(self.io.rowCount()):
            direction,ports,clock,minimum,maximum=row(self.io,i)
            if direction not in ('input','output'):raise ValueError('I/O direction must be input or output.')
            value[direction+'s'].append({'ports':ports,'clock':clock,'min_ns':float(minimum),'max_ns':float(maximum)})
        return constraints.validate(value)

    def refresh_preview(self):
        try:self.preview.setPlainText(constraints.sdc(self.read_intent()));self.generate.setChecked(True);self.error.clear()
        except ValueError as exc:self.error.setText(str(exc))

    def apply(self):
        try:
            out=clone(self.config)
            if self.generate.isChecked():out=constraints.apply(out,self.read_intent())
            else:
                if self.derive.isChecked():raise ValueError('Use generated SDC to derive the synthesis budget, or enter an explicit budget.')
                out.pop('constraints',None);files=[f for f in out['files'] if f['role']=='constraint']
                if len(files)>1:raise ValueError('Select one SDC source before editing constraints.')
                if not files:out['files'].append({'path':'constraints.sdc','role':'constraint','text':self.preview.toPlainText()})
                else:files[0]['text']=self.preview.toPlainText()
            out['synthesis']={'frontend':self.frontend.currentData()}
            if not self.derive.isChecked():out['synthesis'].update(delay_ns=self.delay.value(),driving_cell=self.driver.text().strip(),load_pf=self.load.value())
            if self.corner_checks:
                out['timing_corners']=[name for name,check in self.corner_checks if check.isChecked()]
            from .digital import validate_config
            validate_config(out);constraints.synthesis_settings(out);self.value=out;self.accept()
        except ValueError as exc:self.error.setText(str(exc))
