"""Vector symbol workspace with stable electrical pins and canvas-scoped commands."""
import json,math
from pathlib import Path
from PySide6.QtCore import Qt,QPointF,QRectF,Signal,QEvent,QSettings,QTimer
from PySide6.QtGui import QPainter,QPen,QColor,QFont,QPainterPathStroker,QPicture
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QPushButton,QLabel,QDialogButtonBox,QListWidget,QTableWidget,QTableWidgetItem,QHeaderView,QFileDialog,QInputDialog,QSplitter,QAbstractItemView,QFormLayout,QLineEdit,QDoubleSpinBox,QCheckBox)
from .model import clone,atomic_write,uid,NET
from .ui_style import palette
from .symbol_io import validate_symbol,import_symbol,symbol_text,default_symbol
from . import symbol_geometry as geometry
from .capture_keys import bindings,command_for,profile_dialog
from PySide6.QtWidgets import QStyledItemDelegate

class TerminalDelegate(QStyledItemDelegate):
    choices={3:['in','out','inout','passive'],4:['signal','power','ground','clock','analog'],6:['yes','no'],8:['yes','no']}
    def createEditor(self,parent,option,index):
        if index.column() not in self.choices:return super().createEditor(parent,option,index)
        combo=QComboBox(parent);combo.addItems(self.choices[index.column()]);return combo
    def setEditorData(self,editor,index):
        if isinstance(editor,QComboBox):editor.setCurrentText(index.data())
        else:super().setEditorData(editor,index)
    def setModelData(self,editor,model,index):
        if isinstance(editor,QComboBox):model.setData(index,editor.currentText())
        else:super().setModelData(editor,model,index)

def draw_symbol(p,symbol,color,context=None):geometry.draw(p,symbol,color,context)

