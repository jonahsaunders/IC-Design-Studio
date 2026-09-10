"""0.11 native layout workspace: commands, display profiles and hierarchy context."""
import json
from PySide6.QtCore import Qt,QTimer,QByteArray,QPointF,QRectF,QEvent
from PySide6.QtGui import QKeySequence,QColor,QShortcut
from PySide6.QtWidgets import (QWidget,QHBoxLayout,QVBoxLayout,QLabel,QComboBox,QLineEdit,
 QCheckBox,QTableWidget,QTableWidgetItem,QHeaderView,QDialog,QDialogButtonBox,QListWidget,
 QListWidgetItem,QColorDialog,QMenu,QInputDialog,QApplication,QAbstractItemView)
from .model import clone,digest,scalar,validate
from . import editor_ops
from .drawing_options import DrawingOptionsLayout

KEYMAPS={
 'Studio':{'rectangle':'','polygon':'','path':'','move':'M','copy':'C','edge':'S','vertex':'','via':'V','properties':'Q','fit':'F','measure':'K','rotate':'R','back':'Shift+R','enter':'Shift+E','leave':'Ctrl+B'},
 'Classic analog':{'rectangle':'R','polygon':'Shift+P','path':'P','move':'M','copy':'C','edge':'S','vertex':'Shift+S','via':'O','properties':'Q','fit':'F','measure':'K','rotate':'Shift+R','back':'Ctrl+R','enter':'Shift+E','leave':'Ctrl+B'},
 'KLayout-inspired':{'rectangle':'B','polygon':'P','path':'Shift+P','move':'M','copy':'C','edge':'S','vertex':'V','via':'Shift+V','properties':'Q','fit':'F','measure':'K','rotate':'R','back':'Shift+R','enter':'Shift+E','leave':'Ctrl+B'}}
for _keys in KEYMAPS.values():_keys['instance']='I'


