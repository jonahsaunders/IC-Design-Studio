"""Bounded, selectable logical connectivity cones from compiler netlists."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPen, QBrush
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem
from .digital_inspection import cone


class LogicView(QGraphicsView):
    def __init__(self, workspace):
        super().__init__(); self.workspace = workspace; self.setScene(QGraphicsScene(self))
        self.setAccessibleName('Logical fan-in and fan-out cone'); self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.scene().selectionChanged.connect(self.selected)

    def load(self, index, selected):
        self.scene().clear(); graph = cone(index, selected['module'], selected['name']); positions = {}; rows = {}
        for node in graph['nodes']:
            level = node['distance']; row = rows.get(level,0); rows[level] = row+1
            positions[node['name']] = (level*250, row*100)
        for edge in graph['edges']:
            a = positions[edge['source']]; b = positions[edge['target']]
            self.scene().addLine(a[0]+180,a[1]+30,b[0],b[1]+30,QPen(QColor('#7792bc'),1.5))
        for node in graph['nodes']:
            x,y = positions[node['name']]
            rect = self.scene().addRect(QRectF(0,0,180,64),QPen(QColor('#92b2ed')),QBrush(QColor('#263b56')))
            rect.setPos(x,y)
            rect.setFlag(QGraphicsItem.ItemIsSelectable); rect.setData(0,node)
            text = self.scene().addText(node['name'][:24]+'\n'+node.get('type','net')[:24]); text.setDefaultTextColor(QColor('#edf2fa')); text.setPos(x+8,y+4)
            text.setParentItem(rect); text.setPos(8,4)
            rect.setToolTip(node['name']+'\n'+node.get('type','net')); text.setAcceptedMouseButtons(Qt.NoButton)
        if graph['truncated']:
            text = self.scene().addText('Cone limited to 80 objects. Select a neighbor to continue.'); text.setPos(0,-40)
        self.fitInView(self.scene().itemsBoundingRect().adjusted(-20,-20,20,20),Qt.KeepAspectRatio)

    def selected(self):
        items = self.scene().selectedItems()
        if items:
            self.workspace.probe(items[0].data(0))

    def wheelEvent(self,event):
        factor = 1.15 if event.angleDelta().y()>0 else 1/1.15; self.scale(factor,factor)