class SymbolPad(QWidget):
    changed=Signal();selected=Signal(int);error=Signal(str);properties_requested=Signal()
    def __init__(self,symbol,dark,parent=None):
        super().__init__(parent);self.symbol=geometry.enriched(symbol);self.dark=dark;self.tool='select';self.pin=next(iter(symbol['pins']),'');self.anchor=None;self.cursor=None;self.history=[];self.future=[];self.selection=-1;self.selections=set();self.selected_pins=set();self.scale=3.;self.offset=QPointF();self.panning=False;self.marquee=False;self.handle=None;self.polygon=[];self.keys={};self.setMinimumSize(420,360);self.setMouseTracking(True);self.setFocusPolicy(Qt.StrongFocus);self.installEventFilter(self)
    def eventFilter(self,obj,e):
        cmd=command_for(e,self.keys)
        if cmd:
            if e.type()==QEvent.ShortcutOverride:e.accept();return True
            self.command(cmd);return True
        return super().eventFilter(obj,e)
    def point(self,p):return QPointF(round((p.x()-self.width()/2-self.offset.x())/self.scale/5)*5,round((p.y()-self.height()/2-self.offset.y())/self.scale/5)*5)
    def checkpoint(self):self.history.append(clone(self.symbol));self.history=self.history[-100:];self.future=[]
    def notify(self):self._symbol_picture=None;self.update();self.changed.emit()
    def apply(self,candidate):
        try:validate_symbol(candidate,candidate['pins']);self.checkpoint();self.symbol=candidate;self.error.emit('');self.notify();return True
        except ValueError as e:self.error.emit(str(e));return False
    def chosen(self):return sorted(self.selections or ({self.selection} if self.selection>=0 else set()))
    def command(self,cmd):
        if cmd in ('undo','redo','delete','fit'):getattr(self,cmd)();return
        if cmd=='properties':self.properties_requested.emit();return
        if cmd in ('zoom_in','zoom_out'):self.scale=max(.25,min(12,self.scale*(1.2 if cmd=='zoom_in' else 1/1.2)));self.update();return
        if cmd in ('rotate','mirror','copy'):
            s=clone(self.symbol);indices=self.chosen()
            if cmd=='copy':
                start=len(s['primitives']);s['primitives']+=clone([s['primitives'][i] for i in indices]);indices=list(range(start,len(s['primitives'])));geometry.transform(s,indices,10,10);self.selections=set(indices);self.selection=indices[0] if indices else -1
            else:geometry.transform(s,indices,angle=90 if cmd=='rotate' else 0,mirror='horizontal' if cmd=='mirror' else None,pins=self.selected_pins)
            self.apply(s);return
        self.anchor=None;self.cursor=None;self.polygon=[];self.tool='select' if cmd=='move' else 'handle' if cmd=='stretch' else cmd;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);t=palette(self.dark);p.fillRect(self.rect(),QColor(t['canvas']));p.translate(self.width()/2+self.offset.x(),self.height()/2+self.offset.y());p.scale(self.scale,self.scale);pen=QPen(QColor(t['grid']),1);pen.setCosmetic(True);p.setPen(pen)
        left=self.point(QPointF(0,0));right=self.point(QPointF(self.width(),self.height()))
        for x in range(max(-500,math.floor(left.x()/10)*10),min(501,math.ceil(right.x()/10)*10+1),10):
            for y in range(max(-500,math.floor(left.y()/10)*10),min(501,math.ceil(right.y()/10)*10+1),10):p.drawPoint(QPointF(x,y))
        candidate=self.symbol
        if self.anchor is not None and self.cursor is not None and not self.marquee:
            candidate=clone(self.symbol)
            if self.handle is not None:candidate['primitives'][self.handle[0]]['points'][self.handle[1]]=[self.cursor.x(),self.cursor.y()]
            elif self.tool=='select':geometry.transform(candidate,self.chosen(),self.cursor.x()-self.anchor.x(),self.cursor.y()-self.anchor.y(),pins=self.selected_pins)
            elif self.tool in ('line','rect','ellipse','arc'):candidate['primitives'].append({'kind':self.tool,'points':[[self.anchor.x(),self.anchor.y()],[self.cursor.x(),self.cursor.y()]]})
        if candidate is self.symbol:
            key=(id(self.symbol),t['text']);cached=getattr(self,'_symbol_picture',None)
            if cached is None or cached[0]!=key:
                picture=QPicture();recorder=QPainter(picture);draw_symbol(recorder,self.symbol,t['text']);recorder.end();self._symbol_picture=(key,picture)
            p.drawPicture(0,0,self._symbol_picture[1])
        else:draw_symbol(p,candidate,t['text'])
        for i in self.chosen():
            if i>=len(candidate['primitives']):continue
            primitive=clone(candidate['primitives'][i]);primitive['color']=t['accent'];draw_symbol(p,{'primitives':[primitive]},t['accent']);p.setPen(QPen(QColor(t['accent']),.5))
            for pt in primitive['points']:p.drawRect(QRectF(QPointF(*pt)-QPointF(2,2),QPointF(*pt)+QPointF(2,2)))
        if self.marquee and self.anchor is not None and self.cursor is not None:p.setPen(QPen(QColor(t['accent']),.5));p.drawRect(QRectF(self.anchor,self.cursor).normalized())
        if self.polygon:
            pts=self.polygon+([[self.cursor.x(),self.cursor.y()]] if self.cursor is not None else [])
            for a,b in zip(pts,pts[1:]):p.drawLine(QPointF(*a),QPointF(*b))
        p.setFont(QFont('Sans Serif',6))
        for pin,pt in candidate['pins'].items():
            q=QPointF(*pt);pen=QPen(QColor(t['accent']),2 if pin in self.selected_pins else 1);pen.setCosmetic(True);p.setPen(pen);p.drawRect(QRectF(q-QPointF(2,2),q+QPointF(2,2)))
            if candidate.get('pin_meta',{}).get(pin,{}).get('label_visible',True):p.drawText(q+QPointF(4,-4),pin)
    def mousePressEvent(self,e):
        self.setFocus()
        if e.button()==Qt.MiddleButton:self.panning=True;self.pan_start=e.position();return
        if e.button()==Qt.RightButton:self.finish_polygon();return
        if e.button()!=Qt.LeftButton:return
        pt=self.point(e.position())
        if max(abs(pt.x()),abs(pt.y()))>500:return
        if self.tool=='pin':
            if self.pin in self.symbol['pins']:s=clone(self.symbol);s['pins'][self.pin]=[pt.x(),pt.y()];self.apply(s)
        elif self.tool=='text':
            text,ok=QInputDialog.getText(self,'Symbol text','Text or @name / @value / @parameter')
            if ok and text:s=clone(self.symbol);s['primitives'].append({'kind':'text','points':[[pt.x(),pt.y()],[pt.x()+20,pt.y()+10]],'text':text});self.apply(s)
        elif self.tool=='polygon':self.polygon.append([pt.x(),pt.y()]);self.cursor=pt;self.update()
        elif self.tool in ('select','handle'):
            self.handle=None
            if self.tool=='handle':
                candidates=[((pt-QPointF(*point)).manhattanLength(),i,j) for i in self.chosen() for j,point in enumerate(self.symbol['primitives'][i]['points'])];hit=min(candidates,default=None)
                if hit and hit[0]*self.scale<=12:self.handle=hit[1:];self.anchor=pt;self.cursor=pt
                else:self.error.emit('Select artwork, then drag one of its endpoint handles.')
                return
            pin=next((n for n,q in self.symbol['pins'].items() if (pt-QPointF(*q)).manhattanLength()*self.scale<12),None);hit=None
            if not pin:
                stroker=QPainterPathStroker();stroker.setWidth(8/self.scale)
                for i in reversed(range(len(self.symbol['primitives']))):
                    path=geometry.painter_path(self.symbol['primitives'][i])
                    if path.contains(pt) or stroker.createStroke(path).contains(pt):hit=i;break
            additive=bool(e.modifiers()&(Qt.ControlModifier|Qt.ShiftModifier));self.marquee=pin is None and hit is None
            if not additive and (hit not in self.selections and pin not in self.selected_pins):self.selections=set();self.selected_pins=set()
            if pin:
                if additive and pin in self.selected_pins:self.selected_pins.remove(pin)
                else:self.selected_pins.add(pin)
            elif hit is not None:
                if additive and hit in self.selections:self.selections.remove(hit)
                else:self.selections.add(hit)
            self.selection=min(self.selections,default=-1);self.selected.emit(self.selection);self.anchor=pt;self.cursor=pt;self.update()
        else:self.anchor=pt;self.cursor=pt
    def mouseMoveEvent(self,e):
        if self.panning:self.offset+=e.position()-self.pan_start;self.pan_start=e.position();self.update();return
        self.cursor=self.point(e.position());self.update()
    def mouseReleaseEvent(self,e):
        if self.panning:self.panning=False;return
        if self.anchor is None:return
        end=self.point(e.position());s=clone(self.symbol)
        if self.marquee:
            box=QRectF(self.anchor,end).normalized();self.selections|={i for i,item in enumerate(s['primitives']) if box.intersects(QRectF(QPointF(*geometry.bounds(item)[:2]),QPointF(*geometry.bounds(item)[2:])).adjusted(-.1,-.1,.1,.1))};self.selected_pins|={n for n,p in s['pins'].items() if box.contains(QPointF(*p))};self.selection=min(self.selections,default=-1)
        elif end!=self.anchor:
            if self.handle is not None:s['primitives'][self.handle[0]]['points'][self.handle[1]]=[end.x(),end.y()]
            elif self.tool=='select':geometry.transform(s,self.chosen(),end.x()-self.anchor.x(),end.y()-self.anchor.y(),pins=self.selected_pins)
            elif self.tool in ('line','rect','ellipse','arc'):s['primitives'].append({'kind':self.tool,'points':[[self.anchor.x(),self.anchor.y()],[end.x(),end.y()]]})
            self.apply(s)
        self.anchor=None;self.cursor=None;self.handle=None;self.marquee=False;self.notify()
    def finish_polygon(self):
        if self.polygon:
            s=clone(self.symbol);s['primitives'].append({'kind':'polygon','points':self.polygon})
            if self.apply(s):self.polygon=[];self.cursor=None;self.update()
    def mouseDoubleClickEvent(self,e):
        if self.tool=='polygon':
            if len(self.polygon)>1 and self.polygon[-1]==self.polygon[-2]:self.polygon.pop()
            self.finish_polygon()
        elif self.tool=='select':self.properties_requested.emit()
    def undo(self):
        if self.history:self.future.append(clone(self.symbol));self.symbol=self.history.pop();self.selection=-1;self.selections=set();self.selected_pins=set();self.notify()
    def redo(self):
        if self.future:self.history.append(clone(self.symbol));self.symbol=self.future.pop();self.selection=-1;self.selections=set();self.selected_pins=set();self.notify()
    def delete(self):
        if self.chosen():s=clone(self.symbol);s['primitives']=[p for i,p in enumerate(s['primitives']) if i not in self.chosen()];self.selections=set();self.selection=-1;self.apply(s)
    def wheelEvent(self,e):self.scale=max(.25,min(12,self.scale*(1.15 if e.angleDelta().y()>0 else 1/1.15)));self.update()
    def fit(self):
        pts=list(self.symbol['pins'].values())+[pt for item in self.symbol['primitives'] for pt in item['points']];extent=max([abs(v) for pt in pts for v in pt]+[60]);self.offset=QPointF();self.scale=max(.25,min(5,(min(self.width(),self.height())-80)/(2*extent)));self.update()
    def keyPressEvent(self,e):
        if e.key()==Qt.Key_Delete:self.delete()
        elif e.key()==Qt.Key_Escape:self.anchor=None;self.cursor=None;self.polygon=[];self.tool='select';self.update()
        elif e.key() in (Qt.Key_Return,Qt.Key_Enter):self.finish_polygon()
        else:super().keyPressEvent(e)

