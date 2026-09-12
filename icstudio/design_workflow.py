"""A shared, automatically refreshed circuit workflow for both editors."""
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QTabWidget)
from .model import clone


def inspect_project(project, cid):
    """Pure document inspection; the worker receives an isolated snapshot."""
    from .layout_eco_hierarchy import inventory
    from .analog_constraints import findings
    from .physical import connectivity
    report = inventory(project, cid)
    constraints, connections = [], []
    for cell in report['cells']:
        constraints.extend(findings(project, cell))
        connections.extend(connectivity(project, cell)['issues'])
    return dict(inventory=report, constraints=constraints, connections=connections)


class DesignWorkflow(QWidget):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio=studio;self.identity=None;self.analysis_key=None;self.analysis=None
        self.future=None;self.future_key=None;self.preferred={};self.cid=None;self.bench=None
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='studio-workflow')
        self.stopped=False;self.finding_rows=[]
        root=QVBoxLayout(self);self.note=QLabel();self.note.setWordWrap(True);root.addWidget(self.note)
        row=QHBoxLayout();row.addWidget(QLabel('Saved testbench'))
        self.testbench=QComboBox();self.testbench.setAccessibleName('Workflow testbench');row.addWidget(self.testbench,1)
        self.corner=QLabel();row.addWidget(self.corner);root.addLayout(row)
        self.testbench.currentIndexChanged.connect(self.choose_testbench)
        self.next_action=QPushButton('Checking design…');self.next_action.setProperty('role','primary');root.addWidget(self.next_action)
        self.next_action.clicked.connect(lambda:self.call(self.next_fn))
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setAccessibleName('Design progress');root.addWidget(self.summary)
        self.tabs=QTabWidget();self.tabs.setMinimumHeight(170);root.addWidget(self.tabs,1)
        self.steps=QTableWidget(6,3);self.steps.setHorizontalHeaderLabels(['Step','Current state','Action'])
        self.steps.setAccessibleName('Design workflow steps');self.steps.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.steps.horizontalHeader().setStretchLastSection(False)
        self.steps.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeToContents)
        self.steps.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        self.steps.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeToContents)
        self.steps.verticalHeader().hide();self.tabs.addTab(self.steps,'Steps')
        self.finding_table=QTableWidget(0,3);self.finding_table.setHorizontalHeaderLabels(['State','Object','Details'])
        self.finding_table.setAccessibleName('Actionable design findings');self.finding_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.finding_table.setSelectionBehavior(QAbstractItemView.SelectRows);self.finding_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.finding_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch)
        self.finding_table.cellDoubleClicked.connect(lambda *_:self.call(self.go_to_finding))
        self.tabs.addTab(self.finding_table,'Findings')
        self.values=QTableWidget(0,5);self.values.setHorizontalHeaderLabels(['Measurement','Schematic','Post-layout','Change','Unit'])
        self.values.setEditTriggers(QAbstractItemView.NoEditTriggers);self.values.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.tabs.addTab(self.values,'Physical comparison')
        row=QHBoxLayout()
        for title,fn in [('Go to finding',self.go_to_finding),('Place missing devices',lambda:self.circuit_action(studio.place_schematic_in_layout)),('Verification results',studio.open_silicon)]:
            button=QPushButton(title);button.clicked.connect(lambda _=False,fn=fn:self.call(fn));row.addWidget(button)
        root.addLayout(row)
        self.timer=QTimer(self);self.timer.setInterval(250);self.timer.timeout.connect(self.mark_changed);self.timer.start()
        self.refresh()

    def stop(self, *_):
        if not self.stopped:
            self.stopped=True;self.timer.stop();self.executor.shutdown(wait=False,cancel_futures=True)

    def closeEvent(self,event):
        if hasattr(self,'dock'):self.dock.hide()
        super().closeEvent(event)

    def showEvent(self,event):
        super().showEvent(event)
        if hasattr(self,'timer') and not self.stopped:self.refresh()

    def go_to_finding(self):
        if self.analysis_key!=(id(self.studio.project),self.studio.project['revision'],self.cid):
            raise ValueError('The design changed. Wait for refreshed findings before navigating.')
        index=self.finding_table.currentRow()
        if index<0:raise ValueError('Select a row in Findings first.')
        row=self.finding_rows[index];s=self.studio
        if not s.flush_inspector():return
        if self.analysis_key!=(id(s.project),s.project['revision'],self.cid):
            raise ValueError('The design changed. Wait for refreshed findings before navigating.')
        cid=row.get('cell_id',self.cid);cell=next(c for c in s.project['cells'] if c['id']==cid)
        ids=row.get('objects') or [row.get('device_id') or row.get('object')]
        schematic=bool(set(ids)&{d['id'] for d in cell['devices']})
        known={o['id'] for field in ('devices','wires','labels','annotations','shapes','layout_instances','layout_pins') for o in cell.get(field,[])}
        s.cancel_tool();s.cid=cid;s.selection=[];s.mode_combo.setCurrentIndex(0 if schematic else 1);s.refresh(True)
        s.select([key for key in ids if key in known],'schematic' if schematic else 'layout')
        s.statusBar().showMessage(row.get('detail',row.get('message','')),10000)

    def call(self,fn):
        try:return fn()
        except Exception as exc:self.note.setText(str(exc))

    def state_key(self):
        s=self.studio
        return (id(s.project),s.project['id'],s.project['revision'],s.cid,s._selected_testbench,
                tuple((r['id'],r['state'],id(r.get('result'))) for r in s.run_manager.rows))

    def choose_testbench(self):
        s=self.studio;key=self.testbench.currentData()
        s._selected_testbench=key
        if key:
            s.testbench_combo.setCurrentIndex(s.testbench_combo.findData(key))
        if self.cid:self.preferred[(s.project['id'],self.cid)]=key
        self.refresh()

    def select_context(self):
        s=self.studio;p=s.project
        benches=[t for t in p.get('testbenches',[]) if s.cid in (t['dut_cell'],t['bench_cell'])]
        keys={t['id'] for t in benches};remembered=self.preferred.get((p['id'],s.cid))
        selected=s._selected_testbench if s._selected_testbench in keys else remembered
        if selected not in keys:selected=benches[0]['id'] if len(benches)==1 else None
        self.bench=next((t for t in benches if t['id']==selected),None)
        self.cid=self.bench['dut_cell'] if self.bench else s.cid
        self.testbench.blockSignals(True);self.testbench.clear();self.testbench.addItem('Choose a testbench…' if benches else 'No saved testbench for this cell',None)
        for t in benches:self.testbench.addItem(t['name'],t['id'])
        self.testbench.setCurrentIndex(max(0,self.testbench.findData(selected)));self.testbench.blockSignals(False)
        if self.bench:self.preferred[(p['id'],self.cid)]=selected
        settings=self.bench.get('analysis',{}) if self.bench else {}
        self.corner.setText(('Corner: '+str(settings.get('corner','nominal'))+' · '+str(settings.get('temperature',27))+' °C') if self.bench else '')

    def mark_changed(self):
        if not self.isVisible():return
        if self.future and self.future.done():
            future,key=self.future,self.future_key;self.future=None
            try:
                result=future.result()
                if key==(id(self.studio.project),self.studio.project['revision'],self.cid):
                    self.analysis=result;self.analysis_key=key
            except Exception as exc:
                if key==(id(self.studio.project),self.studio.project['revision'],self.cid):
                    self.analysis={'error':str(exc)};self.analysis_key=key
            self.refresh();return
        if self.identity!=self.state_key():self.refresh()
        elif not self.analysis and not self.future:self.refresh()

    def refresh(self):
        if self.stopped:return
        s=self.studio;p=s.project;self.select_context();self.identity=self.state_key()
        key=(id(p),p['revision'],self.cid)
        if key!=self.analysis_key:self.analysis=None
        editing=getattr(s,'_inspector_dirty',False) or any(
            c.anchor is not None or c.drawing or c._rect_pending or c.moving or c.wire_points or c.wire_drag or c.placement
            for c in (s.schematic,s.layout))
        if self.analysis is None and self.future is None and not editing:
            self.future_key=key;self.future=self.executor.submit(inspect_project,clone(p),self.cid)
        self.render()

    def circuit_action(self,fn):
        s=self.studio
        if not s.flush_inspector():return
        if self.bench:s._selected_testbench=self.bench['id']
        s.cid=self.cid;s.selection=[];s.refresh(True)
        return fn()

    def render(self):
        s=self.studio;p=s.project;bench=self.bench;cid=self.cid
        cell=next(c for c in p['cells'] if c['id']==cid)
        data=self.analysis or {};pending=self.analysis is None;error=data.get('error')
        changes=[r for r in data.get('inventory',{}).get('devices',[]) if r['status'] not in ('current','external')]
        connections=data.get('connections',[]);constraints=data.get('constraints',[])
        missing=sum(r['status']=='missing' for r in changes);unsupported=sum(r['status']=='unsupported' for r in changes)
        self.summary.setText('Checking design…' if pending else error or f'{missing} missing devices · {unsupported} unsupported · {len(connections)} connection findings · {len(constraints)} matching findings')
        self.finding_rows=changes+connections+constraints
        selected=self.finding_table.currentRow();self.finding_table.setRowCount(len(self.finding_rows))
        for i,row in enumerate(self.finding_rows):
            for col,text in enumerate([row.get('status',row.get('code','Finding')),row.get('cell','')+' / '+row.get('name',row.get('object','')),row.get('detail',row.get('message',''))]):
                item=QTableWidgetItem(text);item.setToolTip(text);self.finding_table.setItem(i,col,item)
        if self.finding_rows:self.finding_table.selectRow(max(0,min(selected,len(self.finding_rows)-1)))
        self.tabs.setTabText(1,f'Findings ({len(self.finding_rows)})')
        run=next((r for r in reversed(s.run_manager.rows) if bench and r.get('job',{}).get('settings',{}).get('testbench')==bench['id'] and
                  r.get('result',{}).get('project_id')==p['id'] and r['result'].get('silicon_report',{}).get('cell_id')==cid),None)
        result=run['result'] if run else None;report=result.get('silicon_report',{}) if result else {}
        current_hash=data.get('inventory',{}).get('design_hash')
        stale=bool(result and result['design_hash']!=current_hash)
        status='Choose a testbench' if not bench else 'Not run' if not result else ('Checking revision · ' if pending else 'Stale · ' if stale else '')+report.get('status','unknown').title()
        unknown='Checking…' if pending else 'Inspection needs attention' if error else None
        review=lambda:self.circuit_action(s.layout_eco_dialog)
        verify=lambda:self.circuit_action(s.run_silicon)
        steps=[('1. Electrical tests',bench['name'] if bench else 'Choose or save a fixture and measurement limits','Choose tests',lambda:self.circuit_action(s.open_testbenches)),
            ('2. Schematic → layout',unknown or (str(len(changes))+' devices need review' if changes else 'All device links current'),'Review changes',review),
            ('3. Connections and matching',unknown or f'{len(connections)} connection findings; {len(constraints)} constraint findings','Inspect connections',lambda:self.circuit_action(s.check_linked_layout)),
            ('4. DRC, LVS and extraction',status,'Verify selected testbench',verify),
            ('5. Specifications and corners','Run saved tests across operating conditions','Open test plans',s.test_plan_window),
            ('6. Team review','Discuss an exact checkpoint and its verification results','Open collaboration',s.collaboration_dashboard)]
        for row,(title,state,label,fn) in enumerate(steps):
            self.steps.setItem(row,0,QTableWidgetItem(title));self.steps.setItem(row,1,QTableWidgetItem(state))
            button=QPushButton(label);button.clicked.connect(lambda _=False,fn=fn:self.call(fn));self.steps.setCellWidget(row,2,button)
            self.steps.setRowHeight(row,max(40,button.sizeHint().height()+6))
            if row==3:button.setEnabled(bool(bench) and not pending and not error)
        if not bench:index=0
        elif pending or error:index=None
        elif changes:index=1
        elif connections or constraints:index=2
        elif not result or stale or report.get('status')!='passed':index=3
        else:index=4
        self.next_fn=steps[index][3] if index is not None else self.refresh
        self.next_action.setText('Next: '+steps[index][2] if index is not None else 'Checking design…' if pending else 'Retry design checks')
        self.next_action.setEnabled(index is not None or bool(error))
        values=report.get('comparison',[]);self.values.setRowCount(len(values))
        for row,m in enumerate(values):
            for col,v in enumerate([m['name'],m['before'],m['after'],m['delta'],m['unit']]):
                self.values.setItem(row,col,QTableWidgetItem(f'{v:.6g}' if isinstance(v,(int,float)) else str(v)))
        self.note.setText(cell['name']+' · revision '+str(p['revision'])+'. '+(error or 'Checks update automatically after edits and completed jobs. ')+('Comparison belongs to an older design.' if stale and not pending else ''))


def install(studio):
    guide=DesignWorkflow(studio);studio._design_workflow=guide
    dock=studio.panel('Design workflow','designWorkflow',Qt.BottomDockWidgetArea,guide);guide.dock=dock;studio.workflow_dock=dock
    dock.setAllowedAreas(Qt.AllDockWidgetAreas)
    from .floating_panels import FloatingPanel
    dock._floating_frame=FloatingPanel(dock,dock.titleBarWidget())
    dock.setMinimumHeight(320);studio.tabifyDockWidget(studio.results_dock,dock);dock.raise_()
    studio.resizeDocks([dock],[380],Qt.Vertical)
    studio.restoreDockWidget(dock)
    studio.set_panel_lock(studio._layout_locked)
    def show():
        dock.show();guide.show();dock.raise_();guide.refresh();return guide
    studio.design_workflow=show
    for menu in ('Schematic','Layout'):
        studio.action(studio.task_menus[menu],'Design workflow…',show)
    studio.toolbar.addWidget(studio.button('Workflow',fn=show,tip='Show design progress and actionable findings'))
