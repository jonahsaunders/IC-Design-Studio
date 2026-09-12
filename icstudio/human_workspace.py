"""CAD workspace: shallow menus, visible task commands and recoverable panel layouts.

This outer mixin composes existing controllers. Presentation changes never edit
the project model or bypass its property-draft and History transaction gates.
"""
import json
from PySide6.QtCore import Qt, QTimer, QSize, QRect, QPoint, QEvent
from PySide6.QtGui import QAction, QKeySequence, QPainter, QPalette
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLayout, QLabel,
    QToolButton, QTabWidget, QComboBox, QCheckBox, QSlider, QDialog,
    QDialogButtonBox, QFormLayout, QMenu, QDockWidget, QMainWindow, QSizePolicy, QScrollArea)
from .menu_map import GROUPS, ALIASES, title
from .ui_style import icon, palette
from .grid_settings import GridSettingsMixin


class ElidingLabel(QLabel):
    def paintEvent(self, event):
        painter=QPainter(self)
        painter.setPen(self.palette().color(QPalette.WindowText))
        painter.drawText(self.rect(),Qt.AlignLeft|Qt.AlignVCenter,
                         self.fontMetrics().elidedText(self.text(),Qt.ElideRight,self.width()))


class FlowLayout(QLayout):
    """Wrap named controls on narrow canvases instead of hiding or clipping them."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.setContentsMargins(8, 4, 8, 5)
        self.setSpacing(4)

    def addItem(self, item): self.items.append(item)
    def count(self): return len(self.items)
    def itemAt(self, i): return self.items[i] if 0 <= i < len(self.items) else None
    def takeAt(self, i): return self.items.pop(i) if 0 <= i < len(self.items) else None
    def expandingDirections(self): return Qt.Orientations(0)
    def hasHeightForWidth(self): return True
    def heightForWidth(self, width): return self.arrange(QRect(0, 0, width, 0), True)
    def setGeometry(self, rect): super().setGeometry(rect); self.arrange(rect, False)
    def minimumSize(self):
        return QSize(90, 60)
    def sizeHint(self): return QSize(500, 62)

    def arrange(self, rect, measure):
        left, top, right, bottom = self.getContentsMargins()
        x, y, height = rect.x()+left, rect.y()+top, 0
        for item in self.items:
            size = item.sizeHint()
            if x > rect.x()+left and x+size.width() > rect.right()-right:
                x = rect.x()+left; y += height+self.spacing(); height = 0
            if not measure: item.setGeometry(QRect(QPoint(x, y), size))
            x += size.width()+self.spacing(); height = max(height, size.height())
        return y+height+bottom-rect.y()


class HumanWorkspaceMixin(GridSettingsMixin):
    def __init__(self, *args, **kwargs):
        self._human_ready = False
        self._layout_locked = False
        super().__init__(*args, **kwargs)
        # v3 sessions are migrated by the existing delayed restoration hook.
        if not self.settings.contains('editor/workspaces/Last session'):
            self.apply_workspace_preset('Schematic')

    def make_ui(self):
        super().make_ui()
        self.canvases.setHandleWidth(5)
        self.setDockOptions(QMainWindow.AllowNestedDocks | QMainWindow.AllowTabbedDocks
                            | QMainWindow.AnimatedDocks)
        self.panel_float_buttons=[]
        for dock in self.workspace_docks():
            old = dock.titleBarWidget()
            head=QWidget();head.setObjectName('panelHeader')
            row=QHBoxLayout(head);row.setContentsMargins(12,3,5,3);row.setSpacing(2)
            caption=QLabel(dock.windowTitle());caption.setProperty('role','subtitle')
            caption.setAttribute(Qt.WA_TransparentForMouseEvents)
            row.addWidget(caption);row.addStretch()
            floating=self.button('','float',lambda dock=dock:dock.setFloating(not dock.isFloating()),tip='Float or dock '+dock.windowTitle())
            close=self.button('','close',dock.hide,tip='Hide '+dock.windowTitle()+' · restore from Window')
            for button in (floating,close):button.setFixedSize(28,28);row.addWidget(button)
            self.panel_float_buttons.append(floating)
            dock.setTitleBarWidget(head)
            from .floating_panels import FloatingPanel
            dock._floating_frame=FloatingPanel(dock,head)
            if old: old.deleteLater()
            dock.setAllowedAreas(Qt.AllDockWidgetAreas)
            dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable
                             | QDockWidget.DockWidgetFloatable)
            dock.setToolTip('Drag the title to move; double-click to float or dock. Window restores hidden panels.')
        old_hint=self.tool_hint
        self.tool_hint=ElidingLabel(old_hint.text())
        self.tool_hint.setProperty('role','muted')
        old_hint.parentWidget().layout().replaceWidget(old_hint,self.tool_hint)
        old_hint.deleteLater()
        self.tool_hint.setMinimumWidth(0)
        self.tool_hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.tool_hint.setToolTip('Select: drag to move or box-select. Middle mouse or Space + drag pans. F fits.')
        footer = self.grid_label.parentWidget().layout()
        self.grid_label.hide()
        self.grid_button = self.button('Grid', 'grid', self.grid_settings_dialog,
                                       tip='Visible grid and placement spacing for each editor')
        footer.insertWidget(footer.count()-2, self.grid_button)
        self.zoom_label.setMinimumWidth(40)
        # Each result view can scroll independently when docked into a narrow
        # panel. Its large tables/toolbars must not overlap the design inspector.
        self.results_tabs.setUsesScrollButtons(True)
        self.results_tabs.setElideMode(Qt.ElideNone)
        self.results_tabs.tabBar().setExpanding(False)
        self.result_pages=[]
        for i in range(self.results_tabs.count()):
            page=self.results_tabs.widget(i); name=self.results_tabs.tabText(i)
            self.results_tabs.removeTab(i)
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page)
            scroll.setMinimumSize(120,100)
            self.results_tabs.insertTab(i,scroll,name)
            self.result_pages.append(page)
        self.results_tabs.setCurrentIndex(0)
        for canvas in (self.schematic, self.layout):
            key = 'display/'+canvas.mode+'/'
            canvas.grid_style = self.settings.value(key+'grid_style', 'lines')
            if canvas.grid_style not in ('lines', 'dots', 'off'): canvas.grid_style = 'lines'
            canvas.grid_density = self.settings.value(key+'grid_density', 14, type=int)
            canvas.grid_contrast = self.settings.value(key+'grid_contrast', 65, type=int)
            canvas.grid_origin = self.settings.value(key+'grid_origin', True, type=bool)
            canvas.grid_major_every=max(2,min(100,self.settings.value(key+'grid_major_every',5,type=int)))
            if canvas.mode=='layout':
                canvas.grid_snap_enabled=self.settings.value(key+'grid_snap_enabled',True,type=bool)
                canvas.grid_snap_mode=self.settings.value(key+'grid_snap_mode','visible')
                if canvas.grid_snap_mode not in ('visible','fixed'):canvas.grid_snap_mode='visible'
                canvas.grid_snap_step=max(1,min(1000000000,self.settings.value(key+'grid_snap_step',5,type=int)))
            canvas.installEventFilter(self)

    def workspace_docks(self):
        return (self.nav, self.inspector, self.results_dock)

    def make_actions(self):
        super().make_actions()
        self.reorganize_menus()
        self.make_task_ribbon()
        self.make_window_commands()
        view = self.task_menus['View']
        view.addSeparator()
        self.grid_toggle_action = self.action(view, 'Show grid', self.toggle_visible_grid, 'Ctrl+Shift+G')
        self.grid_toggle_action.setCheckable(True)
        self.grid_settings_action=self.action(view,'Grid Settings…',self.grid_settings_dialog)
        self.grid_snap_action=self.action(view,'Snap to grid',self.toggle_grid_snap);self.grid_snap_action.setCheckable(True)
        self.action(view, 'Zoom in', lambda:self.zoom_active(1.25))
        self.action(view, 'Zoom out', lambda:self.zoom_active(.8))
        self.action(self.task_menus['Help'], 'Workspace guide',
                    lambda:self.open_editor_doc('GUI_OVERHAUL.md'))
        self.workspace_button = self.button('Workspace', 'split', self.configure_windows,
                                            tip='Arrange panels and choose a workspace')
        self.toolbar.insertWidget(self.toolbar.actions()[-1], self.workspace_button)
        self._human_ready = True
        self.reindex_commands()
        self.sync_tools()

    def reorganize_menus(self):
        self._legacy_menus = list(self.findChildren(QMenu))
        # PySide menuAction wrappers must outlive menus shared by multiple owners.
        self._legacy_menu_actions = [a for menu in self._legacy_menus for a in menu.actions()]
        self._legacy_menu_actions.extend(self.menuBar().actions())
        entries = []
        def visit(menu, group):
            for action in menu.actions():
                if action.isSeparator(): continue
                if action.menu(): visit(action.menu(), group+'/'+title(action))
                else: entries.append((group, action))
        for action in self.menuBar().actions(): visit(action.menu(), title(action))
        self.legacy_command_count = len(entries)
        self.command_actions = {}
        for _, action in entries: self.command_actions.setdefault(title(action), action)
        self.menuBar().clear()
        names = ['&File','&Edit','&View','&Design','&Schematic','&Layout','&Route',
                 'Si&mulate','Verif&y','&Tools','&Window','&Help']
        self.task_menus = {name.replace('&',''):self.menuBar().addMenu(name) for name in names}
        self._new_submenus = [];self._task_submenus={}
        placed = set()
        self.unmapped_commands = []
        for path, labels in GROUPS.items():
            parts = path.split('/')
            menu = self.task_menus[parts[0]]
            if len(parts) == 2:
                menu = menu.addMenu(parts[1]); self._new_submenus.append(menu);self._task_submenus[path]=menu
            for text in labels:
                action = self.command_actions.get(text)
                if action:
                    menu.addAction(action); placed.add(text)
        # Retain future extension commands visibly, with an audit in tests.
        for group, action in entries:
            text = title(action)
            if text not in placed and text not in ALIASES:
                self.task_menus.get(group.split('/')[0], self.task_menus['Tools']).addAction(action)
                placed.add(text); self.unmapped_commands.append(text)
        # Context menus continue to use the same live QAction objects.
        self.capture_menu = self.task_menus['Schematic']
        self._editor_menu = self.task_menus['Layout']
        for key, text in [('Place wire','Wire'),('Place component…','Component'),
                          ('Place net label…','Net label')]:
            self.command_actions[key].setToolTip(text+' — '+self.command_actions[key].shortcut().toString())
        # Visually separate everyday actions from specialized command families.
        for name, before in {'File':['Close project','Quit'], 'Edit':['Duplicate','Command palette…'],
            'Design':['Set active cell as top','Library / cell / view browser…'],
            'Schematic':['Move','Bulk parameters…','Enter schematic'],
            'Layout':['Move by reference','Layout properties…'],
            'Route':['Assign physical terminal…','Cut wire'],
            'Simulate':['Save / edit testbench…','Simulation runtime…'],
            'Verify':['Inspect whole net','Physical workflow']}.items():
            for text in before:
                action = self.command_actions.get(text)
                if action: self.task_menus[name].insertSeparator(action)
        self._menu_actions = list(self.menuBar().actions())
        self.command_actions['Component properties…'].setText('Cell definition properties…')
        quit_action=self.command_actions['Quit']
        self.task_menus['File'].removeAction(quit_action)
        self.task_menus['File'].addSeparator();self.task_menus['File'].addAction(quit_action)

    def reindex_commands(self):
        entries = []
        if not hasattr(self,"_menu_action_refs"):self._menu_action_refs=[]
        def visit(menu, group):
            for action in menu.actions():
                if action.isSeparator(): continue
                if action.menu(): visit(action.menu(), group+' / '+title(action))
                else: entries.append((group, action))
        for menu in list(self.task_menus.values())+self._new_submenus:
            try:
                for action in menu.actions():
                    if action not in self._menu_action_refs:self._menu_action_refs.append(action)
            except RuntimeError:pass
        for name, menu in self.task_menus.items(): visit(menu, name)
        self._commands = entries

    def ribbon_button(self, layout, text, command, glyph, tool=None):
        button = QToolButton()
        action = self.command_actions.get(command)
        if action: button.setDefaultAction(action)
        else: button.clicked.connect(lambda checked=False:self.guard(command))
        button.setText(text)
        button.setAccessibleName(text)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(22,22))
        button.setIcon(icon(glyph, palette(self.dark)['muted']))
        button.setMinimumSize(62, 54)
        button.setObjectName('taskButton')
        if action: button.setToolTip(title(action)+('  '+action.shortcut().toString() if not action.shortcut().isEmpty() else ''))
        self._icons.append((button, glyph, False))
        layout.addWidget(button)
        self.ribbon_buttons.append((button, tool))
        return button

    def make_task_ribbon(self):
        self.ribbon = QTabWidget()
        self.ribbon.setObjectName('taskRibbon')
        self.ribbon.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.ribbon_buttons = []
        self.ribbon_pages = {}
        specs = {
          'schematic': [
            ('Draw', [('Select',lambda:self.set_tool(0),'select','select'),('Component','Place component…','plus','place'),('Wire','Place wire','wire','connect'),('Net label','Place net label…','label',None),('Ground','Place ground','ground',None),('To layout',self.place_schematic_in_layout,'chip',None)]),
            ('Edit', [('Move','Move','move','capture_move'),('Stretch','Stretch','stretch','capture_stretch'),('Copy','Copy','copy','capture_copy'),('Rotate','Rotate clockwise','rotate',None),('Mirror','Mirror','mirror',None),('Cut wire','Cut wire','cut','capture_cut'),('Properties',self.reveal_properties,'inspector',None)]),
            ('Review', [('Check','Electrical rule check','check',None),('Inspect net','Inspect whole net','wire',None),('Measure',lambda:self.set_tool(5),'ruler','ruler'),('Cross-probe','Schematic / layout cross-probe…','split',None),('Symbol','Generate / edit active symbol','chip',None),('Check + save','Check and Save','save',None)])],
          'layout': [
            ('Draw', [('Select',lambda:self.set_tool(0),'select','select'),('Rectangle','Rectangle','rect','rect'),('Polygon','Polygon','polygon','polygon'),('Path','Path','path','path'),('Via','Place via','via','via'),('Autovia','Autovia…','via',None),('Cell','Place physical cell…','chip','instance_place'),('From schematic',self.place_schematic_in_layout,'chip',None)]),
            ('Edit', [('Move','Move by reference','move','move_ref'),('Copy','Copy by reference','copy','copy_ref'),('Stretch','Stretch edge','stretch','edge'),('Vertex','Edit vertex','vertex','vertex'),('Rotate','Rotate layout clockwise','rotate',None),('Align','Align layout selection…','align',None)]),
            ('Review', [('Measure','Ruler','ruler','ruler'),('Check DRC','Geometry DRC (generic rules)','check',None),('Connections','Check linked layout and show connections','wire',None),('Cross-probe','Schematic / layout cross-probe…','split',None),('Properties','Layout properties…','inspector',None)])]
        }
        for mode, pages in specs.items():
            self.ribbon_pages[mode] = []
            for name, commands in pages:
                page = QWidget(); layout = FlowLayout(page)
                for text, command, glyph, tool in commands:
                    self.ribbon_button(layout, text, command, glyph, tool)
                self.ribbon_pages[mode].append((name,page))
        self._ribbon_mode = None
        self._ribbon_tab = {'schematic':0,'layout':0}
        self.centralWidget().layout().insertWidget(1, self.ribbon)
        self.ribbon.currentChanged.connect(lambda _:self.size_ribbon())
        self.toolstrip.hide()
        # Layer choice remains visible next to the routing controls.
        self.layer_caption.setParent(self.editor_options)
        self.layer_combo.setParent(self.editor_options)
        self.layer_caption.setProperty('keepNext',True);self.editor_main_row.insertWidget(1, self.layer_caption)
        self.editor_main_row.insertWidget(2, self.layer_combo)
        self.editor_snap.setToolTip('Object snapping for paths and cursor routes. Visible objects can override the drawing grid; the target marker shows the exact feature.')
        self.capture_active.setProperty('role','badge')
        self.editor_tool.setProperty('role','badge')
        self.capture_path.hide()

    def size_ribbon(self):
        page = self.ribbon.currentWidget()
        if page:
            height = page.layout().heightForWidth(max(self.ribbon.width()-4,90))
            self.ribbon.setFixedHeight(height+self.ribbon.tabBar().sizeHint().height()+4)

    def adapt_tools(self):
        if self._human_ready:
            self.toolstrip.resize(self.canvases.width(), self.toolstrip.height())
        super().adapt_tools()
        if not self._human_ready: return
        self.toolstrip.hide()
        self.capture_path.hide()
        self.capture_parent.setVisible(bool(self._capture_stack))
        self.capture_save.hide()  # Directly available in Review.
        self.capture_repeat.setText('Repeat placement')
        self.capture_repeat.setVisible(self.schematic.tool == 'place')
        self.capture_bar.setVisible(self.current_mode=='schematic' and
                                   (self.schematic.tool!='select' or bool(self._capture_stack)))
        self.editor_finish.setVisible(self.layout.tool in ('path','polygon'))
        self.editor_cancel.setVisible(self.layout.tool!='select')
        self.editor_secondary.setVisible(self.current_mode=='layout' and self._editor_compact)
        self.breadcrumb.setVisible(bool(self._edit_context or self._capture_stack))
        self.layer_caption.setVisible(self.current_mode=='layout' and self.canvases.width()>580)
        self.layer_combo.setVisible(self.current_mode=='layout')
        self.size_ribbon()

    def sync_tools(self):
        super().sync_tools()
        if not self._human_ready: return
        mode = self.current_mode
        if mode != self._ribbon_mode:
            if self._ribbon_mode: self._ribbon_tab[self._ribbon_mode] = self.ribbon.currentIndex()
            self.ribbon.blockSignals(True)
            while self.ribbon.count(): self.ribbon.removeTab(0)
            for name,page in self.ribbon_pages[mode]: self.ribbon.addTab(page,name)
            self.ribbon.setCurrentIndex(self._ribbon_tab[mode])
            self.ribbon.blockSignals(False)
            self._ribbon_mode = mode
        active = self.layout if mode=='layout' else self.schematic
        for button,tool in self.ribbon_buttons:
            if tool:
                button.setCheckable(True); button.setChecked(active.tool==tool)
        self.update_canvas_footer()
        self.adapt_tools()

    def eventFilter(self, obj, event):
        if self._human_ready and obj in (self.schematic,self.layout):
            if event.type() in (QEvent.FocusIn,QEvent.MouseButtonPress) and self.mode_combo.currentIndex()==2:
                if self.current_mode != obj.mode:
                    if not self.flush_inspector():return super().eventFilter(obj,event)
                    self.current_mode = obj.mode
                    self.sync_tools()
        return super().eventFilter(obj,event)

    def canvas_message(self, text):
        super().canvas_message(text)
        if not text.startswith('X '): self.tool_hint.setToolTip(text)

    def update_canvas_footer(self):
        super().update_canvas_footer()
        if not hasattr(self,'grid_button'): return
        c = self.layout if self.current_mode=='layout' else self.schematic
        factor=1000 if c.mode=='layout' else 1;units='µm' if c.mode=='layout' else 'units'
        visible=getattr(c,'grid_style','lines')!='off';spacing=f'{c.grid_interval()/factor:g}'
        self.grid_button.setText(f'Grid {spacing} {units}' if visible else 'Grid hidden')
        snap=f'{c.snap_interval()/factor:g} {units}' if c.grid_snap_active() else 'off'
        self.grid_label.setText('Snap '+snap);self.grid_label.show()
        self.grid_button.setToolTip(f'Visible spacing: {spacing} {units}. Snap: {snap}. Click for Grid Settings. Hiding the grid does not disable snapping.')
        if hasattr(self,'grid_toggle_action'):self.grid_toggle_action.setChecked(visible)
        if hasattr(self,'grid_snap_action'):
            self.grid_snap_action.setEnabled(c.mode=='layout');self.grid_snap_action.setChecked(getattr(self.layout,'grid_snap_enabled',True))
        if hasattr(self,'editor_grid_snap'):
            self.editor_grid_snap.blockSignals(True);self.editor_grid_snap.setChecked(getattr(self.layout,'grid_snap_enabled',True));self.editor_grid_snap.blockSignals(False)

    def toggle_visible_grid(self):
        c = self.layout if self.current_mode=='layout' else self.schematic
        if getattr(c,'grid_style','lines')!='off':
            c._visible_grid_style=c.grid_style;c.grid_style='off'
        else:c.grid_style=getattr(c,'_visible_grid_style','lines')
        self.persist_grid(c); c.update(); self.update_canvas_footer()

    def persist_grid(self, canvas):
        for key in ('grid_style','grid_density','grid_contrast','grid_origin','grid_major_every','grid_snap_enabled','grid_snap_mode','grid_snap_step'):
            if not hasattr(canvas,key):continue
            self.settings.setValue('display/'+canvas.mode+'/'+key,getattr(canvas,key))

    def zoom_active(self, factor):
        c=self.layout if self.current_mode=='layout' else self.schematic
        center=c.rect().center(); point=c.model(center)
        c.scale=max(.00001,min(100,c.scale*factor)); c.offset=center-point*c.scale
        c.auto_fit=False; c.update(); c.view_changed.emit()

    def make_window_commands(self):
        menu=self.task_menus['Window']; menu.addSeparator()
        self.action(menu,'Configure windows…',self.configure_windows)
        self.lock_action=self.action(menu,'Lock panel positions',self.toggle_panel_lock)
        self.lock_action.setCheckable(True)
        self.action(menu,'Linked views side by side',lambda:self.arrange_linked(Qt.Horizontal))
        self.action(menu,'Linked views stacked',lambda:self.arrange_linked(Qt.Vertical))
        self.action(menu,'Device library',self.show_library)
        self.action(menu,'Layers',self.show_layers)
        self.action(menu,'Analysis setup',self.run_dialog)
        presets=menu.addMenu('Workspace presets'); self._new_submenus.append(presets)
        for name in ('Schematic','Layout','Simulation','Review'):
            self.action(presets,name,lambda name=name:self.apply_workspace_preset(name))
        for text,index in [('Schematic',0),('Layout',1),('Linked views',2)]:
            self.action(self.task_menus['View'],text,lambda index=index:self.mode_combo.setCurrentIndex(index))

    def show_layers(self, mode=None):
        if mode is not None:
            return super().show_layers(mode)
        if self.mode_combo.currentIndex()==0: self.mode_combo.setCurrentIndex(1)
        self.nav.show();self.navtabs.setCurrentIndex(2)

    def arrange_linked(self, orientation):
        if not self.flush_inspector(): return
        self.canvases.setOrientation(orientation);self.mode_combo.setCurrentIndex(2)
        self.canvases.setSizes([500,500]);self.sync_tools()

    def toggle_panel_lock(self): self.set_panel_lock(not self._layout_locked)

    def set_panel_lock(self, locked):
        self._layout_locked=bool(locked)
        features=QDockWidget.DockWidgetClosable
        if not locked: features |= QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
        for dock in self.workspace_docks(): dock.setFeatures(features)
        for button in self.panel_float_buttons:button.setEnabled(not locked)
        if hasattr(self,'lock_action'): self.lock_action.setChecked(locked)

    def apply_workspace_preset(self, name):
        if not self.flush_inspector(): return
        self._focus_panels=None
        if hasattr(self,'command_actions'):self.command_actions['Focus canvas'].setText('Focus canvas')
        self.set_panel_lock(False)
        for dock,side in zip(self.workspace_docks(),(Qt.LeftDockWidgetArea,Qt.RightDockWidgetArea,Qt.BottomDockWidgetArea)):
            dock.setFloating(False);self.addDockWidget(side,dock)
        mode={'Schematic':0,'Layout':1,'Simulation':0,'Review':2}.get(name,0)
        self.mode_combo.setCurrentIndex(mode)
        self.nav.show();self.inspector.show();self.results_dock.setVisible(name in ('Simulation','Review'))
        self.navtabs.setCurrentIndex(2 if mode==1 else 0)
        self.inspector_tabs.setCurrentIndex(1 if name=='Simulation' else 0)
        if name=='Review': self.results_tabs.setCurrentIndex(1)
        elif name=='Simulation': self.results_tabs.setCurrentIndex(0)
        self.canvases.setOrientation(Qt.Horizontal);self.canvases.setSizes([500,500])
        self.resizeDocks([self.nav,self.inspector],[260,285],Qt.Horizontal)
        self.resizeDocks([self.results_dock],[260],Qt.Vertical)
        self.sync_panel_buttons();self.sync_tools()
        self.statusBar().showMessage(name+' workspace · customize from Window',5000)

    def reset_workspace(self): self.apply_workspace_preset('Schematic')

    def configure_windows(self):
        dlg=QDialog(self);dlg.setWindowTitle('Configure windows');dlg.resize(520,380)
        v=QVBoxLayout(dlg);note=QLabel('Drag panel titles to arrange your workspace, or choose positions below.\nDouble-click a title to float a panel on another screen.')
        note.setWordWrap(True);v.addWidget(note)
        presets=QHBoxLayout()
        for name in ('Schematic','Layout','Simulation','Review'):
            presets.addWidget(self.button(name,fn=lambda name=name:(self.apply_workspace_preset(name),sync())))
        v.addLayout(presets)
        form=QFormLayout();v.addLayout(form);fields=[]
        choices=[('Left',Qt.LeftDockWidgetArea),('Right',Qt.RightDockWidgetArea),('Bottom',Qt.BottomDockWidgetArea),('Top',Qt.TopDockWidgetArea),('Floating',None)]
        for dock in self.workspace_docks():
            row=QWidget();h=QHBoxLayout(row);h.setContentsMargins(0,0,0,0)
            visible=QCheckBox('Show');visible.setAccessibleName('Show '+dock.windowTitle())
            position=QComboBox();position.setAccessibleName(dock.windowTitle()+' position')
            for label,area in choices:position.addItem(label,area)
            h.addWidget(visible);h.addWidget(position,1);form.addRow(dock.windowTitle(),row)
            fields.append((dock,visible,position))
            visible.toggled.connect(dock.setVisible)
            def move(index,dock=dock,position=position):
                self.set_panel_lock(False)
                area=position.currentData()
                if area is None:dock.setFloating(True)
                else:dock.setFloating(False);self.addDockWidget(area,dock)
            position.currentIndexChanged.connect(move)
        def sync(*_):
            from shiboken6 import isValid
            if not isValid(self):return
            for dock,visible,position in fields:
                visible.blockSignals(True);position.blockSignals(True)
                visible.setChecked(not dock.isHidden())
                area=None if dock.isFloating() else self.dockWidgetArea(dock)
                position.setCurrentIndex(next((i for i,(_,a) in enumerate(choices) if a==area),0))
                visible.blockSignals(False);position.blockSignals(False)
        sync()
        row=QHBoxLayout();row.addWidget(self.button('Save arrangement…',fn=self.save_named_workspace))
        row.addWidget(self.button('Restore saved…',fn=self.restore_named_workspace))
        row.addWidget(self.button('Reset',fn=lambda:(self.reset_workspace(),sync())));v.addLayout(row)
        for dock in self.workspace_docks():
            dock.visibilityChanged.connect(sync)
            dock.topLevelChanged.connect(sync)
            dock.dockLocationChanged.connect(sync)
        def disconnect(*_):
            for dock in self.workspace_docks():
                dock.visibilityChanged.disconnect(sync)
                dock.topLevelChanged.disconnect(sync)
                dock.dockLocationChanged.disconnect(sync)
        dlg.finished.connect(disconnect)
        buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(dlg.reject);v.addWidget(buttons)
        dlg.fields=fields;self._windows_dialog=dlg;dlg.show();return dlg

    def save_editor_workspace(self,name):
        super().save_editor_workspace(name)
        key='editor/workspaces/'+name;data=json.loads(self.settings.value(key))
        data['human']={'version':1,'vertical':self.canvases.orientation()==Qt.Vertical,
            'locked':self._layout_locked,'nav_tab':self.navtabs.currentIndex(),
            'inspector_tab':self.inspector_tabs.currentIndex(),'results_tab':self.results_tabs.currentIndex(),
            'ribbon':self.ribbon.currentIndex(),'grid':{c.mode:{k:getattr(c,k) for k in
                ('grid_style','grid_density','grid_contrast','grid_origin','grid_major_every','grid_snap_enabled','grid_snap_mode','grid_snap_step') if hasattr(c,k)} for c in (self.schematic,self.layout)}}
        self.settings.setValue(key,json.dumps(data));self.settings.sync()

    def load_editor_workspace(self,name):
        if not self.flush_inspector():return
        data=json.loads(self.settings.value('editor/workspaces/'+name,'{}'))
        human=data.get('human',{})
        self.canvases.setOrientation(Qt.Vertical if human.get('vertical') else Qt.Horizontal)
        super().load_editor_workspace(name)
        self._focus_panels=None
        self.command_actions['Focus canvas'].setText('Focus canvas')
        for widget,key in [(self.navtabs,'nav_tab'),(self.inspector_tabs,'inspector_tab'),(self.results_tabs,'results_tab'),(self.ribbon,'ribbon')]:
            index=human.get(key,widget.currentIndex())
            if 0<=index<widget.count():widget.setCurrentIndex(index)
        self.set_panel_lock(human.get('locked',False))
        for c in (self.schematic,self.layout):
            values=human.get('grid',{}).get(c.mode,{})
            for key in ('grid_style','grid_density','grid_contrast','grid_origin','grid_major_every','grid_snap_enabled','grid_snap_mode','grid_snap_step'):
                if key in values:setattr(c,key,values[key])
            self.persist_grid(c);c.update()
        self.sync_panel_buttons();self.sync_tools()

    def focus_canvas(self):
        super().focus_canvas()
        action=self.command_actions.get('Focus canvas') if hasattr(self,'command_actions') else None
        if action:action.setText('Restore panels' if self._focus_panels is not None else 'Focus canvas')

    def canvas_context(self, canvas, pos):
        if not self._human_ready:return super().canvas_context(canvas,pos)
        menu=QMenu(self)
        keys = (['Move','Copy','Rotate clockwise','Delete selection']
                if canvas.mode=='schematic' else
                ['Layout properties…','Move by reference','Copy by reference','Stretch edge','Delete selection'])
        if self.selection:
            if canvas.mode=='schematic':menu.addAction('Properties',self.reveal_properties)
            for key in keys:menu.addAction(self.command_actions[key])
            menu.addSeparator()
        else:
            keys = (['Place component…','Place wire','Place net label…','Place ground']
                    if canvas.mode=='schematic' else ['Rectangle','Polygon','Path','Place via'])
            for key in keys:menu.addAction(self.command_actions[key])
            menu.addSeparator()
        if canvas.mode=='schematic':
            child=next((d for d in self.cell['devices'] if d['id'] in self.selection and d['kind']=='X'),None)
            commands=[]
            if child:commands += [('Enter schematic','enter',self.capture_enter),('Enter symbol','symbol',lambda:self.capture_enter(True))]
            if self._capture_stack:commands.append(('Return to parent','leave',self.capture_leave))
            for title, key, callback in commands:
                shortcut=self.capture_keys.get(key,'')
                menu.addAction(title+('\t'+shortcut if shortcut else ''),lambda checked=False,fn=callback:self.guard(fn))
            if commands:menu.addSeparator()
            menu.addAction('Place schematic devices in layout…',lambda:self.guard(self.place_schematic_in_layout))
            candidates=canvas.capture_candidates(canvas.model(pos))
            if len(candidates)>1:
                overlaps=menu.addMenu('Select overlapping object')
                for obj in candidates:
                    name=obj.get('name') or ('Wire' if 'points' in obj else obj.get('text','Label'))
                    overlaps.addAction(name,lambda checked=False,ident=obj['id']:self.select([ident],'schematic'))
            menu.addSeparator()
        self._canvas_context_menu=menu
        menu.addAction('Fit design',self.fit_active)
        menu.addAction('Grid settings…',self.grid_settings_dialog)
        menu.exec(canvas.mapToGlobal(pos))
