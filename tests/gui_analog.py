"""Native editor, saved-bench worker, current overlays and stale-result checks."""
import argparse,os,sys,time,json,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument('--pdk',required=True);parser.add_argument('--ngspice',required=True);parser.add_argument('--output',required=True);args=parser.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
from PySide6.QtCore import Qt,QItemSelectionModel
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import clone,digest,load_project,save_project
from icstudio.analog import reference
errors=[]
def exception(t,v,tb):errors.append(str(v));traceback.print_exception(t,v,tb)
sys.excepthook=exception
app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.error=lambda e:errors.append(str(e));w.resize(1640,1080);w.show()
root=Path(args.pdk).resolve();m=json.loads((root/'package.json').read_text());tech=m['technology'];tech.update(package_root=str(root),package_lock={k:m[k] for k in ('id','revision','files')})
p,cid,key=reference(tech);w.set_project(p);w._selected_testbench=p['testbenches'][1]['id'];w.cid=cid;w.refresh(True);w.settings.setValue('engine/ngspice',args.ngspice)
dlg=w.characterization_dialog();dlg.fields['values'].setText('45u, 50u, 55u');QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok),Qt.LeftButton);QTest.qWait(30);assert w.selected_testbench()['characterization']['values']==['45u','50u','55u'];w.undo();w.redo()
# Current measurement remains editable, with source identity and At coordinate intact.
w.edit_testbench();dlg=w._testbench_dialog;assert dlg.measurements.cellWidget(0,1).currentText()=='current';assert dlg.measurements.item(0,4).text()=='VSENSE';dlg.buttons.button(QDialogButtonBox.Save).click();QTest.qWait(30);assert not dlg.isVisible(),dlg.error.text()
save_project(w.project,out/'roundtrip.icproj');q=load_project(out/'roundtrip.icproj');assert q['testbenches']==w.project['testbenches']
w.run_characterization();deadline=time.monotonic()+90
while w.process and time.monotonic()<deadline:QTest.qWait(30)
assert not w.process,w.console.toPlainText();r=w._characterization_result;assert r and r['status']=='passed',w.console.toPlainText();assert r['cell_id']==w.selected_testbench()['bench_cell'];assert w.characterization_table.rowCount()==3
table=w.characterization_table
for i in range(3):table.selectionModel().select(table.model().index(i,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
w.characterization_probe.setCurrentIndex(w.characterization_probe.count()-1);w.characterization_waveforms();assert len(w.characterization_plot.overlays)==2;assert w.characterization_plot.result['plot_unit']=='A';assert len(w.characterization_plot.result['x'])>100
w.results_tabs.setCurrentIndex(w.characterization_tab);w.resizeDocks([w.results_dock],[520],Qt.Vertical);QTest.qWait(80);w.grab().save(str(out/'characterization.png'))
w.commit(lambda p:p['testbenches'][1]['analysis'].update(temperature='55'),'Change bench temperature');assert 'STALE' in w.characterization_note.text();w.undo();assert 'STALE' in w.characterization_note.text()
# Native whole-layout transform follows ports once and supports undo.
from icstudio.sky130_layout import reference_project,generate_inverter
p,cid=reference_project(tech);generate_inverter(p,cid);w.set_project(p);w.cid=cid;w.mode_combo.setCurrentIndex(1);w.refresh(True);assert w.characterization_table.rowCount()==0
w.select([s['id'] for s in w.cell['shapes']],'layout');old=clone(w.cell['layout_ports']);dlg=w.transform_layout_dialog();dlg.fields['dx'].setText('1');dlg.fields['annotations'].setCurrentText('Yes');dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click();QTest.qWait(20);assert w.cell['layout_ports'][0]['point'][0]==old[0]['point'][0]+1000;w.undo();assert w.cell['layout_ports']==old
assert not errors,errors
(out/'report.json').write_text(json.dumps({'status':'passed','checks':['native saved characterization form and undo/redo','current measurement editor preserves source and coordinate','project save/reopen','real ngspice worker started from DUT returns fixture identity','three-case current waveform overlay','stale on bench edit and revision-changing undo','clears results across projects','whole-layout annotation movement and undo']},indent=2));w.saved_hash=digest(w.project);w.close();print('PASS: analog native UI and actual ngspice characterization')
