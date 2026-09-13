"""Preview and atomically create a saved square spiral from the Tools menu."""
import math

from PySide6.QtCore import Qt,QTimer,QPointF,QRectF,Slot
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,
    QLabel,QComboBox,QLineEdit,QSpinBox,QDoubleSpinBox,QCheckBox,QPushButton,QScrollArea,
    QTabWidget,QTableWidget,QTableWidgetItem,QHeaderView)

from . import inductor
from .model import clone
from .layout import polygon
from .layout_routing import via_recipes
from .layout_vias import technology
from .inductor_jobs import Job,start


class SpiralPreview(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.paths=[];self.pins=[];self.bounds=QRectF();self.pending=False;self.error_box=None;self.dimensions='';self.legend=[]
        self.setMinimumSize(200,200);self.setAccessibleName('Inductor layout preview')

    def set_proposal(self,proposal):
        self.paths=[];self.pins=[];self.bounds=QRectF()
        if proposal:
            colors={l['name']:l['color'] for l in proposal['pdk']['layers']}
            self.legend=[(name,QColor(colors[name])) for name in dict.fromkeys(s['layer'] for s in proposal['shapes'])]
            self.dimensions=f"Winding {proposal.get('outer_x_nm',proposal['outer_nm'])/1000:g} × {proposal.get('outer_y_nm',proposal['outer_nm'])/1000:g} µm"
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
        scale=min((self.width()-70)/max(1,self.bounds.width()),(self.height()-100)/max(1,self.bounds.height()))
        painter.translate(self.width()/2,self.height()/2);painter.scale(scale,scale);painter.translate(-self.bounds.center())
        if self.pending:painter.setOpacity(.45)
        for path,color in self.paths:
            painter.setPen(QPen(color.lighter(125),0));color.setAlpha(195);painter.setBrush(color);painter.drawPath(path)
        if self.error_box:
            x0,y0,x1,y1=self.error_box;painter.setBrush(Qt.NoBrush);pen=QPen(QColor('#d34c4c'));pen.setWidthF(2/scale);painter.setPen(pen)
            painter.drawRect(QRectF(x0,-y1,max(x1-x0,5/scale),max(y1-y0,5/scale)))
        transform=painter.transform();painter.resetTransform();painter.setOpacity(1);font=painter.font();font.setBold(True);painter.setFont(font)
        painter.setPen(self.palette().text().color())
        for pin in self.pins:
            pt=transform.map(QPointF(pin['point'][0],-pin['point'][1]));painter.drawText(QRectF(pt.x()-10,pt.y()+8,24,22),Qt.AlignCenter,pin['pin'].upper())
        painter.drawText(QRectF(10,7,self.width()-20,22),Qt.AlignCenter,self.dimensions)
        if self.pending:painter.drawText(QRectF(10,29,self.width()-20,22),Qt.AlignCenter,'Preview only · awaiting valid placement')
        x=12
        for name,color in self.legend:
            painter.fillRect(QRectF(x,self.height()-23,10,10),color);painter.setPen(self.palette().text().color())
            painter.drawText(QPointF(x+15,self.height()-13),name);x+=painter.fontMetrics().horizontalAdvance(name)+30


class InductorDialog(QDialog):
    def __init__(self,owner,did=None):
        super().__init__(owner);self.owner=owner;self.cid=owner.cid;self.project_id=owner.project['id'];self.proposal=None;self.loading=True
        self.token=0;self.jobs={};self.search_token=None;self.search_serial=-1;self.candidates=[];self.last_error=None;self.closed=False
        self.finished.connect(self.stop_jobs)
        self.setWindowTitle('Inductor creator');self.setWindowModality(Qt.WindowModal);self.setSizeGripEnabled(True)
        self.tech=technology(owner.project);self.base=inductor.defaults(owner.project);self.recipes=via_recipes(self.tech)
        if owner.cell['shapes']:
            boxes=[polygon(s).bbox() for s in owner.cell['shapes']];grid=self.tech['grid']
            data=inductor.geometry(self.tech,self.base)
            self.base['x']=math.ceil((max(b.right for b in boxes)+data['outer_nm']/2+self.base['lead']+10000)/grid)*grid
        outer=QVBoxLayout(self);intro=QLabel('Design a spiral manually or search toward a target inductance. Link its layout to a new or existing schematic L.');intro.setWordWrap(True);outer.addWidget(intro)
        body=QHBoxLayout();outer.addLayout(body,1);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setMinimumWidth(285)
        self.tabs=QTabWidget();body.addWidget(self.tabs,1)
        form_widget=QWidget();form=QFormLayout(form_widget);form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow);form.setRowWrapPolicy(QFormLayout.WrapLongRows);scroll.setWidget(form_widget);self.tabs.addTab(scroll,'Geometry')
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
        self.series_rl=QCheckBox('Simulate with estimated series R');self.series_rl.setAccessibleName('Use DC series RL model');form.addRow(self.series_rl);self.series_rl.toggled.connect(self.schedule)
        self.shape=QComboBox();self.shape.setAccessibleName('Spiral shape')
        for shape in inductor.SHAPES:self.shape.addItem(shape.title(),shape)
        form.addRow('Shape',self.shape);self.shape.currentIndexChanged.connect(self.shape_changed)
        self.fields={}
        for key,label,low,high in (('turns','Turns',1,32),('width','Trace width (µm)',.001,2000),('spacing','Spacing (µm)',.001,2000),('inner','Inner X (µm)',.001,2000),('inner_y','Inner Y (µm)',.001,2000),('lead','Lead length (µm)',.001,2000),('x','Origin X (µm)',-100000,100000),('y','Origin Y (µm)',-100000,100000),('via_rows','Via rows',1,8),('via_columns','Via columns',1,8)):
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
        details=QWidget();detail_layout=QVBoxLayout(details)
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setTextFormat(Qt.PlainText);detail_layout.addWidget(self.summary)
        note=QLabel('DC winding estimate: Mohan coefficients for regular spirals; thin-strip partial inductance for rectangles. RF performance comes from imported EM characterization.');note.setWordWrap(True);detail_layout.addWidget(note)
        detail_scroll=QScrollArea();detail_scroll.setWidgetResizable(True);detail_scroll.setWidget(details);detail_scroll.setMinimumHeight(80);detail_scroll.setMaximumHeight(190);right.addWidget(detail_scroll)
        self.error=QLabel();self.error.setWordWrap(True);self.error.setTextFormat(Qt.PlainText);self.error.setAccessibleName('Inductor validation');outer.addWidget(self.error)
        buttons=QHBoxLayout();outer.addLayout(buttons);refresh=QPushButton('Refresh preview');refresh.clicked.connect(self.refresh_preview);buttons.addWidget(refresh)
        self.fix_button=QPushButton('Apply suggested fix');self.fix_button.clicked.connect(self.fix_error);self.fix_button.hide();buttons.addWidget(self.fix_button);buttons.addStretch()
        self.apply_button=QPushButton('Create inductor');self.apply_button.setDefault(True);self.apply_button.clicked.connect(self.apply);buttons.addWidget(self.apply_button)
        close=QPushButton('Close');close.clicked.connect(self.reject);buttons.addWidget(close)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(100);self.timer.timeout.connect(self.refresh_preview)
        self.build_search_tab();self.build_em_tab()
        self.target.currentIndexChanged.connect(self.target_changed)
        self.target.setCurrentIndex(max(0,self.target.findData(did)));self.loading=False;self.target_changed()
        screen=owner.screen().availableGeometry();self.resize(min(940,screen.width()-40),min(680,screen.height()-60));self.setMinimumSize(580,400)

    def build_search_tab(self):
        widget=QWidget();layout=QVBoxLayout(widget);form=QFormLayout();layout.addLayout(form)
        self.search_fields={}
        for key,label,lo,hi,value in (('target','Target L (nH)',.000001,1000000,2),('tolerance','Tolerance (%)',.01,100,5),
                ('max_width','Max footprint X (µm)',1,5000,300),('max_height','Max footprint Y (µm)',1,5000,300),
                ('width_min','Min trace width (µm)',.001,2000,10),('width_max','Max trace width (µm)',.001,2000,10),
                ('spacing_min','Min spacing (µm)',.001,2000,3),('spacing_max','Max spacing (µm)',.001,2000,3)):
            spin=QDoubleSpinBox();spin.setDecimals(6 if key=='target' else 3);spin.setRange(lo,hi);spin.setValue(value);spin.setKeyboardTracking(False)
            spin.setAccessibleName(label);self.search_fields[key]=spin;form.addRow(label,spin);spin.valueChanged.connect(self.schedule)
        note=QLabel('Search uses the selected shape, metal, leads, via arrays and rectangle aspect ratio. It samples 1–32 turns and three widths/spacings per range.');note.setWordWrap(True);layout.addWidget(note)
        row=QHBoxLayout();self.search_button=QPushButton('Find candidates');self.search_button.clicked.connect(self.find_candidates);row.addWidget(self.search_button)
        self.cancel_button=QPushButton('Cancel');self.cancel_button.clicked.connect(self.cancel_search);self.cancel_button.setEnabled(False);row.addWidget(self.cancel_button)
        self.choose_button=QPushButton('Use candidate');self.choose_button.clicked.connect(self.choose_candidate);self.choose_button.setEnabled(False);row.addWidget(self.choose_button);layout.addLayout(row)
        self.search_status=QLabel();self.search_status.setWordWrap(True);layout.addWidget(self.search_status)
        self.candidate_table=QTableWidget(0,4);self.candidate_table.setHorizontalHeaderLabels(['L (nH)','Error','Footprint (µm)','Turns'])
        self.candidate_table.setSelectionBehavior(QTableWidget.SelectRows);self.candidate_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.candidate_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);self.candidate_table.setAccessibleName('Target inductance candidates');layout.addWidget(self.candidate_table,1)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(widget);self.tabs.addTab(scroll,'Target L')

    def build_em_tab(self):
        widget=QWidget();layout=QVBoxLayout(widget)
        note=QLabel('Create or regenerate the inductor first. Characterization exports the saved geometry, mapped layers, P/N ports and explicit physical stackup. Import solver impedance or Touchstone results to inspect L, Q and self-resonance.');note.setWordWrap(True);layout.addWidget(note)
        self.em_button=QPushButton('Open saved inductor characterization…');self.em_button.clicked.connect(self.open_em);layout.addWidget(self.em_button);layout.addStretch();self.tabs.addTab(widget,'EM results')

    def open_em(self):
        from .inductor_em_ui import CharacterizationDialog
        did=self.target.currentData()
        if did:
            self._em_dialog=CharacterizationDialog(self.owner,self.cid,did,parent=self);self._em_dialog.show()

    def shape_changed(self,*_):
        if hasattr(self,'fields') and 'inner_y' in self.fields:self.fields['inner_y'].setEnabled(self.shape.currentData()=='rectangle')
        self.schedule()

    def stack_changed(self,*_):
        prior=self.metal.currentText();self.metal.clear();recipe=next(v for v in self.recipes if v['name']==self.via.currentData())
        self.metal.addItems([recipe['upper'],recipe['lower']]);self.metal.setCurrentText(prior if prior in (recipe['upper'],recipe['lower']) else recipe['upper']);self.schedule()

    def target_changed(self,*_):
        if self.loading:return
        self.cancel_search(clear=True)
        self.loading=True;did=self.target.currentData();cell=self.owner.cell;d=next((d for d in cell['devices'] if d['id']==did),None)
        record=next((r for r in cell.get('parametric_devices',[]) if did and r['device_id']==did),None)
        spec=clone(self.base)
        if record and record['spec'].get('kind')=='inductor':
            try:spec=inductor.current_spec(cell,record)
            except ValueError:spec=clone(record['spec'])
        self.name.setText(d['name'] if d else self.new_name);self.p_net.setText(d['nets']['p'] if d else self.new_name+'_p');self.n_net.setText(d['nets']['n'] if d else self.new_name+'_n')
        for widget in (self.name,self.p_net,self.n_net):widget.setReadOnly(bool(d))
        self.use_estimate.setChecked(not d);self.use_estimate.setEnabled(bool(d))
        self.series_rl.setChecked(bool(d and d.get('inductor_rl')))
        self.shape.setCurrentIndex(self.shape.findData(spec['shape']))
        for key,spin in self.fields.items():
            value=spec.get(key,spec['inner']);spin.setValue(value if key in ('turns','via_rows','via_columns') else value/1000)
        self.fields['inner_y'].setEnabled(spec['shape']=='rectangle')
        self.em_button.setEnabled(bool(record))
        if d:self.search_fields['target'].setValue(float(__import__('icstudio.model',fromlist=['scalar']).scalar(d['value']))*1e9)
        for key in ('width','spacing'):
            for suffix in ('min','max'):self.search_fields[key+'_'+suffix].setValue(spec[key]/1000)
        self.via.setCurrentIndex(max(0,self.via.findData(spec['via'])));self.stack_changed();self.metal.setCurrentText(spec['metal']);self.rotation.setCurrentIndex(self.rotation.findData(spec['rotation']));self.mirror.setChecked(spec['mirror'])
        self.apply_button.setText('Regenerate inductor' if record else 'Create inductor');self.loading=False;self.refresh_preview()

    def schedule(self,*_):
        if self.loading:return
        self.invalidate();self.cancel_search(clear=True);self.timer.start()

    def invalidate(self):
        self.token+=1;self.proposal=None;self.apply_button.setEnabled(False)
        self.preview.pending=True;self.preview.error_box=None;self.preview.update()
        for job in self.jobs.values():
            if job.kind=='preview':job.cancel()

    def stop_jobs(self,*_):
        self.closed=True;self.timer.stop();self.token+=1
        for job in self.jobs.values():job.cancel()

    def spec(self):
        return dict(kind='inductor',shape=self.shape.currentData(),**{k:int(v.value()) if k in ('turns','via_rows','via_columns') else round(v.value()*1000) for k,v in self.fields.items() if k!='inner_y' or self.shape.currentData()=='rectangle'},
            via=self.via.currentData(),metal=self.metal.currentText(),rotation=self.rotation.currentData(),mirror=self.mirror.isChecked())

    def refresh_preview(self):
        self.timer.stop();self.invalidate()
        try:
            if self.owner.project['id']!=self.project_id or self.owner.cid!=self.cid:raise ValueError('The open project or cell changed. Close and reopen the creator.')
            project=clone(self.owner.project);project['pdk']=clone(technology(project))
            args=dict(p=project,cid=self.cid,spec=self.spec(),did=self.target.currentData(),name=self.name.text().strip(),
                nets=dict(p=self.p_net.text().strip(),n=self.n_net.text().strip()),use_estimate=self.use_estimate.isChecked(),
                series_rl=self.series_rl.isChecked(),locked=set(self.owner.layout.locked_layers))
            job=Job(self.token,'preview',args);self.jobs[self.token]=job
            job.signals.geometry.connect(self.geometry_ready,Qt.QueuedConnection);job.signals.finished.connect(self.preview_ready,Qt.QueuedConnection)
            self.show_error(None);self.error.setText('Checking geometry and placement…');start(job)
        except (ValueError,KeyError,StopIteration) as exc:self.show_error(exc)

    @Slot(int,object)
    def geometry_ready(self,token,data):
        if self.closed or token!=self.token:return
        self.preview.set_proposal(data);self.preview.pending=True

    @Slot(int,object,object)
    def preview_ready(self,token,result,error):
        self.jobs.pop(token,None)
        if self.closed or token!=self.token:return
        if error:
            self.show_error(error);return
        self.proposal=result;self.preview.pending=False;self.preview.set_proposal(result);self.show_error(None)
        self.apply_button.setEnabled(True);p=result;record=next(r for r in p['cell']['parametric_devices'] if r['device_id']==p['device_id'])
        spec=record['spec'];recipe=next(r for r in self.recipes if r['name']==spec['via']);underpass=recipe['lower'] if spec['metal']==recipe['upper'] else recipe['upper']
        target=self.search_fields['target'].value()*1e-9;error_pct=100*(p['estimate_h']/target-1)
        summary=f"Estimated DC L: {p['estimate_h']*1e9:.4g} nH\nTarget {target*1e9:g} nH · difference {error_pct:+.2f}%\nFootprint: {p['footprint_nm'][0]/1000:g} × {p['footprint_nm'][1]/1000:g} µm · {p['via_count']} vias\nSpiral: {spec['metal']} · Underpass: {underpass}"
        if self.target.currentData() and not self.use_estimate.isChecked():summary+=f"\nSchematic value retained: {record['electrical']['target']*1e9:.4g} nH"
        resistance=p['resistance']
        summary+=f"\nEstimated DC R: {resistance['total_ohm']:.4g} Ω" if resistance['total_ohm'] is not None else '\nDC R unavailable: '+resistance['reason']
        self.summary.setText(summary)

    def show_error(self,error):
        self.last_error=error;self.error.setText(str(error) if error else '')
        for widget in list(self.fields.values())+[self.shape,self.via,self.series_rl]:widget.setStyleSheet('')
        self.fix_button.setVisible(bool(getattr(error,'fixes',None)))
        self.preview.error_box=getattr(error,'bbox',None);self.preview.update()
        if error:
            self.proposal=None;self.apply_button.setEnabled(False);self.preview.pending=True
            field=getattr(error,'field',None);widget=self.fields.get(field) or {'shape':self.shape,'via':self.via,'series_rl':self.series_rl}.get(field)
            if widget:widget.setStyleSheet('border: 2px solid #c94b4b;')

    def fix_error(self):
        for key,value in getattr(self.last_error,'fixes',{}).items():
            if key in self.fields:self.fields[key].setValue(value/1000 if key not in ('turns','via_rows','via_columns') else value)

    def find_candidates(self):
        self.cancel_search(clear=True)
        # Search and preview use disjoint token ranges; editing cancels both.
        self.search_serial-=1;self.search_token=self.search_serial;token=self.search_token;v={k:s.value() for k,s in self.search_fields.items()}
        args=dict(tech=clone(technology(self.owner.project)),base=self.spec(),target_h=v['target']*1e-9,
                  max_width_nm=round(v['max_width']*1000),max_height_nm=round(v['max_height']*1000),
                  width_range=tuple(round(v['width_'+k]*1000) for k in ('min','max')),
                  spacing_range=tuple(round(v['spacing_'+k]*1000) for k in ('min','max')),tolerance=v['tolerance']/100)
        job=Job(token,'search',args);self.jobs[token]=job;job.signals.finished.connect(self.search_ready,Qt.QueuedConnection)
        self.search_button.setEnabled(False);self.cancel_button.setEnabled(True);self.search_status.setText('Searching legal geometries…');start(job)

    def cancel_search(self,clear=False):
        for job in self.jobs.values():
            if job.kind=='search':job.cancel()
        self.search_token=None
        if hasattr(self,'search_button'):
            self.search_button.setEnabled(True);self.cancel_button.setEnabled(False)
            if clear:self.candidates=[];self.candidate_table.setRowCount(0);self.search_status.clear();self.choose_button.setEnabled(False)
            else:self.search_status.setText('Search cancelled.')

    @Slot(int,object,object)
    def search_ready(self,token,result,error):
        self.jobs.pop(token,None)
        if self.closed or token!=self.search_token:return
        self.search_button.setEnabled(True);self.cancel_button.setEnabled(False)
        if error:self.search_status.setText(str(error));return
        self.candidates=result['candidates'];self.search_status.setText(result['message']);self.candidate_table.setRowCount(len(self.candidates))
        for i,candidate in enumerate(self.candidates):
            w,h=candidate['footprint_nm'];values=[f"{candidate['estimate_h']*1e9:.5g}",f"{candidate['relative_error']*100:.2f}%"+('' if candidate['within_tolerance'] else ' outside'),f'{w/1000:.3g} × {h/1000:.3g}',str(candidate['spec']['turns'])]
            for j,value in enumerate(values):
                item=QTableWidgetItem(value);item.setToolTip(f"Width {candidate['spec']['width']/1000:g} µm; spacing {candidate['spec']['spacing']/1000:g} µm; footprint {w/1000:g} × {h/1000:g} µm")
                self.candidate_table.setItem(i,j,item)
        self.choose_button.setEnabled(bool(self.candidates))
        if self.candidates:self.candidate_table.selectRow(0)

    def choose_candidate(self):
        row=self.candidate_table.currentRow()
        if not 0<=row<len(self.candidates):return
        spec=self.candidates[row]['spec'];self.loading=True
        for key,spin in self.fields.items():
            if key in spec:spin.setValue(spec[key] if key in ('turns','via_rows','via_columns') else spec[key]/1000)
        self.loading=False;self.tabs.setCurrentIndex(0);self.schedule()

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
            self.show_error(exc)
