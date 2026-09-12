"""Native desktop controls for studies, physical cells, and project packages."""
from __future__ import annotations
import json,csv,io
from pathlib import Path
from PySide6.QtCore import Qt,QPointF
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QPlainTextEdit,QComboBox,QLabel,QDialogButtonBox,QFileDialog,QTableWidget,QTableWidgetItem,QPushButton,QHeaderView,QAbstractItemView,QListWidget,QMessageBox)
from .model import clone,digest,scalar,uid,atomic_write,validate,design_digest

class FeatureMixin:
    def make_ui(self):
        super().make_ui();self.study_table=QTableWidget();self.study_table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.study_table.setSelectionBehavior(QAbstractItemView.SelectRows);self.study_table.verticalHeader().hide();self.study_table.setShowGrid(False);self.study_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);self.study_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter)
        page=QWidget();v=QVBoxLayout(page);self.study_summary=QLabel('Run a study to compare measured results.');self.study_summary.setWordWrap(True);v.addWidget(self.study_summary);v.addWidget(self.study_table)
        buttons=QHBoxLayout();open_case=QPushButton('Open selected waveform');open_case.clicked.connect(lambda:self.guard(self.open_study_case));export=QPushButton('Export study CSV…');export.clicked.connect(lambda:self.guard(self.export_study));buttons.addWidget(open_case);buttons.addWidget(export);buttons.addStretch();v.addLayout(buttons);self.study_tab=self.results_tabs.addTab(page,'Studies')
    def make_actions(self):
        super().make_actions();menus={m.title().replace('&',''):m for m in self._menus}
        items={'File':[('Import edited Xschem package…',self.import_xschem_dialog),('Save project folder…',self.save_project_folder),('Open project folder…',self.open_project_folder),('Export structural Verilog…',self.export_verilog),('Review imported layout changes…',self.review_import)],
        'Design':[('Edit active cell symbol…',self.symbol_dialog),('Manage annotations…',self.annotations_dialog),('Cell parameters…',self.edit_parameters),('Instance parameters…',self.edit_instance_parameters),('Add annotation…',self.add_annotation),('Connect selection to bus…',self.bus_dialog),('Create reusable layout cell…',self.pcell_dialog),('Regenerate active layout cell…',self.regenerate_dialog),('Place physical cell / array…',self.physical_instance_dialog),('Route between coordinates…',self.route_dialog),('Erase layout area…',self.erase_dialog),('Assign physical terminal…',self.physical_pin_dialog),('Common-centroid placement…',self.centroid_dialog)],
        'Analysis':[('Simulate extracted SPICE testbench…',self.deck_dialog),('ngspice device noise…',self.noise_dialog),('Parameter sweep / PVT / Monte Carlo…',self.study_dialog),('Physical terminal connectivity',lambda:self.start_job({'type':'connectivity'})),('Estimate ground capacitance',lambda:self.start_job({'type':'parasitics'})),('Simulate with estimated parasitics',self.post_layout_dialog)],
        'Tools':[('Create PDK reference circuit…',self.sky130_reference_dialog),('Installed PDK revisions…',self.pdk_manager),('Extract layout through Magic…',self.magic_extract_dialog)]}
        self._feature_menus=[]
        schematic=menus['Design'].addMenu('Schematic tools');physical=menus['Design'].addMenu('Physical cells');routing=menus['Design'].addMenu('Routing and terminals');post=menus['Analysis'].addMenu('Physical verification and extraction');folders=menus['File'].addMenu('Project folders')
        self._feature_menus.extend((schematic,physical,routing,post,folders))
        for group,entries in items.items():
            for title,fn in entries:
                target=menus[group]
                if group=='Design':target=routing if any(word in title for word in ('Route','Erase','terminal')) else physical if any(word in title for word in ('layout cell','physical cell','centroid')) else schematic
                elif group=='Analysis' and any(word in title for word in ('connectivity','capacitance','parasitics')):target=post
                elif group=='File' and 'project folder' in title:target=folders
                self.action(target,title,fn)
        for action in list(menus['Design'].actions()):
            if any(word in action.text() for word in ('Generate generic','Generate metal','Create layout array')):menus['Design'].removeAction(action);physical.addAction(action)
        self.action(menus['Analysis'],'Rerun saved study',self.rerun_study)

    def sky130_reference_dialog(self):
        vals=self.simple_form('SKY130 inverter reference flow',{'SKY130A directory':self.settings.value('sky130/root',''),'Output directory':''},'Runs the installed PDK standard-cell inverter through schematic simulation, GDS import, DRC, LVS, capacitance extraction and post-layout simulation. Use an empty output directory. Requires ngspice, Magic and Netgen. This verifies one reference cell, not arbitrary layouts or tapeout signoff.')
        if not vals:return
        args=['sky130-reference','--pdk-root',vals['SKY130A directory'],'--output',vals['Output directory']]
        import shutil
        for name in ('ngspice','magic','netgen'):
            executable=self.settings.value('engine/'+name,'') or shutil.which(name)
            if not executable:raise ValueError('Configure '+name+' in Tools → Engine diagnostics and paths.')
            args+=['--'+name,executable]
        self.settings.setValue('sky130/root',vals['SKY130A directory']);self.start_cli_job(args,'SKY130 inverter reference')
        self.console.appendPlainText('Evidence will be written to '+str(Path(vals['Output directory'])/'report.json')+'; open inverter.icproj to inspect the generated native schematic and layout.')

    def workflow_form(self,title,fields,submit,note=''):
        dlg=QDialog(self);dlg.setWindowTitle(title);dlg.resize(520,300);v=QVBoxLayout(dlg);form=QFormLayout();form.setVerticalSpacing(12);dlg.fields={}
        if note:
            label=QLabel(note);label.setWordWrap(True);label.setProperty('role','muted');v.addWidget(label)
        for key,label,default in fields:
            if isinstance(default,list):w=QComboBox();w.addItems(default)
            elif isinstance(default,tuple):w=QPlainTextEdit(default[0]);w.setMaximumHeight(140)
            else:w=QLineEdit(str(default))
            if key=='layer' and isinstance(w,QComboBox):w.setCurrentText('metal1')
            w.setAccessibleName(label);form.addRow(label,w);dlg.fields[key]=w
        v.addLayout(form);dlg.error=QLabel();dlg.error.setWordWrap(True);dlg.error.setProperty('role','error');v.addWidget(dlg.error);buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);v.addWidget(buttons)
        def accept():
            try:
                if not self.flush_inspector():raise ValueError('Resolve the property edit before continuing.')
                values={k:(w.currentText() if isinstance(w,QComboBox) else w.toPlainText() if isinstance(w,QPlainTextEdit) else w.text()) for k,w in dlg.fields.items()};submit(values);dlg.accept()
            except Exception as e:dlg.error.setText(str(e))
        buttons.accepted.connect(accept);buttons.rejected.connect(dlg.reject);dlg.setAttribute(Qt.WA_DeleteOnClose);self._workflow_dialog=dlg;dlg.show();return dlg
    def refresh(self,fit=False):
        super().refresh(fit);self.render_physical_hierarchy()
    def select(self,*args,**kwargs):
        super().select(*args,**kwargs);self.render_physical_hierarchy()
    def render_physical_hierarchy(self):
        if any(d['kind']=='X' for d in self.cell['devices']):
            by={c['id']:c for c in self.project['cells']};devices=[{**d,'symbol':by[d['cell']]['symbol'],'symbol_context':{'symname':by[d['cell']]['name'],**by[d['cell']].get('parameters',{}),**d.get('parameters',{})}} if d['kind']=='X' and by[d['cell']].get('symbol') else d for d in self.cell['devices']];self.schematic.set_data({**self.cell,'devices':devices},self.project['pdk'],self.selection,self.net)
        if self.cell.get('layout_instances'):
            from .layout_scene import LayoutScene
            if not hasattr(self,'_layout_scene'):self._layout_scene=LayoutScene()
            scene=self._layout_scene.update(self.project,self.cid,getattr(self.layout,'hierarchy_depth',None))
            self.layout.set_data({**self.cell,'_layout_scene':scene},self.project['pdk'],self.selection,self.net,revision=self.project['revision'])
    def move(self,ids,x,y,mode):
        instances=[i for i in self.cell.get('layout_instances',[]) if i['id'] in ids] if mode=='layout' else []
        if instances:
            def edit(p):
                c=next(c for c in p['cells'] if c['id']==self.cid)
                for i in c.get('layout_instances',[]):
                    if i['id'] in ids:i['x']+=int(x);i['y']+=int(y)
                for s in c['shapes']:
                    if s['id'] in ids:s['points']=[[a+int(x),b+int(y)] for a,b in s['points']];s['holes']=[[[a+int(x),b+int(y)] for a,b in h] for h in s.get('holes',[])]
            self.commit(edit,'Move physical instances');return
        super().move(ids,x,y,mode)
    def delete(self):
        if self.current_mode=='schematic' and self.selection:
            ids=set(self.selection)
            def edit(p):
                c=next(c for c in p['cells'] if c['id']==self.cid);c['devices']=[d for d in c['devices'] if d['id'] not in ids];c['layout_pins']=[pin for pin in c.get('layout_pins',[]) if pin['device_id'] not in ids]
                for s in c['shapes']:
                    if s.get('device_id') in ids:s['device_id']=''
            self.commit(edit,'Delete component and terminal assignments');self.select([]);return
        if self.current_mode=='layout' and any(i['id'] in self.selection for i in self.cell.get('layout_instances',[])):
            ids=set(self.selection)
            def edit(p):
                c=next(c for c in p['cells'] if c['id']==self.cid);c['layout_instances']=[i for i in c.get('layout_instances',[]) if i['id'] not in ids];c['shapes']=[s for s in c['shapes'] if s['id'] not in ids]
            self.commit(edit,'Delete physical selection');self.select([]);return
        super().delete()
    def rotate(self):
        if self.current_mode=='layout' and any(i['id'] in self.selection for i in self.cell.get('layout_instances',[])):
            def edit(p):
                c=next(c for c in p['cells'] if c['id']==self.cid)
                for i in c['layout_instances']:
                    if i['id'] in self.selection:i['rotation']=(i.get('rotation',0)+90)%360
            self.commit(edit,'Rotate physical instance');return
        super().rotate()
    def check(self,typ):
        if typ=='drc':
            if self.flush_inspector():self.start_job({'type':'drc'})
            return
        super().check(typ)
    def add_result(self,r):
        super().add_result(r)
        if 'physical_result' in r:self.show_physical_result(r)
        if 'study_rows' in r:self.show_study(r)
    def select_run(self,index):
        super().select_run(index)
        if self.result and 'study_rows' in self.result:self.show_study(self.result)
        if self.result and 'physical_result' in self.result:self.show_physical_result(self.result)
    def job_finished(self,code,status):
        super().job_finished(code,status)
        if self.result and self._job_state=='complete':
            if 'physical_result' in self.result:self.results_tabs.setCurrentIndex(1)
            elif 'study_rows' in self.result:self.results_tabs.setCurrentIndex(self.study_tab)
    def show_physical_result(self,r):
        data=r['physical_result'];self.issues=data.get('issues',[]);self.check_revision=r['revision'];self.fill_checks();self.check_note.setText(f'{r["settings"]["type"]} · r{r["revision"]} · {len(self.issues)} findings. '+data.get('qualification','Generic geometry rules.'))
        if 'capacitors' in data:
            self.console.appendPlainText('\n'.join(f'{x["net"]} / {x["layer"]}: {x["capacitance"]:.6g} F' for x in data['capacitors']));self.check_note.setText('Estimated '+str(len(data['capacitors']))+' lumped capacitances. See Job log for values. '+data['qualification'])
    def show_study(self,r):
        self._study_result=r;rows=r['study_rows'];columns=['index']+[k for k in ('value','corner','voltage','temperature','trial') if k in rows[0]]+['measurement'];self.study_table.setColumnCount(len(columns));self.study_table.setHorizontalHeaderLabels([k.replace('_',' ').title() for k in columns]);self.study_table.setRowCount(len(rows));self.study_table.horizontalHeader().setStretchLastSection(True);self.study_table.setHorizontalHeaderItem(len(columns)-1,QTableWidgetItem(r['settings']['study']['measurement']['trace']+' · '+r['settings']['study']['measurement']['metric']))
        for i,row in enumerate(rows):
            for j,key in enumerate(columns):self.study_table.setItem(i,j,QTableWidgetItem(f'{row[key]:.7g}' if isinstance(row[key],float) else str(row[key])))
        summary=r['summary'];self.study_summary.setText(f'{len(rows)} runs · mean {summary["mean"]:.6g} · min {summary["min"]:.6g} · max {summary["max"]:.6g} · standard deviation {summary["stddev"]:.6g}'+(f' · yield {summary["yield"]:.1%}' if 'yield' in summary else ''));self.study_table.selectRow(0)
    def open_study_case(self):
        i=self.study_table.currentRow()
        if i<0 or not getattr(self,'_study_result',None):raise ValueError('Select a study run.')
        path=Path(self._study_result['study_rows'][i]['result_file']);r=json.loads(path.read_text());self.add_result(r);self.results_tabs.setCurrentIndex(0)
    def export_study(self):
        if not getattr(self,'_study_result',None):raise ValueError('Run a study first.')
        path,_=QFileDialog.getSaveFileName(self,'Export study results','study.csv','CSV (*.csv)')
        if path:
            rows=self._study_result['study_rows'];keys=list(rows[0]);stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader();writer.writerows(rows);atomic_write(path,stream.getvalue())
    def study_dialog(self):
        from .studies import METRICS
        def submit(v):
            kind={'Parameter sweep':'sweep','PVT corners':'pvt','Tolerance Monte Carlo':'monte_carlo'}[v['kind']];spec={'kind':kind,'target':v['target'],'measurement':{'trace':v['trace'],'metric':v['metric']}}
            if kind=='sweep':spec['values']=[x.strip() for x in v['values'].split(',') if x.strip()]
            elif kind=='pvt':spec.update(corners=[x.strip() for x in v['corners'].split(',')],voltages=[scalar(x) for x in v['volts'].split(',')],temperatures=[scalar(x) for x in v['temps'].split(',')])
            else:spec.update(count=int(v['count']),seed=int(v['seed']),variations=[{'target':v['target'],'relative_sigma':float(v['sigma'])/100,'distribution':'normal'}])
            from .studies import cases
            cases(self.project,self.cid,spec);self.commit(lambda p:p.update(last_study=clone(spec)),'Study settings');self.start_job({'type':'study','analysis':clone(self.project['analysis']),'study':spec},'ngspice' if v['engine']=='ngspice' else 'builtin')
        dlg=self.workflow_form('Simulation study',[('kind','Study',['Parameter sweep','PVT corners','Tolerance Monte Carlo']),('target','Numeric target','R1.value'),('values','Sweep values','5k, 10k, 20k'),('corners','PDK corners','nominal'),('volts','Supply voltages','1.6, 1.8, 2.0'),('temps','Temperatures (°C)','0, 27, 85'),('sigma','Standard deviation (%)','5'),('count','Trials','50'),('seed','Random seed','1'),('trace','Measure net','vout'),('metric','Measurement',list(METRICS)),('engine','Engine',['Built-in','ngspice'])],submit,'Uses the current Analysis setup. PVT targets a DC supply, such as VDD.value. Monte Carlo uses an explicit component tolerance.')
        form=next(x for x in dlg.findChildren(QFormLayout))
        def visible(kind):
            for key in ('values','corners','volts','temps','sigma','count','seed'):
                show=key in ({'values'} if kind=='Parameter sweep' else {'corners','volts','temps'} if kind=='PVT corners' else {'sigma','count','seed'});form.setRowVisible(dlg.fields[key],show)
        dlg.fields['kind'].currentTextChanged.connect(visible);visible('Parameter sweep');return dlg
    def save_project_folder(self):
        from .project_store import save_directory
        path=QFileDialog.getExistingDirectory(self,'Save project folder')
        if path:save_directory(self.project,path);self.statusBar().showMessage('Project folder snapshot saved.',8000)
    def open_project_folder(self):
        from .project_store import load_directory
        path,_=QFileDialog.getOpenFileName(self,'Open project folder manifest','','Project manifest (*.icstudio)')
        if path and self.maybe_save():self.set_project(load_directory(path),path)
    def export_verilog(self):
        from .design_ops import verilog
        path,_=QFileDialog.getSaveFileName(self,'Export structural connectivity','design.v','Verilog (*.v)')
        if path:atomic_write(path,verilog(self.project))
    def edit_parameters(self):
        def submit(v):
            definitions=dict(line.split('=',1) for line in v['parameters'].splitlines() if line.strip());definitions={k.strip():x.strip() for k,x in definitions.items()}
            self.commit(lambda p:next(c for c in p['cells'] if c['id']==self.cid).update(parameters=definitions),'Cell parameters')
        self.workflow_form('Cell parameters',[('parameters','Name = value',('\n'.join(k+' = '+str(v) for k,v in self.cell.get('parameters',{}).items()),))],submit,'Example: resistance = 10k. Device values can use {resistance * 2}.')
    def edit_instance_parameters(self):
        d=next((d for d in self.cell['devices'] if d['id'] in self.selection and d['kind']=='X'),None)
        if not d:raise ValueError('Select a schematic cell instance.')
        def submit(v):
            parameters={k.strip():x.strip() for k,x in (line.split('=',1) for line in v['parameters'].splitlines() if line.strip())}
            self.commit(lambda p:next(x for c in p['cells'] for x in c['devices'] if x['id']==d['id']).update(parameters=parameters),'Instance parameters')
        self.workflow_form('Instance parameters',[('parameters','Overrides',('\n'.join(k+' = '+str(x) for k,x in d.get('parameters',{}).items()),))],submit,'Override the referenced cell defaults for this instance.')
    def add_annotation(self):
        def submit(v):
            note={'id':uid(),'x':scalar(v['x']),'y':scalar(v['y']),'text':v['text']}
            self.commit(lambda p:next(c for c in p['cells'] if c['id']==self.cid).setdefault('annotations',[]).append(note),'Add annotation')
            self.mode_combo.setCurrentIndex(0);self.cancel_tool();self.select([note['id']],'schematic');self.reveal_properties()
        self.workflow_form('Schematic annotation',[('text','Text',('',)),('x','X (schematic units)','200'),('y','Y (schematic units)','80')],submit)
    def bus_dialog(self):
        from .design_ops import connect_bus
        ids=list(self.selection)
        self.workflow_form('Connect selected components to bus',[('bus','Bus','data[3:0]'),('pin','Component pin','p')],lambda v:self.commit(lambda p:connect_bus(next(c for c in p['cells'] if c['id']==self.cid),ids,v['pin'],v['bus']),'Connect bus'),'Selection order follows bus order. One selected component is required per signal.')
    @staticmethod
    def nm(v):return round(scalar(v)*1000)
    def pcell_dialog(self):
        from .physical import recipe_cell
        selected=next((d for d in self.cell['devices'] if d['id'] in self.selection),None)
        def submit(v):
            spec={'kind':v['kind'],'width':self.nm(v['width']),'height':self.nm(v['height']),'thickness':self.nm(v['thickness']),'gap':self.nm(v['gap']),'count':int(v['count']),'fingers':int(v['count']),'layer':v['layer'],'net':v['net']}
            cell=recipe_cell(v['name'],spec,selected);self.commit(lambda p:p['cells'].append(cell),'Create reusable layout cell');self.cid=cell['id'];self.mode_combo.setCurrentIndex(1);self.refresh(True)
        dlg=self.workflow_form('Reusable layout generator',[('name','Cell name','guard_ring'),('kind','Generator',['guard_ring','interdigitated','mos']),('width','Width (µm)','12'),('height','Height (µm)','10'),('thickness','Ring thickness (µm)','0.4'),('gap','Finger gap (µm)','0.4'),('count','Fingers','4'),('layer','Layer',[l['name'] for l in self.project['pdk']['layers']]),('net','Ring net','0')],submit,'Geometry recipes remain editable. These generic generators have no foundry qualification. Select a MOS first to generate MOS geometry.')
        form=next(x for x in dlg.findChildren(QFormLayout))
        def relevant(kind):
            for key in ('width','height','thickness','gap','count','layer','net'):
                visible=key in ({'width','height','thickness','layer','net'} if kind=='guard_ring' else {'width','height','gap','count','layer'} if kind=='interdigitated' else {'count'})
                form.setRowVisible(dlg.fields[key],visible)
        dlg.fields['kind'].currentTextChanged.connect(relevant);relevant('guard_ring')
    def regenerate_dialog(self):
        from .physical import regenerate
        recipe=self.cell.get('generator')
        if not recipe:raise ValueError('Open a generated layout cell first.')
        fields=[(k,k.replace('_',' ').title(),str(v)) for k,v in recipe['spec'].items() if k!='kind']
        def submit(v):
            old=recipe['spec'];spec={**old,**{k:(int(x) if isinstance(old[k],int) else x) for k,x in v.items()}}
            self.commit(lambda p:regenerate(next(c for c in p['cells'] if c['id']==self.cid),spec),'Regenerate layout cell')
        self.workflow_form('Regenerate layout cell',fields,submit,'Recipe dimensions are integer database units (nm). Every physical instance updates with the cell.')
    def physical_instance_dialog(self):
        candidates=[c for c in self.project['cells'] if c['id']!=self.cid]
        if not candidates:raise ValueError('Create another layout cell first.')
        def submit(v):
            inst={'id':uid(),'name':v['name'],'cell':next(c['id'] for c in candidates if c['name']==v['cell']),'x':self.nm(v['x']),'y':self.nm(v['y']),'rotation':int(v['rotation']),'nx':int(v['nx']),'ny':int(v['ny']),'dx':self.nm(v['dx']),'dy':self.nm(v['dy'])}
            self.commit(lambda p:next(c for c in p['cells'] if c['id']==self.cid).setdefault('layout_instances',[]).append(inst),'Place physical cell');self.mode_combo.setCurrentIndex(1);self.refresh(True)
        self.workflow_form('Place physical cell',[('cell','Cell',[c['name'] for c in candidates]),('name','Instance name','I1'),('x','X (µm)','0'),('y','Y (µm)','0'),('rotation','Rotation',['0','90','180','270']),('nx','Columns','1'),('ny','Rows','1'),('dx','Column pitch (µm)','15'),('dy','Row pitch (µm)','15')],submit)
    def route_dialog(self):
        from .physical import route
        def submit(v):
            shape=route(self.project,self.cid,v['layer'],[self.nm(v['x1']),self.nm(v['y1'])],[self.nm(v['x2']),self.nm(v['y2'])],self.nm(v['width']),v['net']);self.add_shape(shape);self.mode_combo.setCurrentIndex(1)
        self.workflow_form('Assisted Manhattan route',[('layer','Layer',[l['name'] for l in self.project['pdk']['layers']]),('net','Net','vout'),('width','Width (µm)','0.4'),('x1','Start X (µm)','0'),('y1','Start Y (µm)','0'),('x2','End X (µm)','10'),('y2','End Y (µm)','10')],submit,'Checks width and clearance on the chosen layer. Obstacles on other nets are avoided.')
    def erase_dialog(self):
        from .physical import erase
        def submit(v):
            box=[self.nm(v[k]) for k in ('x1','y1','x2','y2')]
            if box[0]>=box[2] or box[1]>=box[3]:raise ValueError('The upper-right corner must exceed the lower-left corner.')
            self.commit(lambda p:erase(next(c for c in p['cells'] if c['id']==self.cid),v['layer'],box),'Erase physical geometry')
        self.workflow_form('Erase layout area',[('layer','Layer',[l['name'] for l in self.project['pdk']['layers']]),('x1','Left (µm)','0'),('y1','Bottom (µm)','0'),('x2','Right (µm)','1'),('y2','Top (µm)','1')],submit,'Cuts geometry on the active cell and selected layer. Undo restores the edit.')
    def physical_pin_dialog(self):
        devices=[d for d in self.cell['devices'] if d['kind'] not in ('V','I')]
        if not devices:raise ValueError('Add schematic devices before assigning physical terminals.')
        def submit(v):
            d=next(d for d in devices if d['name']==v['device']);pin={'id':uid(),'device_id':d['id'],'pin':v['pin'],'layer':v['layer'],'point':[self.nm(v['x']),self.nm(v['y'])]}
            def edit(p):
                c=next(c for c in p['cells'] if c['id']==self.cid);c['layout_pins']=[x for x in c.get('layout_pins',[]) if (x['device_id'],x['pin'])!=(d['id'],v['pin'])]+[pin]
            self.commit(edit,'Assign physical terminal')
        self.workflow_form('Assign physical terminal',[('device','Device',[d['name'] for d in devices]),('pin','Pin','p'),('layer','Conductor layer',[l['name'] for l in self.project['pdk']['layers']]),('x','X (µm)','0'),('y','Y (µm)','0')],submit,'Place the terminal inside its conductor. Connectivity checks use polygon contact, independent of net labels.')
    def centroid_dialog(self):
        candidates=[c for c in self.project['cells'] if c['id']!=self.cid]
        if len(candidates)<2:raise ValueError('Create two reusable layout unit cells first.')
        def submit(v):
            pitch=self.nm(v['pitch']);a=next(c for c in candidates if c['name']==v['a']);b=next(c for c in candidates if c['name']==v['b'])
            if pitch<=0:raise ValueError('Pitch must be positive.')
            group=uid();items=[{'id':uid(),'name':'CC_'+group[:6]+'_'+str(i),'cell':c['id'],'x':x*pitch,'y':y*pitch,'rotation':0,'matching_group':group} for i,(c,x,y) in enumerate([(a,0,0),(b,1,0),(b,0,1),(a,1,1)])]
            def edit(p):
                c=next(c for c in p['cells'] if c['id']==self.cid);c.setdefault('layout_instances',[]).extend(items);c.setdefault('constraints',[]).append({'id':group,'kind':'common_centroid','groups':[[items[0]['id'],items[3]['id']],[items[1]['id'],items[2]['id']]]})
            self.commit(edit,'Common-centroid placement');self.mode_combo.setCurrentIndex(1);self.refresh(True)
        self.workflow_form('Common-centroid unit placement',[('a','Unit A',[c['name'] for c in candidates]),('b','Unit B',[c['name'] for c in candidates]),('pitch','Unit pitch (µm)','5')],submit,'Creates an A/B/B/A arrangement with coincident instance-origin centroids. Electrical sizing and routing remain explicit.')
    def post_layout_dialog(self):
        self.start_job({'type':'post_layout','analysis':clone(self.project['analysis'])},self.analysis_engine.currentData())
    def pdk_manager(self):
        from .pdks import PDKRegistry
        registry=PDKRegistry(self.data_dir/'pdks');dlg=QDialog(self);dlg.setWindowTitle('Installed PDK revisions');dlg.resize(640,420);v=QVBoxLayout(dlg);note=QLabel('Install a checksummed local technology package. Select an installed revision to activate or roll back.');note.setWordWrap(True);v.addWidget(note);items=QListWidget();v.addWidget(items);error=QLabel();error.setWordWrap(True);v.addWidget(error)
        def fill():
            items.clear()
            for m in registry.entries():items.addItem(m['id']+'@'+m['revision'])
        def install():
            path,_=QFileDialog.getOpenFileName(dlg,'Install technology package','','Package manifest (*.json)')
            if path:
                try:registry.install(path);fill();error.setText('Checksums verified. Select the revision to activate it.')
                except Exception as e:error.setText(str(e))
        def activate():
            if items.currentItem():
                try:
                    tech=registry.technology(items.currentItem().text());self.commit(lambda p:p.update(pdk=tech),'Activate PDK revision');self.layer_combo.clear();self.layer_combo.addItems([l['name'] for l in tech['layers']]);self.layout.visible_layers={l['name'] for l in tech['layers']};self.refresh();dlg.accept()
                except Exception as e:error.setText(str(e))
        row=QHBoxLayout();install_button=QPushButton('Install package…');install_button.clicked.connect(install);activate_button=QPushButton('Activate selected revision');activate_button.clicked.connect(activate);row.addWidget(install_button);row.addWidget(activate_button);v.addLayout(row);fill();self._pdk_dialog=dlg;dlg.show()
    def review_import(self):
        from .import_review import propose_layout_change
        path,_=QFileDialog.getOpenFileName(self,'Review layout changes','','Layout (*.gds *.oas)')
        if not path:return
        proposal,report=propose_layout_change(self.project,path);dlg=QDialog(self);dlg.setWindowTitle('Review imported geometry');dlg.resize(650,440);v=QVBoxLayout(dlg);text=QPlainTextEdit('\n'.join(report));text.setReadOnly(True);v.addWidget(text);buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Ok).setText('Apply reviewed geometry');v.addWidget(buttons)
        baseline=design_digest(self.project)
        def accept():
            if design_digest(self.project)!=baseline:QMessageBox.warning(dlg,'Design changed','Review the import again against the current revision.');return
            self.commit(lambda p:p.update(cells=proposal['cells']),'Apply imported geometry');dlg.accept()
        buttons.accepted.connect(lambda:self.guard(accept));buttons.rejected.connect(dlg.reject);self._import_dialog=dlg;dlg.show()
    def magic_extract_dialog(self):
        from .engines import magic_extract
        def submit(v):
            # Run engine commands in the standard CLI child process, keeping the interface responsive.
            self.start_cli_job(['extract','--executable',v['executable'],'--gds',v['gds'],'--technology',v['technology'],'--top',v['top'],'--output',v['output'],'--profile',v['profile']],'Magic extraction')
        self.workflow_form('Extract through Magic',[('executable','Magic executable',self.settings.value('engine/magic','magic')),('gds','GDS file',''),('technology','Technology file',''),('top','Top cell',self.cell['name']),('output','Output folder',''),('profile','Netlisting profile',['lvs','capacitance','rc'])],submit,'Requires an installed Magic engine and a matching technology file. Extraction and LVS use separate profiles. The output contains the engine log and extracted SPICE deck.')

    def symbol_dialog(self):
        from .symbol_editor import SymbolEditor
        cid=self.cid
        def save(symbol):self.commit(lambda p:next(c for c in p['cells'] if c['id']==cid).update(symbol=symbol),'Edit reusable symbol')
        dlg=SymbolEditor(self.cell,self.dark,save,self);self._symbol_dialog=dlg;dlg.show()
    def annotations_dialog(self):
        notes=self.cell.get('annotations',[])
        if not notes:self.add_annotation();return
        def submit(v):
            ident=notes[int(v['note'].split(':',1)[0])-1]['id']
            def edit(p):
                c=next(c for c in p['cells'] if c['id']==self.cid)
                if v['action']=='Delete':c['annotations']=[n for n in c['annotations'] if n['id']!=ident]
                else:next(n for n in c['annotations'] if n['id']==ident).update(text=v['text'])
            self.commit(edit,'Edit annotation')
        dlg=self.workflow_form('Manage annotations',[('note','Annotation',[str(i+1)+': '+n['text'][:50] for i,n in enumerate(notes)]),('text','Text',(notes[0]['text'],)),('action','Action',['Update','Delete'])],submit)
        dlg.fields['note'].currentIndexChanged.connect(lambda i:dlg.fields['text'].setPlainText(notes[i]['text']))
    def set_project(self,p,path=None):
        super().set_project(p,path)
        files=sorted((self.jobs_dir/p['id']).glob('*/result.json'),key=lambda f:f.stat().st_mtime)[-30:]
        for file in files:
            try:
                result=json.loads(file.read_text())
                if result.get('project_id')==p['id']:self.add_result(result)
            except (ValueError,OSError,KeyError) as e:self.console.appendPlainText('Could not restore a saved run: '+str(e))

    def deck_dialog(self):
        path,_=QFileDialog.getOpenFileName(self,'Run extracted SPICE testbench','','SPICE (*.cir *.spice *.spc)')
        if path:self.start_job({'type':'deck','deck':path},'ngspice')
    def noise_dialog(self):
        sources=[d['name'] for d in self.cell['devices'] if d['kind']=='V']
        if not sources:raise ValueError('Add an independent voltage source first.')
        def submit(v):self.start_job({'type':'noise','output':v['output'],'noise_source':v['source'],'source':v['source'],'start':v['start'],'end':v['end'],'points':int(v['points']),'temperature':scalar(v['temperature'])},'ngspice')
        self.workflow_form('ngspice noise analysis',[('output','Output net','vout'),('source','Input voltage source',sources),('start','Start frequency','10'),('end','End frequency','10meg'),('points','Points per decade','50'),('temperature','Temperature (°C)','27')],submit,'Uses the configured model deck. Device noise coverage depends on the chosen models.')

    def trace_selected(self,it):
        super().trace_selected(it);self.render_physical_hierarchy()
    def duplicate(self):
        items=[i for i in self.cell.get('layout_instances',[]) if i['id'] in self.selection] if self.current_mode=='layout' else []
        if not items:return super().duplicate()
        copies=[];names={i['name'] for i in self.cell['layout_instances']}
        for i in items:
            new=clone(i);new['id']=uid();new.pop('matching_group',None);new['x']+=1000;new['y']+=1000;name=i['name']+'_copy'
            while name in names:name+='x'
            names.add(name);new['name']=name;copies.append(new)
        self.commit(lambda p:next(c for c in p['cells'] if c['id']==self.cid)['layout_instances'].extend(copies),'Duplicate physical instances');self.select([i['id'] for i in copies],'layout')

    def import_xschem_dialog(self):
        from .xschem_io import import_package
        path,_=QFileDialog.getOpenFileName(self,'Import edited Xschem package','','Xschem (*.sch)')
        if not path:return
        candidate,report=import_package(path);dlg=QDialog(self);dlg.setWindowTitle('Review Xschem import');dlg.resize(640,420);v=QVBoxLayout(dlg);text=QPlainTextEdit('\n'.join(report));text.setReadOnly(True);v.addWidget(text);buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Ok).setText('Open imported project');v.addWidget(buttons)
        def accept():
            if self.maybe_save():self.set_project(candidate);dlg.accept()
        buttons.accepted.connect(lambda:self.guard(accept));buttons.rejected.connect(dlg.reject);self._import_dialog=dlg;dlg.show()

    def rerun_study(self):
        if not self.project.get('last_study'):raise ValueError('Configure a simulation study first.')
        self.start_job({'type':'study','analysis':clone(self.project['analysis']),'study':clone(self.project['last_study'])},self.analysis_engine.currentData())
    def help_dialog(self):
        import sys
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).parent.parent))/'docs';text='\n\n'.join((root/name).read_text() for name in ('USER_GUIDE.md','WORKFLOWS_0.3.md') if (root/name).exists());self.text_dialog('IC Design Studio help',text)
