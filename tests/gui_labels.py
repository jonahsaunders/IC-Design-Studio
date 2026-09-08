"""Actual mouse/keyboard placement, dragging, inspection and persistence."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
profile=ROOT/'build/label-profile';os.environ['XDG_DATA_HOME']=str(profile/'data');os.environ['XDG_CONFIG_HOME']=str(profile/'config')
from PySide6.QtCore import Qt,QPointF,QSettings,QTimer
from PySide6.QtWidgets import QApplication,QInputDialog
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import clone,digest,save_project,load_project
from icstudio import net_labels
from test_wiring import circuit
errors=[]
def exception(t,v,tb):
 import traceback
 errors.append(str(v));traceback.print_exception(t,v,tb)
sys.excepthook=exception
app=QApplication([]);app.setStyle('Fusion');QSettings('ICDesignStudio','Studio').clear();w=Studio(False);w.resize(1440,940);w.show();QTest.qWait(100)
w.error=lambda text:(_ for _ in ()).throw(AssertionError(text))
p,cell=circuit();w.set_project(p);c=w.schematic;c.auto_fit=False;c.scale=1.3;c.offset=QPointF(40,90);c.setFocus();QTest.qWait(60)
def screen(pt):return (QPointF(*pt)*c.scale+c.offset).toPoint()
def click(pt):QTest.mouseClick(c,Qt.LeftButton,pos=screen(pt));QTest.qWait(25)
def key(k,mod=Qt.NoModifier):QTest.keyClick(c,k,mod);QTest.qWait(25)
key(Qt.Key_W);click([100,100]);click([400,100]);key(Qt.Key_Escape)
def enter_name():
 dlg=app.activeModalWidget();assert isinstance(dlg,QInputDialog);dlg.setTextValue('out');dlg.accept()
QTimer.singleShot(60,enter_name);key(Qt.Key_L);assert c.tool=='label';click([250,100]);assert w.cell['wires'][0]['net']=='out';label=w.cell['labels'][0];ident=label['id'];anchor=clone(label['anchor'])
# Drag label text, preserve anchor and electrical name.
a=screen([270,80]);b=screen([300,50]);QTest.mousePress(c,Qt.LeftButton,pos=a);QTest.mouseMove(c,b);QTest.mouseRelease(c,Qt.LeftButton,pos=b);QTest.qWait(40)
assert w.cell['labels'][0]['anchor']==anchor;assert w.cell['labels'][0]['offset']!=label['offset'];assert w.cell['wires'][0]['net']=='out';w.undo();w.redo()
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
print('PASS: L label dialog, click placement, artwork drag, N whole-net inspector, rename, G ground, R preview, delete/undo, save/reopen, compact workspace.')
