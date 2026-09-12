"""Preview and atomically create a saved square spiral from the Tools menu."""
import math

from PySide6.QtCore import Qt,QTimer,QPointF,QRectF
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,
    QLabel,QComboBox,QLineEdit,QSpinBox,QDoubleSpinBox,QCheckBox,QPushButton,QScrollArea)

from . import inductor
from .model import clone
from .layout import polygon
from .layout_routing import via_recipes
from .layout_vias import technology


class SpiralPreview(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.paths=[];self.pins=[];self.bounds=QRectF()
        self.setMinimumSize(200,200);self.setAccessibleName('Inductor layout preview')

    def set_proposal(self,proposal):
        self.paths=[];self.pins=[];self.bounds=QRectF()
        if proposal:
            colors={l['name']:l['color'] for l in proposal['pdk']['layers']}
            # Return conductor first, winding second, via cuts and pads last.
            shapes=sorted(proposal['shapes'],key=lambda s:0 if s['pcell_role']=='body.underpass' else 1 if s['kind']=='path' else 2)
            for shape in shapes:
                poly=polygon(shape);path=QPainterPath()
                points=list(poly.each_point_hull())
                path.moveTo(points[0].x,-points[0].y)
                for pt in points[1:]:path.lineTo(pt.x,-pt.y)
                path.closeSubpath()
                for hole in range(poly.holes()):
                    pts=list(poly.each_point_hole(hole));path.moveTo(pts[0].x,-pts[0].y)
                    for pt in pts[1:]:path.lineTo(pt.x,-pt.y)
                    path.closeSubpath()
                self.paths.append((path,QColor(colors[shape['layer']])));self.bounds=self.bounds.united(path.boundingRect())
            self.pins=proposal['pins']
        self.update()

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(),self.palette().base());painter.setPen(self.palette().mid().color())
        painter.drawRoundedRect(self.rect().adjusted(1,1,-1,-1),6,6)
        if not self.paths:
            painter.setPen(self.palette().text().color());painter.drawText(self.rect().adjusted(18,18,-18,-18),Qt.AlignCenter|Qt.TextWordWrap,'Enter valid dimensions to preview the spiral.');return
        scale=min((self.width()-70)/max(1,self.bounds.width()),(self.height()-70)/max(1,self.bounds.height()))
        painter.translate(self.width()/2,self.height()/2);painter.scale(scale,scale);painter.translate(-self.bounds.center())
        for path,color in self.paths:
            painter.setPen(QPen(color.lighter(125),0));color.setAlpha(195);painter.setBrush(color);painter.drawPath(path)
        transform=painter.transform();painter.resetTransform();font=painter.font();font.setBold(True);painter.setFont(font)
        painter.setPen(self.palette().text().color())
        for pin in self.pins:
            pt=transform.map(QPointF(pin['point'][0],-pin['point'][1]));painter.drawText(QRectF(pt.x()-10,pt.y()+8,24,22),Qt.AlignCenter,pin['pin'].upper())


