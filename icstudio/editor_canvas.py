"""Canvas interaction helpers shared by the native layout command workspace."""
import math
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QColor,QPen,QBrush,QPainterPathStroker


class EditorCanvasMixin:
    def editor_allowed(self,layer):
        return layer in self.visible_layers and layer not in getattr(self,'unselectable_layers',set()) and layer not in getattr(self,'locked_layers',set())

    def editor_candidates(self,pos):
        if not self.cell:return []
        filters=getattr(self,'selection_types',{'shapes','instances'});out=[];seen=set();margin=6/self.scale
        indexes=sorted(self._spatial.query((pos.x()-margin,pos.y()-margin,pos.x()+margin,pos.y()+margin)),reverse=True)
        if 'pins' in filters:
            for pin in self.cell.get('layout_pins',[]):
                if self.editor_allowed(pin['layer']) and math.hypot(pos.x()-pin['point'][0],pos.y()-pin['point'][1])<=margin:
                    out.append({'id':'pin:'+pin['id'],'editor_kind':'pin','pin':pin})
        if 'labels' in filters:
            for i,t in enumerate(self.cell.get('layout_texts',[])):
                box=QRectF(t['x'],t['y']-12/self.scale,max(10,len(t['text'])*7)/self.scale,16/self.scale)
                if self.editor_allowed(t['layer']) and box.contains(pos):out.append({'id':'text:'+str(i),'editor_kind':'label','text':t})
        _,paths=self.layout_drawing_cache()
        scene=self.cell.get('_layout_scene')
        rows=[(s,None) for s in reversed(scene.query((pos.x()-margin,pos.y()-margin,pos.x()+margin,pos.y()+margin),cache=False))] if scene is not None else [(self.cell['shapes'][i],paths[i]) for i in indexes]
        for s,path in rows:
            kind='instances' if s.get('source_id') else 'shapes'
            if kind not in filters or not self.editor_allowed(s['layer']) or s['id'] in seen:continue
            if path is None:path=self.path(s)
            elif scene is None:path=path.get()
            if s['kind']=='path':
                stroker=QPainterPathStroker();stroker.setWidth(s['width']+2*margin);inside=stroker.createStroke(path).contains(pos)
            else:inside=path.contains(pos) or path.intersects(QRectF(pos.x()-margin,pos.y()-margin,2*margin,2*margin))
            if inside:out.append(s);seen.add(s['id'])
        return out

    def editor_hit(self,pos):
        candidates=self.editor_candidates(pos);return candidates[0] if candidates else None

    def editor_cycle(self):
        pos=getattr(self,'editor_pointer',None)
        if pos is None:return
        candidates=self.editor_candidates(pos)
        if not candidates:return
        ids=[s['id'] for s in candidates];current=self.selection[0] if len(self.selection)==1 else None
        index=(ids.index(current)+1)%len(ids) if current in ids else 0
        self.selected.emit([ids[index]]);self.message.emit(f'Selection {index+1}/{len(ids)} · Tab or Alt+click cycles overlaps')

    def editor_marquee(self,rect):
        ids=[];filters=getattr(self,'selection_types',{'shapes','instances'});inside=getattr(self,'box_mode','Crossing')=='Inside';boxes={};eligible=set()
        scene=self.cell.get('_layout_scene')
        shapes=scene.query((rect.left(),rect.top(),rect.right(),rect.bottom()),cache=False) if scene is not None else self.cell['shapes']
        for s in shapes:
            if ('instances' if s.get('source_id') else 'shapes') not in filters:continue
            box=self.bounds(s)
            boxes[s['id']]=boxes[s['id']].united(box) if s['id'] in boxes else box
            if self.editor_allowed(s['layer']):eligible.add(s['id'])
        for ident,box in boxes.items():
            if scene is not None and inside:
                b=scene.owner_bounds(ident);box=QRectF(b.left,b.bottom,b.width(),b.height())
            if ident in eligible and (rect.contains(box) if inside else rect.intersects(box)):ids.append(ident)
        if 'pins' in filters:
            ids += ['pin:'+p['id'] for p in self.cell.get('layout_pins',[]) if self.editor_allowed(p['layer']) and rect.contains(QPointF(*p['point']))]
        if 'labels' in filters:
            ids += ['text:'+str(i) for i,t in enumerate(self.cell.get('layout_texts',[])) if self.editor_allowed(t['layer']) and rect.contains(QPointF(t['x'],t['y']))]
        return list(dict.fromkeys(ids))

    def editor_press(self,e):
        if self.mode!='layout' or e.button()!=Qt.LeftButton or self.space:return False
        self.setFocus();pos=self.snap(self.model(e.position()));self.editor_pointer=self.model(e.position())
        if self.tool=='instance_place':self.editor_requested.emit('instance_place',{'x':round(pos.x()),'y':round(pos.y())});return True
        if self.tool=='select' and e.modifiers()&Qt.AltModifier:self.editor_cycle();return True
        if self.tool in ('move_ref','copy_ref'):
            if not self.selection:self.message.emit('Select shapes or an instance first.');return True
            if getattr(self,'reference_point',None) is None:self.reference_point=pos
            else:
                delta=pos-self.reference_point;self.reference_point=None
                if delta.x() or delta.y():self.editor_requested.emit(self.tool,{'dx':round(delta.x()),'dy':round(delta.y())})
            self.update();return True
        if self.tool in ('vertex','edge'):
            candidates=[]
            for s in self.cell['shapes']:
                if s['id'] not in self.selection or s.get('source_id') or not self.editor_allowed(s['layer']):continue
                pts=s['points']
                if s['kind']=='rect':
                    (x1,y1),(x2,y2)=pts;pts=[[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
                for i,pt in enumerate(pts):
                    if self.tool=='edge':
                        if s['kind']=='path' and i==len(pts)-1:continue
                        b=pts[(i+1)%len(pts)];dx,dy=b[0]-pt[0],b[1]-pt[1];length=dx*dx+dy*dy
                        if not length:continue
                        f=max(0,min(1,((pos.x()-pt[0])*dx+(pos.y()-pt[1])*dy)/length));pt=[pt[0]+f*dx,pt[1]+f*dy]
                    candidates.append((math.hypot(pt[0]-pos.x(),pt[1]-pos.y()),s['id'],i))
            nearest=min(candidates,default=None)
            if nearest and nearest[0]*self.scale<=10:self.vertex_pick=nearest[1:];self.anchor=pos;self.drag=pos
            else:self.message.emit('Select a local shape, then drag one of its highlighted '+('vertices' if self.tool=='vertex' else 'edges')+'.')
            self.update();return True
        return False

    def editor_release(self,e):
        if self.mode!='layout' or not getattr(self,'vertex_pick',None):return False
        sid,index=self.vertex_pick;pos=self.snap(self.model(e.position()));self.vertex_pick=None;self.anchor=None
        self.editor_requested.emit('vertex',{'id':sid,'index':index,'point':[round(pos.x()),round(pos.y())],'edge':self.tool=='edge'});self.update();return True

    def editor_overlay(self,p):
        if self.mode!='layout':return
        pen=self.pen('#f0bd72',1.5);p.setPen(pen);p.setBrush(Qt.NoBrush)
        if self.tool=='instance_place' and self.drag is not None:
            p.save();p.translate(self.drag);p.rotate(getattr(self,'instance_angle',0));p.setOpacity(.6)
            for s in getattr(self,'instance_preview',[]):p.drawPath(self.path(s))
            p.restore()
        for pin in self.cell.get('layout_pins',[]):
            if 'pin:'+pin['id'] in self.selection:p.drawEllipse(QPointF(*pin['point']),7/self.scale,7/self.scale)
        for i,t in enumerate(self.cell.get('layout_texts',[])):
            if 'text:'+str(i) in self.selection:p.drawRect(QRectF(t['x']-3/self.scale,t['y']-14/self.scale,max(10,len(t['text'])*7)/self.scale+6/self.scale,20/self.scale))
        if self.tool in ('vertex','edge'):
            for s in self.cell['shapes']:
                if s['id'] not in self.selection or s.get('source_id'):continue
                pts=s['points']
                if s['kind']=='rect':
                    (x1,y1),(x2,y2)=pts;pts=[[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
                if self.tool=='edge':p.drawPath(self.path(s))
                for x,y in pts:p.drawRect(QRectF(x-3/self.scale,y-3/self.scale,6/self.scale,6/self.scale))
            if getattr(self,'vertex_pick',None) and self.drag:p.drawEllipse(self.drag,5/self.scale,5/self.scale)
        reference=getattr(self,'reference_point',None)
        if reference is not None and self.drag:
            delta=self.drag-reference;p.save();p.translate(delta);pen.setStyle(Qt.DashLine);p.setPen(pen)
            for s in self.cell['shapes']:
                if s['id'] in self.selection:p.drawPath(self.path(s))
            p.restore();p.drawLine(reference,self.drag)
        if self.anchor is not None and self.drag is not None and self.tool in ('rect','ruler','vertex','edge','stretch'):
            delta=self.drag-self.anchor;p.save();p.translate(self.drag);p.scale(1/self.scale,1/self.scale)
            p.drawText(QPointF(12,-12),f'ΔX {delta.x()/1000:.3f}  ΔY {delta.y()/1000:.3f} µm');p.restore()

    def editor_background(self,p,view):
        if self.mode!='layout':return
        p.save();p.setOpacity(.18);p.setBrush(Qt.NoBrush)
        colors={l['name']:l['color'] for l in self.tech['layers']}
        for s in getattr(self,'context_shapes',[]):
            if s['layer'] in self.visible_layers and view.intersects(self.bounds(s)):
                p.setPen(self.pen(colors.get(s['layer'],'#888888'),1));p.drawPath(self.path(s))
        p.restore()

    def editor_brush(self,layer,color):
        styles={'Solid':Qt.SolidPattern,'Outline':Qt.NoBrush,'Dense':Qt.Dense4Pattern,'Hatch':Qt.BDiagPattern,'Cross':Qt.DiagCrossPattern}
        return QBrush(color,styles.get(getattr(self,'layer_styles',{}).get(layer,{}).get('pattern','Solid'),Qt.SolidPattern))
