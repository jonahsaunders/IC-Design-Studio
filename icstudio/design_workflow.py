"""A shared, automatically refreshed circuit workflow for both editors."""
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import Qt, QTimer, QEvent, QRect
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QTabWidget,
    QSizePolicy)
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
    from .qualification import project_status
    return dict(inventory=report, constraints=constraints, connections=connections,
                reference=project_status(project))


class DesignWorkflow(QWidget):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio=studio;self.identity=None;self.analysis_key=None;self.analysis=None
        self.future=None;self.future_key=None;self.preferred={};self.cid=None;self.bench=None
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='studio-workflow')
        self.stopped=False;self.finding_rows=[]
        root=QVBoxLayout(self);self.note=QLabel();self.note.setWordWrap(True);root.addWidget(self.note)
        context=QFormLayout();context.setRowWrapPolicy(QFormLayout.WrapLongRows);context.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.testbench=QComboBox();self.testbench.setAccessibleName('Workflow testbench');context.addRow('Saved testbench',self.testbench)
        self.testbench.currentIndexChanged.connect(self.choose_testbench)
        self.plan=QComboBox();self.plan.setAccessibleName('Workflow verification plan');context.addRow('Verification plan',self.plan);root.addLayout(context)
        for choice in (self.testbench,self.plan):
            choice.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);choice.setMinimumContentsLength(16)
            choice.currentTextChanged.connect(choice.setToolTip)
        self.plan.currentIndexChanged.connect(self.refresh)
        self.corner=QLabel();self.corner.setWordWrap(True);root.addWidget(self.corner);self.corner.hide()
        self.next_action=QPushButton('Checking design…');self.next_action.setProperty('role','primary');root.addWidget(self.next_action)
        self.next_action.clicked.connect(lambda:self.call(self.next_fn))
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setAccessibleName('Design progress');root.addWidget(self.summary)
        for text in (self.note,self.summary):text.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        self.section_picker=QComboBox();self.section_picker.setAccessibleName('Workflow section');root.addWidget(self.section_picker);self.section_picker.hide()
        self.tabs=QTabWidget();self.tabs.setMinimumHeight(170);root.addWidget(self.tabs,1)
        self.tabs.tabBar().setElideMode(Qt.ElideNone);self.tabs.tabBar().setExpanding(False)
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
        from PySide6.QtWidgets import QTextBrowser
        self.reference=QTextBrowser();self.reference.setAccessibleName('Archived reference qualification')
        self.tabs.addTab(self.reference,'Reference evidence')
        for index in range(self.tabs.count()):self.section_picker.addItem(self.tabs.tabText(index))
        self.section_picker.currentIndexChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.section_picker.setCurrentIndex)
        from .analog_widgets import actions
        self.action_host=QWidget();action_layout=QVBoxLayout(self.action_host);action_layout.setContentsMargins(0,0,0,0)
        self.finding_actions=actions(action_layout,[('Go to finding',self.go_to_finding),('Place missing devices',lambda:self.circuit_action(studio.place_schematic_in_layout)),('Verification results',studio.open_silicon)],self.call)
        self.action_flow=action_layout.itemAt(0).layout();root.addWidget(self.action_host)
        self.timer=QTimer(self);self.timer.setInterval(250);self.timer.timeout.connect(self.mark_changed);self.timer.start()
        self.refresh()

    def reflow(self):
        """Keep complete status text and section names on a narrow scaled screen."""
        if not hasattr(self,'section_picker') or not hasattr(self,'tabs'):return
        margins=self.layout().contentsMargins();width=max(1,self.width()-margins.left()-margins.right())
        for text in (self.note,self.summary):
            # QLabel.heightForWidth includes its current minimum height. Measure
            # the text directly so widening a dock can shrink an earlier wrap.
            metrics=text.fontMetrics();height=max(metrics.height(),metrics.boundingRect(QRect(0,0,width,16777215),Qt.TextWordWrap,text.text()).height())
            if text.minimumHeight()!=height or text.maximumHeight()!=height:text.setFixedHeight(height)
        if hasattr(self,'action_flow'):
            height=self.action_flow.heightForWidth(width)
            if self.action_host.height()!=height:self.action_host.setFixedHeight(height)
        compact=self.tabs.tabBar().sizeHint().width()>width
        self.tabs.tabBar().setVisible(not compact);self.section_picker.setVisible(compact)
        # The dock's scroll area can grow the content vertically. Reserve the
        # complete wrapped form and action rows instead of compressing labels
        # or drawing the actions over the findings table.
        height=self.layout().totalHeightForWidth(self.width())
        if height>0 and self.minimumHeight()!=height:self.setMinimumHeight(height)

    def resizeEvent(self,event):
        super().resizeEvent(event);self.reflow()

    def event(self,event):
        result=super().event(event)
        if event.type() in (QEvent.FontChange,QEvent.StyleChange,QEvent.LayoutRequest):self.reflow()
        return result

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
        self.testbench.setToolTip(self.testbench.currentText())
        if self.bench:self.preferred[(p['id'],self.cid)]=selected
        settings=self.bench.get('analysis',{}) if self.bench else {}
        self.corner.setText(('Corner: '+str(settings.get('corner','nominal'))+' · '+str(settings.get('temperature',27))+' °C') if self.bench else '')
        self.corner.setVisible(bool(self.bench))
        selected_plan=self.plan.currentData();self.plan.blockSignals(True);self.plan.clear()
        plans=[plan for plan in p.get('test_plans',[]) if self.bench and any(
            e.get('settings',{}).get('testbench')==self.bench['id'] or e.get('cell') in (self.bench['dut_cell'],self.bench['bench_cell'])
            for e in plan.get('entries',[]))]
        self.plan.addItem('Choose a verification plan…' if plans else 'No verification plan for this testbench',None)
        for plan in plans:self.plan.addItem(plan['name'],plan['id'])
        index=self.plan.findData(selected_plan)
        self.plan.setCurrentIndex(index if index>0 else 1 if len(plans)==1 else 0);self.plan.blockSignals(False)
        self.plan.setToolTip(self.plan.currentText())

    def inspect_evidence(self,status):
        row=next((r for r in self.studio.run_manager.rows if r['id']==status.get('run_id')),None)
        if row is None:return self.open_plan_evidence()
        from .analog_run_ui import RunInspector
        self.inspector=RunInspector(self.studio,row);self.inspector.note.setText(status['detail']);self.inspector.show()
        requirement=status.get('requirement')
        if requirement:
            for index,definition in enumerate(self.inspector.requirement_rows):
                if definition['name']==requirement:
                    self.inspector.requirements.setCurrentCell(index,1)
                    self.inspector.focus_requirement(definition);break

    def open_plan_evidence(self):
        window=self.studio.test_plan_window();window.refresh_plans(self.plan.currentData())
        status=getattr(self,'plan_state',{})
        group=window.runs.findData(status.get('group'))
        if group>=0:window.runs.setCurrentIndex(group)
        window.failed.setChecked(status.get('status')=='Failed')
        requirement=status.get('requirement')
        if requirement:
            for row in range(window.table.rowCount()):
                if window.table.item(row,1).text()==requirement:
                    column=next((col for col in range(2,window.table.columnCount())
                                 if window.table.item(row,col).data(Qt.UserRole)==status.get('run_id')),2)
                    window.table.setCurrentCell(row,column);break
        return window

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
        from .qualification import markdown
        self.reference.setMarkdown(markdown(data.get('reference')) or 'No archived reference evidence is attached to this document. Current run results appear in Steps.')
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
        self.section_picker.setItemText(1,self.tabs.tabText(1))
        current_hash=data.get('inventory',{}).get('design_hash')
        from .workflow_status import bench_status,plan_status,state
        unknown_state=state('Running','Checking current design') if pending else state('Blocked',error) if error else None
        electrical=unknown_state or bench_status(p,bench,s.run_manager.rows,current_hash)
        physical=unknown_state or bench_status(p,bench,s.run_manager.rows,current_hash,physical=True)
        plan=next((v for v in p.get('test_plans',[]) if v['id']==self.plan.currentData()),None)
        self.plan_state=unknown_state or plan_status(p,plan,s.run_manager.rows,current_hash)
        self.evidence_states={'electrical':electrical,'physical':physical,'plan':self.plan_state}
        run=next((r for r in s.run_manager.rows if r['id']==physical.get('run_id')),None)
        report=(run.get('result') or {}).get('silicon_report',{}) if run else {}
        stale=physical['status']=='Stale'
        describe=lambda value:value['status']+' · '+value['detail']
        unknown='Checking…' if pending else 'Inspection needs attention' if error else None
        review=lambda:self.circuit_action(s.layout_eco_dialog)
        verify=lambda:self.circuit_action(s.run_silicon)
        electrical_action=(lambda:self.circuit_action(s.open_testbenches)) if bench is None else (lambda:self.inspect_evidence(electrical)) if electrical.get('run_id') and electrical['status'] not in ('Stale',) else (lambda:self.circuit_action(s.run_testbench))
        steps=[('1. Electrical tests',describe(electrical),'Choose tests' if bench is None else 'Inspect electrical run' if electrical.get('run_id') and electrical['status']!='Stale' else 'Run saved testbench',electrical_action),
            ('2. Schematic → layout',unknown or ('Blocked · ' if unsupported else 'Not run · ' if changes else 'Passed · ')+(str(len(changes))+' devices need review' if changes else 'All device links current'),'Review changes',review),
            ('3. Connections and matching',unknown or ('Failed · ' if connections or constraints else 'Passed · ')+f'{len(connections)} connection findings; {len(constraints)} constraint findings','Inspect connections',lambda:self.circuit_action(s.check_linked_layout)),
            ('4. DRC, LVS and extraction',describe(physical),'Inspect physical run' if physical.get('run_id') and physical['status'] not in ('Stale',) else 'Verify selected testbench',(lambda:self.inspect_evidence(physical)) if physical.get('run_id') and physical['status']!='Stale' else verify),
            ('5. Specifications and corners',describe(self.plan_state),'Open plan evidence',self.open_plan_evidence),
            ('6. Team review','Optional · discuss an exact checkpoint and its verification results','Open collaboration',s.collaboration_dashboard)]
        for row,(title,state,label,fn) in enumerate(steps):
            self.steps.setItem(row,0,QTableWidgetItem(title));self.steps.setItem(row,1,QTableWidgetItem(state))
            button=QPushButton(label);button.clicked.connect(lambda _=False,fn=fn:self.call(fn));action_widget=button
            self.steps.setRowHeight(row,max(40,button.sizeHint().height()+6))
            if row==3:button.setEnabled(bool(bench) and not pending and not error)
            evidence=electrical if row==0 else physical if row==3 else None
            if bench and evidence and evidence.get('run_id') and evidence['status'] in ('Failed','Blocked'):
                actions=QWidget();buttons=QHBoxLayout(actions);buttons.setContentsMargins(0,0,0,0);buttons.addWidget(button)
                retry=QPushButton('Rerun');retry.setAccessibleName('Rerun electrical tests' if row==0 else 'Rerun physical verification')
                fn=(lambda:self.circuit_action(s.run_testbench)) if row==0 else verify
                retry.clicked.connect(lambda _=False,fn=fn:self.call(fn));buttons.addWidget(retry)
                action_widget=actions
            self.steps.setCellWidget(row,2,action_widget)
        if not bench:index=0
        elif pending or error:index=None
        elif electrical['status']!='Passed':index=0
        elif changes:index=1
        elif connections or constraints:index=2
        elif physical['status']!='Passed':index=3
        elif self.plan_state['status']!='Passed':index=4
        else:index=5
        self.next_fn=steps[index][3] if index is not None else self.refresh
        self.next_action.setText('Verification complete · optional team review' if index==5 else 'Next: '+steps[index][2] if index is not None else 'Checking design…' if pending else 'Retry design checks')
        self.next_action.setEnabled(index is not None or bool(error))
        values=report.get('comparison',[]);self.values.setRowCount(len(values))
        for row,m in enumerate(values):
            for col,v in enumerate([m['name'],m['before'],m['after'],m['delta'],m['unit']]):
                self.values.setItem(row,col,QTableWidgetItem(f'{v:.6g}' if isinstance(v,(int,float)) else str(v)))
        self.note.setText(cell['name']+' · revision '+str(p['revision'])+'. '+(error or 'Checks update automatically after edits and completed jobs. ')+('Comparison belongs to an older design.' if stale and not pending else ''))
        self.reflow()


