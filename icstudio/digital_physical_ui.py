"""Physical intent editor: geometry, pins, macros, and captured flow scripts."""
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QTabWidget,QWidget,QFormLayout,
    QLineEdit,QDoubleSpinBox,QSpinBox,QPlainTextEdit,QTableWidget,QTableWidgetItem,
    QHeaderView,QPushButton,QLabel,QDialogButtonBox)
from .model import clone
from .digital_physical import DEFAULTS,validate_settings


class PhysicalEditor(QDialog):
    def __init__(self,parent,settings):
        super().__init__(parent);self.value=None;self.settings={**clone(DEFAULTS),**clone(settings)}
        self.setWindowTitle('Physical implementation');self.resize(850,620);root=QVBoxLayout(self)
        note=QLabel('Physical edits are saved with the cell and captured in each implementation run. Coordinates and halos use micrometres.');note.setWordWrap(True);root.addWidget(note)
        self.tabs=QTabWidget();root.addWidget(self.tabs,1);page=QWidget();form=QFormLayout(page);self.tabs.addTab(page,'Floorplan');self.edits={}
        for key,title in (('die_area','Die x1 y1 x2 y2'),('core_area','Core x1 y1 x2 y2'),('min_routing_layer','Lowest routing layer'),('max_routing_layer','Highest routing layer')):
            value=self.settings.get(key,'');edit=QLineEdit(' '.join(map(str,value)) if isinstance(value,list) else value);edit.setAccessibleName(title);form.addRow(title,edit);self.edits[key]=edit
        self.density=QDoubleSpinBox();self.density.setRange(.05,.95);self.density.setSingleStep(.05);self.density.setValue(self.settings['place_density']);form.addRow('Placement density',self.density)
        self.threads=QSpinBox();self.threads.setRange(1,64);self.threads.setValue(self.settings['threads']);form.addRow('Worker threads',self.threads)
        self.halo=QDoubleSpinBox();self.halo.setRange(0,10000);self.halo.setDecimals(3);self.halo.setValue(self.settings.get('macro_halo_um',0));form.addRow('Macro halo',self.halo)
        self.pins=self.grid('Pin groups',['Pin expression','Edge'],[[p['pins'],p['edge']] for p in self.settings.get('pin_constraints',[])])
        self.macros=self.grid('Macros',['Instance','X (µm)','Y (µm)','Orientation'],[[m['name'],m['x'],m['y'],m.get('orientation','R0')] for m in self.settings.get('macro_placements',[])])
        self.scripts={}
        for key,title in (('io_constraints_tcl','Advanced pins'),('macro_placement_tcl','Advanced placement'),('pdn_tcl','Power grid')):
            page=QWidget();layout=QVBoxLayout(page);note=QLabel('Optional OpenROAD Tcl. This script is captured and executed by the implementation engine. Leave empty to use the platform defaults.');note.setWordWrap(True);layout.addWidget(note)
            edit=QPlainTextEdit();edit.setPlainText(self.settings.get(key,''));edit.setAccessibleName(title+' Tcl');layout.addWidget(edit);self.tabs.addTab(page,title);self.scripts[key]=edit
        self.error=QLabel();self.error.setWordWrap(True);root.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.apply);buttons.rejected.connect(self.reject);root.addWidget(buttons)

    def grid(self,title,columns,rows):
        page=QWidget();layout=QVBoxLayout(page);grid=QTableWidget(0,len(columns));grid.setHorizontalHeaderLabels(columns);grid.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);layout.addWidget(grid)
        def add(values=None):
            i=grid.rowCount();grid.insertRow(i)
            for j,v in enumerate(values or ['']*len(columns)):grid.setItem(i,j,QTableWidgetItem(str(v)))
        for row in rows:add(row)
        bar=QHBoxLayout();layout.addLayout(bar);b=QPushButton('Add');b.clicked.connect(lambda:add());bar.addWidget(b);b=QPushButton('Remove');b.clicked.connect(lambda:grid.removeRow(grid.currentRow()));bar.addWidget(b);bar.addStretch();self.tabs.addTab(page,title);return grid

    def apply(self):
        try:
            value={key:[float(v) for v in edit.text().split()] if key.endswith('_area') else edit.text().strip() for key,edit in self.edits.items()}
            value.update(place_density=self.density.value(),threads=self.threads.value(),macro_halo_um=self.halo.value())
            value['pin_constraints']=[{'pins':self.pins.item(i,0).text().strip(),'edge':self.pins.item(i,1).text().strip()} for i in range(self.pins.rowCount())]
            value['macro_placements']=[{'name':self.macros.item(i,0).text().strip(),'x':float(self.macros.item(i,1).text()),'y':float(self.macros.item(i,2).text()),'orientation':self.macros.item(i,3).text().strip() or 'R0'} for i in range(self.macros.rowCount())]
            value.update({key:edit.toPlainText() for key,edit in self.scripts.items()});validate_settings(value);self.value=value;self.accept()
        except (ValueError,AttributeError) as exc:self.error.setText(str(exc))
