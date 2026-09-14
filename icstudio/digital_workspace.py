"""Docked cell views, implementation controls, and connected digital inspection."""
from __future__ import annotations

import json
import re
from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPen, QBrush, QTextCursor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QCheckBox,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QDialog,QDialogButtonBox,QFormLayout,
    QLineEdit,QPlainTextEdit,QFileDialog,QInputDialog,QGraphicsView,QGraphicsScene,QGraphicsItem)

from . import digital_design as design
from .model import clone, scalar

TOOL_NAMES=('iverilog','vvp','verilator','verilator_coverage','yosys','eqy','sby','bitwuzla','sta','openroad','make','klayout')


def table(columns):
    widget=QTableWidget(0,len(columns));widget.setHorizontalHeaderLabels(columns)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers);widget.setSelectionBehavior(QAbstractItemView.SelectRows)
    widget.setShowGrid(False);widget.setAlternatingRowColors(True);widget.verticalHeader().hide()
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);widget.horizontalHeader().setStretchLastSection(True)
    return widget


def fill(widget,rows,fields):
    widget.setRowCount(len(rows))
    for i,row in enumerate(rows):
        for j,key in enumerate(fields):
            value=row.get(key);item=QTableWidgetItem('—' if value is None else f'{value:.6g}' if isinstance(value,float) else str(value))
            item.setData(Qt.UserRole,row);widget.setItem(i,j,item)


from .digital_physical_view import PhysicalView


