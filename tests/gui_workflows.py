"""Native end-to-end checks for the 0.3 workflows."""
import os,sys,time,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
profile=ROOT/'build'/'workflow-profile';profile.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(profile/'data');os.environ['XDG_CONFIG_HOME']=str(profile/'config')
from PySide6.QtCore import Qt,QPoint,QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from icstudio.gui import Studio
from icstudio.model import clone,digest,example,device,uid
from icstudio.physical import recipe_cell
from test_workflows import physical_rc
errors=[]
def exception(t,v,tb):
 import traceback
 errors.append(str(v));traceback.print_exception(t,v,tb)
sys.excepthook=exception
app=QApplication([]);app.setStyle('Fusion');QSettings('ICDesignStudio','Studio').clear();w=Studio(recover=False);w.resize(1440,940);w.show();QTest.qWait(100)
def wait_job():
 deadline=time.monotonic()+30
 while w.process and time.monotonic()<deadline:QTest.qWait(20)
 assert not w.process,'worker timed out'
 assert w._job_state=='complete',w.console.toPlainText()
def accept(dlg):QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok),Qt.LeftButton);QTest.qWait(50)
# Submit a real native study form and browse an individual waveform.
w.project['analysis'].update(type='ac',start='1000',end='100000',points=20);w.load_analysis();dlg=w.study_dialog();QTest.qWait(50);accept(dlg);wait_job();assert len(w.result['study_rows'])==3;assert w.study_table.rowCount()==3;assert w.results_tabs.currentIndex()==w.study_tab;QTest.qWait(100);w.grab().save(str(ROOT/'build'/'workspace-studies-0.3.0.png'));w.open_study_case();assert w.result['settings']['type']=='ac' and len(w.result['x'])==20
# Geometry connectivity, extraction and post-layout response are background jobs.
p=physical_rc();p['cells'][0]['devices'][2]['value']='10f';p['analysis'].update(type='ac',start='1meg',end='1g',points=20);w.set_project(p);w.mode_combo.setCurrentIndex(1);w.start_job({'type':'connectivity'});wait_job();assert not w.issues;assert w.results_tabs.currentIndex()==1
w.start_job({'type':'parasitics'});wait_job();assert w.result['physical_result']['capacitors'];w.start_job({'type':'post_layout','analysis':clone(p['analysis'])});wait_job();assert w.result['extraction']['capacitors'];w.mode_combo.setCurrentIndex(2);w.fit_active();QTest.qWait(80);w.grab().save(str(ROOT/'build'/'workspace-physical-0.3.0.png'))
# A moved/deleted conductor creates an actual, clickable open or missing-pin error.
w.commit(lambda p:p['cells'][0]['shapes'].pop(1),'Delete signal conductor');w.start_job({'type':'connectivity'});wait_job();assert any(i['code']=='LVS.UNLANDED' for i in w.issues);w.undo()
# PCell arrays render and keep instance identity through drag, rotate and undo.
p=example('empty');child=recipe_cell('ring',{'kind':'guard_ring','width':3000,'height':3000,'thickness':300});p['cells'].append(child);inst={'id':uid(),'name':'I1','cell':child['id'],'x':0,'y':0,'rotation':0,'nx':2,'ny':1,'dx':5000};p['cells'][0]['layout_instances']=[inst];w.set_project(p);w.mode_combo.setCurrentIndex(1);w.refresh(True);QTest.qWait(100)
scene=w.layout.cell['_layout_scene'];bounds=scene.bounds;rendered=scene.query((bounds.left,bounds.bottom,bounds.right,bounds.top))
assert len(rendered)==8 and {s['id'] for s in rendered}=={inst['id']}
assert len({s['instance_path'] for s in rendered})==2
w.select([inst['id']],'layout');w.move([inst['id']],100,200,'layout');assert w.cell['layout_instances'][0]['x']==100;w.rotate();assert w.cell['layout_instances'][0]['rotation']==90;w.undo();w.undo();assert w.cell['layout_instances'][0]['x']==0
# Native symbol drawing and save updates all instance renderings.
child['ports']=['p','n'];p['cells'][0]['devices']=[device('X','X1',cell=child['id'],nets={'p':'vin','n':'0'})];w.set_project(p);w.cid=child['id'];w.refresh();w.symbol_dialog();dlg=w._symbol_dialog;dlg.show();QTest.qWait(80);pad=dlg.pad;dlg.tool.setCurrentIndex(1);before=len(pad.symbol['primitives']);QTest.mousePress(pad,Qt.LeftButton,pos=QPoint(180,160));QTest.mouseMove(pad,QPoint(300,160));QTest.mouseRelease(pad,Qt.LeftButton,pos=QPoint(300,160));assert len(pad.symbol['primitives'])==before+1;QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Save),Qt.LeftButton);QTest.qWait(50);assert w.cell['symbol'];w.cid=p['top'];w.refresh();assert w.schematic.cell['devices'][0]['symbol'];w.symbol_dialog();w._symbol_dialog.close()
# Cancel a study without publishing a partial aggregate result.
w.set_project(example());before=len(w.jobs);spec={'kind':'sweep','target':'R1.value','values':[10000+i for i in range(500)],'measurement':{'trace':'vout','metric':'max'}};w.start_job({'type':'study','analysis':{**w.project['analysis'],'type':'ac','points':1000},'study':spec});QTest.qWait(60);w.cancel_job();deadline=time.monotonic()+10
while w.process and time.monotonic()<deadline:QTest.qWait(20)
assert not w.process and w._job_state=='cancelled' and len(w.jobs)==before
# Persisted results are recovered on opening a project with the same ID.
w.set_project(physical_rc());saved=clone(w.project);w.start_job({'type':'connectivity'});wait_job();w.set_project(example());w.set_project(saved);assert w.jobs and w.result['settings']['type']=='connectivity'
w.saved_hash=digest(w.project);w.close();assert not errors,errors
print('PASS: native study form, per-case waveforms, connectivity/extraction/post-layout workers, real physical failure, PCell arrays/edits, vector symbol editor, saved-run recovery.')