def install(studio):
    guide=DesignWorkflow(studio);studio._design_workflow=guide
    from .analog_widgets import scroll
    dock=studio.panel('Design workflow','designWorkflow',Qt.BottomDockWidgetArea,scroll(guide));guide.dock=dock;studio.workflow_dock=dock
    dock.setAllowedAreas(Qt.AllDockWidgetAreas)
    from .floating_panels import FloatingPanel
    dock._floating_frame=FloatingPanel(dock,dock.titleBarWidget())
    dock.setMinimumHeight(180)
    # Do not introduce a large visible dock during startup or tabify its minimum
    # size with Results. Saved workspace restoration remains explicit.
    studio.restoreDockWidget(dock);dock.hide()
    close=next(b for b in dock.titleBarWidget().findChildren(QPushButton) if 'Hide' in b.toolTip())
    close.setText('Close');close.setFixedWidth(76);close.setAccessibleName('Close design workflow')
    guide.close_shortcut=QShortcut(QKeySequence('Escape'),guide)
    guide.close_shortcut.setContext(Qt.WidgetWithChildrenShortcut);guide.close_shortcut.activated.connect(dock.hide)
    studio.set_panel_lock(studio._layout_locked)
    def show():
        was_hidden=dock.isHidden();dock.show();guide.show();dock.raise_();guide.refresh()
        if was_hidden and not dock.isFloating():studio.resizeDocks([dock],[max(180,min(300,studio.height()//3))],Qt.Vertical)
        guide.next_action.setFocus();return guide
    studio.design_workflow=show
    studio.action(studio.task_menus['Design'],'Design workflow…',show)
    studio.task_menus['Window'].addAction(dock.toggleViewAction())
    button=studio.button('Workflow',fn=lambda:dock.hide() if not dock.isHidden() else show(),check=True,tip='Show or close design workflow (Escape closes the focused workflow)')
    studio.workflow_button=button;dock.visibilityChanged.connect(lambda _:button.setChecked(not dock.isHidden()))
    studio.toolbar.addWidget(button)
    studio.action(studio.task_menus['View'],'Reset workspace',studio.reset_workspace,'Ctrl+Shift+0')
