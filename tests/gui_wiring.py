"""Real Qt input regressions: paths, netlist topology, rotation and mnemonics."""
import os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
profile=ROOT/'build'/'wiring-profile';profile.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(profile/'data');os.environ['XDG_CONFIG_HOME']=str(profile/'config')
from PySide6.QtCore import Qt,QPoint,QPointF,QSettings,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMenu
from icstudio.gui import Studio
from icstudio.model import clone,digest,example,device,uid,validate
from icstudio import wiring
from icstudio.interchange import spice,pin_positions
from test_wiring import circuit
errors=[]
def exception(t,v,tb):
 import traceback
 errors.append(str(v));traceback.print_exception(t,v,tb)
sys.excepthook=exception
app=QApplication([]);app.setStyle('Fusion');QSettings('ICDesignStudio','Studio').clear();w=Studio(recover=False);w.capture_repeat.setChecked(False);w.resize(1440,940);w.show();QTest.qWait(120)
w.error=lambda text:(_ for _ in ()).throw(AssertionError(text))
def setup(p=None):
 w.set_project(p or circuit()[0]);w.mode_combo.setCurrentIndex(0);w.results_dock.hide();w.reset_workspace();QTest.qWait(80);c=w.schematic;c.auto_fit=False;c.scale=1.35;c.offset=QPointF(40,80);c.setFocus();c.update();QTest.qWait(30);return c
def screen(c,pt):return (QPointF(*pt)*c.scale+c.offset).toPoint()
def click(c,pt):QTest.mouseClick(c,Qt.LeftButton,pos=screen(c,pt));QTest.qWait(15)
def key(c,k,mod=Qt.NoModifier):QTest.keyClick(c,k,mod);QTest.qWait(15)
# Explicit route through real clicks, plus bend preview/undo/cancel.
c=setup();before=digest(w.project);key(c,Qt.Key_W);assert c.tool=='connect'
click(c,[100,100]);assert c.wire_points==[[100,100]];click(c,[100,40]);click(c,[400,40]);assert len(w.cell['wires'])==0
key(c,Qt.Key_Backspace);assert c.wire_points==[[100,100],[100,40]];click(c,[400,40]);click(c,[400,100]);assert len(w.cell['wires'])==1
assert w.cell['wires'][0]['points']==[[100,100],[100,40],[400,40],[400,100]]
r,cap,l=w.cell['devices'];assert r['nets']['p']==cap['nets']['p'];assert r['nets']['n']!=cap['nets']['n'];wire_id=w.cell['wires'][0]['id']
# Branch to the interior of a placed wire merges all three terminals.
click(c,[250,250]);click(c,[250,40]);assert len(w.cell['wires'])==2;assert len({d['nets']['p'] for d in w.cell['devices']})==1;assert (250,40) in wiring.junction_points(w.cell)
key(c,Qt.Key_Escape);assert c.tool=='select'
# Segment drag keeps endpoints and the existing branch attached.
start=screen(c,[320,40]);end=screen(c,[320,10]);QTest.mousePress(c,Qt.LeftButton,pos=start);QTest.mouseMove(c,end);assert c.wire_drag;QTest.mouseRelease(c,Qt.LeftButton,pos=end);QTest.qWait(30)
assert len({d['nets']['p'] for d in w.cell['devices']})==1
assert w.cell['wires'][0]['points'][0]==[100,100] and w.cell['wires'][0]['points'][-1]==[400,100]
w.undo();assert w.cell['wires'][0]['points']==[[100,100],[100,40],[400,40],[400,100]]
# Delete a branch through the actual editor shortcut; undo restores topology.
branch=w.cell['wires'][1];w.select([branch['id']],'schematic');c.setFocus();key(c,Qt.Key_Delete);assert len(w.cell['wires'])==1;assert w.cell['devices'][2]['nets']['p']!=w.cell['devices'][0]['nets']['p'];key(c,Qt.Key_Z,Qt.ControlModifier);assert len(w.cell['wires'])==2
# Rotation while placing has no premature design commit and persists at placement.
w.begin_placement(3);before=digest(w.project);key(c,Qt.Key_R);assert c.placement['rotation']==90 and digest(w.project)==before
key(c,Qt.Key_R,Qt.ShiftModifier);assert c.placement['rotation']==0;QTest.mouseClick(w.rotate_button,Qt.LeftButton);assert c.placement['rotation']==90
click(c,[520,300]);placed=w.cell['devices'][-1];assert placed['kind']=='L' and placed['rotation']==90
# The project outline is a supported keyboard context too.
w.outline.setCurrentRow(w.outline.count()-1);w.outline.setFocus();key(w.outline,Qt.Key_R);assert w.cell['devices'][-1]['rotation']==180
# Typing R/W/P and Delete in an inspector never edits the circuit.
w.select([placed['id']]);field=w.form_fields['Name'];field.setFocus();field.selectAll();rotation=w.cell['devices'][-1]['rotation'];key(field,Qt.Key_R);key(field,Qt.Key_W);key(field,Qt.Key_P);assert field.text()=='rwp' and w.cell['devices'][-1]['rotation']==rotation;key(field,Qt.Key_Delete);assert len(w.cell['devices'])==4;w.build_inspector()
# A connected component rotation preserves electrical terminal identity.
w.select([w.cell['devices'][0]['id']]);before_nets=[clone(d['nets']) for d in w.cell['devices']];c.setFocus();key(c,Qt.Key_R);assert w.cell['devices'][0]['rotation']==90
assert [d['nets'] for d in w.cell['devices']]==before_nets;key(c,Qt.Key_R,Qt.ShiftModifier);assert w.cell['devices'][0]['rotation']==0;w.undo();w.undo()
# Blank-space completion, exact off-grid pins, cancellation and elbow flip.
key(c,Qt.Key_W);click(c,[500,40]);QTest.mouseMove(c,screen(c,[550,90]));assert c.wire_horizontal;key(c,Qt.Key_Space);assert not c.wire_horizontal
key(c,Qt.Key_Tab);assert c.wire_horizontal;count=len(w.cell['wires']);key(c,Qt.Key_Escape);assert c.tool=='connect' and not c.wire_points and len(w.cell['wires'])==count
click(c,[500,40]);click(c,[550,40]);key(c,Qt.Key_Return);assert len(w.cell['wires'])==count+1 and c.tool=='connect';key(c,Qt.Key_Escape)
# Mouse snapping retains exact terminal coordinates even off the drawing grid.
p,cell=circuit();cell['devices'][0].update(x=103.5,y=155);c=setup(p);key(c,Qt.Key_W);click(c,[103.5,105])
assert c.wire_points[0]==[103.5,105];click(c,[400,100]);assert w.cell['wires'][0]['points'][0]==[103.5,105]
assert w.cell['devices'][0]['nets']['p']==w.cell['devices'][1]['nets']['p'];key(c,Qt.Key_Escape)
# Crossings are open; J deliberately adds/removes the dot.
p=example('empty');p['cells'][0].update(wires=[{'id':uid(),'points':[[100,100],[300,100]]},{'id':uid(),'points':[[200,40],[200,180]]}],junctions=[]);c=setup(p)
a,b=w.cell['wires'];g=wiring.graph(w.cell);assert g[('wire',a['id'])]!=g[('wire',b['id'])]
target=screen(c,[200,100]);assert c.rect().contains(target),(c.size(),target)
QTest.mouseMove(c,target)
# Windows can queue a cursor move behind the immediately following key event.
# Wait for the real move to arrive instead of editing the canvas pointer in the test.
deadline=time.monotonic()+1
while c.drag!=QPointF(200,100) and time.monotonic()<deadline:QTest.qWait(10)
assert c.drag==QPointF(200,100),('Crossing hover was not delivered',c.drag)
key(c,Qt.Key_J);assert [200,100] in w.cell['junctions'],('J did not toggle the crossing',c.drag,app.focusWidget());g=wiring.graph(w.cell);assert g[('wire',a['id'])]==g[('wire',b['id'])]
key(c,Qt.Key_J);assert not w.cell['junctions']
# Every top-level underlined mnemonic opens its menu using an actual Alt event.
for action in w.menuBar().actions():
 text=action.text();index=text.find('&')
 if index<0:continue
 letter=text[index+1].upper();c.setFocus();key(c,getattr(Qt,'Key_'+letter),Qt.AltModifier)
 menu=action.menu();assert menu.isVisible(),text;key(menu,Qt.Key_Escape)