class EditorWorkspaceMixin:
    def make_ui(self):
        self._editor_ready=False;self._edit_context=[];self._render_cache={};self._last_editor_command=None;self._routing_layer=None
        super().make_ui()
        self.layout.unselectable_layers=set();self.layout.layer_styles={};self.layout.selection_types={'shapes','instances'}
        self.layout.editor_requested.connect(lambda cmd,args:self.guard(lambda:self.editor_execute(cmd,args)))
        self.layout.installEventFilter(self)
        self.editor_options=QWidget();options=QVBoxLayout(self.editor_options);options.setContentsMargins(12,4,12,4);options.setSpacing(4);row=DrawingOptionsLayout();options.addLayout(row);self.editor_main_row=row;self._editor_compact=None
        self.editor_secondary=QWidget();self.editor_secondary_row=QHBoxLayout(self.editor_secondary);self.editor_secondary_row.setContentsMargins(0,0,0,0);options.addWidget(self.editor_secondary);self.editor_secondary.hide()
        self.editor_tool=QLabel('Select');self.editor_tool.setMinimumWidth(68);row.addWidget(self.editor_tool)
        self.editor_width=QLineEdit('0.34');self.editor_width.setMaximumWidth(70);self.editor_width.setAccessibleName('Path width in micrometres')
        self.editor_width_label=QLabel('Width µm');self.editor_width_label.setProperty('keepNext',True);row.addWidget(self.editor_width_label);row.addWidget(self.editor_width)
        self.editor_net=QComboBox();self.editor_net.setEditable(True);self.editor_net.setMinimumWidth(100);self.editor_net.setMaximumWidth(150);self.editor_net.setAccessibleName('Routing net');self.editor_net_label=QLabel('Net');self.editor_net_label.setProperty('keepNext',True);row.addWidget(self.editor_net_label);row.addWidget(self.editor_net)
        self.editor_snap=QComboBox();self.editor_snap.addItems(['Objects on','Objects off']);self.editor_snap.setAccessibleName('Layout snapping');self.editor_snap.setToolTip('Path and cursor route: snap to visible corners, edges, route centerlines and terminals. Locked objects can be used as references. Grid only disables object snapping.');row.addWidget(self.editor_snap)
        self.editor_via=QComboBox();self.editor_via.setMaximumWidth(180);self.editor_via.setAccessibleName('Via connection');row.addWidget(self.editor_via)
        self.editor_angle=QComboBox();self.editor_angle.addItems(['0°','90°','180°','270°']);self.editor_angle.setAccessibleName('Placement rotation');self.editor_angle.currentIndexChanged.connect(lambda i:(setattr(self.layout,'instance_angle',i*90),self.layout.update()));row.addWidget(self.editor_angle)
        self.editor_finish=self.button('Finish',fn=self.layout.finish_drawing);row.addWidget(self.editor_finish)
        self.editor_cancel=self.button('Cancel',fn=self.cancel_tool);row.addWidget(self.editor_cancel);row.addStretch()
        drawing_row=DrawingOptionsLayout();options.addLayout(drawing_row)
        self.editor_grid_snap=QCheckBox('Snap to grid');self.editor_grid_snap.setChecked(True);self.editor_grid_snap.setAccessibleName('Snap layout to grid')
        self.editor_grid_snap.toggled.connect(lambda enabled:self.set_grid_snap(enabled));drawing_row.addWidget(self.editor_grid_snap)
        self.editor_bends=QComboBox();self.editor_bends.addItems(['Manhattan bends','Free angle']);self.editor_bends.setAccessibleName('Path bend mode');drawing_row.addWidget(self.editor_bends)
        self.editor_flip=self.button('Flip bend',fn=self.layout.flip_path_bend,tip='Switch horizontal/vertical bend order (Tab)');drawing_row.addWidget(self.editor_flip)
        self.editor_back=self.button('Undo point',fn=self.layout.undo_drawing_point,tip='Remove the last clicked point and its automatic bend (Backspace)');drawing_row.addWidget(self.editor_back)
        self.editor_points=QLabel();drawing_row.addWidget(self.editor_points);drawing_row.addStretch()
        self.drawing_help=QLabel();self.drawing_help.setWordWrap(True);self.drawing_help.setAccessibleName('Drawing instructions');options.addWidget(self.drawing_help)
        self.editor_bends.currentIndexChanged.connect(lambda i:(setattr(self.layout,'orthogonal',i==0),self.layout.drawing_changed()))
        self.layout.draft_changed.connect(self.update_drawing_controls);self.layout.commit_shape_callback=self.commit_canvas_shape
        self.editor_finish.setToolTip('Finish at the last clicked point. Enter in the canvas finishes a path at the pointer.')
        self.centralWidget().layout().insertWidget(2,self.editor_options)
        self.editor_width.editingFinished.connect(lambda:self.guard(self.apply_editor_options))
        self.editor_snap.currentIndexChanged.connect(lambda:self.guard(self.apply_editor_options))
        self.editor_net.currentTextChanged.connect(lambda:self.guard(self.apply_editor_options))
        self.breadcrumb=QLabel();self.breadcrumb.setWordWrap(True);self.breadcrumb.setContentsMargins(12,3,12,3);self.centralWidget().layout().insertWidget(1,self.breadcrumb)
        self.breadcrumb.setTextFormat(Qt.PlainText)
        # Keep the existing layer list as a synchronized compatibility surface.
        self.layers.hide();page=self.navtabs.widget(2);v=page.layout()
        self.layer_table=QTableWidget(0,5);self.layer_table.setHorizontalHeaderLabels(['Layer / purpose','V','S','L','Fill']);self.layer_table.verticalHeader().hide();self.layer_table.setShowGrid(False)
        self.layer_table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.layer_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.layer_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        for col,width in ((1,28),(2,28),(3,28),(4,54)):self.layer_table.setColumnWidth(col,width)
        self.layer_table.setAccessibleName('Layer visibility selectability and locks');v.insertWidget(3,self.layer_table,1)
        self.layer_table.cellChanged.connect(self.editor_layer_changed);self.layer_table.cellClicked.connect(self.editor_layer_clicked);self.layer_table.cellDoubleClicked.connect(self.editor_layer_style)
        self.layer_search.textChanged.connect(self.filter_editor_layers)
        filters=QWidget();fl=QHBoxLayout(filters);fl.setContentsMargins(0,0,0,0);self.editor_filters={}
        for key,label in [('shapes','Shapes'),('instances','Cells'),('pins','Pins'),('labels','Labels')]:
            w=QCheckBox(label);w.setChecked(key in self.layout.selection_types);w.toggled.connect(self.update_editor_filters);self.editor_filters[key]=w;fl.addWidget(w)
        v.insertWidget(4,filters);self.editor_box=QComboBox();self.editor_box.addItems(['Crossing','Inside']);self.editor_box.setToolTip('Box selection: intersecting or fully enclosed objects');self.editor_box.currentTextChanged.connect(lambda text:setattr(self.layout,'box_mode',text));v.insertWidget(5,self.editor_box)
        self.finding_filter=QLineEdit();self.finding_filter.setPlaceholderText('Filter findings by rule, cell, net or message…');self.finding_filter.textChanged.connect(self.filter_editor_findings);self.results_tabs.widget(1).layout().insertWidget(1,self.finding_filter)
        self._editor_ready=True

    def adapt_tools(self):
        super().adapt_tools()
        if not getattr(self,'_editor_ready',False) or not hasattr(self,'layout_more'):return
        compact=self.toolstrip.width()<650;active=self.current_mode=='layout'
        if active and self.toolstrip.width()<950:
            for i in (2,3,4,5):self.tool_buttons[i].setText('');self.tool_buttons[i].setMinimumWidth(34)
        for i in (2,3,4):self.tool_buttons[i].setVisible(active and not compact)
        self.tool_buttons[5].setVisible(not active or not compact)
        self.layout_via_button.setVisible(active and not compact)
        self._editor_compact=False;self.editor_secondary.hide();self.fit_drawing_options()
        self.layer_table.setMinimumHeight(120 if self.height()<850 else 180)
        self.physical_tree.setMaximumHeight(80 if self.height()<850 else 200)

    def make_actions(self):
        super().make_actions();menus={a.text().replace('&',''):a.menu() for a in self.menuBar().actions() if a.menu()}
        menu=menus['Design'].addMenu('Layout editor');self._editor_menu=menu;self.editor_commands={};self.editor_key_bindings={}
        commands=[('rectangle','Rectangle',lambda:self.start_layout_tool('rect')),('polygon','Polygon',lambda:self.start_layout_tool('polygon')),
          ('path','Path',lambda:self.start_layout_tool('path')),('move','Move by reference',lambda:self.start_layout_tool('move_ref')),
          ('copy','Copy by reference',lambda:self.start_layout_tool('copy_ref')),('edge','Stretch edge',lambda:self.start_layout_tool('edge')),
          ('vertex','Edit vertex',lambda:self.start_layout_tool('vertex')),('via','Place via',lambda:self.start_layout_tool('via')),
          ('properties','Layout properties…',self.editor_properties),('fit','Fit layout',self.layout.fit),('measure','Ruler',lambda:self.start_layout_tool('ruler')),
          ('rotate','Rotate layout clockwise',lambda:self.editor_rotate(90)),('back','Rotate layout counterclockwise',lambda:self.editor_rotate(270)),
          ('enter','Edit selected cell in context',self.enter_edit_context),('leave','Return from context',self.leave_edit_context),('instance','Place physical cell…',self.editor_place_instance)]
        for key,title,fn in commands:
            action=self.action(menu,title,fn);action.setProperty('editor_title',title);self.editor_commands[key]=action
            binding=QShortcut(self.layout);binding.setContext(Qt.WidgetShortcut);binding.activated.connect(action.trigger);self.editor_key_bindings[key]=binding
        for title,fn in [('Size selected geometry…',self.editor_size),('Chop selected geometry…',self.editor_chop),('Make selected instance a cell variant…',self.editor_variant),('Resolve selected array',self.editor_resolve_array),('Flatten selected physical instances',self.editor_flatten)]:self.action(menu,title,fn)
        # Layout profiles own these keys only while the layout canvas has focus.
        for _,a in self._commands:
            if a not in self.editor_commands.values() and a.text().replace('&','') in ('Rotate clockwise','Rotate counterclockwise','Place component…','Place wire','Place net label…','Place ground','Inspect whole net','Toggle junction at pointer','Fit design'):self.layout.removeAction(a)
        self.action(menus['View'],'Library / cell / view browser…',self.editor_library)
        self.action(menus['View'],'Save named workspace…',self.save_named_workspace)
        self.action(menus['View'],'Restore named workspace…',self.restore_named_workspace)
        self.action(menus['Tools'],'Layout keyboard profile…',self.keyboard_dialog)
        self.action(menus['Help'],'Compatibility matrix',lambda:self.open_editor_doc('CAPABILITY_MATRIX_0.11.md'))
        self.repeat_action=self.action(menu,'Repeat last layout command',self.repeat_editor,'F4');self.repeat_action.setShortcutContext(Qt.WidgetShortcut);self.layout.addAction(self.repeat_action)
        self.layout_more=self.button('Edit ▾',tip='Move, copy, edge, vertex, hierarchy and geometry commands');self.layout_more.setMenu(menu);self.tool_layout.insertWidget(1,self.layout_more)
        self.layout_via_button=self.button('Via',fn=lambda:self.start_layout_tool('via'));self.tool_layout.insertWidget(2,self.layout_via_button)
        self.key_profile=self.settings.value('editor/profile','Studio');self.set_keyboard_profile(self.key_profile)
        self.load_layer_profile();self._routing_layer=self.layer_combo.currentText();self.layer_combo.currentTextChanged.connect(lambda layer:self.guard(lambda:self.editor_route_layer(layer)));QTimer.singleShot(120,self.restore_last_editor_workspace)

    def start_layout_tool(self,tool):
        if not self.idle_edit():return
        if self.current_mode!='layout':self.mode_combo.setCurrentIndex(1)
        if tool in ('move_ref','copy_ref','edge','vertex') and not self.selection:raise ValueError('Select layout objects first.')
        self.apply_editor_options(require_width=tool=='path');self.layout.cancel_gesture();self.layout.tool=tool;self._last_editor_command=lambda:self.start_layout_tool(tool)
        if tool=='via':
            if not self.editor_via.count():raise ValueError('This technology has no qualified native via stack.')
            self._via_configuration=(self.cid,self.editor_via.currentText(),self.editor_net.currentText().strip())
        self.sync_tools();self.layout.setFocus();self.layout.update()

    def repeat_editor(self):
        if self._last_editor_command:self._last_editor_command()

    def change_tool(self,index):
        super().change_tool(index)
        if getattr(self,'_editor_ready',False) and self.current_mode=='layout' and self.layout.tool!='select':
            tool=self.layout.tool;self.apply_editor_options(require_width=tool=='path');self._last_editor_command=lambda:self.start_layout_tool(tool)

    def apply_editor_options(self,*_,require_width=None):
        if not getattr(self,'_editor_ready',False):return
        if require_width is None:require_width=self.layout.tool=='path'
        if require_width:
            width=round(scalar(self.editor_width.text())*1000);editor_ops.grid(self.project,width)
            if width<=0:raise ValueError('Path width must be positive.')
            self.layout.line_width=width
        self.layout.snap_to_terminals=self.editor_snap.currentIndex()==0;self.layout.snap_target=None;self.layout.update()
        if self.layout.tool=='via':self._via_configuration=(self.cid,self.editor_via.currentText(),self.editor_net.currentText().strip())

    def update_drawing_controls(self):
        if not getattr(self,'_editor_ready',False) or not hasattr(self,'drawing_help'):return
        c=self.layout;tool=c.tool;count=len(c.drawing);path=tool=='path';polygon=tool=='polygon';drawing=path or polygon
        self.editor_bends.setVisible(path);self.editor_flip.setVisible(path);self.editor_back.setVisible(drawing);self.editor_points.setVisible(drawing)
        self.editor_bends.blockSignals(True);self.editor_bends.setCurrentIndex(0 if getattr(c,'orthogonal',True) else 1);self.editor_bends.blockSignals(False)
        self.editor_flip.setEnabled(getattr(c,'orthogonal',True));self.editor_back.setEnabled(bool(count));self.editor_points.setText(f'{count} point'+('' if count==1 else 's'))
        self.editor_finish.setEnabled(count>=(3 if polygon else 2));self.editor_finish.setText('Finish')
        instructions={'path':'Click start and bends; double-click the endpoint to create. Enter: finish at pointer · Tab: flip bend · Backspace: undo point · Esc: cancel.',
            'polygon':'Click vertices, then double-click the final vertex or choose Finish. Backspace removes a point; Esc cancels.',
            'rect':'Click opposite corners, or drag between them. Corners follow the snap grid when enabled; Esc cancels.'}
        text=instructions.get(tool,'')
        if c.drawing_notice:text=c.drawing_notice+'\n'+text
        self.drawing_help.setText(text);self.drawing_help.setVisible(bool(text));self.drawing_help.setToolTip(text)
        self.fit_drawing_options()
        if tool in instructions:self.tool_hint.setText({'path':'Path · double-click endpoint to finish · Enter finishes at pointer','polygon':'Polygon · click vertices · double-click to finish','rect':'Rectangle · click opposite corners or drag'}[tool])

    def fit_drawing_options(self):
        if not hasattr(self,'drawing_help'):return
        width=max(100,self.editor_options.width())
        self.editor_options.setFixedHeight(max(44,self.editor_options.layout().totalHeightForWidth(width)))

    def commit_canvas_shape(self,shape):
        c=self.layout;c.drawing_error=''
        try:
            if not self.idle_edit() or not self.flush_inspector():
                c.drawing_error='Finish or correct the current property edit before placing geometry.';return False
            self.apply_editor_options(require_width=shape['kind']=='path')
            if shape['kind']=='path':shape['width']=c.line_width
            if shape['layer'] in c.locked_layers:raise ValueError('Unlock the drawing layer first.')
            shape['net']=self.editor_net.currentText().strip()
            from .model import NET
            if shape['net'] and not NET.fullmatch(shape['net']):raise ValueError('Use a valid routing net name.')
            gate=getattr(c,'can_commit_shape',None)
            if gate and not gate(shape):return False
            self.add_shape(shape)
            accepted=any(s['id']==shape['id'] for s in self.cell['shapes'])
            if not accepted:c.drawing_error='The shape was not added. Correct the reported error and finish again.'
            return accepted
        except Exception as exc:
            c.drawing_error=str(exc);self.statusBar().showMessage(c.drawing_error,12000);return False

    def sync_tools(self):
        super().sync_tools()
        if not getattr(self,'_editor_ready',False):return
        active=self.current_mode=='layout';self.editor_options.setVisible(active)
        if hasattr(self,'layout_more'):self.layout_more.setVisible(active);self.layout_via_button.setVisible(active)
        tool=self.layout.tool
        for widget in (self.editor_width,self.editor_width_label):widget.setVisible(tool=='path')
        for widget in (self.editor_net,self.editor_net_label):widget.setVisible(tool in ('path','via','rect','polygon'))
        self.editor_via.setVisible(tool=='via');self.editor_angle.setVisible(tool=='instance_place')
        labels={'move_ref':'Move · click reference, then destination','copy_ref':'Copy · click reference, then destination','edge':'Stretch · drag a selected edge','vertex':'Vertex · drag a selected vertex','via':'Via · click to place · Esc exits'}
        self.editor_tool.setText(tool.replace('_ref','').title());self.editor_finish.setEnabled(tool in ('path','polygon'))
        if active and tool in labels:self.tool_hint.setText(labels[tool])
        self.update_drawing_controls();self.update_breadcrumb();self.adapt_tools()

    def refresh(self,fit=False):
        super().refresh(fit)
        if not getattr(self,'_editor_ready',False):return
        self.refresh_editor_layers();old=self.editor_net.currentText();self.editor_net.blockSignals(True);self.editor_net.clear();self.editor_net.addItem('')
        self.editor_net.addItems(sorted({n for d in self.cell['devices'] for n in d['nets'].values()}|{s.get('net','') for s in self.cell['shapes']} - {''}));self.editor_net.setCurrentText(old);self.editor_net.blockSignals(False)
        from .layout_edit import via_options
        before=self.editor_via.currentText();self.editor_via.clear()
        try:self.editor_via.addItems(list(via_options(self.project['pdk'])))
        except ValueError:pass
        if self.editor_via.findText(before)>=0:self.editor_via.setCurrentText(before)
        self.update_breadcrumb();self.filter_editor_findings()

    def render_physical_hierarchy(self):
        if not getattr(self,'_editor_ready',False):return super().render_physical_hierarchy()
        key=(id(self.project),self.project['revision'],self.cid,getattr(self.layout,'hierarchy_depth',None))
        if key in self._render_cache:
            data,schematic=self._render_cache[key];self.layout.set_data(data,self.project['pdk'],self.selection,self.net,revision=self.project['revision']);self.schematic.set_data(schematic,self.project['pdk'],self.selection,self.net)
        else:
            super().render_physical_hierarchy();self._render_cache={key:(self.layout.cell,self.schematic.cell)}
        # Cached geometry must not discard the current layout-to-schematic links.
        linked=[obj['device_id'] for obj in self.cell['shapes']+self.cell.get('layout_instances',[])
                if obj['id'] in self.selection and obj.get('device_id')] if self.current_mode=='layout' else []
        self.schematic.selection=list(dict.fromkeys(self.selection+linked));self.schematic.update()
        self.layout.selection=list(dict.fromkeys(self.selection+[i['id'] for i in self.cell.get('layout_instances',[]) if i.get('device_id') in self.selection]));self.render_edit_context();self.layout.update()

    def set_project(self,p,path=None):
        if getattr(self,'_editor_ready',False):self.save_layer_profile()
        self._edit_context=[];self._render_cache={};self._last_editor_command=None
        result=super().set_project(p,path)
        if getattr(self,'_editor_ready',False):self.load_layer_profile();self.refresh_editor_layers()
        return result

    def update_editor_filters(self):
        self.layout.selection_types={key for key,w in self.editor_filters.items() if w.isChecked()}

    def refresh_editor_layers(self):
        layers=self.project['pdk']['layers'];names=[l['name'] for l in layers]
        if hasattr(self,'layer_combo') and [self.layer_combo.itemText(i) for i in range(self.layer_combo.count())]!=names:
            current=self.layer_combo.currentText();self.layer_combo.blockSignals(True);self.layer_combo.clear();self.layer_combo.addItems(names)
            if current in names:self.layer_combo.setCurrentText(current)
            self.layer_combo.blockSignals(False);self.layout.layer=self.layer_combo.currentText();self._routing_layer=self.layout.layer
        self.layer_table.blockSignals(True);self.layer_table.setRowCount(len(layers))
        for i,l in enumerate(layers):
            name=l['name'];s=self.layout.layer_styles.get(name,{});item=QTableWidgetItem(name+'  '+str(l['gds'])+'/'+str(l['datatype']));item.setToolTip(item.text());item.setData(Qt.UserRole,name);item.setForeground(QColor(s.get('color',l['color'])));self.layer_table.setItem(i,0,item)
            for col,on,tip in [(1,name in self.layout.visible_layers,'Visible'),(2,name not in self.layout.unselectable_layers,'Selectable'),(3,name in self.layout.locked_layers,'Locked against editing')]:
                it=QTableWidgetItem();it.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable);it.setCheckState(Qt.Checked if on else Qt.Unchecked);it.setToolTip(tip);self.layer_table.setItem(i,col,it)
            it=QTableWidgetItem(s.get('pattern','Solid'));it.setToolTip('Double-click to change color and fill pattern');self.layer_table.setItem(i,4,it)
        self.layer_table.blockSignals(False);self.filter_editor_layers()

    def editor_layer_changed(self,row,col):
        if col not in (1,2,3):return
        name=self.layer_table.item(row,0).data(Qt.UserRole);on=self.layer_table.item(row,col).checkState()==Qt.Checked
        target={1:self.layout.visible_layers,2:self.layout.unselectable_layers,3:self.layout.locked_layers}[col]
        if on if col!=2 else not on:target.add(name)
        else:target.discard(name)
        self.save_layer_profile();self.layout.update()

    def editor_layer_clicked(self,row,col):
        if col in (0,4):self.layer_combo.setCurrentText(self.layer_table.item(row,0).data(Qt.UserRole));self.layout.setFocus()

    def filter_editor_layers(self,*_):
        if not hasattr(self,'layer_table'):return
        query=self.layer_search.text().lower()
        for i in range(self.layer_table.rowCount()):self.layer_table.setRowHidden(i,query not in self.layer_table.item(i,0).text().lower())

    def editor_layer_style(self,row,col):
        name=self.layer_table.item(row,0).data(Qt.UserRole);style=self.layout.layer_styles.get(name,{})
        def submit(v):
            if not QColor(v['color']).isValid():raise ValueError('Enter a valid color such as #5e9aff.')
            self.layout.layer_styles[name]={'color':QColor(v['color']).name(),'pattern':v['pattern']};self.save_layer_profile();self.refresh_editor_layers();self.layout.update()
        return self.workflow_form('Layer appearance',[('color','Color',style.get('color',next(l['color'] for l in self.project['pdk']['layers'] if l['name']==name))),('pattern','Fill pattern',[style.get('pattern','Solid')]+[s for s in ('Solid','Outline','Dense','Hatch','Cross') if s!=style.get('pattern','Solid')])],submit,'Display settings do not change process layers or the PDK lock.')

    def layer_profile_key(self):
        lock=self.project['pdk'].get('package_lock',{});return 'editor/layers/'+digest([lock.get('id',self.project['pdk']['name']),lock.get('revision',self.project['pdk']['revision'])])

    def save_layer_profile(self):
        if not getattr(self,'_editor_ready',False):return
        self.settings.setValue(self.layer_profile_key(),json.dumps({'visible':sorted(self.layout.visible_layers),'unselectable':sorted(self.layout.unselectable_layers),'locked':sorted(self.layout.locked_layers),'styles':self.layout.layer_styles}))

    def load_layer_profile(self):
        names={l['name'] for l in self.project['pdk']['layers']}
        try:d=json.loads(self.settings.value(self.layer_profile_key(),'{}'))
        except (ValueError,TypeError):d={}
        self.layout.visible_layers=set(d.get('visible',names))&names;self.layout.unselectable_layers=set(d.get('unselectable',[]))&names;self.layout.locked_layers=set(d.get('locked',[]))&names;self.layout.layer_styles=d.get('styles',{});self.layout.update()

    def set_keyboard_profile(self,name,custom=None):
        if name not in KEYMAPS and name.endswith('-inspired'):
            legacy=name;name='Classic analog'
            if custom is None and self.settings.contains('editor/custom/'+legacy):self.settings.setValue('editor/custom/'+name,self.settings.value('editor/custom/'+legacy))
        name=name if name in KEYMAPS else 'Studio';keys=dict(KEYMAPS[name])
        if custom is None:
            try:custom=json.loads(self.settings.value('editor/custom/'+name,'{}'))
            except (ValueError,TypeError):custom={}
        if set(custom)-set(keys):raise ValueError('Unknown layout command in keyboard settings.')
        keys.update(custom);used={}
        reserved={a.shortcut().toString(QKeySequence.PortableText) for _,a in self._commands if a not in self.editor_commands.values() and a.shortcutContext() in (Qt.WindowShortcut,Qt.ApplicationShortcut)}
        reserved.update(s.key().toString(QKeySequence.PortableText) for s in self.findChildren(QShortcut) if s.context() in (Qt.WindowShortcut,Qt.ApplicationShortcut))
        for command,raw in keys.items():
            value=QKeySequence(raw).toString(QKeySequence.PortableText)
            if raw and not value:raise ValueError('Invalid shortcut for '+command)
            if value and (value in reserved or value in ('F4','Esc','Escape','Tab','Return','Enter','Delete','Del','Ctrl+Z','Ctrl+S','Ctrl+O','Ctrl+N','Ctrl+Q','Ctrl+Shift+Z')):raise ValueError('This shortcut is reserved: '+value)
            if value and value in used:raise ValueError('Shortcut conflict: '+value+' ('+used[value]+' and '+command+')')
            if value:used[value]=command
        for key,a in self.editor_commands.items():
            sequence=QKeySequence(keys.get(key,''));self.editor_key_bindings[key].setKey(sequence)
            a.setText(a.property('editor_title')+('\t'+sequence.toString(QKeySequence.NativeText) if not sequence.isEmpty() else ''))
        self.key_profile=name;self.settings.setValue('editor/profile',name);self.settings.setValue('editor/custom/'+name,json.dumps(custom));self._layout_keys=keys

    def keyboard_dialog(self):
        dlg=QDialog(self);dlg.setWindowTitle('Layout keyboard profile');dlg.resize(560,600);v=QVBoxLayout(dlg);combo=QComboBox();combo.addItems(KEYMAPS);combo.setCurrentText(self.key_profile);v.addWidget(combo)
        note=QLabel('Editable workflow-inspired presets. Layout keys apply only while its canvas has focus. F4 repeats; Tab cycles overlaps.');note.setWordWrap(True);v.addWidget(note)
        table=QTableWidget(len(self.editor_commands),2);table.setHorizontalHeaderLabels(['Command','Shortcut']);table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch);v.addWidget(table)
        def populate():
            for i,(key,a) in enumerate(self.editor_commands.items()):
                item=QTableWidgetItem(a.property('editor_title'));item.setFlags(Qt.ItemIsEnabled);table.setItem(i,0,item);table.setItem(i,1,QTableWidgetItem((self._layout_keys if combo.currentText()==self.key_profile else KEYMAPS[combo.currentText()]).get(key,'')))
        populate();combo.currentTextChanged.connect(populate);error=QLabel();error.setWordWrap(True);v.addWidget(error);buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);v.addWidget(buttons)
        def accept():
            try:self.set_keyboard_profile(combo.currentText(),{key:table.item(i,1).text() for i,key in enumerate(self.editor_commands)});dlg.accept()
            except ValueError as exc:error.setText(str(exc))
        buttons.accepted.connect(accept);buttons.rejected.connect(dlg.reject);dlg.fields={'profile':combo,'table':table};self._keyboard_dialog=dlg;dlg.show();return dlg

    def editor_execute(self,command,args):
        if not self.idle_edit():return
        cid=self.cid;ids=list(self.selection);locked=self.layout.locked_layers;new=[]
        def apply(p):
            if command=='move_ref':
                from .layout_edit import selection_groups
                selection_groups(p,cid,ids,locked);editor_ops.transform_selection(p,cid,ids,args['dx'],args['dy'])
            elif command=='copy_ref':new.extend(editor_ops.copy_selection(p,cid,ids,args['dx'],args['dy'],locked))
            elif command=='vertex':editor_ops.move_vertex(p,cid,args['id'],args['index'],args['point'],args['edge'],locked)
            elif command=='instance_place':
                cfg=self._instance_config
                if cfg['parent']!=cid:raise ValueError('The active cell changed. Restart placement.')
                if cfg.get('device'):
                    from .physical_cells import place
                    i=place(p,cid,cfg['device'],args['x'],args['y'],self.editor_angle.currentIndex()*90)
                else:
                    from .model import uid
                    i={'id':uid(),'name':'P_'+uid()[:6],'cell':cfg['cell'],'x':args['x'],'y':args['y'],'rotation':self.editor_angle.currentIndex()*90,'mirror':False,'nx':1,'ny':1};editor_ops.cell(p,cid).setdefault('layout_instances',[]).append(i)
                new.append(i['id'])
        self.commit(apply,{'move_ref':'Move by reference','copy_ref':'Copy by reference','vertex':'Edit layout vertex or edge','instance_place':'Place physical cell'}[command])
        if new:self.select(new,'layout')
        if command=='instance_place' and self._instance_config.get('device'):self.cancel_tool()

    def editor_rotate(self,angle):
        if not self.idle_edit():return
        if self.layout.tool=='instance_place':self.editor_angle.setCurrentIndex((self.editor_angle.currentIndex()+angle//90)%4);return
        from .layout_edit import selection_groups
        ids=list(self.selection);cid=self.cid
        def apply(p):selection_groups(p,cid,ids,self.layout.locked_layers);editor_ops.transform_selection(p,cid,ids,rotation=angle)
        self.commit(apply,'Rotate layout selection')

    def add_shape(self,s):
        if getattr(self,'_editor_ready',False) and self.current_mode=='layout':
            if s['layer'] in self.layout.locked_layers:raise ValueError('Unlock the drawing layer first.')
            s['net']=self.editor_net.currentText().strip()
            if s['net'] and not __import__('icstudio.model',fromlist=['NET']).NET.fullmatch(s['net']):raise ValueError('Use a valid routing net name.')
        return super().add_shape(s)

    def editor_properties(self):
        cid=self.cid;ids=list(self.selection)
        if len(ids)==1 and ids[0].startswith('pin:'):
            pin=next(p for p in self.layout.cell.get('layout_pins',[]) if 'pin:'+p['id']==ids[0]);self.text_dialog('Physical terminal',json.dumps(pin,indent=2));return
        if len(ids)==1 and ids[0].startswith('text:'):
            index=int(ids[0].split(':')[1]);t=self.cell.get('layout_texts',[])[index]
            def text_apply(v):
                def edit(p):
                    c=editor_ops.cell(p,cid);old=c['layout_texts'][index]
                    if old['text'] in c['ports']:raise ValueError('Use Assign cell layout port to move or rename a port label together with its interface.')
                    if old['layer'] in self.layout.locked_layers:raise ValueError('Unlock the label layer.')
                    x,y=round(scalar(v['x'])*1000),round(scalar(v['y'])*1000);editor_ops.grid(p,x,y);old.update(text=v['text'],x=x,y=y)
                self.commit(edit,'Edit layout label')
            return self.workflow_form('Layout label',[('text','Text',t['text']),('x','X µm',t['x']/1000),('y','Y µm',t['y']/1000)],text_apply)
        if any(i['id'] in ids for i in self.cell.get('layout_instances',[])):self.reveal_properties();return
        rows=editor_ops.local_shapes(self.project,cid,ids)
        def common(key):return str(rows[0].get(key,'')) if len({s.get(key,'') for s in rows})==1 else ''
        def submit(v):
            self.commit(lambda p:editor_ops.properties(p,cid,ids,layer=v['layer'] if v['layer']!='Keep existing' else None,net=v['net'] if v['net_action']=='Set net' else None,width=round(scalar(v['width'])*1000) if v['width'].strip() else None,locked=self.layout.locked_layers),'Edit layout properties')
        return self.workflow_form('Layout properties · '+str(len(rows))+' shapes',[('layer','Layer',['Keep existing']+[l['name'] for l in self.project['pdk']['layers']]),('net_action','Net assignment',['Keep existing','Set net']),('net','Net',common('net')),('width','Path width µm (blank keeps)',str(rows[0]['width']/1000) if all(s['kind']=='path' and s['width']==rows[0].get('width') for s in rows) else '')],submit,'All changes form one undo operation. Device terminals retain their positions; verify edited device geometry.')

    def editor_size(self):
        cid=self.cid;ids=list(self.selection)
        return self.workflow_form('Size selected geometry',[('amount','Grow / shrink µm','0.1')],lambda v:self.commit(lambda p:editor_ops.replace_geometry(p,cid,ids,'size',round(scalar(v['amount'])*1000),locked=self.layout.locked_layers),'Size layout geometry'))

    def editor_chop(self):
        cid=self.cid;ids=list(self.selection)
        return self.workflow_form('Chop selected geometry',[(k,k+' µm','0' if k in ('x1','y1') else '1') for k in ('x1','y1','x2','y2')],lambda v:self.commit(lambda p:editor_ops.replace_geometry(p,cid,ids,'chop',box=[round(scalar(v[k])*1000) for k in ('x1','y1','x2','y2')],locked=self.layout.locked_layers),'Chop layout geometry'))

    def selected_physical_instance(self):
        instances=[i for i in self.cell.get('layout_instances',[]) if i['id'] in self.selection or i.get('device_id') in self.selection]
        if len(instances)!=1:raise ValueError('Select exactly one placed physical cell.')
        return instances[0]

    def editor_place_instance(self):
        if not self.idle_edit():return
        parent=self.cid;by={c['id']:c for c in self.project['cells']};placed={i.get('device_id') for i in self.cell.get('layout_instances',[])};choices={}
        for d in self.cell['devices']:
            if d['kind']=='X' and d['id'] not in placed and (by[d['cell']]['shapes'] or by[d['cell']].get('layout_instances')):choices[d['name']+' → '+by[d['cell']]['name']]={'parent':parent,'device':d['id'],'cell':d['cell']}
        from .physical_cells import reachable
        for c in self.project['cells']:
            if c['id']!=parent and (c['shapes'] or c.get('layout_instances')) and parent not in reachable(self.project,c['id'],True) and not any(by[k]['devices'] for k in reachable(self.project,c['id'],True)):choices['Geometry: '+c['name']]={'parent':parent,'cell':c['id']}
        if not choices:raise ValueError('Create a physical child cell, or generate the layout for an unplaced schematic instance first.')
        def submit(v):
            from .design_ops import flatten_layout
            self._instance_config=choices[v['cell']];self.mode_combo.setCurrentIndex(1);self.layout.instance_preview=flatten_layout(self.project,self._instance_config['cell']);self.layout.tool='instance_place';self.layout.drag=self.layout.snap(self.layout.model(self.layout.rect().center()));self._last_editor_command=self.editor_place_instance;self.sync_tools();self.tool_hint.setText('Place cell · choose rotation above · click to place · Esc cancels');self.layout.setFocus()
        return self.workflow_form('Place physical cell',[('cell','Cell / schematic instance',list(choices))],submit,'Choose an unplaced linked instance or a reusable geometry cell. Placement previews remain editable and on-grid.')

    def editor_variant(self):
        i=self.selected_physical_instance();cid=self.cid
        return self.workflow_form('Independent cell variant',[('name','New cell name',editor_ops.cell(self.project,i['cell'])['name']+'_variant')],lambda v:self.commit(lambda p:editor_ops.make_variant(p,cid,i['id'],v['name']),'Create cell variant'),'The selected physical and linked schematic instance use the new cell. Other instances keep their existing shared cell.')

    def editor_flatten(self):
        ids=list(self.selection);cid=self.cid;out=[]
        self.commit(lambda p:out.extend(editor_ops.flatten_instances(p,cid,ids,self.layout.locked_layers)),'Flatten physical instances');self.select(out,'layout')

    def editor_resolve_array(self):
        i=self.selected_physical_instance();cid=self.cid;out=[]
        self.commit(lambda p:out.extend(editor_ops.resolve_array(p,cid,i['id'])),'Resolve physical array');self.select(out,'layout')

    def editor_route_layer(self,layer):
        previous=self._routing_layer;self._routing_layer=layer
        if self.rebuilding or not previous or previous==layer or self.layout.tool!='path' or not self.layout.drawing:return
        from .layout_edit import via_options,place_via
        def restore_layer():
            self.layer_combo.blockSignals(True);self.layer_combo.setCurrentText(previous);self.layer_combo.blockSignals(False);self.layout.layer=previous;self._routing_layer=previous
        try:
            connection=next((name for name,(a,cut,b,size,pad) in via_options(self.project['pdk']).items() if {a,b}=={previous,layer}),None)
            if not connection:raise ValueError('No native via stack connects these layers. Finish the path before changing to an unrelated layer.')
        except ValueError:restore_layer();raise
        pts=[[round(pt.x()),round(pt.y())] for pt in self.layout.drawing];point=pts[-1];net=self.editor_net.currentText().strip();cid=self.cid
        def edit(p):
            if previous in self.layout.locked_layers or layer in self.layout.locked_layers:raise ValueError('Unlock the routing layers.')
            if len(pts)>1:
                from .model import uid
                editor_ops.cell(p,cid)['shapes'].append({'id':uid(),'kind':'path','layer':previous,'points':pts,'width':self.layout.line_width,'net':net,'device_id':''})
            place_via(p,cid,connection,point,net,self.layout.locked_layers)
        try:self.commit(edit,'Route layer transition with via')
        except Exception:restore_layer();raise
        self.layout.drawing=[QPointF(*point)];self.layout._drawing_undo=[];self.layout.drawing_changed();self.layout.layer=layer;self._routing_layer=layer;self.layout.tool='path';self.layout.update()

    def enter_edit_context(self):
        i=self.selected_physical_instance()
        if i.get('nx',1)!=1 or i.get('ny',1)!=1:raise ValueError('Resolve an array to an individual instance before editing in context.')
        if not self.idle_edit():return
        self._edit_context.append({'parent':self.cid,'instance':i['id'],'child':i['cell']});self.cid=i['cell'];self.selection=[];self.mode_combo.setCurrentIndex(1);self.refresh(True)

    def leave_edit_context(self):
        if not self._edit_context:return self.leave_layout_cell()
        if not self.flush_inspector():return
        frame=self._edit_context.pop();self.cid=frame['parent'];self.selection=[frame['instance']];self.refresh(True)

    def render_edit_context(self):
        self.layout.context_shapes=[]
        if not self._edit_context:return
        frame=self._edit_context[-1];parents=[c for c in self.project['cells'] if c['id']==frame['parent']]
        if self.cid!=frame['child'] or not parents:self._edit_context=[];return
        i=next((i for i in parents[0].get('layout_instances',[]) if i['id']==frame['instance'] and i['cell']==self.cid),None)
        if not i:self._edit_context=[];return
        key=(id(self.project),frame['parent'],frame['instance'])
        if getattr(self,'_context_cache_key',None)==key:self.layout.context_shapes=self._context_cache;return
        from .physical_cells import transform
        from .design_ops import flatten_layout
        from .layout import polygon,shape_from_polygon
        tr=transform(i).inverted();self._context_cache=[shape_from_polygon(polygon(s).transformed(tr),s['layer']) for s in flatten_layout(self.project,frame['parent']) if s['id']!=i['id']]
        self._context_cache_key=key;self.layout.context_shapes=self._context_cache

    def update_breadcrumb(self):
        if not hasattr(self,'breadcrumb'):return
        names={c['id']:c['name'] for c in self.project['cells']};parts=[names.get(f['parent'],'?') for f in self._edit_context]+[names.get(self.cid,'?')]
        suffix='  · editing shared cell; surrounding geometry is read-only' if self._edit_context else ''
        self.breadcrumb.setText(self.project['name']+'  /  '+'  /  '.join(parts)+suffix)

    def editor_library(self):
        dlg=QDialog(self);dlg.setWindowTitle('Library / cell / view');dlg.resize(700,410);v=QVBoxLayout(dlg);row=QHBoxLayout();lists=[]
        for title in ('Library','Cell','View'):
            col=QVBoxLayout();col.addWidget(QLabel(title));w=QListWidget();col.addWidget(w);row.addLayout(col,1);lists.append(w)
        library,cells,views=lists;library.addItem(self.project['name']);library.setCurrentRow(0)
        for c in self.project['cells']:it=QListWidgetItem(c['name']);it.setData(Qt.UserRole,c['id']);cells.addItem(it)
        cells.setCurrentRow(next(i for i,c in enumerate(self.project['cells']) if c['id']==self.cid));views.addItems(['Schematic','Layout','Symbol']);views.setCurrentRow(1 if self.current_mode=='layout' else 0);v.addLayout(row)
        def open_view():
            if not self.flush_inspector():return
            self._edit_context=[];self.cid=cells.currentItem().data(Qt.UserRole);self.selection=[]
            if views.currentRow()==2:self.refresh();self.symbol_dialog()
            else:self.mode_combo.setCurrentIndex(views.currentRow());self.refresh(True)
            dlg.accept()
        v.addWidget(self.button('Open view',fn=open_view));v.addWidget(self.button('Linked PDK device library',fn=lambda:(dlg.accept(),self.show_library())))
        views.itemDoubleClicked.connect(lambda _:open_view());dlg.fields={'library':library,'cells':cells,'views':views};self._library_browser=dlg;dlg.show();return dlg

    def save_editor_workspace(self,name):
        self.save_layer_profile();data={'state':bytes(self.saveState(3).toBase64()).decode(),'mode':self.mode_combo.currentIndex(),'splitter':self.canvases.sizes(),'filters':sorted(self.layout.selection_types),'box':self.editor_box.currentText(),'profile':self.key_profile}
        self.settings.setValue('editor/workspaces/'+name,json.dumps(data))

    def load_editor_workspace(self,name):
        raw=self.settings.value('editor/workspaces/'+name,'')
        if not raw:raise ValueError('This workspace has not been saved.')
        data=json.loads(raw);self.mode_combo.setCurrentIndex(data['mode']);self.restoreState(QByteArray.fromBase64(data['state'].encode()),3);self.canvases.setSizes(data['splitter'])
        for key,w in self.editor_filters.items():w.setChecked(key in data['filters'])
        self.editor_box.setCurrentText(data.get('box','Crossing'));self.set_keyboard_profile(data.get('profile','Studio'));self.sync_tools()

    def save_named_workspace(self):
        return self.workflow_form('Save workspace',[('name','Workspace name','Layout')],lambda v:self.save_editor_workspace(v['name'].strip()) if v['name'].strip() and '/' not in v['name'] else (_ for _ in ()).throw(ValueError('Enter a workspace name without slashes.')))

    def restore_named_workspace(self):
        self.settings.beginGroup('editor/workspaces');names=self.settings.childKeys();self.settings.endGroup()
        if not names:raise ValueError('Save a named workspace first.')
        return self.workflow_form('Restore workspace',[('name','Workspace',names)],lambda v:self.load_editor_workspace(v['name']))

    def restore_last_editor_workspace(self):
        if self.settings.contains('editor/workspaces/Last session'):self.guard(lambda:self.load_editor_workspace('Last session'))

    def closeEvent(self,event):
        super().closeEvent(event)
        if event.isAccepted():self.save_editor_workspace('Last session')

    def filter_editor_findings(self,*_):
        if not hasattr(self,'finding_filter'):return
        text=self.finding_filter.text().lower()
        for row in range(self.checks.rowCount()):self.checks.setRowHidden(row,bool(text) and text not in ' '.join(self.checks.item(row,col).text() for col in range(self.checks.columnCount()) if self.checks.item(row,col)).lower())

    def build_inspector(self):
        result=super().build_inspector()
        if getattr(self,'_editor_ready',False) and self.current_mode=='layout' and self.selection:
            if len(self.selection)>1 or any(i.startswith(('pin:','text:')) for i in self.selection):self.form.insertWidget(1,self.button('Edit layout properties…',fn=self.editor_properties))
        return result

    def eventFilter(self,obj,event):
        if obj is getattr(self,'layout',None) and event.type() in (QEvent.KeyPress,QEvent.ShortcutOverride) and event.key()==Qt.Key_Tab:
            if event.type()==QEvent.ShortcutOverride:event.accept()
            elif self.layout.tool=='path':self.layout.flip_path_bend()
            else:self.layout.editor_cycle()
            return True
        return super().eventFilter(obj,event)

    def open_editor_doc(self,name):
        from pathlib import Path
        self.text_dialog(name,(Path(__file__).resolve().parents[1]/'docs'/name).read_text())
