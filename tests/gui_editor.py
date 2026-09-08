"""Actual Qt acceptance for the 0.11 everyday editing workflow."""
import argparse,json,os,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
a=argparse.ArgumentParser();a.add_argument('--output',required=True);args=a.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['XDG_CONFIG_HOME']=str(out/'profile/config');os.environ['XDG_DATA_HOME']=str(out/'profile/data')
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import example,clone,uid,digest,save_project,load_project
from icstudio.layout import rect,polygon,kdb
from icstudio.editor_ops import resolve_array
errors=[];sys.excepthook=lambda t,v,tb:(errors.append(str(v)),traceback.print_exception(t,v,tb))
app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.settings.remove('editor/workspaces');w.resize(1660,1100);w.error=lambda e:errors.append(str(e));w.show();w.activateWindow();QTest.qWait(180)
p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',0,0,2000,2000),rect('metal2',500,500,2000,2000)];w.set_project(p);w.mode_combo.setCurrentIndex(1);w.refresh(True);QTest.qWait(80);canvas=w.layout
def point(x,y):return (QPointF(x,y)*canvas.scale+canvas.offset).toPoint()
def accept(dlg):dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click();QTest.qWait(30);w.activateWindow();QTest.qWait(30)
checks=[]
# A box must enclose the entire instance, including all of its rendered shapes.
from icstudio.canvas import Canvas
view=Canvas('layout');shapes=[rect('metal1',0,0,1000,1000),rect('metal1',4000,0,1000,1000)]
for s in shapes:s.update(source_id=s['id'],id='placement')
view.set_data({'shapes':shapes},p['pdk']);view.box_mode='Inside';assert not view.editor_marquee(QRectF(-10,-10,1100,1100));assert view.editor_marquee(QRectF(-10,-10,5020,1020))==['placement'];view.box_mode='Crossing';assert view.editor_marquee(QRectF(-10,-10,1100,1100))==['placement'];view.close();checks.append('inside marquee encloses complete physical instance; crossing includes intersections')
# One-key profile commands and normal typing in property fields.
w.set_keyboard_profile('Virtuoso-inspired',{});canvas.setFocus();QTest.keyClick(canvas,Qt.Key_R);assert canvas.tool=='rect';QTest.keyClick(canvas,Qt.Key_Escape);assert canvas.tool=='select'
w.start_layout_tool('path');w.editor_width.setFocus();w.editor_width.selectAll();QTest.keyClicks(w.editor_width,'0.5');assert canvas.tool=='path';w.apply_editor_options();assert canvas.line_width==500;w.cancel_tool()
with_error=False
try:w.set_keyboard_profile('Studio',{'move':'R'})
except ValueError:with_error=True
assert with_error;checks.append('editable shortcut profiles, conflict rejection and text-field isolation')
try:w.set_keyboard_profile('Studio',{'move':'Ctrl+1'});raise AssertionError('Global dock shortcut was accepted')
except ValueError:pass
# Layer visibility, selectability and appearance have no effect on design/PDK hashes.
before=digest(w.project);row=next(i for i,l in enumerate(w.project['pdk']['layers']) if l['name']=='metal2')
w.layer_table.item(row,2).setCheckState(Qt.Unchecked);assert canvas.hit(QPointF(1000,1000))['layer']=='metal1';assert 'metal2' in canvas.visible_layers
w.layer_table.item(row,2).setCheckState(Qt.Checked);w.editor_layer_style(row,4);dlg=w._workflow_dialog;dlg.fields['color'].setText('#ffa86a');dlg.fields['pattern'].setCurrentText('Hatch');accept(dlg);assert canvas.layer_styles['metal2']['pattern']=='Hatch';assert digest(w.project)==before
checks.append('independent layer controls and persistent appearance without PDK mutation')
# Cycle exact overlaps and filter by object category.
canvas.setFocus();QTest.mouseClick(canvas,Qt.LeftButton,pos=point(1000,1000));one=w.selection[:];QTest.keyClick(canvas,Qt.Key_Tab);assert w.selection!=one
w.editor_filters['shapes'].setChecked(False);assert canvas.hit(QPointF(1000,1000)) is None;w.editor_filters['shapes'].setChecked(True)
checks.append('overlap cycling and selection filters')
# Move using two reference clicks and complete keyboard undo/redo.
sid=w.cell['shapes'][0]['id'];w.select([sid],'layout');before=clone(w.cell['shapes'][0]);w.start_layout_tool('move_ref')
QTest.mouseClick(canvas,Qt.LeftButton,pos=point(0,0));QTest.mouseMove(canvas,point(1000,3000));QTest.mouseClick(canvas,Qt.LeftButton,pos=point(1000,3000));assert w.cell['shapes'][0]['points']!=before['points'];w.cancel_tool();canvas.setFocus();QTest.keyClick(canvas,Qt.Key_Z,Qt.ControlModifier);assert w.cell['shapes'][0]==before
QTest.keyClick(canvas,Qt.Key_Z,Qt.ControlModifier|Qt.ShiftModifier);assert w.cell['shapes'][0]!=before;w.undo();checks.append('reference move preview and native undo/redo')
# Reference copy and repeat command keep source identity.
w.select([sid],'layout');w.start_layout_tool('copy_ref');QTest.mouseClick(canvas,Qt.LeftButton,pos=point(0,0));QTest.mouseClick(canvas,Qt.LeftButton,pos=point(4000,0));assert len(w.cell['shapes'])==3;w.cancel_tool();QTest.keyClick(canvas,Qt.Key_F4);assert canvas.tool=='copy_ref';w.cancel_tool();w.undo();checks.append('reference copy and repeat last command')
# Drag a rectangle edge; one undo restores the exact original object.
w.select([sid],'layout');w.start_layout_tool('edge');before=clone(w.cell['shapes'][0]);QTest.mousePress(canvas,Qt.LeftButton,pos=point(2000,1000));QTest.mouseMove(canvas,point(3000,1000),40);QTest.mouseRelease(canvas,Qt.LeftButton,pos=point(3000,1000));assert polygon(w.cell['shapes'][0]).bbox().width()>2000;w.cancel_tool();w.undo();assert w.cell['shapes'][0]==before;checks.append('on-canvas edge editing and atomic undo')
# Multi-object properties update both, preserving ids, with one undo.
ids=[s['id'] for s in w.cell['shapes']];w.select(ids,'layout');dlg=w.editor_properties();dlg.fields['net_action'].setCurrentText('Set net');dlg.fields['net'].setText('BUS');accept(dlg);assert all(s['net']=='BUS' for s in w.cell['shapes']);w.undo();checks.append('multi-object property transaction')
# True context editing: parent/sibling geometry is visible but cannot be selected.
p=example('empty');parent=p['cells'][0];child={'id':uid(),'name':'unit','ports':[],'devices':[],'shapes':[rect('metal1',0,0,1000,1000)]};p['cells'].append(child);inst={'id':uid(),'name':'X1','cell':child['id'],'x':5000,'y':6000,'rotation':90,'mirror':True,'nx':1,'ny':1};parent['layout_instances']=[inst];parent['shapes']=[rect('metal2',0,0,1000,1000)];w.set_project(p);w.mode_combo.setCurrentIndex(1);w.select([inst['id']],'layout');w.enter_edit_context();QTest.qWait(80);assert w.cid==child['id'] and canvas.context_shapes;assert 'shared cell' in w.breadcrumb.text();sid=w.cell['shapes'][0]['id'];w.select([sid],'layout');w.editor_execute('move_ref',{'dx':500,'dy':0});assert w.cell['shapes'][0]['points'][0]==[500,0];assert w.project['cells'][0]['shapes']==parent['shapes'];w.undo();w.grab().save(str(out/'hierarchy-context.png'));w.leave_edit_context();assert w.cid==parent['id'];checks.append('rotated/mirrored hierarchy context, read-only surroundings and undo')
# Library/cell/view navigation and named workspace persistence.
dlg=w.editor_library();dlg.fields['cells'].setCurrentRow(1);dlg.fields['views'].setCurrentRow(1)
next(b for b in dlg.findChildren(__import__('PySide6.QtWidgets',fromlist=['QPushButton']).QPushButton) if b.text()=='Open view').click();assert w.cid==child['id']
w.set_keyboard_profile('KLayout-inspired',{});w.mode_combo.setCurrentIndex(2);w.save_editor_workspace('Review');w.mode_combo.setCurrentIndex(0);w.load_editor_workspace('Review');assert w.mode_combo.currentIndex()==2 and w.key_profile=='KLayout-inspired';checks.append('library/cell/view browser and saved linked-view workspace')
# Save/reopen and inspect the final workspace.
path=out/'editor-roundtrip.icproj';save_project(w.project,path);before=digest(w.project);w.set_project(load_project(path),path);assert digest(w.project)==before
w.mode_combo.setCurrentIndex(1);w.nav.show();w.inspector.show();w.resizeDocks([w.nav,w.inspector],[360,290],Qt.Horizontal);QTest.qWait(80);w.grab().save(str(out/'editor-workspace.png'));checks.append('project round trip')
# Interactive instance preview uses the actual child geometry and rotation.
w.cid=parent['id'];w.refresh(True);QTest.qWait(50);dlg=w.editor_place_instance();accept(dlg);assert canvas.tool=='instance_place' and canvas.instance_preview
w.editor_angle.setCurrentIndex(1);before=len(w.cell['layout_instances']);canvas.fit();QTest.mouseMove(canvas,point(2500,2500));QTest.mouseClick(canvas,Qt.LeftButton,pos=point(2500,2500));assert len(w.cell['layout_instances'])==before+1 and w.cell['layout_instances'][-1]['rotation']==90;w.cancel_tool();w.undo();checks.append('physical cell placement preview and rotation')
assert not errors,errors;w.saved_hash=digest(w.project);w.close();(out/'report.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2));print('PASS',len(checks),'0.11 native editor workflows')
