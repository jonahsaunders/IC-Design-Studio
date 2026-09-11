"""A visible simulation plan, independent run history and offline help surfaces."""
import json, math, shutil, sys, time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QSplitter,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QSpinBox,QLineEdit,
    QPlainTextEdit,QDialog,QDialogButtonBox,QTextBrowser,QMessageBox,QScrollArea,QCheckBox)
from .model import clone, scalar, digest
from .run_manager import RunManager
from .workspace import ANALYSES
from .human_workspace import FlowLayout


class SimulationWorkspaceMixin:
    def make_ui(self):
        super().make_ui()
        self.run_manager=RunManager(self,max(1,min(8,self.settings.value('simulation/parallel',2,type=int))))
        self.run_manager.changed.connect(self.sync_runs);self.run_manager.completed.connect(self.simulation_finished)
        self._plan_hash=None;self._loading_plan=False
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(14,12,14,12);v.setSpacing(10)
        heading=QLabel('Simulation Explorer');heading.setProperty('role','title');v.addWidget(heading)
        note=QLabel('Build a run plan. Follow every job. Open completed waveforms while other simulations continue.');note.setWordWrap(True);note.setProperty('role','muted');v.addWidget(note)
        toolbar=QWidget();bar=FlowLayout(toolbar);v.addWidget(toolbar)
        for title,fn in [('Add current setup',self.add_simulation_setup),('Run enabled',self.run_enabled_setups),('Stop selected',self.stop_selected_runs),('Clear finished',self.clear_finished_runs)]:
            b=self.button(title,fn=lambda checked=False,fn=fn:self.guard(fn));bar.addWidget(b)
        bar.addWidget(QLabel('Parallel jobs'));self.parallel_jobs=QSpinBox();self.parallel_jobs.setRange(1,8);self.parallel_jobs.setValue(self.run_manager.limit);self.parallel_jobs.setAccessibleName('Maximum simultaneous simulation jobs');self.parallel_jobs.valueChanged.connect(self.set_parallel_jobs);bar.addWidget(self.parallel_jobs)
        split=QSplitter();v.addWidget(split,1)
        left=QWidget();lv=QVBoxLayout(left);lv.setContentsMargins(0,0,8,0);lv.addWidget(QLabel('ANALYSIS PLAN'))
        self.setup_table=self.simulation_table(['On','Setup','Analysis','Engine']);self.setup_table.setMinimumWidth(230);lv.addWidget(self.setup_table)
        self.setup_table.itemChanged.connect(self.setup_item_changed);self.setup_table.cellDoubleClicked.connect(lambda *_:self.edit_simulation_setup())
        tools=QHBoxLayout();lv.addLayout(tools)
        for title,fn in [('Edit',self.edit_simulation_setup),('Update',self.update_simulation_setup),('Rename',self.rename_simulation_setup),('Remove',self.remove_simulation_setup)]:tools.addWidget(self.button(title,fn=lambda checked=False,fn=fn:self.guard(fn)))
        self.setup_table.setToolTip('Edit opens the Inspector. Update saves its settings into the selected setup.');split.addWidget(left)
        right=QWidget();rv=QVBoxLayout(right);rv.setContentsMargins(4,0,0,0)
        statusrow=QHBoxLayout();rv.addLayout(statusrow);self.run_summary=QLabel('No runs yet');statusrow.addWidget(self.run_summary);statusrow.addStretch()
        self.simulation_runs=self.simulation_table(['Run','Analysis','Engine','Status','Progress','Elapsed','Revision']);self.simulation_runs.setSelectionMode(QAbstractItemView.ExtendedSelection);self.simulation_runs.setMinimumHeight(160);rv.addWidget(self.simulation_runs,1)
        self.simulation_runs.itemSelectionChanged.connect(self.show_run_details);self.simulation_runs.cellDoubleClicked.connect(lambda *_:self.open_selected_run())
        actionbar=QWidget();row=FlowLayout(actionbar);rv.addWidget(actionbar)
        for title,fn in [('Open waveforms',self.open_selected_run),('Rerun snapshot',self.rerun_snapshot),('Open analysis setup',self.run_dialog)]:row.addWidget(self.button(title,fn=lambda checked=False,fn=fn:self.guard(fn)))
        self.follow_latest=QCheckBox('Follow latest');self.follow_latest.setChecked(True);statusrow.addWidget(self.follow_latest)
        self.log_toggle=QCheckBox('Show log');statusrow.addWidget(self.log_toggle)
        self.simulation_details=QPlainTextEdit();self.simulation_details.setReadOnly(True);self.simulation_details.setMaximumHeight(90);self.simulation_details.setPlaceholderText('Select a run to inspect its saved input and progress log.');rv.addWidget(self.simulation_details);self.simulation_details.hide();self.log_toggle.toggled.connect(self.simulation_details.setVisible)
        split.addWidget(right);split.setStretchFactor(1,1);split.setSizes([345,650])
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page);scroll.setMinimumSize(120,100);self.simulation_tab=self.results_tabs.addTab(scroll,'Simulation Explorer')
        self.run_clock=QTimer(self);self.run_clock.setInterval(1000);self.run_clock.timeout.connect(self.sync_runs);self.run_clock.start()
        from .waveform_tools import WaveformTools
        self.waveform_tools=WaveformTools(self.plot,self)
        self.result_pages[0].layout().insertWidget(1,self.waveform_tools)
        self.fill_simulation_plan()

    def simulation_table(self,headers):
        table=QTableWidget(0,len(headers));table.setHorizontalHeaderLabels(headers);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.verticalHeader().hide();table.setAlternatingRowColors(True);table.setShowGrid(False);table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);table.horizontalHeader().setStretchLastSection(True);return table

    def make_actions(self):
        super().make_actions();menu=self.task_menus['Simulate'];menu.setTitle('&Analysis')
        self.explorer_action=self.action(menu,'Simulation Explorer',self.open_simulation_explorer,'Ctrl+Shift+A')
        menu.removeAction(self.explorer_action);menu.insertAction(menu.actions()[0],self.explorer_action)
        batch=self.action(menu,'Run enabled setups',self.run_enabled_setups,'Ctrl+F5')
        stop=self.action(menu,'Stop all simulations',lambda:self.run_manager.cancel(list(self.run_manager.rows)))
        markers=self.action(menu,'Waveform markers and limits',self.show_waveform_tools)
        setup=self.action(menu,'Analysis setup…',self.run_dialog)
        # Keep the first level focused on planning, running and stopping.
        menu.clear()
        for a in (self.explorer_action,setup):menu.addAction(a)
        menu.addSeparator()
        for a in (self.run_action,batch,self.cancel_action,stop):menu.addAction(a)
        menu.addSeparator()
        groups={
            'Testbenches':['Save / edit testbench…','Run saved testbench','Saved testbenches','ngspice device noise…'],
            'Studies':['Parameter sweep / PVT / Monte Carlo…','Rerun saved study','Configure saved-bench characterization…','Run saved-bench characterization'],
            'Post-layout':['Simulate extracted SPICE testbench…','Simulate with estimated parasitics'],
            'Engine setup':['Simulation runtime…','Engine diagnostics and paths…']}
        self.analysis_submenus={}
        for name,keys in groups.items():
            sub=menu.addMenu(name);self._new_submenus.append(sub);self.analysis_submenus[name]=sub
            for key in keys:
                if key in self.command_actions:sub.addAction(self.command_actions[key])
        wave=menu.addMenu('Waveforms');self._new_submenus.append(wave);wave.addAction(markers)
        wave.addAction(self.command_actions['Export waveform CSV…'])
        self.action(self.task_menus['Window'],'Simulation Explorer',self.open_simulation_explorer)
        self.cancel_action.setText('Stop selected simulation');self.reindex_commands()

    def open_simulation_explorer(self):
        self.results_dock.show();self.results_tabs.setCurrentIndex(self.simulation_tab)
        self.resizeDocks([self.results_dock],[500],Qt.Vertical)

    def show_waveform_tools(self):
        self.results_dock.show();self.results_tabs.setCurrentIndex(0);self.waveform_tools.open_manager()

    def current_analysis_settings(self):
        a=clone(self.project['analysis']);typ=self.analysis_type.currentData()
        a['engine']=self.analysis_engine.currentData()
        if typ not in ('tran','op','dc','ac','noise'):raise ValueError('Choose a circuit analysis first.')
        keys={'tran':{'stop','step'},'op':set(),'dc':{'dc_start','dc_stop','dc_step'},'ac':{'start','end','points'},'noise':{'start','end','points','temperature'}}[typ]
        a.update({k:self.analysis_fields[k].text().strip() for k in keys});a.update(type=typ,source=self.analysis_source.currentText(),points=int(a['points']),temperature=float(a['temperature']))
        self.validate_analysis_settings(a);return a

    def validate_analysis_settings(self,a):
        if not math.isfinite(float(a.get('temperature',27))):raise ValueError('Enter a finite temperature.')
        if a['type']=='tran':
            stop,step=scalar(a['stop']),scalar(a['step'])
            if not 0<step<=stop or stop/step>20000:raise ValueError('Use a positive time step and at most 20,000 steps.')
        elif a['type']=='dc':
            delta=scalar(a['dc_stop'])-scalar(a['dc_start']);step=scalar(a['dc_step'])
            if not a['source'] or step==0 or delta/step<0 or delta/step>5000:raise ValueError('Choose a source and a sweep step toward the stop value, with at most 5,001 points.')
        elif a['type'] in ('ac','noise'):
            if not 0<scalar(a['start'])<scalar(a['end']) or not 2<=int(a['points'])<=1000:raise ValueError('Use increasing positive frequencies and 2–1,000 points.')

    def prepare_simulation(self,settings,engine='builtin',project=None,cid=None):
        p=project or self.project;cid=cid or self.cid;self.validate_analysis_settings(settings)
        if settings['type'] in ('testbench','silicon','characterization') and settings.get('testbench'):
            from .testbenches import get
            t=get(p,settings['testbench']);cid=t['dut_cell' if settings['type']=='silicon' else 'bench_cell']
        job={'project':clone(p),'cell':cid,'settings':clone(settings),'engine':engine}
        if settings['type']=='silicon' and 'tools' not in settings:
            job['settings']['tools']={n:self.settings.value('engine/'+n,'') or shutil.which(n) or '' for n in ('magic','netgen','ngspice')}
        if engine=='ngspice':
            executable=self.settings.value('engine/ngspice','') or shutil.which('ngspice')
            if not executable or not Path(executable).is_file():raise ValueError('ngspice is not installed. Configure it in Tools → Engine diagnostics and paths.')
            job['executable']=str(executable)
        return job

    def start_job(self,settings,engine='builtin'):
        if self.process and self.process not in self.run_manager.processes:raise ValueError('Wait for the external command to finish first.')
        row=self.run_manager.enqueue(self.prepare_simulation(settings,engine),self.jobs_dir,ANALYSES.get(settings['type'],settings['type']))
        self.active_job=row['path'];self._job_state='running';self.open_simulation_explorer();self.sync_runs();return row

    def quick_run(self):
        if not self.flush_inspector():return
        try:
            a=self.current_analysis_settings();self.analysis_dirty=False
            if a!=self.project['analysis']:self.commit(lambda p:p.update(analysis=a),'Analysis settings')
            self.start_job(a,self.analysis_engine.currentData());self.analysis_error.hide()
        except Exception as exc:self.run_dialog();self.analysis_error.setText(str(exc));self.analysis_error.show()

    def set_parallel_jobs(self,value):
        self.run_manager.limit=value;self.settings.setValue('simulation/parallel',value);self.run_manager.pump()

    def sync_runs(self):
        if not hasattr(self,'simulation_runs'):return
        manager=self.run_manager;rows=manager.rows;selected={r['id'] for r in self.selected_simulation_runs()}
        # Keep the legacy busy surface for project lifecycle guards and CLI jobs.
        if self.process is None or any(self.process is r.get('process') for r in rows) or getattr(self,'_simulation_process',None) is self.process:
            self.process=manager.processes[0] if manager.processes else None;self._simulation_process=self.process
        self.simulation_runs.blockSignals(True);self.simulation_runs.setRowCount(len(rows))
        colors={'Complete':'#278461','Failed':'#d05b69','Cancelled':'#a17c3f','Running':'#468ce1','Queued':'#939daa','Stopping':'#cf933f','Interrupted':'#cf933f'}
        for i,row in enumerate(rows):
            elapsed=time.monotonic()-row['started'] if row.get('process') and row.get('started') else row['elapsed']
            values=[row['name'],ANALYSES.get(row['job']['settings']['type'],row['job']['settings']['type']),row['job']['engine'],row['state'],f"{row['progress']}%" if row['state'] in ('Running','Complete','Stopping') else '—',f'{elapsed:.1f} s','r'+str(row['job']['project']['revision'])]
            for j,value in enumerate(values):
                item=QTableWidgetItem(value);item.setData(Qt.UserRole,row['id']);item.setToolTip(value)
                if j==3:item.setForeground(QColor(colors.get(row['state'],'#939daa')))
                self.simulation_runs.setItem(i,j,item)
            if row['id'] in selected:
                for j in range(len(values)):self.simulation_runs.item(i,j).setSelected(True)
        self.simulation_runs.blockSignals(False)
        counts={state:sum(r['state']==state for r in rows) for state in ('Running','Queued','Complete','Failed','Cancelled')}
        self.run_summary.setText('  ·  '.join(f'{n} {state.lower()}' for state,n in counts.items() if n) or 'No runs yet');self.run_summary.setWordWrap(True)
        if hasattr(self,'run_action') and (manager.busy or not self.process):
            self.run_action.setEnabled(True);self.analysis_run.setEnabled(True);self.run_button.setText('Run');self.cancel_action.setEnabled(manager.busy)
            self.progress.setVisible(manager.busy)
            if manager.busy:self.progress.setValue(round(sum(r['progress'] for r in rows if r['state']=='Running')/max(1,counts['Running'])))
        if selected:self.show_run_details()

    def selected_simulation_runs(self):
        if not hasattr(self,'simulation_runs'):return []
        ids={it.data(Qt.UserRole) for it in self.simulation_runs.selectedItems()}
        return [r for r in self.run_manager.rows if r['id'] in ids]

    def show_run_details(self):
        rows=self.selected_simulation_runs()
        if not rows:self.simulation_details.clear();return
        row=rows[0];job=row['job'];text=f"{row['name']} · {row['state']} · saved revision {job['project']['revision']}\n"+json.dumps(job['settings'],ensure_ascii=False)+'\n'+row['log']
        if self.simulation_details.toPlainText()!=text:self.simulation_details.setPlainText(text)

    def simulation_finished(self,row,result):
        # Release a completed process before result callbacks inspect busy state.
        self.sync_runs();self._job_state='complete' if result is not None else row['state'].lower()
        if result is not None:
            previous=self.run_combo.currentIndex();follow=self.follow_latest.isChecked() or previous<0
            self.add_result(result)
            if not follow:self.run_combo.setCurrentIndex(previous)
            if not self.run_manager.busy and follow:
                index=self.characterization_tab if 'characterization_rows' in result else self.silicon_tab if 'silicon_report' in result else self.study_tab if 'study_rows' in result else 1 if 'physical_result' in result else 0
                self.results_tabs.setCurrentIndex(index)
        elif row['state']=='Failed':
            self.analysis_error.setText('Simulation failed. Select its run for the error log.');self.analysis_error.show();self.log_toggle.setChecked(True)
            self.simulation_runs.selectRow(self.run_manager.rows.index(row))
        self.console.appendPlainText(row['name']+' · '+row['state']+'\n'+row['log']);self.update_result_status()

    def update_result_status(self):
        state=getattr(self,'_job_state','idle')
        if state=='running':self._job_state='idle'
        super().update_result_status();self._job_state=state

    def cancel_job(self):
        if self.run_manager.busy:self.stop_selected_runs()
        else:super().cancel_job()

    def stop_selected_runs(self):
        rows=self.selected_simulation_runs()
        if not rows:rows=[r for r in self.run_manager.rows if r['state'] in ('Running','Queued')][-1:]
        self.run_manager.cancel(rows)

    def clear_finished_runs(self):
        self.run_manager.rows[:]=[r for r in self.run_manager.rows if r['state'] in ('Running','Queued','Stopping')];self.sync_runs()

    def open_selected_run(self):
        rows=self.selected_simulation_runs()
        if not rows:return
        result=rows[0].get('result')
        if result is None:self.statusBar().showMessage('This run has no completed result. Its log is shown below.',6000);return
        self.follow_latest.setChecked(False)
        i=next((i for i,r in enumerate(self.jobs) if r==result),None)
        if i is None:self.add_result(result)
        else:self.run_combo.setCurrentIndex(i)
        self.results_tabs.setCurrentIndex(0)

    def rerun_snapshot(self):
        for row in self.selected_simulation_runs():self.run_manager.enqueue(row['job'],self.jobs_dir,row['name']+' · rerun')

    def fill_simulation_plan(self):
        if not hasattr(self,'setup_table'):return
        setups=self.project.get('simulation_setups',[]);value=digest(setups)
        if value==self._plan_hash:return
        self._plan_hash=value;self._loading_plan=True;self.setup_table.setRowCount(len(setups))
        for i,s in enumerate(setups):
            item=QTableWidgetItem();item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if s.get('enabled',True) else Qt.Unchecked);self.setup_table.setItem(i,0,item)
            for j,text in enumerate([s['name'],ANALYSES.get(s['settings']['type'],s['settings']['type']),s['engine']],1):self.setup_table.setItem(i,j,QTableWidgetItem(text))
        self._loading_plan=False

    def setup_item_changed(self,item):
        if self._loading_plan or item.column()!=0:return
        i=item.row();enabled=item.checkState()==Qt.Checked
        self.commit(lambda p:p['simulation_setups'][i].update(enabled=enabled),'Enable simulation setup')

    def add_simulation_setup(self):
        if not self.flush_inspector():return
        settings=self.current_analysis_settings();number=len(self.project.get('simulation_setups',[]))+1
        setup={'name':ANALYSES[settings['type']]+' '+str(number),'cell':self.cid,'engine':self.analysis_engine.currentData(),'settings':settings,'enabled':True}
        self.commit(lambda p:p.setdefault('simulation_setups',[]).append(setup),'Add simulation setup');self.fill_simulation_plan();self.setup_table.selectRow(number-1)

    def edit_simulation_setup(self):
        i=self.setup_table.currentRow()
        if i<0:return
        if not self.flush_inspector():return
        s=self.project['simulation_setups'][i]
        if s['cell']!=self.cid:
            self.cid=s['cell'];self.selection=[];self.refresh()
        self.run_dialog();self._loading_analysis=True
        self.analysis_type.setCurrentIndex(self.analysis_type.findData(s['settings']['type']));self.analysis_engine.setCurrentIndex(self.analysis_engine.findData(s['engine']))
        for key,w in self.analysis_fields.items():w.setText(str(s['settings'][key]))
        self.analysis_source.setCurrentText(s['settings']['source']);self._loading_analysis=False;self.analysis_dirty=True;self.analysis_visibility()

    def rename_simulation_setup(self):
        from PySide6.QtWidgets import QInputDialog
        i=self.setup_table.currentRow()
        if i<0:return
        name,ok=QInputDialog.getText(self,'Rename analysis setup','Name',text=self.project['simulation_setups'][i]['name'])
        if ok and name.strip():self.commit(lambda p:p['simulation_setups'][i].update(name=name.strip()[:100]),'Rename simulation setup');self.fill_simulation_plan();self.setup_table.selectRow(i)

    def update_simulation_setup(self):
        i=self.setup_table.currentRow()
        if i<0:return
        settings=self.current_analysis_settings();engine=self.analysis_engine.currentData()
        self.commit(lambda p:p['simulation_setups'][i].update(settings=settings,engine=engine),'Update simulation setup');self.fill_simulation_plan();self.setup_table.selectRow(i)

    def remove_simulation_setup(self):
        i=self.setup_table.currentRow()
        if i>=0:self.commit(lambda p:p['simulation_setups'].pop(i),'Remove simulation setup');self.fill_simulation_plan()

    def run_enabled_setups(self):
        if not self.flush_inspector():return
        if self.process and self.process not in self.run_manager.processes:raise ValueError('Wait for the external command first.')
        setups=[s for s in self.project.get('simulation_setups',[]) if s.get('enabled',True)]
        if not setups:self.add_simulation_setup();setups=self.project.get('simulation_setups',[])
        # Validate every setup before starting any job in the batch.
        jobs=[(s,self.prepare_simulation(s['settings'],s['engine'],cid=s['cell'])) for s in setups]
        for s,job in jobs:self.run_manager.enqueue(job,self.jobs_dir,s['name'])
        self.open_simulation_explorer()

    def refresh(self,fit=False):
        super().refresh(fit);self.fill_simulation_plan()

    def set_project(self,p,path=None):
        if hasattr(self,'run_manager') and self.run_manager.busy:raise ValueError('Stop the active jobs before switching projects.')
        self.plot.set_result(None)
        super().set_project(p,path);self.run_manager.load(self.jobs_dir,self.project['id']);self.fill_simulation_plan();self.follow_latest.setChecked(True)

    def apply_workspace_preset(self,name):
        super().apply_workspace_preset(name)
        if name=='Simulation' and hasattr(self,'simulation_tab'):self.open_simulation_explorer()

    def closeEvent(self,event):
        if self.run_manager.busy:
            answer=QMessageBox.question(self,'Simulations running','Stop all queued and running simulations and close?',QMessageBox.Yes|QMessageBox.No)
            if answer!=QMessageBox.Yes:event.ignore();return
            self.run_manager.cancel(list(self.run_manager.rows))
            for proc in list(self.run_manager.processes):
                if not proc.waitForFinished(3000):proc.kill();proc.waitForFinished(1000)
        super().closeEvent(event)

    def open_editor_doc(self,name):
        if name.startswith('CAPABILITY_MATRIX'):return self.compatibility_matrix()
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]));path=root/'docs'/name
        dlg=QDialog(self);dlg.setWindowTitle(name.replace('_',' ').removesuffix('.md'));dlg.resize(900,640);v=QVBoxLayout(dlg)
        search=QLineEdit();search.setPlaceholderText('Find in this document…');v.addWidget(search);browser=QTextBrowser();browser.setOpenExternalLinks(True);browser.document().setBaseUrl(QUrl.fromLocalFile(str(path.parent)+'/'));browser.setMarkdown(path.read_text(encoding='utf-8') if path.exists() else 'This document is unavailable. Open Help → Compatibility matrix for built-in capability information.');v.addWidget(browser)
        def find(text):browser.moveCursor(QTextCursor.Start);browser.find(text)
        search.textChanged.connect(find);buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(dlg.close);v.addWidget(buttons);self._document_dialog=dlg;dlg.show()

    def compatibility_matrix(self):
        from .compatibility import ROWS
        dlg=QDialog(self);dlg.setWindowTitle('Compatibility matrix');dlg.resize(1000,620);v=QVBoxLayout(dlg)
        note=QLabel('Supported exchange paths and their practical limits. External tools require installation and the appropriate technology files.');note.setWordWrap(True);v.addWidget(note)
        search=QLineEdit();search.setPlaceholderText('Filter by tool, workflow or capability…');v.addWidget(search)
        table=self.simulation_table(['Tool','Workflow','Support','Scope and limits']);table.setWordWrap(True);table.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch);v.addWidget(table)
        def fill(text=''):
            rows=[r for r in ROWS if text.casefold() in ' '.join(r).casefold()];table.setRowCount(len(rows))
            for i,row in enumerate(rows):
                for j,value in enumerate(row):table.setItem(i,j,QTableWidgetItem(value))
            table.resizeRowsToContents()
        search.textChanged.connect(fill);fill();buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(dlg.close);v.addWidget(buttons);self._compatibility_dialog=dlg;self.compatibility_table=table;self.compatibility_search=search;dlg.show();QTimer.singleShot(0,table.resizeRowsToContents)
