"""Document-focused Qt workspace. UI state is separate from design transactions."""
from __future__ import annotations
import json, math, sys
from pathlib import Path
from PySide6.QtCore import Qt, QSize, QPointF, QTimer, QEvent, QObject
from PySide6.QtGui import QAction, QKeySequence, QShortcut, QColor, QPalette
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QToolButton, QToolBar, QComboBox, QSplitter, QDockWidget,
    QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem, QTabWidget, QTabBar,
    QScrollArea, QLineEdit, QPlainTextEdit, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QProgressBar, QCheckBox, QMenu, QDialog,
    QDialogButtonBox, QSizePolicy, QButtonGroup, QStackedWidget, QDoubleSpinBox)
from .model import clone, device, uid, digest, design_digest, scalar, validate, flatten
from .canvas import Canvas
from .plot import WavePlot, COLORS
from .ui_style import icon, palette, stylesheet, apply_native_window_theme
from . import __version__

DEVICE_NAMES={'R':'Resistor','C':'Capacitor','L':'Inductor','V':'Voltage source','I':'Current source','NMOS':'NMOS transistor','PMOS':'PMOS transistor','X':'Cell instance','PDK':'PDK device','XS':'Xschem component','SPICE':'Native SPICE component'}
DEVICE_ICONS={'R':'resistor','C':'capacitor','L':'inductor','V':'voltage','I':'current','NMOS':'chip','PMOS':'chip','X':'cell','PDK':'chip','XS':'chip','SPICE':'chip'}
ANALYSES={'tran':'Transient','op':'Operating point','dc':'DC sweep','ac':'AC response','noise':'Noise','study':'Study','post_layout':'Post-layout estimate','connectivity':'Physical connectivity','parasitics':'Capacitance estimate','drc':'Geometry DRC','deck':'SPICE testbench'}
ANALYSES['xschem']='Xschem program'
ANALYSES['program']='Native simulation program'

def device_description(d):
    info=d.get('native_spice')
    return ('Simulation program' if info['type']=='program' else info['label']) if info else DEVICE_NAMES[d['kind']]

def label(text='',role=None):
    w=QLabel(text)
    if role:w.setProperty('role',role)
    return w

def box(vertical=True, margins=(0,0,0,0), spacing=8, name=None):
    w=QWidget()
    if name:w.setObjectName(name)
    l=QVBoxLayout(w) if vertical else QHBoxLayout(w);l.setContentsMargins(*margins);l.setSpacing(spacing)
    return w,l

class Section(QWidget):
    """A keyboard-operable disclosure with remembered expansion per section."""
    def __init__(self,title,expanded=True,on_toggle=None):
        super().__init__();v=QVBoxLayout(self);v.setContentsMargins(0,0,0,0);v.setSpacing(4)
        self.button=QToolButton();self.button.setObjectName('sectionHeader');self.button.setText(title);self.button.setCheckable(True);self.button.setChecked(expanded);self.button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon);self.button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow);self.button.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed);self.button.setAccessibleName(title+' section');v.addWidget(self.button)
        self.body=QWidget();self.form=QFormLayout(self.body);self.form.setContentsMargins(2,4,2,10);self.form.setSpacing(9);self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow);self.form.setLabelAlignment(Qt.AlignLeft|Qt.AlignVCenter);v.addWidget(self.body);self.body.setVisible(expanded)
        def toggle(on):
            self.body.setVisible(on);self.button.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
            if on_toggle:on_toggle(on)
        self.button.toggled.connect(toggle)

class WindowThemeFilter(QObject):
    def __init__(self, parent):
        super().__init__(parent);self.dark=True
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Show and isinstance(obj,QWidget) and obj.isWindow():
            apply_native_window_theme(obj,self.dark)
        return False

