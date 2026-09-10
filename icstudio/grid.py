"""Screen-space CAD grids anchored to the document's actual placement lattice."""
import math
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainter, QPen


def visible_interval(base, scale, minimum=14):
    """Decimate by whole lattice multiples; never change the snapping interval."""
    base = max(float(base), 1e-9)
    scale = max(float(scale), 1e-12)
    decade = 1
    while True:
        for factor in (1, 2, 5):
            if base * scale * decade * factor >= minimum:
                return base * decade * factor
        decade *= 10


class GridMixin:
    def manufacturing_grid(self):
        return 10 if self.mode == 'schematic' else self.tech.get('grid', 5)

    def fixed_grid_interval(self):
        base=self.manufacturing_grid()
        requested=getattr(self,'grid_snap_step',base)
        return max(base,round(requested/base)*base)

    def grid_snap_active(self):
        frozen=getattr(self,'_drawing_grid',None)
        return frozen[0] if frozen else getattr(self,'grid_snap_enabled',True)

    def snap_interval(self):
        frozen=getattr(self,'_drawing_grid',None)
        if frozen:return frozen[1]
        if self.mode=='schematic':return 10
        if getattr(self,'grid_snap_mode','visible')=='visible':return self.grid_interval()
        return self.fixed_grid_interval()

    def grid_interval(self):
        frozen=getattr(self,'_drawing_grid',None)
        if frozen:return frozen[2]
        base=self.fixed_grid_interval() if self.mode=='layout' and getattr(self,'grid_snap_mode','visible')=='fixed' else self.manufacturing_grid()
        return visible_interval(base,self.scale,getattr(self,'grid_density',14))

    def begin_drawing_grid(self):
        if self.mode=='layout' and getattr(self,'_drawing_grid',None) is None:
            self._drawing_grid=(self.grid_snap_active(),self.snap_interval(),self.grid_interval())
            self.view_changed.emit()

    def end_drawing_grid(self):
        self._drawing_grid=None
        self.view_changed.emit()

    def paint_grid(self, painter):
        style = getattr(self, 'grid_style', 'lines')
        if style == 'off':
            return
        step = self.grid_interval() * self.scale
        # Freeze drawing coordinates through zoom, but bound rendering work
        # when a user zooms far out in the middle of a shape.
        if step<2:step*=math.ceil(2/step)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)
        minor = QColor('#35465b' if self.dark else '#dce3ec')
        major = QColor('#4d627c' if self.dark else '#b7c6d8')
        alpha = getattr(self, 'grid_contrast', 80) / 100
        minor.setAlphaF(alpha)
        major.setAlphaF(alpha)
        x0 = math.ceil(-self.offset.x() / step)
        y0 = math.ceil(-self.offset.y() / step)
        xs = [(i, self.offset.x() + i * step)
              for i in range(x0, math.floor((self.width()-self.offset.x())/step)+1)]
        ys = [(i, self.offset.y() + i * step)
              for i in range(y0, math.floor((self.height()-self.offset.y())/step)+1)]
        # Line rendering is O(viewport perimeter), independent of design size.
        for strong, color in ((False, minor), (True, major)):
            pen = QPen(color, 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            if style == 'dots':
                points = [QPointF(x, y) for i, x in xs for j, y in ys
                          if (i % getattr(self,'grid_major_every',5) == 0 and j % getattr(self,'grid_major_every',5) == 0) == strong]
                if points:
                    painter.drawPoints(points)
            else:
                for i, x in xs:
                    if (i % getattr(self,'grid_major_every',5) == 0) == strong:
                        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
                for i, y in ys:
                    if (i % getattr(self,'grid_major_every',5) == 0) == strong:
                        painter.drawLine(QPointF(0, y), QPointF(self.width(), y))
        if getattr(self, 'grid_origin', True):
            painter.setPen(QPen(QColor('#7696b4' if self.dark else '#8aa5bd'), 1))
            x, y = self.offset.x(), self.offset.y()
            if 0 <= x <= self.width():
                painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
            if 0 <= y <= self.height():
                painter.drawLine(QPointF(0, y), QPointF(self.width(), y))
        painter.restore()
