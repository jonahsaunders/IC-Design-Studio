"""Reversible drawing drafts and explicit completion for the layout canvas."""
from PySide6.QtCore import QPointF,Qt
from PySide6.QtGui import QColor,QPen,QPolygonF
from .model import uid
from .ui_style import palette


class DrawingCanvasMixin:
    def drawing_changed(self,notice=''):
        self.drawing_notice=notice
        self.draft_changed.emit()
        self.update()

    def append_drawing_point(self,point):
        before=len(self.drawing)
        for pt in self.path_preview(point):
            if not self.drawing or self.drawing[-1]!=pt:self.drawing.append(QPointF(pt))
        if len(self.drawing)!=before:
            self._drawing_undo.append(before)
            self.drawing_changed()

    def undo_drawing_point(self):
        self.setFocus()
        if self._drawing_undo:del self.drawing[self._drawing_undo.pop():]
        elif self.drawing:self.drawing.pop()
        if not self.drawing:self.end_drawing_grid()
        self.drawing_changed('Last point removed.' if self.drawing else 'Click the start point.')

    def flip_path_bend(self):
        self.setFocus()
        self.path_horizontal=not self.path_horizontal
        self.drawing_changed()

    def publish_drawing(self,shape):
        callback=getattr(self,'commit_shape_callback',None)
        if callback:
            accepted=callback(shape)
        else:
            gate=getattr(self,'can_commit_shape',None)
            accepted=not gate or gate(shape)
            if accepted:self.shape_added.emit(shape)
        if not accepted:
            self.drawing_changed(getattr(self,'drawing_error','') or 'Cannot place this shape. Check the layer, width and routing rules; the draft is still here.')
        return accepted

    def finish_drawing(self,include_cursor=False):
        if self.mode!='layout' or self.tool not in ('path','polygon'):return False
        points=list(self.drawing)
        if include_cursor and self.tool=='path' and points and self.drag is not None:
            for point in self.path_preview(self.drag):
                if points[-1]!=point:points.append(QPointF(point))
        required=3 if self.tool=='polygon' else 2
        if len(points)<required:
            self.drawing_changed('Click '+('an endpoint' if self.tool=='path' else 'at least three vertices')+' before finishing. Escape cancels.')
            return False
        shape={'id':uid(),'kind':self.tool,'layer':self.layer,'points':[[round(p.x()),round(p.y())] for p in points],
               'width':self.line_width,'net':'','device_id':''}
        if not self.publish_drawing(shape):return False
        self.drawing=[];self._drawing_undo=[];self.anchor=None;self.end_drawing_grid()
        self.drawing_changed('Path created. Click to start another.' if self.tool=='path' else 'Polygon created. Click to start another.')
        return True

    def paint_drawing_preview(self,p):
        if not self.drawing:return
        color=QColor(palette(self.dark)['accent'])
        tail=self.path_preview(self.drag)
        if self.tool=='path':
            # The filled stroke is the actual width/caps/joins of the path.
            # Fixed points are stronger; the unplaced pointer segment is faint.
            for points,alpha in ((self.drawing,125),([self.drawing[-1]]+tail,65)):
                if len(points)<2:continue
                ink=QColor(color);ink.setAlpha(alpha);pen=QPen(ink,self.line_width)
                pen.setCapStyle(Qt.SquareCap);pen.setJoinStyle(Qt.MiterJoin)
                p.setPen(pen);p.setBrush(Qt.NoBrush);p.drawPolyline(QPolygonF(points))
            p.setPen(self.pen(color,1.2));p.drawPolyline(QPolygonF(self.drawing))
            pen=self.pen(color,1.2);pen.setStyle(Qt.DashLine);p.setPen(pen)
            p.drawPolyline(QPolygonF([self.drawing[-1]]+tail))
        else:
            p.setPen(self.pen(color,1.6));p.setBrush(Qt.NoBrush);p.drawPolyline(QPolygonF(self.drawing+tail))
        p.setPen(self.pen(color,1.4));p.setBrush(Qt.NoBrush)
        for pt in self.drawing:p.drawEllipse(pt,3/self.scale,3/self.scale)
