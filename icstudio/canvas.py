from __future__ import annotations
import math
from PySide6.QtCore import Qt,QPointF,QRectF,Signal
from PySide6.QtGui import QPainter,QPen,QColor,QPainterPath,QFont,QPolygonF
from PySide6.QtWidgets import QWidget
from .interchange import pin_positions
from .model import uid
from .ui_style import palette
from . import wiring
from .wire_canvas import WireCanvasMixin

from .label_canvas import LabelCanvasMixin
from .editor_canvas import EditorCanvasMixin

class Canvas(EditorCanvasMixin,LabelCanvasMixin,WireCanvasMixin,QWidget):
    editor_requested=Signal(str,dict)
    label_requested=Signal(dict)
    wire_added=Signal(list);wire_segment_moved=Signal(str,int,float,float)
    placement_requested=Signal(float,float);tool_cancelled=Signal();context_requested=Signal(object);inspect_requested=Signal();view_changed=Signal()
    selected=Signal(list);move_objects=Signal(list,float,float);connect_pins=Signal(str,str,str,str);shape_added=Signal(dict);message=Signal(str)
    via_requested=Signal(float,float);stretch_requested=Signal(str,int,int)
    def __init__(self,mode,parent=None):
        super().__init__(parent);self.mode=mode;self.cell=None;self.tech={};self.selection=[];self.net='';self.dark=False;self.tool='select';self.layer='metal1';self.line_width=200;self.scale=1.0 if mode=='schematic' else .08;self.offset=QPointF(40,50);self.anchor=None;self.drag=None;self.pan=False;self.space=False;self.pending_pin=None;self.drawing=[];self.visible_layers=set();self.setMinimumSize(250,220);self.setFocusPolicy(Qt.StrongFocus);self.setMouseTracking(True);self.setAccessibleName(mode+' design canvas');self.ruler=None;self.placement=None;self.marquee=False;self.moving=False;self._layers_initialized=False;self.press_screen=None;self.auto_fit=True;self.reset_wire_gesture()
    def set_data(self,cell,tech,selection=None,net=''):
        self.cell=cell;self.tech=tech;self.selection=list(selection or []);self.net=net;
        if self.mode=='layout' and getattr(self,'_indexed_shapes',None) is not cell['shapes']:
            from .spatial import SpatialIndex
            cache=getattr(self,'_spatial_cache',[]);cached=next((index for shapes,index in cache if shapes is cell['shapes']),None)
            self._indexed_shapes=cell['shapes'];self._spatial=cached if cached is not None else SpatialIndex([((b.left(),b.top(),b.right(),b.bottom()),i) for i,s in enumerate(cell['shapes']) for b in [self.bounds(s)]])
            self._spatial_cache=([(cell['shapes'],self._spatial)]+[(shapes,index) for shapes,index in cache if shapes is not cell['shapes']])[:2]
        if not self._layers_initialized:self.visible_layers={l['name'] for l in tech['layers']};self._layers_initialized=True
        names={l['name'] for l in tech['layers']}
        self.visible_layers.update(names-getattr(self,'_known_layers',names));self._known_layers=names
        self.update()
    def model(self,p):return QPointF((p.x()-self.offset.x())/self.scale,(p.y()-self.offset.y())/self.scale)
    def snap(self,p):
        grid=10 if self.mode=='schematic' else self.tech.get('grid',5)
        if self.mode=='layout' and self.tool=='path' and self.cell and getattr(self,'snap_to_terminals',False):
            candidates=[pin['point'] for pin in self.cell.get('layout_pins',[])]+[port['point'] for port in self.cell.get('layout_ports',[])]
            margin=8/self.scale
            for i in self._spatial.query((p.x()-margin,p.y()-margin,p.x()+margin,p.y()+margin)) if hasattr(self,'_spatial') else []:
                shape=self.cell['shapes'][i]
                if shape['layer'] in self.visible_layers and shape['layer'] not in getattr(self,'locked_layers',set()):candidates.extend(shape['points'])
            nearest=min(candidates,key=lambda pt:(pt[0]-p.x())**2+(pt[1]-p.y())**2,default=None)
            if nearest and math.hypot(nearest[0]-p.x(),nearest[1]-p.y())<=margin:return QPointF(*nearest)
        return QPointF(round(p.x()/grid)*grid,round(p.y()/grid)*grid)
    def path_preview(self,pos):
        if pos is None:return []
        if self.mode=='layout' and self.tool=='path' and getattr(self,'orthogonal',False) and self.drawing:
            last=self.drawing[-1]
            if last.x()!=pos.x() and last.y()!=pos.y():return [QPointF(pos.x(),last.y()),pos]
        return [pos]
    def points(self,s):return [QPointF(*p) for p in s['points']]
    def bounds(self,obj):
        if self.mode=='schematic':
            if obj.get('kind') in ('net_label','ground'):return self.label_box(obj)
            if 'points' in obj:
                xs,ys=zip(*obj['points']);return QRectF(min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)).adjusted(-5,-5,5,5)
            radius=65
            if obj.get('symbol'):
                points=list(obj['symbol']['pins'].values())+[pt for item in obj['symbol']['primitives'] for pt in item['points']]
                radius=max([65]+[abs(v)+12 for pt in points for v in pt])
            return QRectF(obj['x']-radius,obj['y']-radius,2*radius,2*radius)
        pts=obj['points'];xs=[p[0] for p in pts];ys=[p[1] for p in pts];w=obj.get('width',0)/2;return QRectF(min(xs)-w,min(ys)-w,max(xs)-min(xs)+2*w,max(ys)-min(ys)+2*w)
    def resizeEvent(self,event):
        if self.cell and getattr(self,"auto_fit",True):self.fit()
        elif event.oldSize().isValid():self.offset+=QPointF((event.size().width()-event.oldSize().width())/2,(event.size().height()-event.oldSize().height())/2)
        super().resizeEvent(event)
    def fit(self):
        self.auto_fit=True
        if not self.cell:return
        objects=self.cell['devices' if self.mode=='schematic' else 'shapes']+(self.cell.get('wires',[])+self.cell.get('labels',[]) if self.mode=='schematic' else []);box=None
        for o in objects:box=self.bounds(o) if box is None else box.united(self.bounds(o))
        if not box or box.isEmpty():self.scale=1 if self.mode=='schematic' else .08;self.offset=QPointF(70,70)
        else:
            box.adjust(-60 if self.mode=='schematic' else -500,-60 if self.mode=='schematic' else -500,60 if self.mode=='schematic' else 500,60 if self.mode=='schematic' else 500);self.scale=min(max(self.width(),250)/box.width(),max(self.height(),220)/box.height());self.offset=QPointF(self.width()/2-box.center().x()*self.scale,self.height()/2-box.center().y()*self.scale)
        self.update();self.view_changed.emit()
    def pen(self,color,width=1.4):
        p=QPen(QColor(color),width);p.setCosmetic(True);return p
    def paintEvent(self,event):
        t=palette(self.dark);p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.fillRect(self.rect(),QColor(t['canvas']));p.setPen(self.pen(t['grid'],1))
        step=(20 if self.mode=='schematic' else 500)*self.scale
        while step<18:step*=5
        if step<200:
            x=self.offset.x()%step
            while x<self.width():
                y=self.offset.y()%step
                while y<self.height():p.drawPoint(QPointF(x,y));y+=step
                x+=step
        if not self.cell:return
        p.translate(self.offset);p.scale(self.scale,self.scale);view=QRectF(self.model(QPointF(0,0)),self.model(QPointF(self.width(),self.height())))
        original=self.cell
        if getattr(self,'capture_preview',None) is not None:self.cell=self.capture_preview
        if self.wire_drag and self.anchor and self.drag:
            ident,index=self.wire_drag;delta=self.drag-self.anchor
            self.cell={**self.cell,'wires':[{**w,'points':wiring.segment_drag(w['points'],index,delta.x(),delta.y())} if w['id']==ident else w for w in self.cell.get('wires',[])]}
        if self.moving and self.anchor and self.drag:
            delta=self.drag-self.anchor;group='devices' if self.mode=='schematic' else 'shapes';objects=[]
            for obj in self.cell[group]:
                if obj['id'] in self.selection:
                    obj=dict(obj)
                    if self.mode=='schematic':obj['x']+=delta.x();obj['y']+=delta.y()
                    else:obj['points']=[[x+delta.x(),y+delta.y()] for x,y in obj['points']];obj['holes']=[[[x+delta.x(),y+delta.y()] for x,y in h] for h in obj.get('holes',[])]
                objects.append(obj)
            self.cell={**self.cell,group:objects}
            if self.mode=='schematic':
                from .model import clone
                self.cell=clone(self.cell);wiring.keep_connections(self.cell,wiring.pins(original))
        if self.mode=='schematic':self.draw_schematic(p,view)
        else:self.editor_background(p,view);self.draw_layout(p,view);self.editor_overlay(p)
        self.cell=original
        if self.placement and self.drag:
            p.save();p.setOpacity(.55);self.cell={**original,'wires':[],'junctions':[],'labels':[],'devices':[{**self.placement,'x':self.drag.x(),'y':self.drag.y()}]};self.draw_schematic(p,view);self.cell=original;p.restore()
        self.draw_wire_preview(p)
        self.draw_label_preview(p)
        if self.anchor and self.drag and (self.tool in ('rect','ruler') or self.marquee):
            pen=self.pen(t['accent'],1.3);p.setPen(pen);p.setBrush(Qt.NoBrush)
            if self.marquee:
                pen.setStyle(Qt.DashLine);p.setPen(pen);fill=QColor(t['accent']);fill.setAlpha(20);p.setBrush(fill)
            if self.tool=='ruler':p.drawLine(self.anchor,self.drag)
            else:p.drawRect(QRectF(self.anchor,self.drag).normalized())
        if self.drawing:
            p.setPen(self.pen(t['accent'],1.6));p.setBrush(Qt.NoBrush);p.drawPolyline(QPolygonF(self.drawing+self.path_preview(self.drag)))
            for pt in self.drawing:p.drawEllipse(pt,3/self.scale,3/self.scale)
        if self.ruler:
            a,b=self.ruler;p.setPen(self.pen(t['accent'],1.5));p.drawLine(a,b)
            length=math.hypot(b.x()-a.x(),b.y()-a.y())/(1000 if self.mode=='layout' else 1);p.save();p.translate((a+b)/2);p.scale(1/self.scale,1/self.scale);p.setFont(QFont('DejaVu Sans',10));p.drawText(QPointF(5,-8),f'{length:.4g} '+('µm' if self.mode=='layout' else 'units'));p.restore()
        p.resetTransform()
        if not self.cell['devices' if self.mode=='schematic' else 'shapes'] and not self.placement and not (self.mode=='schematic' and self.cell.get('wires')):
            p.setPen(QColor(t['text']));p.setFont(QFont('DejaVu Sans',17,QFont.DemiBold));r=QRectF(self.rect());r.setHeight(r.height()-28);p.drawText(r,Qt.AlignCenter,'Build your circuit' if self.mode=='schematic' else 'Start your layout');p.setFont(QFont('DejaVu Sans',10));p.setPen(QColor(t['muted']));r=QRectF(self.rect());r.translate(0,22);p.drawText(r,Qt.AlignCenter,'Choose Place to add a component.' if self.mode=='schematic' else 'Choose a layer, then draw a rectangle, polygon, or path.')
    def draw_schematic(self,p,view):
        self.draw_wires(p)
        self.draw_labels(p)
        for d in self.cell['devices']:
            if not view.intersects(self.bounds(d)):continue
            selected=d['id'] in self.selection;fg=palette(self.dark)['accent'] if selected else ('#dee6f3' if self.dark else '#334259');p.save();p.translate(d['x'],d['y']);p.rotate(d['rotation']);p.scale(-1 if d.get('mirror') else 1,1);p.setPen(self.pen(fg,2));p.setBrush(QColor(palette(self.dark)['tint']) if selected else QColor(palette(self.dark)['canvas']))
            kind=d['kind']
            if selected:
                p.setPen(self.pen(palette(self.dark)['accent'],1))
                if kind in ('R','C','L','V','I'):
                    half_width={'R':16,'C':24,'L':20,'V':28,'I':28}[kind]
                    fill=QColor(palette(self.dark)['accent']);fill.setAlpha(12);p.setBrush(fill)
                    p.drawRoundedRect(QRectF(-half_width,-58,2*half_width,116),4,4)
                    p.setBrush(QColor(palette(self.dark)['canvas']))
                else:p.drawRoundedRect(QRectF(-62,-62,124,124),4,4)
                p.setPen(self.pen(fg,1.8))
            if d.get('symbol'):
                from .symbol_editor import draw_symbol
                draw_symbol(p,d['symbol'],fg,{'name':d['name'],'value':d['value'],'symname':d.get('cell',''),**d.get('params',{}),**d.get('parameters',{}),**d.get('symbol_context',{})})
            elif kind in ('R','C','V'):
                pen=self.pen(fg,1.5);pen.setCapStyle(Qt.RoundCap);pen.setJoinStyle(Qt.RoundJoin);p.setPen(pen)
                # Keep the electrical terminals at +/-50; only the ink changes.
                body_end={'R':24,'C':5,'V':20}[kind]
                p.drawLine(QPointF(0,-50),QPointF(0,-body_end));p.drawLine(QPointF(0,body_end),QPointF(0,50))
                if kind=='R':
                    p.setBrush(Qt.NoBrush)
                    p.drawPolyline(QPolygonF([QPointF(x,y) for x,y in [(0,-24),(7,-20),(-7,-12),(7,-4),(-7,4),(7,12),(-7,20),(0,24)]]))
                elif kind=='C':
                    p.drawLine(-16,-5,16,-5);p.drawLine(-16,5,16,5)
                else:
                    p.drawEllipse(QRectF(-20,-20,40,40));p.drawLine(-4,-7,4,-7);p.drawLine(0,-11,0,-3);p.drawLine(-4,8,4,8)
            elif kind in ('L','I'):
                pen=self.pen(fg,1.5);pen.setCapStyle(Qt.RoundCap);pen.setJoinStyle(Qt.RoundJoin);p.setPen(pen);end=24 if kind=='L' else 20
                p.drawLine(QPointF(0,-50),QPointF(0,-end));p.drawLine(QPointF(0,end),QPointF(0,50))
                if kind=='L':
                    p.setBrush(Qt.NoBrush);path=QPainterPath(QPointF(0,-24))
                    for y in (-24,-12,0,12):path.cubicTo(12,y,12,y+12,0,y+12)
                    p.drawPath(path)
                else:
                    p.drawEllipse(QRectF(-20,-20,40,40));p.drawLine(0,-10,0,10);p.setBrush(QColor(fg));p.drawPolygon(QPolygonF([QPointF(0,10),QPointF(-4,3),QPointF(4,3)]))
            elif kind in ('NMOS','PMOS'):
                p.drawLine(-50,0,-12,0);p.drawLine(-12,-27,-12,27);p.drawLine(-2,-25,-2,25);p.drawLine(-2,-25,20,-25);p.drawLine(20,-25,20,-50);p.drawLine(-2,25,20,25);p.drawLine(20,25,20,50);p.drawLine(2,0,50,0)
                if kind=='PMOS':p.drawEllipse(QRectF(-23,-5,10,10))
                else:p.drawLine(10,0,18,-5);p.drawLine(10,0,18,5)
            elif d.get('symbol'):
                from .symbol_editor import draw_symbol
                draw_symbol(p,d['symbol'],fg,{'name':d['name'],'value':d['value'],'symname':d.get('cell',''),**d.get('params',{}),**d.get('parameters',{}),**d.get('symbol_context',{})})
            else:
                p.drawRect(QRectF(-40,-50,80,max(100,len(d['nets'])*20)));p.drawText(QRectF(-35,-15,70,30),Qt.AlignCenter,'CELL')
                pos=pin_positions({**d,'x':0,'y':0,'rotation':0,'mirror':False})
                for pin,(x,y) in pos.items():p.drawLine(x,y,-40 if x<0 else 40,y)
            p.restore();p.setPen(QColor(fg));p.setFont(QFont('Sans Serif',11));p.drawText(QPointF(d['x']-20 if d['rotation'] in (90,270) else d['x']+37,d['y']-55 if d['rotation'] in (90,270) else d['y']-30),d['name']);p.setFont(QFont('Sans Serif',9));p.setPen(QColor(palette(self.dark)['muted']));p.drawText(QPointF(d['x']-20 if d['rotation'] in (90,270) else d['x']+37,d['y']-39 if d['rotation'] in (90,270) else d['y']-12),d.get('model_ref',{}).get('device','').split('/')[-1].replace('.sym','') if kind=='PDK' else d['value'] if kind not in ('NMOS','PMOS','X') else (d['params']['w']+' / '+d['params']['l'] if kind!='X' else 'hierarchy'))
            for pin,(x,y) in pin_positions(d).items():
                name=d.get('net_labels',d['nets'] if 'wires' not in self.cell else {}).get(pin,'')
                p.setFont(QFont('Sans Serif',8))
                if name:p.drawText(QPointF(x+5,y-7),name)
                connected=(d['id'],pin) in self._wired_pins or bool(name)
                if self.net and d['nets'].get(pin)==self.net:p.setPen(self.pen(palette(self.dark)['accent'],2.5));p.setBrush(Qt.NoBrush);p.drawEllipse(QPointF(x,y),6,6)
                p.setPen(self.pen(fg,1));p.setBrush(QColor(fg) if connected else QColor(palette(self.dark)['canvas']));p.drawEllipse(QPointF(x,y),2.2,2.2)
        p.setPen(QColor(palette(self.dark)['muted']));p.setFont(QFont('Sans Serif',10))
        for note in self.cell.get('annotations',[]):
            p.drawText(QRectF(note['x'],note['y'],320,150),Qt.TextWordWrap,note['text'])
        for i,bus in enumerate(self.cell.get('buses',[])):
            p.drawText(QPointF(20,25+20*i),'Bus '+bus['name'])
    def path(self,s):
        pts=self.points(s);path=QPainterPath(pts[0])
        if s['kind']=='rect':path.addRect(QRectF(pts[0],pts[1]).normalized())
        else:
            for pt in pts[1:]:path.lineTo(pt)
            if s['kind']=='polygon':path.closeSubpath()
        for hole in s.get('holes',[]):
            path.moveTo(*hole[0])
            for pt in hole[1:]:path.lineTo(*pt)
            path.closeSubpath()
        return path
    def layout_drawing_cache(self):
        shapes=self.cell['shapes'];cache=getattr(self,'_drawing_cache',[])
        found=next((entry for entry in cache if entry[0] is shapes),None)
        if found is None:found=(shapes,[self.bounds(s) for s in shapes],[self.path(s) for s in shapes])
        self._drawing_cache=([found]+[entry for entry in cache if entry[0] is not shapes])[:2]
        return found[1:]
    def draw_layout(self,p,view):
        colors={l['name']:getattr(self,'layer_styles',{}).get(l['name'],{}).get('color',l['color']) for l in self.tech['layers']}
        boxes,paths=self.layout_drawing_cache();selection=set(self.selection);inks={};theme=palette(self.dark)
        candidates=sorted(self._spatial.query((view.left(),view.top(),view.right(),view.bottom()))) if hasattr(self,'_spatial') and not self.moving else range(len(self.cell['shapes']))
        for i in candidates:
            s=self.cell['shapes'][i]
            if s['layer'] not in self.visible_layers or not view.intersects(boxes[i]):continue
            selected=s['id'] in selection or s.get('device_id') in selection or bool(self.net and s.get('net')==self.net);key=(s['layer'],selected,s['kind']=='path',s.get('width',0))
            if key not in inks:
                col=QColor(colors[s['layer']]);fill=QColor(col);fill.setAlpha(105 if selected else 65);pen=self.pen('#f6faff' if selected and self.dark else theme['accent'] if selected else col,2.3 if selected else 1)
                if s['kind']=='path':pen.setCosmetic(False);pen.setWidthF(s['width']);pen.setCapStyle(Qt.SquareCap);pen.setJoinStyle(Qt.MiterJoin);pen.setColor(fill);brush=Qt.NoBrush
                else:brush=self.editor_brush(s['layer'],fill)
                inks[key]=(pen,brush,col)
            pen,brush,col=inks[key];p.setPen(pen);p.setBrush(brush);p.drawPath(paths[i])
            if s.get('net') and self.cell.get('layout_label_mode')!='explicit' and boxes[i].width()*self.scale>35:
                p.save();p.translate(*s['points'][0]);p.scale(1/self.scale,1/self.scale);p.setPen(col);p.setFont(QFont('Sans Serif',9));p.drawText(5,15,s['net']);p.restore()
        for guide in getattr(self,'connection_guides',[]):
            pen=self.pen('#f0bd72',1.5);pen.setStyle(Qt.DashLine);p.setPen(pen);p.drawLine(QPointF(*guide['start']),QPointF(*guide['end']))
        if getattr(self,'finding_box',None):
            raw=self.finding_box;p.setPen(self.pen('#ef6767',2.5));p.setBrush(Qt.NoBrush);p.drawRect(QRectF(QPointF(*raw[:2]),QPointF(*raw[2:])).normalized())
        if getattr(self,'_stretch',None) and self.anchor and self.drag:
            sid,segment,axis=self._stretch;s=next((s for s in self.cell['shapes'] if s['id']==sid),None)
            if s:
                pts=[list(pt) for pt in s['points']];delta=self.drag.y()-self.anchor.y() if axis==1 else self.drag.x()-self.anchor.x()
                for pt in pts[segment:segment+2]:pt[axis]+=delta
                pen=self.pen('#f0bd72',2);pen.setStyle(Qt.DashLine);p.setPen(pen);p.setBrush(Qt.NoBrush);p.drawPath(self.path({**s,'points':pts}))
        for text in self.cell.get('layout_texts',[]):
            if text['layer'] not in self.visible_layers:continue
            p.save();p.translate(text['x'],text['y']);p.scale(1/self.scale,1/self.scale);p.setPen(QColor(colors[text['layer']]));p.setFont(QFont('Sans Serif',9));p.drawText(QPointF(0,0),text['text']);p.restore()
        for pin in self.cell.get('layout_pins',[]):
            p.save();p.translate(*pin['point']);p.scale(1/self.scale,1/self.scale);p.setPen(self.pen(palette(self.dark)['accent'],1.3));p.setBrush(Qt.NoBrush);p.drawRect(QRectF(-3,-3,6,6));p.setFont(QFont('Sans Serif',8));d=next((d for d in self.cell['devices'] if d['id']==pin['device_id']),None);
            if self.scale>=.08 or pin['device_id'] in self.selection:p.drawText(QPointF(6,-5),(d['name'] if d else '?')+'.'+pin['pin'])
            p.restore()
    def hit(self,pos):
        if not self.cell:return None
        if self.mode=='layout':return self.editor_hit(pos)
        if self.mode=='schematic':
            rows=self.capture_candidates(pos);return rows[0] if rows else None
    def cancel_gesture(self):
        self.reference_point=None;self.vertex_pick=None
        self._stretch=None
        self.label_placement=None;self.reset_wire_gesture();self.drawing=[];self.pending_pin=None;self.anchor=None;self.drag=None;self.pan=False;self.marquee=False;self.moving=False;self.press_screen=None;self.update()
    def mousePressEvent(self,e):
        if self.editor_press(e):return
        self.setFocus();pos=self.snap(self.model(e.position()));self.drag=pos;self.press_screen=e.position()
        if e.button()==Qt.MiddleButton or (self.space and e.button()==Qt.LeftButton):self.pan=True;self.auto_fit=False;self.anchor=e.position();self.setCursor(Qt.ClosedHandCursor);return
        if e.button()==Qt.RightButton:
            if self.tool!='select':self.cancel_gesture();self.tool_cancelled.emit();return
            hit=self.hit(pos)
            if hit and hit['id'] not in self.selection:self.selected.emit([hit['id']])
            elif not hit:self.selected.emit([])
            self.anchor=None;self.context_requested.emit(e.position().toPoint());return
        if e.button()!=Qt.LeftButton:return
        if self.tool=='label':self.label_requested.emit(self.label_target(self.model(e.position())));return
        if self.tool=='place' and self.placement:self.placement_requested.emit(pos.x(),pos.y());return
        if self.tool=='via' and self.mode=='layout':self.via_requested.emit(pos.x(),pos.y());return
        self.anchor=pos
        if self.tool=='stretch' and self.mode=='layout':
            candidates=[]
            for s in self.cell['shapes']:
                if s['id'] not in self.selection or s['kind']!='path' or s['layer'] in getattr(self,'locked_layers',set()):continue
                for i,(a,b) in enumerate(zip(s['points'],s['points'][1:])):
                    if a==b or (a[0]!=b[0] and a[1]!=b[1]):continue
                    dx,dy=b[0]-a[0],b[1]-a[1];t=max(0,min(1,((pos.x()-a[0])*dx+(pos.y()-a[1])*dy)/(dx*dx+dy*dy)))
                    distance=math.hypot(pos.x()-a[0]-t*dx,pos.y()-a[1]-t*dy)
                    candidates.append((distance,s['id'],i,1 if dy==0 else 0))
            nearest=min(candidates,default=None)
            self._stretch=nearest[1:] if nearest and nearest[0]*self.scale<=10 else None
            if not self._stretch:self.anchor=None;self.message.emit('Click a segment of the selected Manhattan path.')
            return
        if self.tool=='connect' and self.mode=='schematic':self.wire_click(self.model(e.position()));return
        if self.tool in ('polygon','path') and self.mode=='layout':
            for point in self.path_preview(pos):
                if not self.drawing or self.drawing[-1]!=point:self.drawing.append(point)
            self.update();return
        if self.tool in ('rect','ruler'):return
        hit=self.hit(self.model(e.position()));self.moving=bool(hit) and not hit.get('editor_kind');self.marquee=not hit
        if hit and 'points' in hit and self.mode=='schematic':
            target=self.hit_wire(self.model(e.position()));self.wire_drag=(hit['id'],target[1]);self.moving=False
        if hit:
            selected=list(self.selection)
            if e.modifiers()&(Qt.ControlModifier|Qt.ShiftModifier):
                if hit['id'] in selected:selected.remove(hit['id'])
                else:selected.append(hit['id'])
            elif hit['id'] not in selected:selected=[hit['id']]
            self.selected.emit(selected)
        elif not e.modifiers()&(Qt.ControlModifier|Qt.ShiftModifier):self.selected.emit([])
    def mouseMoveEvent(self,e):
        self.editor_pointer=self.model(e.position())
        pos=self.snap(self.model(e.position()));self.drag=pos
        if self.tool=='label':self.label_raw=self.model(e.position());self.update()
        if self.pan and self.anchor:self.offset+=e.position()-self.anchor;self.anchor=e.position();self.update();self.view_changed.emit();return
        if self.tool=='connect' and self.mode=='schematic':
            self.wire_hover=self.wire_target(self.model(e.position()))
            if self.wire_hover:self.drag=QPointF(*self.wire_hover[0])
            self.update()
        if self.anchor or self.drawing or self.placement or self.pending_pin or self.tool=='instance_place' or getattr(self,'reference_point',None) is not None:self.update()
        if self.mode=='layout':self.message.emit(f'X {pos.x()/1000:.3f} µm   Y {pos.y()/1000:.3f} µm')
    def mouseReleaseEvent(self,e):
        if self.editor_release(e):return
        if self.pan:self.pan=False;self.anchor=None;self.unsetCursor();return
        if not self.anchor:return
        end=self.snap(self.model(e.position()));start=self.anchor;distance=(e.position()-self.press_screen).manhattanLength() if self.press_screen else 0
        if self.tool=='stretch' and getattr(self,'_stretch',None):
            sid,segment,axis=self._stretch;delta=end.y()-start.y() if axis==1 else end.x()-start.x()
            self._stretch=None
            if delta:self.stretch_requested.emit(sid,segment,round(delta))
        elif self.wire_drag and distance>4:
            ident,index=self.wire_drag;self.wire_segment_moved.emit(ident,index,end.x()-start.x(),end.y()-start.y())
        elif self.tool=='rect' and self.mode=='layout' and (end-start).manhattanLength()>0:
            r=QRectF(start,end).normalized()
            if r.width()>0 and r.height()>0:self.shape_added.emit({'id':uid(),'kind':'rect','layer':self.layer,'points':[[int(r.left()),int(r.top())],[int(r.right()),int(r.bottom())]],'net':'','device_id':''})
        elif self.tool=='ruler':
            self.ruler=(start,end);self.message.emit(f'Distance: {math.hypot(end.x()-start.x(),end.y()-start.y())/(1000 if self.mode=="layout" else 1):.4f} '+('µm' if self.mode=='layout' else 'units'))
        elif self.tool=='select' and self.marquee and distance>4:
            rect=QRectF(start,end).normalized();ids=[o['id'] for o in self.cell['devices' if self.mode=='schematic' else 'shapes']+(self.cell.get('wires',[])+self.cell.get('labels',[]) if self.mode=='schematic' else []) if (self.mode!='layout' or (o['layer'] in self.visible_layers and o['layer'] not in getattr(self,'locked_layers',set()))) and rect.intersects(self.bounds(o))]
            if self.mode=='layout':ids=self.editor_marquee(rect)
            else:
                filters=getattr(self,'capture_filters',{'devices','wires','labels'});allowed={o['id'] for group in filters for o in self.cell.get(group,[])};ids=[ident for ident in ids if ident in allowed]
            if e.modifiers()&(Qt.ControlModifier|Qt.ShiftModifier):ids=list(dict.fromkeys(self.selection+ids))
            self.selected.emit(ids)
        elif self.tool=='select' and self.moving and self.selection and distance>4 and (end-start).manhattanLength()>0:self.move_objects.emit(self.selection,end.x()-start.x(),end.y()-start.y())
        self.anchor=None;self.wire_drag=None;self.moving=False;self.marquee=False;self.update()
    def finish_drawing(self):
        if len(self.drawing)>=(3 if self.tool=='polygon' else 2):self.shape_added.emit({'id':uid(),'kind':self.tool,'layer':self.layer,'points':[[int(p.x()),int(p.y())] for p in self.drawing],'width':self.line_width,'net':'','device_id':''})
        self.drawing=[];self.anchor=None;self.update()
    def mouseDoubleClickEvent(self,e):
        if self.tool=='connect':self.finish_wire();return
        if self.tool in ('polygon','path'):
            if len(self.drawing)>1 and self.drawing[-1]==self.drawing[-2]:self.drawing.pop()
            self.finish_drawing()
        elif self.tool=='select':
            hit=self.hit(self.model(e.position()))
            if hit:self.selected.emit([hit['id']]);self.inspect_requested.emit()
            self.anchor=None;self.moving=False
    def wheelEvent(self,e):
        old=self.model(e.position());delta=e.angleDelta().y()
        if not delta and not e.pixelDelta().isNull():delta=e.pixelDelta().y()
        if not delta:return
        self.auto_fit=False
        self.scale=max(.0001,min(20,self.scale*(1.18 if delta>0 else 1/1.18)));self.offset=e.position()-old*self.scale;self.update();self.view_changed.emit()
    def keyPressEvent(self,e):
        if self.mode=='layout' and e.key()==Qt.Key_Tab:self.editor_cycle();return
        if self.wire_key(e):return
        if e.key()==Qt.Key_Space:self.space=True;self.setCursor(Qt.OpenHandCursor)
        elif e.key()==Qt.Key_Escape:self.cancel_gesture();self.placement=None;self.tool='select';self.tool_cancelled.emit()
        elif e.key() in (Qt.Key_Return,Qt.Key_Enter) and self.tool in ('polygon','path'):self.finish_drawing()
        elif e.key() in (Qt.Key_Return,Qt.Key_Enter) and self.selection:self.inspect_requested.emit()
        elif e.key()==Qt.Key_F:self.fit()
        elif e.key() in (Qt.Key_Left,Qt.Key_Right,Qt.Key_Up,Qt.Key_Down) and self.selection:
            step=(10 if self.mode=='schematic' else self.tech.get('grid',5))*(10 if e.modifiers()&Qt.ShiftModifier else 1);dx=step if e.key()==Qt.Key_Right else -step if e.key()==Qt.Key_Left else 0;dy=step if e.key()==Qt.Key_Down else -step if e.key()==Qt.Key_Up else 0;self.move_objects.emit(self.selection,dx,dy)
        else:super().keyPressEvent(e)
    def keyReleaseEvent(self,e):
        if e.key()==Qt.Key_Space:self.space=False;self.unsetCursor()
    def focusOutEvent(self,e):
        self.space=False;self.pan=False;self.unsetCursor();super().focusOutEvent(e)
