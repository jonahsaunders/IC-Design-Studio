"""Native mouse/keyboard acceptance, actual comparison worker and fault navigation."""
import argparse, os, sys, time, json, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument('--pdks',required=True);parser.add_argument('--output',required=True)
for name in ('magic','netgen','ngspice'):parser.add_argument('--'+name,required=True)
args=parser.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
from PySide6.QtCore import Qt,QPointF,QItemSelectionModel
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import clone,digest,uid,save_project,load_project
from icstudio.layout import rect
from icstudio.analog import reference
from icstudio.sky130_layout import layers
errors=[]
def exception(t,v,tb):errors.append(str(v));traceback.print_exception(t,v,tb)
sys.excepthook=exception
app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.error=lambda e:errors.append(str(e));w.resize(1660,1100);w.show();QTest.qWait(50)
def tech(name):
    root=Path(args.pdks).resolve()/name;m=json.loads((root/'package.json').read_text());t=m['technology'];t.update(package_root=str(root),package_lock={k:m[k] for k in ('id','revision','files')});return t
def accept(dlg):QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok),Qt.LeftButton);QTest.qWait(20)
def wait_job():
    deadline=time.monotonic()+600
    while w.process and time.monotonic()<deadline:QTest.qWait(50)
    assert not w.process,w.console.toPlainText()
