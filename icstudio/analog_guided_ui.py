"""Progressive, preview-before-commit analog setup."""
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QFormLayout,QComboBox,QLineEdit,QCheckBox,QPlainTextEdit,QTableWidgetItem
from .analog_widgets import label,actions,scroll,table,fill
from .model import clone,design_digest
from . import analog_guided as guided


class GuidedSetup(QDialog):
    def __init__(self,workspace):
        super().__init__(workspace);self.workspace=workspace;self.studio=workspace.studio;self.proposal=None
        self.setWindowTitle('Guided analog setup');self.resize(760,850);self.setMinimumSize(620,500)
        root=QVBoxLayout(self);body=QWidget();layout=QVBoxLayout(body);self.scroller=scroll(body);root.addWidget(self.scroller)
        layout.addWidget(label('Choose your circuit and goals. Preview the editable fixtures and measurements before adding them to the project.'))
        form=QFormLayout();form.setRowWrapPolicy(QFormLayout.WrapLongRows);layout.addLayout(form)
        self.template=QComboBox()
        for title,key in [('Amplifier','amplifier'),('Differential pair','differential_pair'),('Current mirror','current_mirror')]:self.template.addItem(title,key)
        self.dut=QComboBox();self.engine=QComboBox();self.engine.addItem('Built-in teaching solver','builtin');self.engine.addItem('ngspice · process models','ngspice')
        self.name=QLineEdit('guided_amplifier')
        for title,w in [('Circuit type',self.template),('DUT cell',self.dut),('Simulator',self.engine),('Experiment name',self.name)]:form.addRow(label(title,w),w)
        actions(layout,[('Add teaching example',self.example)],self.call)
        self.ports=table(['Role','DUT port','DC bias (V; unused ports)'],True);self.ports.setAccessibleName('DUT port roles and explicit bias voltages');layout.addWidget(self.ports)
        self.values={};self.basic=QFormLayout();self.basic.setRowWrapPolicy(QFormLayout.WrapLongRows);layout.addLayout(self.basic)
        self.advanced_check=QCheckBox('Show stimulus and sweep settings');layout.addWidget(self.advanced_check)
        self.advanced=QWidget();adv=QFormLayout(self.advanced);adv.setRowWrapPolicy(QFormLayout.WrapLongRows);layout.addWidget(self.advanced);self.advanced.hide();self.advanced_check.toggled.connect(self.advanced.setVisible)
        fields=[('supply','Supply (V)'),('common_mode','Input common mode (V)'),('load','Load capacitance (F)'),('gain_min','Minimum gain (V/V)'),('bandwidth_min','Minimum bandwidth (Hz)'),('power_max','Maximum power (W)'),('settling_max','Maximum 2% settling time (s; optional)'),('reference_current','Reference current (A)'),('mirror_ratio','Output / reference ratio'),('current_tolerance','Current tolerance (fraction)'),('compliance','Output clamp (V)'),('start_frequency','AC start (Hz)'),('end_frequency','AC end (Hz)'),('stop_time','Transient duration (s)'),('input_step','Input step (V)'),('temperature','Temperature (°C)')]
        for key,title in fields:
            w=QLineEdit(guided.DEFAULTS[key]);self.values[key]=w;(self.basic if key in ('supply','common_mode','load','gain_min','bandwidth_min','power_max','settling_max','reference_current','mirror_ratio','current_tolerance','compliance') else adv).addRow(label(title,w),w)
            w.textChanged.connect(self.invalidate)
        self.preview_table=table(['Test','Requirement','Expression','Minimum','Maximum','Unit']);self.preview_table.setAccessibleName('Proposed analyses and requirements');layout.addWidget(self.preview_table)
        self.note=label('');root.addWidget(self.note)
        self.preview_button,self.create_button,_=actions(root,[('Preview setup',self.preview),('Create setup',self.create),('Cancel',self.reject)],self.call,'Create setup');self.create_button.setEnabled(False)
        self.template.currentIndexChanged.connect(self.template_changed);self.dut.currentIndexChanged.connect(self.roles);self.engine.currentIndexChanged.connect(self.invalidate);self.name.textChanged.connect(self.invalidate);self.ports.itemChanged.connect(self.invalidate)
        self.refresh();self.template_changed()

    def call(self,fn):
        try:self.workspace.require_saved_setup();return fn()
        except Exception as exc:self.note.setText(str(exc))

    def invalidate(self,*_):
        self.proposal=None
        if hasattr(self,'create_button'):self.create_button.setEnabled(False)

    def refresh(self,selected=None):
        self.dut.blockSignals(True);self.dut.clear()
        for c in self.studio.project['cells']:
            if c['ports']:self.dut.addItem(c['name'],c['id'])
        self.dut.setCurrentIndex(max(0,self.dut.findData(selected or self.studio.cid)));self.dut.blockSignals(False);self.roles()

    def template_changed(self,*_):
        self.name.setText('guided_'+self.template.currentData());mirror=self.template.currentData()=='current_mirror'
        for key in ('common_mode','gain_min','bandwidth_min','settling_max'):
            self.values[key].setVisible(not mirror);self.basic.labelForField(self.values[key]).setVisible(not mirror)
        for key in ('reference_current','mirror_ratio','current_tolerance','compliance'):
            self.values[key].setVisible(mirror);self.basic.labelForField(self.values[key]).setVisible(mirror)
        self.roles()

    def roles(self,*_):
        self.invalidate();self.ports.setRowCount(0)
        c=next((c for c in self.studio.project['cells'] if c['id']==self.dut.currentData()),None)
        if not c:return
        defaults=guided.port_defaults(c,self.template.currentData());self.role_boxes={}
        for role,port in defaults.items():
            i=self.ports.rowCount();self.ports.insertRow(i);self.ports.setItem(i,0,QTableWidgetItem(role.replace('_',' ')));box=QComboBox();box.addItems(['']+c['ports']);box.setCurrentText(port);box.setAccessibleName(role.replace('_',' ')+' DUT port');self.ports.setCellWidget(i,1,box);self.role_boxes[role]=box;box.currentTextChanged.connect(self.invalidate)
        # Bias rows always list all ports; only unused ports are consumed. This
        # keeps typed biases intact while role assignments are changed.
        for port in c['ports']:
            i=self.ports.rowCount();self.ports.insertRow(i)
            for j,text in enumerate(('Unused port bias',port,'')):self.ports.setItem(i,j,QTableWidgetItem(text))
        for box in self.role_boxes.values():box.currentTextChanged.connect(self.update_bias_rows)
        self.update_bias_rows()
        self.note.setText('Map each role to a distinct port. Enter DC biases below for any ports left unused.')

    def update_bias_rows(self,*_):
        used={w.currentText() for w in self.role_boxes.values()};unused=0
        for i in range(len(self.role_boxes),self.ports.rowCount()):
            hidden=self.ports.item(i,1).text() in used;self.ports.setRowHidden(i,hidden);unused+=not hidden
        self.ports.setColumnHidden(2,not unused);self.ports.setMaximumHeight(min(260,40+30*(len(self.role_boxes)+unused)))

    def example(self):
        if not self.studio.flush_inspector():return
        proposal,cid=guided.teaching_example(self.studio.project,self.template.currentData())
        self.studio.commit(lambda p:(p.clear(),p.update(clone(proposal))),'Add analog teaching DUT')
        self.workspace.reload_setup();self.refresh(cid)

    def spec(self):
        roles={k:w.currentText() for k,w in self.role_boxes.items()};used=set(roles.values());biases={}
        for i in range(len(roles),self.ports.rowCount()):
            port=self.ports.item(i,1).text()
            if port not in used:biases[port]=self.ports.item(i,2).text()
        values={k:w.text().strip() for k,w in self.values.items()}
        if self.template.currentData()=='current_mirror':values.update(gain_min='',bandwidth_min='',settling_max='')
        return dict(template=self.template.currentData(),name=self.name.text().strip(),ports=roles,biases=biases,values=values,engine=self.engine.currentData())

    def preview(self):
        if not self.studio.flush_inspector():return
        if not self.dut.currentData():raise ValueError('Expose DUT ports or add a teaching example to begin.')
        self.proposal,self.report=guided.generate(self.studio.project,self.dut.currentData(),self.spec())
        fill(self.preview_table,[[r.get(k,'') for k in ('test','name','expression','min','max','unit')] for r in self.report['requirements']])
        self.scroller.ensureWidgetVisible(self.preview_table)
        self.create_button.setEnabled(True);self.note.setText(f"Ready to add {len(self.report['tests'])} fixture cells, saved analyses and editable testbenches, plus one test plan. No simulations have run.")

    def create(self):
        if not self.proposal:raise ValueError('Preview your setup first.')
        if design_digest(self.studio.project)!=self.report['base_design_hash']:raise ValueError('The design changed. Preview the setup again.')
        self.studio.commit(lambda p:(p.clear(),p.update(clone(self.proposal))),'Create guided analog setup')
        self.workspace.reload_setup();self.workspace.refresh_plans(self.report['plan_id']);self.workspace.optimizer.refresh_sources()
        page=self.workspace.optimizer;page.source.setCurrentIndex(next(i for i in range(page.source.count()) if page.source.itemData(i)['id']==self.report['plan_id']))
        page.parameter_cell.setCurrentIndex(page.parameter_cell.findData(self.report['dut_cell']))
        self.workspace.workspace_note.setText('Guided setup created. Review or run the plan in Results matrix; adjust search parameters in Optimize.');self.accept()
