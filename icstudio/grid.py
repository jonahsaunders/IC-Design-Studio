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
    def snap_interval(self):
        return 10 if self.mode == 'schematic' else self.tech.get('grid', 5)

    def grid_interval(self):
        return visible_interval(self.snap_interval(), self.scale,
                                getattr(self, 'grid_density', 14))

    def paint_grid(self, painter):
        style = getattr(self, 'grid_style', 'lines')
        if style == 'off':
            return
        step = self.grid_interval() * self.scale
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
                          if (i % 5 == 0 and j % 5 == 0) == strong]
                if points:
                    painter.drawPoints(points)
            else:
                for i, x in xs:
                    if (i % 5 == 0) == strong:
                        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
                for i, y in ys:
                    if (i % 5 == 0) == strong:
                        painter.drawLine(QPointF(0, y), QPointF(self.width(), y))
        if getattr(self, 'grid_origin', True):
            painter.setPen(QPen(QColor('#7696b4' if self.dark else '#8aa5bd'), 1))
            x, y = self.offset.x(), self.offset.y()
            if 0 <= x <= self.width():
                painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
            if 0 <= y <= self.height():
                painter.drawLine(QPointF(0, y), QPointF(self.width(), y))
        painter.restore()