for name in ('magic','netgen','ngspice'):w.settings.setValue('engine/'+name,str(Path(getattr(args,name)).resolve()))
p,cid,key=reference(tech('sky130A'));w.set_project(p);w.cid=cid;w.refresh(True);w.mirror_layout_dialog();dlg=w._review_dialog;QTest.qWait(20);dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click();QTest.qWait(20);assert w.cell.get('mirror_layout');w.mode_combo.setCurrentIndex(1);w.refresh(True);w.check_linked_layout();assert not w.issues,w.issues
# Click a real via stack onto the gate pad; one undo removes all three shapes.
before=clone(w.cell['shapes']);pt=next(pin['point'] for pin in w.cell['layout_pins'] if pin['pin']=='g');dlg=w.via_dialog();dlg.fields['net'].setText('IREF');accept(dlg);canvas=w.layout
screen=(QPointF(*pt)*canvas.scale+canvas.offset).toPoint();QTest.mouseClick(canvas,Qt.LeftButton,pos=screen);QTest.keyClick(canvas,Qt.Key_Escape);QTest.qWait(30);assert len(w.cell['shapes'])==len(before)+3;w.undo();assert w.cell['shapes']==before
# Drag a segment, then keyboard undo/redo on the native editor.
sid=uid();s={'id':sid,'kind':'path','layer':layers(w.project['pdk'])['m1'],'points':[[15000,0],[17000,0],[17000,3000],[19000,3000]],'width':340,'net':'','device_id':''}
w.commit(lambda p:next(c for c in p['cells'] if c['id']==cid)['shapes'].append(s),'Add editable route');w.select([sid],'layout');w.refresh(True);w.stretch_mouse();canvas=w.layout
start=(QPointF(17000,1500)*canvas.scale+canvas.offset).toPoint();end=start+__import__('PySide6.QtCore',fromlist=['QPoint']).QPoint(20,0)
QTest.mousePress(canvas,Qt.LeftButton,pos=start);QTest.mouseMove(canvas,end,30);QTest.mouseRelease(canvas,Qt.LeftButton,pos=end);QTest.keyClick(canvas,Qt.Key_Escape);QTest.qWait(30);changed=clone(next(s for s in w.cell['shapes'] if s['id']==sid));assert changed['points'][1][0]!=17000;assert changed['points'][1][0]==changed['points'][2][0]
w.activateWindow();canvas.setFocus();QTest.qWait(50);QTest.keyClick(canvas,Qt.Key_Z,Qt.ControlModifier);QTest.qWait(20);assert next(s for s in w.cell['shapes'] if s['id']==sid)['points'][1][0]==17000;w.redo();assert next(s for s in w.cell['shapes'] if s['id']==sid)==changed;w.undo();w.undo()
# Align unlinked local shapes using the first selection as a fixed reference.
a=rect(layers(w.project['pdk'])['m1'],16000,1000,500,500);b=rect(a['layer'],18000,2000,500,500)
w.commit(lambda p:next(c for c in p['cells'] if c['id']==cid)['shapes'].extend([a,b]),'Add alignment objects');w.select([a['id'],b['id']],'layout');dlg=w.align_dialog();dlg.fields['edge'].setCurrentText('Bottom');accept(dlg);assert w.cell['shapes'][-1]['points'][0][1]==1000;w.undo();w.undo()
# Real saved DC comparison worker starts from the DUT and retains fixture identity.
w._selected_testbench=w.project['testbenches'][1]['id'];w.refresh_testbenches();dlg=w.characterization_dialog();dlg.fields['implementation'].setCurrentText('Schematic and post-layout');accept(dlg);w.run_characterization();wait_job();r=w._characterization_result;assert r and r['status']=='passed',w.console.toPlainText();assert r['cell_id']==w.selected_testbench()['bench_cell'];assert r['layout_comparison'];assert w.characterization_table.rowCount()==3
for i in range(3):w.characterization_table.selectionModel().select(w.characterization_table.model().index(i,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
w.characterization_probe.setCurrentIndex(w.characterization_probe.count()-1);w.characterization_waveforms();assert len(w.characterization_plot.overlays)==5;assert w.characterization_plot.result['plot_unit']=='A';w.resizeDocks([w.results_dock],[520],Qt.Vertical);QTest.qWait(100);w.grab().save(str(out/'comparison.png'))
# Deliberate connectivity break: report selection highlights the net and its guides.
from icstudio.physical import erase
ls=layers(w.project['pdk']);w.commit(lambda p:erase(next(c for c in p['cells'] if c['id']==cid),ls['m2'],[3000,-1000,4000,0]),'Break reference net');w.check_linked_layout();i=next(i for i,v in enumerate(w.issues) if v['code']=='LVS.OPEN');w.check_selected(i,0);assert w.net=='IREF';assert w.layout.connection_guides;assert 'STALE' in w.characterization_note.text();w.undo()
# DRC evidence comes from the real worker and selects the exact added shape.
fault=rect(ls['m1'],20000,20000,100,100);w.commit(lambda p:next(c for c in p['cells'] if c['id']==cid)['shapes'].append(fault),'Introduce DRC fault');w.run_silicon();wait_job();assert w._silicon_result['silicon_report']['status']=='failed';w.physical_findings();i=next(i for i,v in enumerate(w.issues) if v['code']=='MAGIC.DRC' and fault['id'] in v.get('objects',[]));w.checks.selectRow(i);w.check_selected(i,0);assert fault['id'] in w.selection;assert w.layout.finding_box;QTest.qWait(80);w.grab().save(str(out/'drc-navigation.png'));w.undo();w.run_silicon();wait_job();assert w._silicon_result['silicon_report']['status']=='passed';w.physical_probe.setCurrentIndex(w.physical_probe.count()-1);w.physical_overlay();assert len(w.plot.overlays)==1 and w.plot.result['plot_unit']=='A'
save_project(w.project,out/'roundtrip.icproj');q=load_project(out/'roundtrip.icproj');assert q['testbenches']==w.project['testbenches'];assert next(c for c in q['cells'] if c['id']==cid)['layout_ports']==w.cell['layout_ports']
# GF180 native generation adds drawing layers and actual datatype-10 ports to a model-only project.
from icstudio.gf180_layout import reference_project
p,gcid=reference_project(tech('gf180mcuC'));w.set_project(p);w.cid=gcid;w.refresh(True);w.inverter_layout_dialog();dlg=w._review_dialog;dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click();QTest.qWait(30);w.mode_combo.setCurrentIndex(1);w.refresh(True);assert {s['layer'] for s in w.cell['shapes']}<=w.layout.visible_layers;w.check_linked_layout();assert not w.issues,w.issues
# Actual LVS property error selects the GF180 schematic device and its physical footprint.
device_id=w.cell['devices'][0]['id'];poly=next(s for s in w.cell['shapes'] if s['layer']=='gf180_poly');sid=poly['id']
w.commit(lambda p:next(s for c in p['cells'] if c['id']==gcid for s in c['shapes'] if s['id']==sid)['points'][1].__setitem__(0,poly['points'][1][0]+100),'Change physical gate length');w.run_silicon();wait_job();assert w._silicon_result['silicon_report']['status']=='failed';w.physical_findings();i=next(i for i,v in enumerate(w.issues) if v['code']=='NETGEN.PROPERTY' and v['object']==device_id);w.check_selected(i,0);assert device_id in w.selection;assert w.cid==gcid;assert w.layout.finding_box;QTest.qWait(80);w.grab().save(str(out/'lvs-navigation.png'));w.undo()
assert not errors,errors
(out/'report.json').write_text(json.dumps({'status':'passed','checks':['reviewed mirror geometry','mouse via placement and grouped undo','mouse segment stretch and keyboard undo','alignment form and undo','actual three-case pre/post DC worker','six signed-current traces','open-net guides and stale comparison','actual DRC marker navigation','repair and rerun passes','single-run current overlay','save and reopen','GF180 drawing layers and port labels','actual LVS property navigation']},indent=2));w.saved_hash=digest(w.project);w.close();print('PASS: 0.10 native layout and actual-engine workflows')
