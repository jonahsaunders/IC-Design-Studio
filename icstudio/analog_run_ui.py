"""Saved circuit, probes and physical evidence viewed without replacing a document."""
import json
from PySide6.QtCore import Qt,QPointF,QRectF,QEvent
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTabWidget,QWidget,QComboBox,
    QPushButton,QSplitter,QPlainTextEdit)
from .model import clone,design_digest
from .analog_debug import contexts,operating_rows,convergence_hints,comparison_rows
from .analog_workspace_ui import table,fill
from .canvas import Canvas
from .plot import WavePlot
from .analog_widgets import actions,label,scroll


class RunInspector(QDialog):
    def __init__(self,studio,row):
        super().__init__(studio);self.studio=studio;self.row=clone({k:row[k] for k in ('job','name','state','log') if k in row});self.project=clone(row['job']['project'])
        self.result=clone(row.get('result') or {});self.wave=self.result;self.setWindowTitle('Saved analog run · '+row['name']);self.resize(1240,860)
        root=QVBoxLayout(self)
        stale=design_digest(studio.project)!=design_digest(self.project)
        label=QLabel(f"{row['state']} · saved revision {self.project['revision']} · {design_digest(self.project)[:12]}"+(' · current design differs' if stale else ''))
        root.addWidget(label);self.note=QLabel('Inspecting the saved circuit. Editing actions remain in the main design window.');self.note.setWordWrap(True);root.addWidget(self.note)
        self.tabs=QTabWidget();root.addWidget(self.tabs,1)
        page=QWidget();layout=QVBoxLayout(page);self.tabs.addTab(page,'Circuit and waveforms')
        selectors=QHBoxLayout();self.hierarchy=QComboBox();self.hierarchy.setAccessibleName('Saved circuit instance');selectors.addWidget(self.hierarchy,1)
        self.probe=QComboBox();self.probe.setAccessibleName('Saved voltage or current probe');selectors.addWidget(self.probe,1);layout.addLayout(selectors)
        split=QSplitter();self.schematic=Canvas('schematic');self.schematic.dark=studio.dark;self.plot=WavePlot();self.plot.dark=studio.dark;split.addWidget(self.schematic);split.addWidget(self.plot);layout.addWidget(split,2)
        self.devices=table(['Instance','Id / branch current (A)','gm (S)','Bias margin (V)','Region / evidence']);self.devices.setAccessibleName('Saved device operating points');layout.addWidget(self.devices,1)
        self.devices.cellClicked.connect(self.select_device);self.devices.itemActivated.connect(lambda *_:self.call(lambda:self.select_device(self.devices.currentRow())));self.schematic.selected.connect(self.select_canvas_device)
        self.hierarchy.currentIndexChanged.connect(self.show_context);self.probe.currentIndexChanged.connect(self.show_probe)
        self.plot.cursor_changed.connect(self.cursor_sample)
        page=QWidget();layout=QVBoxLayout(page);self.tabs.addTab(page,'Verification and deltas')
        self.stages=table(['Stage','State','Details']);layout.addWidget(self.stages)
        self.comparisons=table(['Requirement','Before','After','Delta','Unit','Before status','After status','Details']);layout.addWidget(self.comparisons)
        actions(layout,[('Schematic waveforms',lambda:self.physical_wave('schematic')),('Extracted waveforms',lambda:self.physical_wave('post-layout')),('Overlay both',self.overlay)],self.call)
        split=QSplitter();self.findings=table(['Rule','Cell / object','Details']);split.addWidget(self.findings);self.layout_canvas=Canvas('layout');self.layout_canvas.dark=studio.dark;split.addWidget(self.layout_canvas);layout.addWidget(split,2)
        self.findings.cellClicked.connect(lambda i,j:self.call(lambda:self.locate_finding(i)))
        self.findings.itemActivated.connect(lambda *_:self.call(lambda:self.locate_finding(self.findings.currentRow())))
        log=QPlainTextEdit();log.setReadOnly(True);log.setAccessibleName('Saved simulation diagnostics and input');self.tabs.addTab(log,'Diagnostics and input')
        raw=row.get('log','')+'\n'+self.result.get('log','');hints=convergence_hints(raw)
        log.setPlainText('\n\n'.join(h['title']+'\n'+h['detail'] for h in hints)+'\n\nSaved analysis\n'+json.dumps(row['job']['settings'],indent=2)+'\n\nSaved variables\n'+json.dumps(self.project.get('parameters',{}),indent=2)+'\n\nEngine log\n'+raw)
        self.populate_wave();self.populate_verification()
        for i in range(2):
            page=self.tabs.widget(i);title=self.tabs.tabText(i);self.tabs.removeTab(i);self.tabs.insertTab(i,scroll(page),title)
        self.setMinimumSize(760,560)
        if self.result.get('silicon_report'):self.tabs.setCurrentIndex(1)

    def call(self,fn):
        try:return fn()
        except Exception as exc:self.note.setText(str(exc))

    def changeEvent(self,event):
        if event.type()==QEvent.PaletteChange:
            for key in ('schematic','layout_canvas','plot'):
                if hasattr(self,key):getattr(self,key).dark=self.studio.dark;getattr(self,key).update()
        super().changeEvent(event)

    def focus_requirement(self,definition):
        """Follow exact saved V/I references; do not guess a derived trace."""
        import ast
        if definition.get('stage') in ('schematic','post-layout'):
            self.physical_wave(definition['stage'])
        probes=[]
        if definition.get('expression'):
            tree=ast.parse(definition['expression'],mode='eval')
            for node in ast.walk(tree):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('V','I'):
                    probes.extend(('voltage' if node.func.id=='V' else 'current',arg.value) for arg in node.args if isinstance(arg,ast.Constant) and isinstance(arg.value,str))
        elif definition.get('node'):probes=[('voltage',definition['node'])]
        elif definition.get('source'):probes=[('current',definition['source'])]
        for kind,name in probes:
            for index in range(self.probe.count()):
                candidate=self.probe.itemData(index)
                if candidate[0]==kind and candidate[1].casefold()==name.casefold():
                    self.probe.setCurrentIndex(index);self.note.setText(definition.get('name','Requirement')+' · '+self.probe.currentText());return

    def populate_wave(self):
        cid=self.wave.get('cell_id',self.row['job']['cell'])
        self.contexts=contexts(self.project,cid);self.hierarchy.blockSignals(True);self.hierarchy.clear()
        by={c['id']:c for c in self.project['cells']}
        for c in self.contexts:self.hierarchy.addItem((c['path'].rstrip('/') or 'Top')+' · '+by[c['cell_id']]['name'],c)
        self.hierarchy.blockSignals(False)
        self.device_rows=operating_rows(self.project,cid,self.wave)
        fill(self.devices,[[r['name'],r['values'].get('id',r['values'].get('current')),r['values'].get('gm'),r['values'].get('headroom'),r['values'].get('region',r['values'].get('source','No saved device vectors'))] for r in self.device_rows])
        self.probe.blockSignals(True);self.probe.clear()
        for name in self.wave.get('traces',{}):self.probe.addItem('V('+name+')',('voltage',name))
        for name in self.wave.get('currents',{}):self.probe.addItem('I('+name+')',('current',name))
        self.probe.blockSignals(False);self.show_context();self.show_probe()

    def show_context(self,*_):
        c=self.hierarchy.currentData()
        if not c:return
        cell=clone(next(v for v in self.project['cells'] if v['id']==c['cell_id']))
        from .annotations import readouts
        self.schematic.set_data(cell,self.project['pdk'])
        rows,label=readouts(self.project,c['cell_id'],self.wave,instance_path=c['path'])
        self.schematic.simulation_annotations=rows;self.schematic.simulation_annotation_label=label;self.schematic.fit()

    def show_probe(self,*_):
        probe=self.probe.currentData()
        if not probe:self.plot.set_result(None,[]);return
        kind,name=probe;data=clone(self.wave)
        if kind=='current':data.update(traces=data.get('currents',{}),phase=data.get('current_phase',{}),y_label='Current (A)')
        self.plot.set_result(data,[name])

    def select_device(self,i,j=0):
        r=self.device_rows[i]
        index=next(n for n,c in enumerate(self.contexts) if c['path']==r['path'])
        self.hierarchy.setCurrentIndex(index);self.schematic.selection=[r['object']];self.schematic.update()
        available={name.casefold():k for k,(kind,name) in enumerate(self.probe.itemData(n) for n in range(self.probe.count())) if kind=='voltage'}
        for net in r['pins'].values():
            if net.casefold() in available:self.probe.setCurrentIndex(available[net.casefold()]);break
        values=', '.join(pin+'='+('unavailable' if value is None else f'{value:.6g} V') for pin,value in r['voltages'].items())
        self.note.setText(r['name']+' · '+values)

    def select_canvas_device(self,ids):
        context=self.hierarchy.currentData()
        for i,r in enumerate(self.device_rows):
            if r['object'] in ids and r['path']==context['path']:
                self.devices.selectRow(i);self.select_device(i);break

    def cursor_sample(self,text):
        self.note.setText(text)
        context=self.hierarchy.currentData()
        if context and self.plot.a is not None:
            from .annotations import readouts
            rows,label=readouts(self.project,context['cell_id'],self.wave,x=self.plot.a,instance_path=context['path'])
            self.schematic.simulation_annotations=rows;self.schematic.simulation_annotation_label=label;self.schematic.update()

    def populate_verification(self):
        report=self.result.get('silicon_report',{})
        fill(self.stages,[[s['name'],s['status'],s.get('error','') or json.dumps(s.get('evidence',{}),ensure_ascii=False)] for s in report.get('stages',[])])
        rows=comparison_rows(report)
        if not rows:
            rows=[dict(name=r['name'],before=r['before'].get('value'),after=r['after'].get('value'),delta=r.get('delta'),unit=r['before'].get('unit',''),before_status=r['before']['status'],after_status=r['after']['status'],detail=r['after'].get('error','')) for r in self.result.get('rc_comparison',[])]
        fill(self.comparisons,[[r.get(k) for k in ('name','before','after','delta','unit','before_status','after_status','detail')] for r in rows])
        self.issue_rows=self.result.get('physical_result',{}).get('issues',report.get('findings',[]))
        fill(self.findings,[[r.get('code',''),r.get('instance_path',r.get('cell_id',''))+' '+r.get('net',r.get('object','')),r.get('message','')] for r in self.issue_rows])
        cell=next(c for c in self.project['cells'] if c['id']==self.result.get('cell_id',self.row['job']['cell']))
        self.layout_canvas.set_data(clone(cell),self.project['pdk']);self.layout_canvas.fit()

    def locate_finding(self,i):
        issue=self.issue_rows[i];cid=issue.get('cell_id',self.result.get('cell_id',self.row['job']['cell']))
        cell=next((c for c in self.project['cells'] if c['id']==cid),None)
        if cell is None:raise ValueError('This finding has no mapped cell; inspect its retained engine log.')
        ids=issue.get('objects') or [issue.get('object','')]
        self.layout_canvas.set_data(clone(cell),self.project['pdk'],ids,issue.get('net',''));self.layout_canvas.fit()
        if issue.get('bbox'):
            box=QRectF(QPointF(*issue['bbox'][:2]),QPointF(*issue['bbox'][2:])).normalized();box.adjust(-500,-500,500,500)
            self.layout_canvas.auto_fit=False;self.layout_canvas.scale=min(self.layout_canvas.width()/box.width(),self.layout_canvas.height()/box.height())
            self.layout_canvas.offset=QPointF(self.layout_canvas.rect().center())-box.center()*self.layout_canvas.scale;self.layout_canvas.update()
        self.note.setText(issue.get('message','')+' · saved revision '+str(self.project['revision']))

    def physical_wave(self,stage):
        from .verification_navigation import waveform
        field='before_waveform' if stage=='schematic' else 'after_waveform'
        self.wave=clone(self.result[field]) if self.result.get('rc_comparison') and field in self.result else waveform(self.result,stage)
        self.populate_wave();self.tabs.setCurrentIndex(0);self.note.setText(stage+' · saved waveform')

    def overlay(self):
        from .verification_navigation import waveform
        if self.result.get('rc_comparison'):before=clone(self.result['before_waveform']);after=clone(self.result['after_waveform'])
        else:before=waveform(self.result,'schematic');after=waveform(self.result,'post-layout')
        if before.get('x_label')!=after.get('x_label'):raise ValueError('Saved waveforms use different axes.')
        self.wave=before;self.populate_wave()
        common=[n for n in before.get('traces',{}) if n in after.get('traces',{})]
        if not common:raise ValueError('No matching saved voltage probes are available.')
        self.plot.set_result(before,common[:4],after);self.tabs.setCurrentIndex(0);self.note.setText('Schematic and extracted waveforms · identical saved testbench')
