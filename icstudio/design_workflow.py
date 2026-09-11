"""One place to advance a saved circuit from schematic changes to team review."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView
from .model import design_digest


class DesignWorkflow(QDialog):
    def __init__(self,studio):
        super().__init__(studio);self.studio=studio;self.identity=None
        self.setWindowTitle('Design workflow');self.resize(840,620)
        root=QVBoxLayout(self);self.note=QLabel();self.note.setWordWrap(True);root.addWidget(self.note)
        self.steps=QTableWidget(0,3);self.steps.setHorizontalHeaderLabels(['Step','Current state','Action']);self.steps.setAccessibleName('Design workflow steps')
        self.steps.setEditTriggers(QAbstractItemView.NoEditTriggers);self.steps.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch);root.addWidget(self.steps,1)
        root.addWidget(QLabel('Latest physical comparison for this circuit'))
        self.values=QTableWidget(0,5);self.values.setHorizontalHeaderLabels(['Measurement','Schematic','Post-layout','Change','Unit']);self.values.setEditTriggers(QAbstractItemView.NoEditTriggers);self.values.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);root.addWidget(self.values)
        row=QHBoxLayout()
        for text,fn in [('Refresh checks',self.refresh),('Open verification results',studio.open_silicon),('Close',self.close)]:
            button=QPushButton(text);button.clicked.connect(lambda _=False,fn=fn:self.call(fn));row.addWidget(button)
        root.addLayout(row);self.timer=QTimer(self);self.timer.setInterval(400);self.timer.timeout.connect(self.mark_changed);self.timer.start();self.refresh()

    def call(self,fn):
        try:return fn()
        except Exception as exc:self.note.setText(str(exc))

    def mark_changed(self):
        if not self.isVisible():return
        s=self.studio
        if self.identity!=(s.project['id'],s.project['revision'],s.cid):
            self.note.setText('The design or selected cell changed. Refresh checks before using the states below.')
            for row in range(self.steps.rowCount()):self.steps.item(row,1).setText('Refresh required')

    def refresh(self):
        s=self.studio;p=s.project;cid=s.cid;self.identity=(p['id'],p['revision'],cid)
        from .layout_eco import inventory
        from .analog_constraints import findings
        bench=next((t for t in p.get('testbenches',[]) if cid in (t['dut_cell'],t['bench_cell'])),None)
        if bench:s._selected_testbench=bench['id'];cid=bench['dut_cell']
        c=next(c for c in p['cells'] if c['id']==cid)
        inv=inventory(p,cid);changed=[r for r in inv['devices'] if r['status']!='current'];constraints=findings(p,cid)
        def circuit(fn):
            if not s.flush_inspector():return
            s.cid=cid;s.selection=[];s.mode_combo.setCurrentIndex(1);s.refresh(True);return fn()
        result=next((row.get('result') for row in reversed(s.run_manager.rows) if row.get('result',{}).get('silicon_report',{}).get('cell_id')==cid and row['result'].get('project_id')==p['id']),None)
        stale=bool(result and result['design_hash']!=design_digest(p));report=result.get('silicon_report',{}) if result else {}
        status='Not run' if not result else ('Stale · ' if stale else '')+report.get('status','unknown').title()
        steps=[('1. Electrical tests',bench['name'] if bench else 'Save a fixture and measurement limits','Choose tests',s.open_testbenches),
            ('2. Schematic → layout',str(len(changed))+' missing, changed, or unsupported devices' if changed else 'All device links current','Review changes',lambda:circuit(s.layout_eco_dialog)),
            ('3. Connections and matching',f"{len(inv['connectivity'])} connection findings; {len(constraints)} constraint findings",'Inspect connections',lambda:circuit(s.check_linked_layout)),
            ('4. DRC, LVS and extraction',status,'Verify saved testbench',s.run_silicon),
            ('5. Specifications and corners','Compare requirements across saved tests and operating conditions','Open test plans',s.test_plan_window),
            ('6. Team review','Save a checkpoint, discuss objects, and share the verified inputs','Open collaboration',s.collaboration_dashboard)]
        self.steps.setRowCount(len(steps))
        for row,(title,state,label,fn) in enumerate(steps):
            self.steps.setItem(row,0,QTableWidgetItem(title));self.steps.setItem(row,1,QTableWidgetItem(state))
            button=QPushButton(label);button.clicked.connect(lambda _=False,fn=fn:self.call(fn));self.steps.setCellWidget(row,2,button)
        values=report.get('comparison',[]);self.values.setRowCount(len(values))
        for row,m in enumerate(values):
            for col,v in enumerate([m['name'],m['before'],m['after'],m['delta'],m['unit']]):self.values.setItem(row,col,QTableWidgetItem(f'{v:.6g}' if isinstance(v,(int,float)) else str(v)))
        self.note.setText(c['name']+' · revision '+str(p['revision'])+'. Complete each check after an electrical or layout change. '+('Comparison belongs to an older design.' if stale else ''))


def install(studio):
    def show():
        old=getattr(studio,'_design_workflow',None)
        if old:old.close()
        studio._design_workflow=DesignWorkflow(studio);studio._design_workflow.show();return studio._design_workflow
    studio.design_workflow=show
    studio.action(studio.task_menus['Layout'],'Design workflow…',show)
