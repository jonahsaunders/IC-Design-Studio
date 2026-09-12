"""Schematic-driven placement, analog constraints and live layout feedback."""
from PySide6.QtCore import Qt,QTimer,QThread,Signal,QEvent,QPointF
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QCheckBox,QTableWidgetItem,QDockWidget,QTabWidget
from .model import clone,digest,uid,scalar,design_digest
from .parametric import placement_inventory,install


class PhysicalCheckThread(QThread):
    checked=Signal(object)
    def __init__(self,p,cid,parent,checker=None):super().__init__(parent);self.project=p;self.cid=cid;self.checker=checker
    def run(self):
        from .live_geometry import full
        try:result=self.checker.check(self.project,self.cid) if self.checker is not None else full(self.project,self.cid)
        except Exception as exc:result={'issues':[],'guides':[],'error':str(exc)}
        self.checked.emit({'project_id':self.project['id'],'revision':self.project['revision'],'cid':self.cid,'result':result})


class PhysicalWorkspaceMixin:
    def make_ui(self):
        super().make_ui();self._live_worker=None;self._live_pending=False
        from .live_geometry import IncrementalChecks
        self._live_checker=IncrementalChecks()
        page,v=self.engineering_page('Physical design assistant','Place schematic devices, review remaining connections and keep analog constraints visible while editing.')
        self.engineering_buttons(v,[('Place / regenerate…',self.parametric_dialog),('Contact array…',lambda:self.utility_generator('contact')),('Guard ring…',lambda:self.utility_generator('guard_ring')),('Check now',self.start_live_checks)])
        self.placement_table=self.simulation_table(['Device','Type','Placement','Missing terminals']);self.placement_table.cellClicked.connect(self.placement_selected);self.placement_table.cellDoubleClicked.connect(lambda *_:self.parametric_dialog());v.addWidget(self.placement_table)
        self.engineering_buttons(v,[('Add constraint…',self.constraint_dialog),('Arrange selected constraint',self.arrange_constraint),('Remove constraint',self.remove_constraint)])
        self.constraint_table=self.simulation_table(['Constraint','Kind','Devices','Status']);v.addWidget(self.constraint_table)
        self.live_check=QCheckBox('Check layout changes in the background');self.live_check.setChecked(self.settings.value('physical/live_checks',True,type=bool));self.live_check.toggled.connect(self.live_toggled);v.addWidget(self.live_check)
        self.protect_routes=QCheckBox('Prevent routes and vias that violate preview checks');self.protect_routes.setChecked(True);v.addWidget(self.protect_routes)
        self.live_note=QLabel('Width, spacing, enclosure, constraint and terminal checks update after edits.');self.live_note.setWordWrap(True);v.addWidget(self.live_note)
        self.live_table=self.simulation_table(['Rule','Finding']);self.live_table.cellClicked.connect(self.live_finding_selected);v.addWidget(self.live_table);self.physical_assistant_tab=self.add_engineering_tab(page,'Placement & rules')
        self.live_timer=QTimer(self);self.live_timer.setSingleShot(True);self.live_timer.setInterval(500);self.live_timer.timeout.connect(self.start_live_checks)
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True);self.preview_timer.setInterval(60);self.preview_timer.timeout.connect(self.update_geometry_preview)
        self.layout.installEventFilter(self);self.layout.can_commit_shape=self.can_commit_geometry;self.refresh_placement()

    def make_actions(self):
        super().make_actions()
        self.action(self.task_menus['Layout'],'Placement and constraints',lambda:self.open_engineering_tab(self.physical_assistant_tab))
        self.action(self.task_menus['Route'],'Live routing feedback',lambda:self.open_engineering_tab(self.physical_assistant_tab))
        self.action(self.task_menus['Window'],'Placement and rules',lambda:self.open_engineering_tab(self.physical_assistant_tab));self.reindex_commands()

    def refresh(self,fit=False):
        super().refresh(fit)
        if hasattr(self,'placement_table'):
            self.refresh_placement()
            if self.live_check.isChecked():self.live_timer.start()

    def refresh_placement(self):
        from .analog_constraints import findings
        self._placement_rows=placement_inventory(self.project,self.cid);self.placement_table.setRowCount(len(self._placement_rows))
        for i,row in enumerate(self._placement_rows):
            for j,value in enumerate((row['name'],row['kind'],row['state'],', '.join(row['missing']))):self.placement_table.setItem(i,j,QTableWidgetItem(value))
        ds={d['id']:d['name'] for d in self.cell['devices']};constraints=self.cell.get('analog_constraints',[]);issues=findings(self.project,self.cid);self.constraint_table.setRowCount(len(constraints))
        for i,c in enumerate(constraints):
            failed=any(v['message'].startswith(c.get('name',c['kind'])+':') for v in issues)
            for j,value in enumerate((c.get('name',c['kind']),c['kind'],', '.join(ds.get(d,'Deleted') for d in c['members']),'Needs attention' if failed else 'Satisfied')):self.constraint_table.setItem(i,j,QTableWidgetItem(value))
    def placement_selected(self,row,col):
        if 0<=row<len(self._placement_rows):self.select([self._placement_rows[row]['id']],'schematic')
    def parametric_dialog(self):
        selected=[d for d in self.cell['devices'] if d['id'] in self.selection]
        if len(selected)!=1:
            i=self.placement_table.currentRow()
            if i>=0:selected=[d for d in self.cell['devices'] if d['id']==self._placement_rows[i]['id']]
        if len(selected)!=1:raise ValueError('Select one device in the placement checklist or schematic.')
        d=selected[0];did=d['id'];cid=self.cid;record=next((r for r in self.cell.get('parametric_devices',[]) if r['device_id']==did),None);spec=record['spec'] if record else {}
        if d.get('native_spice') and d['kind']!='X' and not d.get('physical_binding'):
            return self.native_binding_dialog(did)
        def submit(v):
            x,y=[round(scalar(v[k])*1000) for k in ('x','y')];width=round(scalar(v['width'])*1000) if v['width'].strip() else 0
            def edit(p):
                if d['kind']=='X':
                    from .physical_cells import place
                    place(p,cid,did,x,y);return
                from .catalog import binding_for
                if binding_for(p['pdk'],d) and d['kind'] in ('NMOS','PMOS','PDK'):
                    from .process_adapters import install_mos,regenerate_mos
                    c=next(c for c in p['cells'] if c['id']==cid)
                    if any(s.get('generated_device')==did for s in c['shapes']):regenerate_mos(p,cid,did)
                    else:install_mos(p,cid,did,x,y)
                    return
                install(p,cid,did,{'x':x,'y':y,'width':width or (1000 if d['kind']=='R' else 0),'fingers':int(v['fingers'])})
            self.commit(edit,'Generate linked device');self.mode_combo.setCurrentIndex(1);self.select([did],'layout');self.layout.fit()
        return self.workflow_form('Place / regenerate '+d['name'],[('x','X (µm)',str(spec.get('x',0)/1000)),('y','Y (µm)',str(spec.get('y',0)/1000)),('width','Resistor / capacitor width (µm; blank = automatic)',str(spec.get('width','')/1000) if spec.get('width') else ''),('fingers','Generic MOS fingers',str(spec.get('fingers',1)))],submit,'Uses the schematic value or W/L. Regeneration retains device and terminal IDs and preserves a translated placement. Process models use their native supported MOS recipes.')
    def utility_generator(self,kind):
        fields=[('x','X (µm)','0'),('y','Y (µm)','0'),('net','Net','0')]+([('rows','Rows','2'),('columns','Columns','2')] if kind=='contact' else [('width','Outer width (µm)','20'),('height','Outer height (µm)','20'),('thickness','Ring thickness (µm)','0.6')]);cid=self.cid
        def submit(v):
            spec={'kind':kind,**v}
            for k in ('x','y','width','height','thickness'):
                if k in v:spec[k]=round(scalar(v[k])*1000)
            for k in ('rows','columns'):
                if k in v:spec[k]=int(v[k])
            self.commit(lambda p:install(p,cid,None,spec),'Generate '+kind);self.mode_combo.setCurrentIndex(1);self.layout.fit()
        return self.workflow_form('Generate '+kind.replace('_',' '),fields,submit,'Uses declared technology layers and enclosure rules. Teaching-process geometry is illustrative; process qualification requires its extraction and rule decks.')
    def constraint_dialog(self):
        ds={d['name']:d['id'] for d in self.cell['devices'] if d['kind'] not in ('V','I')};names=[name for name,ident in ds.items() if ident in self.selection];cid=self.cid
        def submit(v):
            groups=[[ds[n.strip()] for n in group.split(',') if n.strip()] for group in v['groups'].split(';')];members=list(dict.fromkeys(sum(groups,[])));row={'id':uid(),'name':v['name'],'kind':v['kind'],'members':members,'axis':v['axis'],'coordinate':round(scalar(v['coordinate'])*1000)}
            if row['kind']=='common_centroid':row['groups']=groups
            if row['kind']=='guard_ring':
                rings=[r for r in self.cell.get('parametric_devices',[]) if r['spec']['kind']=='guard_ring']
                if not rings:raise ValueError('Generate a guard ring first.')
                row['ring']=rings[-1]['id']
            self.commit(lambda p:next(c for c in p['cells'] if c['id']==cid).setdefault('analog_constraints',[]).append(row),'Save analog constraint')
        return self.workflow_form('Analog placement constraint',[('name','Name','Matched group'),('kind','Constraint',['symmetry','matching','common_centroid','guard_ring']),('groups','Devices (comma separated); centroid groups separated by ;',','.join(names)),('axis','Symmetry axis',['x','y']),('coordinate','Axis coordinate (µm)','0')],submit,'Symmetry uses two devices. Matching checks parameters, shape and orientation. Common-centroid uses explicit unit-device groups. Guard coverage uses the most recently generated ring.')
    def arrange_constraint(self):
        from .analog_constraints import arrange
        i=self.constraint_table.currentRow()
        if i<0:raise ValueError('Select a constraint.')
        cid=self.cid;row=clone(self.cell['analog_constraints'][i])
        def submit(v):self.commit(lambda p:arrange(p,cid,row,round(scalar(v['pitch'])*1000)),'Arrange constrained devices');self.layout.fit()
        return self.workflow_form('Arrange constrained devices',[('pitch','Common-centroid pitch (µm)','10')],submit,'Symmetry holds the first device fixed. Automatic common-centroid uses ABBA pairs of explicit unit devices. Existing routes stay in place; remaining connections update after placement.')
    def remove_constraint(self):
        i=self.constraint_table.currentRow();cid=self.cid
        if i>=0:self.commit(lambda p:next(c for c in p['cells'] if c['id']==cid)['analog_constraints'].pop(i),'Remove analog constraint')
    def live_toggled(self,enabled):
        self.settings.setValue('physical/live_checks',enabled)
        if enabled:self.live_timer.start()
        else:self.live_timer.stop()
    def start_live_checks(self):
        if not self.cell['shapes'] and not self.cell.get('layout_instances'):return
        if self._live_worker is not None:self._live_pending=True;return
        self.live_note.setText('Checking revision '+str(self.project['revision'])+'…');worker=PhysicalCheckThread(clone(self.project),self.cid,self,self._live_checker);self._live_worker=worker;worker.checked.connect(self.live_checks_ready);worker.finished.connect(self.live_worker_done);worker.start()
    def live_worker_done(self):
        worker=self._live_worker;self._live_worker=None
        if worker:worker.deleteLater()
        if self._live_pending:self._live_pending=False;self.live_timer.start()
    def live_checks_ready(self,packet):
        if (packet['project_id'],packet['revision'],packet['cid'])!=(self.project['id'],self.project['revision'],self.cid):return
        result=packet['result'];self._live_findings=result['issues'];self._live_revision=self.project['revision'];self.live_table.setRowCount(len(result['issues']))
        for i,issue in enumerate(result['issues']):
            for j,value in enumerate((issue['code'],issue['message'])):self.live_table.setItem(i,j,QTableWidgetItem(value))
        self.layout.connection_guides=result['guides'];self.layout.update();self.live_note.setText(result.get('error') or f"Revision {self.project['revision']} · {len(result['issues'])} findings · {len(result['guides'])} remaining connections. "+result.get('qualification',''))
    def live_finding_selected(self,row,col):
        if getattr(self,'_live_revision',None)!=self.project['revision']:self.live_note.setText('Findings are stale; checking current geometry.');self.live_timer.start();return
        self.issues=self._live_findings;self.check_revision=self.project['revision'];self.fill_checks();self.check_selected(row,0)
    def eventFilter(self,obj,event):
        if hasattr(self,'layout') and obj is self.layout and event.type() in (QEvent.MouseMove,QEvent.MouseButtonPress,QEvent.MouseButtonRelease,QEvent.KeyPress):
            if hasattr(self,'preview_timer') and not self.preview_timer.isActive():self.preview_timer.start()
        return super().eventFilter(obj,event)
    def geometry_candidates(self):
        canvas=self.layout
        if canvas.tool=='via' and self._via_configuration and canvas.drag:
            p=clone(self.project);cid,connection,net=self._via_configuration
            if cid!=self.cid:raise ValueError('The active cell changed. Start via placement again.')
            from .layout_edit import place_via
            ids=place_via(p,cid,connection,[round(canvas.drag.x()),round(canvas.drag.y())],net,canvas.locked_layers);return [s for c in p['cells'] if c['id']==cid for s in c['shapes'] if s['id'] in ids]
        if canvas.tool=='rect' and canvas.anchor and canvas.drag:
            a,b=canvas.anchor,canvas.drag
            if a.x()!=b.x() and a.y()!=b.y():return [{'id':'preview','kind':'rect','layer':canvas.layer,'points':[[int(a.x()),int(a.y())],[int(b.x()),int(b.y())]],'net':self.editor_net.currentText().strip()}]
        if canvas.tool=='path' and canvas.drawing and canvas.drag:
            points=canvas.drawing+canvas.path_preview(canvas.drag);pts=[]
            for pt in points:
                pair=[int(pt.x()),int(pt.y())]
                if not pts or pair!=pts[-1]:pts.append(pair)
            if len(pts)>=2:return [{'id':'preview','kind':'path','layer':canvas.layer,'points':pts,'width':canvas.line_width,'net':self.editor_net.currentText().strip()}]
        return []
    def update_geometry_preview(self):
        from .live_geometry import preview
        try:
            shapes=self.geometry_candidates();issues=preview(self.project,self.cid,shapes) if shapes else [];self.layout.live_preview=[] if self.layout.tool in ('path','rect') else shapes;self.layout.live_preview_blocked=bool(issues)
            if shapes:self.live_note.setText('Blocked: '+issues[0]['message'] if issues else 'Preview clear for declared local rules. Click to place; background connectivity checks follow.')
        except Exception as exc:self.layout.live_preview=[];self.live_note.setText(str(exc))
        self.layout.update()
    def can_commit_geometry(self,shape):
        if shape['kind']!='path' or not self.protect_routes.isChecked():return True
        from .live_geometry import preview
        shape['net']=shape.get('net','');issues=preview(self.project,self.cid,[shape])
        if issues:
            self.layout.drawing_error='Route blocked: '+issues[0]['message'];self.live_note.setText(self.layout.drawing_error);self.statusBar().showMessage(self.layout.drawing_error,12000);return False
        return True
    def place_canvas_via(self,x,y):
        if self._via_configuration and self._via_configuration[0]!=self.cid:
            raise ValueError('The active cell changed. Start via placement again.')
        if self.protect_routes.isChecked() and self._via_configuration:
            from .layout_edit import place_via
            from .live_geometry import preview
            p=clone(self.project);cid,connection,net=self._via_configuration;ids=place_via(p,cid,connection,[round(x),round(y)],net,self.layout.locked_layers);shapes=[s for c in p['cells'] if c['id']==cid for s in c['shapes'] if s['id'] in ids];issues=preview(self.project,cid,shapes)
            if issues:
                self.live_note.setText('Blocked: '+issues[0]['message'])
                raise ValueError('Via blocked: '+issues[0]['message'])
        return super().place_canvas_via(x,y)
    def closeEvent(self,event):
        if getattr(self,'_live_worker',None) is not None:
            self._live_worker.wait(5000)
            if self._live_worker.isRunning():event.ignore();self.statusBar().showMessage('Finishing the current geometry check. Close again when it completes.');return
        return super().closeEvent(event)
