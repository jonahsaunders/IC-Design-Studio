"""Real Qt interaction checks for 0.8 testbenches, hierarchy and layout editing."""
import os,sys,time,json,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')];out=ROOT/'build/verification-0.8.0/gui-hierarchy';out.mkdir(parents=True,exist_ok=True);os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
from PySide6.QtCore import Qt,QPointF
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import clone,digest
from icstudio.ring_oscillator import reference
from icstudio.physical_cells import terminals
from test_silicon import technology
errors=[]
def exception(t,v,tb):errors.append(str(v));traceback.print_exception(t,v,tb)
sys.excepthook=exception
app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.error=lambda e:errors.append(str(e));w.resize(1640,1080);w.show();p,cid,tbid=reference(technology());w.set_project(p);w.cid=cid;w.mode_combo.setCurrentIndex(1);w.refresh(True);w.open_silicon();assert w.testbench_combo.count()==1
w.inverter_layout_dialog();w._review_dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click();QTest.qWait(40);assert len(w.cell['layout_instances'])==3;w.check_linked_layout();assert not w.issues,w.issues
inst=w.cell['layout_instances'][0];iid=inst['id'];did=inst['device_id'];w.select([iid],'layout');assert did in w.schematic.selection;w.select([did],'schematic');assert iid in w.layout.selection;w.select([iid],'layout');old=clone(terminals(w.project,cid));w.layout.setFocus();QTest.keyClick(w.layout,Qt.Key_Right);assert terminals(w.project,cid)[0]['point'][0]==old[0]['point'][0]+5;w.undo();w.rotate();assert w.cell['layout_instances'][0]['rotation']==90;w.undo()
w.enter_selected_cell();assert w.cell['name']=='inverter';w.leave_layout_cell();assert w.cid==cid;w.select([iid],'layout');w.duplicate();assert len(w.cell['devices'])==len(w.cell['layout_instances'])==4;w.undo();assert len(w.cell['layout_instances'])==3
w.open_testbenches();w.edit_testbench();dlg=w._testbench_dialog;dlg.fields['stop'].setText('10n');dlg.fields['temperature'].setText('55');dlg.buttons.button(QDialogButtonBox.Save).click();QTest.qWait(40);assert not dlg.isVisible(),dlg.error.text();assert w.project['testbenches'][0]['analysis']['stop']=='10n';assert w.project['testbenches'][0]['analysis']['temperature']=='55';w.duplicate_testbench();assert len(w.project['testbenches'])==2;w.delete_testbench();assert len(w.project['testbenches'])==1;w.undo();assert len(w.project['testbenches'])==2;w.undo();assert len(w.project['testbenches'])==1
w.select([],'layout');w.mode_combo.setCurrentIndex(1);w.refresh(True);canvas=w.layout;canvas.tool='path';canvas.line_width=340;canvas.setFocus();canvas.snap_to_terminals=False
for pt in (QPointF(5000,2000),QPointF(6000,3000)):QTest.mouseClick(canvas,Qt.LeftButton,pos=(pt*canvas.scale+canvas.offset).toPoint())
QTest.keyClick(canvas,Qt.Key_Return);path=w.cell['shapes'][-1];assert path['kind']=='path';assert len(path['points'])==3;assert all(a[0]==b[0] or a[1]==b[1] for a,b in zip(path['points'],path['points'][1:]));w.select([path['id']],'layout');w.path_vertices_dialog();dlg=w._vertices_dialog;dlg.table.item(2,1).setText(str((path['points'][2][1]+1000)/1000));dlg.buttons.button(QDialogButtonBox.Save).click();assert not dlg.isVisible(),dlg.error.text();w.undo();w.undo();canvas.snap_to_terminals=True;canvas.tool='path';pt=terminals(w.project,cid)[0]['point'];assert canvas.snap(QPointF(pt[0]+1,pt[1]+1))==QPointF(*pt);canvas.tool='select'
w.open_silicon();QTest.qWait(40);w.grab().save(str(out/'workspace.png'));w.run_silicon();deadline=time.monotonic()+20
while w.process and time.monotonic()<deadline:QTest.qWait(20)
assert not w.process;assert w.result['silicon_report']['status']=='blocked';assert w.result['silicon_report']['testbench_id']==w.project['testbenches'][0]['id'];assert 'BLOCKED' in w.silicon_status.text();assert not errors,errors
(out/'report.json').write_text(json.dumps({'status':'passed','checks':['reviewed hierarchical generation','bidirectional instance selection','keyboard movement follows child ports','rotation and undo','enter and return through hierarchy','paired electrical/physical duplication','saved testbench editor','duplicate/delete bench with undo','Manhattan path gesture','native vertex editor','terminal snapping','saved-bench worker and blocked status']},indent=2));w.saved_hash=digest(w.project);w.close();print('PASS: saved benches, linked hierarchy, physical transforms, routing, undo and worker diagnostics.')
