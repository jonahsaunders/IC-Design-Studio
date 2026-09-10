import math
from PySide6.QtCore import Qt,QRectF,QPointF,Signal,QEvent
from PySide6.QtGui import QPainter,QPen,QColor,QPainterPath,QFont
from PySide6.QtWidgets import QWidget

from .ui_style import palette
COLORS=['#315fcd','#a76713','#8b4cb8','#17755e','#b34661','#626e25']
def trace_colors(dark=False):return ['#86a8ff','#e7ba75','#cea5f3','#76c9b1','#ef99ae','#bdcd83'] if dark else COLORS
def engineering(value):
    if value==0:return '0'
    for scale,suffix in [(1e9,'G'),(1e6,'M'),(1e3,'k'),(1,''),(1e-3,'m'),(1e-6,'µ'),(1e-9,'n'),(1e-12,'p')]:
        if abs(value)>=scale:return f'{value/scale:.3g}{suffix}'
    return f'{value:.2g}'
def unit_scale(value):
    for scale,suffix in [(1e9,'G'),(1e6,'M'),(1e3,'k'),(1,''),(1e-3,'m'),(1e-6,'µ'),(1e-9,'n'),(1e-12,'p')]:
        if abs(value)>=scale:return scale,suffix
    return 1,''
def analysis_kind(result):
    s=result['settings'];kind=s['type']
    if kind in ('xschem','program'):return result.get('plot_kind','op')
    if kind in ('post_layout','rc_compare'):return s['analysis']['type']
    if kind=='deck':return {'frequency':'ac','time':'tran'}.get(result['x_label'],'op')
    return kind

