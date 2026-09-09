"""Native design goals, waveform calculation and individual variation cases."""
import json
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QSize
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTableWidgetItem,
 QAbstractItemView,QComboBox,QCheckBox,QDialog,QDialogButtonBox,QScrollArea,QSplitter,QFileDialog)
from .model import clone,digest,scalar
from .human_workspace import FlowLayout
from .specifications import validate_rows,evaluate_rows
from .plot import WavePlot


class EngineeringFlow(FlowLayout):
    def minimumSize(self):return QSize(90,32)
    def sizeHint(self):return QSize(500,36)


class LinkedPlot(WavePlot):
    def notify_view(self):
        if getattr(self,'link_views',None):self.link_views(self)
    def wheelEvent(self,event):super().wheelEvent(event);self.notify_view()
    def mouseMoveEvent(self,event):super().mouseMoveEvent(event);self.notify_view()
    def mouseDoubleClickEvent(self,event):super().mouseDoubleClickEvent(event);self.notify_view()
    def keyPressEvent(self,event):super().keyPressEvent(event);self.notify_view()


class Histogram(QWidget):
    def __init__(self):super().__init__();self.bins=[];self.setMinimumHeight(115)
    def paintEvent(self,event):
        p=QPainter(self);p.setPen(self.palette().text().color());p.drawText(8,18,'Specification distribution · completed cases')
        if not self.bins:p.drawText(8,48,'Completed scalar specifications will appear here.');return
        top=max(b['count'] for b in self.bins);width=(self.width()-24)/len(self.bins);height=max(10,self.height()-60)
        for i,b in enumerate(self.bins):
            h=int(height*b['count']/max(1,top));p.fillRect(int(12+i*width),int(28+height-h),max(1,int(width-4)),h,QColor('#6094e6'));p.drawText(int(12+i*width),int(25+height-h),str(b['count']))
        p.drawText(12,self.height()-7,f"{self.bins[0]['low']:.5g}    →    {self.bins[-1]['high']:.5g}")


