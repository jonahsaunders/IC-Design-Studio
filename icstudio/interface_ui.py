"""Explicit terminal mapping and revision-bound interface review."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QTableWidget,
 QTableWidgetItem,QHeaderView,QPushButton,QCheckBox,QPlainTextEdit,QTabWidget,QWidget)
from . import interface_update as migration

class InterfaceReview(QDialog):
    def __init__(self,studio,cid,symbol,base,done):
        super().__init__(studio);self.studio=studio;self.cid=cid;self.symbol=symbol;self.base=base;self.on_applied=done;self.prepared=None;self.loading=False
        self.setWindowTitle('Review electrical interface update');self.resize(920,690);self.setWindowModality(Qt.WindowModal);v=QVBoxLayout(self)
        note=QLabel('Map existing terminals to the proposed interface. Disconnect preserves wire stubs; added terminals need an explicit connection or remain unconnected. Apply commits every view together; Undo restores the complete update.');note.setWordWrap(True);v.addWidget(note)
        self.tabs=QTabWidget();v.addWidget(self.tabs);self.mapping=QTableWidget(0,2);self.mapping.setHorizontalHeaderLabels(['Existing terminal','Proposed terminal']);self.mapping.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.tabs.addTab(self.mapping,'Terminal mapping')
        info=migration.describe(studio.project,cid,symbol,base);self.info=info;self.mapping.setRowCount(len(info['mapping']))
        for row,(old,new) in enumerate(info['mapping'].items()):
            it=QTableWidgetItem(old);it.setFlags(it.flags()&~Qt.ItemIsEditable);self.mapping.setItem(row,0,it);combo=QComboBox();combo.addItem('Choose mapping…',-1);combo.addItem('Disconnect',None)
            for name in symbol['pin_order']:combo.addItem(name,name)
            combo.setCurrentIndex(combo.findData(new) if new is not None else 0);self.mapping.setCellWidget(row,1,combo);combo.currentIndexChanged.connect(self.mapping_changed)
        self.connections=QTableWidget(0,3);self.connections.setHorizontalHeaderLabels(['Instance / parent cell','Added terminal','Net (blank = unconnected)']);self.connections.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.tabs.addTab(self.connections,'Instance connections');self.connections.itemChanged.connect(self.invalidate)
        self.physical=QTableWidget(0,4);self.physical.setHorizontalHeaderLabels(['Added physical port','Layer (blank = unassigned)','X (nm)','Y (nm)']);self.physical.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.tabs.addTab(self.physical,'Physical ports');self.physical.itemChanged.connect(self.invalidate)
        self.drop_probes=QCheckBox('Remove invalid saved probes and their dependent measurements (listed in review)');self.drop_probes.toggled.connect(self.invalidate);v.addWidget(self.drop_probes)
        self.summary=QPlainTextEdit();self.summary.setReadOnly(True);v.addWidget(self.summary,1);self.error=QLabel();self.error.setWordWrap(True);v.addWidget(self.error);buttons=QHBoxLayout();v.addLayout(buttons)
        self.refresh_button=QPushButton('Refresh review');self.refresh_button.clicked.connect(self.prepare);buttons.addWidget(self.refresh_button);buttons.addStretch();cancel=QPushButton('Cancel');cancel.clicked.connect(self.reject);buttons.addWidget(cancel);self.apply_button=QPushButton('Apply reviewed update');self.apply_button.clicked.connect(self.apply);self.apply_button.setEnabled(False);buttons.addWidget(self.apply_button);self.mapping_changed();self.prepare()
    def invalidate(self,*_):
        if self.loading:return
        self.prepared=None;self.apply_button.setEnabled(False);self.error.setText('Refresh the review after changing mappings or connections.')
    def values(self):
        return {self.mapping.item(i,0).text():self.mapping.cellWidget(i,1).currentData() for i in range(self.mapping.rowCount())}
    def mapping_changed(self,*_):
        self.loading=True;old={(self.connections.item(i,0).data(Qt.UserRole),self.connections.item(i,1).text()):self.connections.item(i,2).text() for i in range(self.connections.rowCount())};ports={self.physical.item(i,0).text():[self.physical.cellWidget(i,1).currentText(),self.physical.item(i,2).text(),self.physical.item(i,3).text()] for i in range(self.physical.rowCount())}
        added=[n for n in self.symbol['pin_order'] if n not in self.values().values()];rows=[(use,pin) for use in self.info['instances'] for pin in added];self.connections.setRowCount(len(rows))
        for i,(use,pin) in enumerate(rows):
            for j,value in enumerate((use['cell_name']+' / '+use['name'],pin,old.get((use['id'],pin),''))):
                it=QTableWidgetItem(value)
                if j<2:it.setFlags(it.flags()&~Qt.ItemIsEditable)
                if j==0:it.setData(Qt.UserRole,use['id'])
                self.connections.setItem(i,j,it)
        self.physical.setRowCount(len(added));layers=['']+[l['name'] for l in self.studio.project['pdk']['layers'] if l['name'] in self.studio.project['pdk'].get('connectivity',{}).get('conductors',['metal1','metal2'])]
        for i,name in enumerate(added):
            previous=ports.get(name,['','0','0']);it=QTableWidgetItem(name);it.setFlags(it.flags()&~Qt.ItemIsEditable);self.physical.setItem(i,0,it);combo=QComboBox();combo.addItems(layers);combo.setCurrentText(previous[0]);self.physical.setCellWidget(i,1,combo);combo.currentTextChanged.connect(self.invalidate)
            for j in (2,3):self.physical.setItem(i,j,QTableWidgetItem(previous[j-1]))
        self.loading=False;self.invalidate()
    def prepare(self):
        self.prepared=None;self.apply_button.setEnabled(False)
        try:
            mapping=self.values()
            if -1 in mapping.values():raise ValueError('Choose a replacement or Disconnect for every removed terminal.')
            connections={};physical={}
            for i in range(self.connections.rowCount()):connections.setdefault(self.connections.item(i,0).data(Qt.UserRole),{})[self.connections.item(i,1).text()]=self.connections.item(i,2).text().strip()
            for i in range(self.physical.rowCount()):
                layer=self.physical.cellWidget(i,1).currentText();physical[self.physical.item(i,0).text()]={'layer':layer,'point':[int(self.physical.item(i,j).text()) for j in (2,3)]} if layer else None
            self.prepared=migration.plan(self.studio.project,self.cid,self.symbol,self.base,mapping,connections,physical,self.drop_probes.isChecked());impact=self.prepared['impact'];lines=['REVIEW · '+str(len(impact['instances']))+' instance(s), '+str(len(impact['physical_ports']))+' existing physical port(s), '+str(len(impact['testbenches']))+' affected saved bench(es).','', 'Terminal order: '+', '.join(self.symbol['pin_order']),'Added: '+(', '.join(impact['added']) or 'none'),'Removed: '+(', '.join(impact['removed']) or 'none')]
            lines+=['Map '+old+' → '+(new or 'Disconnect') for old,new in mapping.items() if old!=new]
            lines+=['Instance: '+u['cell_name']+'/'+u['name']+(' · linked layout' if u['physical'] else '')+' · '+json.dumps(u['nets'],sort_keys=True) for u in impact['instances']]
            lines+=['Disconnect '+r['instance']+'.'+r['pin']+' from '+r['net'] for r in impact['disconnected']]
            lines+=['Bench: '+t['name']+' · saved results become stale' for t in impact['testbenches']]
            lines+=['Remove bench data: '+json.dumps(t,sort_keys=True) for t in impact['bench_changes']]
            lines+=['Unassigned physical port: '+n+' · flagged by electrical checks' for n in impact['unassigned_physical']]
            uses={u['id']:u['cell_name']+'/'+u['name'] for u in impact['instances']}
            for did,values in connections.items():lines+=['Added connection '+uses[did]+'.'+pin+' → '+(net or 'unconnected') for pin,net in values.items()]
            self.summary.setPlainText('\n'.join(lines));self.error.clear();self.apply_button.setEnabled(True)
        except (ValueError,KeyError,StopIteration) as e:self.error.setText(str(e))
    def apply(self):
        if not self.prepared:return
        try:
            if not self.studio.capture_commit(lambda p:migration.apply(p,self.prepared),'Apply reviewed electrical interface'):raise ValueError('Resolve pending property edits first.')
            self.on_applied();self.accept()
        except (ValueError,KeyError) as e:self.error.setText(str(e));self.prepared=None;self.apply_button.setEnabled(False)
