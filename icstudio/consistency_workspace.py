"""0.13 interface reviews, check policy, occurrence navigation and capture feedback."""
from PySide6.QtCore import Qt,QPointF,QEvent,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,
 QTableWidget,QTableWidgetItem,QHeaderView,QDialogButtonBox,QLineEdit,QAbstractItemView)
from .model import clone
from . import capture_ops,electrical_rules,cross_probe

class ConsistencyWorkspaceMixin:
    def make_ui(self):
        super().make_ui();row=self.capture_bar.layout().itemAt(1).layout();self.capture_parent=row.itemAt(1).widget();self.capture_save=row.itemAt(2).widget();self.capture_active=QLabel('Select');self.capture_active.setMinimumWidth(60);row.insertWidget(0,self.capture_active)
        self.capture_finish=self.button('Finish',fn=self.schematic.finish_wire);self.capture_cancel=self.button('Cancel',fn=self.cancel_tool);row.addWidget(self.capture_finish);row.addWidget(self.capture_cancel);self.capture_update()
    def make_actions(self):
        super().make_actions();menus={a.text().replace('&',''):a.menu() for a in self.menuBar().actions() if a.menu()}
        self.action(menus['Tools'],'Electrical check rules…',self.electrical_policy_dialog);self.action(menus['Design'],'Schematic / layout cross-probe…',self.open_cross_probe)
        self.action(self.capture_menu,'Check electrical rules',lambda:self.check('erc'));self.action(self.capture_menu,'Cross-probe hierarchy…',self.open_cross_probe)
        menu=self.capture_menu.addMenu('Selection filter');self.schematic.capture_filters={'devices','wires','labels'}
        for group in ('devices','wires','labels'):
            action=menu.addAction(group.title());action.setCheckable(True);action.setChecked(True);action.toggled.connect(lambda value,group=group:self.schematic.capture_filters.add(group) if value else self.schematic.capture_filters.discard(group))
    def capture_update(self):
        super().capture_update()
        if hasattr(self,'capture_active'):
            tool=self.schematic.tool;self.capture_active.setText(tool.removeprefix('capture_').replace('_',' ').title());self.capture_finish.setVisible(tool=='connect');self.capture_cancel.setVisible(tool!='select')
            compact=self.toolstrip.width()<760;self.capture_repeat.setText('Repeat' if compact else 'Repeat placement');self.capture_repeat.setVisible(not compact or tool in ('select','place'));self.capture_parent.setText('Parent' if compact else '← Parent');self.capture_save.setText('Check + Save' if compact else 'Check and Save');self.capture_save.setVisible(not compact or tool=='select')
    def adapt_tools(self):
        super().adapt_tools()
        if hasattr(self,'check_button'):
            compact=self.toolstrip.width()<650;self.check_button.setText('' if compact else 'Check');self.check_button.setMinimumWidth(34 if compact else 0);self.check_button.setMaximumWidth(34 if compact else 16777215)
    def eventFilter(self,obj,e):
        if obj is getattr(self,'schematic',None) and self.schematic.tool=='select':
            if e.type() in (QEvent.KeyPress,QEvent.ShortcutOverride) and e.key()==Qt.Key_Tab and not e.modifiers():
                if e.type()==QEvent.ShortcutOverride:e.accept()
                elif getattr(self.schematic,'editor_pointer',None) is not None:self.schematic.capture_cycle(self.schematic.editor_pointer)
                return True
            if e.type()==QEvent.MouseButtonPress and e.button()==Qt.LeftButton and e.modifiers()&Qt.AltModifier:self.schematic.capture_cycle(self.schematic.model(e.position()));return True
        if obj is getattr(self,'schematic',None) and e.type() in (QEvent.KeyPress,QEvent.MouseButtonPress):QTimer.singleShot(0,self.capture_update)
        return super().eventFilter(obj,e)
    def capture_start(self,command):super().capture_start(command);self.capture_update()
    def place_device_at(self,x,y):super().place_device_at(x,y);self.capture_update()
    def open_symbol_editor(self,cell,device_id=None):
        if device_id:return super().open_symbol_editor(cell,device_id)
        from .symbol_editor import SymbolEditor
        from .symbol_geometry import enriched
        from .symbol_io import default_symbol
        from .interface_ui import InterfaceReview
        cid=cell['id'];project_id=self.project['id'];base=enriched(cell.get('symbol') or default_symbol(cell['ports']));seed={**cell,'symbol':base}
        def save(s):
            if self.project['id']!=project_id:raise ValueError('Project changed while editing the symbol.')
            current=capture_ops.cell(self.project,cid)
            if current['ports']!=cell['ports'] or (current.get('symbol') or default_symbol(current['ports']))!=(cell.get('symbol') or default_symbol(cell['ports'])):raise ValueError('This cell interface changed while the editor was open. Reopen the editor to use the latest definition.')
            changed=s['pin_order']!=base['pin_order'] or set(s['pins'])!=set(base['pins'])
            if changed:
                def done():dlg.saved=True;dlg.accept()
                self._interface_review=InterfaceReview(self,cid,s,base,done);self._interface_review.show();return False
            if not self.capture_commit(lambda p:capture_ops.apply_symbol(p,cid,s,base),'Edit symbol'):raise ValueError('Resolve pending property edits before saving.')
        dlg=SymbolEditor(seed,self.dark,save,self,allow_interface=True);dlg.setWindowModality(Qt.WindowModal);self._symbol_dialog=dlg;dlg.show()
    def check(self,typ):
        if typ!='erc':return super().check(typ)
        if not self.flush_inspector():return
        self.issues=electrical_rules.check(self.project,self.cid);self.check_revision=self.project['revision'];self.check_note.setText(str(len(self.issues))+' electrical findings · '+self.project.get('electrical_rules',{}).get('scope','hierarchy')+' · click a row to inspect');self.fill_checks();self.results_dock.show();self.results_tabs.setCurrentIndex(1)
    def electrical_policy_dialog(self):
        dlg=QDialog(self);dlg.setWindowTitle('Electrical check rules');dlg.resize(630,610);v=QVBoxLayout(dlg);scope=QComboBox();scope.addItem('Active cell and its schematic hierarchy','hierarchy');scope.addItem('All project cells','project');scope.setCurrentIndex(scope.findData(self.project.get('electrical_rules',{}).get('scope','hierarchy')));v.addWidget(scope);table=QTableWidget(len(electrical_rules.DEFAULTS),2);table.setHorizontalHeaderLabels(['Rule','Severity']);table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch);v.addWidget(table);current=electrical_rules.validate_policy(self.project.get('electrical_rules',{}));fields={}
        for i,(code,title) in enumerate(electrical_rules.LABELS.items()):
            it=QTableWidgetItem(title+' · '+code);it.setFlags(it.flags()&~Qt.ItemIsEditable);table.setItem(i,0,it);combo=QComboBox();combo.addItems(['off','warning','error']);combo.setCurrentText(current[code]);table.setCellWidget(i,1,combo);fields[code]=combo
        note=QLabel('Rules travel with this project and apply to F6 and Check and Save. Optional terminals can be marked in the symbol editor. These checks complement physical DRC and extracted LVS.');note.setWordWrap(True);v.addWidget(note);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);v.addWidget(buttons);buttons.rejected.connect(dlg.reject)
        def save():
            policy={'scope':scope.currentData(),'rules':{code:field.currentText() for code,field in fields.items()}}
            if self.capture_commit(lambda p:p.update(electrical_rules=policy),'Configure electrical checks'):dlg.accept();self.check('erc')
        buttons.accepted.connect(lambda:self.guard(save));dlg.fields=fields;dlg.scope=scope;self._electrical_policy=dlg;dlg.show()
    def navigate_occurrence(self,row,layout=False):
        if not self.flush_inspector():return False
        root=row['root'];cid=root;stack=[]
        for did in row.get('path',[]):
            c=capture_ops.cell(self.project,cid);d=next(d for d in c['devices'] if d['id']==did and d['kind']=='X');stack.append((cid,[did],1.,QPointF(40,50)));cid=d['cell']
        if cid!=row['cell']:raise ValueError('The selected hierarchy occurrence changed. Refresh the list.')
        self.cancel_tool();self._capture_stack=stack;self._edit_context=[];self._layout_navigation=[entry[0] for entry in stack];self.cid=cid;ids=row.get('physical',[]) if layout else ([row['object']] if row.get('object') else row.get('objects',[]));self.selection=list(ids);self.mode_combo.setCurrentIndex(1 if layout else 0);self.refresh(True);self.select(ids,'layout' if layout else 'schematic');self.net=row.get('net','');canvas=self.layout if layout else self.schematic;canvas.net=self.net
        target=None
        if not layout and row.get('object'):
            d=next((d for d in self.cell['devices'] if d['id']==row['object']),None)
            if d:
                from .interchange import pin_positions
                target=pin_positions(d).get(row.get('pin'),[d['x'],d['y']])
        if not layout and target is None and row.get('pin'):target=self.cell.get('symbol',{}).get('pins',{}).get(row['pin'])
        if target is not None:canvas.scale=max(canvas.scale,.8);canvas.offset=QPointF(canvas.width()/2,canvas.height()/2)-QPointF(*target)*canvas.scale
        canvas.update();self.update_canvas_footer();return True
    def check_selected(self,row,col):
        if row<len(self.issues) and self.check_revision==self.project['revision'] and self.issues[row].get('root'):
            self.navigate_occurrence(self.issues[row],self.issues[row]['code'].startswith('LAYOUT.'));self.canvas_message(self.issues[row]['message']);return
        return super().check_selected(row,col)
    def open_cross_probe(self):
        if not self.flush_inspector():return
        dlg=QDialog(self);dlg.setWindowTitle('Schematic / layout cross-probe');dlg.resize(940,590);v=QVBoxLayout(dlg);root=self.cid;project_id=self.project['id'];bar=QHBoxLayout();v.addLayout(bar);mode=QComboBox();mode.addItems(['Instances','Net occurrences']);bar.addWidget(mode);net=QComboBox();net.addItems(sorted({n for d in self.cell['devices'] for n in d['nets'].values()}));bar.addWidget(net);search=QLineEdit();search.setPlaceholderText('Filter path, status or terminal…');bar.addWidget(search,1);refresh=QPushButton('Refresh');bar.addWidget(refresh)
        table=QTableWidget(0,3);table.setHorizontalHeaderLabels(['Hierarchy occurrence','Physical status / local net','Missing terminals']);table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection);v.addWidget(table);note=QLabel();note.setWordWrap(True);v.addWidget(note);buttons=QHBoxLayout();v.addLayout(buttons);state={}
        def update(*_):
            try:
                if self.project['id']!=project_id:raise ValueError('Project changed. Reopen cross-probing for the current project.')
                state.update(rows=cross_probe.occurrences(self.project,root) if mode.currentIndex()==0 else cross_probe.net_occurrences(self.project,root,net.currentText()),revision=self.project['revision']);table.setRowCount(len(state['rows']))
                for i,row in enumerate(state['rows']):
                    for j,text in enumerate((row['name'],row.get('status',row.get('net','')),', '.join(row.get('missing_pins',[])))):table.setItem(i,j,QTableWidgetItem(text))
                filter_rows();note.setText('Select an occurrence to open its shared cell definition. Connection guidance checks real conductor contact in that cell.');net.setEnabled(mode.currentIndex()==1)
            except ValueError as e:note.setText(str(e));state.clear();table.setRowCount(0)
        def filter_rows(*_):
            for i in range(table.rowCount()):table.setRowHidden(i,search.text().casefold() not in ' '.join(table.item(i,j).text() for j in range(3)).casefold())
        def chosen():
            if self.project['id']!=project_id or state.get('revision')!=self.project['revision']:raise ValueError('Design changed. Refresh the occurrence list.')
            row=table.currentRow()
            if row<0:raise ValueError('Select an occurrence first.')
            return state['rows'][row]
        def act(action):
            try:
                row=chosen()
                if not self.navigate_occurrence(row,action!='schematic'):return
                if action=='guidance':
                    from .physical import connectivity
                    result=connectivity(self.project,self.cid);self.layout.connection_guides=[g for g in result['guides'] if not row.get('net') or g['net']==row['net']];self.layout.update();note.setText(str(len(result['issues']))+' connection finding(s), '+str(len(self.layout.connection_guides))+' guide(s). '+('; '.join(i['message'] for i in result['issues'][:3]) or 'Assigned terminals are connected.'))
                elif action=='place':
                    d=next(d for d in self.cell['devices'] if d['id']==row.get('object'))
                    if row.get('physical'):raise ValueError('This occurrence already has physical geometry. Open Layout to inspect it.')
                    if d['kind']=='X':
                        from .physical_cells import ports
                        from .design_ops import flatten_layout
                        child=capture_ops.cell(self.project,d['cell'])
                        if not child['shapes'] and not child.get('layout_instances'):raise ValueError('Create the child layout before placing this instance.')
                        if {r['name'] for r in ports(self.project,d['cell'])}!=set(child['ports']):raise ValueError('Assign every child physical port before placement.')
                        self._instance_config={'parent':self.cid,'device':d['id'],'cell':d['cell']};self.layout.instance_preview=flatten_layout(self.project,d['cell']);self.layout.tool='instance_place';self.layout.drag=self.layout.snap(self.layout.model(self.layout.rect().center()));self.sync_tools();dlg.hide();self.layout.setFocus()
                    elif d['kind'] in ('NMOS','PMOS','PDK'):self.select([d['id']],'schematic');self.mos_layout_dialog()
                    else:raise ValueError('Draw or import this device footprint, then assign its physical terminals using the layout tools.')
                else:note.setText(row['name']+' · '+('local net '+row['net'] if 'net' in row else row['status']))
            except (ValueError,StopIteration) as e:note.setText(str(e) or 'Choose an instance occurrence.')
        for title,key in [('Schematic','schematic'),('Layout','layout'),('Connection guidance','guidance'),('Place missing instance…','place')]:b=QPushButton(title);buttons.addWidget(b);b.clicked.connect(lambda _,key=key:act(key))
        refresh.clicked.connect(update);mode.currentIndexChanged.connect(update);net.currentTextChanged.connect(update);search.textChanged.connect(filter_rows);table.cellDoubleClicked.connect(lambda *_:act('schematic'));dlg.table=table;dlg.mode=mode;dlg.net=net;dlg.state=state;dlg.act=act;dlg.refresh_rows=update;self._cross_probe=dlg;update();dlg.show()
