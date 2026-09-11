"""A specification-by-condition workspace backed by the existing job scheduler."""
import csv
import io
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QLineEdit,
    QFormLayout, QDialogButtonBox, QFileDialog, QAbstractItemView)
from .model import clone, uid, scalar, atomic_write
from .test_plans import sources, validate_plans, prepare, matrix, compare


class PlanEditor(QDialog):
    def __init__(self, window, plan=None):
        super().__init__(window);self.window=window;self.plan=clone(plan or {});self.identity=window.studio.project['id']
        self.setWindowTitle('Edit test plan' if plan else 'New test plan');self.resize(720,550)
        root=QVBoxLayout(self);form=QFormLayout()
        self.name=QLineEdit(self.plan.get('name','Analog verification'))
        self.corners=QLineEdit(', '.join(self.plan.get('corners',['nominal'])))
        self.temperatures=QLineEdit(', '.join(map(str,self.plan.get('temperatures',[27]))))
        self.voltages=QLineEdit(', '.join(map(str,self.plan.get('voltages',[]))))
        for label,widget in [('Plan name',self.name),('Model corners',self.corners),('Temperatures (°C)',self.temperatures),('Supply voltages (V; optional)',self.voltages)]:
            widget.setAccessibleName(label);form.addRow(label,widget)
        root.addLayout(form)
        self.compare_layout=QCheckBox('Compare schematic and post-layout, including DRC and LVS')
        self.compare_layout.setChecked(self.plan.get('compare_layout',False));root.addWidget(self.compare_layout)
        note=QLabel('Use comma-separated conditions. Choose the tests to run; a voltage sweep requires a DC supply target for each test. Requirements come from the saved testbench or cell.')
        note.setWordWrap(True);root.addWidget(note)
        available=sources(window.studio.project);saved={e['id']:e for e in self.plan.get('entries',[])}
        self.entries=[clone(saved.get(e['id'],e)) for e in available]
        self.entries.extend(clone(e) for key,e in saved.items() if key not in {v['id'] for v in available})
        self.table=QTableWidget(len(self.entries),3);self.table.setHorizontalHeaderLabels(['Run','Test','DC supply target'])
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        from .studies import supply_targets
        for i,e in enumerate(self.entries):
            checked=QTableWidgetItem();checked.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable)
            checked.setCheckState(Qt.Checked if not plan or e['id'] in saved else Qt.Unchecked);self.table.setItem(i,0,checked)
            item=QTableWidgetItem(e['name']);item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable);self.table.setItem(i,1,item)
            targets=supply_targets(window.studio.project,e['cell'])
            default=next((t for t in targets if t.lower().startswith('vdd.')),targets[0] if targets else '')
            self.table.setItem(i,2,QTableWidgetItem(e.get('supply',default)))
        self.table.setAccessibleName('Tests included in plan');root.addWidget(self.table,1)
        self.error=QLabel('');self.error.setWordWrap(True);root.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);root.addWidget(buttons)

    def save(self):
        try:
            studio=self.window.studio
            if studio.project['id']!=self.identity:raise ValueError('The project changed. Open a new plan editor.')
            if self.plan and next((p for p in studio.project.get('test_plans',[]) if p['id']==self.plan['id']),None)!=self.plan:
                raise ValueError('This plan changed or was deleted. Close and reopen its editor before saving.')
            values=lambda w:[s.strip() for s in w.text().split(',') if s.strip()]
            plan=dict(id=self.plan.get('id',uid()),name=self.name.text().strip(),corners=values(self.corners),
                      temperatures=[scalar(v) for v in values(self.temperatures)],voltages=[scalar(v) for v in values(self.voltages)],entries=[],compare_layout=self.compare_layout.isChecked())
            for i,entry in enumerate(self.entries):
                if self.table.item(i,0).checkState()==Qt.Checked:
                    plan['entries'].append(dict(entry,supply=self.table.item(i,2).text().strip()))
            plans=[p for p in studio.project.get('test_plans',[]) if p['id']!=plan['id']]+[plan]
            validate_plans({**studio.project,'test_plans':plans})
            studio.commit(lambda p:p.update(test_plans=clone(plans)),'Save verification test plan')
            self.window.refresh_plans(plan['id']);self.accept()
        except Exception as exc:self.error.setText(str(exc))


