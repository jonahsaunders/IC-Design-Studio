"""Symbol geometry and metadata shared by drawing, properties and interchange."""
import math,re
from .model import clone,uid

def enriched(symbol):
    s=clone(symbol);s.setdefault('pin_order',list(s['pins']));s.setdefault('pin_meta',{});s.setdefault('attributes',{})
    for name in s['pins']:
        m=s['pin_meta'].setdefault(name,{})
        for key,value in {'id':uid(),'direction':'inout','role':'signal','bus':'','label_visible':True,'required':True}.items():m.setdefault(key,value)
    return s

def text_value(text,context=None):
    context=context or {}
    return re.sub(r'@([A-Za-z_][A-Za-z0-9_]*)',lambda m:str(context.get(m[1],m[0])),text)


def visible_text(item, context=None):
    """Xschem diagnostic placeholders have no value without backannotation.

    Older saved imports did not retain hide=true. Recognize their diagnostic
    tokens as well, without hiding unknown user-defined parameter names.
    """
    if item.get('hidden') and context is not None:return ''
    text=text_value(item['text'],context)
    if context is not None and re.search(r'@(?:#\S+|spice_get_\w+)',text):return ''
    return text

def transform(s,indices,dx=0,dy=0,angle=0,mirror=None,origin=(0,0),pins=()):
    co=round(math.cos(math.radians(angle)));si=round(math.sin(math.radians(angle)))
    def point(pt):
        x,y=pt[0]-origin[0],pt[1]-origin[1]
        if mirror=='horizontal':x=-x
        if mirror=='vertical':y=-y
        return [origin[0]+x*co-y*si+dx,origin[1]+x*si+y*co+dy]
    for i in indices:
        item=s['primitives'][i];item['points']=[point(p) for p in item['points']]
        if item['kind']=='arc':
            start=item.get('start',0);sweep=item.get('sweep',90)
            if mirror=='horizontal':start=180-start;sweep=-sweep
            if mirror=='vertical':start=-start;sweep=-sweep
            item.update(start=(start+angle)%360,sweep=sweep)
        if item['kind']=='text':item['rotation']=(item.get('rotation',0)+angle)%360
    for name in pins:s['pins'][name]=point(s['pins'][name])
    return s

def bounds(item):
    xs,ys=zip(*item['points']);return min(xs),min(ys),max(xs),max(ys)

def align(s,indices,mode):
    if len(indices)<2:raise ValueError('Select at least two artwork objects.')
    boxes=[bounds(s['primitives'][i]) for i in indices]
    axis=1 if mode in ('top','bottom','center_y','distribute_y') else 0
    coord=lambda b:(b[axis]+b[axis+2])/2 if mode.startswith(('center','distribute')) else b[axis+2] if mode in ('right','bottom') else b[axis]
    if mode.startswith('distribute'):
        if len(indices)<3:raise ValueError('Distribution requires at least three objects.')
        order=sorted(zip(indices,boxes),key=lambda v:coord(v[1]));start,end=coord(order[0][1]),coord(order[-1][1]);moves=[(i,start+(end-start)*j/(len(order)-1)-coord(b)) for j,(i,b) in enumerate(order)]
    else:moves=[(i,coord(boxes[0])-coord(b)) for i,b in zip(indices[1:],boxes[1:])]
    for i,delta in moves:transform(s,[i],dy=delta if axis else 0,dx=delta if not axis else 0)

def painter_path(item):
    from PySide6.QtCore import QPointF,QRectF
    from PySide6.QtGui import QPainterPath
    pts=item['points'];p=QPainterPath();kind=item['kind'];box=QRectF(QPointF(*pts[0]),QPointF(*pts[-1])).normalized()
    if kind=='rect':p.addRect(box)
    elif kind=='ellipse':p.addEllipse(box)
    elif kind=='arc':p.arcMoveTo(box,-item.get('start',0));p.arcTo(box,-item.get('start',0),-item.get('sweep',90))
    elif kind=='text':p.addRect(box)
    else:
        p.moveTo(*pts[0])
        for pt in pts[1:]:p.lineTo(*pt)
        if kind=='polygon':p.closeSubpath()
    return p

