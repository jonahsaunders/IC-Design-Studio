"""Saved testbenches, linked placements and precise native layout editing."""
import json,shutil
from pathlib import Path
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView,QDialog,QDialogButtonBox,QPushButton
from .model import clone,uid,scalar,validate,design_digest
from .physical_cells import terminals,instance_pins,place,ports,transform_selection,audit
from .testbenches import get


class HierarchyMixin:
    def make_ui(self):
        super().make_ui();self._selected_testbench=None;self._layout_navigation=[];self._bench_result=None
        page=QWidget();v=QVBoxLayout(page);self.bench_note=QLabel('Save a fixture schematic to reuse its stimulus, loads, analysis and measurements.');self.bench_note.setWordWrap(True);v.addWidget(self.bench_note);row=QHBoxLayout()
        for title,fn in [('New…',lambda:self.edit_testbench(True)),('Edit…',self.edit_testbench),('Duplicate',self.duplicate_testbench),('Delete',self.delete_testbench),('Open fixture',lambda:self.open_bench_cell(False)),('Open circuit',lambda:self.open_bench_cell(True)),('Simulate',self.run_testbench),('Verify layout',self.run_silicon)]:row.addWidget(self.button(title,fn=fn))
        v.addLayout(row);self.bench_table=QTableWidget(0,4);self.bench_table.setHorizontalHeaderLabels(['Saved testbench','Circuit','Analysis','Corner']);self.bench_table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.bench_table.setSelectionBehavior(QAbstractItemView.SelectRows);self.bench_table.setSelectionMode(QAbstractItemView.SingleSelection);self.bench_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.bench_table.cellClicked.connect(self.choose_bench_row);self.bench_table.cellDoubleClicked.connect(lambda *_:self.edit_testbench());v.addWidget(self.bench_table)
        self.bench_measurements=QTableWidget(0,4);self.bench_measurements.setHorizontalHeaderLabels(['Measurement','Value','Unit','Status / detail']);self.bench_measurements.setEditTriggers(QAbstractItemView.NoEditTriggers);self.bench_measurements.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);v.addWidget(self.bench_measurements);self.testbench_tab=self.results_tabs.addTab(page,'Testbenches')
        row=QHBoxLayout();row.addWidget(QLabel('Saved testbench'));self.testbench_combo=QComboBox();self.testbench_combo.setMinimumWidth(210);self.testbench_combo.currentIndexChanged.connect(self.choose_bench_combo);row.addWidget(self.testbench_combo,1);row.addWidget(self.button('Edit…',fn=self.edit_testbench));row.addWidget(self.button('All testbenches',fn=self.open_testbenches));self.results_tabs.widget(self.silicon_tab).layout().insertLayout(1,row)
        row=QHBoxLayout();row.addWidget(self.button('← Parent',fn=self.leave_layout_cell));row.addWidget(self.button('Enter selected cell',fn=self.enter_selected_cell));self.navtabs.widget(2).layout().addLayout(row)
        self.layout.orthogonal=True;self.layout.snap_to_terminals=True

    def make_actions(self):
        super().make_actions();menus={a.text().replace('&',''):a.menu() for a in self.menuBar().actions() if a.menu()}
        for menu,items in {'File':[('New SKY130 ring oscillator',self.new_ring),('Export saved SPICE testbench…',self.export_testbench)],'View':[('Saved testbenches',self.open_testbenches)],'Analysis':[('Save / edit testbench…',self.edit_testbench),('Run saved testbench',self.run_testbench),('Verify saved testbench layout',self.run_silicon)],'Design':[('Place linked physical instance…',self.place_linked_dialog),('Assign cell layout port…',self.cell_port_dialog),('Enter selected physical cell',self.enter_selected_cell),('Return to parent cell',self.leave_layout_cell),('Transform layout selection…',self.transform_layout_dialog),('Edit path vertices…',self.path_vertices_dialog),('Route linked terminals…',self.route_terminals_dialog),('Layout drawing settings…',self.layout_settings_dialog)]}.items():
            for title,fn in items:self.action(menus[menu],title,fn)

    def refresh(self,fit=False):
        super().refresh(fit)
        if hasattr(self,'bench_table'):self.refresh_testbenches()

    def refresh_testbenches(self):
        benches=self.project.get('testbenches',[]);by={c['id']:c for c in self.project['cells']};old=getattr(self,'_selected_testbench',None)
        if old not in {t['id'] for t in benches}:self._selected_testbench=next((t['id'] for t in benches if self.cid in (t['dut_cell'],t['bench_cell'])),benches[0]['id'] if benches else None)
        self.bench_table.setRowCount(len(benches));self.testbench_combo.blockSignals(True);self.testbench_combo.clear()
        for row,t in enumerate(benches):
            for col,val in enumerate((t['name'],by[t['dut_cell']]['name'],t['analysis']['type'],t['analysis'].get('corner','nominal'))):self.bench_table.setItem(row,col,QTableWidgetItem(val))
            self.testbench_combo.addItem(t['name']+' · '+by[t['dut_cell']]['name'],t['id'])
            if t['id']==self._selected_testbench:self.bench_table.selectRow(row)
        self.testbench_combo.setCurrentIndex(self.testbench_combo.findData(self._selected_testbench));self.testbench_combo.blockSignals(False)
        if not benches:self.bench_note.setText('Select a fixture schematic with one circuit instance, then choose New. Supplies and loads remain editable schematic components.');self.bench_measurements.setRowCount(0)
        else:self.bench_note.setText('Saved fixture, model corner, probes and measurements travel with the project. Physical verification uses the selected testbench and its circuit hierarchy.')
        self.refresh_silicon();self.refresh_bench_result()

    def choose_bench_row(self,row,col=0):
        if 0<=row<len(self.project.get('testbenches',[])):self._selected_testbench=self.project['testbenches'][row]['id'];self.testbench_combo.setCurrentIndex(self.testbench_combo.findData(self._selected_testbench))
    def choose_bench_combo(self,index):
        if index>=0:self._selected_testbench=self.testbench_combo.itemData(index);self.bench_table.selectRow(index);self.refresh_silicon();self.refresh_bench_result()
    def selected_testbench(self):
        benches=self.project.get('testbenches',[])
        if getattr(self,'_selected_testbench',None) not in {t['id'] for t in benches}:self._selected_testbench=next((t['id'] for t in benches if self.cid in (t['dut_cell'],t['bench_cell'])),benches[0]['id'] if benches else None)
        return get(self.project,self._selected_testbench)
    def open_testbenches(self):self.results_dock.show();self.results_tabs.setCurrentIndex(self.testbench_tab);self.resizeDocks([self.results_dock],[360],Qt.Vertical);self.refresh_testbenches()
    def edit_testbench(self,new=False):
        from .testbench_ui import editor
        return editor(self,None if new or not self.project.get('testbenches') else self.selected_testbench())
    def duplicate_testbench(self):
        t=clone(self.selected_testbench());t['id']=uid();names={t['name'].casefold() for t in self.project['testbenches']};base=t['name'][:54];i=2
        while (base+'_'+str(i)).casefold() in names:i+=1
        t['name']=base+'_'+str(i);self._selected_testbench=t['id'];self.commit(lambda p:p['testbenches'].append(t),'Duplicate testbench')
    def delete_testbench(self):
        key=self.selected_testbench()['id'];self.commit(lambda p:p.update(testbenches=[t for t in p['testbenches'] if t['id']!=key]),'Delete saved testbench')
    def open_bench_cell(self,dut):
        if not self.flush_inspector():return
        self.cid=self.selected_testbench()['dut_cell' if dut else 'bench_cell'];self.selection=[];self.mode_combo.setCurrentIndex(1 if dut else 0);self.refresh(True)
    def export_testbench(self):
        from PySide6.QtWidgets import QFileDialog
        from .testbenches import spice_testbench
        from .model import atomic_write
        t=self.selected_testbench();path,_=QFileDialog.getSaveFileName(self,'Export saved SPICE testbench',t['name']+'.cir','SPICE (*.cir *.spice)')
        if path:atomic_write(path,spice_testbench(self.project,t));self.statusBar().showMessage('Exported saved testbench. Keep its locked PDK models available at the included paths.')
    def run_testbench(self):
        if not self.flush_inspector():return
        t=self.selected_testbench();exe=self.settings.value('engine/ngspice','') or shutil.which('ngspice')
        if not exe:raise ValueError('Configure ngspice in Engine diagnostics & paths.')
        self.start_job({'type':'testbench','testbench':t['id'],'executable':exe})
    def run_silicon(self):
        if not self.project.get('testbenches'):return super().run_silicon()
        if not self.flush_inspector():return
        t=self.selected_testbench();self.start_job({'type':'silicon','testbench':t['id'],'tools':{n:self.settings.value('engine/'+n,'') or shutil.which(n) or '' for n in ('magic','netgen','ngspice')}});self.open_silicon();self.silicon_status.setText('Verifying '+t['name']+' and its circuit hierarchy. The saved snapshot is retained with this run.')
    def refresh_silicon(self):
        super().refresh_silicon()
        r=getattr(self,'_silicon_result',None)
        if r and r.get('silicon_report',{}).get('testbench_id'):
            report=r['silicon_report'];self.silicon_status.setText(report['cell_name']+' · '+report['testbench_name']+' · '+self.silicon_status.text());parts=[]
            for m in report.get('comparison',[]):
                if m['unit']=='Hz':parts.append(m['name']+f': {m["before"]/1e9:.3f} → {m["after"]/1e9:.3f} GHz')
                elif m['unit']=='s':parts.append(m['name']+f': {m["before"]*1e12:.2f} → {m["after"]*1e12:.2f} ps')
            self.silicon_metrics.setText(' · '.join(parts))
            for row,s in enumerate(report['stages']):
                ev=s.get('evidence',{})
                if 'measurements' in ev:self.silicon_table.setItem(row,2,QTableWidgetItem(str(ev['samples'])+' samples · '+str(sum(m['status']=='passed' for m in ev['measurements']))+'/'+str(len(ev['measurements']))+' measurements passed'))
        elif not r and self.project.get('testbenches') and getattr(self,'_selected_testbench',None):
            t=self.selected_testbench();self.silicon_status.setText('Selected bench: '+t['name']+'. Stimulus, loads, analysis and limits come from its saved fixture. Generate/place the circuit layout, check connections, then verify.')
    def silicon_waveform(self,stage):
        r=getattr(self,'_silicon_result',None)
        if not r or not r.get('silicon_report',{}).get('testbench_id'):return super().silicon_waveform(stage)
        f=Path(r['evidence_directory'])/stage/'result.json'
        if not f.is_file():raise ValueError('This simulation stage did not complete. Review its report.')
        wave=json.loads(f.read_text());self.plot.set_result(wave,[n.lower() for n in r['silicon_report']['testbench']['probes']]);self.results_tabs.setCurrentIndex(0);self.cursor_label.setText(r['silicon_report']['testbench_name']+' · '+stage+(' · STALE: design changed' if r['design_hash']!=design_digest(self.project) else ''))
    def refresh_bench_result(self):
        r=getattr(self,'_bench_result',None)
        if not r or r.get('project_id')!=self.project['id'] or r.get('testbench_id')!=self._selected_testbench:
            self.bench_measurements.setRowCount(0);return
        if r.get('testbench_id') and r.get('measurements'):
            rows=r['measurements']['measurements'];self.bench_measurements.setRowCount(len(rows))
            for i,m in enumerate(rows):
                for col,val in enumerate((m['name'],f'{m["value"]:.6g}' if 'value' in m else '',m.get('unit',''),m['status']+' '+m.get('error',''))):self.bench_measurements.setItem(i,col,QTableWidgetItem(val))
            self.bench_note.setText(('STALE — design or bench changed. ' if r['design_hash']!=design_digest(self.project) else '')+'Saved testbench simulation · measurements '+r['measurements']['status']+'. Open Waveforms to inspect the saved probes.')
    def add_result(self,r):
        super().add_result(r)
        if r.get('testbench_id') and r.get('measurements'):self._bench_result=r;self.refresh_bench_result()
    def select_run(self,index):
        super().select_run(index)
        if self.result and self.result.get('testbench_id') and self.result.get('measurements'):self._bench_result=self.result;self.refresh_bench_result()
    def new_ring(self):
        if not self.maybe_save():return
        from .ring_oscillator import reference
        p,cid,key=reference(self.project['pdk']);self._selected_testbench=key;self.set_project(p);self.cid=cid;self.refresh(True);self.open_silicon()
    def inverter_layout_dialog(self):
        if len(self.cell['devices'])==3 and all(d['kind']=='X' for d in self.cell['devices']):
            cid=self.cid
            def build():
                from .ring_oscillator import generate
                p=clone(self.project);c=next(c for c in p['cells'] if c['id']==cid);generate(p,cid,bool(c.get('ring_layout')))
                return p,'Place three linked instances of the shared inverter layout and replace this cell’s routes and port labels. Manual edits in this ring cell are replaced. Child geometry is reused. Review connections and run the saved testbench after applying. Undo restores the complete previous layout.'
            self.review_dialog('Generate hierarchical ring layout',build);return
        super().inverter_layout_dialog()

    def render_physical_hierarchy(self):
        super().render_physical_hierarchy()
        if self.cell.get('layout_instances'):
            self.layout.set_data({**self.layout.cell,'layout_pins':terminals(self.project,self.cid)},self.project['pdk'],self.selection,self.net)
            self.layout.selection=list(dict.fromkeys(self.selection+[i['id'] for i in self.cell['layout_instances'] if i.get('device_id') in self.selection]));self.layout.update()
    def select(self,ids,mode=None):
        super().select(ids,mode)
        if (mode or self.current_mode)=='layout':
            linked=[i['device_id'] for i in self.cell.get('layout_instances',[]) if i['id'] in self.selection and i.get('device_id')];self.schematic.selection=list(dict.fromkeys(self.schematic.selection+linked));self.schematic.update()
    def build_inspector(self):
        inst=next((i for i in self.cell.get('layout_instances',[]) if i['id'] in self.selection),None) if self.current_mode=='layout' else None
        if not inst:return super().build_inspector()
        self.clear_form();self._inspector_dirty=False;child=next(c for c in self.project['cells'] if c['id']==inst['cell']);self.form.addWidget(QLabel(inst['name']+' → '+child['name']));self.form.addWidget(QLabel('Linked physical instance' if inst.get('device_id') else 'Physical instance — schematic link missing'));self.form.addWidget(QLabel(f'X {inst["x"]/1000:g} µm · Y {inst["y"]/1000:g} µm\nRotation {inst.get("rotation",0)}° · Mirror {inst.get("mirror",False)}'))
        for title,fn in [('Enter cell layout',self.enter_selected_cell),('Edit placement…',self.transform_layout_dialog),('Link to schematic…',self.link_placement_dialog)]:self.form.addWidget(self.button(title,fn=fn))
        self.form.addStretch();self._building_inspector=False
    def enter_layout_cell(self,item,col=0):
        if item.data(0,Qt.UserRole)!=self.cid:self._layout_navigation.append(self.cid)
        super().enter_layout_cell(item,col)
    def enter_selected_cell(self):
        i=next((i for i in self.cell.get('layout_instances',[]) if i['id'] in self.selection or i.get('device_id') in self.selection),None)
        if not i:raise ValueError('Select a placed physical cell or its schematic instance.')
        if not self.flush_inspector():return
        self._layout_navigation.append(self.cid);self.cid=i['cell'];self.selection=[];self.mode_combo.setCurrentIndex(1);self.refresh(True)
    def leave_layout_cell(self):
        if not self.flush_inspector():return
        valid={c['id'] for c in self.project['cells']};parents=[c['id'] for c in self.project['cells'] if any(i['cell']==self.cid for i in c.get('layout_instances',[]))]
        while self._layout_navigation:
            cid=self._layout_navigation.pop()
            if cid in valid:break
        else:
            if not parents:raise ValueError('The active cell has no physical parent.')
            cid=parents[0]
        self.cid=cid;self.selection=[];self.mode_combo.setCurrentIndex(1);self.refresh(True)
    def place_linked_dialog(self):
        ds=[d for d in self.cell['devices'] if d['kind']=='X'];cid=self.cid
        if not ds:raise ValueError('Place an electrical cell instance in the schematic first.')
        selected=next((d for d in ds if d['id'] in self.selection),ds[0]);choices=[selected['name']]+[d['name'] for d in ds if d['id']!=selected['id']]
        def apply(v):self.commit(lambda p:place(p,cid,next(d['id'] for d in ds if d['name']==v['instance']),round(scalar(v['x'])*1000),round(scalar(v['y'])*1000),int(v['rotation']),v['mirror']=='Yes'),'Place linked cell');self.mode_combo.setCurrentIndex(1);self.refresh(True)
        self.workflow_form('Place linked physical cell',[('instance','Schematic instance',choices),('x','X (µm)','0'),('y','Y (µm)','0'),('rotation','Rotation',['0','90','180','270']),('mirror','Mirror',['No','Yes'])],apply,'Child port coordinates follow its physical view. Existing routes remain fixed when a cell is moved or regenerated.')
    def link_placement_dialog(self):
        i=next(i for i in self.cell['layout_instances'] if i['id'] in self.selection);cid=self.cid;ds=[d for d in self.cell['devices'] if d['kind']=='X' and d['cell']==i['cell']]
        if not ds:raise ValueError('No schematic instance references this physical cell.')
        self.workflow_form('Link physical instance',[('instance','Schematic instance',[d['name'] for d in ds])],lambda v:self.commit(lambda p:next(j for c in p['cells'] if c['id']==cid for j in c['layout_instances'] if j['id']==i['id']).update(device_id=next(d['id'] for d in ds if d['name']==v['instance'])),'Link physical instance'))
    def cell_port_dialog(self):
        from .physical_cells import assign_port
        cid=self.cid
        if not self.cell['ports']:raise ValueError('Declare the cell electrical ports first.')
        self.workflow_form('Assign cell layout port',[('name','Cell port',self.cell['ports']),('layer','Conductor',[l['name'] for l in self.project['pdk']['layers'] if l['datatype']==20]),('x','X (µm)','0'),('y','Y (µm)','0')],lambda v:self.commit(lambda p:assign_port(p,cid,v['name'],v['layer'],[round(scalar(v['x'])*1000),round(scalar(v['y'])*1000)]),'Assign physical cell port'),'The named terminal is shared by every placed instance. A matching PDK label is written for external extraction.')
    def move(self,ids,x,y,mode):
        if mode=='schematic':
            from .schematic_ui import SchematicMixin
            return SchematicMixin.move(self,ids,x,y,mode)
        if any(s['id'] in ids and s['layer'] in self.layout.locked_layers for s in self.cell['shapes']):raise ValueError('Unlock selected shapes before moving them.')
        self.guard(lambda:self.commit(lambda p:transform_selection(p,self.cid,ids,round(x),round(y)),'Move layout selection'))
    def rotate(self,angle=90):
        if self.current_mode!='layout':return super().rotate(angle)
        if any(s['id'] in self.selection and s['layer'] in self.layout.locked_layers for s in self.cell['shapes']):raise ValueError('Unlock selected shapes before rotating them.')
        self.commit(lambda p:transform_selection(p,self.cid,self.selection,rotation=angle%360),'Rotate layout selection')
    def duplicate(self):
        chosen=[i for i in self.cell.get('layout_instances',[]) if i['id'] in self.selection] if self.current_mode=='layout' else []
        if not chosen:return super().duplicate()
        cid=self.cid;newids=[]
        def edit(p):
            c=next(c for c in p['cells'] if c['id']==cid);names={d['name'].casefold() for d in c['devices']}|{i['name'].casefold() for i in c['layout_instances']}
            for source in chosen:
                i=clone(source);i['id']=uid();i['x']+=5000;i['y']+=5000;base=i['name'][:54];n=2
                while (base+'_'+str(n)).casefold() in names:n+=1
                i['name']=base+'_'+str(n);names.add(i['name'].casefold());d=next((d for d in c['devices'] if d['id']==source.get('device_id')),None)
                if d:
                    d=clone(d);d.update(id=uid(),name=i['name'],x=d['x']+40,y=d['y']+40,net_labels=clone(d['nets']));c['devices'].append(d);i['device_id']=d['id']
                c['layout_instances'].append(i);newids.append(i['id'])
        self.commit(edit,'Duplicate linked schematic and physical instance');self.select(newids,'layout')
    def transform_layout_dialog(self):
        if not self.selection:raise ValueError('Select layout shapes or physical instances first.')
        ids=list(self.selection);cid=self.cid
        def apply(v):
            if any(s['id'] in ids and s['layer'] in self.layout.locked_layers for s in self.cell['shapes']):raise ValueError('Unlock selected shapes before transforming them.')
            self.commit(lambda p:transform_selection(p,cid,ids,round(scalar(v['dx'])*1000),round(scalar(v['dy'])*1000),int(v['rotation']),v['mirror']=='Yes',(round(scalar(v['px'])*1000),round(scalar(v['py'])*1000)),v['annotations']=='Yes'),'Transform layout selection')
        return self.workflow_form('Transform layout selection',[('dx','Move X (µm)','0'),('dy','Move Y (µm)','0'),('rotation','Rotate',['0','90','180','270']),('mirror','Mirror across X',['No','Yes']),('px','Pivot X (µm)','0'),('py','Pivot Y (µm)','0'),('annotations','Move cell ports and labels',['No','Yes'])],apply,'To move named ports, labels and assigned terminals together, select every cell shape and placement and choose Yes. Parent routes stay fixed; check connections after moving a child cell.')
    def check_linked_layout(self):
        super().check_linked_layout();self.issues=[*audit(self.project,self.cid),*[i for i in self.issues if i['code']!='PDK.STALE']];self.fill_checks()
    def check_selected(self,row,col):
        if row<len(self.issues) and self.check_revision==self.project['revision']:
            cid=self.issues[row].get('cell_id')
            if cid and cid!=self.cid:self.cid=cid;self.selection=[];self.refresh(True)
        super().check_selected(row,col)
    def layout_settings_dialog(self):
        def apply(v):
            width=round(scalar(v['width'])*1000)
            if width<=0 or width%self.project['pdk']['grid']:raise ValueError('Path width must be positive and on the layout grid.')
            self.layout.line_width=width;self.layout.orthogonal=v['mode']=='Manhattan';self.layout.snap_to_terminals=v['snap']=='Yes';self.statusBar().showMessage('Layout drawing settings updated.')
        self.workflow_form('Layout drawing settings',[('width','Path width (µm)',str(self.layout.line_width/1000)),('mode','Path bends',['Manhattan','Free angle'] if self.layout.orthogonal else ['Free angle','Manhattan']),('snap','Snap to terminals / vertices',['Yes','No'] if self.layout.snap_to_terminals else ['No','Yes'])],apply,'Grid snapping is always active. Terminal and vertex snapping is applied while drawing paths; Manhattan mode inserts orthogonal bends.')
    def route_terminals_dialog(self):
        from .physical import route
        pins=terminals(self.project,self.cid);ds={d['id']:d for d in self.cell['devices']};choices={ds[i['device_id']]['name']+'.'+i['pin']:i for i in pins};cid=self.cid
        if len(choices)<2:raise ValueError('Place devices or cells with assigned terminals first.')
        def apply(v):
            a,b=choices[v['a']],choices[v['b']];net=ds[a['device_id']]['nets'][a['pin']]
            if a['layer']!=b['layer'] or net!=ds[b['device_id']]['nets'][b['pin']]:raise ValueError('Choose different terminals on the same schematic net and conductor layer. Add vias explicitly for a layer change.')
            if a['point']==b['point']:raise ValueError('The two terminals already occupy the same point.')
            self.commit(lambda p:next(c for c in p['cells'] if c['id']==cid)['shapes'].append(route(p,cid,a['layer'],a['point'],b['point'],round(scalar(v['width'])*1000),net)),'Route linked terminals')
        self.workflow_form('Route linked terminals',[('a','From terminal',list(choices)),('b','To terminal',list(choices)[1:]+list(choices)[:1]),('width','Width (µm)','.34')],apply,'Searches for an orthogonal route with up to two bends. Inspect the result and run DRC/LVS.')
    def path_vertices_dialog(self):
        shape=next((s for s in self.cell['shapes'] if s['id'] in self.selection and s['kind']=='path'),None)
        if not shape:raise ValueError('Select one path in the active cell.')
        cid=self.cid;sid=shape['id'];dlg=QDialog(self);dlg.setWindowTitle('Edit path vertices');dlg.resize(460,440);v=QVBoxLayout(dlg);table=QTableWidget(len(shape['points']),2);table.setHorizontalHeaderLabels(['X (µm)','Y (µm)']);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for i,pt in enumerate(shape['points']):
            for j,n in enumerate(pt):table.setItem(i,j,QTableWidgetItem(str(n/1000)))
        v.addWidget(table);row=QHBoxLayout();add=QPushButton('Add point');remove=QPushButton('Remove point');row.addWidget(add);row.addWidget(remove);v.addLayout(row)
        def append():
            i=table.rowCount();table.insertRow(i)
            for col in range(2):table.setItem(i,col,QTableWidgetItem('0'))
        add.clicked.connect(append);remove.clicked.connect(lambda:table.removeRow(table.currentRow()) if table.currentRow()>=0 else None);error=QLabel();error.setWordWrap(True);v.addWidget(error);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);v.addWidget(buttons)
        def save():
            try:
                pts=[[round(scalar(table.item(i,j).text())*1000) for j in range(2)] for i in range(table.rowCount())]
                if len(pts)<2 or any(a==b for a,b in zip(pts,pts[1:])) or any(n%self.project['pdk']['grid'] for pt in pts for n in pt):raise ValueError('Use at least two distinct points on the project grid.')
                if self.layout.orthogonal and any(a[0]!=b[0] and a[1]!=b[1] for a,b in zip(pts,pts[1:])):raise ValueError('Manhattan routing requires horizontal or vertical segments.')
                self.commit(lambda p:next(s for c in p['cells'] if c['id']==cid for s in c['shapes'] if s['id']==sid).update(points=pts),'Edit path vertices');dlg.accept()
            except Exception as e:error.setText(str(e))
        buttons.accepted.connect(save);buttons.rejected.connect(dlg.reject);self._vertices_dialog=dlg;dlg.table=table;dlg.buttons=buttons;dlg.error=error;dlg.setWindowModality(Qt.WindowModal);dlg.show()
