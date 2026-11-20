"""Compact native label and ground rendering and placement gestures."""
import math
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QColor,QFont,QFontMetricsF,QTransform
from . import net_labels
from .ui_style import palette

class LabelCanvasMixin:
    def example_supply(self, label):
        if (not self.cell.get('example_drawing') or label['kind']!='net_label'
                or label['name'].casefold() not in ('vdd','vcc','vpwr')
                or label['rotation'] or label['anchor']['kind']!='pin'
                or label['offset'] not in ([8,-12],[8,-30])):
            return False
        device=next((d for d in self.cell['devices'] if d['id']==label['anchor']['id']),None)
        return device is not None and net_labels.point(label,self.cell)[1]<device['y']

    def label_box(self,label):
        x,y=net_labels.point(label,self.cell);dx,dy=label['offset']
        if self.example_supply(label) and not (self.moving and label['id'] in self.selection):
            text=QFontMetricsF(QFont('Sans Serif',10)).boundingRect(label['name'])
            return text.translated(x-text.center().x(),y-22).united(QRectF(x-12,y-16,24,16)).adjusted(-3,-3,3,3)
        if self.moving and self.anchor and self.drag and label['id'] in self.selection:dx+=self.drag.x()-self.anchor.x();dy+=self.drag.y()-self.anchor.y()
        box=QRectF(-14,-5,28,33) if label['kind']=='ground' else QFontMetricsF(QFont('Sans Serif',10)).boundingRect(label['name']).adjusted(-4,-4,5,4)
        t=QTransform();t.translate(x+dx,y+dy);t.rotate(label['rotation']);return t.mapRect(box)

    def label_target(self,raw):
        target=self.wire_target(raw)
        if target:
            pt,key=target
            if key[0]=='pin':return {'kind':'pin','id':key[1],'pin':key[2]}
            if key[0]=='label':
                from .model import clone
                return clone(next(l['anchor'] for l in self.cell['labels'] if l['id']==key[1]))
            if key[0]=='wire':return {'kind':'wire','id':key[1],'point':list(pt)}
        pt=self.snap(raw);return {'kind':'point','point':[pt.x(),pt.y()]}

    def draw_labels(self,p,ghost=None):
        labels=[ghost] if ghost else self.cell.get('labels',[]);t=palette(self.dark)
        for l in labels:
            x,y=net_labels.point(l,self.cell);dx,dy=l['offset'];selected=l['id'] in self.selection
            if self.moving and self.anchor and self.drag and selected:dx+=self.drag.x()-self.anchor.x();dy+=self.drag.y()-self.anchor.y()
            ink=t['accent'] if selected or self.net==l['name'] or ghost else '#b7c9e6' if self.dark else '#395779'
            p.save();p.setPen(self.pen(ink,1.3));p.setBrush(Qt.NoBrush)
            if self.example_supply(l) and not (self.moving and selected):
                p.drawLine(QPointF(x,y),QPointF(x,y-14))
                p.drawLine(QPointF(x-11,y-14),QPointF(x+11,y-14))
                p.setFont(QFont('Sans Serif',10))
                center=p.fontMetrics().boundingRect(l['name']).center().x()
                p.drawText(QPointF(x-center,y-22),l['name'])
                p.restore()
                if selected:
                    p.save();p.setPen(self.pen(t['accent'],.7));p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(self.label_box(l),3,3);p.restore()
                continue
            # Close labels read beside the conductor. Longer offsets and
            # active editing retain a leader to the precise attachment.
            if (dx or dy) and (ghost or selected or abs(dx)>45 or abs(dy)>40):
                pen=self.pen(t['muted'],.8);pen.setStyle(Qt.DotLine);p.setPen(pen);p.drawLine(QPointF(x,y),QPointF(x+dx,y+dy));p.setPen(self.pen(ink,1.3))
            if selected or ghost:p.drawEllipse(QPointF(x,y),2.5,2.5)
            p.translate(x+dx,y+dy);p.rotate(l['rotation'])
            if l['kind']=='ground':
                p.drawLine(0,0,0,12)
                for half,yy in ((12,12),(8,18),(3,24)):p.drawLine(-half,yy,half,yy)
            else:p.setFont(QFont('Sans Serif',10));p.drawText(QPointF(0,0),l['name'])
            p.restore()
            if selected:
                p.setPen(self.pen(t['accent'],.7));p.setBrush(Qt.NoBrush);p.drawRoundedRect(self.label_box(l),3,3)

    def draw_label_preview(self,p):
        if not getattr(self,'label_placement',None) or self.drag is None:return
        spec=self.label_placement;raw=getattr(self,'label_raw',self.drag);a=self.label_target(raw)
        self.draw_labels(p,{'id':'preview','kind':spec['kind'],'name':spec['name'],'anchor':a,'offset':[0,0] if spec['kind']=='ground' else [10,-12],'rotation':spec.get('rotation',0)})