class WavePlot(QWidget):
    cursor_changed=Signal(str)
    markers_changed=Signal()
    result_changed=Signal()
    def event(self,event):
        if event.type()==QEvent.ShortcutOverride and event.key() in (Qt.Key_F,Qt.Key_Delete,Qt.Key_Backspace,Qt.Key_Escape):
            event.accept();return True
        return super().event(event)
    def __init__(self,parent=None):
        super().__init__(parent);self.result=None;self.compare=None;self.names=[];self.dark=False;self.a=None;self.b=None;self._bounds=None;self.empty_message="Run an analysis to inspect voltages and measurements";self.setMinimumHeight(155);self.setMouseTracking(True);self.setFocusPolicy(Qt.StrongFocus);self.setAccessibleName('Waveform plot; place and drag X cursors, Y limits and X/Y checks')
        self.markers=[];self.marker_mode='Inspect';self.marker_trace='';self.marker_rule='<=';self.nearest_sample=False;self.selected_marker=None;self._drag_marker=None;self._pan=None;self._view_bounds=None
    def set_result(self,result,names=None,compare=None,overlays=None):
        changed=self.result is not result
        self.result=result;self.names=list(names if names is not None else result['traces'] if result else []);self.compare=compare;self.overlays=list(overlays or []);self._bounds=None
        if changed:
            self.a=None;self.b=None;self.markers=[];self.selected_marker=None;self._view_bounds=None;self.result_changed.emit()
        self.update()
    def bounds(self):
        if self._view_bounds is not None:return self._view_bounds
        if self._bounds is not None:return self._bounds
        xs=list(self.result['x']);values=[v for n in self.names for v in self.result['traces'].get(n,[])]
        for r in getattr(self,'overlays',[]):
            xs+=r['x'];values += [v for n in self.names for v in r['traces'].get(n,[])]
        if self.compare:xs+=self.compare['x'];values += [v for n in self.names for v in self.compare['traces'].get(n,[])]
        ymin=min([0]+values);ymax=max([0]+values);padding=(ymax-ymin)*.1 or 1
        self._bounds=(min(xs),max(xs) if max(xs)>min(xs) else min(xs)+1,ymin-padding,ymax+padding);return self._bounds
    def screen(self,x,y):
        x0,x1,y0,y1=self.bounds();log=analysis_kind(self.result) in ('ac','noise')
        frac=(math.log10(max(x,1e-99))-math.log10(x0))/(math.log10(x1)-math.log10(x0)) if log else (x-x0)/(x1-x0)
        return QPointF(self.box.left()+frac*self.box.width(),self.box.bottom()-(y-y0)/(y1-y0)*self.box.height())
    def paintEvent(self,e):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.fillRect(self.rect(),QColor(palette(self.dark)['canvas'] if self.dark else '#ffffff'));fg=palette(self.dark)['muted'];p.setPen(QColor(fg));p.setFont(QFont('Sans Serif',9))
        if not self.result or not self.result['x']:p.drawText(self.rect(),Qt.AlignCenter,self.empty_message);return
        self.box=QRectF(48,20,max(10,self.width()-66),max(10,self.height()-58));x0,x1,y0,y1=self.bounds();log=analysis_kind(self.result) in ('ac','noise')
        yscale,yprefix=unit_scale(max(abs(y0),abs(y1)));xscale,xprefix=unit_scale(x1) if analysis_kind(self.result)=='tran' else (1,'')
        for i in range(6):
            y=self.box.top()+i*self.box.height()/5;p.setPen(QColor('#26313e' if self.dark else '#e8edf2'));p.drawLine(QPointF(self.box.left(),y),QPointF(self.box.right(),y));p.setPen(QColor(fg));p.drawText(QRectF(0,y-8,40,18),Qt.AlignRight|Qt.AlignVCenter,f'{(y1-i*(y1-y0)/5)/yscale:.3g}')
            x=self.box.left()+i*self.box.width()/5;v=x0*(x1/x0)**(i/5) if log else x0+(x1-x0)*i/5;p.drawText(QRectF(x-30,self.box.bottom()+8,60,18),Qt.AlignCenter,engineering(v) if log else f'{v/xscale:.3g}')
        p.drawText(QRectF(self.box.left(),self.height()-18,self.box.width(),17),Qt.AlignCenter,('Time ('+xprefix+'s)') if analysis_kind(self.result)=='tran' else self.result['x_label']);p.drawText(QPointF(7,12),yprefix+self.result.get('plot_unit',('V/√Hz' if analysis_kind(self.result)=='noise' else 'Hz' if self.result['settings'].get('study',{}).get('measurement',{}).get('metric')=='peak_x' else 'V')))
        p.save();p.setClipRect(self.box)
        for nindex,name in enumerate(self.names):
            for series,(result,is_old) in enumerate([(self.result,False)]+[(r,False) for r in getattr(self,'overlays',[])]+[(self.compare,True)]):
                if not result or name not in result['traces']:continue
                color_index=series if getattr(self,'overlays',[]) else list(self.result['traces']).index(name)
                pen=QPen(QColor(trace_colors(self.dark)[color_index%6]),1.1 if is_old else 2);pen.setStyle(Qt.DashLine if is_old else Qt.SolidLine);p.setPen(pen);path=QPainterPath();xs=result['x'];ys=result['traces'][name];stride=max(1,len(xs)//max(200,self.width()*2))
                indices=list(range(0,len(xs),stride))
                if xs and indices[-1]!=len(xs)-1:indices.append(len(xs)-1)
                for j in indices:
                    pos=self.screen(xs[j],ys[j]);path.moveTo(pos) if j==0 else path.lineTo(pos)
                if len(xs)==1:p.drawEllipse(self.screen(xs[0],ys[0]),4,4)
                else:p.drawPath(path)
        p.restore()
        for index,label in [(self.a,'A'),(self.b,'B')]:
            if index is not None:
                x=self.screen(self.result['x'][index],0).x();p.setPen(QPen(QColor(palette(self.dark)['accent']),1,Qt.DashLine));p.drawLine(QPointF(x,self.box.top()),QPointF(x,self.box.bottom()));p.drawText(QPointF(x+4,self.box.top()+12),label)
        self.paint_markers(p)

    def data_point(self,pos):
        x0,x1,y0,y1=self.bounds();fx=(pos.x()-self.box.left())/self.box.width();fy=(self.box.bottom()-pos.y())/self.box.height()
        x=x0*(x1/x0)**fx if analysis_kind(self.result) in ('ac','noise') else x0+(x1-x0)*fx
        return x,y0+(y1-y0)*fy

    def fit_plot(self):self._view_bounds=None;self._bounds=None;self.update()

    def add_marker(self,kind,x,y,trace=None):
        from .model import uid
        if len(self.markers)>=200:self.cursor_changed.emit('Remove a marker before adding more than 200.');return None
        marker={'id':uid(),'kind':kind,'x':float(x),'y':float(y),'trace':trace or self.marker_trace or (self.names[0] if self.names else ''),'rule':self.marker_rule,'nearest':self.nearest_sample}
        self.markers.append(marker);self.selected_marker=marker['id'];self.markers_changed.emit();self.marker_readout();self.update();return marker

    def marker_readout(self):
        from .measurements import evaluate
        pieces=[]
        for i,m in enumerate(self.markers):
            result=evaluate(self.result,m);value='—' if result['value'] is None else f"{result['value']:.7g}"
            pieces.append(f"M{i+1} · {m['trace']} · "+(f"X={m['x']:.7g} · " if m['kind']!='Y' else '')+f"Y={value} · {result['verdict']}")
        xs=[m for m in self.markers if m['kind']!='Y']
        if len(xs)>=2:
            a,b=xs[-2:];dt=b['x']-a['x'];ya=evaluate(self.result,a)['value'];yb=evaluate(self.result,b)['value'];pieces.append(f'ΔX={dt:.7g}'+(f' · ΔY={yb-ya:.7g}' if ya is not None and yb is not None else ''))
        if pieces:self.cursor_changed.emit('   |   '.join(pieces[-4:]))

    def paint_markers(self,p):
        from .measurements import evaluate
        p.save();p.setClipRect(self.box.adjusted(-1,-1,1,1))
        for i,m in enumerate(self.markers):
            check=evaluate(self.result,m);color='#e0a33c' if m['id']==self.selected_marker else '#d35d79' if check['verdict']=='FAIL' else '#38a283' if check['verdict']=='PASS' else palette(self.dark)['accent']
            p.setPen(QPen(QColor(color),1.7 if m['id']==self.selected_marker else 1,Qt.DashLine));pos=self.screen(m['x'],m['y'])
            if m['kind']!='Y':p.drawLine(QPointF(pos.x(),self.box.top()),QPointF(pos.x(),self.box.bottom()))
            if m['kind']!='X':p.drawLine(QPointF(self.box.left(),pos.y()),QPointF(self.box.right(),pos.y()))
            if m['kind']!='Y' and check['value'] is not None:
                at=self.screen(m['x'],check['value']);p.setBrush(QColor(color));p.drawEllipse(at,4,4);p.setBrush(Qt.NoBrush)
            text=f"M{i+1}"+(f" · {check['verdict']}" if m['kind']!='X' else '')
            x=max(self.box.left()+4,min(self.box.right()-110,pos.x()+6)) if m['kind']!='Y' else self.box.left()+6
            y=max(self.box.top()+14,min(self.box.bottom()-4,pos.y()-6)) if m['kind']!='X' else self.box.top()+14+(i%3)*15
            p.drawText(QPointF(x,y),text)
        p.restore()

    def marker_hit(self,pos):
        hits=[]
        for m in self.markers:
            screen=self.screen(m['x'],m['y']);dx=abs(pos.x()-screen.x());dy=abs(pos.y()-screen.y())
            distance=dx if m['kind']=='X' else dy if m['kind']=='Y' else min(dx,dy)
            if distance<7:hits.append((distance,m))
        return min(hits,key=lambda pair:pair[0])[1] if hits else None

    def mousePressEvent(self,e):
        if not self.result or not self.result['x'] or not hasattr(self,'box') or not self.box.contains(e.position()):return
        self.setFocus()
        if e.button()==Qt.MiddleButton:self._pan=(e.position(),self.bounds());return
        if e.button()==Qt.LeftButton:
            hit=self.marker_hit(e.position())
            if hit:
                at=self.screen(hit['x'],hit['y']);dx=abs(e.position().x()-at.x());dy=abs(e.position().y()-at.y())
                axis=hit['kind'] if hit['kind']!='XY' else 'XY' if dx<7 and dy<7 else 'X' if dx<dy else 'Y'
                self.selected_marker=hit['id'];self._drag_marker=(hit,dict(hit),axis,self.data_point(e.position()));self.markers_changed.emit();self.update();return
            if self.marker_mode in ('X','Y','XY'):
                x,y=self.data_point(e.position());m=self.add_marker(self.marker_mode,x,y)
                if m:self._drag_marker=(m,dict(m),m['kind'],(x,y))
                return
        index=min(range(len(self.result['x'])),key=lambda i:abs(self.screen(self.result['x'][i],0).x()-e.position().x()))
        if e.button()==Qt.RightButton:self.b=index
        else:self.a=index
        pieces=[]
        for i,label in [(self.a,'A'),(self.b,'B')]:
            if i is not None:pieces.append(label+f': x={self.result["x"][i]:.6g}  '+', '.join(f'{n}={self.result["traces"][n][i]:.6g}' for n in self.names))
        if self.a is not None and self.b is not None:
            dt=self.result['x'][self.b]-self.result['x'][self.a];pieces.append(f'Δx={dt:.6g}'+(f'  1/|Δt|={1/abs(dt):.6g} Hz' if dt and analysis_kind(self.result)=='tran' else ''))
        self.cursor_changed.emit('   |   '.join(pieces));self.update()

    def mouseMoveEvent(self,e):
        if not self.result or not self.result['x'] or not hasattr(self,'box'):return
        if self._drag_marker:
            m,old,axis,start=self._drag_marker;x,y=self.data_point(e.position())
            if axis!='Y':m['x']=old['x']+x-start[0]
            if axis!='X':m['y']=old['y']+y-start[1]
            self.marker_readout();self.update();return
        if self._pan:
            start,bounds=self._pan;dx=(e.position().x()-start.x())/self.box.width();dy=(e.position().y()-start.y())/self.box.height();x0,x1,y0,y1=bounds
            if analysis_kind(self.result) in ('ac','noise'):factor=(x1/x0)**(-dx);x0*=factor;x1*=factor
            else:delta=(x1-x0)*dx;x0-=delta;x1-=delta
            delta=(y1-y0)*dy;self._view_bounds=(x0,x1,y0+delta,y1+delta);self.update();return
        self.setCursor(Qt.SizeAllCursor if self.marker_hit(e.position()) else Qt.CrossCursor)

    def mouseReleaseEvent(self,e):
        if self._drag_marker:self._drag_marker=None;self.markers_changed.emit()
        self._pan=None

    def wheelEvent(self,e):
        if not self.result or not self.result['x'] or not hasattr(self,'box') or not self.box.contains(e.position()):return
        x,y=self.data_point(e.position());x0,x1,y0,y1=self.bounds();factor=.8 if e.angleDelta().y()>0 else 1.25
        if not e.modifiers()&Qt.ShiftModifier:
            if analysis_kind(self.result) in ('ac','noise'):x0=x*(x0/x)**factor;x1=x*(x1/x)**factor
            else:x0=x+(x0-x)*factor;x1=x+(x1-x)*factor
        if e.modifiers()&(Qt.ControlModifier|Qt.ShiftModifier):y0=y+(y0-y)*factor;y1=y+(y1-y)*factor
        if x1>x0 and y1>y0:self._view_bounds=(x0,x1,y0,y1);self.update()
        e.accept()

    def mouseDoubleClickEvent(self,e):
        if e.button()==Qt.LeftButton and self.marker_mode=='Inspect':self.fit_plot()

    def keyPressEvent(self,e):
        if e.key()==Qt.Key_Escape:
            if self._drag_marker:
                marker,old,*_=self._drag_marker;marker.clear();marker.update(old);self._drag_marker=None
            self.marker_mode='Inspect';self._pan=None;self.markers_changed.emit();self.update();return
        if e.key() in (Qt.Key_Delete,Qt.Key_Backspace) and self.selected_marker:
            self.markers=[m for m in self.markers if m['id']!=self.selected_marker];self.selected_marker=None;self.markers_changed.emit();self.update();return
        if e.key()==Qt.Key_F:self.fit_plot();return
        super().keyPressEvent(e)
