"""Visual editing of the same native fixture specification the assistant previews."""
import json
from PySide6.QtCore import Qt, QEvent, QPointF, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QSplitter, QTabWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from . import ai_testbench, studies
from .analog_widgets import actions, scroll, table
from .canvas import Canvas
from .interchange import pin_positions
from .model import clone, scalar


class PinCanvas(Canvas):
    picked = Signal(str)

    def marks(self):
        for d in (self.cell or {}).get('devices', []):
            for pin, point in pin_positions(d).items():
                net = d['nets'][pin]
                if net in self.candidates:
                    yield net, QPointF(point[0]*self.scale, point[1]*self.scale) + self.offset

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(self.palette().highlight().color(), 3))
        for _, pt in self.marks():
            painter.drawEllipse(pt, 7, 7)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            for name, point in self.marks():
                if (event.position()-point).manhattanLength() < 16:
                    self.picked.emit(name)
                    return
        super().mousePressEvent(event)


class FixtureView(QWidget):
    def __init__(self, dark):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        self.cell_picker = QComboBox()
        self.cell_picker.setAccessibleName('Schematic to inspect')
        layout.addWidget(self.cell_picker)
        self.canvas = PinCanvas('schematic')
        self.canvas.dark = dark
        self.canvas.candidates = set()
        self.canvas.setAccessibleName('Proposed fixture and circuit schematic')
        layout.addWidget(self.canvas,1)
        self.cell_picker.hide()
        self.cell_picker.currentIndexChanged.connect(self.select_cell)

    def show_candidates(self, cell, pdk, names):
        self.cell_picker.hide()
        self.canvas.candidates = set(names)
        self.canvas.set_data(clone(cell),pdk)
        self.canvas.fit()

    def show_fixture(self, cells, dut, pdk):
        # A standalone snapshot contains the actual sources and loads; the
        # fixture that surrounds it normally contains only a single instance.
        self.cells = [cells[-1], cells[0] if len(cells)>1 else dut]
        self.pdk = pdk
        self.cell_picker.blockSignals(True)
        self.cell_picker.clear()
        self.cell_picker.addItems(['Fixture · '+self.cells[0]['name'], 'Circuit · '+self.cells[1]['name']])
        self.cell_picker.setCurrentIndex(1 if len(cells)>1 else 0)
        self.cell_picker.blockSignals(False)
        self.cell_picker.show()
        self.canvas.candidates = set()
        self.select_cell(self.cell_picker.currentIndex())

    def select_cell(self, index):
        if index >= 0:
            self.canvas.set_data(clone(self.cells[index]),self.pdk)
            self.canvas.fit()


CONNECTIONS = {
    'observe': (), 'ground': (), 'dc': ('value','ac'), 'pulse': ('low','high','period','delay','duty'),
    'resistor': ('value',), 'capacitor': ('value',),
}
DEFAULTS = {'value':'1','ac':'0','low':'0','high':'1.8','period':'10u','delay':'0','duty':'0.5'}
SWEEPS = {'op': {}, 'tran': {'stop':'100u','step':'200n'}, 'ac': {'start':'10','end':'10Meg','points':'40'}}