def text_bounds(item,context=None,frame=None,*,xschem=False):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont,QFontMetricsF,QTransform
    text=visible_text(item,context)
    if not text:return QRectF()
    font=QFont('Sans Serif');font.setPointSizeF(item.get('font_size',8));font.setBold(item.get('bold',False))
    metrics=QFontMetricsF(font)
    transform=QTransform(frame) if frame is not None else QTransform()
    transform.translate(*item['points'][0]);transform.rotate(item.get('rotation',0))
    if xschem or item.get('text_anchor')=='corner':
        if item.get('mirror'):transform.scale(-1,1)
        width,height=metrics.horizontalAdvance(text),metrics.height()
        box=QRectF(-width/2 if item.get('hcenter') else 0,-height/2 if item.get('vcenter') else 0,width,height)
    else:
        box=metrics.boundingRect(text)
        box.translate(-box.center().x() if item.get('hcenter') else 0,-box.center().y() if item.get('vcenter') else 0)
    return transform.mapRect(box)


def draw(p,symbol,color,context=None,*,xschem=False):
    from PySide6.QtCore import Qt,QPointF,QRectF
    from PySide6.QtGui import QColor,QPen,QFont,QFontMetricsF,QTransform
    for item in symbol.get('primitives',[]):
        p.save();pen=QPen(QColor(item.get('color',color)),item.get('line_width',1.5));pen.setCosmetic(True);pen.setCapStyle(Qt.RoundCap);pen.setJoinStyle(Qt.RoundJoin);p.setPen(pen);p.setBrush(QColor(item.get('color',color)) if item.get('fill',False) else Qt.NoBrush)
        if item['kind']=='text':
            text=visible_text(item,context)
            p.translate(QPointF(*item['points'][0]));p.rotate(item.get('rotation',0));font=QFont('Sans Serif');font.setPointSizeF(item.get('font_size',8));font.setBold(item.get('bold',False));p.setFont(font)
            metrics=QFontMetricsF(font);box=metrics.boundingRect(text)
            if xschem or item.get('text_anchor')=='corner':
                # Xschem rotation/flip select the corner of a text box; they
                # do not produce mirrored or upside-down glyphs. Preserve the
                # transformed box while painting readable horizontal/vertical ink.
                if item.get('mirror'):p.scale(-1,1)
                width=metrics.horizontalAdvance(text);height=metrics.height()
                frame=p.worldTransform()
                target=frame.mapRect(QRectF(-width/2 if item.get('hcenter') else 0,
                                           -height/2 if item.get('vcenter') else 0,width,height))
                scale=math.hypot(frame.m11(),frame.m12())
                vertical=abs(frame.m12())>abs(frame.m11())
                p.setWorldTransform(QTransform())
                p.translate(target.left(),target.bottom() if vertical else target.top())
                if vertical:p.rotate(-90)
                p.scale(scale,scale)
                p.drawText(QPointF(0,metrics.ascent()),text)
            else:
                p.drawText(QPointF(-box.center().x() if item.get('hcenter') else 0,-box.center().y() if item.get('vcenter') else 0),text)
        else:p.drawPath(painter_path(item))
        p.restore()


def generated(symbol):
    """Arrange the existing electrical interface around a labelled body."""
    s=enriched(symbol);sides={'left':[],'right':[],'top':[],'bottom':[]}
    for name in s['pin_order']:
        m=s['pin_meta'][name];direction=m['direction'];role=m['role']
        side='top' if role=='power' else 'bottom' if role=='ground' else 'left' if direction=='in' else 'right' if direction=='out' else 'left' if len(sides['left'])<=len(sides['right']) else 'right'
        sides[side].append(name)
    width=max(40,20*max(len(sides['top']),len(sides['bottom'])));height=max(40,20*max(len(sides['left']),len(sides['right'])));s['primitives']=[{'kind':'rect','points':[[-width,-height],[width,height]]}]
    for side,names in sides.items():
        for i,name in enumerate(names):
            offset=(i-(len(names)-1)/2)*40
            tip=[-width-20,offset] if side=='left' else [width+20,offset] if side=='right' else [offset,-height-20] if side=='top' else [offset,height+20]
            base=[-width,offset] if side=='left' else [width,offset] if side=='right' else [offset,-height] if side=='top' else [offset,height]
            s['pins'][name]=tip;s['primitives'].append({'kind':'line','points':[tip,base]})
    s['primitives'] += [{'kind':'text','points':[[-width+5,-10],[width-5,0]],'text':'@symname','font_size':6},{'kind':'text','points':[[-width+5,15],[width-5,25]],'text':'@name','font_size':6}]
    return s
