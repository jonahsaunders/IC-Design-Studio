"""Layout picture invalidation and capture-preview isolation in native Qt."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
from icstudio.canvas import Canvas
from icstudio.layout import rect
from icstudio.model import clone,digest,example
from icstudio import wiring

app=QApplication([]);p=example('empty');cell=p['cells'][0]
cell['shapes']=[rect('metal1',0,0,500,500),rect('metal2',700,0,500,500)]
canvas=Canvas('layout');canvas.resize(500,350);canvas.show()
canvas.set_data(cell,p['pdk'],revision=1,immutable=True);canvas.scale=.2;canvas.offset=QPointF(30,30);canvas.auto_fit=False
canvas.grab();picture=canvas._layout_picture[2]
canvas.set_data({**cell,'devices':[]},p['pdk'],revision=2,immutable=True);canvas.grab()
assert canvas._layout_picture[2] is picture
for field,value in (('net','marked'),('layer','metal2'),('device_id','linked')):
    modified=clone(cell);modified['shapes'][0][field]=value
    canvas.set_data(modified,p['pdk'],['linked'],revision=3,immutable=True)
    actual=canvas.grab().toImage();assert canvas._layout_picture[2] is not picture
    canvas.cache_layout_pictures=False;expected=canvas.grab().toImage()
    assert actual==expected,field+' metadata gave stale cached geometry'
    canvas.cache_layout_pictures=True
    canvas.set_data(cell,p['pdk'],revision=4,immutable=True);canvas.grab();picture=canvas._layout_picture[2]

# Tech/style-only edits change cached colors, and undo restores the old image.
before=canvas.grab().toImage();tech=clone(p['pdk']);tech['layers'][0]['color']='#ff0011'
canvas.set_data(cell,tech,revision=4,immutable=True);actual=canvas.grab().toImage()
canvas.cache_layout_pictures=False;assert canvas.grab().toImage()==actual
canvas.cache_layout_pictures=True;canvas.set_data(cell,p['pdk'],revision=5,immutable=True)
assert canvas.grab().toImage()==before
canvas.layer_styles={'metal1':{'color':'#0033ff','pattern':'Hatch'}}
actual=canvas.grab().toImage();canvas.cache_layout_pictures=False
assert canvas.grab().toImage()==actual;canvas.close()

# A mouse-frame preview must never deep-copy unrelated physical geometry.
class PhysicalGeometry(list):
    def __deepcopy__(self,memo):raise AssertionError('Capture preview copied layout geometry')
p=example();cell=p['cells'][0];wiring.migrate(cell,p)
cell['shapes']=PhysicalGeometry([rect('metal1',0,0,500,500)])
view=Canvas('schematic');view.resize(800,500);view.set_data(cell,p['pdk']);view.show()
before=digest(cell);view.selection=[cell['devices'][0]['id']]
view.moving=True;view.anchor=QPointF(10,10);view.drag=QPointF(30,30);view.grab()
assert view.cell is cell and digest(cell)==before
view.moving=False;view.wire_drag=(cell['wires'][0]['id'],0);view.grab()
assert view.cell is cell and digest(cell)==before
view.close();print('PASS: cached layout pictures, metadata/technology/style invalidation and schematic preview isolation.')
