"""Indexed placement drawing and batched routing with linked CAD selection."""
from collections import defaultdict
import math

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPen, QBrush, QPainterPath
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem


def rectangle(c):
    return QRectF(c['x'], -c['y']-c['height'], c['width'], c['height'])


class Placement(QGraphicsItem):
    def __init__(self, view):
        super().__init__(); self.view = view
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption)

    def boundingRect(self):
        return self.view.bounds

    def paint(self, painter, option, widget=None):
        v = self.view
        if not v.show_cells: return
        exposed = option.exposedRect
        if v.density:
            painter.setPen(Qt.NoPen)
            for tile, area in v.areas.items():
                rect = v.tile_rect(tile)
                if not exposed.intersects(rect): continue
                ratio = min(1, area/(v.pitch*v.pitch))
                painter.setBrush(QColor.fromHsvF((1-ratio)*.45, .65, .8, .75))
                painter.drawRect(rect)
            return
        painter.setPen(QPen(QColor('#57bcae'), 0)); painter.setBrush(QBrush(QColor('#285f5a')))
        for name in v.candidates(exposed):
            rect = v.objects[name]
            if rect.intersects(exposed): painter.drawRect(rect)


class PhysicalView(QGraphicsView):
    def __init__(self, workspace):
        super().__init__(); self.workspace = workspace; self.setScene(QGraphicsScene(self))
        self.objects = {}; self.records = {}; self.tiles = defaultdict(list); self.areas = defaultdict(float)
        self.layers = {}; self.net_paths = {}; self.highlights = []; self.bounds = QRectF(); self.pitch = 1
        self.show_cells = True; self.density = False; self.routes = True; self.active_layer = ''
        self.setDragMode(QGraphicsView.ScrollHandDrag); self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setAccessibleName('Physical implementation; select an instance, drag to pan, scroll to zoom')
        self.setBackgroundBrush(QColor('#131820')); self.setMouseTracking(True)

    def tile_keys(self, rect):
        for x in range(math.floor(rect.left()/self.pitch), math.floor(rect.right()/self.pitch)+1):
            for y in range(math.floor(rect.top()/self.pitch), math.floor(rect.bottom()/self.pitch)+1):
                yield x, y

    def tile_rect(self, key):
        return QRectF(key[0]*self.pitch, key[1]*self.pitch, self.pitch, self.pitch)

    def candidates(self, rect):
        return {name for key in self.tile_keys(rect) for name in self.tiles.get(key, [])}

    def load(self, data):
        self.scene().clear(); self.objects = {}; self.records = {}; self.tiles.clear(); self.areas.clear()
        self.layers = {}; self.net_paths = {}; self.highlights = []; self.bounds = QRectF()
        if not data: return
        x1, y1, x2, y2 = data['die']; self.bounds = QRectF(x1,-y2,x2-x1,y2-y1)
        self.pitch = max(self.bounds.width(),self.bounds.height())/32
        self.scene().addRect(self.bounds,QPen(QColor('#92a0b8'),0))
        for c in data['components']:
            rect = rectangle(c); self.objects[c['name']] = rect; self.records[c['name']] = c
            for key in self.tile_keys(rect):
                self.tiles[key].append(c['name']); overlap = rect.intersected(self.tile_rect(key))
                self.areas[key] += overlap.width()*overlap.height()
        self.placement = Placement(self); self.scene().addItem(self.placement)
        paths = defaultdict(QPainterPath)
        for segment in data['segments']:
            a,b = segment['points']; path = paths[segment['layer']]
            path.moveTo(a[0],-a[1]); path.lineTo(b[0],-b[1])
            key = segment['net']; net = self.net_paths.setdefault(key,QPainterPath())
            net.moveTo(a[0],-a[1]); net.lineTo(b[0],-b[1])
        for i,(name,path) in enumerate(sorted(paths.items())):
            item = self.scene().addPath(path,QPen(QColor.fromHsv((i*67+265)%360,125,205,150),0))
            self.layers[name] = item
        self.set_filters(); self.scene().setSceneRect(self.bounds); self.fit()

    def set_filters(self, cells=None, routes=None, density=None, layer=None):
        if cells is not None: self.show_cells = cells
        if routes is not None: self.routes = routes
        if density is not None: self.density = density
        if layer is not None: self.active_layer = layer
        for name,item in self.layers.items(): item.setVisible(self.routes and (not self.active_layer or name == self.active_layer))
        self.viewport().update()

    def highlight(self, names, nets=()):
        for item in self.highlights: self.scene().removeItem(item)
        self.highlights = []
        for name in names:
            rect = self.objects.get(name)
            if rect is None: continue
            item = self.scene().addRect(rect,QPen(QColor('#ffd479'),0),QBrush(QColor(255,212,121,80)))
            item.setData(0,name); item.setFlag(QGraphicsItem.ItemIsSelectable); item.setSelected(True); item.setZValue(3)
            self.highlights.append(item)
        for name in nets:
            path = self.net_paths.get(name)
            if path is not None:
                item = self.scene().addPath(path,QPen(QColor('#ffcd63'),0)); item.setZValue(4); self.highlights.append(item)

    def find(self, name):
        names = [n for n in self.objects if name.casefold() in n.casefold()]
        nets = [n for n in self.net_paths if name.casefold() in n.casefold()]
        self.highlight(names,nets)
        self.workspace.window.message.setText(f'{len(names)} instances · {len(nets)} routed nets match {name}')
        if len(names)==1: self.workspace.probe_object(names[0])

    def fit(self):
        if not self.bounds.isEmpty(): self.fitInView(self.bounds,Qt.KeepAspectRatio)

    def mousePressEvent(self,event):
        self.press = event.position(); super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        if event.button()!=Qt.LeftButton or (event.position()-self.press).manhattanLength()>4: return
        point = self.mapToScene(event.position().toPoint()); rect = QRectF(point.x()-.01,point.y()-.01,.02,.02)
        matches = [n for n in self.candidates(rect) if self.objects[n].contains(point)]
        if matches:
            name = min(matches,key=lambda n:self.objects[n].width()*self.objects[n].height())
            self.highlight([name]); self.workspace.probe_object(name)

    def mouseMoveEvent(self,event):
        super().mouseMoveEvent(event)
        point = self.mapToScene(event.position().toPoint()); rect = QRectF(point.x()-.01,point.y()-.01,.02,.02)
        name = next((n for n in self.candidates(rect) if self.objects[n].contains(point)),None)
        self.setToolTip(name+'\n'+self.records[name]['master'] if name else '')

    def wheelEvent(self,event):
        factor = 1.2 if event.angleDelta().y()>0 else 1/1.2
        if .0001 < self.transform().m11()*factor < 10000: self.scale(factor,factor)

    def resizeEvent(self,event):
        first = self.viewport().width() < 10
        super().resizeEvent(event)
        if first: self.fit()
