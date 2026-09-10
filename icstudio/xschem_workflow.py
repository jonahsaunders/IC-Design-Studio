"""Direct open, component editing and multi-analysis waveform navigation."""
import json,re
from pathlib import Path
from PySide6.QtCore import Qt,QPointF,QUrl,QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPlainTextEdit,QDialog,QDialogButtonBox,QFileDialog,QComboBox,QTableWidgetItem,QAbstractItemView,QListWidget,QListWidgetItem,QSpinBox)
from .model import clone,device,uid,digest,load_project,validate
from .xschem_runtime import compatible,find_ngspice,probes,read_plot
from .xschem_project import properties,records


class XschemWorkflowMixin:
    def make_ui(self):
        super().make_ui();self._xschem_rows=[];self._xschem_run_path=None;self._xschem_case_signature=None
        installed=self.settings.value('engine/ngspice','');executable=find_ngspice(installed)
        if executable and str(Path(str(installed).strip('"')).resolve())!=executable:self.settings.setValue('engine/ngspice',executable)
        page,v=self.engineering_page('Program analyses','Each analysis inside a simulation program appears here. Open a completed waveform while later cases continue.')
        self.xschem_case_summary=QLabel('Run an imported simulation program to populate this table.');self.xschem_case_summary.setWordWrap(True);v.addWidget(self.xschem_case_summary)
        self.engineering_buttons(v,[('Run program',self.quick_run),('Edit simulation program',self.edit_xschem_program),('Open selected waveform',self.open_xschem_case),('Open output files',self.open_xschem_outputs)])
        self.xschem_case_table=self.simulation_table(['Case','Analysis','Conditions','State','Samples','Specifications']);self.xschem_case_table.cellDoubleClicked.connect(lambda *_:self.guard(self.open_xschem_case));v.addWidget(self.xschem_case_table)
        self.xschem_measurements=self.simulation_table(['Measurement','Value','Details']);self.xschem_measurements.setMaximumHeight(160);v.addWidget(self.xschem_measurements);self.xschem_measurements.hide();self.xschem_case_table.itemSelectionChanged.connect(self.show_xschem_measurements)
        self.xschem_tab=self.add_engineering_tab(page,'Program analyses');self.result_groups[0][1].append(self.xschem_tab)
        self.xschem_case_clock=QTimer(self);self.xschem_case_clock.setInterval(1200);self.xschem_case_clock.timeout.connect(self.refresh_xschem_cases);self.xschem_case_clock.start()
        self.simulation_runs.itemSelectionChanged.connect(self.refresh_xschem_cases)
        self.xschem_controls=QWidget();form=QVBoxLayout(self.xschem_controls);form.setContentsMargins(0,0,0,0)
        note=QLabel('Runs the schematic’s saved ngspice program, including its loops, measurements and output files.');note.setWordWrap(True);form.addWidget(note)
        form.addWidget(self.button('Edit simulation program…',fn=lambda:self.guard(self.edit_xschem_program)))
        form.addWidget(QLabel('Waveforms to retain'));self.xschem_probes=QLineEdit();self.xschem_probes.setPlaceholderText('v(vref) v(avdd) i(vdd)');self.xschem_probes.setAccessibleName('Waveforms to retain');form.addWidget(self.xschem_probes)
        self.xschem_timeout=QSpinBox();self.xschem_timeout.setRange(1,1440);self.xschem_timeout.setSuffix(' minutes');self.xschem_timeout.setValue(240);form.addWidget(QLabel('Maximum runtime'));form.addWidget(self.xschem_timeout)
        self.analysis_run.parentWidget().layout().insertWidget(3,self.xschem_controls);self.xschem_controls.hide()
        self.xschem_probes.textChanged.connect(self.analysis_changed);self.xschem_timeout.valueChanged.connect(self.analysis_changed)
        self.xschem_plot_combo=QComboBox();self.xschem_plot_combo.setAccessibleName('Analysis waveform');self.xschem_plot_combo.currentIndexChanged.connect(self.select_xschem_plot);self.result_pages[0].layout().insertWidget(2,self.xschem_plot_combo);self.xschem_plot_combo.hide()

    def make_actions(self):
        super().make_actions()
        menu=self.task_menus['Simulate'];self.action(menu,'Program analyses',lambda:self.open_engineering_tab(self.xschem_tab));self.action(menu,'Edit simulation program…',self.edit_xschem_program)
        self.action(self.task_menus['Help'],'Included Xschem libraries',lambda:self.open_editor_doc('UPDATE_0.18.md'));self.reindex_commands()
        self.action(self._task_submenus['File/Examples'],'Xschem multi-analysis program',self.open_xschem_program_example);self.reindex_commands()

    def open_xschem_program_example(self):
        import sys
        from .xschem_workspace import show_review
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]));return show_review(self,root/'examples/xschem-analysis/rc-program.sch',[],auto_open=True)

    def open_project(self):
        path,_=QFileDialog.getOpenFileName(self,'Open project or schematic',str(self.path.parent) if self.path else '','Projects and Xschem schematics (*.icproj *.sch);;IC Studio project (*.icproj);;Xschem schematic (*.sch)')
        if not path:return
        if Path(path).suffix.lower()=='.sch':
            from .xschem_workspace import show_review
            return show_review(self,path,auto_open=True)
        p=load_project(path)
        if self.maybe_save():self.set_project(p,path)

    def export_spice(self):
        if not compatible(self.project):return super().export_spice()
        from .xschem_runtime import netlist
        from .model import atomic_write
        directory=QFileDialog.getExistingDirectory(self,'Export SPICE circuit and model files')
        if not directory:return
        target=Path(directory)/(self.project['name']+'-spice')
        if target.exists() and any(target.iterdir()):raise ValueError('The export folder already contains files. Choose another destination.')
        netlist(self.project,target);self.statusBar().showMessage('Exported source.cir and its model files to '+str(target),12000)

    def set_project(self,p,path=None):
        self._xschem_case_signature=None;self._xschem_run_path=None;self._xschem_rows=[]
        super().set_project(p,path)
        if hasattr(self,'xschem_probes'):
            self.xschem_probes.setText(p.get('analysis',{}).get('probes') or (probes(p) if compatible(p) else ''));self.xschem_timeout.setValue(max(1,int(p.get('analysis',{}).get('timeout',14400))//60));self.analysis_dirty=False
            self.refresh_xschem_cases()
        if compatible(p):self.statusBar().showMessage('Xschem project opened · symbols and models are saved inside the project',12000)

    def refresh(self,fit=False):
        super().refresh(fit)
        if compatible(self.project):
            lock=self.project['xschem_exchange'].get('library_lock',{});variant=lock.get('variant')
            self.tech_name.setText((variant or 'Xschem')+' · simulation libraries');self.tech_detail.setText('Included model files · preserved device parameters');self.analysis_visibility()

    def load_analysis(self):
        super().load_analysis()
        if compatible(self.project):
            self._loading_analysis=True;self.analysis_type.setCurrentIndex(self.analysis_type.findData('xschem'));self.analysis_engine.setCurrentIndex(self.analysis_engine.findData('ngspice'));self._loading_analysis=False;self.analysis_dirty=False
        self.analysis_visibility()

    def analysis_visibility(self,*args):
        super().analysis_visibility(*args)
        if not hasattr(self,'xschem_controls'):return
        from .engine_selection import requirement
        active=compatible(self.project);self.xschem_controls.setVisible(active);self.analysis_engine.setEnabled(not requirement(self.project));self.analysis_type.setEnabled(not active)
        self.analysis_caption.setText('Model files and original device parameters are preserved. Measurements are reported by ngspice.' if active else 'Generic circuit models. Configure an external engine in Analysis → Engine setup.')

    def current_analysis_settings(self):
        if compatible(self.project):return {**clone(self.project['analysis']),'type':'xschem','probes':self.xschem_probes.text().strip() or probes(self.project),'timeout':self.xschem_timeout.value()*60}
        return super().current_analysis_settings()

    def prepare_simulation(self,settings,engine='builtin',project=None,cid=None):
        p=project or self.project
        if compatible(p):
            if settings.get('type')!='xschem':raise ValueError('Run the imported simulation program. Its analysis setup is available in the Inspector.')
            executable=find_ngspice(self.settings.value('engine/ngspice',''))
            if not executable:raise ValueError('The ngspice runtime is missing. Extract the complete Windows app or source package, including icstudio/assets/runtime/ngspice. For another installation, choose ngspice in Analysis → Engine setup, or set ICSTUDIO_NGSPICE to its executable.')
            job={'project':clone(p),'cell':p['top'],'settings':clone(settings),'engine':'ngspice','executable':executable}
            from .run_environment import stamp
            job['environment']=stamp(job);return job
        return super().prepare_simulation(settings,engine,project,cid)

    def edit_xschem_properties(self,ident=None):
        if not self.flush_inspector():return
        ident=ident or next((d['id'] for d in self.cell['devices'] if d['id'] in self.selection and d.get('xschem')),None)
        d=next((d for c in self.project['cells'] for d in c['devices'] if d['id']==ident and d.get('xschem')),None)
        if d is None:raise ValueError('Select an imported Xschem component first.')
        dlg=QDialog(self);dlg.setWindowTitle('Xschem properties · '+d['name']);dlg.resize(760,600);v=QVBoxLayout(dlg);v.addWidget(QLabel(d['xschem']['reference']))
        props=clone(d['xschem']['properties']);props['name']=d['name'];program=d['xschem']['kind']=='netlist_commands'
        if program:
            editor=QPlainTextEdit(props.get('value',''));editor.setAccessibleName('ngspice simulation program');editor.setLineWrapMode(QPlainTextEdit.NoWrap);v.addWidget(editor,1)
        else:
            table=self.simulation_table(['Property','Value']);table.setEditTriggers(QAbstractItemView.DoubleClicked|QAbstractItemView.EditKeyPressed|QAbstractItemView.AnyKeyPressed);keys=[k for k in props if k not in ('studio_id','format')];table.setRowCount(len(keys))
            for i,key in enumerate(keys):
                item=QTableWidgetItem(key);item.setFlags(item.flags()&~Qt.ItemIsEditable);table.setItem(i,0,item);table.setItem(i,1,QTableWidgetItem(props[key]))
            v.addWidget(table,1)
        error=QLabel();error.setWordWrap(True);v.addWidget(error);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);v.addWidget(buttons)
        def save():
            try:
                values={**props,'value':editor.toPlainText()} if program else {**props,**{key:table.item(i,1).text() for i,key in enumerate(keys)}}
                def change(p):
                    obj=next(d for c in p['cells'] for d in c['devices'] if d['id']==ident);obj['xschem']['properties']=values;obj['name']=values.get('name',obj['name']);obj['symbol_context']={**values,'symname':Path(obj['xschem']['reference']).stem}
                self.commit(change,'Edit Xschem properties');dlg.accept()
            except Exception as exc:error.setText(str(exc))
        buttons.accepted.connect(save);buttons.rejected.connect(dlg.reject);dlg.editor=editor if program else table;self._xschem_property_dialog=dlg;dlg.show();return dlg

    def edit_xschem_program(self):
        programs=[d for c in self.project['cells'] for d in c['devices'] if d.get('xschem',{}).get('kind')=='netlist_commands']
        if not programs:raise ValueError('Open an Xschem schematic with a simulation program, or place a code_shown component from the library.')
        if len(programs)==1:return self.edit_xschem_properties(programs[0]['id'])
        from PySide6.QtWidgets import QInputDialog
        name,ok=QInputDialog.getItem(self,'Simulation program','Program',[d['name'] for d in programs],0,False)
        if ok:return self.edit_xschem_properties(next(d['id'] for d in programs if d['name']==name))

    def show_library(self):
        if not compatible(self.project):return super().show_library()
        from .xschem_libraries import ASSETS
        dlg=QDialog(self);dlg.setWindowTitle('Place Xschem component');dlg.resize(640,580);v=QVBoxLayout(dlg);search=QLineEdit();search.setPlaceholderText('Search included symbols…');v.addWidget(search);listing=QListWidget();v.addWidget(listing)
        for folder,title in [(ASSETS/'gf180mcu/symbols','GF180MCU'),(ASSETS/'xschem/devices','Xschem')]:
            for path in sorted(folder.glob('*.sym')):
                item=QListWidgetItem(path.stem+'  ·  '+title);item.setData(Qt.UserRole,str(path));listing.addItem(item)
        search.textChanged.connect(lambda text:[listing.item(i).setHidden(text.casefold() not in listing.item(i).text().casefold()) for i in range(listing.count())])
        def place(item):
            if item:self.begin_xschem_placement(item.data(Qt.UserRole));dlg.accept()
        listing.itemDoubleClicked.connect(lambda item:self.guard(lambda:place(item)));v.addWidget(self.button('Place selected',fn=lambda:self.guard(lambda:place(listing.currentItem()))))
        def custom():
            path,_=QFileDialog.getOpenFileName(dlg,'Choose symbol','','Xschem symbol (*.sym)')
            if path:self.begin_xschem_placement(path);dlg.accept()
        v.addWidget(self.button('Choose another symbol file…',fn=lambda:self.guard(custom)));self._xschem_library_dialog=dlg;dlg.show()

    def begin_placement(self,index):
        if not compatible(self.project):return super().begin_placement(index)
        from .xschem_libraries import ASSETS
        self.begin_xschem_placement(ASSETS/'xschem/devices'/['','res.sym','capa.sym','ind.sym','vsource.sym','isource.sym','nmos4.sym','pmos4.sym'][index])

    def begin_xschem_placement(self,path):
        from .xschem_compat import CaptureReader
        path=Path(path).resolve();reader=CaptureReader(path,[path.parent],None);symbol,attrs=reader.symbol(path);props=properties(attrs.get('template',''));kind=attrs.get('type','')
        if kind in ('label','ipin','opin','iopin'):raise ValueError('Use the Net label or Ground tool to place labels.')
        if kind=='subcircuit' and not attrs.get('spice_sym_def') and attrs.get('spice_primitive')!='true':raise ValueError('Import the schematic containing this hierarchical symbol so its child cell is included.')
        name=props.get('name','X1');prefix=re.sub(r'\d+$','',name);number=1;names={d['name'].casefold() for d in self.cell['devices']}
        while (prefix+str(number)).casefold() in names:number+=1
        name=prefix+str(number);props['name']=name;info={'record_index':-1,'reference':path.name,'symbol_path':str(path),'properties':props,'original_properties':clone(props),'symbol':clone(symbol),'kind':kind,'missing':False,'native_symbol_hash':digest(symbol)}
        d=device('XS',name,0,0,symbol=clone(symbol),nets={p:'open' for p in symbol['pin_order']},xschem=info,symbol_context={**props,'symname':path.stem});d['_source_assets']={str(p):data for p,data in reader.files.items()}
        if kind=='netlist_commands':d['symbol']['primitives']=[{'kind':'rect','points':[[0,0],[180,45]]},{'kind':'text','points':[[8,8],[170,35]],'text':'@name: simulation program','font_size':9}]
        self.mode_combo.setCurrentIndex(0);self.cancel_tool();self.schematic.placement=d;self.schematic.tool='place';self.schematic.drag=self.schematic.snap(self.schematic.model(self.schematic.rect().center()));self.schematic.setFocus();self.schematic.update();self.tool_hint.setText('Place '+name+' · R rotates · Esc cancels')

    def place_device_at(self,x,y):
        if not compatible(self.project) or not self.schematic.placement:return super().place_device_at(x,y)
        d=clone(self.schematic.placement);assets=d.pop('_source_assets',{});d.update(id=uid(),x=x,y=y);self.cancel_tool()
        def change(p):
            c=next(c for c in p['cells'] if c['id']==self.cid);c['devices'].append(d);p['xschem_exchange']['source_files'].update(assets)
            from .wiring import rebuild
            rebuild(c,p)
        self.commit(change,'Place '+d['name']);self.select([d['id']],'schematic');self.reveal_properties();self.schematic.setFocus()

    def refresh_xschem_cases(self):
        if not hasattr(self,'xschem_case_table'):return
        selected=self.selected_simulation_runs();rows=[r for r in (selected or self.run_manager.rows[::-1]) if r['job']['settings']['type'] in ('xschem','program')];row=rows[0] if rows else None
        path=Path(row['path']) if row else None;file=path/'cases.json' if path else None
        if not file or not file.is_file():
            if self._xschem_run_path!=path:self.xschem_case_table.setRowCount(0);self._xschem_rows=[];self._xschem_run_path=path
            return
        signature=(str(path),file.stat().st_mtime_ns)
        if signature==self._xschem_case_signature:return
        try:data=json.loads(file.read_text())
        except (OSError,ValueError):return
        self._xschem_case_signature=signature;self._xschem_run_path=path;self._xschem_rows=data['cases'];current=self.xschem_case_table.currentRow();self.xschem_case_table.setRowCount(len(self._xschem_rows))
        for i,case in enumerate(self._xschem_rows):
            state=case['state']
            if state=='Running' and row['state'] in ('Failed','Cancelled','Interrupted'):state=row['state']
            for j,value in enumerate((case['number'],case['analysis'].upper(),case['context'],state,case.get('points',''),case.get('spec_status','—'))):self.xschem_case_table.setItem(i,j,QTableWidgetItem(str(value)))
        if current>=0:self.xschem_case_table.selectRow(current)
        done=sum(c['state']=='Complete' for c in self._xschem_rows);self.xschem_case_summary.setText(f"{row['name']} · {done}/{data['total']} analyses captured · {row.get('result',{}).get('program_status',row['state'])}")

    def show_xschem_measurements(self):
        i=self.xschem_case_table.currentRow();items=self._xschem_rows[i].get('measurements',[]) if 0<=i<len(self._xschem_rows) else [];self.xschem_measurements.setVisible(bool(items));self.xschem_measurements.setRowCount(len(items))
        for row,item in enumerate(items):
            for col,value in enumerate((item['name'],f"{item['value']:.12g}",item.get('details',''))):self.xschem_measurements.setItem(row,col,QTableWidgetItem(value))

    def open_xschem_case(self):
        i=self.xschem_case_table.currentRow()
        if not 0<=i<len(self._xschem_rows):return
        case=self._xschem_rows[i]
        if case['state']!='Complete':raise ValueError('Wait for this analysis to finish before opening its waveform.')
        row=next(r for r in self.run_manager.rows if Path(r['path'])==self._xschem_run_path)
        if row.get('result'):
            self.add_result(clone(row['result']));self.select_xschem_case_data(case['number'])
        else:
            from .model import design_digest,now
            p=row['job']['project'];plot=read_plot(self._xschem_run_path/case['file']);result={'schema':1,'created':now(),'engine':'ngspice · active program','project_id':p['id'],'revision':p['revision'],'design_hash':design_digest(p),'cell_id':row['job']['cell'],'settings':row['job']['settings'],'warnings':[],'log':row['log'],'xschem_cases':clone(self._xschem_rows),'case_directory':str(self._xschem_run_path),'active_case':case['number'],**plot};self.add_result(result)
        self.follow_latest.setChecked(False);self.results_tabs.setCurrentIndex(0)

    def select_run(self,index):
        super().select_run(index)
        if not hasattr(self,'xschem_plot_combo'):return
        self.xschem_plot_combo.blockSignals(True);self.xschem_plot_combo.clear();cases=(self.result or {}).get('analysis_cases',(self.result or {}).get('xschem_cases',[]))
        for case in cases:
            if case['state']=='Complete':self.xschem_plot_combo.addItem(f"Case {case['number']} · {case['analysis'].upper()} · {case['context']}",case['number'])
        self.xschem_plot_combo.setCurrentIndex(self.xschem_plot_combo.findData((self.result or {}).get('active_case')));self.xschem_plot_combo.setVisible(bool(cases));self.xschem_plot_combo.blockSignals(False)

    def select_xschem_plot(self,index):
        if index>=0:self.guard(lambda:self.select_xschem_case_data(self.xschem_plot_combo.itemData(index)))

    def select_xschem_case_data(self,number):
        result=self.result
        if not result or not result.get('analysis_cases',result.get('xschem_cases')):return
        case=next(c for c in result.get('analysis_cases',result.get('xschem_cases',[])) if c['number']==number);path=Path(result['case_directory'])/case['file'];plot=read_plot(path)
        result={**result,**plot,'active_case':number}
        if case.get('specifications'):result['specifications']=case['specifications']
        elif result.get('specifications'):
            from .specifications import evaluate_rows
            result['specifications']=evaluate_rows(result['specifications'],result)
        self.jobs[self.run_combo.currentIndex()]=result;self.select_run(self.run_combo.currentIndex())

    def open_xschem_outputs(self):
        if not self._xschem_run_path:raise ValueError('Select a simulation program run first.')
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._xschem_run_path)))