class FixtureEditor(QDialog):
    def __init__(self, panel, spec):
        super().__init__(panel)
        self.panel, self.spec = panel, clone(spec)
        self.project, self.cell = panel.studio.project, panel.bench_cell()
        self.candidates = spec.get('output_candidates', [])
        nets = set(self.cell['ports']) or ai_testbench.circuit_nets(self.cell)
        if (not isinstance(self.candidates, list) or any(not isinstance(n,str) or n not in nets or n=='0' for n in self.candidates)):
            raise ValueError('The suggested output candidates must be existing circuit pins.')
        self.nets = sorted(nets - {'0'})
        self.setWindowTitle('Edit Testbench Fixture')
        self.resize(880, 640)
        root = QVBoxLayout(self)
        split = QSplitter()
        root.addWidget(split,1)
        left = QWidget()
        lv = QVBoxLayout(left)
        self.view = FixtureView(panel.studio.dark)
        self.canvas = self.view.canvas
        self.view.show_candidates(self.cell,self.project['pdk'],self.candidates)
        lv.addWidget(self.view,1)
        self.output = QComboBox()
        self.output.setAccessibleName('Output pin')
        if self.candidates:
            lv.addWidget(QLabel('Choose the output from the highlighted pins'))
            self.output.addItems(['Select output…'] + self.candidates)
            lv.addWidget(self.output)
            self.canvas.picked.connect(self.output.setCurrentText)
        split.addWidget(left)
        self.tabs = QTabWidget()
        split.addWidget(self.tabs)
        split.setSizes([420,440])
        setup = QWidget()
        form = QFormLayout(setup)
        self.tabs.addTab(scroll(setup),'Analysis')
        self.name = QLineEdit(str(spec['name']))
        form.addRow('Testbench name',self.name)
        self.kind = QComboBox()
        for key, title in [('op','Operating Point'),('tran','Transient'),('ac','AC Sweep')]:
            self.kind.addItem(title,key)
        self.kind.setCurrentIndex(max(0,self.kind.findData(spec['analysis'].get('type'))))
        form.addRow('Analysis',self.kind)
        self.sweep = {}
        for key, title in [('stop','Duration (s)'),('step','Time step (s)'),('start','Start frequency (Hz)'),
                           ('end','Stop frequency (Hz)'),('points','Points per decade')]:
            field = QLineEdit(str(spec['analysis'].get(key, {**SWEEPS['tran'],**SWEEPS['ac']}[key])))
            self.sweep[key] = field
            form.addRow(title,field)
        def sweep_changed():
            for key, field in self.sweep.items():
                form.setRowVisible(field,key in SWEEPS[self.kind.currentData()])
        self.kind.currentIndexChanged.connect(sweep_changed)
        sweep_changed()
        ports = QWidget()
        details = QVBoxLayout(ports)
        self.tabs.addTab(scroll(ports),'Stimulus && Load')
        self.connections = {}
        for port in self.cell['ports']:
            config = spec['connections'].get(port, {'kind':'observe'})
            pf = QFormLayout()
            details.addLayout(pf)
            kind = QComboBox()
            kind.addItems(list(CONNECTIONS))
            kind.setCurrentText(config.get('kind','observe'))
            pf.addRow(port,kind)
            values = {}
            for key, default in DEFAULTS.items():
                field = QLineEdit(str(config.get(key, default)))
                values[key] = field
                pf.addRow(key.capitalize(),field)
            def update_fields(idx=None, pf=pf, kind=kind, values=values):
                for k,w in values.items():
                    pf.setRowVisible(w, k in CONNECTIONS[kind.currentText()])
                if 'value' in CONNECTIONS[kind.currentText()]:
                    pf.labelForField(values['value']).setText({'dc':'Voltage (V)','resistor':'Resistance (Ω)','capacitor':'Capacitance (F)'}[kind.currentText()])
            kind.currentIndexChanged.connect(update_fields)
            update_fields()
            self.connections[port] = kind, values
        self.overrides = {}
        if not self.cell['ports']:
            sf = QFormLayout()
            details.addLayout(sf)
            for key in studies.targets(self.project, self.cell['id']):
                value = studies.get_target(self.project,self.cell['id'],key)
                field = QLineEdit(str(spec.get('overrides',{}).get(key, value)))
                sf.addRow(key,field)
                self.overrides[key] = field, value
        details.addStretch()
        page = QWidget()
        pl = QVBoxLayout(page)
        self.tabs.addTab(scroll(page),'Probes && Limits')
        self.probes = {}
        for n in self.nets:
            box = QCheckBox(n)
            box.setChecked(n in spec['probes'])
            pl.addWidget(box)
            self.probes[n] = box
        self.measure = table(['Name','Probe','Minimum (V)','Maximum (V)','At (s or Hz)'],True)
        pl.addWidget(self.measure)
        actions(pl,[('Add Measurement',lambda:self.add_measure({})),('Remove Measurement',self.remove_measure)],lambda fn:fn())
        for m in spec['measurements']:
            self.add_measure(m)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.PlainText)
        root.addWidget(self.message)
        actions(root,[('Update Preview',self.preview),('Use Fixture',self.use),('Cancel',self.reject)],self.call,'Use Fixture')
        self.call(self.preview)

    def add_measure(self, m):
        row = self.measure.rowCount()
        self.measure.insertRow(row)
        self.measure.setItem(row,0,QTableWidgetItem(m.get('name',f'voltage_{row+1}')))
        box = QComboBox()
        box.addItems((['@output'] if self.candidates else []) + self.nets)
        box.setCurrentText(m.get('node', next(iter(self.nets),'')))
        self.measure.setCellWidget(row,1,box)
        for i,k in enumerate(('min','max','at'),2):
            self.measure.setItem(row,i,QTableWidgetItem(str(m.get(k,''))))

    def remove_measure(self):
        if self.measure.currentRow()>=0:
            self.measure.removeRow(self.measure.currentRow())

    def call(self, fn):
        try:
            fn()
        except (TypeError, ValueError, KeyError, OverflowError) as exc:
            self.message.setText(str(exc))

    def spec_value(self):
        kind = self.kind.currentData()
        probes = [n for n,b in self.probes.items() if b.isChecked()]
        if self.candidates:
            if self.output.currentIndex() <= 0:
                raise ValueError('Select one of the highlighted output pins.')
            if self.output.currentText() not in probes:
                probes.append(self.output.currentText())
        m = []
        for r in range(self.measure.rowCount()):
            node = self.measure.cellWidget(r,1).currentText()
            row = dict(name=self.measure.item(r,0).text(), node=self.output.currentText() if node=='@output' else node)
            for i,k in enumerate(('min','max','at'),2):
                value = self.measure.item(r,i).text().strip()
                if value:
                    row[k] = value
            m.append(row)
        con = {p:{'kind': k.currentText(), **{x:v[x].text() for x in CONNECTIONS[k.currentText()]}}
               for p,(k,v) in self.connections.items()}
        overrides = {k:w.text() for k,(w,old) in self.overrides.items() if scalar(w.text())!=old}
        return dict(name=self.name.text(), analysis={'type':kind, **{k:self.sweep[k].text() for k in SWEEPS[kind]}},
                    connections=con, probes=probes, measurements=m, overrides=overrides)

    def preview(self):
        self.panel.verify_origin()
        spec = self.spec_value()
        cells, bench, summary = ai_testbench.propose(self.project,self.cell,json.dumps(spec))
        self.view.show_fixture(cells,self.cell,self.project['pdk'])
        self.message.setText(summary.splitlines()[0])
        self.message.setToolTip(summary)
        return spec

    def use(self):
        self.spec = self.preview()
        self.accept()

    def changeEvent(self, event):
        if event.type() == QEvent.PaletteChange and hasattr(self,'canvas'):
            self.canvas.dark = self.panel.studio.dark
            self.canvas.update()
        super().changeEvent(event)
