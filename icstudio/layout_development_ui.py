"""Desktop commands for connected editing, route planning and layout inspection."""
import json
import shutil
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QTableWidgetItem,QFileDialog
from .model import clone, scalar, digest, file_digest, design_digest


def nm(text):return round(scalar(text)*1000)
def point(text):
    values=text.split(',')
    if len(values)!=2:raise ValueError('Enter X, Y in micrometres, for example 5, 2.')
    return [nm(v) for v in values]


class LayoutDevelopmentMixin:
    def make_ui(self):
        super().make_ui()
        from PySide6.QtCore import QTimer
        self._cursor_route=None;self._cursor_hover=None
        self.cursor_route_timer=QTimer(self);self.cursor_route_timer.setSingleShot(True);self.cursor_route_timer.setInterval(80)
        self.cursor_route_timer.timeout.connect(lambda:self.guard(self.update_cursor_route))
        self.layout.route_point_requested.connect(lambda x,y:self.guard(lambda:self.cursor_route_click(x,y)))
        self.layout.route_hover_requested.connect(self.cursor_route_hover)
        self.layout.tool_cancelled.connect(self.cancel_cursor_route)

    def make_actions(self):
        super().make_actions();menu=self.task_menus['Layout']
        self.action(menu,'3D layout viewer…',self.layout_3d_dialog)
        self.connected_layout_action=self.action(menu,'Preserve connections on move / stretch',lambda:None)
        self.connected_layout_action.setCheckable(True);self.connected_layout_action.setChecked(True)
        routing=menu.addMenu('Multilayer routing')
        self.action(routing,'Route with cursor…',self.cursor_route_dialog)
        for title,fn in [('Plan route…',self.route_dialog),('Plan matched pair…',self.matched_route_dialog),('Shield selected route…',self.shield_route_dialog)]:self.action(routing,title,fn)
        self.action(routing,'Review selected route result',self.review_selected_layout_result)
        library=menu.addMenu('PCell library')
        for title,fn in [('Import definition…',self.import_pcell_definition),('Create cell from library…',self.library_cell_dialog),('Regenerate library cell…',self.library_regenerate_dialog),('Inspect library cells',self.library_audit_dialog)]:self.action(library,title,fn)
        inspect=menu.addMenu('Inspection and finishing')
        for title,fn in [('Query layout…',self.layout_query_dialog),('Compare against GDSII / OASIS…',self.layout_compare_dialog),('Measure layer density…',self.layout_density_dialog),('Insert dummy fill…',self.layout_fill_dialog),('Round selected corners…',self.layout_round_dialog)]:self.action(inspect,title,fn)
        self.action(self.task_menus['Verify'],'Run bundled KLayout rules…',self.klayout_bundle_dialog)
        self.action(menu,'Review schematic changes in layout…',self.layout_eco_dialog)
        self.action(self.analysis_submenus['Post-layout'],'Calibrate RC from measurements…',self.rc_calibration_dialog)
        self.action(self.task_menus['Help'],'Layout development guide',lambda:self.open_editor_doc('LAYOUT_SCALE_AND_COLLABORATION.md'))
        self.reindex_commands()

    def layout_3d_dialog(self):
        from .layout_3d_ui import show
        return show(self)

    def layout_eco_dialog(self):
        from .layout_eco_ui import show
        return show(self)

    def rc_calibration_dialog(self):
        path,_=QFileDialog.getOpenFileName(self,'Import RC coupon measurements','','JSON (*.json)')
        if not path:return
        from .rc_calibration import calibrate,install
        if Path(path).stat().st_size>1000000:raise ValueError('Use a measurement JSON file below 1 MB.')
        result=calibrate(self.project['pdk'],json.loads(Path(path).read_text()))
        def build():
            p=clone(self.project);install(p['pdk'],result)
            return p,'Corner '+result['corner']+' · '+str(len(result['coefficients']))+' layers. Maximum coupon residual: '+format(result['max_relative_error'],'.2%')+'. Source: '+result['source']+'. Calibration covers only the supplied coupons and declared model. See PRIORITIES_0.22.md for the input format.'
        return self.review_dialog('Review RC calibration',build)

    def cursor_route_dialog(self):
        if not self.idle_edit():return
        from .route_interaction import CursorRoute
        cid=self.cid
        def submit(v):
            args=self.route_arguments(v);net=v['net'].strip()
            if not {v['start_layer'],v['end_layer']}<=set(args['layers']):raise ValueError('Include both endpoint layers in Allowed layers.')
            session=CursorRoute(self.project,cid,net,args['width'],args['layers'],args['locked'])
            self.cancel_cursor_route();self._cursor_route={'session':session,'cid':cid,'revision':self.project['revision'],'project_id':self.project['id'],'start':None,'start_layer':v['start_layer'],'end_layer':v['end_layer'],'net':net,'arguments':args}
            self.mode_combo.setCurrentIndex(1);self.layout.snap_to_terminals=self.editor_snap.currentIndex()==0;self.layout.cancel_gesture();self.layout.tool='route_cursor';self.layout.setFocus();self.statusBar().showMessage('Click the start, then the destination. Preview checks direct bends; the worker searches detours. Escape cancels.')
        return self.workflow_form('Route with cursor',self.route_fields()+[('net','Net',self.net or 'signal')],submit,'Preview supports up to 2,500 expanded shapes. Clicking the destination starts a cancellable route job; review the result before installation. All saved analog and route constraints remain visible in live checks.')

    def cancel_cursor_route(self):
        self._cursor_route=None;self.cursor_route_timer.stop();self.layout.cursor_route_preview=[];self.layout.update()

    def cursor_route_current(self):
        s=self._cursor_route
        if not s:return None
        if (s['project_id'],s['revision'],s['cid'])!=(self.project['id'],self.project['revision'],self.cid) or set(s['arguments']['locked']) != self.layout.locked_layers:
            self.cancel_cursor_route();raise ValueError('The design, active cell or layer locks changed. Start the cursor route again.')
        return s

    def cursor_route_click(self,x,y):
        s=self.cursor_route_current()
        if not s:return
        if s['start'] is None:s['start']={'layer':s['start_layer'],'point':[round(x),round(y)]};return
        args={**s['arguments'],'net':s['net'],'start':s['start'],'end':{'layer':s['end_layer'],'point':[round(x),round(y)]}}
        self.enqueue_layout(s['cid'],{'type':'layout_route','operation':'route','arguments':args},'Cursor route proposal')
        self.cancel_cursor_route();self.layout.tool='select'

    def cursor_route_hover(self,x,y):
        self._cursor_hover=[round(x),round(y)]
        if self._cursor_route and self._cursor_route['start'] is not None and not self.cursor_route_timer.isActive():self.cursor_route_timer.start()

    def update_cursor_route(self):
        if self.layout.tool!='route_cursor':self.cancel_cursor_route();return
        s=self.cursor_route_current()
        if not s or s['start'] is None:return
        result=s['session'].preview(s['start'],{'layer':s['end_layer'],'point':self._cursor_hover})
        self.layout.cursor_route_preview=result['shapes'];self.layout.cursor_route_blocked=not result['clear'];self.layout.update();self.statusBar().showMessage(result['message'])

    def move(self,ids,x,y,mode):
        if mode=='layout' and not self.connected_layout_action.isChecked() and hasattr(self.history,'commit_shape_move'):
            if not self.flush_inspector():return
            if self.history.commit_shape_move(self.cid,ids,round(x),round(y),self.layout.locked_layers):
                self.queue_recovery(validated=True)
                self.refresh_layout_edit()
                return
        if mode!='layout' or not self.connected_layout_action.isChecked():
            from .hierarchy_ui import HierarchyMixin
            return HierarchyMixin.move(self,ids,x,y,mode)
        def edit():
            if not self.flush_inspector():return
            if not self.history.commit_layout_move(self.cid,ids,round(x),round(y),self.layout.locked_layers):
                from .layout_topology import move
                return self.commit(lambda p:move(p,self.cid,ids,round(x),round(y),self.layout.locked_layers),'Connected layout move')
            self.queue_recovery(validated=True)
            self.refresh_layout_edit()
        self.guard(edit)

    def arrange_layout(self,cid,ids,edge,locked=(),**options):
        if not self.flush_inspector():return
        if not self.history.commit_layout_arrange(cid,ids,edge,locked,**options):
            from .layout_tools_ui import LayoutToolsMixin
            return LayoutToolsMixin.arrange_layout(self,cid,ids,edge,locked,**options)
        self.queue_recovery(validated=True)
        self.refresh_layout_edit()

    def refresh_layout_edit(self,recovered=True):
        """Geometry-only refresh; the cell tree, layers and circuit are unchanged."""
        self.layout.set_data(self.cell,self.project['pdk'],self.selection,self.net,revision=self.project['revision'],dirty_indices=self.history.layout_stats['indices'])
        self.schematic.set_data(self.cell,self.project['pdk'],self.selection,self.net)
        self.revision_label.setText(f"r{self.project['revision']}  /  {self.project['pdk']['name']}")
        self.undo_action.setEnabled(bool(self.history.undo_stack));self.redo_action.setEnabled(bool(self.history.redo_stack))
        self.update_save_status()
        self._inspector_dirty=False;self.build_inspector();self.update_result_status()
        self.layout.connection_guides=[];self.layout.finding_box=None
        self.live_note.setText('Layout changed; previous findings are stale.')
        self.filter_editor_findings()
        if self.live_check.isChecked():self.live_timer.start()

    def check_layout_incremental(self):
        # The UI probe owns a separate cache from the serial background worker.
        from .live_geometry import IncrementalChecks
        if not hasattr(self,'_local_check_cache'):self._local_check_cache=IncrementalChecks()
        return self._local_check_cache.check(self.project,self.cid)

    def stretch_layout_path(self,p,cid,sid,segment,offset,locked):
        if self.connected_layout_action.isChecked():
            from .layout_topology import stretch
            return stretch(p,cid,sid,segment,offset,locked)
        from .layout_edit import stretch_path
        return stretch_path(p,cid,sid,segment,offset,locked)

    def route_fields(self):
        from .layout_routing import conductors
        layers=conductors(self.project['pdk'])
        if not layers:raise ValueError('This technology has no declared routing conductors.')
        return [('start_layer','Start layer',layers),('end_layer','End layer',layers),
                ('layers','Allowed layers',', '.join(layers)),('width','Width (µm)','0.4'),('margin','Search margin (µm)','5')]

    def route_arguments(self,v):
        return {'width':nm(v['width']),'layers':[l.strip() for l in v['layers'].split(',')],
                'margin':nm(v['margin']),'locked':list(self.layout.locked_layers)}

    def enqueue_layout(self,cid,settings,title):
        self.run_manager.enqueue({'project':clone(self.project),'cell':cid,'engine':'builtin','settings':settings},self.jobs_dir,title)
        self.open_engineering_tab(self.simulation_tab)

    def route_dialog(self):
        if not self.idle_edit():return
        cid=self.cid
        def submit(v):
            args={**self.route_arguments(v),'net':v['net'].strip(),
                'start':{'layer':v['start_layer'],'point':point(v['start'])},
                'end':{'layer':v['end_layer'],'point':point(v['end'])}}
            self.enqueue_layout(cid,{'type':'layout_route','operation':'route','arguments':args},'Multilayer route proposal')
        return self.workflow_form('Plan multilayer route',self.route_fields()+[('net','Net','signal'),('start','Start X, Y (µm)','0, 0'),('end','End X, Y (µm)','5, 0')],submit,
            'The planner checks declared width, spacing and via footprints. Review the result before installation. Search runs in a cancellable job; use Run queue to cancel it.')

    def matched_route_dialog(self):
        if not self.idle_edit():return
        cid=self.cid
        def submit(v):
            args={**self.route_arguments(v),'nets':[v['net1'].strip(),v['net2'].strip()],
                'starts':[{'layer':v['start_layer'],'point':point(v['start'+str(i)])} for i in (1,2)],
                'ends':[{'layer':v['end_layer'],'point':point(v['end'+str(i)])} for i in (1,2)],'tolerance':nm(v['tolerance'])}
            self.enqueue_layout(cid,{'type':'layout_route','operation':'matched_pair','arguments':args},'Matched route proposal')
        fields=self.route_fields()+[('net1','First net','plus'),('net2','Second net','minus'),
            ('start1','First start X, Y (µm)','0, 0'),('end1','First end X, Y (µm)','5, 0'),
            ('start2','Second start X, Y (µm)','0, 5'),('end2','Second end X, Y (µm)','7, 5'),('tolerance','Length tolerance (µm)','0')]
        return self.workflow_form('Plan matched pair',fields,submit,'Matches geometric centreline length. Automatic tuning requires one straight shorter route and a clear detour corridor. Electrical matching requires extraction.')

    def shield_route_dialog(self):
        if not self.idle_edit():return
        s=self.selected_path();cid=self.cid;sid=s['id'];fields=self.route_fields()
        fields=[f for f in fields if f[0] not in ('start_layer','end_layer')]
        from .layout_routing import conductors
        fields += [('ground_layer','Reference layer',conductors(self.project['pdk'])),('ground','Reference X, Y (µm)','0, 0'),('net','Reference net','0'),('gap','Signal-to-shield gap (µm)','0.5')]
        def submit(v):
            args={**self.route_arguments(v),'sid':sid,'ground':{'layer':v['ground_layer'],'point':point(v['ground'])},'net':v['net'].strip(),'gap':nm(v['gap'])}
            self.enqueue_layout(cid,{'type':'layout_route','operation':'shield','arguments':args},'Grounded shield proposal')
        return self.workflow_form('Shield selected route',fields,submit,'Creates two shields beside a straight route and routes each to an existing conductor labeled with the reference net.')

    def add_result(self,result):
        super().add_result(result)
        if result.get('layout_proposal'):self.review_layout_proposal(result['layout_proposal'])
        if result.get('layout_comparison'):self.show_layout_comparison(result['layout_comparison'],result)

    def rerun_snapshot(self):
        from .layout_jobs import replay_job
        for row in self.selected_simulation_runs():self.run_manager.enqueue(replay_job(row),self.jobs_dir,row['name']+' · rerun')

    def review_layout_proposal(self,proposal):
        dlg=QDialog(self);dlg.setWindowTitle('Route proposal');v=QVBoxLayout(dlg)
        lengths=proposal.get('lengths_nm',[proposal.get('length_nm',0)])
        label=QLabel(f"{len(proposal['shapes'])} shapes · {proposal.get('via_count',sum(s['kind']=='rect' for s in proposal['shapes'])//3)} vias\nLengths: "+', '.join(f'{x/1000:g} µm' for x in lengths)+'\n'+proposal['qualification']);label.setWordWrap(True);v.addWidget(label)
        source=next((row['job']['project'] for row in self.run_manager.rows if row.get('result',{}).get('layout_proposal',{}).get('route_group')==proposal['route_group']),None)
        if source is None and design_digest(self.project)==proposal['design_hash']:source=self.project
        if source is not None:
            from .canvas import Canvas
            from .design_ops import flatten_layout
            cell=clone(next(c for c in source['cells'] if c['id']==proposal['cell_id']))
            cell['shapes']=clone(flatten_layout(source,proposal['cell_id']))+clone(proposal['shapes'])
            preview=Canvas('layout',dlg);preview.tool='ruler';preview.locked_layers={l['name'] for l in source['pdk']['layers']}
            preview.set_data(cell,clone(source['pdk']),[s['id'] for s in proposal['shapes']]);v.addWidget(preview,2);dlg.preview=preview
            v.addWidget(QLabel('Proposed geometry is highlighted. Scroll to zoom; middle-drag to pan.'))
        table=self.simulation_table(['Layer','Kind','Net','Length (µm)']);table.setRowCount(len(proposal['shapes']));v.addWidget(table)
        from .layout_routing import length,install
        for i,s in enumerate(proposal['shapes']):
            for j,value in enumerate((s['layer'],s['kind'],s.get('net',''),f'{length([s])/1000:g}')):table.setItem(i,j,QTableWidgetItem(str(value)))
        error=QLabel();error.setWordWrap(True);v.addWidget(error);button=QPushButton('Install route');v.addWidget(button)
        def accept():
            try:
                if not self.idle_edit() or not self.flush_inspector():return
                ids=[];self.commit(lambda p:ids.extend(install(p,proposal,self.layout.locked_layers)),'Install route proposal')
                self.cid=proposal['cell_id'];self.refresh();self.mode_combo.setCurrentIndex(1);self.select(ids,'layout');self.layout.fit();dlg.accept()
            except Exception as exc:error.setText(str(exc))
        button.clicked.connect(accept);dlg.resize(850,780);self._layout_proposal_dialog=dlg;dlg.show()

    def review_selected_layout_result(self):
        if not self.result or not self.result.get('layout_proposal'):raise ValueError('Select a completed route job in the run queue.')
        return self.review_layout_proposal(self.result['layout_proposal'])

    def import_pcell_definition(self):
        if not self.idle_edit():return
        path,_=QFileDialog.getOpenFileName(self,'Import PCell definition','','JSON definition (*.json)')
        if not path:return
        if Path(path).stat().st_size>2_000_000:raise ValueError('The PCell definition exceeds 2 MB.')
        from .pcell_library import register
        definition=json.loads(Path(path).read_text(encoding='utf-8'));self.commit(lambda p:register(p,definition),'Import PCell definition')

    def library_cell_dialog(self):
        if not self.idle_edit():return
        names=list(self.project.get('pcell_library',{}))
        if not names:raise ValueError('Import a PCell JSON definition first. See the layout development guide for an example.')
        def choose(v):
            definition=self.project['pcell_library'][v['definition']];fields=[('name','New cell name',v['definition']+'_cell')]+[(n,n+' (integer)',s['default']) for n,s in definition.get('parameters',{}).items()]
            def submit(values):
                from .pcell_library import create_cell
                ids=[];self.commit(lambda p:ids.append(create_cell(p,values['name'],v['definition'],{n:int(values[n]) for n in definition.get('parameters',{})})),'Create library PCell')
                self.cid=ids[0];self.refresh(True);self.mode_combo.setCurrentIndex(1)
            self.workflow_form('PCell parameters',fields,submit,'Geometry dimensions are integer nanometres. The new cell can be placed through Physical cells / Place physical cell or array.')
        return self.workflow_form('Choose PCell',[('definition','Definition',names)],choose)

    def library_regenerate_dialog(self):
        if not self.idle_edit():return
        r=self.cell.get('library_pcell');cid=self.cid
        if not r:raise ValueError('Open a cell created from the PCell library.')
        from .pcell_library import regenerate
        return self.workflow_form('Regenerate library PCell',[(n,n+' (integer)',v) for n,v in r['parameters'].items()],
            lambda v:self.commit(lambda p:regenerate(p,cid,{n:int(x) for n,x in v.items()}),'Regenerate library PCell'),
            'Uses the current registered definition and preserves shape IDs by role. Parent connections are checked before committing.')

    def layout_table(self,title,columns,rows,keys,locate=None,note=''):
        dlg=QDialog(self);dlg.setWindowTitle(title);dlg.resize(960,600);v=QVBoxLayout(dlg);label=QLabel(note);label.setWordWrap(True);v.addWidget(label)
        table=self.simulation_table(columns);table.setRowCount(len(rows));v.addWidget(table)
        for i,row in enumerate(rows):
            for j,key in enumerate(keys):table.setItem(i,j,QTableWidgetItem(str(row[key])))
        if locate:table.cellDoubleClicked.connect(lambda i,j:self.guard(lambda:locate(rows[i])))
        dlg.table=table;self._layout_table_dialog=dlg;dlg.show();return dlg

    def library_audit_dialog(self):
        from .pcell_library import audit
        return self.layout_table('PCell library cells',['Cell','Definition','State'],audit(self.project),['cell','name','state'])

    def locate_layout_box(self,cid,box,source_hash):
        if design_digest(self.project)!=source_hash:raise ValueError('The design changed. Run the inspection again.')
        self.cid=cid;self.refresh();self.mode_combo.setCurrentIndex(1);self.layout.finding_box=box;self.layout.fit();self.layout.update()

    def layout_query_dialog(self):
        cid=self.cid
        def submit(v):
            from .layout_inspection import query
            result=query(self.project,cid,v['layer'] if v['layer']!='All' else '',v['net'].strip(),minimum_area=scalar(v['area'])*1e6)
            self.layout_table('Layout query',['Layer','Net','Kind','Area (µm²)','Instance'],result['rows'],['layer','net','kind','area_um2','instance_path'],
                lambda row:self.locate_layout_box(cid,row['bbox'],result['design_hash']),f"{result['total']} matches; showing {len(result['rows'])}. Double-click to locate geometry.")
        return self.workflow_form('Query layout',[('layer','Layer',['All']+[l['name'] for l in self.project['pdk']['layers']]),('net','Exact net (blank for all)',''),('area','Minimum area (µm²)','0')],submit)

    def layout_compare_dialog(self):
        path,_=QFileDialog.getOpenFileName(self,'Select reference layout','','GDSII / OASIS (*.gds *.gds2 *.oas)')
        if not path:return
        cid=self.cid
        return self.workflow_form('Compare layout',[('top','Reference top (blank for single root)','')],
            lambda v:self.enqueue_layout(cid,{'type':'layout_compare','reference':path,'reference_sha256':file_digest(path),'reference_top':v['top'].strip()},'Layout geometry comparison'),
            'Compares the active cell with the reference top by layer and datatype. The worker expands up to 500,000 shapes. Text and electrical equivalence are separate checks.')

    def show_layout_comparison(self,comparison,result):
        return self.layout_table('Layout geometry differences',['Layer','Datatype','Change','Area (µm²)'],comparison['rows'],['layer','datatype','change','area_um2'],
            lambda row:self.locate_layout_box(result['cell_id'],[v*1000 for v in row['bbox_um']],result['design_hash']),
            f"{comparison['total']} difference polygons; showing {len(comparison['rows'])}. Added means present in the reference only. "+comparison['qualification'])

    def region_fields(self):return [('layer','Layer',[l['name'] for l in self.project['pdk']['layers']]),('lower','Lower X, Y (µm)','0, 0'),('upper','Upper X, Y (µm)','20, 20')]

    def layout_density_dialog(self):
        cid=self.cid
        def submit(v):
            from .layout_inspection import density
            result=density(self.project,cid,v['layer'],point(v['lower'])+point(v['upper']),nm(v['tile']))
            self.layout_table('Layer density',['Tile bounds (nm)','Area fraction'],result['rows'],['bbox','density'],lambda row:self.locate_layout_box(cid,row['bbox'],result['design_hash']),f"Minimum {result['minimum']:.1%}; maximum {result['maximum']:.1%}. These are geometric area fractions, not process density-rule results.")
        return self.workflow_form('Measure layer density',self.region_fields()+[('tile','Tile size (µm)','10')],submit)

    def layout_fill_dialog(self):
        if not self.idle_edit():return
        cid=self.cid
        def submit(v):
            from .layout_inspection import fill
            ids=[];self.commit(lambda p:ids.extend(fill(p,cid,v['layer'],point(v['lower'])+point(v['upper']),nm(v['size']),nm(v['pitch']),nm(v['keepout']),self.layout.locked_layers)),'Insert dummy fill');self.select(ids,'layout')
        return self.workflow_form('Insert dummy fill',self.region_fields()+[('size','Square size (µm)','1'),('pitch','Pitch (µm)','3'),('keepout','All-layer keepout (µm)','1')],submit,
            'Adds floating square fill outside existing geometry on every layer. Run process density checks and re-extract parasitics after filling.')

    def layout_round_dialog(self):
        if not self.idle_edit():return
        cid=self.cid;ids=list(self.selection)
        from .layout_inspection import round_corners
        return self.workflow_form('Round selected corners',[('inner','Inner radius (µm)','0.1'),('outer','Outer radius (µm)','0.1'),('points','Points per circle','32')],
            lambda v:self.commit(lambda p:round_corners(p,cid,ids,nm(v['inner']),nm(v['outer']),int(v['points']),self.layout.locked_layers),'Round layout corners'),
            'Rounds polygon corners and quantizes to the project grid. Existing physical connections must remain intact. Run DRC after rounding.')

    def klayout_bundle_dialog(self):
        path,_=QFileDialog.getOpenFileName(self,'Select KLayout rule entry','','KLayout DRC (*.drc *.rb)')
        if not path:return
        root=QFileDialog.getExistingDirectory(self,'Choose dependency folder containing the entry',str(Path(path).parent))
        if not root:return
        from .rule_bundle import capture
        bundle=capture(path,root);executable=self.settings.value('engine/klayout','') or shutil.which('klayout')
        if not executable or not Path(executable).is_file():executable,_=QFileDialog.getOpenFileName(self,'Locate KLayout executable')
        if not executable or not self.flush_inspector():return
        text=bundle['files'][bundle['entry']];settings={'type':'klayout_drc','runset_text':text,'runset_hash':digest(text),
            'rule_bundle':bundle,'bundle_hash':digest(bundle),'executable':executable,'executable_sha256':file_digest(executable),'timeout':600}
        self.settings.setValue('engine/klayout',executable)
        self.run_manager.enqueue({'project':clone(self.project),'cell':self.cid,'engine':'klayout','settings':settings},self.jobs_dir,'Bundled KLayout verification');self.open_engineering_tab(self.simulation_tab)