class SymbolEditor(QDialog):
    def __init__(self,cell,dark,commit,parent=None,allow_interface=False):
        super().__init__(parent);self.setWindowTitle('Symbol editor · '+cell['name']);self.resize(1180,780);self.cell=cell;self.saved=False;self.loading=False;self.allow_interface=allow_interface;self.settings=getattr(parent,'settings',QSettings('ICDesignStudio','Capture'));v=QVBoxLayout(self);title=QLabel(cell['name']+'  /  SYMBOL');title.setStyleSheet('font-size:20px;font-weight:600');v.addWidget(title)
        symbol=geometry.enriched(cell.get('symbol') or default_symbol(cell['ports']));self.pad=SymbolPad(symbol,dark);self._initial=clone(self.pad.symbol);self.pad.tool='select';bar=QHBoxLayout();self.tool=QComboBox();self.tool.addItems(['Select / move','Line','Rectangle','Ellipse','Place pin','Text','Polygon','Arc','Endpoint handles']);bar.addWidget(self.tool);self.pins=QComboBox();bar.addWidget(self.pins)
        def button(row,text,fn):b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b);return b
        for text,fn in [('Undo',self.pad.undo),('Redo',self.pad.redo),('Copy',lambda:self.pad.command('copy')),('Rotate',lambda:self.pad.command('rotate')),('Mirror',lambda:self.pad.command('mirror')),('Fit',self.pad.fit)]:button(bar,text,fn)
        v.addLayout(bar);bar=QHBoxLayout();self.align=QComboBox();self.align.addItems(['left','right','top','bottom','center_x','center_y','distribute_x','distribute_y']);bar.addWidget(self.align);button(bar,'Align / distribute',self.align_artwork)
        for text,fn in [('Properties…',self.artwork_properties),('Attributes…',self.attributes_dialog),('Generate',self.generate),('Keys…',self.keyboard),('Import…',self.import_file),('Export…',self.export_file)]:button(bar,text,fn)
        v.addLayout(bar);split=QSplitter();split.addWidget(self.pad);side=QWidget();sv=QVBoxLayout(side);sv.addWidget(QLabel('ARTWORK · Shift selects multiple'));self.artwork=QListWidget();self.artwork.setSelectionMode(QAbstractItemView.ExtendedSelection);sv.addWidget(self.artwork,1);self.artwork.itemSelectionChanged.connect(self.select_artwork);sv.addWidget(QLabel('TERMINALS · row order is netlist order'))
        self.pin_table=QTableWidget(0,9);self.pin_table.setHorizontalHeaderLabels(['Name','X','Y','Direction','Role','Bus','Label','Identity','Req.']);self.pin_table.horizontalHeaderItem(8).setToolTip('Required terminal: no omits unused and dangling-terminal warnings.');self.pin_table.setItemDelegate(TerminalDelegate(self.pin_table));self.pin_table.hideColumn(7);self.pin_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);sv.addWidget(self.pin_table,2);row=QHBoxLayout()
        for text,fn in [('Add pin',self.add_pin),('Remove',self.remove_pin),('↑',lambda:self.order_pin(-1)),('↓',lambda:self.order_pin(1))]:button(row,text,fn)
        sv.addLayout(row);self.interface_note=QLabel();self.interface_note.setWordWrap(True);sv.addWidget(self.interface_note);split.addWidget(side);split.setSizes([650,480]);v.addWidget(split,1);self.error=QLabel();self.error.setWordWrap(True);self.error.setProperty('role','error');v.addWidget(self.error);v.addWidget(QLabel('Drag selects/moves; Shift adds to selection. Middle drag pans. Polygon: Enter finishes. Esc cancels.'))
        self.pin_table.itemChanged.connect(self.edit_pin);self.tool.currentIndexChanged.connect(lambda i:self.pad.command(('move','line','rect','ellipse','pin','text','polygon','arc','stretch')[i]));self.pins.currentTextChanged.connect(lambda text:setattr(self.pad,'pin',text));self.pad.changed.connect(self.refresh);self.pad.error.connect(self.error.setText);self.pad.properties_requested.connect(self.artwork_properties)
        self.commit_callback=commit;buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);v.addWidget(buttons);self.refresh();self.set_profile(self.settings.value('capture/symbol/profile','Studio'));QTimer.singleShot(0,self.pad.fit)
    def set_profile(self,name):self.pad.keys=bindings(self.settings,'symbol',name)
    def keyboard(self):self._keys_dialog=profile_dialog(self,self.settings,'symbol',self.set_profile)
    def save(self):
        try:
            validate_symbol(self.pad.symbol,self.pad.symbol['pins'] if self.allow_interface else self.cell['ports'])
            if self.commit_callback(clone(self.pad.symbol)) is False:return
            self.saved=True;self.accept()
        except Exception as e:self.error.setText(str(e))
    def refresh(self):
        self.loading=True;row=self.pin_table.currentRow();column=self.pin_table.currentColumn();self.artwork.clear();self.pins.clear();s=self.pad.symbol;self.pins.addItems(s['pin_order']);self.pins.setCurrentText(self.pad.pin);self.pin_table.setRowCount(len(s['pin_order']))
        for i,p in enumerate(s['primitives']):self.artwork.addItem(f'{i+1}. {p["kind"]}  '+p.get('text',''));self.artwork.item(i).setSelected(i in self.pad.chosen())
        for i,pin in enumerate(s['pin_order']):
            m=s['pin_meta'][pin];values=[pin,*s['pins'][pin],m['direction'],m['role'],m.get('bus',''),'yes' if m['label_visible'] else 'no',m['id'],'yes' if m.get('required',True) else 'no']
            for j,value in enumerate(values):
                it=QTableWidgetItem(str(value))
                if j==7 or j==0 and not self.allow_interface:it.setFlags(it.flags()&~Qt.ItemIsEditable)
                self.pin_table.setItem(i,j,it)
        if 0<=row<self.pin_table.rowCount():self.pin_table.setCurrentCell(row,column)
        changed=sum(self._initial['pin_meta'].get(n,{})!=s['pin_meta'].get(n,{}) or self._initial['pins'].get(n)!=pt for n,pt in s['pins'].items());self.interface_note.setText(str(changed)+' terminal definitions changed. Stable identities preserve connected nets when terminals move or are renamed.\nDirections: in / out / inout / passive. Roles: signal / power / ground / clock / analog.');self.loading=False
    def select_artwork(self,*_):
        if not self.loading:self.pad.selections={self.artwork.row(it) for it in self.artwork.selectedItems()};self.pad.selection=min(self.pad.selections,default=-1);self.pad.update()
    def edit_pin(self,item):
        if self.loading:return
        try:
            s=clone(self.pad.symbol);old=s['pin_order'][item.row()];col=item.column();value=item.text().strip()
            if col==0:
                if not self.allow_interface:raise ValueError('Device terminals are fixed.')
                if not NET.fullmatch(value) or value=='0' or value in s['pins'] and value!=old:raise ValueError('Choose a unique terminal name.')
                s['pins'][value]=s['pins'].pop(old);s['pin_meta'][value]=s['pin_meta'].pop(old);s['pin_order'][item.row()]=value
            elif col in (1,2):s['pins'][old][col-1]=float(value)
            elif col in (3,4,5):s['pin_meta'][old][{3:'direction',4:'role',5:'bus'}[col]]=value
            elif col in (6,8):
                if value not in ('yes','no'):raise ValueError('Label visibility must be yes or no.')
                s['pin_meta'][old]['label_visible' if col==6 else 'required']=value=='yes'
            if not self.pad.apply(s):self.refresh()
        except Exception as e:self.error.setText(str(e));self.refresh()
    def add_pin(self):
        if not self.allow_interface:self.error.setText('Device terminals are fixed by their electrical model.');return
        name,ok=QInputDialog.getText(self,'New terminal','Name')
        if ok:
            if not NET.fullmatch(name) or name=='0' or name in self.pad.symbol['pins']:self.error.setText('Choose a unique terminal name.');return
            s=clone(self.pad.symbol);s['pins'][name]=[-60,0];s['pin_order'].append(name);self.pad.apply(geometry.enriched(s))
    def remove_pin(self):
        row=self.pin_table.currentRow()
        if not self.allow_interface or row<0:return
        s=clone(self.pad.symbol);name=s['pin_order'].pop(row);s['pins'].pop(name);s['pin_meta'].pop(name);self.pad.apply(s)
    def order_pin(self,delta):
        row=self.pin_table.currentRow();s=clone(self.pad.symbol)
        if 0<=row+delta<len(s['pin_order']) and row>=0:s['pin_order'][row],s['pin_order'][row+delta]=s['pin_order'][row+delta],s['pin_order'][row];self.pad.apply(s);self.pin_table.selectRow(row+delta)
    def generate(self):
        s=geometry.generated(self.pad.symbol);self.pad.selections=set();self.pad.selection=-1;self.pad.apply(s);self.pad.fit()
    def align_artwork(self):
        try:s=clone(self.pad.symbol);geometry.align(s,self.pad.chosen(),self.align.currentText());self.pad.apply(s)
        except Exception as e:self.error.setText(str(e))
    def artwork_properties(self):
        ids=self.pad.chosen()
        if not ids:self.error.setText('Select artwork first.');return
        dlg=QDialog(self);dlg.setWindowTitle('Artwork properties');v=QVBoxLayout(dlg);form=QFormLayout();v.addLayout(form);first=self.pad.symbol['primitives'][ids[0]];fields={}
        for key,label,default in [('text','Text / @parameter',''),('color','Color (#RRGGBB)', '#42cbb5')]:
            field=QLineEdit(str(first.get(key,default)));fields[key]=field;form.addRow(label,field)
        for key,label,low,high,default in [('font_size','Text size',1,72,8),('line_width','Line width',.1,20,1.5),('start','Arc start angle',-360,360,0),('sweep','Arc sweep angle',-360,360,90)]:
            field=QDoubleSpinBox();field.setRange(low,high);field.setValue(first.get(key,default));fields[key]=field;form.addRow(label,field)
        for key,label in [('bold','Bold text'),('fill','Filled artwork')]:field=QCheckBox();field.setChecked(first.get(key,False));fields[key]=field;form.addRow(label,field)
        vertices=QTableWidget(len(first['points']),2);vertices.setHorizontalHeaderLabels(['X','Y']);vertices.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for i,pt in enumerate(first['points']):
            for j,value in enumerate(pt):vertices.setItem(i,j,QTableWidgetItem(str(value)))
        if len(ids)==1:v.addWidget(QLabel('Exact vertices'));v.addWidget(vertices)
        else:v.addWidget(QLabel('Styles apply to '+str(len(ids))+' objects. Geometry stays in place.'))
        error=QLabel();error.setWordWrap(True);v.addWidget(error);buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);v.addWidget(buttons)
        def save():
            try:
                candidate=clone(self.pad.symbol)
                for i in ids:
                    item=candidate['primitives'][i]
                    for key,field in fields.items():
                        if key=='text' and item['kind']!='text':continue
                        item[key]=field.text() if isinstance(field,QLineEdit) else field.isChecked() if isinstance(field,QCheckBox) else field.value()
                    if len(ids)==1:item['points']=[[float(vertices.item(row,col).text()) for col in range(2)] for row in range(vertices.rowCount())]
                if self.pad.apply(candidate):dlg.accept()
                else:error.setText(self.error.text())
            except Exception as e:error.setText(str(e))
        buttons.accepted.connect(save);buttons.rejected.connect(dlg.reject);self._properties_dialog=dlg;dlg.fields=fields;dlg.vertices=vertices;dlg.show()
    def attributes_dialog(self):
        dlg=QDialog(self);dlg.setWindowTitle('Symbol attributes');v=QVBoxLayout(dlg);v.addWidget(QLabel('Declarative labels and exchange attributes. Use @name, @value or @parameter in text.'))
        attrs=self.pad.symbol.get('attributes',{});table=QTableWidget(len(attrs)+4,2);table.setHorizontalHeaderLabels(['Attribute','Value']);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for row,(key,value) in enumerate(attrs.items()):table.setItem(row,0,QTableWidgetItem(key));table.setItem(row,1,QTableWidgetItem(value))
        v.addWidget(table);error=QLabel();v.addWidget(error);buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);v.addWidget(buttons)
        def save():
            candidate=clone(self.pad.symbol);values={}
            for row in range(table.rowCount()):
                key=table.item(row,0).text().strip() if table.item(row,0) else ''
                if key in values:error.setText('Attribute names must be unique.');return
                if key:values[key]=table.item(row,1).text() if table.item(row,1) else ''
            candidate['attributes']=values
            if self.pad.apply(candidate):dlg.accept()
            else:error.setText(self.error.text())
        buttons.accepted.connect(save);buttons.rejected.connect(dlg.reject);self._attributes_dialog=dlg;dlg.show()
    def import_file(self):
        path,_=QFileDialog.getOpenFileName(self,'Import symbol','','Symbols (*.sym *.json)')
        if not path:return
        try:
            s=import_symbol(path,True)[0] if Path(path).suffix=='.sym' else json.loads(Path(path).read_text())
            if not self.allow_interface and {n.casefold() for n in s['pins']}=={n.casefold() for n in self.cell['ports']}:
                mapping={n:next(pin for pin in self.cell['ports'] if pin.casefold()==n.casefold()) for n in s['pins']};s['pins']={mapping[n]:pt for n,pt in s['pins'].items()};s['pin_meta']={mapping[n]:m for n,m in s.get('pin_meta',{}).items()};s['pin_order']=[mapping.get(n,n) for n in s.get('pin_order',list(s['pins']))]
            validate_symbol(s,s['pins'] if self.allow_interface else self.cell['ports']);s=geometry.enriched(s)
            for n in s['pins']:
                if n in self.pad.symbol['pin_meta']:s['pin_meta'][n]['id']=self.pad.symbol['pin_meta'][n]['id']
            self.pad.selections=set();self.pad.selection=-1;self.pad.apply(s);self.pad.fit()
        except Exception as e:self.error.setText(str(e))
    def export_file(self):
        path,_=QFileDialog.getSaveFileName(self,'Export symbol',self.cell['name']+'.sym','Xschem symbol (*.sym);;Native symbol (*.json)')
        if path:
            try:validate_symbol(self.pad.symbol,self.pad.symbol['pins']);atomic_write(path,json.dumps(self.pad.symbol,indent=2) if Path(path).suffix=='.json' else symbol_text(self.pad.symbol));self.error.setText('Exported '+Path(path).name)
            except Exception as e:self.error.setText(str(e))
