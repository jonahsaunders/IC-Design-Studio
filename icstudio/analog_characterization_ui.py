"""Reusable isolated-device tables and reviewable sizing suggestions."""
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QFormLayout,QComboBox,QLineEdit,QCheckBox,QTableWidgetItem,QTabWidget
from .analog_widgets import label,scroll,actions,table,fill
from .model import scalar,clone,design_digest
from . import analog_characterization as library,analog_optimizer as opt,variation_runs
from .plot import WavePlot


class CharacterizationLibrary(QDialog):
    def __init__(self,page):
        super().__init__(page);self.page=page;self.studio=page.studio;self.project_id=self.studio.project['id'];self.manifest=None;self.data=None;self.estimates=[]
        self.setWindowTitle('Device characterization library');self.resize(1050,920);self.setMinimumSize(700,550)
        root=QVBoxLayout(self);self.tabs=QTabWidget();root.addWidget(self.tabs);body=QWidget();layout=QVBoxLayout(body);self.tabs.addTab(scroll(body),'Characterize')
        layout.addWidget(label('Characterize an isolated device once, then reuse its model-specific data for initial sizing. Circuit search verifies the resulting design.'))
        form=QFormLayout();form.setRowWrapPolicy(QFormLayout.WrapLongRows);layout.addLayout(form)
        self.cell=QComboBox();self.device=QComboBox();self.engine=QComboBox();self.engine.addItem('Built-in teaching solver','builtin');self.engine.addItem('ngspice','ngspice')
        for c in self.studio.project['cells']:self.cell.addItem(c['name'],c['id'])
        self.cell.setCurrentIndex(max(0,self.cell.findData(self.studio.cid)))
        for title,w in [('Device cell',self.cell),('MOS instance',self.device),('Simulator',self.engine)]:form.addRow(label(title,w),w)
        self.cell.currentIndexChanged.connect(self.devices);self.devices()
        self.sweeps={};defaults=dict(length='0.5u, 1u',vgs='0.5, 0.6, 0.7, 0.8, 0.9, 1.0',vds='1.0, 1.8',vsb='0',temperature='27',corner='nominal')
        for key,title in [('length','Lengths (m)'),('vgs','Forward VGS / VSG (V)'),('vds','Forward VDS / VSD (V)'),('vsb','Reverse body bias (V)'),('temperature','Temperatures (°C)'),('corner','Model corners')]:
            w=QLineEdit(defaults[key]);self.sweeps[key]=w;form.addRow(label(title+' · comma separated',w),w)
        layout.addWidget(label('SI suffixes are accepted (0.5u = 0.5 µm). Process library: standard SKY130 1.8 V MOS, one finger and one device. Generic teaching tables omit weak inversion and body/temperature effects.'))
        actions(layout,[('Characterize / reuse cache',self.start),('Cancel remaining',self.cancel),('Resume unfinished',self.resume)],self.call,'Characterize / reuse cache')
        self.history=QComboBox();self.history.setAccessibleName('Saved device characterizations');layout.addWidget(label('Saved characterization',self.history));layout.addWidget(self.history);self.history.currentIndexChanged.connect(self.select_history)
        self.results=table(['State','gm/Id (1/V)','Id/W (A/m)','Forward VGS (V)','L (m)','Condition']);self.results.setAccessibleName('Captured model characterization points');layout.addWidget(self.results)
        self.plot=WavePlot();self.plot.dark=self.studio.dark;self.plot.setAccessibleName('Measured gm/Id for the selected length and bias slice');layout.addWidget(self.plot)
        self.results.itemSelectionChanged.connect(self.select_point)
        sizing=QWidget();layout=QVBoxLayout(sizing);self.tabs.addTab(scroll(sizing),'Size and transfer');layout.addWidget(label('Select a characterized bias slice, enter your gm/Id and current targets, then review the suggested dimensions. Width scaling is an initial estimate that needs circuit verification.'))
        query_form=QFormLayout();query_form.setRowWrapPolicy(QFormLayout.WrapLongRows);layout.addLayout(query_form);self.query={}
        for key,title,value in [('length','Sizing length (m)','0.5u'),('vds','Forward drain bias (V)','1.0'),('vsb','Reverse body bias (V)','0'),('temperature','Sizing temperature (°C)','27'),('corner','Sizing corner','nominal'),('gmid','Target gm/Id (1/V)','10'),('current','Target |Id| (A)','10u')]:
            w=QLineEdit(value);self.query[key]=w;query_form.addRow(label(title,w),w)
        self.suggestions=table(['Estimated W (m)','L (m)','Forward gate bias (V)','Target |Id| (A)','Target gm/Id (1/V)']);self.suggestions.setAccessibleName('Initial sizing alternatives requiring circuit verification');self.suggestions.setColumnWidth(2,205);layout.addWidget(self.suggestions)
        actions(layout,[('Estimate sizing',self.estimate),('Use selected sizing in search',self.seed),('Inspect selected saved point',self.inspect)],self.call,'Estimate sizing');layout.addStretch()
        self.note=label('Select a device and characterize its bias grid.');root.addWidget(self.note)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(200);self.timer.timeout.connect(self.refresh);self.studio.run_manager.changed.connect(self.schedule)
        self.load_history()

    def call(self,fn):
        try:
            if self.studio.project['id']!=self.project_id:raise ValueError('The project changed. Reopen the characterization library.')
            self.page.workspace.require_saved_setup();return fn()
        except Exception as exc:self.note.setText(str(exc))

    def devices(self,*_):
        self.device.clear();self.device.addItems(opt.device_names(self.studio.project,self.cell.currentData()))

    def schedule(self):
        if not self.timer.isActive():self.timer.start()

    def load_history(self,selected=None):
        self.saved=[m for m in variation_runs.load(self.studio.jobs_dir,self.project_id) if m.get('library')]
        self.history.blockSignals(True);self.history.clear()
        for m in self.saved:self.history.addItem(m['name']+' · '+m['created'],m['id'])
        self.history.setCurrentIndex(max(0,self.history.findData(selected)));self.history.blockSignals(False);self.select_history()

    def select_history(self,*_):
        self.manifest=next((m for m in self.saved if m['id']==self.history.currentData()),None);self.data=None;self.estimates=[];self.suggestions.setRowCount(0);self.refresh()

    def start(self):
        if not self.studio.flush_inspector():return
        if not self.device.currentText():raise ValueError('Choose a MOS device, or add a teaching DUT with Guided design setup.')
        spec={k:[v.strip() for v in w.text().split(',') if v.strip()] for k,w in self.sweeps.items()};spec['engine']=self.engine.currentData()
        m=library.prepare(self.studio.project,self.cell.currentData(),self.device.currentText(),spec,self.studio.prepare_simulation)
        cached=library.load_cache(m['library']['key'],self.studio.jobs_dir)
        if cached:
            self.manifest=m;self.data=cached;self.estimates=[];self.suggestions.setRowCount(0);self.render();self.note.setText('Reused a matching model/engine cache. No simulations were queued.');return
        variation_runs.save(m,self.studio.jobs_dir);self.page.enqueue(m,m['jobs']);self.load_history(m['id'])

    def refresh(self):
        if not self.manifest:return
        # Cached rows may originate in another project. Their saved values remain
        # readable, but inspection is offered only if the originating run exists.
        if self.data and self.data['complete']:return
        self.data=library.collect(self.manifest,self.studio.run_manager.rows)
        if self.data['complete']:library.save_cache(self.data,self.studio.jobs_dir)
        self.render()

    def render(self):
        if not self.data:return
        selected=self.results.currentRow();self.results.blockSignals(True)
        fill(self.results,[[p['status'],p.get('values',{}).get('gmid'),p.get('values',{}).get('current_density'),p['condition']['vgs'],p['condition']['length'],f"VDS {p['condition']['vds']:g} V · VSB {p['condition']['vsb']:g} V · {p['condition']['temperature']:g} °C · {p['condition']['corner']}"] for p in self.data['points']])
        for col,width in enumerate((80,115,130,145,90,250)):self.results.setColumnWidth(col,width)
        if 0<=selected<self.results.rowCount():self.results.selectRow(selected)
        self.results.blockSignals(False)
        passed=sum(p['status']=='Passed' for p in self.data['points']);self.note.setText(f"{passed}/{len(self.data['points'])} valid measured points. "+('Table saved for model-matched reuse.' if self.data['complete'] else 'Characterization running; failed or missing points remain visible.'))
        if selected<0 and self.results.rowCount():self.results.selectRow(0)

    def select_point(self):
        i=self.results.currentRow()
        if not self.data or not 0<=i<len(self.data['points']):return
        point=self.data['points'][i];condition=point['condition']
        for key in ('length','vds','vsb','temperature','corner'):self.query[key].setText(str(condition[key]))
        rows=[p for p in self.data['points'] if all(p['condition'][k]==condition[k] for k in ('length','vds','vsb','temperature','corner'))]
        segments=[];current=[]
        for p in sorted(rows,key=lambda p:p['condition']['vgs']):
            if p.get('values'):current.append((p['condition']['vgs'],p['values']['gmid']))
            elif current:segments.append(current);current=[]
        if current:segments.append(current)
        datasets=[dict(x=[p[0] for p in segment],traces={'gm/Id':[p[1] for p in segment]},settings={'type':'dc'},x_label='Forward VGS / VSG (V)',plot_unit='1/V') for segment in segments]
        self.plot.set_result(datasets[0] if datasets else None,['gm/Id'],overlays=datasets[1:])
        if point.get('error'):self.note.setText(point['error'])

    def estimate(self):
        if not self.data:raise ValueError('Characterize a device or choose a saved table first.')
        query={k:w.text().strip() for k,w in self.query.items()}
        self.estimates=library.size(self.data,query,query['gmid'],query['current'])
        fill(self.suggestions,[[e[k] for k in ('width','length','vgs','desired_current','desired_gmid')] for e in self.estimates]);self.suggestions.selectRow(0)
        self.tabs.setCurrentIndex(1)
        self.note.setText('Initial estimates from interpolation at the requested L and bias. Multiple crossings are separate choices. Circuit search must verify width scaling and the actual bias.')

    def seed(self):
        i=self.suggestions.currentRow()
        if not 0<=i<len(self.estimates):raise ValueError('Estimate sizing and select one alternative first.')
        m=self.manifest
        if design_digest(self.studio.project)!=m['base_design_hash']:raise ValueError('The circuit changed. Choose the current device and reuse or regenerate its matching table before transferring sizing.')
        geometry=opt.device_geometry(self.studio.project,m['cell_id'],m['library']['source_device']);name=m['library']['source_device'].rsplit('/',1)[-1];point=self.estimates[i];page=self.page
        page.parameter_cell.setCurrentIndex(page.parameter_cell.findData(geometry['cell_id']));page.axes.setRowCount(0);page.seed_values={}
        for key,value in [('w',point['width']),('l',point['length'])]:
            page.add_axis();r=page.axes.rowCount()-1;target=name+'.params.'+key;page.axes.cellWidget(r,0).setCurrentText(target)
            for j,text in enumerate((str(value*.8),str(value*1.2),'11',''),1):page.axes.setItem(r,j,QTableWidgetItem(text))
            page.seed_values[target]=value
        page.strategy.setCurrentIndex(page.strategy.findData('adaptive'));page.modes.setCurrentIndex(0);page.workspace.tabs.setCurrentIndex(4)
        self.note.setText(f"Sizing range copied to Circuit search. Suggested forward VGS/VSG={point['vgs']:.6g} V; set the appropriate DUT bias in the editable fixture. The circuit is unchanged.")

    def inspect(self):
        i=self.results.currentRow()
        if not self.data or not 0<=i<len(self.data['points']):raise ValueError('Select a measured point.')
        point=self.data['points'][i];row=next((r for r in self.studio.run_manager.rows if r['id'] in point['run_ids']),None)
        if not row:raise ValueError('This reusable table retains values and provenance, but its original run is not loaded in this project.')
        from .analog_run_ui import RunInspector
        self.inspector=RunInspector(self.studio,row);self.inspector.show()

    def cancel(self):
        if self.manifest:self.studio.run_manager.cancel(list(opt.evaluate(self.manifest,self.studio.run_manager.rows)['current'].values()))

    def resume(self):
        if self.manifest:
            variation_runs.save(self.manifest,self.studio.jobs_dir)
            self.data=None;self.page.enqueue(self.manifest,variation_runs.pending(self.manifest,self.studio.run_manager.rows));self.schedule()
