"""Compare chunk playback pixel-for-pixel with the independent direct renderer."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
from icstudio.canvas import Canvas
from icstudio.layout import rect
from icstudio.model import History,example,clone

app=QApplication([]);p=example('empty');cell=p['cells'][0]
cell['shapes']=[rect('metal1' if i%3 else 'metal2',(i%32)*400,(i//32)*400,600,600) for i in range(768)]
history=History(p);canvas=Canvas('layout');canvas.resize(600,500);canvas.show();canvas.auto_fit=False
canvas.scale=.035;canvas.offset=QPointF(35,35)
def compare():
    canvas.cache_layout_pictures=True;actual=canvas.grab().toImage()
    canvas.cache_layout_pictures=False;expected=canvas.grab().toImage()
    canvas.cache_layout_pictures=True
    assert actual==expected,'Chunk playback changed pixels'
def refresh():canvas.set_data(history.project['cells'][0],history.project['pdk'],revision=history.project['revision'],immutable=True)
refresh();compare();old={i:v[2] for i,v in canvas._layout_chunks.items()}
history.commit_shape_move(cell['id'],[cell['shapes'][10]['id']],100,0);refresh();compare()
assert canvas._layout_chunks[0][2] is not old[0]
assert canvas._layout_chunks[1][2] is old[1] and canvas._layout_chunks[2][2] is old[2]
history.undo();refresh();compare();history.redo();refresh();compare()
def highlight(selection=(),net='',changed=()):
    old={i:v[2] for i,v in canvas._layout_chunks.items()}
    canvas.selection=list(selection);canvas.net=net;compare()
    assert {i for i,v in canvas._layout_chunks.items() if v[2] is not old[i]}==set(changed)
highlight([cell['shapes'][3]['id']],changed=(0,))
highlight([cell['shapes'][600]['id']],changed=(0,2))
highlight(changed=(2,))
highlight(['not-in-this-cell'])
# Linked device selections and net cross-probing may span several chunks.
# Metadata changes, unversioned in-place edits and equivalent highlight masks
# must agree with the direct renderer too.
linked=clone(history.project['cells'][0])
for index in (10,600):linked['shapes'][index].update(device_id='linked-device',net='signal')
linked['shapes'][300]['net']='other'
linked['layout_label_mode']='explicit'
canvas.selection=[];canvas.set_data(linked,history.project['pdk']);compare()
highlight(['linked-device'],changed=(0,2))
highlight(net='signal')  # Same highlighted geometry, no pictures need rebuilding.
highlight(net='other',changed=(0,1,2))
highlight(changed=(1,))
linked['shapes'][600]['device_id']='second-device'
canvas.set_data(linked,history.project['pdk']);compare()
highlight(['linked-device'],changed=(0,))
highlight(['linked-device','second-device'],changed=(2,))
highlight(changed=(0,2))
canvas.net='other';linked['shapes'][300]['net']='changed-in-place'
canvas.set_data(linked,history.project['pdk']);compare()
canvas.net=''
# Reordering invalidates content even when the number of shapes is unchanged.
linked['shapes'].reverse();canvas.set_data(linked,history.project['pdk']);compare()
for dark in (False,True):canvas.dark=dark;compare()
for scale in (.065,.02):canvas.scale=scale;compare()
canvas.offset=QPointF(-150,70);compare()
canvas.visible_layers={'metal2'};compare()
canvas.layer_styles={'metal2':{'color':'#fa1091','pattern':'Hatch'}};compare()
canvas.close();print('PASS: chunk reuse, overlap order, undo/redo, selection, themes, scale, pan and layer styles')