# Mnemonic selects a safe menu command and command-palette entries remain alive.
view_action=next(a for a in w._menu_actions if a.text()=='&View');view=view_action.menu();fit=next(a for a in view.actions() if a.text().replace('&','')=='Fit design');c.setFocus();key(c,Qt.Key_V,Qt.AltModifier);letter=fit.text()[fit.text().index('&')+1].upper();key(view,getattr(Qt,'Key_'+letter));assert c.auto_fit
for _,a in w._commands:assert a.text()
def palette_test():
 dlg=app.activeModalWidget();dlg.query.setText('Rotate counterclockwise');assert any(dlg.items.item(i).text().startswith('Rotate counterclockwise') for i in range(dlg.items.count()));QTest.keyClick(dlg.query,Qt.Key_Escape)
QTimer.singleShot(40,palette_test);w.command_palette()
# Screenshot of the actual native RC circuit and corrected L/I artwork.
p=example();cell=p['cells'][0];wiring.migrate(cell,p)
cell['devices'] += [device('L','L1',230,500,net_labels={}),device('I','I1',500,500,net_labels={})];wiring.rebuild(cell,p)
w.set_project(p);w.resize(1440,940);w.navtabs.setCurrentIndex(1);w.inspector.show();w.select([w.cell['devices'][-1]['id']]);w.fit_active();c=w.schematic;c.setFocus();QTest.qWait(120);assert w.grab().save(str(ROOT/'build'/'workspace-wiring-0.3.1.png'))
w.resize(1100,760);QTest.qWait(80);assert w.width()==1100;w.grab().save(str(ROOT/'build'/'workspace-wiring-compact.png'))
w.saved_hash=digest(w.project);w.close();app.processEvents();assert not errors,errors
print('PASS: manual bend placement, branch topology, segment drag, delete/undo, rotation preview/selection/outline, typing safety, crossings/junctions, finish/cancel/flip, Alt menu mnemonics, palette, compact desktop and screenshots.')
