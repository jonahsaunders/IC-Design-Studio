"""Exercise reviewed layout generation, cross-selection, stale checks and undo."""
import os,sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
profile=ROOT/'build/gui-silicon-profile';profile.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(profile/'data');os.environ['XDG_CONFIG_HOME']=str(profile/'config')
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import digest,clone
from icstudio.sky130_layout import reference_project,audit
from test_silicon import technology
errors=[]
def exception(t,v,tb):
 import traceback
 errors.append(str(v));traceback.print_exception(t,v,tb)
sys.excepthook=exception
app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.error=lambda e:errors.append(str(e));w.resize(1440,1000);w.show();QTest.qWait(70)
p,cid=reference_project(technology());w.set_project(p);w.cid=cid;w.refresh(True);w.open_silicon();w.inverter_layout_dialog();dlg=w._review_dialog;QTest.qWait(20)
assert dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).isEnabled();dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click();QTest.qWait(20)
assert w.cell['shapes'];assert len(w.cell['layout_pins'])==8;w.check_linked_layout();assert not w.issues,w.issues
n=w.cell['devices'][0];w.select([n['id']],'schematic');assert n['id'] in w.layout.selection
s=next(s for s in w.cell['shapes'] if s.get('device_id')==n['id']);w.select([s['id']],'layout');assert n['id'] in w.schematic.selection
before=clone(w.cell['shapes']);w.commit(lambda p:next(c for c in p['cells'] if c['id']==cid)['devices'][0]['params'].update(w='1.5u'),'Resize MOS');w.check_linked_layout();assert any(i['code']=='PDK.STALE' for i in w.issues)
w.inverter_layout_dialog();dlg=w._review_dialog;dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click();assert not audit(w.project,cid);w.undo();assert w.cell['shapes']==before;assert audit(w.project,cid)
w.redo();w.mode_combo.setCurrentIndex(2);w.refresh(True);w.open_silicon();QTest.qWait(70)
out=ROOT/'build/verification-0.7.0';out.mkdir(parents=True,exist_ok=True);w.grab().save(str(out/'physical-workspace.png'))
# Missing setup runs as a completed diagnostic report, never a passing silicon run.
w.start_job({'type':'silicon','tools':{}});deadline=time.monotonic()+20
while w.process and time.monotonic()<deadline:QTest.qWait(20)
assert not w.process;assert w.result['silicon_report']['status']=='blocked';assert w.silicon_table.rowCount()==7;assert 'BLOCKED' in w.silicon_status.text()
assert not errors,errors
w.saved_hash=digest(w.project);w.close();print('PASS: reviewed MOS layout, cross-selection, terminal connectivity, stale sizing, regeneration/undo, physical workflow worker and blocked status.')
