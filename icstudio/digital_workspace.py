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

TOOL_NAMES=('iverilog','vvp','verilator','verilator_coverage','yosys','eqy','sta','openroad','make','klayout')


def table(columns):
    widget=QTableWidget(0,len(columns));widget.setHorizontalHeaderLabels(columns)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers);widget.setSelectionBehavior(QAbstractItemView.SelectRows)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);widget.horizontalHeader().setStretchLastSection(True)
    return widget


def fill(widget,rows,fields):
    widget.setRowCount(len(rows))
    for i,row in enumerate(rows):
        for j,key in enumerate(fields):
            value=row.get(key);item=QTableWidgetItem('—' if value is None else f'{value:.6g}' if isinstance(value,float) else str(value))
            item.setData(Qt.UserRole,row);widget.setItem(i,j,item)


class PhysicalView(QGraphicsView):
    def __init__(self,workspace):
        super().__init__();self.workspace=workspace;self.setScene(QGraphicsScene(self));self.objects={}
        self.setDragMode(QGraphicsView.ScrollHandDrag);self.setAccessibleName('Physical placement and signal routing')
        self.scene().selectionChanged.connect(self.selected)

    def load(self,data):
        self.scene().clear();self.objects={}
        if not data:return
        x1,y1,x2,y2=data['die'];self.scene().addRect(QRectF(x1,-y2,x2-x1,y2-y1),QPen(QColor('#92a0b8'),0))
        for component in data['components'][:20000]:
            item=self.scene().addRect(QRectF(component['x'],-component['y']-component['height'],component['width'],component['height']),
                                      QPen(QColor('#51c9b5'),0),QBrush(QColor('#245b58')))
            item.setData(0,component['name']);item.setToolTip(component['name']+'\n'+component['master']);item.setFlag(QGraphicsItem.ItemIsSelectable)
            self.objects[component['name']]=item
        for segment in data['segments'][:50000]:
            a,b=segment['points'];item=self.scene().addLine(a[0],-a[1],b[0],-b[1],QPen(QColor('#ae90e8'),0))
            item.setToolTip(segment['net']+' · '+segment['layer'])
        self.fitInView(self.scene().itemsBoundingRect(),Qt.KeepAspectRatio)

    def highlight(self,names):
        self.scene().blockSignals(True);self.scene().clearSelection()
        for name in names:
            item=self.objects.get(name)
            if item:item.setSelected(True)
        self.scene().blockSignals(False)

    def selected(self):
        items=self.scene().selectedItems()
        if items:self.workspace.probe_object(items[0].data(0))

    def wheelEvent(self,event):
        factor=1.2 if event.angleDelta().y()>0 else 1/1.2;self.scale(factor,factor)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.objects:self.fitInView(self.scene().itemsBoundingRect(),Qt.KeepAspectRatio)


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
        self.timing=table(['Check','Startpoint','Endpoint','Slack (ns)']);window.result_tabs.addTab(self.timing,'Timing')
        self.timing.cellClicked.connect(lambda row,col:self.probe_path(self.timing.item(row,0).data(Qt.UserRole)))
        self.proof=table(['Partition','Status','Strategies']);window.result_tabs.addTab(self.proof,'Equivalence')
        self.proof.setToolTip('Double-click a partition to open its counterexample waveform, when available.')
        self.proof.cellDoubleClicked.connect(lambda row,col:window.attempt(lambda:self.open_proof(self.proof.item(row,0).data(Qt.UserRole))))
        physical_page=QWidget();pv=QVBoxLayout(physical_page);self.physical_note=QLabel();self.physical_note.setWordWrap(True);pv.addWidget(self.physical_note)
        self.physical=PhysicalView(self);pv.addWidget(self.physical);window.result_tabs.addTab(physical_page,'Physical')
        self.regression=table(['Test','Simulator','Status','Line coverage (%)','Error']);window.result_tabs.addTab(self.regression,'Regression')
        self.regression.cellDoubleClicked.connect(lambda row,col:window.attempt(lambda:self.open_case(self.regression.item(row,0).data(Qt.UserRole))))
        self.coverage_table=table(['Source','Line','Hits']);window.result_tabs.addTab(self.coverage_table,'Coverage')
        self.coverage_table.cellDoubleClicked.connect(lambda row,col:self.jump(self.coverage_table.item(row,0).data(Qt.UserRole)))
        self.comparison=table(['Run','Stage','State','Verdict','Cells','Area (µm²)','Δ area','Setup slack (ns)','Δ setup','Hold slack (ns)','Power estimate (W)','Δ power'])
        self.comparison.setToolTip('Deltas use the earliest completed run at the same stage with the same platform and corner.')
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
        w.studio.cid=w.cell_id;w.studio.selection=[];w.studio.mode_combo.setCurrentIndex(1 if layout else 0);w.studio.refresh(True)

    def open_bound_view(self,row):
        w=self.window;record=self.views.item(row,0).data(Qt.UserRole)
        if record['name']=='Schematic':return self.open_view(False)
        if record['name']=='Layout':return self.open_view(True)
        if record['name']=='RTL':w.tabs.setCurrentIndex(0);return
        if record.get('directory'):
            match=next((r for r in w.studio.run_manager.rows if str(r['path'])==record['directory']),None)
            if not match:raise ValueError('The saved view run is unavailable. Restore its captured run folder.')
            w.runs.setCurrentIndex(w.runs.findData(match['id']));w.tabs.setCurrentIndex(1)

    def publish(self):
        w=self.window
        if not w.apply():return
        row=w.selected_run()
        if not row or not row.get('result'):raise ValueError('Select a completed elaboration or synthesis run first.')
        w.studio.commit(lambda p:design.publish_interface(p,w.cell_id,row['result'],row['path']),'Publish digital cell symbol')
        self.refresh_design();self.open_view(False)

    def attach_layout(self):
        w=self.window;row=w.selected_run()
        if not row or not row.get('result'):raise ValueError('Select a completed physical run first.')
        from .digital_flow import validate_result
        validate_result(row['result'],row['path']);data=row['result']['digital_result']
        if data['source_hash']!=design.identity(w.studio.project,w.cell_id):raise ValueError('The physical result is stale. Implement the current inputs before attaching it.')
        record=data['artifacts'].get('gds')
        if not record:raise ValueError('Run Finish / GDS before attaching the physical macro.')
        from .digital_layout import attach
        w.studio.commit(lambda p:attach(p,w.cell_id,row['result'],row['path']),'Attach implemented digital macro')
        self.open_view(True)

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
        w=self.window
        if not w.config:raise ValueError('Open an RTL cell first.')
        values=self.form('Generate clock and I/O constraints',[
            ('port','Clock port','clk'),('name','Clock name','core_clk'),('period','Period (ns)',10),
            ('inputs','Input port patterns','reset'),('input_delay','Input delay (ns)',1),
            ('outputs','Output port patterns','count*'),('output_delay','Output delay (ns)',1)])
        if values is None:return
        from .engines import tcl_word
        period=scalar(values['period'])
        if period<=0:raise ValueError('The clock period must be positive.')
        lines=['create_clock -name '+tcl_word(values['name'])+' -period '+str(period)+' [get_ports '+tcl_word(values['port'])+']']
        for direction in ('input','output'):
            patterns=values[direction+'s'].split();delay=scalar(values[direction+'_delay'])
            if patterns:lines.append('set_'+direction+'_delay '+str(delay)+' -clock '+tcl_word(values['name'])+' [get_ports '+tcl_word(' '.join(patterns))+']')
        w.sync_file();files=w.config['files'];index=next((i for i,f in enumerate(files) if f['role']=='constraint'),None)
        if index is None:
            files.append({'path':'constraints.sdc','role':'constraint','text':''});index=len(files)-1;w.files.addItem('constraints.sdc')
        files[index]['text']='\n'.join(lines)+'\n';w.file_index=-1;w.files.setCurrentRow(index);w.select_file(index);w.edited();w.tabs.setCurrentIndex(0)

    def physical_settings(self):
        from .digital_physical import DEFAULTS,validate_settings
        w=self.window
        if not w.config:raise ValueError('Open an RTL cell first.')
        values={**DEFAULTS,**w.config.get('physical',{})}
        edits=self.form('Physical implementation settings',[(key,label,' '.join(map(str,values[key])) if isinstance(values[key],list) else values[key]) for key,label in
            [('die_area','Die x1 y1 x2 y2 (µm)'),('core_area','Core x1 y1 x2 y2 (µm)'),('place_density','Placement density'),('threads','Threads')]])
        if edits is None:return
        values={key:[scalar(s) for s in value.split()] if key.endswith('area') else int(value) if key=='threads' else scalar(value) for key,value in edits.items()}
        validate_settings(values);w.config['physical']=values;w.edited()

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
        self.physical.load(None);self.physical_note.clear()
        if not row or not row.get('result'):return
        data=row['result']['digital_result'];artifacts=data['artifacts']
        if 'netlist_index' in artifacts:
            self.index=json.loads((row['path']/artifacts['netlist_index']['path']).read_text())
            fill(self.netlist,self.index[:20000],['module','name','kind','type'])
        fill(self.timing,data.get('timing',{}).get('paths',[]),['check','startpoint','endpoint','slack_ns'])
        fill(self.proof,data.get('equivalence',{}).get('partitions',[]),['partition','status','strategies'])
        if 'layout_preview' in artifacts:
            preview=json.loads((row['path']/artifacts['layout_preview']['path']).read_text());self.physical.load(preview)
            self.physical_note.setText(preview['scope']+f" Displaying {min(20000,len(preview['components']))}/{len(preview['components'])} instances and {min(50000,len(preview['segments']))}/{len(preview['segments'])} segments.")
        cases=[{**case,'percent':(case.get('coverage') or {}).get('percent')} for case in data.get('regression',{}).get('cases',[])]
        fill(self.regression,cases,['name','simulator','status','percent','error'])
        coverage=[{'path':file['path'],**line} for file in data.get('coverage',{}).get('files',[]) for line in file['lines']]
        fill(self.coverage_table,coverage[:20000],['path','line','hits'])
        target=self.timing if 'timing' in data else self.proof if 'equivalence' in data else self.regression if 'regression' in data else self.physical.parentWidget() if 'physical' in data else None
        if target:self.window.result_tabs.setCurrentWidget(target)

    def refresh_comparison(self):
        from .digital_reports import compare_results
        rows=[r for r in self.window.studio.run_manager.rows if r['job']['settings'].get('type')=='digital' and r['job']['cell']==self.window.cell_id]
        fill(self.comparison,compare_results(rows),['name','stage','state','verdict','cells','area_um2','area_um2_delta','setup_worst_slack_ns','setup_worst_slack_ns_delta','hold_worst_slack_ns','power_w','power_w_delta'])

    def jump(self,location):
        w=self.window;path=location.get('path','');files=(w.config or {}).get('files',[])
        index=next((i for i,f in enumerate(files) if path==f['path'] or path.endswith('/'+f['path'])),None)
        if index is None:w.message.setText('This location is outside the captured RTL sources.');return
        w.files.setCurrentRow(index);block=w.editor.document().findBlockByLineNumber(max(0,int(location.get('line',1))-1))
        if block.isValid():w.editor.setTextCursor(QTextCursor(block));w.editor.centerCursor()
        w.tabs.setCurrentIndex(0)

    def probe(self,item):
        self.physical.highlight([item['name']])
        if item.get('locations'):self.jump(item['locations'][0])
        else:self.window.message.setText('No retained RTL source location for '+item['name']+'.')

    def probe_object(self,name):
        item=next((x for x in self.index if x['name']==name and x['kind']=='cell'),None)
        if item:self.probe(item)

    def probe_path(self,path):
        names={pin.rsplit('/',1)[0] for pin in path.get('pins',[]) if '/' in pin};self.physical.highlight(names)
        self.window.message.setText(path['startpoint']+' → '+path['endpoint']+f" · {path['slack_ns']:.6g} ns slack")

    def find_signal(self,name):
        short=re.sub(r'\[.*\]$','',name.rsplit('.',1)[-1])
        item=next((x for x in self.index if x['kind']=='net' and x['name']==short and x.get('locations')),None)
        if item:return self.jump(item['locations'][0])
        for file in (self.window.config or {}).get('files',[]):
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
            self.show_waveform(json.loads((path/artifact['path']).read_text()));w.message.setText(case['name']+' · '+case['status'])

    def show_waveform(self,waveform):
        w=self.window;w.wave.cursor=0;w.wave.zoom=1;w.wave.set_data(waveform)
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
