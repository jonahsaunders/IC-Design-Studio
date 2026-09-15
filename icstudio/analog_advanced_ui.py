"""Closable advanced studies, sharing the optimizer's snapshots and job queue."""
import json
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QFormLayout,QStackedWidget,QSpinBox,QCheckBox,QPlainTextEdit,QFileDialog,QTableWidgetItem)
from .model import clone,scalar,atomic_write,design_digest
from .analog_widgets import actions,label,scroll,table,fill
from .analog_optimizer_ui import combo,edit,condition_text
from . import analog_optimizer as opt,variation_runs,analog_automation as automation


def number(name,lo,hi,value):
    w=QSpinBox();w.setRange(lo,hi);w.setValue(value);w.setAccessibleName(name);return w


class AdvancedAnalyses(QDialog):
    def __init__(self,page):
        super().__init__(page.workspace);self.page=page;self.studio=page.studio;self.project_id=page.project_id
        self.setWindowTitle('Advanced analog analyses');self.setModal(False);self.resize(940,750);self.setMinimumSize(520,440)
        self._report_cache={}
        self.manifests=[m for m in variation_runs.load(self.studio.jobs_dir,self.project_id) if m.get('advanced')]
        for m in self.manifests:m['execution_active']=False
        root=QVBoxLayout(self);self.context=label('');root.addWidget(self.context);self.action_error=label('');root.addWidget(self.action_error);self.action_error.hide()
        self.mode=combo('Advanced analysis category')
        for name in ('Global sensitivity','Robustness','Electrical diagnostics','Model fidelity','Verification workflow'):self.mode.addItem(name)
        root.addWidget(self.mode);self.run_button=actions(root,[('Run selected study',self.run_selected)],self.call,'Run selected study')[0]
        self.stack=QStackedWidget();root.addWidget(self.stack,2);self.mode.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.build_sensitivity();self.build_robustness();self.build_diagnostics();self.build_fidelity();self.build_workflow()
        self.history=combo('Saved advanced experiment');self.history_label=label('&Saved experiment',self.history);root.addWidget(self.history_label);root.addWidget(self.history)
        self.status=label('Configure a study, then run it. Closing this window returns to the workspace; queued runs continue.');root.addWidget(self.status)
        self.results=table(['Item','State','Measured result','Detail']);self.results.setAccessibleName('Advanced analysis evidence');root.addWidget(self.results,2)
        self.details_toggle=QCheckBox('Show exact selected evidence');self.details_toggle.setAccessibleName(self.details_toggle.text());root.addWidget(self.details_toggle)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setAccessibleName('Exact selected evidence and scope');self.details.setMaximumHeight(140);root.addWidget(self.details);self.details.hide();self.details_toggle.toggled.connect(self.details.setVisible)
        self.results.cellDoubleClicked.connect(lambda *_:self.details_toggle.setChecked(True))
        self.run_choice=combo('Saved diagnostic or study run');root.addWidget(self.run_choice)
        self.inspect_button,self.apply_button,self.pause_button,self.resume_button,self.export_button,_=actions(root,[('Inspect saved run…',self.inspect),('Apply full-SPICE finalist',self.apply),('Pause',self.pause),('Resume',self.resume),('Export report…',self.export),('Close',self.close)],self.call)
        self.history.currentIndexChanged.connect(self.render);self.results.itemSelectionChanged.connect(self.selection)
        self.mode.currentIndexChanged.connect(lambda:self.fill_history())
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.tick);self.timer.start()
        self.fill_history();self.refresh_context()

    def call(self,fn):
        try:
            self.action_error.hide()
            if self.studio.project['id']!=self.project_id:raise ValueError('The project changed. Reopen the analog workspace.')
            return fn()
        except Exception as exc:self.action_error.setText('Could not complete this action: '+str(exc));self.action_error.show()

    def panel(self,description):
        widget=QWidget();layout=QVBoxLayout(widget);layout.addWidget(label(description));form=QFormLayout();form.setRowWrapPolicy(QFormLayout.WrapLongRows);form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow);layout.addLayout(form);self.stack.addWidget(scroll(widget));return layout,form

    def field(self,form,name,widget):form.addRow(label(name,widget),widget)

    def refresh_context(self):
        plan=self.page.source.currentData()
        self.context.setText('Uses Circuit search’s selected plan, parameter ranges, objectives and simulation budget: '+(plan['name'] if plan else 'Choose a saved analysis in Circuit search.'))

    def build_sensitivity(self):
        layout,form=self.panel('Find influential parameters and interactions over the ranges in Circuit search. Linked targets move together. Missing samples prevent an index from being reported.')
        self.sensitivity_method=combo('Sensitivity method');self.sensitivity_method.addItem('Morris · parameter screening','morris');self.sensitivity_method.addItem('Sobol · first and total-order effects','sobol')
        self.sensitivity_count=number('Trajectories or base pairs',2,256,6);self.seed=number('Reproducible sampling seed',0,2147483647,1)
        for title,w in [('Method',self.sensitivity_method),('Trajectories / base pairs',self.sensitivity_count),('Seed',self.seed)]:self.field(form,title,w)
        layout.addWidget(label('Before duplicate reuse: Morris needs R × (D + 1) candidates; Sobol needs N × (D + 2). Each candidate runs every saved condition. Small samples can give wide confidence intervals.'))
        layout.addStretch(1)

    def build_robustness(self):
        layout,form=self.panel('Explore adverse conditions or test explicit parameter distributions. Statistical results apply only to the declared model and saved tests; solver failures stay unresolved.')
        self.robust_method=combo('Robustness study type')
        for name,key in [('Search worst conditions','worst'),('User-declared tolerances','tolerance'),('Validated PDK statistical model','statistical')]:self.robust_method.addItem(name,key)
        self.robust_count=number('Robustness samples',4,500,20);self.robust_seed=number('Robustness seed',0,2147483647,1)
        self.stat_model=combo('Validated PDK statistical model')
        for key,value in self.studio.project['pdk'].get('statistical_models',{}).items():
            if value.get('validated') and value.get('evidence') and value.get('variations'):self.stat_model.addItem(key,key)
        self.validate_selected=QCheckBox('Validate the selected passing Circuit search candidate');self.validate_selected.setAccessibleName(self.validate_selected.text())
        for title,w in [('Study',self.robust_method),('Samples',self.robust_count),('Seed',self.robust_seed),('PDK statistical model',self.stat_model)]:self.field(form,title,w)
        layout.addWidget(self.validate_selected)
        self.uncertain=table(['Parameter','Lower','Upper','Absolute σ','Relative σ','Distribution','Shared factor','Loading'],True);self.uncertain.setAccessibleName('Uncertain parameters and distribution assumptions');self.uncertain.setMaximumHeight(160);layout.addWidget(self.uncertain)
        self.uncertain_target=combo('Parameter to add as uncertain');self.uncertain_target.addItems(opt.targets(self.studio.project,self.page.parameter_cell.currentData())+['temperature','supply']);self.field(form,'Uncertain parameter',self.uncertain_target)
        actions(layout,[('Add uncertain parameter',self.add_uncertain),('Use search ranges',self.use_ranges),('Remove selected parameter',lambda:self.uncertain.removeRow(self.uncertain.currentRow()))],self.call)
        layout.addWidget(label('Worst-condition search uses Lower/Upper. Tolerance studies use normal or uniform distributions and σ (relative 0.01 = 1%). Normal rows sharing a factor have correlation equal to the product of their loadings. No samples are clipped or resampled.'))
        layout.addStretch(1)

    def add_uncertain(self,target=None,lo=None,hi=None):
        from .analog_robustness import nominal
        target=target or self.uncertain_target.currentText();p=self.studio.project;plan=self.page.source.currentData()
        value=nominal(p,self.page.parameter_cell.currentData(),plan,target)
        if lo is None:lo,hi=sorted((value*.9,value*1.1)) if value else (-1,1)
        i=self.uncertain.rowCount();self.uncertain.insertRow(i)
        for j,v in enumerate((target,lo,hi,'0','.01','normal','','0')):self.uncertain.setItem(i,j,QTableWidgetItem(str(v)))

    def use_ranges(self):
        self.uncertain.setRowCount(0)
        for a in self.page.axes_spec():self.add_uncertain(a['target'],a['lower'],a['upper'])

    def build_diagnostics(self):
        layout,form=self.panel('Run one saved graphical analysis across its PVT conditions. Noise sources, poles/zeros and startup need ngspice. Loop margins require your circuit to contain a valid injection fixture.')
        self.diagnostic=combo('Electrical diagnostic')
        for name,key in [('Noise contributors','noise'),('Poles and zeros','pole_zero'),('Supply ramp and startup','startup'),('Loop gain and margins','loop'),('Device bias across conditions','bias')]:self.diagnostic.addItem(name,key)
        self.field(form,'Diagnostic',self.diagnostic);self.diagnostic_fields={}
        fields=[('output','Output net','out'),('source','Voltage source','V1'),('input','Input net','in'),('input_return','Input return','0'),('output_return','Output return','0'),
            ('start','Start frequency (Hz)','10'),('end','End frequency (Hz)','1G'),('points','Points per decade','40'),('stop','Transient stop (s)','100u'),('step','Maximum time step (s)','100n'),
            ('supply','Final supply (V)','1.8'),('ramps','Supply ramp times (s), comma separated','1u, 10u'),('initial_node','Initial-condition net','out'),('initials','Initial voltages (V), comma separated','0, 0.9'),
            ('minimum','Final output minimum (V)','0.5'),('maximum','Final output maximum (V)','1.3'),('numerator','Return voltage net','out'),('denominator','Injection voltage net','in')]
        for key,title,value in fields:
            w=edit(value,title);self.diagnostic_fields[key]=w;self.field(form,title,w)
        self.loop_sign=combo('Return ratio sign');self.loop_sign.addItem('T = return / injection',1);self.loop_sign.addItem('T = −return / injection',-1);self.field(form,'Polarity for 1 + T',self.loop_sign)
        visible=dict(noise={'output','source','start','end','points'},pole_zero={'input','input_return','output','output_return'},startup={'output','source','stop','step','supply','ramps','initial_node','initials','minimum','maximum'},loop={'numerator','denominator','start','end','points'},bias=set())
        def visibility():
            kind=self.diagnostic.currentData()
            for key,w in self.diagnostic_fields.items():w.setVisible(key in visible[kind]);form.labelForField(w).setVisible(key in visible[kind])
            self.loop_sign.setVisible(kind=='loop');form.labelForField(self.loop_sign).setVisible(kind=='loop')
        self.diagnostic.currentIndexChanged.connect(visibility);visibility()
        layout.addStretch(1)

    def build_fidelity(self):
        layout,form=self.panel('Screen candidates with coarser AC/noise or transient sampling, learn the measured discrepancy, then promote candidates to the full saved SPICE plan. The first three candidates calibrate both levels. All saved full-resolution limits must pass before a finalist can be applied.')
        self.coarse_count=number('Coarse candidates',3,100,12);self.full_count=number('Full-resolution candidates',3,100,6);self.factor=number('Resolution reduction factor',2,20,4);self.fidelity_seed=number('Fidelity sampling seed',0,2147483647,1)
        for title,w in [('Coarse candidates',self.coarse_count),('Full candidates',self.full_count),('Coarse resolution factor',self.factor),('Seed',self.fidelity_seed)]:self.field(form,title,w)
        layout.addWidget(label('Both levels use the same device models and ngspice. Numerical sampling is the approximation. Coarse feasibility is provisional; this study does not replace extracted-layout verification.'))
        layout.addStretch(1)

    def build_workflow(self):
        layout,form=self.panel('Assign every saved test to an ordered stage. A later stage starts only after all earlier conditions pass. Invalid or failed simulations block progression; saved performance failures screen out that candidate.')
        self.stages=table(['Saved test','Stage'],False);self.stages.setMaximumHeight(160);layout.addWidget(self.stages)
        self.stage_names=edit('Bias, Frequency response, Transient, Final checks','Stage names in order')
        self.retry_count=number('Simulation retries per case',0,2,0);self.minutes=number('Total worker minutes',1,1440,60);self.reuse=QCheckBox('Reuse completed results with identical inputs and verified tool/model identities');self.reuse.setAccessibleName(self.reuse.text())
        for title,w in [('Stage names, comma separated',self.stage_names),('Retries for simulation failures',self.retry_count),('Total worker-time budget (minutes)',self.minutes)]:self.field(form,title,w)
        layout.addWidget(self.reuse);layout.addWidget(label('The simulation budget reserves retry capacity. Runtime adds the work of parallel workers; it is not wall-clock time. Cached results cost no worker time. A report is saved automatically when an experiment finishes.'))
        actions(layout,[('Load selected plan tests',self.load_stages),('Use workflow in Circuit search',self.use_workflow),('Clear workflow',self.clear_workflow)],self.call);layout.addStretch(1);self.load_stages()

    def load_stages(self):
        plan=self.page.source.currentData();entries=plan['entries'] if plan else [];self.stage_entries=clone(entries);self.stages.setRowCount(len(entries))
        for i,e in enumerate(entries):
            self.stages.setItem(i,0,QTableWidgetItem(e['name']));w=number('Stage for '+e['name'],1,8,{'op':1,'ac':2,'noise':2,'tran':3}.get(e['settings']['type'],4));self.stages.setCellWidget(i,1,w)

    def use_workflow(self):
        plan=self.page.source.currentData()
        if not plan or plan['entries']!=self.stage_entries:raise ValueError('The plan changed. Load its tests before assigning stages.')
        names=[s.strip() for s in self.stage_names.text().split(',')];stages=[]
        for n in sorted({self.stages.cellWidget(i,1).value() for i in range(len(self.stage_entries))}):
            if n>len(names) or not names[n-1]:raise ValueError('Give each assigned stage a name.')
            stages.append(dict(name=names[n-1],entries=[e['id'] for i,e in enumerate(self.stage_entries) if self.stages.cellWidget(i,1).value()==n]))
        workflow=dict(stages=stages,retries=self.retry_count.value(),runtime_seconds=60*self.minutes.value(),reuse=self.reuse.isChecked())
        automation.validate(plan,workflow);self.page.workflow=workflow;self.page.screen_op.setChecked(False);self.page.screen_op.setEnabled(False);self.page.workflow_note.setText('Workflow: '+' → '.join(s['name'] for s in stages));self.status.setText('Workflow configured for the next Circuit search. Existing experiments retain their saved stages.')

    def clear_workflow(self):
        self.page.workflow=None;self.page.screen_op.setEnabled(True);self.page.workflow_note.setText('');self.status.setText('The next search will use the standard test plan.')

    def inputs(self):
        self.refresh_context()
        if not self.studio.flush_inspector():raise ValueError('Finish editing the current device before running.')
        self.page.workspace.require_saved_setup();plan=self.page.source.currentData()
        if not plan:raise ValueError('Choose a saved analysis or plan in Circuit search.')
        self.page.verify_source(plan);return self.studio.project,self.page.parameter_cell.currentData(),plan,self.page.search_spec()

    def run_selected(self):
        return [self.run_sensitivity,self.run_robustness,self.run_diagnostics,self.run_fidelity,self.use_workflow][self.mode.currentIndex()]()

    def run_sensitivity(self):
        from .analog_sensitivity import prepare
        p,cid,plan,spec=self.inputs();self.queue(prepare(p,cid,plan,spec,self.studio.prepare_simulation,self.sensitivity_method.currentData(),self.sensitivity_count.value(),self.seed.value()))

    def run_robustness(self):
        from .analog_robustness import prepare
        p,cid,plan,spec=self.inputs();validation=None
        if self.validate_selected.isChecked():
            m=self.page.manifest();c=self.page.selected()
            if not m or not c or c['state']!='Passed' or m['base_design_hash']!=design_digest(p) or cid!=m['cell_id']:raise ValueError('Select a fully passing Circuit search candidate for the current design and parameter cell.')
            p=clone(p)
            for k,v in c['changes'].items():opt.set_target(p,cid,k,v)
            validation=dict(experiment=m['id'],candidate=c['candidate'],changes=clone(c['changes']))
        keys=('target','lower','upper','absolute_sigma','relative_sigma','distribution','group','rho')
        variables=[{key:self.uncertain.item(i,j).text().strip() if self.uncertain.item(i,j) else '' for j,key in enumerate(keys)} for i in range(self.uncertain.rowCount())]
        self.queue(prepare(p,cid,plan,spec,self.studio.prepare_simulation,variables,self.robust_method.currentData(),self.robust_count.value(),self.robust_seed.value(),self.stat_model.currentData(),validation))

    def run_diagnostics(self):
        from .analog_diagnostics import prepare
        p,_,plan,_=self.inputs();config={k:w.text().strip() for k,w in self.diagnostic_fields.items()};config.update(kind=self.diagnostic.currentData(),sign=self.loop_sign.currentData())
        ramps=[scalar(v.strip()) for v in config.pop('ramps').split(',')];initials=[scalar(v.strip()) for v in config.pop('initials').split(',')];config.update(ramp=ramps[0],initial_voltage=initials[0],points=int(config['points']))
        self.queue(prepare(p,plan['entries'][0]['cell'],plan,self.studio.prepare_simulation,config,self.page.budget.value(),ramps,initials))

    def run_fidelity(self):
        from .analog_fidelity import prepare
        p,cid,plan,spec=self.inputs();self.queue(prepare(p,cid,plan,spec,self.studio.prepare_simulation,self.coarse_count.value(),self.full_count.value(),self.factor.value(),self.fidelity_seed.value()))

    def enqueue(self,m,jobs):
        if jobs:self.studio.run_manager.enqueue_many(jobs,self.studio.jobs_dir,[m['name']+' · '+str(j['case']['index'])+' · '+condition_text(j['case']['labels']) for j in jobs])

    def queue(self,m):
        variation_runs.save(m,self.studio.jobs_dir);self.manifests.append(m);self.mode.setCurrentIndex(['sensitivity','robustness','diagnostics','fidelity'].index(m['advanced']['kind']));self.fill_history(m['id']);self.enqueue(m,m['jobs']);self.render()

    def fill_history(self,selected=None):
        selected=selected or self.history.currentData();kind=['sensitivity','robustness','diagnostics','fidelity',None][self.mode.currentIndex()]
        self.run_button.setText('Use workflow in Circuit search' if kind is None else 'Run selected study');self.run_button.setAccessibleName(self.run_button.text())
        self.history.blockSignals(True);self.history.clear()
        for m in self.manifests:
            if m['advanced']['kind']==kind:self.history.addItem(m['name']+' · '+m['created'],m['id'])
        i=self.history.findData(selected);self.history.setCurrentIndex(i if i>=0 else self.history.count()-1);self.history.blockSignals(False);self.render()

    def manifest(self):return next((m for m in self.manifests if m['id']==self.history.currentData()),None)

    def report(self,m):
        kind=m['advanced']['kind']
        current=variation_runs.latest(m,self.studio.run_manager.rows)
        signature=(len(m['jobs']),m['advanced'].get('done'),tuple((i,r['id'],r['state'],id(r.get('result'))) for i,r in current.items()))
        cached=self._report_cache.get(m['id'])
        if cached and cached[0]==signature:return cached[1]
        from . import analog_sensitivity,analog_robustness,analog_diagnostics,analog_fidelity
        result={'sensitivity':analog_sensitivity,'robustness':analog_robustness,'diagnostics':analog_diagnostics,'fidelity':analog_fidelity}[kind].analyze(m,self.studio.run_manager.rows)
        self._report_cache[m['id']]=(signature,result);return result

    def tick(self):
        if self.studio.project['id']!=self.project_id:return
        for i,m in enumerate(self.manifests):
            if not m.get('execution_active'):continue
            try:
                if m['advanced']['kind'] in ('robustness','fidelity'):
                    from . import analog_robustness,analog_fidelity
                    module=analog_robustness if m['advanced']['kind']=='robustness' else analog_fidelity
                    updated,jobs=module.advance(m,self.studio.run_manager.rows,self.studio.prepare_simulation)
                    if updated!=m:variation_runs.save(updated,self.studio.jobs_dir);self.manifests[i]=m=updated;self.enqueue(m,jobs)
                report=self.report(m)
                if report['complete']:m['execution_active']=False;automation.save_report(m,report,self.studio.jobs_dir);variation_runs.save(m,self.studio.jobs_dir)
            except Exception as exc:
                m['execution_active']=False;m['advanced']['pause_reason']=str(exc);variation_runs.save(m,self.studio.jobs_dir);self.status.setText('Study paused: '+str(exc))
        if self.isVisible():self.render()

    def render(self):
        m=self.manifest();self.result_rows=[];self.run_choice.clear();self.apply_button.setEnabled(False)
        evidence=self.mode.currentIndex()!=4
        for w in (self.history_label,self.history,self.results,self.details_toggle,self.run_choice,self.inspect_button,self.apply_button,self.pause_button,self.resume_button,self.export_button):w.setVisible(evidence)
        self.details.setVisible(evidence and self.details_toggle.isChecked())
        for w in (self.inspect_button,self.pause_button,self.resume_button,self.export_button):w.setEnabled(bool(m))
        if not m:
            self.results.setRowCount(0);self.details.clear();self.status.setText('Configure the next search’s verification stages above.' if not evidence else 'No saved study in this category. Configure the study above to begin.');return
        report=self.report(m);kind=m['advanced']['kind'];self.current_report=report
        if kind=='sensitivity':
            self.result_rows=report['rows'];morris=report['method']=='morris';headers=['Parameter','Objective','μ*' if morris else 'First order','σ' if morris else 'Total order','95% interval / state']
            data=[[r.get('target','—'),r['objective'],r.get('mu_star') if morris else r.get('first_order'),r.get('sigma') if morris else r.get('total_order'),r.get('confidence',r['status'])] for r in self.result_rows]
        elif kind=='robustness':
            headers=['Sample','State','Worst objective','Conditions']
            self.result_rows=report['candidates'];data=[[r['candidate'],r['state'],r.get('worst_value'),r['changes']] for r in self.result_rows]
        elif kind=='fidelity':
            headers=['Candidate / level','State','Worst objectives','Parameters']
            self.result_rows=[{**r,'level':level} for level,key in [('coarse','coarse_candidates'),('full','full_candidates')] for r in report[key]];data=[[str(r['candidate'])+' · '+r['level'],r['state'],[v['value'] for v in r['metrics']],r['changes']] for r in self.result_rows]
        else:
            headers,data,self.result_rows=diagnostic_rows(report,m['advanced']['diagnostic'])
        previous=self.results.currentRow();self.results.blockSignals(True);self.results.setColumnCount(len(headers));self.results.setHorizontalHeaderLabels(headers);fill(self.results,data)
        if 0<=previous<len(data):self.results.selectRow(previous)
        self.results.blockSignals(False)
        current=variation_runs.latest(m,self.studio.run_manager.rows)
        for r in current.values():self.run_choice.addItem(str(r['job']['case']['index'])+' · '+r['job']['case']['test_name']+' · '+condition_text(r['job']['case']['labels'])+' · '+r['state'],r['id'])
        status=('Finished. ' if report['complete'] else 'Running. ' if m.get('execution_active') else 'Paused. ')+report['scope']
        finished=sum(r['state'] in opt.TERMINAL for r in current.values());status=f'{finished}/{len(m["jobs"])} proposed simulations finished. '+status
        if kind=='robustness':status+=f" {report['passed']} pass / {report['failed']} fail / {report['unresolved']} unresolved."
        if kind=='robustness' and report['confidence_95'] is not None:status+=f" Pass fraction {report['pass_fraction']:.1%}; 95% interval {report['confidence_95'][0]:.1%}–{report['confidence_95'][1]:.1%}."
        if m['advanced'].get('pause_reason'):status+=' '+m['advanced']['pause_reason']
        self.status.setText(status);self.pause_button.setEnabled(bool(m.get('execution_active')));self.resume_button.setEnabled(not m.get('execution_active') and (not report['complete'] or bool(variation_runs.pending(m,self.studio.run_manager.rows))));self.inspect_button.setEnabled(bool(current));self.selection()

    def selection(self):
        i=self.results.currentRow();r=self.result_rows[i] if 0<=i<len(self.result_rows) else None
        self.details.setPlainText(json.dumps(r,indent=2,ensure_ascii=False) if r else 'Select a result for exact values, confidence intervals and evidence scope.')
        m=self.manifest();self.apply_button.setEnabled(bool(m and r and r.get('level')=='full' and r.get('state')=='Passed' and self.current_report['complete'] and m['base_design_hash']==design_digest(self.studio.project)))
        if r:
            rid=r.get('run_id') or next(iter(r.get('runs',[])),None)
            if rid and self.run_choice.findData(rid)>=0:self.run_choice.setCurrentIndex(self.run_choice.findData(rid))

    def pause(self):
        m=self.manifest()
        if m:m['execution_active']=False;variation_runs.save(m,self.studio.jobs_dir);self.studio.run_manager.cancel(list(variation_runs.latest(m,self.studio.run_manager.rows).values()));self.render()

    def resume(self):
        m=self.manifest()
        if not m:return
        m['execution_active']=True;m['advanced'].pop('pause_reason',None);variation_runs.save(m,self.studio.jobs_dir);self.enqueue(m,variation_runs.pending(m,self.studio.run_manager.rows));self.tick();self.render()

    def inspect(self):
        row=next((r for r in self.studio.run_manager.rows if r['id']==self.run_choice.currentData()),None)
        if not row:raise ValueError('Choose a saved run.')
        from .analog_run_ui import RunInspector
        self.inspector=RunInspector(self.studio,row);self.inspector.show()

    def apply(self):
        from .analog_fidelity import apply_candidate
        m=self.manifest();i=self.results.currentRow()
        if not m or not 0<=i<len(self.result_rows) or self.result_rows[i].get('level')!='full':raise ValueError('Select a full-SPICE finalist.')
        self.page.workspace.require_saved_setup();candidate=self.result_rows[i]['candidate']
        self.studio.commit(lambda p:apply_candidate(p,m,self.studio.run_manager.rows,candidate),'Apply full-SPICE optimizer finalist');self.page.workspace.reload_setup();self.render()

    def export(self):
        m=self.manifest()
        if not m:return
        path,_=QFileDialog.getSaveFileName(self,'Export advanced analysis report','analog-analysis.json','JSON (*.json)')
        if path:atomic_write(path,json.dumps(automation.report_document(m,self.report(m)),indent=2,allow_nan=False));self.status.setText('Report exported with saved parameters, conditions and evidence scope.')


