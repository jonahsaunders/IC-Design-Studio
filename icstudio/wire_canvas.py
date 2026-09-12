"""Manual schematic wire gestures and vector rendering for the native canvas."""
import math
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QColor,QPainterPath,QPolygonF
from . import wiring
from .ui_style import palette


class WireCanvasMixin:
    def capture_candidates(self,pos):
        filters=getattr(self,'capture_filters',{'devices','wires','labels','annotations'});out=[]
        if 'annotations' in filters:out.extend(n for n in reversed(self.cell.get('annotations',[])) if self.annotation_box(n).contains(pos))
        if 'labels' in filters:out.extend(l for l in reversed(self.cell.get('labels',[])) if self.label_box(l).contains(pos))
        devices=[]
        if 'devices' in filters:
            for d in reversed(self.cell['devices']):
                dx,dy=pos.x()-d['x'],pos.y()-d['y'];a=math.radians(-d['rotation']);x=dx*math.cos(a)-dy*math.sin(a);y=dx*math.sin(a)+dy*math.cos(a)
                if not d.get('symbol') and d['kind'] in ('R','C','L','V','I'):
                    if abs(x)<={'R':12,'C':20,'L':16,'V':24,'I':24}[d['kind']] and abs(y)<=53:devices.append(d)
                elif self.bounds(d).contains(pos):devices.append(d)
        if 'wires' in filters:
            _,_,_,_,segments,index=self.wire_spatial();limit=6/self.scale;seen=set();hits=[]
            for i in sorted(index.query((pos.x()-limit,pos.y()-limit,pos.x()+limit,pos.y()+limit)),reverse=True):
                wire,_,a,b=segments[i]
                distance=math.dist([pos.x(),pos.y()],wiring.nearest([pos.x(),pos.y()],a,b))
                if distance<=limit:hits.append((distance,-i,wire))
            for _,_,wire in sorted(hits,key=lambda row:row[:2]):
                if wire['id'] not in seen:out.append(wire);seen.add(wire['id'])
        return out+devices
    def capture_cycle(self,pos):
        rows=self.capture_candidates(pos)
        if not rows:return
        self.auto_fit=False
        ids=[o['id'] for o in rows];current=self.selection[0] if len(self.selection)==1 else None;i=(ids.index(current)+1)%len(ids) if current in ids else 0;self.selected.emit([ids[i]]);self.message.emit('Selection '+str(i+1)+'/'+str(len(ids))+' · Tab or Alt+click cycles overlaps')
    def wire_spatial(self):
        key=(self.cell.get('wires',()),self.cell['devices'],self.cell.get('junctions',()),self.cell.get('labels',()))
        if hasattr(self,'_wire_spatial_key') and all(a is b for a,b in zip(key,self._wire_spatial_key)):return self._wire_spatial_cache
        from .spatial import SpatialIndex
        from .net_labels import point as label_point
        pinlist=list(wiring.pins(self.cell).items());labels=[(l['id'],label_point(l,self.cell)) for l in key[3]];segments=[(w,i,a,b) for w in key[0] for i,(a,b) in enumerate(zip(w['points'],w['points'][1:]))]
        self._wire_spatial_key=key;self._wire_spatial_cache=(pinlist,SpatialIndex([((pt[0],pt[1],pt[0],pt[1]),i) for i,(_,pt) in enumerate(pinlist)]),labels,SpatialIndex([((pt[0],pt[1],pt[0],pt[1]),i) for i,(_,pt) in enumerate(labels)]),segments,SpatialIndex([((min(a[0],b[0])-1e-7,min(a[1],b[1])-1e-7,max(a[0],b[0])+1e-7,max(a[1],b[1])+1e-7),i) for i,(_,_,a,b) in enumerate(segments)]));return self._wire_spatial_cache
    def focusNextPrevChild(self,next):
        if self.mode=='schematic' and self.tool in ('select','connect'):return False
        return super().focusNextPrevChild(next)

    def reset_wire_gesture(self):
        self.wire_points=[];self.wire_bends=[];self.wire_horizontal=True
        self.wire_hover=None;self.wire_drag=None;self.pending_pin=None

    def wire_target(self,pos):
        """Use screen-space tolerance, and retain exact off-grid pin positions."""
        point=[pos.x(),pos.y()];limit=9/self.scale;best=None;box=(point[0]-limit,point[1]-limit,point[0]+limit,point[1]+limit);pins,pindex,labels,lindex,segments,index=self.wire_spatial()
        for i in sorted(pindex.query(box)):
            key,pt=pins[i]
            distance=math.dist(point,pt)
            if distance<=limit:best=(pt,('pin',*key));limit=distance
        if best:return best
        for i in sorted(lindex.query(box)):
            lid,pt=labels[i];distance=math.dist(point,pt)
            if distance<=limit:best=(pt,('label',lid));limit=distance
        if best:return best
        for i in sorted(index.query(box)):
            wire,segment,a,b=segments[i];pt=wiring.nearest(point,a,b);distance=math.dist(point,pt)
            if distance<=limit:
                snapped=[round(pt[0]/10)*10,round(pt[1]/10)*10];snapped=wiring.nearest(snapped,a,b);best=(snapped,('wire',wire['id'],segment));limit=distance
        return best

    def wire_tail(self,end):
        if not self.wire_points:return [end]
        a=self.wire_points[-1]
        bend=[end[0],a[1]] if self.wire_horizontal else [a[0],end[1]]
        return wiring.clean([a,bend,end])

    def wire_click(self,raw):
        self.wire_hover=self.wire_target(raw);snap=self.snap(raw)
        point=self.wire_hover[0] if self.wire_hover else [snap.x(),snap.y()]
        self.drag=QPointF(*point)
        if not self.wire_points:
            self.wire_points=[point];self.pending_pin=tuple(self.wire_hover[1][1:]) if self.wire_hover and self.wire_hover[1][0]=='pin' else None
            self.message.emit('Wire · click bends; finish on a pin/wire · Space flips bend · Enter finishes · Esc cancels')
        elif point!=self.wire_points[-1]:
            self.wire_bends.append(list(self.wire_points));self.wire_points=wiring.clean(self.wire_points+self.wire_tail(point)[1:])
            if self.wire_hover:self.finish_wire()
        self.anchor=None;self.update()

    def finish_wire(self):
        if len(self.wire_points)>1:
            points=[list(pt) for pt in self.wire_points];self.reset_wire_gesture()
            self.wire_added.emit(points)
        else:self.reset_wire_gesture()
        self.anchor=None;self.update()

    def wire_key(self,event):
        if self.mode!='schematic' or self.tool!='connect':return False
        key=event.key()
        if key in (Qt.Key_Space,Qt.Key_Tab):
            self.wire_horizontal=not self.wire_horizontal;self.update();return True
        if key==Qt.Key_Backspace:
            if self.wire_bends:self.wire_points=self.wire_bends.pop()
            else:self.reset_wire_gesture()
            self.update();return True
        if key in (Qt.Key_Return,Qt.Key_Enter):self.finish_wire();return True
        if key==Qt.Key_Escape and self.wire_points:
            self.reset_wire_gesture();self.update();self.message.emit('Wire cancelled · click to start another · Esc returns to Select');return True
        return False

    def hit_wire(self,pos):
        point=[pos.x(),pos.y()];limit=6/self.scale;best=None;_,_,_,_,segments,index=self.wire_spatial()
        for i in sorted(index.query((point[0]-limit,point[1]-limit,point[0]+limit,point[1]+limit))):
            wire,segment,a,b=segments[i];distance=math.dist(point,wiring.nearest(point,a,b))
            if distance<=limit:best=(wire,segment);limit=distance
        return best

    def wire_geometry(self):
        key=(self.cell.get('wires',()),self.cell['devices'],self.cell.get('junctions',()),self.cell.get('labels',()))
        if hasattr(self,'_wire_geometry_key') and all(a is b for a,b in zip(key,self._wire_geometry_key)):return self._wire_geometry_cache
        self._wire_geometry_key=key
        dots=wiring.junction_points(self.cell);pinlist,_,_,_,segments,index=self.wire_spatial();bridges=[];seen=set()
        for wire,_,a,b in segments:
            if a[0]!=b[0]:continue
            for i in index.query((a[0],min(a[1],b[1]),a[0],max(a[1],b[1]))):
                other,_,c,d=segments[i]
                if c[1]!=d[1]:continue
                x,y=a[0],c[1]
                if min(a[1],b[1])<y<max(a[1],b[1]) and min(c[0],d[0])<x<max(c[0],d[0]) and (x,y) not in dots and (x,y) not in seen:
                    seen.add((x,y));bridges.append((wire,x,y))
        connected={pin for pin,point in pinlist if any(wiring.on_segment(point,segments[i][2],segments[i][3]) for i in index.query((*point,*point)))}
        if self.cell.get('labels'):
            groups=wiring.graph(self.cell,labels=False);label_roots={groups[('label',l['id'])] for l in self.cell['labels']}
            connected.update(pin for pin,_ in pinlist if groups[pin] in label_roots)
        self._wire_geometry_cache=(dots,bridges,connected);return self._wire_geometry_cache

    def draw_wires(self,p):
        t=palette(self.dark);color='#91a5c2' if self.dark else '#7187a6';chosen=set(self.selection);a=self.model(QPointF(0,0));b=self.model(QPointF(self.width(),self.height()));view=(min(a.x(),b.x())-10,min(a.y(),b.y())-10,max(a.x(),b.x())+10,max(a.y(),b.y())+10);_,_,_,_,segments,index=self.wire_spatial();visible={segments[i][0]['id'] for i in index.query(view)}
        def ink(wire):return t['accent'] if wire['id'] in chosen or (self.net and wire.get('net')==self.net) else color
        wires=self.cell.get('wires',[])
        if getattr(self,'_wire_draw_source',None) is not wires:
            self._wire_draw_source=wires;base=QPainterPath();paths={}
            for wire in wires:
                points=wire['points'];path=QPainterPath(QPointF(*points[0]))
                for pt in points[1:]:path.lineTo(QPointF(*pt))
                base.addPath(path);paths[wire['id']]=path
            self._wire_draw_base=base;self._wire_draw_paths=paths
        p.setPen(self.pen(color,1.3));p.setBrush(Qt.NoBrush);p.drawPath(self._wire_draw_base)
        for wire in wires:
            selected=wire['id'] in chosen
            if wire['id'] not in visible or not (selected or self.net and wire.get('net')==self.net):continue
            p.setPen(self.pen(ink(wire),2 if selected else 1.3));p.drawPath(self._wire_draw_paths[wire['id']])
            if selected:
                for pt in wire['points']:p.drawRect(QRectF(pt[0]-3/self.scale,pt[1]-3/self.scale,6/self.scale,6/self.scale))
        dots,bridges,self._wired_pins=self.wire_geometry();p.setPen(Qt.NoPen);p.setBrush(QColor(color))
        for pt in dots:p.drawEllipse(QPointF(*pt),3,3)
        for wire,x,y in bridges:
            p.setPen(self.pen(t['canvas'],5));p.drawLine(QPointF(x,y-4),QPointF(x,y+4));p.setBrush(Qt.NoBrush);p.setPen(self.pen(ink(wire),1.3))
            path=QPainterPath(QPointF(x,y-4));path.cubicTo(x+6,y-4,x+6,y+4,x,y+4);p.drawPath(path)

    def draw_wire_preview(self,p):
        if self.mode!='schematic':return
        t=palette(self.dark)
        if self.wire_points:
            p.setBrush(Qt.NoBrush);p.setPen(self.pen(t['accent'],1.5));p.drawPolyline(QPolygonF([QPointF(*pt) for pt in self.wire_points]))
            if self.drag:
                pen=self.pen(t['accent'],1.5);pen.setStyle(Qt.DashLine);p.setPen(pen)
                p.drawPolyline(QPolygonF([QPointF(*pt) for pt in self.wire_tail([self.drag.x(),self.drag.y()])]))
            for pt in self.wire_points:p.drawRect(QRectF(pt[0]-2/self.scale,pt[1]-2/self.scale,4/self.scale,4/self.scale))
        if self.tool=='connect' and self.wire_hover:
            p.setPen(self.pen(t['accent'],1.6));p.setBrush(Qt.NoBrush);p.drawEllipse(QPointF(*self.wire_hover[0]),6/self.scale,6/self.scale)
            target=self.wire_hover[1];label=target[0].title()
            if target[0]=='pin':label=next(d['name'] for d in self.cell['devices'] if d['id']==target[1])+'.'+target[2]
            p.save();p.resetTransform();p.drawText(QPointF(*self.wire_hover[0])*self.scale+self.offset+QPointF(10,-10),label);p.restore()