class InductorDialog(QDialog):
    def __init__(self,owner,did=None):
        super().__init__(owner);self.owner=owner;self.cid=owner.cid;self.project_id=owner.project['id'];self.proposal=None;self.loading=True
        self.setWindowTitle('Inductor creator');self.setWindowModality(Qt.WindowModal);self.setSizeGripEnabled(True)
        self.tech=technology(owner.project);self.base=inductor.defaults(owner.project);self.recipes=via_recipes(self.tech)
        if owner.cell['shapes']:
            boxes=[polygon(s).bbox() for s in owner.cell['shapes']];grid=self.tech['grid']
            data=inductor.geometry(self.tech,self.base)
            self.base['x']=math.ceil((max(b.right for b in boxes)+data['outer_nm']/2+self.base['lead']+10000)/grid)*grid
        outer=QVBoxLayout(self);intro=QLabel('Create a square spiral with an underpass and two terminals. Select an existing schematic L or create a linked one.');intro.setWordWrap(True);outer.addWidget(intro)
        body=QHBoxLayout();outer.addLayout(body,1);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setMinimumWidth(270)
        form_widget=QWidget();form=QFormLayout(form_widget);form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow);scroll.setWidget(form_widget);body.addWidget(scroll,1)
        self.target=QComboBox();self.target.setAccessibleName('Schematic inductor');self.target.addItem('New schematic inductor',None)
        for d in owner.cell['devices']:
            if d['kind']=='L' and not d.get('native_spice'):self.target.addItem(d['name']+' · '+d['value']+' H',d['id'])
        form.addRow('Link to',self.target)
        names={d['name'].casefold() for d in owner.cell['devices']};i=1
        while ('L'+str(i)).casefold() in names:i+=1
        self.new_name='L'+str(i);self.name=QLineEdit(self.new_name);self.p_net=QLineEdit(self.new_name+'_p');self.n_net=QLineEdit(self.new_name+'_n')
        for label,widget in (('Name',self.name),('P net',self.p_net),('N net',self.n_net)):
            widget.setAccessibleName(label);form.addRow(label,widget);widget.textChanged.connect(self.schedule)
        self.use_estimate=QCheckBox('Set schematic L to the estimate');form.addRow(self.use_estimate);self.use_estimate.toggled.connect(self.schedule)
        self.fields={}
        for key,label,low,high in (('turns','Turns',1,32),('width','Trace width (µm)',.001,2000),('spacing','Spacing (µm)',.001,2000),('inner','Inner opening (µm)',.001,2000),('lead','Lead length (µm)',.001,2000),('x','Origin X (µm)',-100000,100000),('y','Origin Y (µm)',-100000,100000),('via_rows','Via rows',1,8),('via_columns','Via columns',1,8)):
            integer=key in ('turns','via_rows','via_columns');spin=QSpinBox() if integer else QDoubleSpinBox()
            if not integer:spin.setDecimals(3);spin.setSingleStep(self.tech['grid']*(1 if key in ('x','y') else 2)/1000)
            spin.setRange(low,high);spin.setKeyboardTracking(False);spin.setAccessibleName(label);spin.valueChanged.connect(self.schedule);self.fields[key]=spin;form.addRow(label,spin)
        self.via=QComboBox();self.via.setAccessibleName('Via stack')
        for recipe in self.recipes:self.via.addItem(recipe['name'],recipe['name'])
        form.addRow('Via stack',self.via);self.via.currentIndexChanged.connect(self.stack_changed)
        self.metal=QComboBox();self.metal.setAccessibleName('Spiral metal');form.addRow('Spiral metal',self.metal);self.metal.currentIndexChanged.connect(self.schedule)
        self.rotation=QComboBox();self.rotation.setAccessibleName('Rotation')
        for angle in (0,90,180,270):self.rotation.addItem(str(angle)+'°',angle)
        form.addRow('Rotation',self.rotation);self.rotation.currentIndexChanged.connect(self.schedule)
        self.mirror=QCheckBox('Mirror horizontally');form.addRow(self.mirror);self.mirror.toggled.connect(self.schedule)
        grid_note=QLabel(f'Dimensions: multiples of {2*self.tech["grid"]/1000:g} µm. Origin: {self.tech["grid"]/1000:g} µm grid.');grid_note.setWordWrap(True);form.addRow(grid_note)
        right=QVBoxLayout();body.addLayout(right,1);self.preview=SpiralPreview();right.addWidget(self.preview,1)
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setTextFormat(Qt.PlainText);right.addWidget(self.summary)
        note=QLabel('DC estimate: Mohan current-sheet formula. Leads, substrate loss, Q and resonance are excluded. Use process DRC and qualified EM/device extraction before fabrication.');note.setWordWrap(True);right.addWidget(note)
        self.error=QLabel();self.error.setWordWrap(True);self.error.setTextFormat(Qt.PlainText);self.error.setAccessibleName('Inductor validation');outer.addWidget(self.error)
        buttons=QHBoxLayout();outer.addLayout(buttons);refresh=QPushButton('Refresh preview');refresh.clicked.connect(self.refresh_preview);buttons.addWidget(refresh);buttons.addStretch()
        self.apply_button=QPushButton('Create inductor');self.apply_button.setDefault(True);self.apply_button.clicked.connect(self.apply);buttons.addWidget(self.apply_button)
        close=QPushButton('Close');close.clicked.connect(self.reject);buttons.addWidget(close)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(100);self.timer.timeout.connect(self.refresh_preview)
        self.target.currentIndexChanged.connect(self.target_changed)
        self.target.setCurrentIndex(max(0,self.target.findData(did)));self.loading=False;self.target_changed()
        screen=owner.screen().availableGeometry();self.resize(min(940,screen.width()-40),min(680,screen.height()-60));self.setMinimumSize(580,400)

    def stack_changed(self,*_):
        prior=self.metal.currentText();self.metal.clear();recipe=next(v for v in self.recipes if v['name']==self.via.currentData())
        self.metal.addItems([recipe['upper'],recipe['lower']]);self.metal.setCurrentText(prior if prior in (recipe['upper'],recipe['lower']) else recipe['upper']);self.schedule()

    def target_changed(self,*_):
        if self.loading:return
        self.loading=True;did=self.target.currentData();cell=self.owner.cell;d=next((d for d in cell['devices'] if d['id']==did),None)
        record=next((r for r in cell.get('parametric_devices',[]) if did and r['device_id']==did),None)
        spec=clone(self.base)
        if record and record['spec'].get('kind')=='inductor':
            try:spec=inductor.current_spec(cell,record)
            except ValueError:spec=clone(record['spec'])
        self.name.setText(d['name'] if d else self.new_name);self.p_net.setText(d['nets']['p'] if d else self.new_name+'_p');self.n_net.setText(d['nets']['n'] if d else self.new_name+'_n')
        for widget in (self.name,self.p_net,self.n_net):widget.setReadOnly(bool(d))
        self.use_estimate.setChecked(not d);self.use_estimate.setEnabled(bool(d))
        for key,spin in self.fields.items():spin.setValue(spec[key] if key in ('turns','via_rows','via_columns') else spec[key]/1000)
        self.via.setCurrentIndex(max(0,self.via.findData(spec['via'])));self.stack_changed();self.metal.setCurrentText(spec['metal']);self.rotation.setCurrentIndex(self.rotation.findData(spec['rotation']));self.mirror.setChecked(spec['mirror'])
        self.apply_button.setText('Regenerate inductor' if record else 'Create inductor');self.loading=False;self.refresh_preview()

    def schedule(self,*_):
        if self.loading:return
        self.proposal=None;self.apply_button.setEnabled(False);self.timer.start()

    def spec(self):
        return dict(kind='inductor',shape='square',**{k:int(v.value()) if k in ('turns','via_rows','via_columns') else round(v.value()*1000) for k,v in self.fields.items()},
            via=self.via.currentData(),metal=self.metal.currentText(),rotation=self.rotation.currentData(),mirror=self.mirror.isChecked())

    def refresh_preview(self):
        self.timer.stop();self.proposal=None
        try:
            if self.owner.project['id']!=self.project_id or self.owner.cid!=self.cid:raise ValueError('The open project or cell changed. Close and reopen the creator.')
            self.proposal=inductor.plan(self.owner.project,self.cid,self.spec(),did=self.target.currentData(),name=self.name.text().strip(),
                nets=dict(p=self.p_net.text().strip(),n=self.n_net.text().strip()),use_estimate=self.use_estimate.isChecked(),locked=self.owner.layout.locked_layers)
            p=self.proposal;record=next(r for r in p['cell']['parametric_devices'] if r['device_id']==p['device_id']);spec=record['spec']
            recipe=next(r for r in self.recipes if r['name']==spec['via']);underpass=recipe['lower'] if spec['metal']==recipe['upper'] else recipe['upper']
            summary=f"Estimated DC L: {p['estimate_h']*1e9:.4g} nH\nOuter winding: {p['outer_nm']/1000:g} × {p['outer_nm']/1000:g} µm · {p['via_count']} vias\nSpiral: {spec['metal']} · Underpass: {underpass}"
            if self.target.currentData() and not self.use_estimate.isChecked():summary+=f"\nSchematic value retained: {record['electrical']['target']*1e9:.4g} nH"
            self.summary.setText(summary);self.error.clear()
        except (ValueError,KeyError,StopIteration) as exc:self.error.setText(str(exc));self.summary.clear()
        self.preview.set_proposal(self.proposal);self.apply_button.setEnabled(self.proposal is not None)

    def apply(self):
        if not self.proposal:return
        try:
            if not self.owner.idle_edit():return
            if self.owner.cid!=self.cid:raise ValueError('The active cell changed. Reopen the creator.')
            ids=[]
            self.owner.commit(lambda p:ids.extend(inductor.install(p,self.proposal,locked=self.owner.layout.locked_layers)),'Generate linked inductor')
            if not ids:return
            self.owner.mode_combo.setCurrentIndex(1);self.owner.select(ids,'layout');self.owner.layout.fit();self.accept()
        except (ValueError,KeyError) as exc:
            self.proposal=None;self.apply_button.setEnabled(False);self.error.setText(str(exc));self.preview.set_proposal(None)