def diagnostic_rows(report,kind):
    headers={'bias':['Device','Region / bias','gm/Id (1/V)','Headroom (V)','Condition'],
        'noise':['Contribution','RMS (V)','Output power share','Evidence','Condition'],
        'pole_zero':['Pole / zero','Real (rad/s)','Imaginary (rad/s)','Magnitude (Hz)','Condition'],
        'startup':['Run','Output window','Final (V)','Settled by (s)','Condition / ramp'],
        'loop':['Crossing','Frequency (Hz)','Phase margin (°)','Gain margin (dB)','Condition']}[kind]
    data=[];details=[]
    for run in report['rows']:
        e=run.get('evidence') or {};condition=condition_text(run['condition']);values=[];items=[]
        if kind=='bias':
            items=e.get('devices',[]);values=[[r['device'],r['bias_status'],r['gm_Id_per_V'],r['headroom_V'],condition] for r in items]
        elif kind=='noise':
            items=e.get('contributors',[]);values=[[r['vector'],r['rms_V'],None if r['fraction_of_output'] is None else f"{r['fraction_of_output']:.2%}",'Subtotal (overlaps)' if r['subtotal'] else 'Source component',condition] for r in items]
        elif kind=='pole_zero':
            items=[{**r,'type':name} for name,key in [('Pole','poles'),('Zero','zeros')] for r in e.get(key,[])];values=[[r['type']+(' · RHP' if r['right_half_plane'] else ''),r['real_rad_s'],r['imag_rad_s'],r['frequency_Hz'],condition] for r in items]
        elif kind=='startup' and e:
            items=[e];values=[[run['index'],'Pass' if e['passed'] else 'Fail',e['final_V'],e['settled_by_s'],condition+f" · ramp {e['ramp_s']:g} s · initial {e['initial_voltage_V']:g} V"]]
        elif kind=='loop':
            items=[{**r,'crossing':name} for name,key in [('Unity gain','unity_crossings'),('Negative real axis','negative_real_crossings')] for r in e.get(key,[])];values=[[r['crossing'],r['frequency_Hz'],r.get('phase_margin_deg'),r.get('gain_margin_dB'),condition] for r in items]
        if not items:items=[e];values=[[run['index'],run['state'],'No captured crossing' if e and kind=='loop' else 'Unavailable',None,condition]]
        data.extend(values);details.extend([{**run,'selected':item} for item in items])
    return headers,data,details
