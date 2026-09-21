"""Explicit distribution editing and trial/PVT yield evidence."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QComboBox,QSpinBox,QLineEdit,
    QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QDialogButtonBox,QPushButton,QAbstractItemView)
from .model import clone,scalar
from .campaign_statistics import configuration


class StatisticsEditor(QDialog):
    def __init__(self,parent,project,plan,value=None):
        super().__init__(parent);self.project=project;self.plan=plan;self.value=clone(value or {})
        self.setWindowTitle('Statistical verification');self.resize(900,570)
        root=QVBoxLayout(self);form=QFormLayout();root.addLayout(form)
        self.kind=QComboBox()
        for label,key in [('Disabled',''),('Independent component tolerances','monte_carlo'),('Correlated component tolerances','correlated'),('Validated PDK mismatch model','model_mismatch')]:self.kind.addItem(label,key)
        self.kind.setCurrentIndex(max(0,self.kind.findData(self.value.get('kind',''))))
        self.cell=QComboBox()
        for cell in project['cells']:self.cell.addItem(cell['name'],cell['id'])
        self.cell.setCurrentIndex(max(0,self.cell.findData(self.value.get('cell',project['top']))))
        self.count=QSpinBox();self.count.setRange(2,10000);self.count.setValue(self.value.get('count',100))
        self.seed=QLineEdit(str(self.value.get('seed',1)));self.model=QComboBox()
        for name,model in project['pdk'].get('statistical_models',{}).items():
            if model.get('validated') and model.get('evidence') and model.get('variations'):self.model.addItem(name,name)
        self.model.setCurrentIndex(max(0,self.model.findData(self.value.get('model'))))
        for name,widget in [('Sampling',self.kind),('Parameter cell',self.cell),('Trials',self.count),('Repeatable seed',self.seed),('PDK model',self.model)]:
            widget.setAccessibleName(name);form.addRow(name,widget)
        note=QLabel('Each trial uses one saved realization across all tests and PVT conditions. Normal rows sharing a factor have correlation equal to the product of their loadings. Samples are never clipped or redrawn. Component tolerances are not foundry distributions.')
        note.setWordWrap(True);root.addWidget(note)
        self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(['Numeric target','Sigma','Sigma basis','Distribution','Shared factor','Factor loading'])
        self.table.setAccessibleName('Statistical parameter distributions');self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);root.addWidget(self.table,1)
        for row in self.value.get('variations',[]):self.add(row)
        buttons=QHBoxLayout();root.addLayout(buttons)
        add=QPushButton('Add parameter');add.clicked.connect(lambda:self.add());buttons.addWidget(add)
        remove=QPushButton('Remove selected');remove.clicked.connect(lambda:self.table.removeRow(self.table.currentRow()) if self.table.currentRow()>=0 else None);buttons.addWidget(remove)
        self.error=QLabel();self.error.setWordWrap(True);root.addWidget(self.error)
        actions=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);actions.accepted.connect(self.save);actions.rejected.connect(self.reject);root.addWidget(actions)
        self.kind.currentIndexChanged.connect(self.changed);self.changed()

    def changed(self):
        model=self.kind.currentData()=='model_mismatch';self.model.setEnabled(model);self.table.setEnabled(bool(self.kind.currentData()) and not model)

    def add(self,row=None):
        if self.table.rowCount()>=8:return
        row=row or {};index=self.table.rowCount();self.table.insertRow(index)
        self.table.setItem(index,0,QTableWidgetItem(row.get('target','')));self.table.setItem(index,1,QTableWidgetItem(str(row.get('absolute_sigma',row.get('relative_sigma',.01)))))
        for column,choices,selected in [(2,['Relative','Absolute'],'Absolute' if row.get('absolute_sigma') else 'Relative'),(3,['normal','uniform'],row.get('distribution','normal'))]:
            widget=QComboBox();widget.addItems(choices);widget.setCurrentText(selected);self.table.setCellWidget(index,column,widget)
        self.table.setItem(index,4,QTableWidgetItem(row.get('group','')))
        self.table.setItem(index,5,QTableWidgetItem(str(row.get('rho',1 if row.get('group') else 0))))

    def save(self):
        try:
            kind=self.kind.currentData()
            if not kind:self.value=None;self.accept();return
            value=dict(kind=kind,cell=self.cell.currentData(),count=self.count.value(),seed=int(self.seed.text()),variations=[])
            if kind=='model_mismatch':value['model']=self.model.currentData()
            else:
                for i in range(self.table.rowCount()):
                    row=dict(target=self.table.item(i,0).text().strip(),distribution=self.table.cellWidget(i,3).currentText())
                    row['absolute_sigma' if self.table.cellWidget(i,2).currentText()=='Absolute' else 'relative_sigma']=scalar(self.table.item(i,1).text())
                    group=self.table.item(i,4).text().strip();rho=scalar(self.table.item(i,5).text())
                    if group:row['group']=group
                    if group or rho:row['rho']=rho
                    value['variations'].append(row)
            configuration(self.project,{**self.plan,'statistics':value});self.value=value;self.accept()
        except Exception as exc:self.error.setText(str(exc))


class StatisticsReport(QDialog):
    def __init__(self,parent,campaign):
        super().__init__(parent);self.campaign=campaign;self.setWindowTitle('Statistical verification results');self.resize(850,480)
        root=QVBoxLayout(self);self.note=QLabel();self.note.setWordWrap(True);root.addWidget(self.note)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(['Conditions','Trials','Passed','Failed','Unresolved','Pass fraction','95% Wilson interval'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);root.addWidget(self.table,1)
        refresh=QPushButton('Refresh saved evidence');refresh.clicked.connect(self.refresh);root.addWidget(refresh);self.refresh()

    def refresh(self):
        report=self.campaign.statistics()
        if report is None:self.note.setText('This deterministic PVT campaign has no statistical trials.');return
        self.note.setText(report['scope']+f" Seed {report['seed']}. Unresolved simulations and measurement errors remain explicit; yield and confidence are withheld until every trial resolves.")
        rows=[('All tests and PVT conditions',report['joint'])]+[(f"{r['corner']} / {r['temperature']:g} °C"+(f" / {r['voltage']:g} V" if r['voltage'] is not None else ''),r) for r in report['pvt']]
        self.table.setRowCount(len(rows))
        for i,(name,row) in enumerate(rows):
            interval=row['confidence_95'];fraction=row['pass_fraction']
            values=[name,row['trials'],row['passed'],row['failed'],row['unresolved'],f'{fraction:.2%}' if fraction is not None else 'Unresolved',f'{interval[0]:.2%}–{interval[1]:.2%}' if interval else 'Unresolved']
            for j,value in enumerate(values):self.table.setItem(i,j,QTableWidgetItem(str(value)))
