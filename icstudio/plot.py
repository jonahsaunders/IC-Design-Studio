import math
from PySide6.QtCore import Qt,QRectF,QPointF,Signal
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
    if kind=='post_layout':return s['analysis']['type']
    if kind=='deck':return {'frequency':'ac','time':'tran'}.get(result['x_label'],'op')
    return kind

class WavePlot(QWidget):
    cursor_changed=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.result=None;self.compare=None;self.names=[];self.dark=False;self.a=None;self.b=None;self._bounds=None;self.empty_message="Run an analysis to inspect voltages and measurements";self.setMinimumHeight(155);self.setMouseTracking(True);self.setAccessibleName('Waveform plot; click for cursor A, right-click for cursor B')
    def set_result(self,result,names=None,compare=None,overlays=None):self.result=result;self.names=list(names if names is not None else result['traces'] if result else []);self.compare=compare;self.overlays=list(overlays or []);self.a=None;self.b=None;self._bounds=None;self.update()
    def bounds(self):
        if self._bounds is not None:return self._bounds
        xs=list(self.result['x']);values=[v for n in self.names for v in self.result['traces'].get(n,[])]
        for r in getattr(self,'overlays',[]):
            xs+=r['x'];values += [v for n in self.names for v in r['traces'].get(n,[])]
        if self.compare:values += [v for n in self.names for v in self.compare['traces'].get(n,[])]
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
        for nindex,name in enumerate(self.names):
            for series,(result,is_old) in enumerate([(self.result,False)]+[(r,False) for r in getattr(self,'overlays',[])]+[(self.compare,True)]):
                if not result or name not in result['traces']:continue
                color_index=series if getattr(self,'overlays',[]) else list(self.result['traces']).index(name)
                pen=QPen(QColor(trace_colors(self.dark)[color_index%6]),1.1 if is_old else 2);pen.setStyle(Qt.DashLine if is_old else Qt.SolidLine);p.setPen(pen);path=QPainterPath();xs=result['x'];ys=result['traces'][name];stride=max(1,len(xs)//max(200,self.width()*2))
                for j in range(0,len(xs),stride):
                    pos=self.screen(xs[j],ys[j]);path.moveTo(pos) if j==0 else path.lineTo(pos)
                if len(xs)==1:p.drawEllipse(self.screen(xs[0],ys[0]),4,4)
                else:p.drawPath(path)
        for index,label in [(self.a,'A'),(self.b,'B')]:
            if index is not None:
                x=self.screen(self.result['x'][index],0).x();p.setPen(QPen(QColor(palette(self.dark)['accent']),1,Qt.DashLine));p.drawLine(QPointF(x,self.box.top()),QPointF(x,self.box.bottom()));p.drawText(QPointF(x+4,self.box.top()+12),label)
    def mousePressEvent(self,e):
        if not self.result or not self.result['x'] or not hasattr(self,'box'):return
        index=min(range(len(self.result['x'])),key=lambda i:abs(self.screen(self.result['x'][i],0).x()-e.position().x()))
        if e.button()==Qt.RightButton:self.b=index
        else:self.a=index
        pieces=[]
        for i,label in [(self.a,'A'),(self.b,'B')]:
            if i is not None:pieces.append(label+f': x={self.result["x"][i]:.6g}  '+', '.join(f'{n}={self.result["traces"][n][i]:.6g}' for n in self.names))
        if self.a is not None and self.b is not None:
            dt=self.result['x'][self.b]-self.result['x'][self.a];pieces.append(f'Δx={dt:.6g}'+(f'  1/|Δt|={1/abs(dt):.6g} Hz' if dt and analysis_kind(self.result)=='tran' else ''))
        self.cursor_changed.emit('   |   '.join(pieces));self.update()