class EngineeringWorkspaceMixin:
    def make_ui(self):
        super().make_ui();self._spec_owner=None;self._spec_drafts={};self._spec_loaded_rows=[];self._case_manifests=[];self._case_project=None
        page,v=self.engineering_page('Design specifications','Save reusable requirements with a cell or testbench. Each run retains the requirements and results from its input snapshot.')
        self.spec_scope=QComboBox();self.spec_scope.setAccessibleName('Specification owner');v.addWidget(self.spec_scope);self.spec_scope.currentIndexChanged.connect(self.load_spec_editor)
        self.spec_editor=self.simulation_table(['Name','Expression','Minimum','Maximum','Unit']);self.spec_editor.setEditTriggers(QAbstractItemView.DoubleClicked|QAbstractItemView.EditKeyPressed|QAbstractItemView.AnyKeyPressed);self.spec_editor.setMinimumHeight(95);self.spec_editor.setMaximumHeight(170);v.addWidget(self.spec_editor);self.spec_editor.hide()
        self.spec_editbar=self.engineering_buttons(v,[('Add requirement',self.add_spec_row),('Remove selected',lambda:self.spec_editor.removeRow(self.spec_editor.currentRow())),('Save requirements',self.save_specifications),('Reload',self.load_spec_editor)]);self.spec_editbar.hide()
        self.engineering_buttons(v,[('Edit requirements',self.toggle_spec_editor),('Evaluate selected run',self.evaluate_selected_specs),('Export results…',self.export_specs)])
        self.spec_note=QLabel('Run an analysis to evaluate saved requirements.');self.spec_note.setWordWrap(True);v.addWidget(self.spec_note)
        self.spec_results=self.simulation_table(['Requirement','Value','Unit','Margin','Result','Details']);v.addWidget(self.spec_results)
        self.annotate_check=QCheckBox('Show operating-point values on schematic');self.annotate_check.toggled.connect(self.update_annotations);v.addWidget(self.annotate_check)
        self.spec_tab=self.add_engineering_tab(page,'Specifications')
        page,v=self.engineering_page('Variation studies','Each case is a separate simulation job. Resume reuses completed snapshots and queues interrupted, cancelled or failed cases.')
        self.case_bench=QComboBox();self.case_bench.setAccessibleName('Study analysis source');v.addWidget(self.case_bench)
        controls=QHBoxLayout();self.case_kind=QComboBox();self.case_kind.setAccessibleName('New study type')
        for name,kind in [('Parameter sweep','sweep'),('PVT matrix','pvt'),('Component tolerances','monte_carlo'),('Model mismatch','model_mismatch'),('Sensitivity','sensitivity'),('Bounded parameter search','optimization')]:self.case_kind.addItem(name,kind)
        controls.addWidget(self.case_kind,1)
        def create_study():
            kind=self.case_kind.currentData()
            return self.search_dialog(kind) if kind in ('sensitivity','optimization') else self.model_mismatch_dialog() if kind=='model_mismatch' else self.case_dialog(kind)
        for title,fn in [('New study…',create_study),('Resume / retry',self.resume_cases),('Open case',self.open_case),('Stop',self.stop_cases)]:controls.addWidget(self.button(title,fn=lambda checked=False,fn=fn:self.guard(fn)))
        self.case_apply=self.button('Apply best values',fn=lambda:self.guard(self.apply_search_values));self.case_apply.setEnabled(False);controls.addWidget(self.case_apply);v.addLayout(controls)
        self.case_group=QComboBox();self.case_group.setAccessibleName('Saved variation study');self.case_group.currentIndexChanged.connect(self.case_group_changed);selectors=QHBoxLayout();selectors.addWidget(self.case_group,2);v.addLayout(selectors)
        self.case_metric=QComboBox();self.case_metric.setAccessibleName('Study specification metric');self.case_metric.currentTextChanged.connect(self.refresh_cases);selectors.addWidget(self.case_metric,1)
        self.case_summary=QLabel('No study selected.');self.case_summary.setWordWrap(True);v.addWidget(self.case_summary)
        self.case_table=self.simulation_table(['Case','Condition','State','Requirement','Value','Margin','Result']);self.case_table.cellDoubleClicked.connect(lambda *_:self.open_case());case_results=QSplitter();case_results.addWidget(self.case_table);v.addWidget(case_results,1)
        self.case_histogram=Histogram();self.case_histogram.setMinimumWidth(160);case_results.addWidget(self.case_histogram);case_results.setStretchFactor(0,4);case_results.setStretchFactor(1,1);case_results.setSizes([760,190]);self.cases_tab=self.add_engineering_tab(page,'Variation cases')
        self.case_refresh_timer=QTimer(self);self.case_refresh_timer.setSingleShot(True);self.case_refresh_timer.setInterval(160);self.case_refresh_timer.timeout.connect(self.refresh_cases);self.run_manager.changed.connect(lambda:self.case_refresh_timer.start())
        self.reload_engineering()

    def engineering_page(self,title,note):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(14,12,14,12);label=QLabel(title);label.setProperty('role','title');v.addWidget(label);label=QLabel(note);label.setWordWrap(True);label.setProperty('role','muted');v.addWidget(label);return page,v
    def engineering_buttons(self,layout,buttons):
        widget=QWidget();flow=EngineeringFlow(widget)
        for title,fn in buttons:flow.addWidget(self.button(title,fn=lambda checked=False,fn=fn:self.guard(fn)))
        layout.addWidget(widget);return widget
    def add_engineering_tab(self,page,title):
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page);return self.results_tabs.addTab(scroll,title)
    def open_engineering_tab(self,index):self.results_dock.show();self.results_tabs.setCurrentIndex(index);self.resizeDocks([self.results_dock],[480],Qt.Vertical)

    def make_actions(self):
        super().make_actions();menu=self.task_menus['Simulate'];first=menu.actions()[0]
        for title,fn in [('Design specifications',lambda:self.open_engineering_tab(self.spec_tab)),('Variation cases',lambda:self.open_engineering_tab(self.cases_tab)),('Waveform calculator…',self.wavecalc_dialog)]:
            action=self.action(menu,title,fn);menu.removeAction(action);menu.insertAction(first,action)
        self.action(self.task_menus['Window'],'Specifications',lambda:self.open_engineering_tab(self.spec_tab));self.action(self.task_menus['Window'],'Variation cases',lambda:self.open_engineering_tab(self.cases_tab));self.reindex_commands()

    def refresh(self,fit=False):
        super().refresh(fit)
        if hasattr(self,'spec_editor'):
            self.reload_engineering();self.update_annotations()
            if self._spec_owner and digest(self.spec_owner().get('specifications',[]))!=getattr(self,'_spec_source_hash',None) and self.raw_editor_specs()==self._spec_loaded_rows:self.load_spec_editor()

    def reload_engineering(self):
        key=(self.project['id'],self.cid,tuple((t['id'],t['name']) for t in self.project.get('testbenches',[])))
        if key!=getattr(self,'_engineering_scope',None):
            self._engineering_scope=key;self.spec_scope.blockSignals(True);self.spec_scope.clear();self.spec_scope.addItem('Cell · '+self.cell['name'],('cells',self.cid))
            for t in self.project.get('testbenches',[]):self.spec_scope.addItem('Testbench · '+t['name'],('testbenches',t['id']))
            self.spec_scope.blockSignals(False);self.load_spec_editor()
            self.case_bench.clear();self.case_bench.addItem('Current cell · Inspector analysis',None)
            for t in self.project.get('testbenches',[]):self.case_bench.addItem('Saved testbench · '+t['name'],t['id'])
        if self._case_project!=self.project['id']:
            from .variation_runs import load
            self._case_project=self.project['id'];self._case_manifests=load(self.jobs_dir,self.project['id']);self.fill_case_groups()

    def spec_owner(self,p=None):
        group,key=self.spec_scope.currentData();return next(c for c in (p or self.project)[group] if c['id']==key)
    def load_spec_editor(self,*_):
        if not hasattr(self,'spec_editor') or not self.spec_scope.currentData():return
        if self._spec_owner:
            raw=self.raw_editor_specs()
            if raw!=self._spec_loaded_rows:self._spec_drafts[self._spec_owner]=raw
            else:self._spec_drafts.pop(self._spec_owner,None)
        self._spec_owner=(self.project['id'],self.spec_scope.currentData());self.spec_editor.setRowCount(0);source=self.spec_owner().get('specifications',[])
        for row in self._spec_drafts.get(self._spec_owner,source):self.add_spec_row(row)
        self._spec_loaded_rows=[{k:str(row.get(k,'')) for k in ('name','expression','min','max','unit')} for row in source];self._spec_source_hash=digest(source)
    def toggle_spec_editor(self):
        visible=self.spec_editor.isHidden();self.spec_editor.setVisible(visible);self.spec_editbar.setVisible(visible)
        if visible and not self.spec_editor.rowCount():self.add_spec_row()
    def add_spec_row(self,row=None):
        if not isinstance(row,dict):
            net=next(iter((self.result or {}).get('traces',{})),next((n for d in self.cell['devices'] for n in d['nets'].values() if n!='0'),'out'));row={'name':'Output '+str(self.spec_editor.rowCount()+1),'expression':'final(V('+json.dumps(net)+'))','min':'0','unit':'V'}
        index=self.spec_editor.rowCount();self.spec_editor.insertRow(index)
        for j,key in enumerate(('name','expression','min','max','unit')):self.spec_editor.setItem(index,j,QTableWidgetItem(str(row.get(key,''))))
    def raw_editor_specs(self):
        return [{key:self.spec_editor.item(i,j).text().strip() if self.spec_editor.item(i,j) else '' for j,key in enumerate(('name','expression','min','max','unit'))} for i in range(self.spec_editor.rowCount())]
    def editor_specs(self):return validate_rows(self.raw_editor_specs())
    def save_specifications(self):
        if self._spec_owner!=(self.project['id'],self.spec_scope.currentData()):raise ValueError('Reload the specifications for the active document.')
        rows=self.editor_specs();self._spec_loaded_rows=clone(rows);self._spec_drafts.pop(self._spec_owner,None);self.commit(lambda p:self.spec_owner(p).update(specifications=rows),'Save design specifications');self.spec_editor.hide();self.spec_editbar.hide();self.spec_note.setText('Requirements saved. New runs will evaluate these exact definitions.');return rows
    def show_specs(self,rows,note):
        self._displayed_specs=rows;self.spec_note.setText(note);self.spec_results.setRowCount(len(rows))
        for i,row in enumerate(rows):
            vals=[row['name'],'—' if row.get('value') is None else f"{row['value']:.7g}",row.get('unit',''),'—' if row.get('margin') is None else f"{row['margin']:+.5g}",row['status'],row.get('error','')]
            for j,value in enumerate(vals):
                item=QTableWidgetItem(value)
                if j==4:item.setForeground(QColor('#35aa86' if value=='PASS' else '#e2757f'))
                self.spec_results.setItem(i,j,item)
    def evaluate_selected_specs(self):
        if not self.result:raise ValueError('Open a completed run first.')
        self.show_specs(evaluate_rows(self.editor_specs(),self.result),'Preview: current editor requirements evaluated on the selected saved run. Saved run evidence is retained.')
    def export_specs(self):
        import csv
        if not getattr(self,'_displayed_specs',None):raise ValueError('Evaluate requirements or open a completed run first.')
        path,_=QFileDialog.getSaveFileName(self,'Export specification results','','CSV (*.csv)')
        if path:
            with open(path,'w',newline='',encoding='utf-8') as f:
                w=csv.DictWriter(f,fieldnames=['name','expression','min','max','unit','value','margin','status','error'],extrasaction='ignore');w.writeheader();w.writerows(self._displayed_specs)
    def select_run(self,i):
        super().select_run(i)
        if hasattr(self,'spec_results') and self.result:
            self.show_specs(self.result.get('specifications',[]),'Saved run requirements · '+self.result.get('created','')+' · revision '+str(self.result['revision']));self.update_annotations()
    def simulation_finished(self,row,result):
        page=self.results_tabs.currentIndex();super().simulation_finished(row,result)
        if row['job'].get('case') and page==self.cases_tab:self.results_tabs.setCurrentIndex(page)
        if row['job']['settings']['type']=='rc_compare' and page==getattr(self,'rc_tab',None):self.results_tabs.setCurrentIndex(page)
    def update_result_status(self):
        super().update_result_status()
        from .model import design_digest
        r=self.result
        if r and r.get('case') and r['case'].get('base_design_hash')==design_digest(self.project):
            self.result_status.setText('Saved study case '+str(r['case']['index'])+' · '+r['engine']);self.result_status.setStyleSheet('color:#79a6e8;')
    def update_annotations(self,*_):
        if not hasattr(self,'annotate_check'):return
        from .annotations import readouts
        rows,label=readouts(self.project,self.cid,self.result) if self.annotate_check.isChecked() else ({},'')
        self.schematic.simulation_annotations=rows;self.schematic.simulation_annotation_label=label;self.schematic.update()

    def wavecalc_dialog(self):
        from .wavecalc import plot_result,parse
        if not self.result:raise ValueError('Open a completed run before calculating waveforms.')
        dlg=QDialog(self);dlg.setWindowTitle('Waveform calculator');dlg.resize(1100,780);v=QVBoxLayout(dlg);owner_id=self.cid;project_id=self.project['id'];source=self.result
        label=QLabel('Use V("out"), I("V1"), abs(), phase(), db20(), deriv(), integ() and fft(). FFT uses a Hann window, amplitude correction and zero padding; uniformly sampled time data is required.');label.setWordWrap(True);v.addWidget(label)
        table=self.simulation_table(['Panel name','Expression']);table.setEditTriggers(QAbstractItemView.AllEditTriggers);table.setMaximumHeight(135);v.addWidget(table);dlg.expression_table=table
        def add(row=None):
            index=table.rowCount();table.insertRow(index);row=row or {'name':'Panel '+str(index+1),'expression':'V('+json.dumps(next(iter(source['traces'])))+')'}
            for j,k in enumerate(('name','expression')):table.setItem(index,j,QTableWidgetItem(row[k]))
        for row in self.cell.get('plot_layouts',[]) or [{'name':'Output','expression':'V('+json.dumps(next(iter(source['traces'])))+')'}]:add(row)
        linked=QCheckBox('Link X zoom and pan for panels with the same axis');linked.setChecked(True);v.addWidget(linked)
        area=QScrollArea();area.setWidgetResizable(True);host=QWidget();plots_layout=QVBoxLayout(host);area.setWidget(host);v.addWidget(area,1);error=QLabel();error.setWordWrap(True);v.addWidget(error);plots=[]
        def rows():return [{'name':table.item(i,0).text().strip(),'expression':table.item(i,1).text().strip()} for i in range(table.rowCount())]
        def link(origin):
            if not linked.isChecked():return
            bounds=origin.bounds()
            for other in plots:
                if other is origin or other.result['x_label']!=origin.result['x_label'] or other.result['x']!=origin.result['x']:continue
                ob=other.bounds();other._view_bounds=(bounds[0],bounds[1],ob[2],ob[3]);other.update()
        def render():
            try:
                definitions=rows()
                if not 1<=len(definitions)<=12:raise ValueError('Use 1–12 waveform panels.')
                waves=[plot_result(source,r['expression'],r['name']) for r in definitions]
                while plots_layout.count():plots_layout.takeAt(0).widget().deleteLater()
                plots.clear()
                from .waveform_tools import WaveformTools
                for wave in waves:
                    plot=LinkedPlot();plot.dark=self.dark;plot.set_result(wave);plot.link_views=link;plots.append(plot);plots_layout.addWidget(QLabel(next(iter(wave['traces']))));plots_layout.addWidget(WaveformTools(plot,self));plots_layout.addWidget(plot)
                dlg.plots=plots;error.clear()
            except Exception as exc:error.setText(str(exc))
        def save():
            if self.project['id']!=project_id or self.cid!=owner_id:raise ValueError('The active cell changed. Reopen the calculator.')
            definitions=rows()
            for row in definitions:parse(row['expression'])
            self.commit(lambda p:next(c for c in p['cells'] if c['id']==owner_id).update(plot_layouts=definitions),'Save plot layout');error.setText('Plot definitions saved with this cell.')
        self.engineering_buttons(v,[('Add panel',add),('Remove panel',lambda:table.removeRow(table.currentRow())),('Calculate / plot',render),('Save plot layout',save)])
        dlg.render_plots=render;self._wavecalc_dialog=dlg;render();dlg.show();return dlg

    def case_dialog(self,kind):
        owner_id=next((t['bench_cell'] for t in self.project.get('testbenches',[]) if t['id']==self.case_bench.currentData()),self.cid)
        from .studies import targets,supply_targets
        devices=next(c for c in self.project['cells'] if c['id']==owner_id)['devices'];supply=next(iter(supply_targets(self.project,owner_id)),None)
        if kind=='pvt' and supply is None:raise ValueError('PVT requires a DC supply in the active cell. Add a DC voltage source or select a fixture cell containing its supply.')
        available=targets(self.project,owner_id)
        if not available:raise ValueError('This cell has no editable numeric parameters. Expressions can be edited in device properties.')
        target=next((t for t in available if t.split('.')[0].upper().startswith('R')),available[0])
        common=[('name','Study name',{'pvt':'PVT matrix','sweep':'Parameter sweep','monte_carlo':'Component tolerances'}[kind]),('target','Target (instance.field)',supply if kind=='pvt' else target)]
        fields={'pvt':[('corners','Model corners (comma separated)','nominal'),('voltages','Supply values','1.6,1.8,2.0'),('temperatures','Temperatures (°C)','0,27,85')],'sweep':[('values','Parameter values','5k,10k,20k')],'monte_carlo':[('sigma','Relative sigma','0.05'),('distribution','Distribution',['normal','uniform']),('count','Number of trials','30'),('seed','Repeatable seed','1')]}[kind]
        def submit(values):
            spec={**values,'kind':kind}
            for key in ('corners','voltages','temperatures','values'):
                if key in spec:spec[key]=[x.strip() for x in spec[key].split(',') if x.strip()]
            if kind=='monte_carlo':spec.update(count=int(values['count']),seed=int(values['seed']),variations=[{'target':target.strip(),'relative_sigma':values['sigma'],'distribution':values['distribution']} for target in values['target'].split(',') if target.strip()])
            self.launch_cases(spec,review=True)
        return self.workflow_form(common[0][2],common+fields,submit,'Uses the current cell and Inspector analysis. Save requirements in Specifications first. Numeric targets: '+', '.join(available)+'. Tolerances use declared component distributions.')
    def model_mismatch_dialog(self):
        models=[k for k,v in self.project['pdk'].get('statistical_models',{}).items() if v.get('validated') and v.get('evidence') and v.get('variations')]
        if not models:raise ValueError('No validated statistical model is declared by the linked technology. Add a statistical model with evidence and numeric parameter mappings, or use Component tolerances.')
        return self.workflow_form('Model mismatch',[('model','Validated model',models),('count','Trials','30'),('seed','Seed','1')],lambda v:self.launch_cases({**v,'kind':'model_mismatch','count':int(v['count']),'seed':int(v['seed'])}),'Runs the parameter distributions declared in the selected technology model. The model evidence remains part of every saved input.')

    def search_dialog(self,kind):
        from .studies import targets,get_target
        available=targets(self.project,self.cid);metrics=[r['name'] for r in self.cell.get('specifications',[])]
        if not available or not metrics:raise ValueError('Add a numeric device parameter and save a scalar specification before starting a search.')
        target=next((t for t in available if t.upper().startswith('R')),available[0]);nominal=get_target(self.project,self.cid,target)
        fields=[('name','Study name','Sensitivity' if kind=='sensitivity' else 'Bounded search'),('metric','Measured specification',metrics)]
        if kind=='sensitivity':fields += [('targets','Targets (comma separated)',target),('relative_step','Relative perturbation','0.01'),('absolute_step','Step for zero-valued parameters','1u')]
        else:fields += [('target','Numeric parameter',[target]+[t for t in available if t!=target]),('lower','Lower bound',str(nominal*.5 if nominal>0 else nominal-1)),('upper','Upper bound',str(nominal*1.5 if nominal>0 else nominal+1)),('count','Samples including both bounds','11'),('goal','Objective',['target','minimize','maximize']),('objective','Desired specification value','0.5')]
        def submit(v):
            spec={**v,'kind':kind}
            if kind=='sensitivity':spec['targets']=[t.strip() for t in v['targets'].split(',') if t.strip()]
            else:spec['axes']=[{'target':v['target'],'lower':v['lower'],'upper':v['upper'],'count':int(v['count'])}]
            base=self.prepare_simulation(self.current_analysis_settings(),self.analysis_engine.currentData())
            self.launch_cases(spec,job=base,review=True)
        return self.workflow_form('Sensitivity' if kind=='sensitivity' else 'Bounded parameter search',fields,submit,'Every point runs as an independent case. Search ranks passing candidates on the sampled grid; it does not claim a global optimum. Sensitivity reports central differences in each parameter’s declared units. Numeric targets: '+', '.join(available))

    def apply_search_values(self):
        from .design_search import apply_best
        m=self.selected_manifest()
        if not m or m['spec']['kind']!='optimization':raise ValueError('Select a completed bounded parameter search.')
        if not self.flush_inspector():return
        self.commit(lambda p:apply_best(p,m,self.run_manager.rows),'Apply best measured search parameters')
    def launch_cases(self,spec,job=None,review=False):
        from .variation_runs import prepare,save
        if not self.flush_inspector():return
        if job is None and self.case_bench.currentData():
            t=next(t for t in self.project['testbenches'] if t['id']==self.case_bench.currentData());job=self.prepare_simulation({'type':'testbench','testbench':t['id']},'ngspice');job['settings']['executable']=job['executable']
        base=job or self.prepare_simulation(self.current_analysis_settings(),self.analysis_engine.currentData());manifest=prepare(base,spec)
        if review:return self.review_case_matrix(manifest)
        return self.queue_manifest(manifest)
    def queue_manifest(self,manifest):
        from .variation_runs import save
        save(manifest,self.jobs_dir);self._case_manifests.append(manifest);self.fill_case_groups(manifest['id']);self.run_manager.enqueue_many(manifest['jobs'],self.jobs_dir,[manifest['name']+' · '+str(i+1) for i in range(len(manifest['jobs']))]);self.open_engineering_tab(self.cases_tab);return manifest
    def review_case_matrix(self,manifest):
        dlg=QDialog(self);dlg.setWindowTitle('Review variation matrix');dlg.resize(980,610);v=QVBoxLayout(dlg);note=QLabel('Uncheck cases to omit them. Double-click a case to edit its parameter values and temperature before running. Every enabled case receives a separate immutable input.');note.setWordWrap(True);v.addWidget(note);table=self.simulation_table(['Run','Case','Conditions','Parameter changes']);table.setRowCount(len(manifest['jobs']));v.addWidget(table)
        def fill():
            for i,j in enumerate(manifest['jobs']):
                item=QTableWidgetItem();item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked);table.setItem(i,0,item)
                for col,val in enumerate((str(i+1),str(j['case']['labels']),str(j['case']['changes'])),1):table.setItem(i,col,QTableWidgetItem(val))
        fill()
        def edit_case(i,col):
            from .studies import set_target
            from .model import validate
            job=manifest['jobs'][i];case=job['case'];fields=[('param'+str(k),target,str(value)) for k,(target,value) in enumerate(case['changes'].items())]
            fields.append(('temperature','Temperature (°C)',str(job['settings'].get('temperature',27))))
            def submit(values):
                q=clone(job);changes={target:scalar(values['param'+str(k)]) for k,target in enumerate(case['changes'])};temp=scalar(values['temperature'])
                if temp<=-273.15:raise ValueError('Temperature must exceed absolute zero.')
                for target,value in changes.items():set_target(q['project'],q['cell'],target,value)
                q['settings']['temperature']=temp
                if q['settings'].get('testbench'):
                    next(t for t in q['project']['testbenches'] if t['id']==q['settings']['testbench'])['analysis']['temperature']=temp
                validate(q['project']);q['case']['changes']=changes;q['case']['labels'].update(temperature=temp,edited=True);q['case']['fingerprint']=digest({k:v for k,v in q.items() if k!='case'});manifest['jobs'][i]=q
                table.item(i,2).setText(str(q['case']['labels']));table.item(i,3).setText(str(changes))
            self.workflow_form('Edit case '+str(i+1),fields,submit,'Edits apply only to this planned case.')
        table.cellDoubleClicked.connect(edit_case);buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Ok).setText('Run enabled cases');v.addWidget(buttons)
        def run():
            m=clone(manifest);m['jobs']=[j for i,j in enumerate(m['jobs']) if table.item(i,0).checkState()==Qt.Checked]
            if not m['jobs']:raise ValueError('Enable at least one case.')
            for i,j in enumerate(m['jobs']):j['case']['index']=i+1
            self.queue_manifest(m);dlg.accept()
        buttons.accepted.connect(lambda:self.guard(run));buttons.rejected.connect(dlg.reject);dlg.case_table=table;dlg.manifest=manifest;self._case_matrix_dialog=dlg;dlg.show();return dlg
    def case_group_changed(self,*_):
        from .specifications import for_job
        if not hasattr(self,'case_metric'):return
        m=self.selected_manifest();old=self.case_metric.currentText();self.case_metric.blockSignals(True);self.case_metric.clear()
        if m:self.case_metric.addItems([r['name'] for r in for_job(m['jobs'][0])])
        if self.case_metric.findText(old)>=0:self.case_metric.setCurrentText(old)
        self.case_metric.blockSignals(False);self.refresh_cases()

    def fill_case_groups(self,selected=None):
        old=selected or self.case_group.currentData();self.case_group.blockSignals(True);self.case_group.clear()
        for m in self._case_manifests:self.case_group.addItem(m['name']+' · '+m['created'],m['id'])
        i=self.case_group.findData(old);self.case_group.setCurrentIndex(i if i>=0 else self.case_group.count()-1);self.case_group.blockSignals(False);self.case_group_changed()
    def selected_manifest(self):return next((m for m in self._case_manifests if m['id']==self.case_group.currentData()),None)
    def refresh_cases(self,*_):
        if not hasattr(self,'case_table'):return
        from .variation_runs import latest,summary
        m=self.selected_manifest()
        self.case_apply.setEnabled(bool(m and m['spec']['kind']=='optimization'))
        if not m:self.case_table.setRowCount(0);self.case_summary.setText('No study selected.');self.case_histogram.bins=[];self.case_histogram.update();return
        current=latest(m,self.run_manager.rows);selected=self.case_table.currentRow();self.case_table.setRowCount(len(m['jobs']))
        for i,job in enumerate(m['jobs']):
            row=current.get(i+1,{});specs=row.get('result',{}).get('specifications',[]);worst=next((r for r in specs if r['name']==self.case_metric.currentText()),specs[0] if specs else {})
            vals=[str(i+1),', '.join(str(k)+'='+str(v) for k,v in job['case']['labels'].items()),row.get('state','Not started'),worst.get('name',''),'' if worst.get('value') is None else f"{worst['value']:.6g}",'' if worst.get('margin') is None else f"{worst['margin']:+.4g}",worst.get('status','No requirements' if row.get('state')=='Complete' else '')]
            for j,value in enumerate(vals):self.case_table.setItem(i,j,QTableWidgetItem(value))
        if selected>=0:self.case_table.selectRow(selected)
        s=summary(m,self.run_manager.rows,self.case_metric.currentText());worst=s['worst'];self.case_summary.setText(f"{s['completed']}/{s['total']} complete · {s['passed']} pass · {s['failed']} fail · {s['errors']} measurement errors · pass / planned {s['yield']:.1%}"+(f" · Worst {worst['name']}: case {worst['case']}, margin {worst['margin']:+.5g}" if worst else ''))
        self.case_histogram.bins=s['bins'];self.case_histogram.update()
        if m['spec']['kind'] in ('sensitivity','optimization'):
            from .design_search import evaluate
            report=evaluate(m,self.run_manager.rows);details=[]
            for row in report.get('sensitivities',[]):details.append(f"{row['target']}: derivative {row['derivative']:.6g}"+(f", normalized {row['normalized']:.6g}" if row['normalized'] is not None else ''))
            if report.get('best'):details.append(f"Best passing sampled point: case {report['best']['case']}, {report['metric']} = {report['best']['value']:.6g}")
            if not report['complete']:details.append('Partial results; finish or retry all cases before applying values.')
            self.case_summary.setText(self.case_summary.text()+'\n'+'; '.join(details))
    def resume_cases(self):
        from .variation_runs import pending
        m=self.selected_manifest()
        if not m:return
        jobs=pending(m,self.run_manager.rows)
        from .run_environment import verify
        for job in jobs:verify(job)
        self.run_manager.enqueue_many(jobs,self.jobs_dir,[m['name']+' · '+str(j['case']['index'])+' · retry' for j in jobs]);self.refresh_cases()
    def stop_cases(self):
        m=self.selected_manifest()
        if m:self.run_manager.cancel([r for r in self.run_manager.rows if r['job'].get('case',{}).get('group')==m['id']])
    def open_case(self):
        from .variation_runs import latest
        m=self.selected_manifest()
        if not m:return
        row=latest(m,self.run_manager.rows).get(self.case_table.currentRow()+1)
        if not row or not row.get('result'):raise ValueError('Select a completed case. Failed cases have logs in Simulation Explorer.')
        self.follow_latest.setChecked(False);result=row['result'];index=next((i for i,r in enumerate(self.jobs) if r==result),None)
        if index is None:self.add_result(result)
        else:self.run_combo.setCurrentIndex(index)
        self.open_engineering_tab(self.spec_tab)