class Workspace:
    def __init__(self,window,root):
        self.window=window;self.current_key=None;self.index=[]
        bar=QHBoxLayout();root.insertLayout(0,bar);bar.addWidget(QLabel('Cell'))
        self.cells=QComboBox();self.cells.setAccessibleName('Digital cell library');bar.addWidget(self.cells,1)
        self.cells.currentIndexChanged.connect(lambda:self.window.attempt(lambda:self.switch_cell(self.cells.currentData())))
        for title,fn in [('New RTL cell…',self.new_cell),('Schematic',lambda:self.open_view(False)),('Layout',lambda:self.open_view(True)),
                         ('Publish symbol',self.publish),('Attach routed GDS',self.attach_layout)]:
            self.button(bar,title,fn)
        controls=QHBoxLayout();root.insertLayout(2,controls)
        self.button(controls,'Platform…',self.import_platform);self.button(controls,'Constraints…',self.constraints)
        self.button(controls,'Floorplan…',self.physical_settings);self.button(controls,'Test cases…',self.test_cases)
        self.button(controls,'Jobs folder…',self.jobs_folder)
        self.coverage=QCheckBox('Line coverage');controls.addWidget(self.coverage);self.coverage.toggled.connect(self.coverage_changed)
        self.use_selected=QCheckBox('Use selected mapped run');self.use_selected.setToolTip('Bind the selected mapped netlist or resume a compatible physical checkpoint.');controls.addWidget(self.use_selected)
        self.platform=QLabel();self.platform.setWordWrap(True);root.insertWidget(3,self.platform)
        self.views=table(['Cell view','State / revision']);window.tabs.addTab(self.views,'Cell views')
        self.views.cellDoubleClicked.connect(lambda row,col:self.window.attempt(lambda:self.open_bound_view(row)))
        self.diagnostics=table(['Source','Line','Severity','Diagnostic']);window.result_tabs.addTab(self.diagnostics,'Diagnostics')
        self.diagnostics.cellDoubleClicked.connect(lambda row,col:self.jump(self.diagnostics.item(row,0).data(Qt.UserRole)))
        self.netlist=table(['Module','Object','Kind','Cell type']);window.result_tabs.addTab(self.netlist,'Netlist browser')
        self.netlist.cellClicked.connect(lambda row,col:self.probe(self.netlist.item(row,0).data(Qt.UserRole)))
        self.timing=table(['Corner','Check','Startpoint','Endpoint','Slack (ns)'])
        self.timing.cellClicked.connect(lambda row,col:self.probe_path(self.timing.item(row,0).data(Qt.UserRole)))
        self.proof=table(['Partition','Status','Strategies']);window.result_tabs.addTab(self.proof,'Equivalence')
        self.proof.setToolTip('Double-click a partition to open its counterexample waveform, when available.')
        self.proof.cellDoubleClicked.connect(lambda row,col:window.attempt(lambda:self.open_proof(self.proof.item(row,0).data(Qt.UserRole))))
        physical_page=QWidget();self.physical_page=physical_page;pv=QVBoxLayout(physical_page);self.physical_note=QLabel();self.physical_note.setWordWrap(True);pv.addWidget(self.physical_note)
        self.physical=PhysicalView(self)
        filters=QHBoxLayout();pv.addLayout(filters)
        for label,key,checked in (('Cells','cells',True),('Routes','routes',True),('Density','density',False)):
            check=QCheckBox(label);check.setChecked(checked);check.toggled.connect(lambda value,k=key:self.physical.set_filters(**{k:value}));filters.addWidget(check)
        self.layers=QComboBox();self.layers.addItem('All layers','');self.layers.currentIndexChanged.connect(lambda:self.physical.set_filters(layer=self.layers.currentData() or ''));filters.addWidget(self.layers)
        self.button(filters,'Fit',self.physical.fit)
        self.physical_search=QLineEdit();self.physical_search.setPlaceholderText('Find instance or net…');self.physical_search.returnPressed.connect(lambda:self.physical.find(self.physical_search.text()));pv.addWidget(self.physical_search)
        pv.addWidget(self.physical);window.result_tabs.addTab(physical_page,'Physical')
        from PySide6.QtWidgets import QSplitter
        self.timing_split=QSplitter(Qt.Vertical);self.linked_physical=PhysicalView(self);self.timing_split.addWidget(self.timing);self.timing_split.addWidget(self.linked_physical)
        # Construct directly in the splitter: reparenting an inactive tab retains
        # Qt's explicit hidden state and collapses the timing table to zero height.
        window.result_tabs.insertTab(5,self.timing_split,'Timing');self.timing_split.setSizes([250,450])
        self.regression=table(['Test','Simulator','Status','Line coverage (%)','Error']);window.result_tabs.addTab(self.regression,'Regression')
        self.regression.cellDoubleClicked.connect(lambda row,col:window.attempt(lambda:self.open_case(self.regression.item(row,0).data(Qt.UserRole))))
        self.coverage_table=table(['Source','Line','Hits']);window.result_tabs.addTab(self.coverage_table,'Coverage')
        self.coverage_table.cellDoubleClicked.connect(lambda row,col:self.jump(self.coverage_table.item(row,0).data(Qt.UserRole)))
        self.comparison=table(['Run','Stage','State','Verdict','Cells','Area (µm²)','Δ area','Setup slack (ns)','Δ setup','Hold slack (ns)','Power estimate (W)','Δ power'])
        self.comparison.setToolTip('Deltas require the same stage, technology, constraints, synthesis settings, timing corners, parasitic mode and engine environment.')
        window.result_tabs.addTab(self.comparison,'Compare runs')
        window.signals.itemDoubleClicked.connect(lambda item:self.find_signal(item.text()))

    def button(self,layout,title,callback):
        b=QPushButton(title);b.clicked.connect(lambda checked=False:self.window.attempt(callback));layout.addWidget(b);return b

    def tools(self):return {name:self.window.studio.settings.value('engine/'+name,'') for name in TOOL_NAMES}

    def refresh_design(self):
        w=self.window;self.cells.blockSignals(True);self.cells.clear()
        for c in w.studio.project['cells']:self.cells.addItem(c['name']+(' · RTL' if design.config(w.studio.project,c['id']) else ''),c['id'])
        self.cells.setCurrentIndex(self.cells.findData(w.cell_id));self.cells.blockSignals(False)
        fill(self.views,design.views(w.studio.project,w.cell_id),['name','state'])
        platform=(w.config or {}).get('platform',{})
        revision=platform.get('revision','')
        self.platform.setText(platform.get('name','No digital platform selected')+' · '+platform.get('corner','')+' · '+revision[:20])
        self.platform.setToolTip(revision)
        self.coverage.blockSignals(True);self.coverage.setChecked((w.config or {}).get('coverage',False));self.coverage.blockSignals(False)

    def switch_cell(self,cid):
        w=self.window
        if not cid or cid==w.cell_id:return
        if w.dirty and not w.apply():return
        w.cell_id=cid;w.display_key=None;self.current_key=None;w.load_sources();w.refresh_runs()
        if hasattr(w,'flow'):w.flow.restore()
        if hasattr(w,'shell'):w.shell.key=None;w.shell.refresh()

    def new_cell(self):
        from .digital import counter_project
        w=self.window;name,ok=QInputDialog.getText(w,'New RTL cell','Cell name')
        if not ok:return
        source=clone((w.config or counter_project()['digital']));source.pop('platform',None)
        created=[];w.studio.commit(lambda p:created.append(design.new_cell(p,name,source)),'Create RTL cell')
        if created:self.switch_cell(created[0])

    def open_view(self,layout):
        w=self.window
        if w.dirty and not w.apply():return
        w.studio.leave_digital_workspace()
        w.studio.cid=w.cell_id;w.studio.selection=[];w.studio.mode_combo.setCurrentIndex(1 if layout else 0);w.studio.refresh(True)

    def open_bound_view(self,row):
        w=self.window;record=self.views.item(row,0).data(Qt.UserRole)
        if record['name']=='Schematic':return self.open_view(False)
        if record['name']=='Layout':return self.open_view(True)
        if record['name']=='RTL':w.reveal_source();return
        if record.get('directory'):
            match=next((r for r in w.studio.run_manager.rows if str(r['path'])==record['directory']),None)
            if not match:raise ValueError('The saved view run is unavailable. Restore its captured run folder.')
            w.runs.setCurrentIndex(w.runs.findData(match['id']));w.reveal_results()

    def publish(self):
        w=self.window
        if not w.apply():return
        row=w.selected_run()
        if not row or not row.get('result'):raise ValueError('Select a completed elaboration or synthesis run first.')
        symbol,interface=design.interface_proposal(w.studio.project,w.cell_id,row['result'],row['path'])
        c=design.cell(w.studio.project,w.cell_id)
        if c['ports'] and c['ports']!=symbol['pin_order']:
            from .interface_ui import InterfaceReview
            def finalize(candidate):
                design.cell(candidate,w.cell_id)['digital_interface']=interface
                design.bind_result(candidate,w.cell_id,row['result'],row['path'],'Netlist')
            dialog=InterfaceReview(w.studio,w.cell_id,symbol,c.get('symbol'),self.refresh_design,finalize)
            dialog.exec()
        else:
            w.studio.commit(lambda p:design.publish_interface(p,w.cell_id,row['result'],row['path']),'Publish digital cell symbol')
            self.refresh_design()
        w.message.setText('Published interface uses scalar electrical terminals with bus metadata. Open Cell views to inspect its symbol.')

    def attach_layout(self):
        w=self.window;row=w.selected_run()
        if not row or not row.get('result'):raise ValueError('Select a completed physical run first.')
        from .digital_flow import validate_result
        validate_result(row['result'],row['path']);data=row['result']['digital_result']
        from .digital_identity import current
        if not current(data,design.config(w.studio.project,w.cell_id)):raise ValueError('The physical result is stale. Implement the current inputs before attaching it.')
        record=data['artifacts'].get('gds')
        if not record:raise ValueError('Run Finish / GDS before attaching the physical macro.')
        from .digital_layout import attach
        w.studio.commit(lambda p:attach(p,w.cell_id,row['result'],row['path']),'Attach implemented digital macro')
        self.open_view(True)

    def export_macro(self):
        row=self.window.selected_run()
        if not row or not row.get('result'):raise ValueError('Select a completed Finish / GDS run.')
        path,_=QFileDialog.getSaveFileName(self.window,'Export implemented macro','','Macro bundle (*.zip)')
        if path:
            from .digital_macro import export
            export(row['result'],row['path'],path)
            self.window.message.setText('Exported macro geometry, terminals, netlist, constraints, parasitics and provenance.')

    def import_platform(self):
        from .digital_platform import from_orfs,read_manifest
        w=self.window
        if not w.config:raise ValueError('Open or import an RTL cell first.')
        choice,ok=QInputDialog.getItem(w,'Digital platform','Import source',['ORFS sky130hd','ORFS nangate45','Platform JSON manifest'],0,False)
        if not ok:return
        if choice.startswith('ORFS'):
            path=QFileDialog.getExistingDirectory(w,'Choose OpenROAD Flow Scripts checkout',w.studio.settings.value('digital/orfs',''))
            if not path:return
            platform=from_orfs(path,choice.split()[1]);w.studio.settings.setValue('digital/orfs',path)
        else:
            path,_=QFileDialog.getOpenFileName(w,'Choose platform manifest','','JSON (*.json)')
            if not path:return
            platform=read_manifest(path)
        if len(platform['corners'])>1:
            corner,ok=QInputDialog.getItem(w,'Library corner','Corner',list(platform['corners']),0,False)
            if not ok:return
            platform['corner']=corner
        w.config['platform']=platform;w.edited();self.refresh_design()

    def form(self,title,fields):
        d=QDialog(self.window);d.setWindowTitle(title);root=QVBoxLayout(d);form=QFormLayout();root.addLayout(form);edits={}
        for key,label,value in fields:
            edit=QLineEdit(str(value));edit.setAccessibleName(label);form.addRow(label,edit);edits[key]=edit
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);root.addWidget(buttons)
        buttons.accepted.connect(d.accept);buttons.rejected.connect(d.reject)
        return {key:edit.text() for key,edit in edits.items()} if d.exec() else None

    def constraints(self):
        from .digital_constraints_ui import ConstraintEditor
        w=self.window
        if not w.config:raise ValueError('Open an RTL cell first.')
        w.sync_file();dialog=ConstraintEditor(w,w.config)
        if dialog.exec() and dialog.value:
            w.config=dialog.value;w.loading=True;w.file_index=-1;w.files.clear()
            w.files.addItems([f['path'] for f in w.config['files']]);w.loading=False
            w.files.setCurrentRow(next(i for i,f in enumerate(w.config['files']) if f['role']=='constraint'))
            w.edited();w.reveal_source()

    def physical_settings(self):
        from .digital_physical_ui import PhysicalEditor
        w=self.window
        if not w.config:raise ValueError('Open an RTL cell first.')
        dialog=PhysicalEditor(w,w.config.get('physical',{}))
        if dialog.exec() and dialog.value:
            w.config['physical']=dialog.value;w.edited()

    def jobs_folder(self):
        w=self.window
        if w.studio.run_manager.busy:raise ValueError('Finish or stop current jobs before changing their folder.')
        path=QFileDialog.getExistingDirectory(w,'Jobs folder',str(w.studio.jobs_dir))
        if path:
            w.studio.jobs_dir=Path(path);w.studio.settings.setValue('digital/jobs_dir',path)
            w.studio.run_manager.load(w.studio.jobs_dir,w.project_id);w.refresh_runs()

    def coverage_changed(self,value):
        if self.window.config:self.window.config['coverage']=value;self.window.edited()

    def test_cases(self):
        from .digital_regression import validate_tests
        w=self.window
        if not w.config:raise ValueError('Open an RTL cell first.')
        dialog=QDialog(w);dialog.setWindowTitle('Digital regression cases');dialog.resize(850,450);layout=QVBoxLayout(dialog)
        note=QLabel('Each case selects a testbench and simulator. Definitions are a JSON object. Assertions must fail the testbench on a mismatch.');note.setWordWrap(True);layout.addWidget(note)
        cases=clone(w.config.get('tests',[{'name':'Default test','testbench':w.config.get('testbench',''),'simulator':'icarus'}]))
        grid=QTableWidget(0,5);grid.setHorizontalHeaderLabels(['Name','Testbench','Simulator','Definitions (JSON)','Coverage']);grid.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);layout.addWidget(grid)
        def add(case=None):
            case=case or {'name':'Test '+str(grid.rowCount()+1),'testbench':w.config.get('testbench','')};row=grid.rowCount();grid.insertRow(row)
            for col,value in enumerate((case['name'],case['testbench'],case.get('simulator','icarus'),json.dumps(case.get('defines',{})))):grid.setItem(row,col,QTableWidgetItem(value))
            item=QTableWidgetItem();item.setCheckState(Qt.Checked if case.get('coverage') else Qt.Unchecked);grid.setItem(row,4,item)
        for case in cases:add(case)
        bar=QHBoxLayout();layout.addLayout(bar);self.button(bar,'Add case',add);self.button(bar,'Remove case',lambda:grid.removeRow(grid.currentRow()))
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec():
            cases=[{'name':grid.item(i,0).text(),'testbench':grid.item(i,1).text(),'simulator':grid.item(i,2).text(),
                    'defines':json.loads(grid.item(i,3).text()),'coverage':grid.item(i,4).checkState()==Qt.Checked} for i in range(grid.rowCount())]
            validate_tests(cases);w.config['tests']=cases;w.edited()

    def show_diagnostics(self,row):
        from .digital_reports import diagnostics
        rows=diagnostics(row['log'],(self.window.config or {}).get('files',[]))
        fill(self.diagnostics,rows,['path','line','severity','message'])

    def show_result(self,row):
        key=(row['id'],row['state']) if row else None
        if key==self.current_key:return
        self.current_key=key;self.index=[]
        for widget in (self.netlist,self.timing,self.proof,self.regression,self.coverage_table):widget.setRowCount(0)
        self.physical.load(None);self.linked_physical.load(None);self.physical_note.clear()
        if not row or not row.get('result'):return
        data=row['result']['digital_result'];artifacts=data['artifacts']
        if 'netlist_index' in artifacts:
            self.index=json.loads((row['path']/artifacts['netlist_index']['path']).read_text())
            fill(self.netlist,self.index[:20000],['module','name','kind','type'])
        fill(self.timing,data.get('timing',{}).get('paths',[]),['corner','check','startpoint','endpoint','slack_ns'])
        fill(self.proof,data.get('equivalence',{}).get('partitions',[]),['partition','status','strategies'])
        if 'layout_preview' in artifacts:
            preview=json.loads((row['path']/artifacts['layout_preview']['path']).read_text());self.physical.load(preview);self.linked_physical.load(preview)
            self.layers.blockSignals(True);self.layers.clear();self.layers.addItem('All layers','')
            for layer in self.physical.layers:self.layers.addItem(layer,layer)
            self.layers.blockSignals(False)
            self.physical_note.setText(preview['scope']+f" {len(preview['components'])} instances · {len(preview['segments'])} segments.")
        cases=[{**case,'percent':(case.get('coverage') or {}).get('percent')} for case in data.get('regression',{}).get('cases',[])]
        fill(self.regression,cases,['name','simulator','status','percent','error'])
        coverage=[{'path':file['path'],**line} for file in data.get('coverage',{}).get('files',[]) for line in file['lines']]
        fill(self.coverage_table,coverage[:20000],['path','line','hits'])
        target=self.timing_split if 'timing' in data else self.proof if 'equivalence' in data else self.regression if 'regression' in data else self.physical.parentWidget() if 'physical' in data else None
        if target:self.window.result_tabs.setCurrentWidget(target)

    def refresh_comparison(self):
        from .digital_reports import compare_results
        rows=[r for r in self.window.studio.run_manager.rows if r['job']['settings'].get('type')=='digital' and r['job']['cell']==self.window.cell_id]
        fill(self.comparison,compare_results(rows),['name','stage','state','verdict','cells','area_um2','area_um2_delta','setup_worst_slack_ns','setup_worst_slack_ns_delta','hold_worst_slack_ns','power_w','power_w_delta'])

    def jump(self,location):
        if hasattr(self.window, 'shell'):
            self.window.shell.show_captured(location)
            return
        w=self.window;path=location.get('path','');files=(w.config or {}).get('files',[])
        index=next((i for i,f in enumerate(files) if path==f['path'] or path.endswith('/'+f['path'])),None)
        if index is None:w.message.setText('This location is outside the captured RTL sources.');return
        w.files.setCurrentRow(index);block=w.editor.document().findBlockByLineNumber(max(0,int(location.get('line',1))-1))
        if block.isValid():w.editor.setTextCursor(QTextCursor(block));w.editor.centerCursor()
        w.reveal_source()

    def probe(self,item):
        if hasattr(self.window,'shell'):
            from .digital_inspection import Selection
            row=self.window.selected_run()
            selection=Selection(row['id'] if row else '',self.window.cell_id,item['module'],item['name'],item['kind'])
            self.window.shell.inspect(item,selection)
        self.physical.highlight([item['name']], [item['name']] if item['kind']=='net' else [])
        self.linked_physical.highlight([item['name']], [item['name']] if item['kind']=='net' else [])
        if item.get('locations'):self.jump(item['locations'][0])
        else:self.window.message.setText('No retained RTL source location for '+item['name']+'.')

    def probe_object(self,name):
        item=next((x for x in self.index if x['name']==name and x['kind']=='cell'),None)
        if item:self.probe(item)

    def probe_path(self,path):
        names={pin.rsplit('/',1)[0] for pin in path.get('pins',[]) if '/' in pin};self.physical.highlight(names);self.linked_physical.highlight(names)
        self.window.message.setText(path['startpoint']+' → '+path['endpoint']+f" · {path['slack_ns']:.6g} ns slack")
        if hasattr(self.window,'shell'):
            shell=self.window.shell;shell.selection_title.setText(path['check'].title()+' timing path')
            shell.selection_details.setPlainText('\n'.join([path['startpoint'],'→ '+path['endpoint'],f"Slack: {path['slack_ns']:.6g} ns",'','Path pins:',*path.get('pins',[])]))
            # Keep the timing table visible. A linked physical pane can be opened explicitly.

    def find_signal(self,name):
        from .digital_inspection import sources_for_signal
        candidates=sources_for_signal(self.index,name)
        if len(candidates)==1 and candidates[0].get('locations'):return self.jump(candidates[0]['locations'][0])
        if len(candidates)>1:
            self.window.message.setText('Multiple hierarchy matches. Select the intended object in the hierarchy navigator.');return
        short=re.sub(r'\[.*\]$','',name.rsplit('.',1)[-1])
        row=self.window.selected_run()
        captured=design.config(row['job']['project'],row['job']['cell']) if row else self.window.config
        for file in (captured or {}).get('files',[]):
            if file['role']=='rtl':
                for line,text in enumerate(file['text'].splitlines(),1):
                    if re.search(r'\b'+re.escape(short)+r'\b',text):
                        self.jump({'path':file['path'],'line':line});self.window.message.setText('Source search match for '+short);return

    def open_case(self,case):
        w=self.window;row=w.selected_run();path=row['path']/case['directory']
        if not (path/'result.json').is_file():
            w.wave.set_data(None);w.signals.clear();w.report.setPlainText(case.get('error','No result'));w.result_tabs.setCurrentWidget(w.report)
            if (path/'input.json').is_file():
                job=json.loads((path/'input.json').read_text());cfg=design.config(job['project'],job['cell'])
                from .digital import validate_config
                validate_config(cfg)
                trace=path/'sources'/cfg.get('waveform','wave.vcd')
                if trace.is_file():
                    from .digital_waveform import read_vcd
                    self.show_waveform(read_vcd(trace));w.message.setText(case['name']+' · failed test; waveform ends at the failure')
            return
        from .job_store import read_result
        result=read_result(path/'result.json',w.project_id);artifact=result['digital_result']['artifacts'].get('waveform')
        if artifact:
            from .digital_trace_store import open_waveform
            self.show_waveform(open_waveform(path/artifact['path']));w.message.setText(case['name']+' · '+case['status'])

    def show_waveform(self,waveform):
        w=self.window;w.wave.cursor=0;w.wave.cursor_b=0;w.wave.zoom=1;w.wave.set_data(waveform)
        w.signals.blockSignals(True);w.signals.clear()
        from PySide6.QtWidgets import QListWidgetItem
        for index,signal in enumerate(waveform['signals']):
            item=QListWidgetItem(signal['name']);item.setData(Qt.UserRole,index);item.setCheckState(Qt.Checked if index<12 else Qt.Unchecked);w.signals.addItem(item)
        w.signals.blockSignals(False);w.result_tabs.setCurrentIndex(0)

    def open_proof(self,partition):
        w=self.window;row=w.selected_run()
        from .digital_flow import validate_result
        validate_result(row['result'],row['path'])
        traces=[v for key,v in row['result']['digital_result']['artifacts'].items() if key.startswith('counterexample_') and partition['partition'] in Path(v['path']).parts]
        if not traces:w.message.setText('No counterexample trace was produced for '+partition['partition']+'. Inspect its proof log.');return
        from .digital_waveform import read_vcd
        self.show_waveform(read_vcd(row['path']/traces[0]['path']));w.message.setText('EQY counterexample · '+partition['partition'])