class WorkspaceMixin:
    def __init__(self,*args,**kwargs):
        self._icons=[];self._commands=[];self._sections={};self._inspector_dirty=False;self._building_inspector=False;self._view_state={};self._active_view_key=None;self._focus_panels=None;self._selection_guard=False;self._job_state='idle'
        super().__init__(*args,**kwargs)
        self.setMinimumSize(1000,680);self.resize(1440,900)
        geometry=self.settings.value('workspace/v2/geometry')
        if geometry:self.restoreGeometry(geometry)
        from .window_geometry import keep_visible
        keep_visible(self)
        QApplication.instance().screenRemoved.connect(self.recover_window_geometry)
        state=self.settings.value('workspace/v2/state')
        if state:self.restoreState(state,2)
        self.results_dock.hide();self.sync_panel_buttons()

    def recover_window_geometry(self,*_):
        from .window_geometry import keep_visible
        QTimer.singleShot(0,lambda:keep_visible(self))

    def button(self,text,icon_name=None,fn=None,role=None,tip=None,check=False):
        w=QPushButton(text);w.setCheckable(check);w.setCursor(Qt.PointingHandCursor);w.setAccessibleName(text or tip or icon_name)
        if role:w.setProperty('role',role)
        if icon_name:self._icons.append((w,icon_name,role=='primary'));w.setIcon(icon(icon_name,'#ffffff' if role=='primary' else palette(self.dark)['muted']));w.setIconSize(QSize(18,18))
        if tip:w.setToolTip(tip)
        if fn:w.clicked.connect(lambda checked=False:self.guard(fn))
        return w

    def panel(self,title,name,side,body):
        dock=QDockWidget(title,self);dock.setObjectName(name);dock.setAllowedAreas(Qt.LeftDockWidgetArea|Qt.RightDockWidgetArea if side!=Qt.BottomDockWidgetArea else Qt.BottomDockWidgetArea)
        head,hl=box(False,(14,6,8,6),5,'panelHeader');hl.addWidget(label(title,'subtitle'));hl.addStretch();close=self.button('','close',dock.hide,tip='Hide '+title);close.setFixedSize(28,28);hl.addWidget(close);dock.setTitleBarWidget(head);dock.setWidget(body);self.addDockWidget(side,dock);return dock

    def make_ui(self):
        self.toolbar=QToolBar('Workspace',self);self.toolbar.setMovable(False);self.toolbar.setObjectName('workspaceToolbar');self.addToolBar(self.toolbar)
        # Document header and contextual tools stay with the canvas.
        center,cv=box(True,spacing=0)
        doc,dh=box(False,(14,0,12,0),12,'documentBar');self.cell_combo=QComboBox();self.cell_combo.setMinimumWidth(105);self.cell_combo.setMaximumWidth(180);self.cell_combo.setAccessibleName('Active cell');self.cell_combo.currentIndexChanged.connect(self.switch_cell_combo);dh.addWidget(self.cell_combo)
        self.mode_combo=QTabBar();self.mode_combo.setDocumentMode(True);self.mode_combo.setExpanding(False)
        for title in ('Schematic','Layout','Linked views'):self.mode_combo.addTab(title)
        self.mode_combo.setAccessibleName('Editor views');self.mode_combo.currentChanged.connect(self.change_mode);dh.addWidget(self.mode_combo);dh.addStretch();self.revision_label=label('','muted');dh.addWidget(self.revision_label);cv.addWidget(doc)
        self.toolstrip,self.tool_layout=box(False,(10,6,10,6),3,'toolStrip');cv.addWidget(self.toolstrip)
        self.schematic=Canvas('schematic');self.layout=Canvas('layout');self.canvases=QSplitter();self.canvases.setHandleWidth(1);self.canvases.addWidget(self.schematic);self.canvases.addWidget(self.layout);self.layout.hide();cv.addWidget(self.canvases,1)
        for canvas in (self.schematic,self.layout):
            canvas.selected.connect(lambda ids,c=canvas:self.select(ids,c.mode));canvas.move_objects.connect(lambda ids,x,y,c=canvas:self.move(ids,x,y,c.mode));canvas.message.connect(self.canvas_message);canvas.connect_pins.connect(self.connect);canvas.shape_added.connect(self.add_shape)
            canvas.placement_requested.connect(self.place_device_at);canvas.tool_cancelled.connect(self.cancel_tool);canvas.context_requested.connect(lambda pos,c=canvas:self.canvas_context(c,pos));canvas.inspect_requested.connect(self.reveal_properties);canvas.view_changed.connect(self.update_canvas_footer)
        foot,fl=box(False,(14,4,10,4),8,'canvasFooter');self.tool_hint=label('Select · click an object to edit','muted');fl.addWidget(self.tool_hint,1);self.grid_label=label('10 unit grid','muted');fl.addWidget(self.grid_label);self.zoom_label=label('100%','muted');fl.addWidget(self.zoom_label);self.fit_button=self.button('Fit','fit',self.fit_active,tip='Fit design (F)');fl.addWidget(self.fit_button);cv.addWidget(foot)
        self.setCentralWidget(center)
        # Navigation separates document hierarchy from the objects in the active cell.
        navbody,nv=box(True,spacing=0,name='sidebarBody');self.navtabs=QTabWidget();nv.addWidget(self.navtabs)
        project,pv=box(True,(10,8,10,12),8,'sidebarBody');self.project_search=QLineEdit();self.project_search.setPlaceholderText('Find a cell or component…');self.project_search.setClearButtonEnabled(True);self.project_search.setAccessibleName('Search project');self.project_search.textChanged.connect(self.filter_navigation);pv.addWidget(self.project_search)
        self.tree=QTreeWidget();self.tree.setObjectName('projectTree');self.tree.setHeaderHidden(True);self.tree.setIndentation(15);self.tree.setUniformRowHeights(True);self.tree.setMinimumHeight(135);self.tree.setMaximumHeight(300);self.tree.itemClicked.connect(self.tree_clicked);self.tree.itemActivated.connect(self.tree_clicked);pv.addWidget(self.tree)
        title,tl=box(False,spacing=0);tl.addWidget(label('COMPONENTS','section'));tl.addStretch();tl.addWidget(self.button('','plus',self.show_library,tip='Place a component'));pv.addWidget(title)
        self.outline=QListWidget();self.outline.setObjectName('outline');self.outline.setSelectionMode(QAbstractItemView.ExtendedSelection);self.outline.itemSelectionChanged.connect(self.outline_selected);self.outline.itemDoubleClicked.connect(lambda _:self.reveal_properties());pv.addWidget(self.outline,1)
        self.nav_empty=label('No components yet.\nUse Place to add your first device.','muted');self.nav_empty.setWordWrap(True);pv.addWidget(self.nav_empty)
        self.tech_name=label('','subtitle');pv.addWidget(self.tech_name);self.tech_detail=label('Generic models · unqualified','muted');self.tech_detail.setWordWrap(True);pv.addWidget(self.tech_detail);pv.addWidget(self.button('Technology settings','settings',self.pdk_status))
        self.navtabs.addTab(project,'Project')
        library,lv=box(True,(12,12,12,12),10);self.library_search=QLineEdit();self.library_search.setPlaceholderText('Search devices…');self.library_search.setClearButtonEnabled(True);self.library_search.setAccessibleName('Search devices');lv.addWidget(self.library_search);self.library_list=QListWidget();self.library_list.setIconSize(QSize(28,28));lv.addWidget(self.library_list,1)
        for i,(kind,desc) in enumerate([('R','Resistance · Ω'),('C','Capacitance · F'),('L','Inductance · H'),('V','DC, pulse or sine'),('I','DC, pulse or sine'),('NMOS','Generic n-channel model'),('PMOS','Generic p-channel model')],1):
            it=QListWidgetItem(DEVICE_NAMES[kind]+'\n'+desc);it.setData(Qt.UserRole,i);it.setData(Qt.UserRole+1,kind);it.setSizeHint(QSize(190,62));it.setIcon(icon(DEVICE_ICONS[kind]));self.library_list.addItem(it)
        self.library_list.setCurrentRow(0);self.library_search.textChanged.connect(self.filter_library);self.library_list.itemDoubleClicked.connect(lambda it:self.begin_placement(it.data(Qt.UserRole)));self.place_library_button=self.button('Place component','plus',lambda:self.begin_placement(self.library_list.currentItem().data(Qt.UserRole)) if self.library_list.currentItem() else None,role='primary');lv.addWidget(self.place_library_button);note=label('Choose a device, then click the canvas to place it. Esc cancels.','muted');note.setWordWrap(True);lv.addWidget(note);self.navtabs.addTab(library,'Devices')
        layers,layv=box(True,(12,12,12,12),10);layv.addWidget(label('VISIBLE LAYERS','section'));self.layers=QListWidget();self.layers.itemChanged.connect(self.layer_changed);self.layers.itemClicked.connect(lambda it:self.layer_combo.setCurrentText(it.text()));layv.addWidget(self.layers,1);layv.addWidget(label('Click a layer to draw on it.','muted'));self.navtabs.addTab(layers,'Layers');self.navtabs.setTabEnabled(2,False)
        self.nav=self.panel('Project','navigator',Qt.LeftDockWidgetArea,navbody);self.nav.setMinimumWidth(210)
        # Properties and analysis share a predictable trailing panel.
        self.inspector_tabs=QTabWidget();self.form_host=QWidget();self.form=QVBoxLayout(self.form_host);self.form.setContentsMargins(16,16,16,18);self.form.setSpacing(12);self.form.setAlignment(Qt.AlignTop);self.inspector_scroll=QScrollArea();self.inspector_scroll.setWidgetResizable(True);self.inspector_scroll.setWidget(self.form_host);self.inspector_tabs.addTab(self.inspector_scroll,'Properties');self.analysis_page=self.make_analysis_panel();self.inspector_tabs.addTab(self.analysis_page,'Analysis');self.inspector=self.panel('Inspector','inspector',Qt.RightDockWidgetArea,self.inspector_tabs);self.inspector.setMinimumWidth(280)
        # Results open on demand and occupy only the center column.
        self.results_tabs=QTabWidget();self.results_dock=self.panel('Results','results',Qt.BottomDockWidgetArea,self.results_tabs);self.results_dock.setMinimumHeight(240)
        wave,wv=box(True,(12,4,12,6),6);bar,bl=box(False,spacing=10);self.run_combo=QComboBox();self.run_combo.setMinimumWidth(170);self.run_combo.setMaximumWidth(270);self.run_combo.currentIndexChanged.connect(self.select_run);bl.addWidget(self.run_combo);self.compare_check=QCheckBox('Compare previous');self.compare_check.toggled.connect(self.update_plot);bl.addWidget(self.compare_check);bl.addStretch();self.result_status=label('No analysis yet','muted');bl.addWidget(self.result_status);wv.addWidget(bar)
        split=QSplitter();split.setHandleWidth(1);self.traces=QListWidget();self.traces.setMinimumWidth(85);self.traces.setMaximumWidth(130);self.traces.itemChanged.connect(self.update_plot);self.traces.itemClicked.connect(self.trace_selected);self.plot=WavePlot();self.plot.cursor_changed.connect(lambda t:self.cursor_label.setText(t));split.addWidget(self.traces);split.addWidget(self.plot);wv.addWidget(split,1);self.cursor_label=label('Click to measure. Right-click to set a second cursor.','muted');self.cursor_label.setWordWrap(True);wv.addWidget(self.cursor_label);self.results_tabs.addTab(wave,'Waveforms')
        checks,cl=box(True,(12,8,12,8),8);self.check_note=label('Run a check to see findings for this cell.','muted');self.check_note.setWordWrap(True);cl.addWidget(self.check_note);self.checks=QTableWidget(0,4);self.checks.setHorizontalHeaderLabels(['Severity','Rule','Details','Waiver']);self.checks.setEditTriggers(QAbstractItemView.NoEditTriggers);self.checks.setSelectionBehavior(QAbstractItemView.SelectRows);self.checks.setSelectionMode(QAbstractItemView.SingleSelection);self.checks.verticalHeader().hide();self.checks.setShowGrid(False);self.checks.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch);self.checks.setColumnWidth(0,80);self.checks.setColumnWidth(1,110);self.checks.setColumnWidth(3,80);self.checks.cellClicked.connect(self.check_selected);cl.addWidget(self.checks,1);self.waive_button=self.button('Waive selected finding…',fn=self.waive);self.waive_button.setEnabled(False);self.checks.itemSelectionChanged.connect(lambda:self.waive_button.setEnabled(self.checks.currentRow()>=0));cl.addWidget(self.waive_button);self.results_tabs.addTab(checks,'Checks')
        self.console=QPlainTextEdit();self.console.setReadOnly(True);self.console.setMaximumBlockCount(5000);self.results_tabs.addTab(self.console,'Job log');self.results_dock.hide()
        self.setCorner(Qt.BottomLeftCorner,Qt.LeftDockWidgetArea);self.setCorner(Qt.BottomRightCorner,Qt.RightDockWidgetArea)
        self.progress=QProgressBar();self.progress.setMaximumWidth(120);self.progress.setTextVisible(False);self.progress.hide();self.statusBar().addPermanentWidget(self.progress);self.save_label=label('Unsaved','muted');self.statusBar().addPermanentWidget(self.save_label);self.statusBar().showMessage('Ready')
        self.resizeDocks([self.nav,self.inspector],[230,300],Qt.Horizontal)

    def action(self,menu,text,fn,shortcut=None,icon=None):
        a=super().action(menu,text,fn,shortcut,icon);self._commands.append((menu.title().replace('&',''),a));return a

    def make_actions(self):
        # Retain the complete command menu and shortcuts from the controller.
        super().make_actions()
        for widget in (self.tool_combo,self.add_combo,self.layer_combo):widget.setParent(self);widget.hide()
        self.toolbar.clear()
        self.nav_toggle=self.button('','sidebar',lambda:self.nav.setVisible(not self.nav.isVisible()),tip='Show or hide Project (Ctrl+1)',check=True);self.toolbar.addWidget(self.nav_toggle)
        title,tv=box(True,(6,0,16,0),1);self.project_label=label('','subtitle');self.project_subtitle=label('IC Design Studio','muted');tv.addWidget(self.project_label);tv.addWidget(self.project_subtitle);self.toolbar.addWidget(title)
        save=self.button('','save',self.save,tip='Save project (Ctrl+S)');self.toolbar.addWidget(save)
        for action,name in ((self.undo_action,'undo'),(self.redo_action,'redo')):
            b=self.button('',name,action.trigger,tip=action.text()+' ('+action.shortcut().toString()+')');b.setEnabled(action.isEnabled());action.changed.connect(lambda a=action,w=b:w.setEnabled(a.isEnabled()));self.toolbar.addWidget(b)
        stretch=QWidget();stretch.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred);self.toolbar.addWidget(stretch)
        self.command_button=self.button('Find a command…   Ctrl+K','search',self.command_palette,role='search');self.command_button.setMinimumWidth(200);self.toolbar.addWidget(self.command_button)
        self.inspector_toggle=self.button('','inspector',lambda:self.inspector.setVisible(not self.inspector.isVisible()),tip='Show or hide Inspector (Ctrl+2)',check=True);self.toolbar.addWidget(self.inspector_toggle)
        self.run_action.triggered.disconnect();self.run_action.setText('Run analysis');self.run_action.triggered.connect(lambda:self.guard(self.quick_run));self.run_button=self.button('Run','play',self.run_action.trigger,role='primary',tip='Run current analysis (F5)');self.toolbar.addWidget(self.run_button);self.run_action.changed.connect(lambda:self.run_button.setEnabled(self.run_action.isEnabled()))
        self.stop_button=self.button('Stop','stop',self.cancel_job,role='danger',tip='Cancel job (Shift+F5)');self.toolbar.addWidget(self.stop_button);self.stop_button.hide();self.stop_widget_action=self.toolbar.actions()[-1];self.stop_widget_action.setVisible(False);self.cancel_action.changed.connect(lambda:self.stop_widget_action.setVisible(self.cancel_action.isEnabled()))
        self.setup_button=self.button('','settings',self.run_dialog,tip='Analysis setup');self.toolbar.addWidget(self.setup_button)
        # Contextual commands. They remain in fixed groups as the editor changes.
        self.tool_buttons={};self.tool_group=QButtonGroup(self);self.tool_group.setExclusive(True)
        for index,text,name,tip in [(0,'Select','select','Select and move (Esc)'),(1,'Wire','wire','Place wire (W): click bends, finish on a pin or wire'),(2,'Rectangle','rect','Draw a rectangle'),(3,'Polygon','polygon','Click vertices; Enter finishes'),(4,'Path','path','Draw a path'),(5,'Measure','ruler','Measure distance')]:
            b=self.button(text,name,lambda i=index:self.set_tool(i),tip=tip,check=True);self.tool_group.addButton(b,index);self.tool_buttons[index]=b
        self.tool_layout.addWidget(self.tool_buttons[0]);self.tool_layout.addWidget(self.tool_buttons[1]);self.place_button=self.button('Place…','plus',self.show_library,tip='Open device library (P)');self.tool_layout.addWidget(self.place_button)
        for i in (2,3,4,5):self.tool_layout.addWidget(self.tool_buttons[i])
        self.tool_layout.addStretch();self.layer_caption=label('Layer','muted');self.tool_layout.addWidget(self.layer_caption);self.layer_combo.setParent(self.toolstrip);self.layer_combo.setMinimumWidth(100);self.layer_combo.setMaximumWidth(140);self.layer_combo.setAccessibleName('Drawing layer');self.tool_layout.addWidget(self.layer_combo)
        self.check_button=self.button('Check','check',lambda:self.check('drc' if self.current_mode=='layout' else 'erc'),tip='Check the active design');self.tool_layout.addWidget(self.check_button)
        self.results_toggle=self.button('Results','wave',lambda:self.results_dock.setVisible(not self.results_dock.isVisible()),check=True,tip='Show or hide results (Ctrl+3)');self.statusBar().addPermanentWidget(self.results_toggle)
        for d in (self.nav,self.inspector,self.results_dock):d.visibilityChanged.connect(self.sync_panel_buttons)
        self._menus=self.findChildren(QMenu);view=next(m for m in self._menus if m.title()=='&View');view.addSeparator();self.action(view,'Focus canvas',self.focus_canvas,'Ctrl+Shift+F');self.action(view,'Reset workspace',self.reset_workspace)
        for shortcut,fn in [('Ctrl+1',lambda:self.nav.setVisible(not self.nav.isVisible())),('Ctrl+2',lambda:self.inspector.setVisible(not self.inspector.isVisible())),('Ctrl+3',lambda:self.results_dock.setVisible(not self.results_dock.isVisible())),('Ctrl+Return',self.run_dialog)]:QShortcut(QKeySequence(shortcut),self,activated=fn)
        for shortcut,fn in [('P',self.show_library),('W',lambda:self.set_tool(1))]:QShortcut(QKeySequence(shortcut),self.schematic,activated=fn).setContext(Qt.WidgetWithChildrenShortcut)
        for i in range(3):QShortcut(QKeySequence('Alt+'+str(i+1)),self,activated=lambda x=i:self.mode_combo.setCurrentIndex(x))
        self.sync_tools();self.sync_panel_buttons()

    def sync_panel_buttons(self,*args):
        for button_name,dock_name in [('nav_toggle','nav'),('inspector_toggle','inspector'),('results_toggle','results_dock')]:
            if hasattr(self,button_name):getattr(self,button_name).setChecked(not getattr(self,dock_name).isHidden())

    def apply_theme(self):
        self.setStyleSheet(stylesheet(self.dark));t=palette(self.dark)
        q=QPalette()
        for role,value in [(QPalette.Window,t['panel']),(QPalette.Base,t['field']),(QPalette.AlternateBase,t['bg']),(QPalette.WindowText,t['text']),(QPalette.Text,t['text']),(QPalette.Button,t['panel']),(QPalette.ButtonText,t['text']),(QPalette.Highlight,t['tint']),(QPalette.HighlightedText,t['accent']),(QPalette.ToolTipBase,t['panel']),(QPalette.ToolTipText,t['text'])]:q.setColor(role,QColor(value))
        app=QApplication.instance();app.setPalette(q)
        if not hasattr(app,'studio_window_theme'):
            app.studio_window_theme=WindowThemeFilter(app);app.installEventFilter(app.studio_window_theme)
        app.studio_window_theme.dark=self.dark
        for window in app.topLevelWidgets():
            if window.isVisible():apply_native_window_theme(window,self.dark)
        for w,name,primary in self._icons:
            try:w.setIcon(icon(name,'#ffffff' if primary else t['muted']))
            except RuntimeError:pass
        for c in (self.schematic,self.layout):c.dark=self.dark;c.update()
        self.plot.dark=self.dark;self.plot.update();self.color_traces()
        self.update_result_status()
        for i in range(self.library_list.count()):
            it=self.library_list.item(i);it.setIcon(icon(DEVICE_ICONS[it.data(Qt.UserRole+1)],t['muted']))

    def refresh(self,fit=False):
        self.rebuilding=True;current_hash=digest(self.project)
        if not any(c['id']==self.cid for c in self.project['cells']):self.cid=self.project['top']
        self.project_label.setText(self.project['name']);self.project_subtitle.setText('IC Design Studio   /   '+('Saved' if self.saved_hash==current_hash else 'Unsaved changes'));self.revision_label.setText(f'r{self.project["revision"]}');self.setWindowTitle(self.project['name']+' — IC Design Studio '+__version__);self.cell_combo.clear();self.tree.clear()
        t=palette(self.dark)
        for c in self.project['cells']:
            self.cell_combo.addItem(c['name'],c['id']);item=QTreeWidgetItem(self.tree,[c['name']+('  · root' if c['id']==self.project['top'] else '')]);item.setIcon(0,icon('cell',t['muted']));item.setData(0,Qt.UserRole,('cell',c['id']));item.setExpanded(c['id']==self.cid)
            for mode,title in enumerate(('Schematic','Layout')):
                sub=QTreeWidgetItem(item,[title]);sub.setIcon(0,icon('wire' if mode==0 else 'layers',t['muted']));sub.setData(0,Qt.UserRole,('view',c['id'],mode))
                if c['id']==self.cid and mode==self.mode_combo.currentIndex():self.tree.setCurrentItem(sub)
        self.tree.setMaximumHeight(min(300,36*(len(self.project['cells'])+2)+10));self.cell_combo.setCurrentIndex(next(i for i,c in enumerate(self.project['cells']) if c['id']==self.cid))
        self.schematic.set_data(self.cell,self.project['pdk'],self.selection,self.net);self.layout.set_data(self.cell,self.project['pdk'],self.selection,self.net,revision=self.project['revision'])
        self.outline.blockSignals(True);self.outline.clear()
        for d in self.cell['devices']:
            it=QListWidgetItem(d['name']+'   '+device_description(d));it.setData(Qt.UserRole,d['id']);it.setToolTip(d['name']+' · '+d.get('value',''));it.setIcon(icon(DEVICE_ICONS[d['kind']],t['muted']));self.outline.addItem(it);it.setSelected(d['id'] in self.selection)
        self.outline.blockSignals(False);self.nav_empty.setVisible(not self.cell['devices']);self.layers.blockSignals(True);self.layers.clear()
        for l in self.project['pdk']['layers']:
            it=QListWidgetItem(l['name']);it.setIcon(icon('layers',l['color']));it.setFlags(it.flags()|Qt.ItemIsUserCheckable);it.setCheckState(Qt.Checked if l['name'] in self.layout.visible_layers else Qt.Unchecked);self.layers.addItem(it)
        self.layers.blockSignals(False);self.undo_action.setEnabled(bool(self.history.undo_stack));self.redo_action.setEnabled(bool(self.history.redo_stack));self.update_save_status(current_hash);self.tech_name.setText(self.project['pdk']['name']);self.tech_detail.setText(self.project['pdk']['revision']+' · '+self.project['pdk'].get('status','unqualified'));self.rebuilding=False;self._inspector_dirty=False;self.build_inspector();self.update_result_status();self.filter_navigation();self.sync_tools()
        if not getattr(self,'analysis_dirty',False):self.load_analysis()
        if fit:QTimer.singleShot(20,self.fit_active)

    def filter_navigation(self,*args):
        q=self.project_search.text().lower()
        for i in range(self.tree.topLevelItemCount()):
            it=self.tree.topLevelItem(i);it.setHidden(bool(q) and q not in it.text(0).lower() and not any(q in d['name'].lower() for c in self.project['cells'] if c['id']==it.data(0,Qt.UserRole)[1] for d in c['devices']))
        for i in range(self.outline.count()):it=self.outline.item(i);it.setHidden(q not in it.text().lower())

    def filter_library(self,*args):
        q=self.library_search.text().lower();first=None
        for i in range(self.library_list.count()):
            it=self.library_list.item(i);it.setHidden(q not in it.text().lower())
            if not it.isHidden() and first is None:first=it
        if first:self.library_list.setCurrentItem(first)
        self.place_library_button.setEnabled(first is not None)

    def outline_selected(self):
        if self.rebuilding:return
        self.select([it.data(Qt.UserRole) for it in self.outline.selectedItems()],'schematic')

    def select(self,ids,mode=None):
        if self._selection_guard:return
        if not self.flush_inspector():return
        self.selection=list(ids);self.current_mode=mode or self.current_mode;self.net='';linked=[s.get('device_id') for s in self.cell['shapes'] if s['id'] in ids and s.get('device_id')];self.schematic.set_data(self.cell,self.project['pdk'],list(dict.fromkeys(ids+linked)));self.layout.set_data(self.cell,self.project['pdk'],ids,revision=self.project['revision']);self.build_inspector();self.outline.blockSignals(True)
        for i in range(self.outline.count()):self.outline.item(i).setSelected(self.outline.item(i).data(Qt.UserRole) in ids)
        self.outline.blockSignals(False);self.sync_tools()

    def tree_clicked(self,it,col=0):
        data=it.data(0,Qt.UserRole)
        if not data or not self.flush_inspector():return
        self.store_view();changed=self.cid!=data[1];self.cid=data[1];self.selection=[];self.net=''
        if data[0]=='view':self.mode_combo.setCurrentIndex(data[2])
        self.refresh(False)
        if changed:self.restore_view()

    def switch_cell_combo(self,i):
        if self.rebuilding or i<0:return
        if not self.flush_inspector():return
        self.store_view();self.cid=self.cell_combo.itemData(i);self.selection=[];self.net='';self.refresh();self.restore_view()

    def store_view(self):
        if self._active_view_key:
            self._view_state[self._active_view_key]=[(c.scale,QPointF(c.offset),c.width(),c.height(),c.auto_fit) for c in (self.schematic,self.layout)]
    def restore_view(self):
        key=(self.project['id'],self.cid,self.mode_combo.currentIndex());self._active_view_key=key
        def restore():
            saved=self._view_state.get(key)
            for i,c in enumerate((self.schematic,self.layout)):
                if saved:
                    c.auto_fit=saved[i][4]
                    if c.auto_fit and c.isVisible():c.fit()
                    else:c.scale=saved[i][0];c.offset=QPointF(saved[i][1])+QPointF((c.width()-saved[i][2])/2,(c.height()-saved[i][3])/2);c.update()
                elif c.isVisible():c.fit()
            self.update_canvas_footer()
        QTimer.singleShot(10,restore)
    def change_mode(self,i):
        if not hasattr(self,'schematic'):return
        previous=self._active_view_key[2] if self._active_view_key else 0
        if not self.flush_inspector():self.mode_combo.blockSignals(True);self.mode_combo.setCurrentIndex(previous);self.mode_combo.blockSignals(False);return
        self.store_view();self.schematic.setVisible(i!=1);self.layout.setVisible(i!=0);self.current_mode='layout' if i==1 else 'schematic';self.cancel_tool();self.selection=[];self.net=''
        self.schematic.selection=[];self.layout.selection=[];self.restore_view();self.build_inspector();self.sync_tools();self.navtabs.setTabEnabled(2,i!=0)
        if i==1:self.navtabs.setCurrentIndex(2)
        elif i==0 and self.navtabs.currentIndex()==2:self.navtabs.setCurrentIndex(0)
    def sync_tools(self):
        if not hasattr(self,'tool_buttons'):return
        physical=self.current_mode=='layout';linked=self.mode_combo.currentIndex()==2
        for i,b in self.tool_buttons.items():b.setVisible(i in (0,5) or (i==1 and not physical) or (i in (2,3,4) and physical))
        self.place_button.setVisible(not physical);self.layer_caption.setVisible(physical);self.layer_combo.setVisible(physical);self.navtabs.setTabEnabled(2,physical or linked)
        active=self.layout if physical else self.schematic;mapping={'select':0,'connect':1,'rect':2,'polygon':3,'path':4,'ruler':5}
        if active.tool in mapping:self.tool_buttons[mapping[active.tool]].setChecked(True)
        self.update_canvas_footer();self.adapt_tools();self.sync_navigation()
    def set_tool(self,index):
        if not self.flush_inspector():return
        self.schematic.placement=None;self.tool_combo.setCurrentIndex(index);self.change_tool(index)
    def change_tool(self,index):
        tool=['select','connect','rect','polygon','path','ruler'][index]
        if tool=='connect' and self.mode_combo.currentIndex()==1:self.mode_combo.setCurrentIndex(0)
        if tool in ('rect','polygon','path') and self.mode_combo.currentIndex()==0:self.mode_combo.setCurrentIndex(1)
        for c in (self.schematic,self.layout):c.cancel_gesture();c.tool=tool if (c.mode=='layout' and tool!='connect') or (c.mode=='schematic' and tool in ('select','connect','ruler')) else 'select';c.update()
        self.current_mode='layout' if tool in ('rect','polygon','path') else 'schematic' if tool=='connect' else self.current_mode
        self.tool_hint.setText({'select':'Select · drag to move or box-select','connect':'Wire · click start and bends · Space flips bend · Enter finishes · Esc cancels','rect':'Rectangle · drag between opposite corners','polygon':'Polygon · click vertices, Enter to finish','path':'Path · click vertices, Enter to finish','ruler':'Measure · drag between two points'}[tool]);self.sync_tools();(self.layout if self.current_mode=='layout' else self.schematic).setFocus()
    def cancel_tool(self):
        for c in (self.schematic,self.layout):c.cancel_gesture();c.placement=None;c.tool='select';c.update()
        if hasattr(self,'tool_combo'):self.tool_combo.blockSignals(True);self.tool_combo.setCurrentIndex(0);self.tool_combo.blockSignals(False)
        self.tool_hint.setText('Select · drag to move or box-select');self.sync_tools()
    def show_library(self):
        self.nav.show();self.navtabs.setCurrentIndex(1);self.library_search.setFocus()
    def begin_placement(self,index):
        if not self.flush_inspector():return
        self.mode_combo.setCurrentIndex(0);self.cancel_tool();kind=['','R','C','L','V','I','NMOS','PMOS'][index];self.schematic.placement=device(kind,self.next_device_name(kind),0,0);self.schematic.tool='place';self.schematic.setFocus();self.schematic.drag=self.schematic.snap(self.schematic.model(self.schematic.rect().center()));self.schematic.update();self.tool_hint.setText('Place '+DEVICE_NAMES[kind].lower()+' · R / Shift+R rotate · click to place · Esc cancels');self.sync_tools()
    def next_device_name(self,kind):
        prefix={'NMOS':'MN','PMOS':'MP'}.get(kind,kind);names={d['name'] for d in self.cell['devices']};n=1
        while prefix+str(n) in names:n+=1
        return prefix+str(n)
    def place_device_at(self,x,y):
        if not self.schematic.placement:return
        d=clone(self.schematic.placement);d['id']=uid();d.update(x=x,y=y);self.cancel_tool();self.commit(lambda p:next(c for c in p['cells'] if c['id']==self.cid)['devices'].append(d),'Place '+d['name']);self.select([d['id']],'schematic');self.reveal_properties();self.schematic.setFocus()
    def fit_active(self):
        for c in (self.schematic,self.layout):
            if c.isVisible():c.fit()
        self._active_view_key=(self.project['id'],self.cid,self.mode_combo.currentIndex());self.update_canvas_footer()
    def update_canvas_footer(self):
        if not hasattr(self,'zoom_label'):return
        active=self.layout if self.current_mode=='layout' else self.schematic;self.zoom_label.setText(f'{active.scale*100:.0f}%');self.grid_label.setText(f'{self.project["pdk"].get("grid",5)} nm grid' if self.current_mode=='layout' else '10 unit grid')
    def canvas_message(self,text):
        if text.startswith('X '):self.statusBar().showMessage(text)
        else:self.tool_hint.setText(text)
    def reveal_properties(self):self.inspector.show();self.inspector_tabs.setCurrentIndex(0)
    def canvas_context(self,canvas,pos):
        menu=QMenu(self)
        if self.selection:
            menu.addAction('Properties',self.reveal_properties);menu.addSeparator();menu.addAction('Duplicate',lambda:self.guard(self.duplicate))
            if canvas.mode=='schematic':menu.addAction(self.rotate_action);menu.addAction(self.rotate_back_action)
            menu.addAction('Delete',lambda:self.guard(self.delete));menu.addSeparator()
        if canvas.mode=='schematic':menu.addAction('Place component…',self.show_library);menu.addAction(self.wire_action);menu.addAction(self.label_action);menu.addAction(self.ground_action);menu.addAction(self.net_action)
        else:
            for i,text in [(2,'Rectangle'),(3,'Polygon'),(4,'Path')]:menu.addAction('Draw '+text.lower(),lambda x=i:self.set_tool(x))
        menu.addAction('Fit design',self.fit_active);menu.exec(canvas.mapToGlobal(pos))
    def focus_canvas(self):
        docks=self.workspace_docks() if hasattr(self,'workspace_docks') else (self.nav,self.inspector,self.results_dock)
        if self._focus_panels is None:
            self._focus_panels=[not d.isHidden() for d in docks]
            for d in docks:d.hide()
        else:
            for d,on in zip(docks,self._focus_panels):d.setVisible(on)
            self._focus_panels=None
    def reset_workspace(self):
        self._focus_panels=None
        for dock,side in [(self.nav,Qt.LeftDockWidgetArea),(self.inspector,Qt.RightDockWidgetArea),(self.results_dock,Qt.BottomDockWidgetArea)]:dock.setFloating(False);self.addDockWidget(side,dock)
        self.nav.show();self.inspector.show();self.results_dock.setVisible(bool(self.result));self.resizeDocks([self.nav,self.inspector],[230,300],Qt.Horizontal);self.resizeDocks([self.results_dock],[290],Qt.Vertical);self.fit_active()

    def clear_form(self):
        self._building_inspector=True
        while self.form.count():
            item=self.form.takeAt(0)
            if item.widget():item.widget().hide();item.widget().deleteLater()
        self.form_fields={};self.property_error=None
    def section(self,title,expanded=True):
        s=Section(title,self._sections.get(title,expanded),lambda on:self._sections.update({title:on}));self.form.addWidget(s);return s.form
    def field(self,title,value,key=None,form=None,placeholder=None):
        w=QLineEdit(str(value));w.setAccessibleName(title)
        if placeholder:w.setPlaceholderText(placeholder)
        w.setMinimumWidth(70);(form or self.form).addRow(title,w);self.form_fields[key or title]=w;w.textChanged.connect(self.inspector_changed);w.returnPressed.connect(lambda:self.apply_inspector(self._inspected_device));return w
    def inspector_changed(self,*args):
        if self._building_inspector:return
        self._inspector_dirty=True
        if hasattr(self,'apply_button'):self.apply_button.setEnabled(True);self.reset_button.setEnabled(True)
        if self.property_error:self.property_error.hide()
    def build_inspector(self):
        self.clear_form();self._inspector_dirty=False;objects=[o for o in self.cell['devices']+self.cell['shapes'] if o['id'] in self.selection]
        if len(objects)>1:
            self.form.addWidget(label(f'{len(objects)} objects selected','title'));note=label('Move, duplicate, or delete the selection together. Select one object to edit its properties.','muted');note.setWordWrap(True);self.form.addWidget(note);self.form.addWidget(self.button('Duplicate selection','plus',self.duplicate,role='secondary'));self.form.addWidget(self.button('Clear selection',fn=lambda:self.select([])));self._building_inspector=False;return
        if not objects:
            self.form.addWidget(label(self.cell['name'],'title'));self.form.addWidget(label('Layout document' if self.current_mode=='layout' else 'Schematic document','muted'));f=self.section('Document');f.addRow('Components',label(str(len(self.cell['devices']))));f.addRow('Layout shapes',label(str(len(self.cell['shapes']))));ports=label(', '.join(self.cell['ports']) or 'No external ports');ports.setWordWrap(True);f.addRow('Ports',ports);f.addRow(self.button('Edit cell ports…',fn=self.edit_ports,role='secondary'))
            note=label('Select an object to see its properties.\n\nDrag empty space to select a group. Hold Space and drag to pan.','muted');note.setWordWrap(True);self.form.addWidget(note)
            if self.current_mode=='schematic':self.form.addWidget(self.button('Place a component','plus',self.show_library,role='secondary'))
            else:self.form.addWidget(self.button('Draw a rectangle','rect',lambda:self.set_tool(2),role='secondary'))
            self.form.addStretch();self._building_inspector=False;return
        obj=objects[0];self.inspected_id=obj['id'];is_device='nets' in obj;self._inspected_device=is_device
        self.form.addWidget(label(obj['name'] if is_device else {'rect':'Rectangle','polygon':'Polygon','path':'Path'}[obj['kind']],'title'));self.form.addWidget(label(device_description(obj) if is_device else obj['layer']+' geometry','muted'))
        if is_device:
            f=self.section('Electrical');self.field('Designator',obj['name'],'Name',f)
            if obj.get('native_spice'):
                self.form.addWidget(self.button('Edit device parameters…',fn=lambda:self.edit_native_properties(obj['id'])))
                f.addRow('Definition',label(obj['native_spice'].get('label','Simulation program')))
            if obj['kind']=='XS':
                self.form.addWidget(self.button('Edit Xschem properties…',fn=lambda:self.edit_xschem_properties(obj['id'])))
                f.addRow('Symbol',label(obj['xschem']['reference']))
            if obj['kind'] not in ('NMOS','PMOS','X','PDK','XS','SPICE'):self.field('Value',obj['value'],form=f,placeholder='e.g. 10k')
            if obj['kind'] in ('NMOS','PMOS'):
                self.field('Width',obj['params']['w'],'param:w',f);self.field('Length',obj['params']['l'],'param:l',f)
            f=self.section('Connections')
            for pin,computed in obj['nets'].items():
                n=obj.get('net_labels',obj['nets'] if 'wires' not in self.cell else {}).get(pin,'');self.field({'p':'Positive (+)','n':'Negative (−)','d':'Drain','g':'Gate','s':'Source','b':'Bulk'}.get(pin,pin),n,'net:'+pin,f,placeholder='Connected: '+computed if not computed.startswith('N_') else 'Unlabelled · draw a wire')
            if obj['kind'] in ('V','I'):
                f=self.section('Source waveform');combo=QComboBox();combo.addItems(['dc','pulse','sine']);combo.setCurrentText(obj['source']['type']);f.addRow('Waveform',combo);self.form_fields['source:type']=combo;combo.currentIndexChanged.connect(self.inspector_changed)
                for k,title in [('low','Low level'),('high','High level'),('period','Period'),('delay','Delay'),('duty','Duty cycle'),('ac','AC magnitude')]:self.field(title,obj['source'][k],'source:'+k,f)
                def source_visibility(form=f,source=combo):
                    typ=source.currentText()
                    for k in ('low','high','period','delay','duty','ac'):
                        on=k=='ac' or (typ!='dc' and (k!='duty' or typ=='pulse'));w=self.form_fields.get('source:'+k)
                        if w:w.setVisible(on);form.labelForField(w).setVisible(on)
                combo.currentTextChanged.connect(lambda _:source_visibility());source_visibility()
            f=self.section('Position',True);self.field('X',obj['x'],form=f);self.field('Y',obj['y'],form=f);f.addRow('Rotation',label(str(obj['rotation'])+'°'));buttons,bl=box(False,spacing=4);bl.addWidget(self.button('↶  Shift+R',fn=lambda:self.rotate(-90),role='secondary'));bl.addWidget(self.button('↷  R',fn=self.rotate,role='secondary'));f.addRow(buttons)
            if obj['kind'] in ('NMOS','PMOS') and not __import__('icstudio.catalog',fromlist=['binding_for']).binding_for(self.project['pdk'],obj):
                f=self.section('Generic model',False)
                for k,title in [('vto','Threshold (V)'),('kp','Kp (A/V²)'),('lambda','Lambda (1/V)')]:self.field(title,obj['params'][k],'param:'+k,f)
        else:
            f=self.section('Assignment');layers=QComboBox();layers.addItems([l['name'] for l in self.project['pdk']['layers']]);layers.setCurrentText(obj['layer']);layers.currentIndexChanged.connect(self.inspector_changed);self.form_fields['layer']=layers;f.addRow('Layer',layers);self.field('Net',obj.get('net',''),form=f)
            linked=QComboBox();linked.addItem('None','')
            for d in self.cell['devices']:linked.addItem(d['name']+' · '+device_description(d),d['id'])
            linked.setCurrentIndex(max(0,linked.findData(obj.get('device_id',''))));linked.currentIndexChanged.connect(self.inspector_changed);self.form_fields['device_link']=linked;f.addRow('Component',linked)
            f=self.section('Geometry (µm)')
            if obj['kind']=='rect':
                xs=[p[0] for p in obj['points']];ys=[p[1] for p in obj['points']]
                for k,val in [('Left',min(xs)),('Top',min(ys)),('Width',max(xs)-min(xs)),('Height',max(ys)-min(ys))]:self.field(k,f'{val/1000:g}',form=f)
            else:
                self.vertex_table=QTableWidget(len(obj['points']),2);self.vertex_table.setHorizontalHeaderLabels(['X (µm)','Y (µm)']);self.vertex_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.vertex_table.setMaximumHeight(185)
                for i,pt in enumerate(obj['points']):
                    for j,value in enumerate(pt):self.vertex_table.setItem(i,j,QTableWidgetItem(f'{value/1000:g}'))
                self.vertex_table.itemChanged.connect(self.inspector_changed);f.addRow(self.vertex_table)
                if obj['kind']=='path':self.field('Width',f'{obj["width"]/1000:g}',form=f)
                if obj.get('holes'):n=label(f'{len(obj["holes"])} interior holes preserved.','muted');n.setWordWrap(True);f.addRow(n)
        self.property_error=label('','error');self.property_error.setWordWrap(True);self.property_error.hide();self.form.addWidget(self.property_error)
        buttons,bl=box(False,spacing=6);self.reset_button=self.button('Reset',fn=self.build_inspector);self.apply_button=self.button('Apply changes',fn=lambda:self.apply_inspector(is_device),role='primary');self.apply_button.setEnabled(False);self.reset_button.setEnabled(False);bl.addWidget(self.reset_button);bl.addWidget(self.apply_button,1);self.form.addWidget(buttons);self.form.addStretch();self._building_inspector=False

    def flush_inspector(self):
        if not self._inspector_dirty or self._building_inspector:return True
        return self.apply_inspector(self._inspected_device)
    def apply_inspector(self,is_device):
        try:
            values={k:(w.currentText() if isinstance(w,QComboBox) else w.text().strip()) for k,w in self.form_fields.items()};oid=self.inspected_id
            candidate=clone(self.project);c=next(c for c in candidate['cells'] if c['id']==self.cid);obj=next(o for o in c['devices' if is_device else 'shapes'] if o['id']==oid)
            if is_device:
                obj.update(name=values['Name'],x=float(values['X']),y=float(values['Y']))
                if 'Value' in values:obj['value']=values['Value']
                for key,val in values.items():
                    if key.startswith('net:'):
                        if 'wires' in c:
                            from .wiring import set_label
                            old_label=obj.get('net_labels',{}).get(key[4:],'')
                            if val!=old_label:set_label(c,oid,key[4:],val,candidate)
                        else:obj['nets'][key[4:]]=val
                    elif key.startswith('param:'):obj['params'][key[6:]]=val
                    elif key.startswith('instanceparam:'):obj.setdefault('parameters',{})[key[14:]]=val
                    elif key.startswith('modelparam:'):obj.setdefault('model_params',{})[key[11:]]=val
                    elif key.startswith('source:'):obj['source'][key[7:]]=val
            else:
                def nm(key):
                    raw=float(values[key])*1000
                    if not math.isfinite(raw) or abs(raw-round(raw))>1e-5:raise ValueError(key+': use a whole number of nanometres (0.001 µm).')
                    return round(raw)
                obj.update(layer=values['layer'],net=values['Net'],device_id=self.form_fields['device_link'].currentData())
                if obj['kind']=='rect':
                    x,y,w,h=(nm(k) for k in ('Left','Top','Width','Height'))
                    if w<=0 or h<=0:raise ValueError('Width and height must be greater than zero.')
                    obj['points']=[[x,y],[x+w,y+h]]
                else:
                    pts=[]
                    for i in range(self.vertex_table.rowCount()):
                        pt=[]
                        for j in range(2):
                            raw=float(self.vertex_table.item(i,j).text())*1000
                            if not math.isfinite(raw) or abs(raw-round(raw))>1e-5:raise ValueError('Vertices must lie on whole nanometres (0.001 µm).')
                            pt.append(round(raw))
                        pts.append(pt)
                    obj['points']=pts
                    if obj['kind']=='path':obj['width']=nm('Width')
            if is_device and 'wires' in c:
                from .wiring import pins,keep_connections
                keep_connections(c,pins(self.cell,self.project),candidate)
                from .net_labels import reconcile
                reconcile(c,self.cell,candidate)
            validate(candidate)
            if c==self.cell or ('wires' not in c and obj==next(o for o in self.cell['devices' if is_device else 'shapes'] if o['id']==oid)):self._inspector_dirty=False;self.build_inspector();return True
            replacement=clone(c)
            def edit(p):
                cell=next(c for c in p['cells'] if c['id']==self.cid);cell.clear();cell.update(replacement)
            self._inspector_dirty=False;self.commit(edit,'Edit properties');self.statusBar().showMessage('Properties updated · Ctrl+Z to undo',5000);return True
        except Exception as exc:
            self._inspector_dirty=True
            if self.property_error:self.property_error.setText(str(exc));self.property_error.show();self.inspector_scroll.ensureWidgetVisible(self.property_error)
            self.reveal_properties();return False

    def make_analysis_panel(self):
        self.analysis_dirty=False;self._loading_analysis=True;page,v=box(True,(16,16,16,18),12);v.addWidget(label('Analysis setup','title'));v.addWidget(label('Configure once. Run with F5.','muted'));self.analysis_type=QComboBox();self.analysis_type.setAccessibleName('Analysis type')
        for value,text in ANALYSES.items():self.analysis_type.addItem(text,value)
        v.addWidget(self.analysis_type);self.analysis_engine=QComboBox();self.analysis_engine.addItem('Built-in solver','builtin');self.analysis_engine.addItem('ngspice','ngspice');self.analysis_engine.setAccessibleName('Simulation engine');v.addWidget(label('ENGINE','section'));v.addWidget(self.analysis_engine)
        self.engine_requirement=QLabel();self.engine_requirement.setWordWrap(True);v.addWidget(self.engine_requirement)
        fields=QWidget();self.analysis_form=QFormLayout(fields);self.analysis_form.setContentsMargins(0,8,0,8);self.analysis_form.setSpacing(10);self.analysis_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow);self.analysis_fields={}
        for key,title,hint in [('stop','Stop time','100u'),('step','Time step','200n'),('dc_start','Start (V / A)','0'),('dc_stop','Stop (V / A)','1.8'),('dc_step','Step (V / A)','10m'),('start','Start (Hz)','10'),('end','Stop (Hz)','1Meg'),('points','Points','100'),('temperature','Temperature (°C)','27')]:
            w=QLineEdit();w.setPlaceholderText(hint);w.setAccessibleName(title);w.textChanged.connect(self.analysis_changed);self.analysis_fields[key]=w;self.analysis_form.addRow(title,w)
        self.analysis_source=QComboBox();self.analysis_source.setAccessibleName('DC sweep source');self.analysis_form.addRow('Source',self.analysis_source);self.analysis_source.currentIndexChanged.connect(self.analysis_changed);v.addWidget(fields)
        self.analysis_error=label('','error');self.analysis_error.setWordWrap(True);self.analysis_error.hide();v.addWidget(self.analysis_error);self.analysis_run=self.button('Run analysis','play',self.quick_run,role='primary');v.addWidget(self.analysis_run);self.analysis_caption=label('Generic circuit models. Configure an external engine in Tools → Engine diagnostics.','muted');self.analysis_caption.setWordWrap(True);v.addWidget(self.analysis_caption);v.addStretch()
        self.analysis_type.currentIndexChanged.connect(self.analysis_changed);self.analysis_type.currentIndexChanged.connect(self.analysis_visibility);self.analysis_engine.currentIndexChanged.connect(self.analysis_changed);self.analysis_engine.currentIndexChanged.connect(self.analysis_visibility);self._loading_analysis=False
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page);return scroll
    def analysis_changed(self,*args):
        if self._loading_analysis:return
        self.analysis_dirty=True;self.analysis_error.hide()
    def analysis_visibility(self,*args):
        typ=self.analysis_type.currentData();visible={'tran':{'stop','step'},'op':set(),'dc':{'dc_start','dc_stop','dc_step'},'ac':{'start','end','points'},'noise':{'start','end','points','temperature'},'xschem':set()}.get(typ,set())
        for k,w in self.analysis_fields.items():w.setVisible(k in visible);self.analysis_form.labelForField(w).setVisible(k in visible)
        self.analysis_source.setVisible(typ=='dc');self.analysis_form.labelForField(self.analysis_source).setVisible(typ=='dc')
        self.analysis_form.labelForField(self.analysis_fields['points']).setText('Points / decade' if self.analysis_engine.currentData()=='ngspice' and typ=='ac' else 'Points')
    def load_analysis(self):
        self._loading_analysis=True;a=self.project['analysis'];self.analysis_type.setCurrentIndex(self.analysis_type.findData(a['type']))
        from .engine_selection import selected,requirement
        reason=requirement(self.project);self.analysis_engine.setCurrentIndex(self.analysis_engine.findData(selected(self.project)))
        self.analysis_engine.setEnabled(not reason);self.engine_requirement.setText(reason);self.engine_requirement.setVisible(bool(reason))
        for k,w in self.analysis_fields.items():w.setText(str(a[k]))
        self.analysis_source.clear()
        try:names=[d['name'] for d in flatten(self.project,self.cid) if d['kind'] in ('V','I')]
        except ValueError:names=[]
        self.analysis_source.addItems(names);self.analysis_source.setCurrentText(a['source']);self._loading_analysis=False;self.analysis_dirty=False;self.analysis_visibility()
    def run_dialog(self):
        self.inspector.show();self.inspector_tabs.setCurrentIndex(1);self.analysis_type.setFocus()
    def quick_run(self):
        if self.process:return
        if not self.flush_inspector():return
        try:
            a=clone(self.project['analysis']);typ=self.analysis_type.currentData();keys={'tran':{'stop','step'},'op':set(),'dc':{'dc_start','dc_stop','dc_step'},'ac':{'start','end','points'},'noise':{'start','end','points','temperature'}}[typ];a.update({k:self.analysis_fields[k].text().strip() for k in keys});a.update(type=typ,source=self.analysis_source.currentText(),points=int(a['points']),temperature=float(a['temperature']))
            if not math.isfinite(a['temperature']):raise ValueError('Enter a finite temperature.')
            if a['type']=='tran':
                stop,step=scalar(a['stop']),scalar(a['step'])
                if not 0<step<=stop or stop/step>20000:raise ValueError('Use a positive time step and at most 20,000 steps.')
            elif a['type']=='dc':
                delta=scalar(a['dc_stop'])-scalar(a['dc_start']);step=scalar(a['dc_step'])
                if not a['source']:raise ValueError('Add a voltage or current source before running a DC sweep.')
                if step==0 or delta/step<0 or delta/step>5000:raise ValueError('Choose a sweep step toward the stop value, with at most 5,001 points.')
            elif a['type'] in ('ac','noise'):
                if not 0<scalar(a['start'])<scalar(a['end']) or not 2<=a['points']<=1000:raise ValueError('Use increasing positive frequencies and 2–1,000 points.')
            self.analysis_dirty=False
            if a!=self.project['analysis']:self.commit(lambda p:p.update(analysis=a),'Analysis settings')
            self.start_job(a,self.analysis_engine.currentData());self.analysis_error.hide();self.results_tabs.setCurrentIndex(0)
        except Exception as exc:
            self.run_dialog();self.analysis_error.setText(str(exc));self.analysis_error.show()
    def start_job(self,settings,engine='builtin'):
        super().start_job(settings,engine);self._job_state='running';self.analysis_run.setEnabled(False);self.run_button.setText('Running…');self.resizeDocks([self.results_dock],[290],Qt.Vertical);self.result_status.setText('Running…');self.result_status.setStyleSheet('');self.plot.empty_message='Running analysis…\nResults will appear here when the job completes.';self.plot.update();self.statusBar().showMessage('Running '+ANALYSES.get(settings['type'],settings['type']))
    def job_finished(self,code,status):
        cancelled=getattr(self,'cancelled',False)
        count=len(self.jobs);super().job_finished(code,status);self.analysis_run.setEnabled(True);self.run_button.setText('Run')
        self._job_state='cancelled' if cancelled else 'complete' if len(self.jobs)>count else 'failed'
        self.update_result_status()
        text={'cancelled':'Analysis cancelled. Adjust settings or Run again.','failed':'Analysis failed. Open Job log for details.','complete':'Analysis complete.'}[self._job_state]
        self.statusBar().showMessage(text,12000);self.plot.empty_message=text;self.plot.update()
        if self._job_state=='failed':
            self.analysis_error.setText(text);self.analysis_error.show()
    def cancel_job(self):
        if self.process:self.result_status.setText('Cancelling…');self.run_button.setText('Stopping…')
        return super().cancel_job()
    def add_result(self,r):
        super().add_result(r);i=len(self.jobs)-1;self.run_combo.setItemText(i,f'Run {i+1:02d} · {ANALYSES.get(r["settings"]["type"],r["settings"]["type"])} · r{r["revision"]}');self.run_combo.setItemData(i,r.get('created','')+' · '+r.get('engine',''),Qt.ToolTipRole)
    def update_result_status(self):
        if self._job_state=='running':self.result_status.setText('Running…');self.result_status.setStyleSheet('');return
        if not self.result:self.result_status.setText({'cancelled':'Cancelled','failed':'Failed · see Job log'}.get(self._job_state,'No analysis yet'));self.result_status.setStyleSheet('');return
        stale=self.result['design_hash']!=design_digest(self.project);self.result_status.setText('STALE · rerun' if stale else 'Current revision');self.result_status.setToolTip(self.result['engine']);self.result_status.setStyleSheet('color:'+('#b9701b' if not self.dark else '#f0bd72')+';' if stale else 'color:'+('#24765b' if not self.dark else '#8bccb3')+';')
        if self.check_revision is not None and self.check_revision!=self.project['revision']:self.check_note.setText('Design changed. Run checks again to refresh these findings.')
    def check(self,typ):
        if not self.flush_inspector():return
        super().check(typ);self.resizeDocks([self.results_dock],[290],Qt.Vertical)
        if not self.issues:self.check_note.setText(self.check_note.text()+' No findings from this check.')
    def set_project(self,p,path=None):
        if self.process:raise ValueError('Stop the active job before switching projects.')
        self._inspector_dirty=False;self.analysis_dirty=False;self.check_revision=None;self._active_view_key=None;self._job_state='idle';self.plot.empty_message='Run an analysis to inspect voltages and measurements';self.cancel_tool();super().set_project(p,path);self.load_analysis();self.results_dock.setVisible(bool(self.result));self.navtabs.setCurrentIndex(0)
    def save(self,as_new=False):
        if not self.flush_inspector():return False
        if not self.flush_analysis():return False
        return super().save(as_new)
    def maybe_save(self):
        if not self.flush_inspector():return False
        if not self.flush_analysis():return False
        return super().maybe_save()
    def flush_analysis(self):
        if not getattr(self,'analysis_dirty',False):return True
        try:
            settings=self.current_analysis_settings();self.analysis_dirty=False
            if settings!=self.project['analysis']:self.commit(lambda p:p.update(analysis=settings),'Analysis settings')
            return True
        except (ValueError,KeyError) as exc:
            self.analysis_error.setText(str(exc));self.analysis_error.show();self.run_dialog();return False
    def commit(self,fn,label='Edit'):
        if not self.flush_inspector():return
        return super().commit(fn,label)
    def closeEvent(self,e):
        state=self.saveState(2);geometry=self.saveGeometry();super().closeEvent(e)
        if e.isAccepted():self.settings.setValue('workspace/v2/state',state);self.settings.setValue('workspace/v2/geometry',geometry)


    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'tool_buttons'):QTimer.singleShot(0,self.adapt_tools)
    def adapt_tools(self):
        compact=self.toolstrip.width()<740
        names={0:'Select',1:'Wire',2:'Rectangle',3:'Polygon',4:'Path',5:'Measure'}
        for i,b in self.tool_buttons.items():
            b.setText('' if compact and i in (2,3,4,5) else names[i]);b.setMinimumWidth(34 if compact and i in (2,3,4,5) else 0)
        self.layer_caption.setVisible(self.current_mode=='layout' and not compact)
        self.command_button.setText('Commands   Ctrl+K' if self.width()<1200 else 'Find a command…   Ctrl+K');self.command_button.setMinimumWidth(155 if self.width()<1200 else 200)
    def sync_navigation(self):
        for i in range(self.tree.topLevelItemCount()):
            cell=self.tree.topLevelItem(i)
            for j in range(cell.childCount()):
                it=cell.child(j);data=it.data(0,Qt.UserRole)
                if data[1]==self.cid and data[2]==self.mode_combo.currentIndex():self.tree.setCurrentItem(it)
    def color_traces(self):
        from .plot import trace_colors
        if not hasattr(self,'traces'):return
        self.traces.blockSignals(True)
        for i in range(self.traces.count()):self.traces.item(i).setForeground(QColor(trace_colors(self.dark)[i%6]))
        self.traces.blockSignals(False)
    def select_run(self,index):
        super().select_run(index);self.color_traces()


    def command_palette(self):
        entries=[];seen=set()
        for group,a in self._commands:
            if not a.isEnabled():continue
            key=(a.text(),a.shortcut().toString())
            if key in seen:continue
            seen.add(key);entries.append((group,a))
        class PaletteDialog(QDialog):
            def eventFilter(dlg,obj,event):
                if obj is dlg.query and event.type()==QEvent.KeyPress and event.key() in (Qt.Key_Down,Qt.Key_Up):
                    direction=1 if event.key()==Qt.Key_Down else -1;dlg.items.setCurrentRow(max(0,min(dlg.items.count()-1,dlg.items.currentRow()+direction)));return True
                return super().eventFilter(obj,event)
        dlg=PaletteDialog(self);dlg.setWindowTitle('Find a command');dlg.resize(600,450);v=QVBoxLayout(dlg);v.setContentsMargins(18,18,18,14);v.setSpacing(12);dlg.query=QLineEdit();dlg.query.setPlaceholderText('Search by action or menu…');dlg.query.setAccessibleName('Search commands');dlg.query.setClearButtonEnabled(True);v.addWidget(dlg.query);dlg.items=QListWidget();dlg.items.setIconSize(QSize(18,18));v.addWidget(dlg.items,1);v.addWidget(label('↑ ↓ to choose     Enter to run     Esc to close','muted'));dlg.query.installEventFilter(dlg)
        def fill():
            q=dlg.query.text().lower().split();dlg.items.clear()
            for i,(group,a) in enumerate(entries):
                text=a.text().replace('&','');hay=(group+' '+text).lower()
                if all(word in hay for word in q):
                    shortcut=a.shortcut().toString(QKeySequence.NativeText);it=QListWidgetItem(text+('    '+shortcut if shortcut else '')+'\n'+group);it.setData(Qt.UserRole,i);it.setSizeHint(QSize(500,56));dlg.items.addItem(it)
            if dlg.items.count():dlg.items.setCurrentRow(0)
        def choose():
            item=dlg.items.currentItem()
            if item:action=entries[item.data(Qt.UserRole)][1];dlg.accept();action.trigger()
        dlg.query.textChanged.connect(fill);dlg.query.returnPressed.connect(choose);dlg.items.itemActivated.connect(lambda _:choose());fill();dlg.query.setFocus();dlg.exec()
