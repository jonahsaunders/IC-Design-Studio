"""Schematic capture commands, browser previews and hierarchy navigation."""
import json
from PySide6.QtCore import Qt,QEvent,QPointF
from PySide6.QtGui import QPainter,QPixmap,QColor
from PySide6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QLabel,QCheckBox,QMenu,QInputDialog
from .model import clone,uid,device
from .capture_keys import bindings,command_for,profile_dialog
from . import capture_ops,wiring

class CaptureWorkspaceMixin:
    def make_ui(self):
        self._capture_ready=False;self._capture_stack=[];self._capture_last=None;self._capture_anchor=None;self._capture_drag=False;self._capture_raw_transaction=False
        super().make_ui();self.schematic.capture_preview=None;self.schematic.installEventFilter(self)
        self.capture_bar=QWidget();column=QVBoxLayout(self.capture_bar);column.setContentsMargins(12,3,12,3);column.setSpacing(2);self.capture_path=QLabel();self.capture_path.setWordWrap(True);column.addWidget(self.capture_path);row=QHBoxLayout();column.addLayout(row);self.capture_repeat=QCheckBox('Repeat placement');self.capture_repeat.setChecked(self.settings.value('capture/repeat',True,type=bool));self.capture_repeat.toggled.connect(lambda value:self.settings.setValue('capture/repeat',value));row.addWidget(self.capture_repeat)
        row.addWidget(self.button('← Parent',fn=self.capture_leave));row.addWidget(self.button('Check and Save',fn=self.check_and_save));self.centralWidget().layout().insertWidget(2,self.capture_bar)
        self.capture_preview_label=QLabel();self.capture_preview_label.setMinimumHeight(100);self.capture_preview_label.setMaximumHeight(140);self.capture_preview_label.setAlignment(Qt.AlignCenter);self.navtabs.widget(1).layout().insertWidget(2,self.capture_preview_label)
        self._capture_ready=True;self.capture_profile=self.settings.value('capture/schematic/profile','Studio');self.set_capture_profile(self.capture_profile);self.capture_update()
    def make_actions(self):
        super().make_actions();menus={a.text().replace('&',''):a.menu() for a in self.menuBar().actions() if a.menu()};menu=menus['Design'].addMenu('Schematic editor');self.capture_menu=menu
        for title,fn in [('Move',lambda:self.capture_start('move')),('Stretch',lambda:self.capture_start('stretch')),('Copy',lambda:self.capture_start('copy')),('Cut wire',lambda:self.capture_start('cut')),('Rejoin two wires',self.capture_rejoin),('Mirror',self.capture_mirror),('Bulk parameters…',self.capture_properties),('Make cell from selection…',self.capture_make_cell),('Enter schematic',self.capture_enter),('Enter symbol',lambda:self.capture_enter(True)),('Return to parent',self.capture_leave),('Generate / edit active symbol',self.symbol_dialog),('Check and Save',self.check_and_save)]:self.action(menu,title,fn)
        self.action(menus['Tools'],'Schematic command profile…',self.capture_keyboard);self.capture_more=self.button('Capture ▾');self.capture_more.setMenu(menu);self.tool_layout.insertWidget(1,self.capture_more);self.more_tools.menu().addMenu(menu)
    def set_capture_profile(self,name):self.capture_profile=name;self.capture_keys=bindings(self.settings,'schematic',name);self.capture_update()
    def capture_keyboard(self):self._capture_keys_dialog=profile_dialog(self,self.settings,'schematic',self.set_capture_profile)
    def capture_update(self):
        if not getattr(self,'_capture_ready',False):return
        active=self.current_mode!='layout';self.capture_bar.setVisible(active)
        if hasattr(self,'capture_more'):self.capture_more.setVisible(active and self.toolstrip.width()>=740)
        by={c['id']:c['name'] for c in self.project['cells']};self.capture_path.setText(' / '.join([by.get(cid,'') for cid,_,_,_ in self._capture_stack]+[self.cell['name']])+' · schematic · '+self.capture_profile)
    def adapt_tools(self):
        super().adapt_tools()
        if not getattr(self,'_capture_ready',False):return
        self.capture_update()
        if self.current_mode=='schematic' and self.toolstrip.width()<560:
            self.tool_buttons[5].hide()
            self.place_button.setText('');self.place_button.setMinimumWidth(34)
    def sync_tools(self):super().sync_tools();self.capture_update()
    def refresh(self,fit=False):super().refresh(fit);self.capture_update()
    def set_project(self,project,path=None):
        self._capture_stack=[];self._capture_anchor=None
        return super().set_project(project,path)
    def capture_commit(self,fn,label):
        if not self.flush_inspector():return False
        previous=self._capture_raw_transaction;self._capture_raw_transaction=True
        try:self.commit(fn,label);return True
        finally:self._capture_raw_transaction=previous
    def eventFilter(self,obj,e):
        if obj is getattr(self,'schematic',None) and getattr(self,'_capture_ready',False):
            cmd=command_for(e,self.capture_keys)
            if cmd=='leave' and self.schematic.tool=='connect':cmd=None
            if cmd:
                if e.type()==QEvent.ShortcutOverride:e.accept();return True
                self.guard(lambda:self.capture_command(cmd));return True
            if e.type()==QEvent.KeyPress and e.key()==Qt.Key_Escape:self._capture_anchor=None;self.schematic.capture_preview=None
            if e.type()==QEvent.MouseButtonPress and e.button()==Qt.RightButton and e.modifiers()&Qt.AltModifier and self.settings.value('capture/mouse/'+self.capture_profile+'/cut',True,type=bool):
                self.guard(lambda:self.capture_cut(self.schematic.model(e.position())));return True
            if e.type()==QEvent.MouseButtonPress and e.button()==Qt.LeftButton and e.modifiers()&Qt.ControlModifier and self.schematic.tool=='select' and self.settings.value('capture/mouse/'+self.capture_profile+'/stretch',True,type=bool):
                hit=self.schematic.hit(self.schematic.model(e.position()))
                if hit and 'kind' in hit and hit['kind'] in ('R','C','L','V','I','NMOS','PMOS','X','PDK'):
                    if hit['id'] not in self.selection:self.select([hit['id']],'schematic')
                    self.capture_start('stretch');self._capture_anchor=self.schematic.snap(self.schematic.model(e.position()));self._capture_drag=True;return True
            if self.schematic.tool.startswith('capture_'):
                if e.type()==QEvent.MouseButtonPress and e.button()==Qt.LeftButton:
                    self.guard(lambda:self.capture_click(e.position()));return True
                if e.type()==QEvent.MouseMove:
                    self.capture_hover(e.position());return True
                if e.type()==QEvent.MouseButtonRelease and e.button()==Qt.LeftButton:
                    if self._capture_drag:self.guard(lambda:self.capture_click(e.position()));self._capture_drag=False
                    return True
        return super().eventFilter(obj,e)
    def capture_command(self,cmd):
        commands={'place':self.show_library,'wire':lambda:self.change_tool(1),'label':self.begin_label,'ground':lambda:self.begin_label('ground'),'move':lambda:self.capture_start('move'),'stretch':lambda:self.capture_start('stretch'),'copy':lambda:self.capture_start('copy'),'cut':lambda:self.capture_start('cut'),'properties':self.capture_properties,'rotate':self.rotate,'mirror':self.capture_mirror,'fit':self.schematic.fit,'enter':self.capture_enter,'symbol':lambda:self.capture_enter(True),'leave':self.capture_leave,'undo':self.undo,'redo':self.redo,'check':self.check_and_save,'repeat':lambda:self.capture_command(self._capture_last) if self._capture_last else None,'zoom_in':lambda:self.capture_zoom(1.2),'zoom_out':lambda:self.capture_zoom(1/1.2)}
        if cmd not in ('repeat','undo','redo'):self._capture_last=cmd
        commands[cmd]()
    def capture_zoom(self,factor):self.schematic.scale=max(.1,min(6,self.schematic.scale*factor));self.schematic.update();self.update_canvas_footer()
    def capture_start(self,command):
        if not self.flush_inspector():return
        self.mode_combo.setCurrentIndex(0)
        if command!='cut' and not self.selection:raise ValueError('Select schematic objects first.')
        self.cancel_tool();self.schematic.tool='capture_'+command;self._capture_anchor=None;self.schematic.setFocus();self.canvas_message(('Cut: click inside a wire segment.' if command=='cut' else command.title()+': click a reference point, then the destination. Esc cancels.'));self._capture_last=command
    def capture_click(self,screen):
        canvas=self.schematic;point=canvas.snap(canvas.model(screen));command=canvas.tool.removeprefix('capture_')
        if command=='cut':self.capture_cut(canvas.model(screen));return
        if self._capture_anchor is None:self._capture_anchor=point;self.canvas_message(command.title()+': choose destination.');return
        delta=point-self._capture_anchor;ids=list(self.selection);result=[]
        def edit(p):result.extend(capture_ops.transform(p,self.cid,ids,delta.x(),delta.y(),stretch=command=='stretch',copy=command=='copy'))
        if self.capture_commit(edit,command.title()+' schematic selection'):self.cancel_tool();self.select(result,'schematic')
    def capture_hover(self,screen):
        canvas=self.schematic;point=canvas.snap(canvas.model(screen));canvas.drag=point
        if self._capture_anchor is not None:
            delta=point-self._capture_anchor;key=(id(self.project),tuple(self.selection),canvas.tool,delta.x(),delta.y())
            if getattr(self,'_capture_preview_key',None)==key:return
            self._capture_preview_key=key;p={**self.project,'cells':[clone(c) if c['id']==self.cid else c for c in self.project['cells']]}
            try:
                capture_ops.transform(p,self.cid,self.selection,delta.x(),delta.y(),stretch=canvas.tool=='capture_stretch',copy=canvas.tool=='capture_copy');canvas.capture_preview=capture_ops.cell(p,self.cid);canvas.update()
            except ValueError as e:canvas.capture_preview=None;self.canvas_message(str(e))
    def cancel_tool(self):
        self._capture_drag=False;self._capture_anchor=None;self._capture_preview_key=None
        if hasattr(self,'schematic'):self.schematic.capture_preview=None
        return super().cancel_tool()
    def capture_cut(self,point):
        hit=self.schematic.hit_wire(point)
        if not hit:raise ValueError('Point at a wire segment to cut it.')
        self.capture_commit(lambda p:capture_ops.cut_wire(p,self.cid,hit[0]['id'] if isinstance(hit[0],dict) else hit[0],hit[1],[point.x(),point.y()]),'Cut schematic wire');self.canvas_message('Wire cut. Named labels still connect nets with the same name. Undo restores the cut.')
    def capture_rejoin(self):
        ids=list(self.selection);self.capture_commit(lambda p:capture_ops.rejoin(p,self.cid,ids),'Rejoin schematic wires')
    def capture_mirror(self):
        if self.schematic.placement:self.schematic.placement['mirror']=not self.schematic.placement.get('mirror',False);self.schematic.update();return
        self.capture_commit(lambda p:capture_ops.transform(p,self.cid,self.selection,mirror=True),'Mirror schematic devices')
    def place_device_at(self,x,y):
        seed=clone(self.schematic.placement);super().place_device_at(x,y)
        if seed and self.capture_repeat.isChecked():
            seed['name']=self.next_device_name(seed['kind']);self.schematic.placement=seed;self.schematic.tool='place';self.schematic.drag=QPointF(x,y);self.schematic.update();self.canvas_message('Place '+seed['name']+' · rotate / mirror before placement · Esc finishes')
    def library_selected(self,item,*args):
        super().library_selected(item,*args)
        if not hasattr(self,'capture_preview_label') or not item:return
        from .symbol_io import default_symbol,device_symbol
        from .symbol_geometry import draw
        from .catalog import create_device
        try:
            index=item.data(Qt.UserRole)
            if isinstance(index,dict):child=capture_ops.cell(self.project,index['cell']);s=child.get('symbol') or default_symbol(child['ports'])
            elif isinstance(index,int):s=device_symbol(device(['','R','C','L','V','I','NMOS','PMOS'][index],'Preview'))
            else:d=create_device(self.project['pdk'],index,'Preview');s=d.get('symbol') or device_symbol(d)
            pix=QPixmap(260,120);pix.fill(QColor('#15202c' if self.dark else '#f7f9fc'));p=QPainter(pix);p.setRenderHint(QPainter.Antialiasing);p.translate(130,60);pts=list(s['pins'].values())+[pt for item in s['primitives'] for pt in item['points']];extent=max([abs(v) for pt in pts for v in pt]+[60]);scale=50/extent;p.scale(scale,scale);draw(p,s,'#42cbb5',{'name':'Preview','symname':item.text().split('\n')[0]});p.end();self.capture_preview_label.setPixmap(pix)
        except (ValueError,KeyError,IndexError):self.capture_preview_label.clear()
    def capture_properties(self):
        ds=[d for d in self.cell['devices'] if d['id'] in self.selection]
        if len(ds)<2:self.reveal_properties();return
        def fields(d):
            keys=set(d['params']) if d['kind'] in ('NMOS','PMOS','PDK') else set(d['params'])&{'tc1','tc2'} if d['kind']=='R' else set()
            return {'params.'+key for key in keys}|({'value'} if d['kind'] in ('R','C','L','V','I') else set())
        common=fields(ds[0])
        for d in ds[1:]:common&=fields(d)
        if all(d['kind']=='X' for d in ds):
            shared=set(capture_ops.cell(self.project,ds[0]['cell']).get('parameters',{}))
            for d in ds[1:]:shared&=set(capture_ops.cell(self.project,d['cell']).get('parameters',{}))
            common|={'parameters.'+key for key in shared}
        if not common:raise ValueError('Selected models have no shared editable parameter.')
        ids=list(self.selection);cid=self.cid
        def apply(values):self.capture_commit(lambda p:capture_ops.bulk_parameters(p,cid,ids,{values['field']:values['value']}),'Bulk device parameters')
        self.workflow_form('Bulk parameters · '+str(len(ds))+' devices',[('field','Parameter',sorted(common)),('value','New value','')],apply,'One undo step. Every selected device must accept the value; PDK parameter limits still apply.')
    def capture_make_cell(self):
        name,ok=QInputDialog.getText(self,'Make cell from selection','New cell name')
        if ok:
            result=[]
            if self.capture_commit(lambda p:result.extend(capture_ops.make_cell(p,self.cid,self.selection,name.strip())),'Make reusable schematic cell'):self.select([result[1]],'schematic');self.canvas_message('Created '+name+'. Enter its schematic or symbol from the Capture menu.')
    def capture_enter(self,symbol=False):
        if not self.flush_inspector():return
        d=next((d for d in self.cell['devices'] if d['id'] in self.selection and d['kind']=='X'),None)
        if not d:
            if symbol:return self.edit_selected_symbol()
            raise ValueError('Select a reusable cell instance first.')
        if symbol:return self.open_symbol_editor(capture_ops.cell(self.project,d['cell']))
        self._capture_stack.append((self.cid,list(self.selection),self.schematic.scale,QPointF(self.schematic.offset)));self.cid=d['cell'];self.selection=[];self.mode_combo.setCurrentIndex(0);self.refresh(True)
    def capture_leave(self):
        if not self.flush_inspector() or not self._capture_stack:return
        cid,selection,scale,offset=self._capture_stack.pop()
        if not any(c['id']==cid for c in self.project['cells']):self._capture_stack=[];return
        self.cid=cid;self.selection=selection;self.refresh();self.schematic.scale=scale;self.schematic.offset=offset;self.schematic.update()
    def edit_ports(self):
        self.open_symbol_editor(self.cell);self._symbol_dialog.pin_table.setFocus()
    def open_symbol_editor(self,cell,device_id=None):
        if device_id:return super().open_symbol_editor(cell,device_id)
        from .symbol_editor import SymbolEditor
        from .symbol_geometry import enriched
        from .symbol_io import default_symbol
        cid=cell['id'];project_id=self.project['id'];base=enriched(cell.get('symbol') or default_symbol(cell['ports']));seed={**cell,'symbol':base}
        def save(s):
            if self.project['id']!=project_id:raise ValueError('Project changed while editing symbol.')
            if not self.capture_commit(lambda p:capture_ops.apply_symbol(p,cid,s,base),'Edit symbol and electrical interface'):raise ValueError('Resolve pending property edits before saving the symbol.')
        dlg=SymbolEditor(seed,self.dark,save,self,allow_interface=True);dlg.setWindowModality(Qt.WindowModal);self._symbol_dialog=dlg;dlg.show()
    def check_and_save(self):
        if not self.flush_inspector():return
        self.issues=capture_ops.findings(self.project,self.cid);self.check_revision=self.project['revision'];self.check_note.setText('Check and Save · '+str(len(self.issues))+' findings · click a row to inspect');self.fill_checks();self.results_dock.show();self.results_tabs.setCurrentIndex(1)
        if any(i['severity']=='error' for i in self.issues):self.canvas_message('Resolve electrical errors before Check and Save. File → Save can retain unfinished work.');return False
        return self.save()
    def check_selected(self,row,col):
        if row<len(self.issues) and self.check_revision==self.project['revision'] and self.issues[row].get('cell'):
            issue=self.issues[row];self.cid=issue['cell'];self.selection=[issue['object']] if issue.get('object') else [];self.mode_combo.setCurrentIndex(0);self.refresh(True);return
        return super().check_selected(row,col)
    def canvas_context(self,canvas,pos):
        if canvas.mode!='schematic':return super().canvas_context(canvas,pos)
        menu=QMenu(self);menu.addMenu(self.capture_menu);menu.addAction('Place component…',self.show_library);menu.addAction('Delete',lambda:self.guard(self.delete));menu.exec(canvas.mapToGlobal(pos))
