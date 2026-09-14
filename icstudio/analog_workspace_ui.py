"""Analog workspace UI backed by the existing document and job lifecycles."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTabWidget,
    QComboBox,QTableWidget,QTableWidgetItem,QAbstractItemView,QPlainTextEdit,QHeaderView)
from .model import clone
from .test_plan_ui import TestPlanWindow
from .analog_workspace import assignments


def table(headers,editable=False):
    widget=QTableWidget(0,len(headers));widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.AllEditTriggers if editable else QAbstractItemView.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows);widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    return widget


def fill(widget,rows):
    widget.setRowCount(len(rows))
    for i,row in enumerate(rows):
        for j,value in enumerate(row):widget.setItem(i,j,QTableWidgetItem('—' if value is None else str(value)))


class AnalogWorkspace(TestPlanWindow):
    def __init__(self,studio):
        super().__init__(studio);self.setWindowTitle('Analog design workspace');self.resize(1180,800)
        results=QWidget();results.setLayout(self.layout());root=QVBoxLayout(self)
        self.tabs=QTabWidget();root.addWidget(self.tabs)
        self.setup=QWidget();self.tabs.addTab(self.setup,'Setup');self.tabs.addTab(results,'Results matrix')
        self.layout_page=QWidget();self.tabs.addTab(self.layout_page,'Layout and constraints')
        self.verification_page=QWidget();self.tabs.addTab(self.verification_page,'Verification runs')
        self.workspace_note=QLabel();self.workspace_note.setWordWrap(True);root.addWidget(self.workspace_note)
        self.build_setup();self.build_layout();self.build_verification()
        self.tabs.currentChanged.connect(self.page_changed);self.reload_setup();self.refresh_layout();self.refresh_verification()

    def call(self,fn):
        try:
            if self.studio.project['id']!=self.project_id:raise ValueError('The project changed. Reopen the analog workspace.')
            return fn()
        except Exception as exc:
            (self.workspace_note if hasattr(self,'workspace_note') else self.note).setText(str(exc))

    def buttons(self,layout,items):
        row=QHBoxLayout()
        for title,fn in items:
            button=QPushButton(title);button.clicked.connect(lambda _=False,fn=fn:self.call(fn));row.addWidget(button)
        layout.addLayout(row)

    def build_setup(self):
        layout=QVBoxLayout(self.setup)
        note=QLabel('Save design variables and measurement limits here. Add analyses or testbenches, then create a PVT plan in Results matrix. Each run retains its circuit and requirements.');note.setWordWrap(True);layout.addWidget(note)
        self.scope=QComboBox();self.scope.setAccessibleName('Analog requirement owner');layout.addWidget(self.scope)
        self.variables=QPlainTextEdit();self.variables.setMaximumHeight(110);self.variables.setAccessibleName('Project design variables');self.variables.setPlaceholderText('bias = 1.2\nload = 10k');layout.addWidget(QLabel('Project design variables · name = value'));layout.addWidget(self.variables)
        self.specs=table(['Name','Expression','Minimum','Maximum','Unit'],True);self.specs.setAccessibleName('Analog measurement limits');layout.addWidget(self.specs,1)
        self.buttons(layout,[('Add measurement',self.add_requirement),('Remove measurement',lambda:self.specs.removeRow(self.specs.currentRow())),('Save variables and limits',self.save_setup),('Reload setup',self.reload_setup)])
        self.analyses=table(['Analysis / testbench','Cell','Engine','Type']);layout.addWidget(self.analyses,1)
        self.buttons(layout,[('Save current analysis',self.new_analysis),('Edit analysis…',self.edit_analysis),('Testbench editor…',self.studio.edit_testbench),('New PVT plan…',self.new_plan)])
        self.scope.currentIndexChanged.connect(self.change_scope)
        self._scope_drafts={};self._loaded_scope=None

    def raw_specs(self):
        keys=('name','expression','min','max','unit')
        return [{k:self.specs.item(i,j).text().strip() if self.specs.item(i,j) else '' for j,k in enumerate(keys)} for i in range(self.specs.rowCount())]

    def owner(self,key=None):
        group,ident=key or self.scope.currentData()
        return next(c for c in self.studio.project[group] if c['id']==ident)

    def change_scope(self,*_):
        if self._loaded_scope:self._scope_drafts[self._loaded_scope]=(self.raw_specs(),self._source_specs)
        self._loaded_scope=self.scope.currentData()
        if not self._loaded_scope:return
        source=clone(self.owner().get('specifications',[]))
        rows,self._source_specs=self._scope_drafts.get(self._loaded_scope,(source,source))
        fill(self.specs,[[r.get(k,'') for k in ('name','expression','min','max','unit')] for r in rows])

    def reload_setup(self):
        self._scope_drafts={};self._loaded_scope=None
        self._source_variables=clone(self.studio.project.get('parameters',{}))
        self.variables.setPlainText('\n'.join(k+' = '+str(v) for k,v in self._source_variables.items()))
        old=self.scope.currentData();self.scope.blockSignals(True);self.scope.clear()
        for group,title in (('cells','Cell'),('testbenches','Testbench')):
            for c in self.studio.project.get(group,[]):self.scope.addItem(title+' · '+c['name'],(group,c['id']))
        index=self.scope.findData(old or ('cells',self.studio.cid));self.scope.setCurrentIndex(max(0,index));self.scope.blockSignals(False);self.change_scope()
        self.refresh_sources();self.workspace_note.setText('Setup loaded. Unsaved edits stay in this window until saved or reloaded.')

    def refresh_sources(self):
        from .test_plans import sources
        self.source_rows=[s for s in sources(self.studio.project) if s['engine']!='digital']
        by={c['id']:c['name'] for c in self.studio.project['cells']}
        fill(self.analyses,[[s['name'],by[s['cell']],s['engine'],s['settings']['type']] for s in self.source_rows])

    def add_requirement(self):
        i=self.specs.rowCount();self.specs.insertRow(i)
        for j,text in enumerate(('Output '+str(i+1),'final(V("out"))','0','','V')):self.specs.setItem(i,j,QTableWidgetItem(text))

    def save_setup(self):
        from .specifications import validate_rows
        from .model import validate
        variables=assignments(self.variables.toPlainText());rows=validate_rows(self.raw_specs());key=self.scope.currentData()
        if self.studio.project.get('parameters',{})!=self._source_variables or self.owner().get('specifications',[])!=self._source_specs:
            raise ValueError('Variables or requirements changed elsewhere. Reload setup before saving.')
        def edit(p):
            p['parameters']=variables;next(c for c in p[key[0]] if c['id']==key[1])['specifications']=rows;validate(p)
        self.studio.commit(edit,'Save analog design variables and limits')
        self._source_variables=clone(variables);self._source_specs=clone(rows);self._scope_drafts.pop(key,None)
        self.workspace_note.setText('Variables and limits saved. Existing results retain their original definitions.')

    def edit_analysis(self):
        i=self.analyses.currentRow()
        if i<0:raise ValueError('Select a saved analysis or testbench.')
        entry=self.source_rows[i]
        if entry['id'].startswith('setup:'):
            self.studio.setup_table.selectRow(int(entry['id'].split(':')[1]));self.studio.edit_simulation_setup()
        else:
            self.studio.testbench_combo.setCurrentIndex(self.studio.testbench_combo.findData(entry['settings']['testbench']));self.studio.edit_testbench()

    def new_analysis(self):
        self.studio.add_simulation_setup();self.refresh_sources()

    def new_plan(self):
        self.tabs.setCurrentIndex(1);self.edit()

    def build_layout(self):
        layout=QVBoxLayout(self.layout_page)
        self.layout_note=QLabel();layout.addWidget(self.layout_note)
        self.placements=table(['Device','Type','State','Missing terminals']);layout.addWidget(self.placements,1)
        self.buttons(layout,[('Show selected device',self.select_device),('Place / regenerate…',self.generate),('Review schematic changes…',self.eco),('Show unrouted connections',self.connections),('Refresh',self.refresh_layout)])
        self.constraints=table(['Constraint','Kind','Members','State']);layout.addWidget(self.constraints,1)
        self.buttons(layout,[('Add constraint…',self.studio.constraint_dialog),('Arrange selected…',self.arrange),('Guard ring…',lambda:self.studio.utility_generator('guard_ring'))])

    def refresh_layout(self):
        from .parametric import placement_inventory
        from .analog_constraints import findings
        self.layout_cid=self.studio.cid;cell=self.studio.cell;self.placement_rows=placement_inventory(self.studio.project,self.layout_cid)
        fill(self.placements,[[r['name'],r['kind'],r['state'],', '.join(r['missing'])] for r in self.placement_rows])
        issues=findings(self.studio.project,self.layout_cid);self.constraint_rows=clone(cell.get('analog_constraints',[]))
        fill(self.constraints,[[r.get('name',r['kind']),r['kind'],len(r['members']),'Needs attention' if any(v['object'] in r['members'] for v in issues) else 'Satisfied'] for r in self.constraint_rows])
        self.layout_note.setText('Active cell: '+cell['name']+' · changes use normal review and undo. Rerun connection and process checks after placement.')

    def select_device(self):
        if self.studio.cid!=self.layout_cid:raise ValueError('The active cell changed. Refresh the placement list.')
        i=self.placements.currentRow()
        if i<0:raise ValueError('Select a device to place or inspect.')
        self.studio.mode_combo.setCurrentIndex(2);self.studio.select([self.placement_rows[i]['id']],'schematic')

    def generate(self):self.select_device();return self.studio.parametric_dialog()
    def eco(self):
        from .layout_eco_ui import show
        return show(self.studio)
    def connections(self):self.studio.check_linked_layout();self.studio.mode_combo.setCurrentIndex(2)
    def arrange(self):
        if self.studio.cid!=self.layout_cid or self.studio.cell.get('analog_constraints',[])!=self.constraint_rows:raise ValueError('Constraints changed. Refresh the layout list.')
        self.studio.constraint_table.selectRow(self.constraints.currentRow());return self.studio.arrange_constraint()

    def build_verification(self):
        layout=QVBoxLayout(self.verification_page)
        note=QLabel('Inspect DRC/LVS locations and compare schematic/extracted requirements using each run’s saved circuit. Select a saved testbench to launch physical verification.');note.setWordWrap(True);layout.addWidget(note)
        self.verify_bench=QComboBox();self.verify_bench.setAccessibleName('Physical verification testbench');layout.addWidget(self.verify_bench)
        self.verification=table(['Run','Revision','State','Flow']);layout.addWidget(self.verification,1)
        self.buttons(layout,[('Inspect selected run',self.inspect_verification),('Run saved testbench verification',self.run_verification),('Refresh',self.refresh_verification)])
        self.verification.cellDoubleClicked.connect(lambda *_:self.call(self.inspect_verification))
    def refresh_verification(self):
        old=self.verify_bench.currentData();self.verify_bench.clear()
        for bench in self.studio.project.get('testbenches',[]):self.verify_bench.addItem(bench['name'],bench['id'])
        if self.verify_bench.findData(old)>=0:self.verify_bench.setCurrentIndex(self.verify_bench.findData(old))
        self.verification_rows=[r for r in self.studio.run_manager.rows if r['job']['project']['id']==self.project_id and r['job']['settings']['type'] in ('silicon','rc_compare','drc','lvs','erc')]
        fill(self.verification,[[r['name'],r['job']['project']['revision'],r['state'],r['job']['settings']['type']] for r in self.verification_rows])
    def run_verification(self):
        key=self.verify_bench.currentData()
        if key is None:raise ValueError('Save a testbench in Setup before running physical verification.')
        self.studio.testbench_combo.setCurrentIndex(self.studio.testbench_combo.findData(key));self.studio.run_silicon();self.refresh_verification()
    def inspect_verification(self):
        from .analog_run_ui import RunInspector
        i=self.verification.currentRow()
        if i<0:raise ValueError('Select a verification run.')
        self.run_inspector=RunInspector(self.studio,self.verification_rows[i]);self.run_inspector.show()
    def page_changed(self,index):
        if index==0:self.refresh_sources()
        if index==2:self.call(self.refresh_layout)
        if index==3:self.refresh_verification()
