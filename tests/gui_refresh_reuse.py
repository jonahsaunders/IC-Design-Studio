"""Native refresh checks: reused rows still follow edits, undo and UI state."""
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
(ROOT/'build').mkdir(exist_ok=True)
profile=tempfile.TemporaryDirectory(prefix='gui-refresh-',dir=ROOT/'build')
os.environ['XDG_CONFIG_HOME']=str(Path(profile.name)/'config')
os.environ['XDG_DATA_HOME']=str(Path(profile.name)/'data')

from PySide6.QtCore import Qt,QSettings,QStandardPaths
from PySide6.QtWidgets import QApplication
from icstudio.gui import Studio
from icstudio.layout import rect
from icstudio.model import clone,device,digest,example,uid

QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(Path(profile.name)/'settings'))
QStandardPaths.writableLocation=staticmethod(lambda kind:str(Path(profile.name)/str(kind.value)))
app=QApplication([]);app.setStyle('Fusion')
w=Studio(recover=False);w.live_check.setChecked(False)
w.error=lambda text:(_ for _ in ()).throw(AssertionError(text))
p=example('empty');cell=p['cells'][0]
cell['devices']=[device('R','R1',0,0),device('R','R2',200,0)]
first,second=[d['id'] for d in cell['devices']]
cell['shapes']=[rect('metal1',0,0,500,500),rect('metal1',1000,0,500,500)]
for shape,did in zip(cell['shapes'],(first,second)):shape['device_id']=did
cell['analog_constraints']=[{'id':uid(),'kind':'symmetry','name':'Matched placement','members':[first,second],'axis':'x','coordinate':750}]
w.set_project(p);w.select([first],'schematic')
outline=w.outline.item(0);placement=w.placement_table.item(0,0)
constraint=w.constraint_table.item(0,3);layer=w.layer_table.item(0,0)
assert constraint.text()=='Satisfied'
net_resets=[];via_resets=[]
w.editor_net.model().modelReset.connect(lambda:net_resets.append(True))
w.editor_via.model().modelReset.connect(lambda:via_resets.append(True))
w.editor_net.setCurrentText('draft_route')

# Ordinary schematic geometry changes retain presentation rows and draft text.
w.capture_commit(lambda q:q['cells'][0]['devices'][0].update(x=40),'Move schematic')
assert w.outline.item(0) is outline and outline.isSelected()
assert w.placement_table.item(0,0) is placement
assert w.constraint_table.item(0,3) is constraint
assert w.layer_table.item(0,0) is layer
assert w.editor_net.currentText()=='draft_route' and not net_resets and not via_resets
w.undo();w.redo();assert w.outline.item(0) is outline

# Data edits update reused rows, including undo and redo, without stale caches.
w.commit(lambda q:q['cells'][0]['devices'][0].update(name='RINPUT',value='22k'),'Rename resistor')
assert w.outline.item(0) is outline and outline.text().startswith('RINPUT')
assert outline.toolTip()=='RINPUT · 22k'
assert w.placement_table.item(0,0) is placement and placement.text()=='RINPUT'
w.undo();assert outline.text().startswith('R1') and placement.text()=='R1'
w.redo();assert outline.text().startswith('RINPUT') and placement.text()=='RINPUT'
w.select([second],'schematic');w.refresh()
assert not outline.isSelected() and w.outline.item(1).isSelected()

# Physical findings and routing suggestions update after geometry/net changes.
def move_shape(q):
    shape=q['cells'][0]['shapes'][0]
    shape['points']=[[x+500,y] for x,y in shape['points']]
    shape['net']='route_added'
w.commit(move_shape,'Move physical footprint')
assert constraint.text()=='Needs attention'
assert w.editor_net.findText('route_added')>=0 and w.editor_net.currentText()=='draft_route'
w.undo();assert constraint.text()=='Satisfied' and w.editor_net.findText('route_added')<0

# Row insertions/deletions and project replacement refresh identity and content.
w.commit(lambda q:q['cells'][0]['devices'].append(device('C','C1',400,0)),'Add capacitor')
assert w.outline.count()==3 and w.placement_table.rowCount()==3
assert w.outline.item(2).text().startswith('C1')
w.undo();assert w.outline.count()==2 and w.placement_table.rowCount()==2
replacement=clone(w.project);replacement['cells'][0]['devices'][0]['name']='RREOPENED'
w.set_project(replacement)
assert w.outline.item(0).text().startswith('RREOPENED')
assert w.placement_table.item(0,0).text()=='RREOPENED'

# Layer display choices are UI-only; updates reflect visibility and style.
unchanged=digest(w.project);name=w.project['pdk']['layers'][0]['name']
w.layout.visible_layers.discard(name);w.refresh_editor_layers()
assert w.layer_table.item(0,1).checkState()==Qt.Unchecked
w.layout.layer_styles[name]={'color':'#ff9933','pattern':'Hatch'};w.refresh_editor_layers()
assert w.layer_table.item(0,0).foreground().color().name()=='#ff9933'
assert w.layer_table.item(0,4).text()=='Hatch' and digest(w.project)==unchanged
w.dark=not w.dark;w.refresh_outline()
assert w.outline.item(0).text().startswith('RREOPENED')

# Plain reference moves share untouched geometry and retain exact undo/redo.
p=example('empty');cell=p['cells'][0]
cell['shapes']=[rect('metal1',0,0,500,500),rect('metal1',2000,0,500,500)]
w.set_project(p);w.mode_combo.setCurrentIndex(1)
sid=w.cell['shapes'][0]['id'];w.select([sid],'layout')
before=clone(w.cell);untouched=w.cell['shapes'][1]
w.editor_execute('move_ref',{'dx':500,'dy':0})
assert w.cell['shapes'][1] is untouched
assert w.history.undo_stack[-1][1]=='Move by reference'
assert w.cell['shapes'][0]['points'][0]==[500,0]
assert w.selection==[sid] and w.layout.selection==[sid]
assert w.form_fields['Left'].text()=='0.5'
after=clone(w.cell);w.undo();assert w.cell==before
w.redo();assert w.cell==after
w.layout.locked_layers.add('metal1');before=digest(w.project)
try:w.editor_execute('move_ref',{'dx':500,'dy':0});raise AssertionError('Locked shape moved')
except ValueError:pass
assert digest(w.project)==before;w.layout.locked_layers.clear()

# Complete-group validation and live transaction hooks must remain in force.
w.commit(lambda q:[s.update(via_group='same_stack') for s in q['cells'][0]['shapes']],'Group via')
before=digest(w.project)
try:w.editor_execute('move_ref',{'dx':500,'dy':0});raise AssertionError('Partial via stack moved')
except ValueError:pass
assert digest(w.project)==before
w.undo();original_move=w.history.commit_shape_move
w.history.commit_shape_move=lambda *a,**k:(_ for _ in ()).throw(AssertionError('Live move bypassed transaction'))
w.live_client=object()
try:w.editor_execute('move_ref',{'dx':500,'dy':0})
finally:w.live_client=None;w.history.commit_shape_move=original_move
assert w.cell['shapes'][0]['points'][0]==[1000,0]
w.maybe_save=lambda:True;w.close();app.processEvents();profile.cleanup()
print('PASS: presentation reuse, properties, selection, findings, nets, undo/redo, project replacement, layer display and guarded reference moves.')
