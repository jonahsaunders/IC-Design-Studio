"""Interaction regressions for the redesigned native workspace (headless Qt)."""
import os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
profile=ROOT/'build'/'usability-profile';profile.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(profile/'data');os.environ['XDG_CONFIG_HOME']=str(profile/'config')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint,QPointF,QTimer
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import digest,example,clone
from icstudio.layout import rect
errors=[]
def exception(t,v,tb):
 import traceback
 errors.append(str(v));traceback.print_exception(t,v,tb)
sys.excepthook=exception
app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.capture_repeat.setChecked(False);w.dark=False;w.apply_theme();w.resize(1440,900);w.show();QTest.qWait(150);w.reset_workspace();QTest.qWait(60)
w.error=lambda text:(_ for _ in ()).throw(AssertionError(text))
def screen(canvas,x,y):return (QPointF(x,y)*canvas.scale+canvas.offset).toPoint()
def reset(kind='rc'):
 w.set_project(example(kind));w.mode_combo.setCurrentIndex(0);w.fit_active();QTest.qWait(70)
def capture(name):
 QTest.qWait(80);assert w.grab().save(str(ROOT/'build'/name))
assert w.results_dock.isHidden(), 'empty results must not consume design space'
# Ghost placement is cancellable, and click placement uses the pointer location.
w.begin_placement(1);assert w.schematic.placement;before=digest(w.project);QTest.keyClick(w.schematic,Qt.Key_Escape);assert not w.schematic.placement and digest(w.project)==before
w.begin_placement(2);point=QPoint(140,170);expected=w.schematic.snap(w.schematic.model(QPointF(point)));QTest.mouseClick(w.schematic,Qt.LeftButton,pos=point);assert len(w.cell['devices'])==4;placed=w.cell['devices'][-1];assert (placed['x'],placed['y'])==(expected.x(),expected.y());assert w.schematic.tool=='select';assert w.selection==[placed['id']];w.undo()
# Invalid property drafts stay visible and cannot silently change selection.
a,b=w.cell['devices'][1:3];w.select([a['id']]);w.form_fields['Value'].setText('not-a-value');w.select([b['id']]);assert w.selection==[a['id']];assert not w.property_error.isHidden();assert w.cell['devices'][1]['value']=='10k'
w.form_fields['Value'].setText('22k');w.select([b['id']]);assert w.cell['devices'][1]['value']=='22k';assert w.selection==[b['id']];w.undo()
# Rubber-band selection and a drag commit operate through native mouse events.
w.select([]);c=w.schematic;start=QPoint(20,30);end=QPoint(c.width()-20,c.height()-30);QTest.mousePress(c,Qt.LeftButton,pos=start);QTest.mouseMove(c,end);QTest.mouseRelease(c,Qt.LeftButton,pos=end);assert set(w.selection)=={o['id'] for o in w.cell['devices']+w.cell['wires']}
r=w.cell['devices'][1];w.select([r['id']]);pos=screen(c,r['x'],r['y']);end=pos+QPoint(45,20);expected=c.snap(c.model(QPointF(end)))-c.snap(c.model(QPointF(pos)));x,y=r['x'],r['y'];QTest.mousePress(c,Qt.LeftButton,pos=pos);QTest.mouseMove(c,end);assert w.schematic.moving;QTest.mouseRelease(c,Qt.LeftButton,pos=end);r=w.cell['devices'][1];assert (r['x'],r['y'])==(x+expected.x(),y+expected.y());w.undo()
# Connect pins from actual screen positions.
from icstudio.interchange import pin_positions
w.set_tool(1);a,b=w.cell['devices'][0],w.cell['devices'][2];QTest.mouseClick(c,Qt.LeftButton,pos=screen(c,*pin_positions(a)['p']));assert c.pending_pin;QTest.mouseClick(c,Qt.LeftButton,pos=screen(c,*pin_positions(b)['p']));assert w.cell['devices'][2]['nets']['p']=='vin';QTest.keyClick(c,Qt.Key_Escape);w.undo()
# Analysis setup uses only relevant fields and reports errors inline.
w.run_dialog();assert w.inspector_tabs.currentIndex()==1;w.analysis_fields['step'].setText('0');w.quick_run();assert not w.process;assert not w.analysis_error.isHidden();w.analysis_fields['step'].setText('200n');w.quick_run();deadline=time.monotonic()+20
while w.process and time.monotonic()<deadline:QTest.qWait(30)
QTest.qWait(30);assert w.result and not w.process;assert w.results_dock.isVisible();assert w.stop_button.isHidden();w.select([w.cell['devices'][1]['id']]);w.reveal_properties();w.fit_active();capture('workspace-schematic.png')
# Responsive layout must fit inside the requested window, including toolbar.
w.resize(1100,760);QTest.qWait(100);assert w.width()==1100;capture('workspace-compact.png');w.resize(1440,900);QTest.qWait(80)
# Units-based layout inspector, layer visibility, and drawing at the cursor.
w.add_shape(rect('metal1',0,0,1000,1500));w.mode_combo.setCurrentIndex(1);QTest.qWait(80);s=w.cell['shapes'][0];w.select([s['id']],'layout');assert 'Vertices' not in w.form_fields and 'Linked device ID' not in w.form_fields;w.form_fields['Width'].setText('2.5');assert w.apply_inspector(False);assert w.cell['shapes'][0]['points'][1][0]==2500
for i in range(w.layers.count()):w.layers.item(i).setCheckState(Qt.Unchecked)
assert not w.layout.visible_layers;w.select([],'layout');assert not w.layout.visible_layers
for i in range(w.layers.count()):w.layers.item(i).setCheckState(Qt.Checked)
w.results_dock.hide();w.fit_active();w.select([w.cell['shapes'][0]['id']],'layout');capture('workspace-layout.png')
w.resize(1100,760);QTest.qWait(70);capture('workspace-layout-compact.png');assert w.width()==1100;w.resize(1440,900)
# Source disclosure updates and command palette keyboard navigation.
w.select([w.cell['devices'][0]['id']],'schematic');w.form_fields['source:type'].setCurrentText('dc');assert w.form_fields['source:period'].isHidden();w.build_inspector()
def use_palette():
 dlg=app.activeModalWidget();assert dlg is not None;dlg.query.setText('View');assert dlg.items.count()>1;QTest.keyClick(dlg.query,Qt.Key_Down);assert dlg.items.currentRow()==1;dlg.query.setText('Fit design');QTest.keyClick(dlg.query,Qt.Key_Return)
QTimer.singleShot(60,use_palette);w.command_palette()
# Editor changes preserve a user-controlled camera.
w.layout.auto_fit=False;w.layout.scale=.17;w.layout.offset=QPointF(141,191);w.mode_combo.setCurrentIndex(0);QTest.qWait(30);w.mode_combo.setCurrentIndex(1);QTest.qWait(40);assert abs(w.layout.scale-.17)<1e-9
w.mode_combo.setCurrentIndex(0);QTest.qWait(50);w.show_library();capture('workspace-devices.png');w.run_dialog();capture('workspace-analysis.png');w.dark=True;w.apply_theme();w.navtabs.setCurrentIndex(0);w.reveal_properties();w.select([w.cell['devices'][1]['id']]);w.results_dock.show();w.fit_active();capture('workspace-dark.png')
w.focus_canvas();assert w.nav.isHidden() and w.inspector.isHidden();w.focus_canvas();assert w.nav.isVisible() and w.inspector.isVisible()
w.saved_hash=digest(w.project);w.close();app.processEvents();assert not errors,errors
print('PASS: placement/cancel, draft validation, box selection, drag preview/commit, pin wiring, analysis validation/run, layout property units, hidden layers, camera memory, panel controls, compact layouts, screenshots.')
