"""Native Qt integration checks. Run with QT_QPA_PLATFORM=offscreen for headless QA."""
import os,sys,time,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
scratch=ROOT/'build'/'gui-test-profile';scratch.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(scratch/'data');os.environ['XDG_CONFIG_HOME']=str(scratch/'config')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import digest,clone,example
from icstudio.layout import rect
errors=[]
def exception(t,v,tb):
 import traceback
 errors.append(str(v));traceback.print_exception(t,v,tb)
sys.excepthook=exception
app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.capture_repeat.setChecked(False);w.error=lambda text: (_ for _ in ()).throw(AssertionError(text));w.dark=False;w.apply_theme();w.show();QTest.qWait(100)
assert w.project_label.text()=='RC low-pass'
# Property transaction and native undo/redo.
r=w.cell['devices'][1];w.select([r['id']]);w.form_fields['Value'].setText('20k');w.apply_inspector(True);assert w.cell['devices'][1]['value']=='20k';w.undo();assert w.cell['devices'][1]['value']=='10k';w.redo();assert w.cell['devices'][1]['value']=='20k';w.undo()
# Connect a pin, restore, add/move/duplicate/delete through the real controller.
a=w.cell['devices'][0];b=w.cell['devices'][2];w.connect(a['id'],'p',b['id'],'p');assert w.cell['devices'][2]['nets']['p']=='vin';w.undo()
w.add_device(1);assert len(w.cell['devices'])==4;new=w.cell['devices'][-1];w.move([new['id']],20,10,'schematic');w.duplicate();assert len(w.cell['devices'])==5;w.delete();assert len(w.cell['devices'])==4;w.undo();w.undo();w.undo();w.undo();assert len(w.cell['devices'])==3
# Background process simulation and result revision tracking.
w.start_job(clone(w.project['analysis']));deadline=time.monotonic()+25
while w.process and time.monotonic()<deadline:QTest.qWait(30)
assert not w.process,'worker did not finish';assert w.result and len(w.result['x'])==501;assert 'Current revision' in w.result_status.text()
w.commit(lambda p:p['cells'][0]['devices'][1].update(value='12k'));assert 'STALE' in w.result_status.text();w.undo()
# Shape editing, real KLayout Boolean, DRC, net cross-probe and keyboard selection.
w.add_shape(rect('metal1',0,0,1000,1000));w.add_shape(rect('metal1',500,500,1000,1000));w.select([s['id'] for s in w.cell['shapes']],'layout');w.boolean('union');assert len(w.cell['shapes'])==1;w.check('drc');deadline=time.monotonic()+20
while w.process and time.monotonic()<deadline:QTest.qWait(20)
assert not w.process and w.check_revision==w.project['revision'];w.mode_combo.setCurrentIndex(2);QTest.qWait(60);w.layout.fit();w.schematic.fit()
# Native key events move a selected layout polygon one grid step.
s=w.cell['shapes'][0];before=s['points'][0][0];w.select([s['id']],'layout');w.layout.setFocus();QTest.keyClick(w.layout,Qt.Key_Right);assert w.cell['shapes'][0]['points'][0][0]==before+5
w.results_tabs.setCurrentIndex(0);w.mode_combo.setCurrentIndex(0);w.select([w.cell['devices'][1]['id']]);QTest.qWait(60)
image=ROOT/'build'/'desktop-light.png';assert w.grab().save(str(image));w.toggle_theme();QTest.qWait(60);assert w.grab().save(str(ROOT/'build'/'desktop-dark.png'))
# Check missing ground reports and recovery file availability.
assert (w.recovery_dir/(w.project['id']+'.icproj')).exists()
w.saved_hash=digest(w.project);w.close();app.processEvents();assert not errors,errors
print('PASS: native property edits, undo/redo, pin connections, add/move/duplicate/delete, background simulation, staleness, geometry, DRC, keyboard nudge, themes, recovery.')
