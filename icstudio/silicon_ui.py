"""One desktop workspace for schematic-linked layout and physical evidence."""
from pathlib import Path
import json,shutil
from PySide6.QtCore import Qt,QUrl,QPointF,QRectF
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView
from .model import clone,design_digest,validate
from .sky130_layout import reference_project
from .process_adapters import inverter_devices
from .process_adapters import generate_inverter,install_mos,audit


class SiliconMixin:
    def make_actions(self):
        super().make_actions()
        menus={a.text().replace('&',''):a.menu() for a in self.menuBar().actions() if a.menu()}
        for menu,entries in {
            'File':[('New PDK inverter…',self.new_silicon_example)],
            'Design':[('Generate PDK device layout…',self.mos_layout_dialog),('Generate inverter layout…',self.inverter_layout_dialog)],
            'Analysis':[('Verify custom inverter through silicon',self.run_silicon),('Check linked layout and show connections',self.check_linked_layout)],
            'View':[('Physical workflow',self.open_silicon)]}.items():
            for title,fn in entries:self.action(menus[menu],title,fn)

    def make_ui(self):
        super().make_ui()
        page=QWidget();layout=QVBoxLayout(page);self.silicon_status=QLabel('Select an inverter cell to generate and verify its layout.');self.silicon_status.setWordWrap(True);layout.addWidget(self.silicon_status)
        row=QHBoxLayout()
        for title,fn in [('Generate layout…',self.inverter_layout_dialog),('Check connections',self.check_linked_layout),('Run physical verification',self.run_silicon),('Evidence folder',self.open_silicon_evidence)]:row.addWidget(self.button(title,fn=fn))
        row.addStretch();layout.addLayout(row)
        self.silicon_table=QTableWidget(0,3);self.silicon_table.setHorizontalHeaderLabels(['Stage','Status','Result']);self.silicon_table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.silicon_table.verticalHeader().hide();self.silicon_table.verticalHeader().setDefaultSectionSize(24);self.silicon_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch);self.silicon_table.setColumnWidth(0,190);layout.addWidget(self.silicon_table,1)
        row=QHBoxLayout()
        for title,fn in [('Before layout',lambda:self.silicon_waveform('schematic')),('After layout',lambda:self.silicon_waveform('post-layout'))]:row.addWidget(self.button(title,fn=fn))
        self.silicon_metrics=QLabel();self.silicon_metrics.setWordWrap(True);row.addWidget(self.silicon_metrics,1);layout.addLayout(row)
        self.silicon_tab=self.results_tabs.addTab(page,'Physical workflow')
        self._silicon_result=None

    def open_silicon(self):
        self.results_dock.show();self.results_tabs.setCurrentIndex(self.silicon_tab);self.resizeDocks([self.results_dock],[330],Qt.Vertical);self.refresh_silicon()

    def new_silicon_example(self):
        if not self.maybe_save():return
        p,cid=reference_project(self.project['pdk']);self.set_project(p);self.cid=cid;self.refresh(True);self.open_silicon()

    def mos_layout_dialog(self):
        if not self.idle_edit():return
        d=next((d for d in self.cell['devices'] if d['id'] in self.selection),None)
        if len(self.selection)!=1 or d is None:raise ValueError('Select one supported schematic MOS device first.')
        did=d['id'];cid=self.cid
        if any(r['device_id']==did for r in self.cell.get('pdk_layouts',[])):
            def build():
                from .process_adapters import regenerate_mos
                p=clone(self.project);regenerate_mos(p,cid,did)
                return p,'Replace the linked footprint of '+d['name']+' using its current W/L, model and nets. Manual edits to its generated shapes are replaced. Existing routes and port labels remain at their coordinates. Check connections and rerun DRC/LVS after applying.'
            self.review_dialog('Regenerate linked device layout',build);return
        def submit(v):
            from .model import scalar
            x,y=[round(scalar(v[k])*1000) for k in ('x','y')]
            self.commit(lambda p:install_mos(p,cid,did,x,y),'Generate PDK device layout');self.mode_combo.setCurrentIndex(1);self.refresh(True)
        self.workflow_form('Generate linked PDK device',[('x','X (µm)','0'),('y','Y (µm)','0')],submit,'SKY130: standard 1.8 V MOS, 1–8 fingers. GF180: standard 3.3 V MOS, one finger, W 1–10 µm and L 0.28–2 µm. Dimensions follow the schematic; each device has four contacted terminals.')

    def inverter_layout_dialog(self):
        if not self.idle_edit():return
        cid=self.cid;inverter_devices(self.project,cid)
        def build():
            p=clone(self.project);c=next(c for c in p['cells'] if c['id']==cid);previous=len(c['shapes']);generate_inverter(p,cid,replace=bool(c.get('inverter_layout')))
            return p,'Generate '+c['name']+' from its two schematic transistors.\n\n'+ '\n'.join(d['name']+': W='+d['params']['w']+', L='+d['params']['l'] for d in c['devices'])+'\n\n'+str(previous)+' existing shapes → '+str(len(c['shapes']))+' editable shapes.\nAll geometry, routes and port labels in this generated cell are replaced, including manual edits.\nUndo restores the previous layout. DRC, LVS and extraction must run again.'
        self.review_dialog('Generate inverter layout',build)

    def check_linked_layout(self):
        if not self.flush_inspector():return
        from .physical import connectivity
        data=connectivity(self.project,self.cid);self.issues=audit(self.project,self.cid)+data['issues'];self.check_revision=self.project['revision'];self.fill_checks()
        self.layout.connection_guides=data.get('guides',[]);self.layout.update();self.check_note.setText(f'{len(self.issues)} findings. Dashed lines show disconnected terminal groups; run extracted LVS after routing.');self.results_dock.show();self.results_tabs.setCurrentIndex(1)

    def run_silicon(self):
        if not self.flush_inspector():return
        inverter_devices(self.project,self.cid)
        if self.project['pdk'].get('package_lock',{}).get('id')=='gf180mcuC':raise ValueError('Save a testbench with explicit GF180 stimulus, loads and measurement limits before physical verification.')
        config={n:self.settings.value('engine/'+n,'') or shutil.which(n) or '' for n in ('magic','netgen','ngspice')}
        self.start_job({'type':'silicon','tools':config});self.open_silicon();self.silicon_status.setText('Verifying the saved project snapshot. Progress and complete logs are retained with this run.')

    def add_result(self,r):
        super().add_result(r)
        if r.get('silicon_report'):self._silicon_result=r;self.refresh_silicon()

    def select_run(self,index):
        super().select_run(index)
        if self.result and self.result.get('silicon_report'):self._silicon_result=self.result;self.refresh_silicon()

    def job_finished(self,code,status):
        super().job_finished(code,status)
        if self.result and self.result.get('silicon_report'):self.open_silicon()

    def refresh(self,fit=False):
        super().refresh(fit)
        if hasattr(self,'silicon_status'):self.refresh_silicon()
        if hasattr(self,'layout'):self.layout.connection_guides=[]

    def refresh_silicon(self):
        r=getattr(self,'_silicon_result',None)
        if r and r['project_id']!=self.project['id']:self._silicon_result=None;r=None
        self.silicon_metrics.clear()
        if not r:
            self.silicon_table.setRowCount(0);self.silicon_status.setText('Active cell: '+self.cell['name']+'. Generate or import layout for the linked technology, then run physical verification with a saved testbench. Supply, loads and measurement limits come from that testbench.');return
        report=r['silicon_report'];stale=r['design_hash']!=design_digest(self.project)
        self.silicon_status.setText(('STALE — design changed. ' if stale else '')+report['status'].upper()+' · '+report.get('error',report['qualification']))
        self.silicon_table.setRowCount(len(report['stages']))
        for row,s in enumerate(report['stages']):
            ev=s.get('evidence',{});detail=s.get('error','') or ('0 violations' if 'violations' in ev else 'Unique match; no property errors' if ev.get('unique_match') else str(ev['capacitors'])+' capacitors' if 'capacitors' in ev else str(ev['samples'])+' samples; settled logic passed' if 'samples' in ev else 'Assets and tools recorded')
            if s['status']=='not_run':detail='Waiting on an earlier stage to pass'
            for col,val in enumerate(({'drc':'Magic DRC','lvs':'Netgen LVS','lvs_extraction':'LVS extraction'}.get(s['name'],s['name'].replace('_',' ').title()),s['status'].replace('_',' '),detail)):self.silicon_table.setItem(row,col,QTableWidgetItem(val))
        pre=next((s.get('evidence') for s in report['stages'] if s['name']=='schematic_simulation'),None);post=next((s.get('evidence') for s in report['stages'] if s['name']=='post_layout_simulation'),None)
        if pre and post and 'mean_delay_s' in pre and 'mean_delay_s' in post:self.silicon_metrics.setText(f'Mean delay: {pre["mean_delay_s"]*1e12:.2f} ps → {post["mean_delay_s"]*1e12:.2f} ps · Δ {post["delay_delta_s"]*1e12:+.2f} ps')

    def open_silicon_evidence(self):
        r=getattr(self,'_silicon_result',None)
        if not r:raise ValueError('Run physical verification first.')
        QDesktopServices.openUrl(QUrl.fromLocalFile(r['evidence_directory']))

    def check_selected(self,row,col):
        if row<len(self.issues) and self.check_revision==self.project['revision'] and self.issues[row].get('bbox'):
            if self.result and self.result.get('silicon_report') and self.result['cell_id']!=self.cid:
                self.cid=self.result['cell_id'];self.selection=[];self.refresh()
            box=QRectF(QPointF(*self.issues[row]['bbox'][:2]),QPointF(*self.issues[row]['bbox'][2:])).normalized();box.adjust(-500,-500,500,500);self.mode_combo.setCurrentIndex(1);self.layout.auto_fit=False;self.layout.scale=min(self.layout.width()/box.width(),self.layout.height()/box.height());self.layout.offset=QPointF(self.layout.rect().center())-box.center()*self.layout.scale;self.layout.update();return
        super().check_selected(row,col)

    def silicon_waveform(self,stage):
        r=getattr(self,'_silicon_result',None)
        if not r:raise ValueError('Run physical verification first.')
        f=Path(r['evidence_directory'])/stage/'result.json'
        if not f.is_file():raise ValueError('This simulation stage did not complete. Review the physical workflow report.')
        wave=json.loads(f.read_text());self.plot.set_result(wave,['vin','vout']);self.results_tabs.setCurrentIndex(0)
        self.cursor_label.setText(stage+' · saved physical verification waveform'+(' · STALE: design changed' if r['design_hash']!=design_digest(self.project) else ''))
