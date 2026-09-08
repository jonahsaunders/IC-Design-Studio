"""Native layout tools and verification navigation for the analog physical flow."""
import shutil
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtWidgets import QHBoxLayout, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from .model import clone, scalar, design_digest
from .layout_edit import place_via, via_options, stretch_path, align


class LayoutToolsMixin:
    def make_ui(self):
        super().make_ui(); self._via_configuration=None
        self.layout.via_requested.connect(lambda x,y:self.guard(lambda:self.place_canvas_via(x,y)))
        self.layout.stretch_requested.connect(lambda sid,segment,offset:self.guard(lambda:self.commit(
            lambda p:stretch_path(p,self.cid,sid,segment,offset,self.layout.locked_layers),'Stretch path segment')))
        row=QHBoxLayout(); self.physical_probe=QComboBox();self.physical_probe.setAccessibleName('Physical comparison probe');row.addWidget(self.physical_probe,1)
        row.addWidget(self.button('Overlay before / after',fn=self.physical_overlay));row.addWidget(self.button('View findings',fn=self.physical_findings))
        v=self.results_tabs.widget(self.silicon_tab).layout();v.addLayout(row)
        self.physical_comparison=QTableWidget(0,5);self.physical_comparison.setHorizontalHeaderLabels(['Measurement','Schematic','Post-layout','Delta','Unit']);self.physical_comparison.setEditTriggers(QAbstractItemView.NoEditTriggers);self.physical_comparison.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.physical_comparison.setMaximumHeight(140);v.addWidget(self.physical_comparison)
        self.silicon_table.cellDoubleClicked.connect(self.physical_stage_selected)

    def make_actions(self):
        super().make_actions();menus={a.text().replace('&',''):a.menu() for a in self.menuBar().actions() if a.menu()}
        for title,fn in [('Place via…',self.via_dialog),('Stretch path segment…',self.stretch_dialog),('Stretch path with mouse',self.stretch_mouse),('Align layout selection…',self.align_dialog)]:self.action(menus['Design'],title,fn)
        self.action(menus['File'],'New GF180 3.3 V inverter',self.new_gf180_inverter)

    def new_gf180_inverter(self):
        from .gf180_layout import reference_project
        p,cid=reference_project(self.project['pdk'])
        if not self.maybe_save():return
        self.set_project(p);self.cid=cid;self._selected_testbench=p['testbenches'][0]['id'];self.refresh(True);self.open_silicon()

    def via_dialog(self):
        if not self.idle_edit():return
        options=via_options(self.project['pdk'])
        def submit(v):
            if v['placement']=='Click canvas':
                self._via_configuration=(self.cid,v['connection'],v['net'].strip());self.mode_combo.setCurrentIndex(1);self.layout.tool='via';self.layout.setFocus();self.statusBar().showMessage('Click to place vias on the layout grid. Escape exits placement.')
            else:
                ids=[]
                def edit(p):ids.extend(place_via(p,self.cid,v['connection'],[round(scalar(v[k])*1000) for k in ('x','y')],v['net'].strip(),self.layout.locked_layers))
                self.commit(edit,'Place via stack');self.mode_combo.setCurrentIndex(1);self.select(ids,'layout')
        return self.workflow_form('Place via',[('connection','Connection',list(options)),('net','Net (optional)',self.net or ''),('placement','Placement',['Click canvas','Coordinates']),('x','X (µm)','0'),('y','Y (µm)','0')],submit,'Places the cut and both conductor enclosures as editable geometry. Run connectivity and full DRC after routing.')

    def place_canvas_via(self,x,y):
        if not self._via_configuration:return
        cid,connection,net=self._via_configuration
        if cid!=self.cid:raise ValueError('The active cell changed. Start via placement again.')
        ids=[]
        def edit(p):ids.extend(place_via(p,cid,connection,[round(x),round(y)],net,self.layout.locked_layers))
        self.commit(edit,'Place via stack');self.select(ids,'layout')

    def selected_path(self):
        paths=[s for s in self.cell['shapes'] if s['id'] in self.selection and s['kind']=='path']
        if len(paths)!=1 or len(self.selection)!=1:raise ValueError('Select exactly one local path.')
        if paths[0]['layer'] in self.layout.locked_layers:raise ValueError('Unlock the path layer first.')
        return paths[0]

    def stretch_dialog(self):
        if not self.idle_edit():return
        s=self.selected_path();cid=self.cid;sid=s['id']
        return self.workflow_form('Stretch path segment',[('segment','Segment',[str(i+1) for i in range(len(s['points'])-1)]),('offset','Perpendicular offset (µm)','0.1')],
            lambda v:self.commit(lambda p:stretch_path(p,cid,sid,int(v['segment'])-1,round(scalar(v['offset'])*1000),self.layout.locked_layers),'Stretch path segment'),
            'Horizontal segments move in Y; vertical segments move in X. Connected bends follow. Terminals and ports retain their positions; check connectivity after stretching an endpoint.')

    def stretch_mouse(self):
        if not self.idle_edit():return
        self.selected_path();self.mode_combo.setCurrentIndex(1);self.layout.tool='stretch';self.layout.setFocus();self.statusBar().showMessage('Drag a segment perpendicular to itself. Escape exits stretch mode.')

    def align_dialog(self):
        if not self.idle_edit():return
        ids=list(self.selection);cid=self.cid;edges={'Left':'left','Right':'right','Top':'top','Bottom':'bottom','Horizontal center':'center_x','Vertical center':'center_y'}
        return self.workflow_form('Align layout selection',[('edge','Align',list(edges))],
            lambda v:self.commit(lambda p:align(p,cid,ids,edges[v['edge']],self.layout.locked_layers),'Align layout selection'),
            'The first selected object stays fixed. Select complete device footprints and via stacks; their terminals move with them. Parent routing and cell ports stay at their saved coordinates. Check connectivity afterward.')

    def cell_port_dialog(self):
        from .physical_cells import assign_port
        from .process_adapters import layer_datatypes
        cid=self.cid;drawing,_,_=layer_datatypes(self.project['pdk'])
        if not self.cell['ports']:raise ValueError('Declare the cell electrical ports first.')
        return self.workflow_form('Assign cell layout port',[('name','Cell port',self.cell['ports']),('layer','Conductor',[l['name'] for l in self.project['pdk']['layers'] if l['datatype']==drawing]),('x','X (µm)','0'),('y','Y (µm)','0')],lambda v:self.commit(lambda p:assign_port(p,cid,v['name'],v['layer'],[round(scalar(v[k])*1000) for k in ('x','y')]),'Assign physical cell port'))

    def refresh(self,fit=False):
        super().refresh(fit)
        if hasattr(self,'layout'):self.layout.finding_box=None

    def refresh_silicon(self):
        super().refresh_silicon()
        if not hasattr(self,'physical_comparison'):return
        r=getattr(self,'_silicon_result',None);report=r.get('silicon_report',{}) if r else {};rows=report.get('comparison',[])
        self.physical_comparison.setRowCount(len(rows))
        for i,m in enumerate(rows):
            for j,val in enumerate((m['name'],f"{m['before']:.6g}",f"{m['after']:.6g}",f"{m['delta']:+.6g}",m['unit'])):self.physical_comparison.setItem(i,j,QTableWidgetItem(val))
        old=self.physical_probe.currentData();self.physical_probe.clear()
        if report.get('testbench'):
            t=report['testbench']
            for n in t['probes']:self.physical_probe.addItem('V('+n+')',('voltage',n.lower()))
            for m in t['measurements']:
                if m['kind']=='current' and self.physical_probe.findData(('current',m['source'].lower()))<0:self.physical_probe.addItem('I('+m['source']+')',('current',m['source'].lower()))
        index=self.physical_probe.findData(old)
        if index>=0:self.physical_probe.setCurrentIndex(index)

    def silicon_waveform(self,stage):
        r=getattr(self,'_silicon_result',None)
        if not r or not r.get('silicon_report',{}).get('testbench_id'):return super().silicon_waveform(stage)
        from .verification_navigation import waveform
        wave=waveform(r,stage);probe=self.physical_probe.currentData()
        if probe:
            kind,name=probe;wave['traces']={name:wave['currents' if kind=='current' else 'traces'][name]};wave['plot_unit']='A' if kind=='current' else 'V';self.plot.set_result(wave,[name])
        self.results_tabs.setCurrentIndex(0);self.cursor_label.setText(stage+(' · STALE: design changed' if r['design_hash']!=design_digest(self.project) else ''))

    def physical_overlay(self):
        from .verification_navigation import waveform
        r=getattr(self,'_silicon_result',None)
        if not r or not self.physical_probe.currentData():raise ValueError('Run a saved-testbench physical verification first.')
        kind,name=self.physical_probe.currentData();waves=[]
        for stage in ('schematic','post-layout'):
            wave=waveform(r,stage);wave['traces']={name:wave['currents' if kind=='current' else 'traces'][name]};wave['plot_unit']='A' if kind=='current' else 'V';waves.append(wave)
        self.plot.set_result(waves[0],[name],overlays=[waves[1]]);self.results_tabs.setCurrentIndex(0);self.cursor_label.setText('Schematic / post-layout · '+self.physical_probe.currentText()+(' · STALE' if r['design_hash']!=design_digest(self.project) else ''))

    def physical_findings(self):
        r=getattr(self,'_silicon_result',None)
        if not r:raise ValueError('Run physical verification first.')
        self.show_physical_result(r);self.results_tabs.setCurrentIndex(1)

    def physical_stage_selected(self,row,col):
        self.physical_findings()
        r=self._silicon_result;name=r['silicon_report']['stages'][row]['name'];prefix='MAGIC.' if name=='drc' else 'NETGEN.' if name=='lvs' else ''
        i=next((i for i,v in enumerate(self.issues) if prefix and v['code'].startswith(prefix)),None)
        if i is not None:self.checks.selectRow(i);self.check_selected(i,0)

    def check_selected(self,row,col):
        if not 0<=row<len(self.issues):return
        issue=self.issues[row]
        if self.check_revision!=self.project['revision'] or issue.get('source_design_hash',design_digest(self.project))!=design_digest(self.project):
            self.statusBar().showMessage('These findings are stale. Run verification on the current design before navigating.');return
        key=issue.get('cell_id',self.cid)
        if key not in {c['id'] for c in self.project['cells']}:return
        if key!=self.cid:self.cid=key;self.selection=[];self.refresh(True)
        ids=list(issue.get('objects',[])) or ([issue['object']] if issue.get('object') else [])
        net=issue.get('net','');self.net=net
        if net:
            ids=list(dict.fromkeys(ids+[s['id'] for s in self.cell['shapes'] if s.get('net')==net]))
        if issue.get('bbox') or ids or net:
            self.mode_combo.setCurrentIndex(1);self.select(ids,'layout');self.net=net;self.layout.net=net
            if net:
                from .physical import connectivity
                self.layout.connection_guides=[g for g in connectivity(self.project,self.cid)['guides'] if g['net']==net]
            raw=issue.get('bbox')
            if not raw:
                shapes=[s for s in self.layout.cell['shapes'] if s['id'] in ids or s.get('device_id') in ids or (net and s.get('net')==net)]
                if shapes:
                    box=self.layout.bounds(shapes[0])
                    for s in shapes[1:]:box=box.united(self.layout.bounds(s))
                    raw=[box.left(),box.top(),box.right(),box.bottom()]
                    self.layout.visible_layers.update(s['layer'] for s in shapes)
            if raw:
                box=QRectF(QPointF(*raw[:2]),QPointF(*raw[2:])).normalized();self.layout.finding_box=list(raw);box.adjust(-500,-500,500,500);self.layout.auto_fit=False;self.layout.scale=min(self.layout.width()/box.width(),self.layout.height()/box.height());self.layout.offset=QPointF(self.layout.rect().center())-box.center()*self.layout.scale
            self.layout.update();self.statusBar().showMessage(self.cell['name']+': '+issue['message']);return
        return super().check_selected(row,col)
