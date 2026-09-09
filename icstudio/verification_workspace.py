"""Extracted requirement comparisons and reviewed schematic exchange."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QDialogButtonBox,QFileDialog,QPlainTextEdit,QTableWidgetItem,QWidget,QTabBar
from .model import clone,scalar,digest


class VerificationWorkspaceMixin:
    def make_ui(self):
        super().make_ui()
        page,v=self.engineering_page('Extracted requirement comparison','Evaluate the same saved specifications before and after distributed interconnect RC extraction.')
        self.engineering_buttons(v,[('RC coefficients…',self.rc_coefficients_dialog),('Extract and compare…',self.rc_compare_dialog),('Before / after waveforms',self.rc_overlay),('Export extracted network…',self.export_rc_network)])
        self.rc_note=QLabel('Declare calibrated coefficients for your technology, or explicitly use teaching estimates for a teaching design.');self.rc_note.setWordWrap(True);v.addWidget(self.rc_note)
        self.rc_table=self.simulation_table(['Requirement','Before','After','Delta','Unit','Before result','After result','Details']);v.addWidget(self.rc_table);self.rc_tab=self.add_engineering_tab(page,'Extracted comparison');self._rc_result=None;self.install_results_navigation()
    def set_project(self,p,path=None):
        super().set_project(p,path)
        if hasattr(self,'rc_table') and (not self.result or 'rc_comparison' not in self.result):self._rc_result=None;self.rc_table.setRowCount(0);self.rc_note.setText('Run an extracted comparison for this project.')
    def install_results_navigation(self):
        self.result_groups=[('Simulation',[self.simulation_tab,self.spec_tab,self.cases_tab,self.testbench_tab,self.characterization_tab]),('Waveforms',[0,self.study_tab]),('Physical',[self.physical_assistant_tab,self.silicon_tab,self.rc_tab]),('Checks',[1,2])]
        # Keep controller page identities stable while replacing the long scrolling strip.
        host=QWidget();layout=QVBoxLayout(host);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0);self.result_categories=QTabBar();self.result_sections=QTabBar();self.result_categories.setAccessibleName('Results workspace');self.result_sections.setAccessibleName('Results page')
        for name,indices in self.result_groups:self.result_categories.addTab(name)
        layout.addWidget(self.result_categories);layout.addWidget(self.result_sections);self.results_tabs.tabBar().hide();self.results_tabs.setParent(host);layout.addWidget(self.results_tabs);self.results_dock.setWidget(host);self._result_nav_sync=False;self._result_last={}
        self.result_categories.currentChanged.connect(self.choose_result_category);self.result_sections.currentChanged.connect(self.choose_result_section);self.results_tabs.currentChanged.connect(self.sync_result_navigation);self.sync_result_navigation(self.results_tabs.currentIndex())
    def choose_result_category(self,group):
        if self._result_nav_sync:return
        self.results_tabs.setCurrentIndex(self._result_last.get(group,self.result_groups[group][1][0]))
    def choose_result_section(self,index):
        if not self._result_nav_sync and index>=0:self.results_tabs.setCurrentIndex(self.result_groups[self.result_categories.currentIndex()][1][index])
    def sync_result_navigation(self,index):
        group=next((i for i,(_,indices) in enumerate(self.result_groups) if index in indices),None)
        if group is None:return
        self._result_nav_sync=True;self._result_last[group]=index;self.result_categories.setCurrentIndex(group)
        while self.result_sections.count():self.result_sections.removeTab(0)
        for page in self.result_groups[group][1]:self.result_sections.addTab(self.results_tabs.tabText(page))
        self.result_sections.setCurrentIndex(self.result_groups[group][1].index(index));self._result_nav_sync=False
    def make_actions(self):
        super().make_actions();sub=self.analysis_submenus['Post-layout']
        self.action(sub,'Distributed RC and specification comparison',lambda:self.open_engineering_tab(self.rc_tab));self.action(self.task_menus['Help'],'Design workflow guide',lambda:self.open_editor_doc('UPDATE_0.16.md'))
        for title,path in [('Distributed RC and specifications','distributed-rc-specifications.icproj'),('Differential amplifier design goals','differential-amplifier-goals.icproj'),('Common-centroid resistor array','common-centroid-resistors.icproj')]:self.action(self._task_submenus['File/Examples'],title,lambda path=path:self.open_engineering_example(path))
        self.action(self._task_submenus.get('File/Import',self.task_menus['File']),'Import Xschem schematic…',self.import_direct_xschem_dialog)
        self.action(self.task_menus['Help'],'Xschem import and export guide',lambda:self.open_editor_doc('UPDATE_0.18.md'))
        self.action(self._task_submenus['File/Examples'],'Xschem amplifier project',self.open_xschem_example)
        self.reindex_commands()
    def open_xschem_example(self):
        import sys
        from pathlib import Path
        from .xschem_workspace import show_review
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
        return show_review(self,root/'examples/xschem-amplifier/amplifier.sch',[])
    def import_direct_xschem_dialog(self):
        path,_=QFileDialog.getOpenFileName(self,'Import Xschem schematic','','Xschem schematic (*.sch)')
        if path:
            from .xschem_workspace import show_review
            return show_review(self,path,auto_open=True)
    def open_engineering_example(self,name):
        import sys
        from pathlib import Path
        from .model import load_project
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
        p=load_project(root/'examples'/name)
        if self.maybe_save():self.set_project(p);self.mode_combo.setCurrentIndex(2);self.open_engineering_tab(self.spec_tab)
    def rc_coefficients_dialog(self):
        layers=[l['name'] for l in self.project['pdk']['layers'] if l['name'] in self.project['pdk'].get('connectivity',{}).get('conductors',['metal1','metal2'])]
        if not layers:raise ValueError('Declare conducting layers in the technology first.')
        def submit(v):
            row={k:scalar(v[k]) for k in ('sheet_ohm','cap_f_per_um2','edge_f_per_um','coupling_f_per_um')}
            if row['sheet_ohm']<=0 or any(x<0 for x in row.values()):raise ValueError('Resistance must be positive and capacitance coefficients non-negative.')
            row['source']=v['source'];self.commit(lambda p:p['pdk'].setdefault('parasitics',{}).update({v['layer']:row}),'Declare RC coefficients')
        return self.workflow_form('Interconnect coefficients',[('layer','Conductor',layers),('sheet_ohm','Sheet resistance (Ohm / square)','0.1'),('cap_f_per_um2','Ground capacitance (F / µm²)','0.02f'),('edge_f_per_um','Ground edge capacitance (F / µm)','0.01f'),('coupling_f_per_um','Parallel coupling (F / µm at 1 µm gap)','0.02f'),('source','Coefficient source / calibration evidence','Illustrative estimate; replace with calibrated values')],submit,'These values are estimates until you supply calibration evidence. Coupling uses inverse edge-gap scaling for parallel routes on the same layer. Wider physical coverage uses the process extraction workflow.')
    def rc_compare_dialog(self):
        cid=self.cid
        def submit(v):
            settings={'type':'rc_compare','analysis':self.current_analysis_settings(),'section_nm':round(scalar(v['section'])*1000),'layout_cell':cid};self.start_job(settings,self.analysis_engine.currentData());self.open_engineering_tab(self.rc_tab)
        return self.workflow_form('Extract and compare',[('section','Maximum RC section length (µm)','5')],submit,'Requires connected physical terminals and Manhattan conducting paths in the active cell. Runs before and after using the same saved requirements. Rectangular pads are ideal. Model-based device extraction remains in Physical workflow.')
    def select_run(self,i):
        super().select_run(i)
        if hasattr(self,'rc_table') and self.result and 'rc_comparison' in self.result:
            self._rc_result=self.result;rows=self.result['rc_comparison'];self.rc_table.setRowCount(len(rows));e=self.result['extraction'];self.rc_note.setText(f"{len(e['resistors'])} resistors · {len(e['capacitors'])} capacitors · "+e['qualification'])
            for i,row in enumerate(rows):
                a,b=row['before'],row['after'];fmt=lambda v:'—' if v is None else f'{v:.6g}'
                for j,value in enumerate((row['name'],fmt(a['value']),fmt(b['value']),fmt(row['delta']),a['unit'],a['status'],b['status'],a.get('error','')+' '+b.get('error',''))):self.rc_table.setItem(i,j,QTableWidgetItem(value))
    def rc_overlay(self):
        if not self._rc_result:raise ValueError('Run an extracted comparison first.')
        r=self._rc_result;self.plot.set_result(r['before_waveform'],overlays=[r['after_waveform']]);self.results_tabs.setCurrentIndex(0)
    def export_rc_network(self):
        if not self._rc_result:raise ValueError('Run an extracted comparison first.')
        path,_=QFileDialog.getSaveFileName(self,'Export extracted network','','JSON (*.json)')
        if path:
            from .model import atomic_write
            atomic_write(path,json.dumps(self._rc_result['extraction'],indent=2))
    def import_xschem_dialog(self):
        path,_=QFileDialog.getOpenFileName(self,'Review edited Xschem package','','Xschem (*.sch)')
        if path:return self.show_xschem_review(path)
    def show_xschem_review(self,path):
        from pathlib import Path
        if not (Path(path).parent/'project.icproj').is_file():
            from .xschem_workspace import show_review
            return show_review(self,path)
        from .exchange_review import review,apply_review
        record=review(path);dlg=QDialog(self);dlg.setWindowTitle('Review Xschem changes');dlg.resize(1080,640);v=QVBoxLayout(dlg);note=QLabel('Inspect device values, placement and net changes before opening the imported project. Unsupported constructs and blocking errors appear below.');note.setWordWrap(True);v.addWidget(note)
        table=self.simulation_table(['Cell','Object','Change','Before','After']);table.setRowCount(len(record['changes']));v.addWidget(table,1)
        for i,row in enumerate(record['changes']):
            for j,key in enumerate(('cell','object','change','before','after')):table.setItem(i,j,QTableWidgetItem(row[key]))
        text=QPlainTextEdit('\n'.join(['ERROR: '+s for s in record['errors']]+record['warnings']));text.setReadOnly(True);v.addWidget(text)
        buttons=QDialogButtonBox(QDialogButtonBox.Open|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Open).setText('Open reviewed project');buttons.button(QDialogButtonBox.Open).setEnabled(record['candidate'] is not None and not record['errors']);v.addWidget(buttons)
        def accept():
            candidate=apply_review(record)
            if self.maybe_save():self.set_project(candidate);dlg.accept()
        buttons.accepted.connect(lambda:self.guard(accept));buttons.rejected.connect(dlg.reject);dlg.record=record;dlg.change_table=table;self._import_dialog=dlg;dlg.show();return dlg
