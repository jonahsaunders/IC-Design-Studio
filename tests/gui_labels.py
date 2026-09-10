"""Actual mouse/keyboard placement, dragging, inspection and persistence."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
parser=argparse.ArgumentParser();parser.add_argument('--compact-canvas',action='store_true');args=parser.parse_args()
profile=ROOT/'build/label-profile'/('compact' if args.compact_canvas else 'normal');os.environ['XDG_DATA_HOME']=str(profile/'data');os.environ['XDG_CONFIG_HOME']=str(profile/'config')
from PySide6.QtCore import Qt,QEvent,QPointF,QSettings,QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication,QInputDialog
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import clone,digest,save_project,load_project
from icstudio import net_labels
from test_wiring import circuit
errors=[]
evidence=ROOT/'build/label-evidence'/('compact' if args.compact_canvas else 'normal');evidence.mkdir(parents=True,exist_ok=True)
drag_states=[]
def exception(t,v,tb):
 import traceback
 errors.append(str(v));traceback.print_exception(t,v,tb)
 (evidence/'failure.json').write_text(json.dumps({'error':str(v),'platform':sys.platform,'drag_states':drag_states},indent=2),encoding='utf-8')
 if 'w' in globals():w.grab().save(str(evidence/'failure.png'))
sys.excepthook=exception
app=QApplication([]);app.setStyle('Fusion');QSettings('ICDesignStudio','Studio').clear();w=Studio(False);w.resize(1440,940);w.show();QTest.qWait(100)
w.error=lambda text:(_ for _ in ()).throw(AssertionError(text))
p,cell=circuit();w.set_project(p);c=w.schematic;c.auto_fit=False;c.scale=1.3;c.offset=QPointF(40,90);c.setFocus();QTest.qWait(60)
if args.compact_canvas:c.setFixedSize(250,220);QTest.qWait(60)
def screen(pt):return (QPointF(*pt)*c.scale+c.offset).toPoint()
def center_on(pt):
 c.auto_fit=False;c.offset=QPointF(c.rect().center())-QPointF(*pt)*c.scale;c.update()
def click(pt):
 # Inspector widths vary by platform. Pan an offscreen model point into
 # the actual viewport before sending its click; never click outside it.
 if not c.rect().adjusted(12,12,-12,-12).contains(screen(pt)):center_on(pt)
 at=screen(pt);assert c.rect().contains(at),(pt,at,c.rect())
 QTest.mouseClick(c,Qt.LeftButton,pos=at);QTest.qWait(25)
def key(k,mod=Qt.NoModifier):QTest.keyClick(c,k,mod);QTest.qWait(25)
key(Qt.Key_W);click([100,100]);click([400,100]);key(Qt.Key_Escape)
def enter_name():
 dlg=app.activeModalWidget();assert isinstance(dlg,QInputDialog);dlg.setTextValue('out');dlg.accept()
QTimer.singleShot(60,enter_name);key(Qt.Key_L);assert c.tool=='label';click([250,100]);assert w.cell['wires'][0]['net']=='out';label=w.cell['labels'][0];ident=label['id'];anchor=clone(label['anchor'])
# Drag label text, preserve anchor and electrical name.
# Placing the label rebuilds the inspector and can refit/resize the canvas.
# Center the artwork in the actual viewport after layout has settled.
# A fixed offset can put its model coordinates outside a narrow canvas.
QTest.qWait(60);c.auto_fit=False;c.scale=1.3
original_offset=clone(label['offset']);center=c.label_box(label).center()
center_on([center.x(),center.y()])
a=screen([center.x(),center.y()]);b=screen([center.x()+30,center.y()-30])
drag_states.append({'event':'Viewport','size':[c.width(),c.height()],
                    'start':[a.x(),a.y()],'end':[b.x(),b.y()]})
assert c.rect().contains(a) and c.rect().contains(b),'Label drag is outside the canvas'
hit=c.hit(c.model(QPointF(a)));assert hit and hit['id']==ident,'Drag must start on label artwork'
delta=c.snap(c.model(QPointF(b)))-c.snap(c.model(QPointF(a)))
expected_offset=[original_offset[0]+delta.x(),original_offset[1]+delta.y()]
assert expected_offset!=original_offset,'Drag must cross a snap interval'
def drag_event(kind,position,button,buttons):
 # Deliver the complete button state directly to Qt. QTest.mouseMove uses
 # the platform cursor; avoid depending on its offscreen event delivery.
 event=QMouseEvent(kind,QPointF(position),QPointF(c.mapToGlobal(position)),button,buttons,Qt.NoModifier)
 QApplication.sendEvent(c,event)
 drag_states.append({'event':kind.name,'position':[position.x(),position.y()],
                     'moving':c.moving,'selection':list(c.selection),
                     'offset':clone(w.cell['labels'][0]['offset'])})
drag_event(QEvent.MouseButtonPress,a,Qt.LeftButton,Qt.LeftButton)
assert c.moving and c.selection==[ident],'Label drag did not start'
drag_event(QEvent.MouseMove,b,Qt.NoButton,Qt.LeftButton)
drag_event(QEvent.MouseButtonRelease,b,Qt.LeftButton,Qt.NoButton);QTest.qWait(40)
assert w.cell['labels'][0]['anchor']==anchor
assert w.cell['labels'][0]['offset']==expected_offset,(expected_offset,w.cell['labels'][0]['offset'],drag_states)
assert w.cell['wires'][0]['net']=='out'
w.undo();assert w.cell['labels'][0]['offset']==original_offset
w.redo();assert w.cell['labels'][0]['offset']==expected_offset
# Whole net inspector and rename through the real property form.
w.select([ident]);w.activateWindow();c.setFocus();QTest.qWait(30);key(Qt.Key_N);assert w.net=='out' and w.net_members.count()==2 and c.net=='out';w.select([ident]);f=w.form_fields['label:name'];f.setFocus();f.selectAll();QTest.keyClicks(f,'output');QTest.keyClick(f,Qt.Key_Return);QTest.qWait(40);assert w.cell['wires'][0]['net']=='output'
# Ground placement and rotation preview do not commit until the click.
c.setFocus();before=digest(w.project);key(Qt.Key_G);key(Qt.Key_R);assert digest(w.project)==before;click([400,200]);ground=w.cell['labels'][-1];assert ground['kind']=='ground' and ground['rotation']==90 and w.cell['devices'][1]['nets']['n']=='0'
# Delete, undo, save/reopen retain the connection and the artwork.
key(Qt.Key_Delete);assert w.cell['devices'][1]['nets']['n']!='0';key(Qt.Key_Z,Qt.ControlModifier);assert w.cell['devices'][1]['nets']['n']=='0'
path=ROOT/'build/labels-roundtrip.icproj';save_project(w.project,path);saved=clone(w.project);w.set_project(load_project(path),path);assert w.cell['labels']==saved['cells'][0]['labels']
w.select([w.cell['labels'][0]['id']]);w.fit_active();QTest.qWait(80);assert w.grab().save(str(ROOT/'build/workspace-labels-0.4.0.png'))
w.resize(1000,720);QTest.qWait(80);assert w.grab().save(str(ROOT/'build/workspace-labels-compact-0.4.0.png'))
w.saved_hash=digest(w.project);w.close();assert not errors,errors
(evidence/'report.json').write_text(json.dumps({'status':'passed','platform':sys.platform,
 'scale_factor':os.environ.get('QT_SCALE_FACTOR','1'),'compact_canvas':args.compact_canvas,'drag_states':drag_states,
 'checks':['Exact snapped artwork displacement','Anchor and net preserved','Undo and redo','Rename','Ground placement and rotation','Save and reopen']},indent=2),encoding='utf-8')
print('PASS: L label dialog, click placement, artwork drag, N whole-net inspector, rename, G ground, R preview, delete/undo, save/reopen, compact workspace.')