class TestPlanWindow(QDialog):
    def __init__(self,studio):
        super().__init__(studio);self.studio=studio;self.project_id=studio.project['id'];self.data=None
        self.setWindowTitle('Verification test plans');self.resize(1000,650)
        root=QVBoxLayout(self);bar=QHBoxLayout();self.plans=QComboBox();self.plans.setAccessibleName('Saved test plan');bar.addWidget(self.plans,1)
        for name,fn in [('New plan…',lambda:self.edit()),('Edit plan…',lambda:self.edit(self.plan())),('Delete plan',self.delete),('Run plan',self.run)]:
            b=QPushButton(name);b.clicked.connect(lambda _=False,fn=fn:self.call(fn));bar.addWidget(b)
        root.addLayout(bar)
        row=QHBoxLayout();self.runs=QComboBox();self.runs.setAccessibleName('Test plan run');self.baseline=QComboBox();self.baseline.setAccessibleName('Baseline run')
        row.addWidget(QLabel('Run'));row.addWidget(self.runs,1);row.addWidget(QLabel('Compare with'));row.addWidget(self.baseline,1);root.addLayout(row)
        self.note=QLabel('Save a testbench or analysis setup, then create a plan. Each cell shows a requirement under one operating condition.')
        self.note.setWordWrap(True);root.addWidget(self.note)
        self.failed=QCheckBox('Show only failures, errors, and regressions');root.addWidget(self.failed)
        self.table=QTableWidget();self.table.setAccessibleName('Specifications by operating condition');self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);root.addWidget(self.table,1)
        actions=QHBoxLayout()
        for name,fn in [('Open selected run',self.open_run),('Retry failed / cancelled',self.retry),('Export CSV…',self.export),('Close',self.close)]:
            b=QPushButton(name);b.clicked.connect(lambda _=False,fn=fn:self.call(fn));actions.addWidget(b)
        root.addLayout(actions)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(180);self.timer.timeout.connect(self.refresh)
        studio.run_manager.changed.connect(self.schedule)
        self.plans.currentIndexChanged.connect(self.refresh);self.runs.currentIndexChanged.connect(self.render);self.baseline.currentIndexChanged.connect(self.render);self.failed.toggled.connect(self.render)
        self.table.cellDoubleClicked.connect(lambda *_:self.call(self.open_run));self.refresh_plans()

    def call(self,fn):
        try:
            if self.studio.project['id']!=self.project_id:raise ValueError('The project changed. Close and reopen Test plans.')
            return fn()
        except Exception as exc:self.note.setText(str(exc))

    def schedule(self):
        if self.isVisible() and not self.timer.isActive():self.timer.start()

    def plan(self):
        p=next((p for p in self.studio.project.get('test_plans',[]) if p['id']==self.plans.currentData()),None)
        if p is None:raise ValueError('Create or select a test plan first.')
        return p

    def refresh_plans(self,selected=None):
        selected=selected or self.plans.currentData();self.plans.blockSignals(True);self.plans.clear()
        for p in self.studio.project.get('test_plans',[]):self.plans.addItem(p['name'],p['id'])
        index=self.plans.findData(selected);self.plans.setCurrentIndex(max(0,index));self.plans.blockSignals(False);self.refresh()

    def edit(self,plan=None):
        if not sources(self.studio.project):raise ValueError('Save a testbench or analysis setup before creating a test plan.')
        self.editor=PlanEditor(self,plan);self.editor.show();return self.editor

    def delete(self):
        key=self.plan()['id']
        self.studio.commit(lambda p:p.update(test_plans=[v for v in p.get('test_plans',[]) if v['id']!=key]),'Delete verification test plan')
        self.refresh_plans()

    def run(self):
        if not self.studio.flush_inspector():return
        jobs=prepare(self.studio.project,self.plan(),self.studio.prepare_simulation)
        names=[j['case']['test_name']+' · '+str(j['case']['labels']) for j in jobs]
        self.studio.run_manager.enqueue_many(jobs,self.studio.jobs_dir,names)
        self.refresh();self.runs.setCurrentIndex(self.runs.count()-1)

    def refresh(self):
        if self.studio.project['id']!=self.project_id:return
        groups={}
        for row in self.studio.run_manager.rows:
            case=row['job'].get('case',{})
            if case.get('kind')=='test_plan' and case.get('plan_id')==self.plans.currentData():groups[case['group']]=case
        for combo,is_baseline in ((self.runs,False),(self.baseline,True)):
            selected=combo.currentData();combo.blockSignals(True);combo.clear()
            if is_baseline:combo.addItem('No baseline',None)
            for i,(key,case) in enumerate(groups.items(),1):combo.addItem(f"Run {i} · {case['base_design_hash'][:8]}",key)
            index=combo.findData(selected);combo.setCurrentIndex(index if index>=0 else (0 if is_baseline else combo.count()-1));combo.blockSignals(False)
        self.render()

    def render(self):
        self.data=matrix(self.studio.run_manager.rows,self.runs.currentData())
        if self.baseline.currentData():self.data=compare(self.data,matrix(self.studio.run_manager.rows,self.baseline.currentData()))
        rows=self.data['rows'];conditions=self.data['conditions']
        if self.failed.isChecked():rows=[r for r in rows if any(v['status'] in ('FAIL','ERROR','CANCELLED') or v.get('regressed') for v in r['values'].values())]
        self.table.setColumnCount(2+len(conditions));self.table.setHorizontalHeaderLabels(['Test','Requirement']+[f'{c} / {t:g} °C'+(f' / {v:g} V' if v is not None else '') for c,t,v in conditions]);self.table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            self.table.setItem(i,0,QTableWidgetItem(row['test']));self.table.setItem(i,1,QTableWidgetItem(row['name']))
            for j,condition in enumerate(conditions,2):
                cell=row['values'].get(condition,{});value=cell.get('value');text=cell.get('status','NOT RUN')
                if value is not None:text+=f' · {value:.6g} {row["unit"]}'
                if 'delta' in cell:text+=f' · Δ {cell["delta"]:+.4g}'
                item=QTableWidgetItem(text);item.setData(Qt.UserRole,cell.get('run_id'));item.setToolTip(str(row['definition'])+'\n'+str(cell.get('detail',''))+'\nMargin: '+str(cell.get('margin')))
                if cell.get('status') in ('FAIL','ERROR'):item.setForeground(QColor('#d35c54'))
                elif cell.get('status')=='PASS':item.setForeground(QColor('#31936c'))
                self.table.setItem(i,j,item)
        if self.data['rows']:
            cells=[v for r in self.data['rows'] for v in r['values'].values()]
            self.note.setText(f"{len(self.data['rows'])} requirements · {sum(v['status']=='PASS' for v in cells)} passed · {sum(v['status'] in ('FAIL','ERROR') for v in cells)} failed/error. Values belong to the run's saved revision. Baseline deltas require identical requirements and conditions.")

    def open_run(self):
        item=self.table.currentItem();key=item.data(Qt.UserRole) if item else None
        row=next((r for r in self.studio.run_manager.rows if r['id']==key),None)
        if row is None:raise ValueError('Select a condition result in the matrix.')
        self.studio.open_simulation_explorer();self.studio.simulation_runs.selectRow(self.studio.run_manager.rows.index(row));self.studio.show_run_details();self.studio.open_selected_run()
        if row.get('result',{}).get('silicon_report'):
            self.studio._silicon_result=row['result'];self.studio.open_silicon()

    def retry(self):
        latest={}
        for row in self.studio.run_manager.rows:
            case=row['job'].get('case',{})
            if case.get('group')==self.runs.currentData():latest[case['index']]=row
        rows=[r for r in latest.values() if r['state'] in ('Failed','Cancelled')]
        if not rows:raise ValueError('This run has no failed or cancelled jobs to retry.')
        self.studio.run_manager.enqueue_many([clone(r['job']) for r in rows],self.studio.jobs_dir,[r['name']+' · retry' for r in rows])

    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'Export test plan matrix','test-plan.csv','CSV (*.csv)')
        if not path:return
        stream=io.StringIO();writer=csv.writer(stream);writer.writerow(['test','requirement','corner','temperature_C','voltage_V','status','value','unit','margin','baseline','delta','run_id'])
        for row in self.data['rows']:
            for condition,cell in row['values'].items():writer.writerow([row['test'],row['name'],*condition,cell['status'],cell['value'],row['unit'],cell['margin'],cell.get('baseline',''),cell.get('delta',''),cell['run_id']])
        atomic_write(path,stream.getvalue())


def install(studio):
    def show():
        old=getattr(studio,'_test_plan_window',None)
        if old:old.close()
        studio._test_plan_window=TestPlanWindow(studio);studio._test_plan_window.show();return studio._test_plan_window
    studio.test_plan_window=show
    studio.action(studio.task_menus['Simulate'],'Verification test plans…',show)
