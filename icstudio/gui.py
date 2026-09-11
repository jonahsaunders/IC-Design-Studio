from __future__ import annotations
import json,math,os,shutil,subprocess,sys,tempfile,traceback
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QSettings,QStandardPaths,QProcess,QUrl
from PySide6.QtGui import QAction,QKeySequence,QColor,QIcon,QDesktopServices,QPainter,QPixmap,QFont,QShortcut
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QSplitter,QLabel,QPushButton,QComboBox,QToolBar,QTreeWidget,QTreeWidgetItem,QDockWidget,QFormLayout,QLineEdit,QScrollArea,QTabWidget,QPlainTextEdit,QTableWidget,QTableWidgetItem,QFileDialog,QMessageBox,QInputDialog,QDialog,QDialogButtonBox,QSpinBox,QCheckBox,QListWidget,QListWidgetItem,QAbstractItemView,QProgressBar,QMenu,QStyle,QSizePolicy)
from . import __version__,recovery,job_store
from .model import *
from .canvas import Canvas
from .plot import WavePlot,COLORS
from .interchange import spice,export_layout,import_layout,export_handoff,export_csv,export_xschem

from .recovery_ui import RecoveryUIMixin

class StudioCore(RecoveryUIMixin,QMainWindow):
    def __init__(self,recover=True):
        super().__init__();self.setWindowTitle('IC Design Studio');self.resize(1440,930);self.setMinimumSize(900,600)
        self.settings=QSettings('ICDesignStudio','Studio');self.history=History(example());self.cid=self.project['top'];self.path=None;self.saved_hash=None;self.selection=[];self.net='';self.current_mode='schematic';self.jobs=[];self.result=None;self.issues=[];self.check_revision=None;self.process=None;self.active_job=None;self.rebuilding=False;self.form_fields={}
        self.data_dir=Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation));self.data_dir.mkdir(parents=True,exist_ok=True);self.recovery_root=Path(self.settings.value('storage/recovery_root',str(self.data_dir/'recovery')));self.reset_recovery_status();self.recovery_dir=self.recovery_root/uid();self._recovered_from=None;self._disk_hash=None;self.jobs_dir=self.data_dir/'runs';self.jobs_dir.mkdir(exist_ok=True)
        self.dark=self.settings.value('appearance/theme','dark')!='light';self.make_ui();self.make_actions();self.apply_theme();self.refresh(True)
        if recover:QTimer.singleShot(100,self.offer_recovery)
    @property
    def project(self):return self.history.project
    @property
    def cell(self):return next(c for c in self.project['cells'] if c['id']==self.cid)
    def guard(self,fn):
        try:return fn()
        except Exception as e:self.error(str(e));return None
    def error(self,text):
        self.console.appendPlainText('ERROR: '+text);self.statusBar().showMessage(text,12000);QMessageBox.warning(self,'Action could not complete',text)
    def make_ui(self):
        self.toolbar=QToolBar('Design tools',self);self.toolbar.setMovable(False);self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon);self.addToolBar(self.toolbar)
        self.project_label=QLabel();self.project_label.setObjectName('projectTitle');self.revision_label=QLabel();self.revision_label.setObjectName('revisionLabel')
        heading=QWidget();heading.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed);hl=QHBoxLayout(heading);hl.setContentsMargins(20,12,20,12);hl.addWidget(self.project_label);hl.addWidget(self.revision_label);hl.addStretch();self.mode_combo=QComboBox();self.mode_combo.addItems(['Schematic','Layout','Linked views']);self.mode_combo.currentIndexChanged.connect(self.change_mode);hl.addWidget(self.mode_combo)
        self.cell_combo=QComboBox();self.cell_combo.setMinimumWidth(120);self.cell_combo.currentIndexChanged.connect(self.switch_cell_combo);hl.addWidget(self.cell_combo)
        self.schematic=Canvas('schematic');self.layout=Canvas('layout');self.canvases=QSplitter();self.canvases.addWidget(self.schematic);self.canvases.addWidget(self.layout);self.layout.hide()
        for canvas in (self.schematic,self.layout):
            canvas.selected.connect(lambda ids,c=canvas:self.select(ids,c.mode));canvas.move_objects.connect(lambda ids,x,y,c=canvas:self.move(ids,x,y,c.mode));canvas.message.connect(lambda t:self.statusBar().showMessage(t));canvas.connect_pins.connect(self.connect);canvas.shape_added.connect(self.add_shape)
        center=QWidget();vl=QVBoxLayout(center);vl.setContentsMargins(0,0,0,0);vl.setSpacing(0);vl.addWidget(heading);vl.addWidget(self.canvases,1);self.setCentralWidget(center)
        self.nav=QDockWidget('PROJECT',self);self.nav.setObjectName('navigator');self.nav.setAllowedAreas(Qt.LeftDockWidgetArea|Qt.RightDockWidgetArea);navtabs=QTabWidget();self.tree=QTreeWidget();self.tree.setHeaderHidden(True);self.tree.itemClicked.connect(self.tree_clicked);navtabs.addTab(self.tree,'Design');self.layers=QListWidget();self.layers.itemChanged.connect(self.layer_changed);self.layers.itemClicked.connect(lambda it:self.layer_combo.setCurrentText(it.text()));navtabs.addTab(self.layers,'Layers');self.nav.setWidget(navtabs);self.addDockWidget(Qt.LeftDockWidgetArea,self.nav)
        self.inspector=QDockWidget('INSPECTOR',self);self.inspector.setObjectName('inspector');self.inspector.setMinimumWidth(230);self.form_host=QWidget();self.form=QFormLayout(self.form_host);self.form.setContentsMargins(14,14,14,14);self.form.setVerticalSpacing(10);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.form_host);self.inspector.setWidget(scroll);self.addDockWidget(Qt.RightDockWidgetArea,self.inspector)
        self.results_dock=QDockWidget('RESULTS',self);self.results_dock.setObjectName('results');self.results_tabs=QTabWidget();self.results_dock.setWidget(self.results_tabs);self.addDockWidget(Qt.BottomDockWidgetArea,self.results_dock)
        wavepage=QWidget();wavevl=QVBoxLayout(wavepage);wavevl.setContentsMargins(12,5,12,5);bar=QHBoxLayout();self.run_combo=QComboBox();self.run_combo.setMinimumWidth(280);self.run_combo.currentIndexChanged.connect(self.select_run);bar.addWidget(self.run_combo);self.compare_check=QCheckBox('Compare previous');self.compare_check.toggled.connect(self.update_plot);bar.addWidget(self.compare_check);bar.addStretch();self.result_status=QLabel('No analysis yet');bar.addWidget(self.result_status);wavevl.addLayout(bar)
        split=QSplitter();self.traces=QListWidget();self.traces.setMaximumWidth(190);self.traces.itemChanged.connect(self.update_plot);self.traces.itemClicked.connect(self.trace_selected);self.plot=WavePlot();self.plot.cursor_changed.connect(lambda t:self.cursor_label.setText(t));split.addWidget(self.traces);split.addWidget(self.plot);wavevl.addWidget(split);self.cursor_label=QLabel('Click the plot for cursor A; right-click for cursor B.');self.cursor_label.setWordWrap(True);wavevl.addWidget(self.cursor_label);self.results_tabs.addTab(wavepage,'Waveforms')
        checkpage=QWidget();cv=QVBoxLayout(checkpage);self.check_note=QLabel('ERC, geometry DRC, and device mapping checks. Foundry LVS is separate.');self.check_note.setWordWrap(True);cv.addWidget(self.check_note);self.checks=QTableWidget(0,4);self.checks.setHorizontalHeaderLabels(['Severity','Rule','Details','Waiver']);self.checks.horizontalHeader().setStretchLastSection(True);self.checks.setColumnWidth(2,600);self.checks.setEditTriggers(QAbstractItemView.NoEditTriggers);self.checks.setSelectionBehavior(QAbstractItemView.SelectRows);self.checks.cellClicked.connect(self.check_selected);cv.addWidget(self.checks);waive=QPushButton('Waive selected violation for this revision…');waive.clicked.connect(self.waive);cv.addWidget(waive);self.results_tabs.addTab(checkpage,'Checks')
        self.console=QPlainTextEdit();self.console.setReadOnly(True);self.console.setMaximumBlockCount(5000);self.results_tabs.addTab(self.console,'Job log');self.results_dock.setMinimumHeight(230)
        self.progress=QProgressBar();self.progress.setMaximumWidth(140);self.progress.setMaximumHeight(14);self.progress.hide();self.statusBar().addPermanentWidget(self.progress);self.save_label=QLabel('Example • not saved');self.statusBar().addPermanentWidget(self.save_label);self.statusBar().showMessage('Select a device to edit parameters. Press F to fit the canvas.')
        self.resizeDocks([self.nav,self.inspector],[225,270],Qt.Horizontal);self.resizeDocks([self.results_dock],[270],Qt.Vertical)
    def action(self,menu,text,fn,shortcut=None,icon=None):
        a=QAction(text,self)
        if shortcut:a.setShortcut(QKeySequence(shortcut))
        if icon:a.setIcon(self.style().standardIcon(icon))
        a.triggered.connect(lambda checked=False:self.guard(fn));menu.addAction(a);return a
    def make_actions(self):
        f=self.menuBar().addMenu('&File');self.action(f,'New project…',self.new_project,'Ctrl+N');self.action(f,'Open project…',self.open_project,'Ctrl+O');self.action(f,'Save',self.save,'Ctrl+S',QStyle.SP_DialogSaveButton);self.action(f,'Save as…',lambda:self.save(True),'Ctrl+Shift+S');f.addSeparator();self.action(f,'Import GDSII / OASIS…',self.import_gds);self.action(f,'Export reproducible handoff…',self.handoff,'Ctrl+E');self.action(f,'Export SPICE deck…',self.export_spice);self.action(f,'Export GDSII / OASIS…',self.export_gds);self.action(f,'Export Xschem package…',self.export_sch);self.action(f,'Export waveform CSV…',self.export_wave);self.action(f,'Save canvas image…',self.export_image);f.addSeparator();self.action(f,'Retry recovery save',self.retry_recovery);self.action(f,'Choose recovery folder…',self.choose_recovery_folder);self.action(f,'Quit',self.close,'Ctrl+Q')
        ed=self.menuBar().addMenu('&Edit');self.undo_action=self.action(ed,'Undo',self.undo,'Ctrl+Z',QStyle.SP_ArrowBack);self.redo_action=self.action(ed,'Redo',self.redo,'Ctrl+Shift+Z',QStyle.SP_ArrowForward);self.action(ed,'Duplicate',self.duplicate,'Ctrl+D');self.action(ed,'Delete selection',self.delete);self.action(ed,'Rotate 90°',self.rotate);self.action(ed,'Rename project…',self.rename_project);self.action(ed,'Command palette…',self.command_palette,'Ctrl+K')
        design=self.menuBar().addMenu('&Design');self.action(design,'Add cell…',self.add_cell);self.action(design,'Instantiate cell…',self.instantiate_cell);self.action(design,'Set active cell as top',lambda:self.commit(lambda p:p.update(top=self.cid),'Set top cell'));self.action(design,'Edit cell ports…',self.edit_ports);self.action(design,'Generate generic MOS geometry…',self.generate_mos);self.action(design,'Generate metal guard ring…',self.generate_ring);self.action(design,'Create layout array…',self.array_shapes)
        boolean=design.addMenu('Boolean geometry')
        for label,op in [('Union','union'),('Subtract from first','subtract'),('Intersection','intersection'),('Exclusive OR','xor')]:self.action(boolean,label,lambda o=op:self.boolean(o))
        analysis=self.menuBar().addMenu('&Analysis');self.run_action=self.action(analysis,'Run analysis…',self.run_dialog,'F5',QStyle.SP_MediaPlay);self.cancel_action=self.action(analysis,'Cancel job',self.cancel_job,'Shift+F5',QStyle.SP_MediaStop);self.action(analysis,'Electrical rule check',lambda:self.check('erc'),'F6');self.action(analysis,'Geometry DRC (generic rules)',lambda:self.check('drc'),'F7');self.action(analysis,'Device mapping audit',lambda:self.check('mapping'))
        tools=self.menuBar().addMenu('&Tools');self.action(tools,'Engine diagnostics & paths…',self.engine_dialog);self.action(tools,'Import technology descriptor…',self.import_technology);self.action(tools,'Technology & qualification status',self.pdk_status);self.action(tools,'Convert GDS through Magic…',self.magic_dialog);self.action(tools,'Compare netlists with Netgen…',self.lvs_dialog)
        view=self.menuBar().addMenu('&View');self.action(view,'Fit design',lambda:(self.schematic.fit(),self.layout.fit()));self.theme_action=self.action(view,'Toggle light / dark',self.toggle_theme,'Ctrl+Shift+T');view.addAction(self.nav.toggleViewAction());view.addAction(self.inspector.toggleViewAction());view.addAction(self.results_dock.toggleViewAction())
        helpmenu=self.menuBar().addMenu('&Help');self.action(helpmenu,'Searchable help…',self.help_dialog,'F1');self.action(helpmenu,'About & release status',self.about)
        self.toolbar.addAction(self.undo_action);self.toolbar.addAction(self.redo_action);self.toolbar.addSeparator();self.tool_combo=QComboBox();self.tool_combo.addItems(['Select','Connect pins','Rectangle','Polygon','Path','Ruler']);self.tool_combo.currentIndexChanged.connect(self.change_tool);self.toolbar.addWidget(self.tool_combo)
        self.add_combo=QComboBox();self.add_combo.addItems(['Add device…','R · Resistor','C · Capacitor','L · Inductor','V · Voltage source','I · Current source','NMOS','PMOS']);self.add_combo.activated.connect(self.add_device);self.toolbar.addWidget(self.add_combo);self.layer_combo=QComboBox();self.layer_combo.addItems([l['name'] for l in self.project['pdk']['layers']]);self.layer_combo.setCurrentText('metal1');self.layer_combo.currentTextChanged.connect(lambda text:setattr(self.layout,'layer',text));self.toolbar.addWidget(self.layer_combo);self.toolbar.addSeparator();self.toolbar.addAction(self.run_action);self.toolbar.addAction(self.cancel_action);self.cancel_action.setEnabled(False)
        for canvas in (self.schematic,self.layout):
            QShortcut(QKeySequence('Delete'),canvas,activated=lambda:self.guard(self.delete)).setContext(Qt.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence('R'),self.schematic,activated=lambda:self.guard(self.rotate)).setContext(Qt.WidgetWithChildrenShortcut)
    def apply_theme(self):
        bg='#202935' if self.dark else '#ffffff';fg='#dae5ef' if self.dark else '#293c4e';line='#34404e' if self.dark else '#e0e6ec';alt='#18212b' if self.dark else '#f3f6f8';muted='#93a6b8' if self.dark else '#738395'
        self.setStyleSheet(f'''QMainWindow,QDialog,QWidget {{font-family:"Inter","Segoe UI","DejaVu Sans";font-size:13px;color:{fg};background:{bg};}} QMenuBar,QMenu,QToolBar{{background:{bg};}} QToolBar{{spacing:8px;padding:9px;border-bottom:1px solid {line};}} QToolButton,QPushButton{{padding:7px 10px;border:1px solid {line};border-radius:5px;background:{bg};}} QToolButton:hover,QPushButton:hover{{background:{alt};border-color:#20a89b;}} QPushButton:default{{background:#138c82;color:white;border-color:#138c82;}} QLineEdit,QComboBox,QSpinBox{{padding:6px;border:1px solid {line};border-radius:4px;background:{alt};selection-background-color:#138c82;}} QTreeWidget,QListWidget,QTableWidget,QPlainTextEdit{{background:{bg};border:none;selection-background-color:#174e4d;selection-color:white;}} QTreeWidget::item,QListWidget::item{{padding:6px 3px;}} QDockWidget::title{{padding:10px;font-size:11px;letter-spacing:1px;color:{muted};background:{alt};}} QTabWidget::pane{{border:1px solid {line};}} QTabBar::tab{{padding:9px 16px;background:{alt};border-bottom:2px solid transparent;}} QTabBar::tab:selected{{background:{bg};border-bottom:2px solid #19a79a;}} QLabel#projectTitle{{font-size:19px;font-weight:600;}} QLabel#revisionLabel{{color:{muted};padding-left:12px;font-size:12px;}} QStatusBar{{background:{alt};border-top:1px solid {line};font-size:12px;}} QHeaderView::section{{background:{alt};padding:7px;border:none;}} QSplitter::handle{{background:{line};}} QScrollArea{{border:none;}} QProgressBar{{border:none;background:{alt};}} QProgressBar::chunk{{background:#19a79a;}}''')
        for c in (self.schematic,self.layout):c.dark=self.dark;c.update()
        self.plot.dark=self.dark;self.plot.update()
    def toggle_theme(self):self.dark=not self.dark;self.settings.setValue('appearance/theme','dark' if self.dark else 'light');self.apply_theme()
    def refresh(self,fit=False):
        self.rebuilding=True
        if not any(c['id']==self.cid for c in self.project['cells']):self.cid=self.project['top']
        self.project_label.setText(self.project['name']);self.revision_label.setText(f'r{self.project["revision"]}  /  {self.project["pdk"]["name"]}');self.setWindowTitle(self.project['name']+' — IC Design Studio 0.1.0');self.cell_combo.clear()
        self.tree.clear();root=QTreeWidgetItem(self.tree,[self.project['name']]);root.setExpanded(True)
        for c in self.project['cells']:
            self.cell_combo.addItem(c['name'],c['id']);item=QTreeWidgetItem(root,[c['name']+('  · top' if c['id']==self.project['top'] else '')]);item.setData(0,Qt.UserRole,('cell',c['id']));item.setExpanded(c['id']==self.cid)
            for d in c['devices']:
                it=QTreeWidgetItem(item,[d['name']+'  '+d['kind']]);it.setData(0,Qt.UserRole,('device',c['id'],d['id']))
        self.cell_combo.setCurrentIndex(next(i for i,c in enumerate(self.project['cells']) if c['id']==self.cid));self.schematic.set_data(self.cell,self.project['pdk'],self.selection,self.net);self.layout.set_data(self.cell,self.project['pdk'],self.selection,self.net,revision=self.project['revision'])
        self.layers.blockSignals(True);self.layers.clear()
        for l in self.project['pdk']['layers']:
            it=QListWidgetItem(l['name']);it.setForeground(QColor(l['color']));it.setFlags(it.flags()|Qt.ItemIsUserCheckable);it.setCheckState(Qt.Checked if l['name'] in self.layout.visible_layers else Qt.Unchecked);self.layers.addItem(it)
        self.layers.blockSignals(False);self.undo_action.setEnabled(bool(self.history.undo_stack));self.redo_action.setEnabled(bool(self.history.redo_stack));self.update_save_status();self.rebuilding=False;self.build_inspector();self.update_result_status()
        if fit:QTimer.singleShot(20,lambda:(self.schematic.fit(),self.layout.fit()))
    def commit(self,fn,label='Edit'):
        self.history.commit(fn,label)
        self.queue_recovery()
        self.refresh()
    def undo(self):self.history.undo();self.persist_history()
    def redo(self):self.history.redo();self.persist_history()
    def persist_history(self):
        self.queue_recovery()
        self.refresh()
    def select(self,ids,mode=None):
        self.selection=ids;self.current_mode=mode or self.current_mode;self.net='';self.schematic.set_data(self.cell,self.project['pdk'],ids);self.layout.set_data(self.cell,self.project['pdk'],ids,revision=self.project['revision']);self.build_inspector()
    def change_mode(self,i):
        self.schematic.setVisible(i!=1);self.layout.setVisible(i!=0);self.current_mode='layout' if i==1 else 'schematic';QTimer.singleShot(10,lambda:(self.schematic.fit(),self.layout.fit()));self.build_inspector()
    def change_tool(self,i):
        tool=['select','connect','rect','polygon','path','ruler'][i];self.schematic.tool=tool if tool in ('select','connect','ruler') else 'select';self.layout.tool=tool if tool!='connect' else 'select'
        if tool in ('rect','polygon','path'):self.mode_combo.setCurrentIndex(1)
        if tool=='connect':self.mode_combo.setCurrentIndex(0)
        self.statusBar().showMessage('Click vertices; Enter or double-click finishes. Esc cancels.' if tool in ('polygon','path') else 'Click two device pins to connect their nets.' if tool=='connect' else tool.title())
    def layer_changed(self,it):
        if it.checkState()==Qt.Checked:self.layout.visible_layers.add(it.text())
        else:self.layout.visible_layers.discard(it.text())
        self.layout.update()
    def switch_cell_combo(self,i):
        if self.rebuilding or i<0:return
        self.cid=self.cell_combo.itemData(i);self.selection=[];self.net='';self.refresh(True)
    def tree_clicked(self,it,col):
        data=it.data(0,Qt.UserRole)
        if not data:return
        self.cid=data[1];self.selection=[data[2]] if data[0]=='device' else [];self.refresh(data[0]=='cell')
    def clear_form(self):
        while self.form.count():
            item=self.form.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.form_fields={}
    def field(self,label,value,key=None):
        edit=QLineEdit(str(value));edit.setAccessibleName(label);self.form.addRow(label,edit);self.form_fields[key or label]=edit;return edit
    def build_inspector(self):
        self.clear_form();obj=next((o for o in self.cell['devices']+self.cell['shapes'] if o['id'] in self.selection),None)
        if not obj:
            title=QLabel(self.cell['name']);title.setStyleSheet('font-size:18px;font-weight:600;');self.form.addRow(title);self.form.addRow('Devices',QLabel(str(len(self.cell['devices']))));self.form.addRow('Layout shapes',QLabel(str(len(self.cell['shapes']))));self.form.addRow('Ports',QLabel(', '.join(self.cell['ports']) or 'None'));note=QLabel('Select a device or shape to inspect it.\n\nConnections are defined by pin net names. Ground is 0.');note.setWordWrap(True);self.form.addRow(note);return
        if len(self.selection)>1:self.form.addRow(QLabel(f'{len(self.selection)} objects selected. Editing first.'))
        self.inspected_id=obj['id'];is_device='nets' in obj
        if is_device:
            self.form.addRow(QLabel(obj['kind']+' instance'));self.field('Name',obj['name']);self.field('X',obj['x']);self.field('Y',obj['y'])
            if obj['kind'] not in ('NMOS','PMOS','X'):self.field('Value',obj['value'])
            for pin,n in obj['nets'].items():self.field('Net · '+pin,n,'net:'+pin)
            if obj['kind'] in ('NMOS','PMOS'):
                for k in ('w','l','vto','kp','lambda'):self.field(k,obj['params'][k],'param:'+k)
            if obj['kind'] in ('V','I'):
                combo=QComboBox();combo.addItems(['dc','pulse','sine']);combo.setCurrentText(obj['source']['type']);self.form.addRow('Waveform',combo);self.form_fields['source:type']=combo
                for k in ('low','high','period','delay','duty','ac'):self.field(k,obj['source'][k],'source:'+k)
        else:
            self.form.addRow(QLabel(obj['kind'].title()+' · integer nanometres'));combo=QComboBox();combo.addItems([l['name'] for l in self.project['pdk']['layers']]);combo.setCurrentText(obj['layer']);self.form.addRow('Layer',combo);self.form_fields['layer']=combo;self.field('Net',obj.get('net',''));self.field('Linked device ID',obj.get('device_id',''));self.field('Vertices',json.dumps(obj['points']))
            if obj['kind']=='path':self.field('Width (nm)',obj['width'])
        apply=QPushButton('Apply changes');apply.setDefault(True);apply.clicked.connect(lambda:self.guard(lambda:self.apply_inspector(is_device)));self.form.addRow(apply)
        note=QLabel('Stable ID\n'+obj['id']);note.setTextInteractionFlags(Qt.TextSelectableByMouse);note.setStyleSheet('font-size:11px;color:#7e91a2;');self.form.addRow(note)
    def apply_inspector(self,is_device):
        values={k:(w.currentText() if isinstance(w,QComboBox) else w.text().strip()) for k,w in self.form_fields.items()};oid=self.inspected_id
        def edit(p):
            c=next(c for c in p['cells'] if c['id']==self.cid);o=next(o for o in c['devices' if is_device else 'shapes'] if o['id']==oid)
            if is_device:
                o['name']=values['Name'];o['x']=float(values['X']);o['y']=float(values['Y'])
                if 'Value' in values:o['value']=values['Value']
                for key,val in values.items():
                    if key.startswith('net:'):o['nets'][key[4:]]=val
                    elif key.startswith('param:'):o['params'][key[6:]]=val
                    elif key.startswith('source:'):o['source'][key[7:]]=val
            else:
                o['layer']=values['layer'];o['net']=values['Net'];o['device_id']=values['Linked device ID'];o['points']=json.loads(values['Vertices'])
                if 'Width (nm)' in values:o['width']=int(values['Width (nm)'])
        self.commit(edit,'Edit properties')
    def add_device(self,index):
        if index==0:return
        kind=['','R','C','L','V','I','NMOS','PMOS'][index];prefix='MN' if kind=='NMOS' else 'MP' if kind=='PMOS' else kind;names={d['name'] for d in self.cell['devices']};n=1
        while prefix+str(n) in names:n+=1
        pos=self.schematic.snap(self.schematic.model(self.schematic.rect().center()));d=device(kind,prefix+str(n),pos.x(),pos.y());self.commit(lambda p:next(c for c in p['cells'] if c['id']==self.cid)['devices'].append(d),'Add device');self.select([d['id']],'schematic');self.mode_combo.setCurrentIndex(0);self.add_combo.setCurrentIndex(0)
    def add_shape(self,s):self.guard(lambda:self.commit(lambda p:next(c for c in p['cells'] if c['id']==self.cid)['shapes'].append(s),'Draw geometry'))
    def move(self,ids,dx,dy,mode):
        def change(p):
            c=next(c for c in p['cells'] if c['id']==self.cid)
            for o in c['devices' if mode=='schematic' else 'shapes']:
                if o['id'] in ids:
                    if mode=='schematic':o['x']+=dx;o['y']+=dy
                    else:
                        o['points']=[[x+int(dx),y+int(dy)] for x,y in o['points']]
                        o['holes']=[[[x+int(dx),y+int(dy)] for x,y in h] for h in o.get('holes',[])]
        self.guard(lambda:self.commit(change,'Move selection'))
    def connect(self,a,ap,b,bp):
        if a==b and ap==bp:return
        def edit(p):
            c=next(c for c in p['cells'] if c['id']==self.cid);da=next(d for d in c['devices'] if d['id']==a);db=next(d for d in c['devices'] if d['id']==b);db['nets'][bp]=da['nets'][ap]
        self.guard(lambda:self.commit(edit,'Connect pins'))
    def delete(self):
        if not self.selection:return
        focus=QApplication.focusWidget()
        if isinstance(focus,(QLineEdit,QPlainTextEdit)):return
        ids=set(self.selection)
        def change(p):
            c=next(c for c in p['cells'] if c['id']==self.cid);c['devices']=[d for d in c['devices'] if d['id'] not in ids];c['shapes']=[s for s in c['shapes'] if s['id'] not in ids]
            for s in c['shapes']:
                if s.get('device_id') in ids:s['device_id']=''
        self.selection=[];self.commit(change,'Delete objects')
    def rotate(self):
        def edit(p):
            c=next(c for c in p['cells'] if c['id']==self.cid)
            for d in c['devices']:
                if d['id'] in self.selection:d['rotation']=(d['rotation']+90)%360
        self.commit(edit,'Rotate devices')
    def duplicate(self):
        selected=set(self.selection);newids=[]
        def edit(p):
            c=next(c for c in p['cells'] if c['id']==self.cid);names={d['name'] for d in c['devices']}
            for group in ('devices','shapes'):
                for obj in list(c[group]):
                    if obj['id'] not in selected:continue
                    o=clone(obj);o['id']=uid();newids.append(o['id'])
                    if group=='devices':
                        i=2
                        while o['name']+'_'+str(i) in names:i+=1
                        o['name']+='_'+str(i);names.add(o['name']);o['x']+=40;o['y']+=40
                    else:o['points']=[[x+500,y+500] for x,y in o['points']];o['holes']=[[[x+500,y+500] for x,y in h] for h in o.get('holes',[])]
                    c[group].append(o)
        self.commit(edit,'Duplicate');self.select(newids)
    def set_project(self,p,path=None):
        self.reset_recovery_status()
        self._disk_hash=file_digest(path) if path and Path(path).is_file() else None
        self.history=History(p);self.cid=p['top'];self.path=Path(path) if path else None;self.saved_hash=digest(p) if path else None;self.selection=[];self.net='';self.jobs=[];self.result=None;self.run_combo.clear();self.plot.result=None;self.plot.update();self.traces.clear();self.layer_combo.clear();self.layer_combo.addItems([l['name'] for l in p['pdk']['layers']]);self.layout.visible_layers={l['name'] for l in p['pdk']['layers']};self.issues=[];self.checks.setRowCount(0);self.refresh(True)
        for f in sorted((self.jobs_dir/p['id']).glob('*/result.json'),key=lambda f:f.stat().st_mtime_ns)[-30:]:
            try:
                r=job_store.read_result(f,p['id']);self.add_result(r)
            except Exception:pass
    def maybe_save(self):
        if self.saved_hash==digest(self.project):return True
        answer=QMessageBox.question(self,'Save project?','Save changes to '+self.project['name']+'?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
        if answer==QMessageBox.Cancel:return False
        if answer==QMessageBox.Save:return bool(self.save())
        self.clear_recovery();return True
    def new_project(self):
        template,ok=QInputDialog.getItem(self,'New project','Start from',['Empty circuit','RC low-pass example','CMOS inverter example'],0,False)
        if not ok or not self.maybe_save():return
        self.set_project(example({'Empty circuit':'empty','RC low-pass example':'rc','CMOS inverter example':'inverter'}[template]))
    def open_project(self):
        path,_=QFileDialog.getOpenFileName(self,'Open project',str(self.path.parent) if self.path else '', 'IC Studio projects (*.icproj)')
        if path:
            p=load_project(path)
            if self.maybe_save():self.set_project(p,path)
    def save(self,as_new=False):
        path=self.path
        if path is None or as_new:
            name,_=QFileDialog.getSaveFileName(self,'Save project',str(path or (self.project['name']+'.icproj')),'IC Studio project (*.icproj)')
            if not name:return False
            path=Path(name)
            if path.suffix.lower()!='.icproj':path=path.with_suffix('.icproj')
        if not as_new and self.path and self._disk_hash and Path(path).exists() and file_digest(path)!=self._disk_hash:raise ValueError('This project changed on disk in another application. Use Save As to preserve your edits, then review both versions.')
        if Path(path).suffix=='.icstudio':
            from .project_store import save_directory
            save_directory(self.project,Path(path).parent)
        else:save_project(self.project,path)
        self._disk_hash=file_digest(path);self.path=path;self.saved_hash=digest(self.project);self.clear_recovery();self.settings.setValue('last_project',str(path));self.refresh();return True
    def clear_recovery(self):
        self.finish_recovery(discard=True)
        self.reset_recovery_status()
        recovery.clear(self.recovery_dir/(self.project['id']+'.icproj'))
        if self._recovered_from:recovery.clear(self._recovered_from);self._recovered_from=None
    def offer_recovery(self):
        roots=[self.recovery_root]+[Path(v) for v in self.settings.value('storage/previous_recovery_roots',[]) or []]
        unique={}
        for root in roots:
            for row in recovery.candidates(root):unique[str(row[0].resolve())]=row
        items=sorted(unique.values(),key=lambda row:row[0].stat().st_mtime,reverse=True)
        if not items:return
        choices=[f'{i+1}. {p["name"]} · revision {p["revision"]}'+(' · previous valid snapshot' if fallback else '') for i,(_,p,fallback) in enumerate(items)]
        choice,ok=QInputDialog.getItem(self,'Recover edits','Recover an interrupted session (the saved project remains unchanged):',choices,0,False)
        if ok:
            path,p,_=items[choices.index(choice)];self.set_project(p);self._recovered_from=path
    def rename_project(self):
        name,ok=QInputDialog.getText(self,'Rename project','Project name',text=self.project['name'])
        if ok:self.commit(lambda p:p.update(name=name.strip()),'Rename project')
    def add_cell(self):
        name,ok=QInputDialog.getText(self,'New cell','Unique cell name')
        if not ok:return
        c={'id':uid(),'name':name.strip(),'ports':[],'devices':[],'shapes':[]};self.commit(lambda p:p['cells'].append(c),'Add cell');self.cid=c['id'];self.selection=[];self.refresh(True)
    def edit_ports(self):
        ports,ok=QInputDialog.getText(self,'Cell ports','Space-separated external net names (e.g. in out vdd vss)',text=' '.join(self.cell['ports']))
        if not ok:return
        new=ports.split()
        def edit(p):
            target=next(c for c in p['cells'] if c['id']==self.cid);target['ports']=new
            if target.get('symbol'):
                from .symbol_editor import default_symbol
                positions=default_symbol(new)['pins'];target['symbol']['pins']={pin:target['symbol']['pins'].get(pin,positions[pin]) for pin in new}
            for c in p['cells']:
                for d in c['devices']:
                    if d['kind']=='X' and d['cell']==self.cid:
                        d['nets']={pin:d['nets'].get(pin,'0') for pin in new};d.pop('symbol',None)
        self.commit(edit,'Change cell ports')
    def instantiate_cell(self):
        choices=[c for c in self.project['cells'] if c['id']!=self.cid and c['ports']]
        if not choices:raise ValueError('Create another cell with external ports first.')
        name,ok=QInputDialog.getItem(self,'Instantiate cell','Cell',[c['name'] for c in choices],0,False)
        if not ok:return
        target=next(c for c in choices if c['name']==name);i=1
        while any(d['name']==f'X{i}' for d in self.cell['devices']):i+=1
        d=device('X',f'X{i}',400,300,cell=target['id'],nets={pin:'0' for pin in target['ports']});self.commit(lambda p:next(c for c in p['cells'] if c['id']==self.cid)['devices'].append(d),'Instantiate cell');self.select([d['id']]);self.mode_combo.setCurrentIndex(0)
    def generate_mos(self):
        from .layout import generate_mos
        ds=[d for d in self.cell['devices'] if d['id'] in self.selection and d['kind'] in ('NMOS','PMOS')]
        if not ds:raise ValueError('Select a MOS device in the schematic first.')
        if self.project['pdk']['revision']!='generic-1':raise ValueError('This generator is only available for the generic teaching technology.')
        fingers,ok=QInputDialog.getInt(self,'Generic MOS geometry','Fingers (illustrative geometry, unqualified)',1,1,64)
        if not ok:return
        shapes=[]
        for i,d in enumerate(ds):shapes.extend(generate_mos(d,i*6000,0,fingers))
        self.commit(lambda p:next(c for c in p['cells'] if c['id']==self.cid)['shapes'].extend(shapes),'Generate MOS geometry');self.mode_combo.setCurrentIndex(2);QTimer.singleShot(30,self.layout.fit)
    def generate_ring(self):
        from .layout import guard_ring
        values=self.simple_form('Metal guard ring',{'X (nm)':'0','Y (nm)':'0','Outer width (nm)':'6000','Outer height (nm)':'5000','Thickness (nm)':'300','Net':'0'})
        if not values:return
        if 'metal1' not in [l['name'] for l in self.project['pdk']['layers']]:raise ValueError('This generator requires a metal1 layer.')
        shapes=guard_ring(int(values['X (nm)']),int(values['Y (nm)']),int(values['Outer width (nm)']),int(values['Outer height (nm)']),int(values['Thickness (nm)']),values['Net']);self.commit(lambda p:next(c for c in p['cells'] if c['id']==self.cid)['shapes'].extend(shapes),'Generate ring');self.mode_combo.setCurrentIndex(1);QTimer.singleShot(30,self.layout.fit)
    def array_shapes(self):
        shapes=[s for s in self.cell['shapes'] if s['id'] in self.selection]
        if not shapes:raise ValueError('Select layout shapes first.')
        vals=self.simple_form('Layout array',{'Columns':'2','Rows':'2','X pitch (nm)':'4000','Y pitch (nm)':'4000'})
        if not vals:return
        cols=int(vals['Columns']);rows=int(vals['Rows']);dx=int(vals['X pitch (nm)']);dy=int(vals['Y pitch (nm)'])
        if not 1<=cols<=64 or not 1<=rows<=64 or cols*rows*len(shapes)>10000:raise ValueError('Keep arrays within 10,000 shapes and 64 rows/columns.')
        new=[]
        for x in range(cols):
            for y in range(rows):
                if x==y==0:continue
                for s in shapes:
                    o=clone(s);o['id']=uid();o['points']=[[a+x*dx,b+y*dy] for a,b in s['points']];o['holes']=[[[a+x*dx,b+y*dy] for a,b in h] for h in s.get('holes',[])];new.append(o)
        self.commit(lambda p:next(c for c in p['cells'] if c['id']==self.cid)['shapes'].extend(new),'Create array')
    def boolean(self,op):
        from .layout import boolean
        shapes=[next(s for s in self.cell['shapes'] if s['id']==i) for i in self.selection if any(s['id']==i for s in self.cell['shapes'])];result=boolean(shapes,op);ids={s['id'] for s in shapes}
        def edit(p):
            c=next(c for c in p['cells'] if c['id']==self.cid);c['shapes']=[s for s in c['shapes'] if s['id'] not in ids]+result
        self.commit(edit,'Boolean '+op);self.select([s['id'] for s in result],'layout')
    def simple_form(self,title,values,description=None):
        dlg=QDialog(self);dlg.setWindowTitle(title);dlg.setMinimumWidth(450);layout=QVBoxLayout(dlg)
        if description:lab=QLabel(description);lab.setWordWrap(True);layout.addWidget(lab)
        form=QFormLayout();fields={}
        for k,v in values.items():
            edit=QLineEdit(str(v));form.addRow(k,edit);fields[k]=edit
        layout.addLayout(form);buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);layout.addWidget(buttons)
        return {k:w.text().strip() for k,w in fields.items()} if dlg.exec()==QDialog.Accepted else None
    def run_dialog(self):
        if self.process:raise ValueError('A job is running. Cancel or wait for it before starting another.')
        dlg=QDialog(self);dlg.setWindowTitle('Analysis setup');dlg.setMinimumWidth(480);v=QVBoxLayout(dlg);note=QLabel('Built-in analysis uses generic circuit models. Linked PDK devices use their locked models through ngspice.');note.setWordWrap(True);v.addWidget(note);f=QFormLayout();typ=QComboBox();types=['tran','op','dc','ac','noise'];typ.addItems(['Transient','Operating point','DC sweep','AC response','Resistor thermal noise']);typ.setCurrentIndex(types.index(self.project['analysis']['type']));f.addRow('Analysis',typ);engine=QComboBox();engine.addItems(['Built-in teaching solver','ngspice']);f.addRow('Engine',engine);fields={}
        labels={'stop':'Stop time','step':'Time step','dc_start':'DC start','dc_stop':'DC stop','dc_step':'DC step','start':'Start frequency','end':'End frequency','points':'Frequency points','temperature':'Temperature (°C)'}
        for k,label in labels.items():ed=QLineEdit(str(self.project['analysis'][k]));fields[k]=ed;f.addRow(label,ed)
        src=QComboBox();src.addItems([d['name'] for d in flatten(self.project,self.cid) if d['kind'] in ('V','I')]);src.setCurrentText(self.project['analysis']['source']);f.addRow('DC source',src)
        def relevant(index):
            t=types[index]
            for k,ed in fields.items():
                visible=k in ({'stop','step'} if t=='tran' else {'dc_start','dc_stop','dc_step'} if t=='dc' else {'start','end','points','temperature'} if t=='noise' else {'start','end','points'} if t=='ac' else set());ed.setVisible(visible);f.labelForField(ed).setVisible(visible)
            src.setVisible(t=='dc');f.labelForField(src).setVisible(t=='dc')
        typ.currentIndexChanged.connect(relevant);relevant(typ.currentIndex());v.addLayout(f);buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Ok).setText('Run analysis');v.addWidget(buttons);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject)
        if dlg.exec()!=QDialog.Accepted:return
        settings=clone(self.project['analysis']);settings.update({k:w.text() for k,w in fields.items()});settings['type']=types[typ.currentIndex()];settings['source']=src.currentText();settings['points']=int(settings['points']);settings['temperature']=float(settings['temperature']);self.commit(lambda p:p.update(analysis=settings),'Analysis settings');self.start_job(settings,'ngspice' if engine.currentIndex() else 'builtin')
    def start_job(self,settings,engine='builtin'):
        if self.process:raise ValueError('Only one job may run at a time.')
        # Validate basic limits before spawning, including external jobs.
        if settings['type']=='tran':
            stop=scalar(settings['stop']);step=scalar(settings['step'])
            if not 0<step<=stop or stop/step>20000:raise ValueError('Use 1–20,000 transient steps.')
        if settings['type']=='dc':
            delta=scalar(settings['dc_stop'])-scalar(settings['dc_start']);step=scalar(settings['dc_step'])
            if step==0 or delta/step<0 or delta/step>5000:raise ValueError('Invalid DC sweep or more than 5,001 points.')
        if settings['type'] in ('ac','noise') and not (0<scalar(settings['start'])<scalar(settings['end']) and 2<=int(settings['points'])<=1000):raise ValueError('Invalid frequency range/points.')
        job_cell=self.cid
        if settings['type'] in ('testbench','silicon','characterization') and settings.get('testbench'):
            from .testbenches import get
            t=get(self.project,settings['testbench']);job_cell=t['dut_cell' if settings['type']=='silicon' else 'bench_cell']
        job={'project':clone(self.project),'cell':job_cell,'settings':settings,'engine':engine};executable=''
        if engine=='ngspice':
            executable=self.settings.value('engine/ngspice','') or shutil.which('ngspice')
            if not executable or not Path(executable).is_file():raise ValueError('ngspice is not installed. Configure it in Tools → Engine diagnostics & paths.')
            job['executable']=executable
        path=self.jobs_dir/self.project['id']/(now().replace(':','-')+'_'+uid());path.mkdir(parents=True);atomic_write(path/'input.json',json.dumps(job));job_store.state(path,'running');self.active_job=path;self.cancelled=False;self.process=QProcess(self);self.process.setProcessChannelMode(QProcess.MergedChannels);self.process.readyReadStandardOutput.connect(self.read_job_output);self.process.finished.connect(self.job_finished);self.process.errorOccurred.connect(self.job_process_error);self.job_buffer='';self.process.setWorkingDirectory(str(Path(__file__).parent.parent))
        args=['--worker',str(path/'input.json'),str(path/'result.json')]
        if not getattr(sys,'frozen',False):args=[str(Path(__file__).parent.parent/'main.py')]+args
        self.process.start(sys.executable,args);self.progress.setValue(0);self.progress.show();self.run_action.setEnabled(False);self.cancel_action.setEnabled(True);self.console.appendPlainText(f'Running {settings["type"]} · revision {self.project["revision"]} · {engine}');self.results_dock.show()
    def read_job_output(self):
        if not self.process:return
        self.job_buffer+=bytes(self.process.readAllStandardOutput()).decode('utf-8',errors='replace')
        while '\n' in self.job_buffer:
            line,self.job_buffer=self.job_buffer.split('\n',1)
            try:
                msg=json.loads(line)
                if 'progress' in msg:self.progress.setValue(int(msg['progress']*100));self.statusBar().showMessage(msg.get('message',''))
                if 'error' in msg:self.console.appendPlainText(msg['error'])
            except json.JSONDecodeError:self.console.appendPlainText(line)
    def job_process_error(self,error):
        if error==QProcess.FailedToStart:self.console.appendPlainText('Worker could not start. Check application installation.');self.job_finished(-1,QProcess.CrashExit)
    def job_finished(self,code,status):
        if not self.process:return
        self.read_job_output();path=self.active_job;cancelled=self.cancelled;self.process.deleteLater();self.process=None;self.progress.hide();self.run_action.setEnabled(True);self.cancel_action.setEnabled(False)
        if not cancelled and code==0 and (path/'result.json').exists():
            try:
                result=job_store.read_result(path/'result.json',self.project['id'],False);job_store.state(path,'complete');self.add_result(result);self.console.appendPlainText('Analysis completed. Result saved with immutable input and hashes.');self.results_tabs.setCurrentIndex(0)
            except Exception as e:job_store.state(path,'failed',error=str(e));self.console.appendPlainText('Result could not be opened: '+str(e));self.results_tabs.setCurrentIndex(2)
        else:job_store.state(path,'cancelled' if cancelled else 'failed',exit_code=code);self.console.appendPlainText('Job cancelled.' if cancelled else 'Job failed. Review the error above.');self.results_tabs.setCurrentIndex(2)
    def cancel_job(self):
        if not self.process:return
        self.cancelled=True;job_store.state(self.active_job,'cancelled')
        if os.name=='nt':subprocess.run(['taskkill','/PID',str(self.process.processId()),'/T','/F'],capture_output=True)
        else:self.process.terminate()
        target=self.process;QTimer.singleShot(2500,lambda:target.kill() if self.process is target and target.state()!=QProcess.NotRunning else None)
    def add_result(self,r):
        self.jobs.append(r);self.run_combo.addItem(f'{len(self.jobs):02d} · {r["settings"]["type"].upper()} · r{r["revision"]} · {r["created"][:19]}');self.run_combo.setCurrentIndex(len(self.jobs)-1)
    def select_run(self,i):
        if i<0 or i>=len(self.jobs):return
        self.result=self.jobs[i];self.traces.blockSignals(True);self.traces.clear()
        for j,name in enumerate(self.result['traces']):
            it=QListWidgetItem(name);it.setFlags(it.flags()|Qt.ItemIsUserCheckable);it.setCheckState(Qt.Checked);it.setForeground(QColor(COLORS[j%len(COLORS)]));self.traces.addItem(it)
        self.traces.blockSignals(False);self.update_plot();self.update_result_status()
    def update_plot(self,*_):
        if not self.result:return
        names=[self.traces.item(i).text() for i in range(self.traces.count()) if self.traces.item(i).checkState()==Qt.Checked];i=self.run_combo.currentIndex();old=self.jobs[i-1] if self.compare_check.isChecked() and i>0 else None
        from .plot import analysis_kind
        if old and (analysis_kind(old)!=analysis_kind(self.result) or old['cell_id']!=self.result['cell_id']):old=None
        self.plot.set_result(self.result,names,old);measure=[]
        for name in names[:3]:
            vals=self.result['traces'][name]
            if vals:
                rms=math.sqrt(sum(v*v for v in vals)/len(vals));measure.append(f'{name}: min {min(vals):.4g} · max {max(vals):.4g} · RMS {rms:.4g}')
        self.cursor_label.setText('   |   '.join(measure))
    def trace_selected(self,it):
        self.net=it.text();self.schematic.set_data(self.cell,self.project['pdk'],self.selection,self.net);self.layout.set_data(self.cell,self.project['pdk'],self.selection,self.net,revision=self.project['revision'])
    def update_result_status(self):
        if not self.result:self.result_status.setText('No analysis yet');return
        stale=self.result['design_hash']!=design_digest(self.project);self.result_status.setText(('STALE · rerun after edits' if stale else 'Current revision')+'  ·  '+self.result['engine']);self.result_status.setStyleSheet('color:#d79342;' if stale else 'color:#19a79a;')
        if self.check_revision is not None and self.check_revision!=self.project['revision']:self.check_note.setText('STALE CHECKS · Design changed. Run checks again. Existing waivers apply only to the old revision.')
    def check(self,typ):
        from .layout import drc,mapping_audit
        self.issues=erc(self.project,self.cid) if typ=='erc' else drc(self.project,self.cid) if typ=='drc' else mapping_audit(self.project,self.cid);self.check_revision=self.project['revision'];self.check_note.setText(f'{typ.upper()} · revision {self.check_revision} · {len(self.issues)} findings. '+('Width, spacing and grid only; unqualified technology rules.' if typ=='drc' else 'Mapping audit checks links, not extracted connectivity or LVS.' if typ=='mapping' else 'Connectivity sanity checks; simulation may reveal additional errors.'));self.fill_checks();self.results_dock.show();self.results_tabs.setCurrentIndex(1)
    def fill_checks(self):
        self.checks.setRowCount(len(self.issues));waivers={w['fingerprint']:w for w in self.project['waivers'] if w['revision']==self.check_revision}
        for i,issue in enumerate(self.issues):
            fp=issue.get('fingerprint') or digest({'revision':self.check_revision,'issue':issue});issue['fingerprint']=fp
            for j,value in enumerate([issue['severity'],issue['code'],issue['message'],waivers.get(fp,{}).get('reason','')]):self.checks.setItem(i,j,QTableWidgetItem(value))
    def check_selected(self,row,col):
        if row<len(self.issues) and self.check_revision==self.project['revision']:
            oid=self.issues[row].get('object');self.select([oid] if oid else []);s=next((s for s in self.cell['shapes'] if s['id']==oid),None)
            if s:self.mode_combo.setCurrentIndex(1);box=self.layout.bounds(s);self.layout.offset=__import__('PySide6.QtCore',fromlist=['QPointF']).QPointF(self.layout.rect().center())-box.center()*self.layout.scale;self.layout.update()
    def waive(self):
        row=self.checks.currentRow()
        if row<0 or row>=len(self.issues):return
        if self.check_revision!=self.project['revision']:raise ValueError('Rerun stale checks before applying a waiver.')
        reason,ok=QInputDialog.getText(self,'Record waiver','Reason (revision-specific; does not establish signoff)')
        if not ok:return
        if len(reason.strip())<3:raise ValueError('Provide a meaningful waiver reason.')
        # Waivers are review metadata and do not change the design revision.
        self.project['waivers'].append({'revision':self.check_revision,'fingerprint':self.issues[row]['fingerprint'],'reason':reason.strip(),'created':now()});self.save_recovery();self.fill_checks()
    def import_gds(self):
        path,_=QFileDialog.getOpenFileName(self,'Import physical layout','','Layout (*.gds *.gds2 *.oas)')
        if not path:return
        p,warnings=import_layout(path)
        if self.maybe_save():self.set_project(p);self.mode_combo.setCurrentIndex(1);self.console.appendPlainText('\n'.join(warnings));self.results_tabs.setCurrentIndex(2)
    def handoff(self):
        parent=QFileDialog.getExistingDirectory(self,'Choose parent for a new handoff folder')
        if not parent:return
        dest=Path(parent)/(re.sub('[^A-Za-z0-9_-]','_',self.project['name'])+f'_r{self.project["revision"]}_handoff');export_handoff(self.project,dest);QMessageBox.information(self,'Handoff exported',f'Exported to {dest}\n\nRead preservation-report.json for supported formats and limitations.');QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest)))
    def export_spice(self):
        path,_=QFileDialog.getSaveFileName(self,'Export simulation deck',self.cell['name']+'.cir','SPICE deck (*.cir *.spice)')
        if path:atomic_write(path,spice(self.project,self.cid,self.project['analysis']));self.statusBar().showMessage('SPICE deck exported.',8000)
    def export_gds(self):
        path,_=QFileDialog.getSaveFileName(self,'Export physical layout',self.project['name']+'.gds','GDSII (*.gds);;OASIS (*.oas)')
        if path:export_layout(self.project,path);self.statusBar().showMessage('Layout, sidecar and preservation report exported.',8000)
    def export_sch(self):
        path=QFileDialog.getExistingDirectory(self,'Choose Xschem package directory')
        if path:export_xschem(self.project,path);self.statusBar().showMessage('Xschem package exported; destination qualification is pending.',8000)
    def export_wave(self):
        if not self.result:raise ValueError('Run an analysis first.')
        path,_=QFileDialog.getSaveFileName(self,'Export waveform data','waveforms.csv','CSV (*.csv)')
        if path:export_csv(self.result,path)
    def export_image(self):
        path,_=QFileDialog.getSaveFileName(self,'Save canvas image',self.current_mode+'.png','PNG (*.png)')
        if path:
            if not (self.layout if self.current_mode=='layout' else self.schematic).grab().save(path):raise ValueError('Could not write image.')
    def engine_dialog(self):
        from .engines import diagnostics
        config={n:self.settings.value('engine/'+n,'') for n in ('ngspice','klayout','magic','netgen')};ds=diagnostics(config);vals=self.simple_form('Engine diagnostics & paths',{d['name']:d['path'] for d in ds},'KLayout geometry is bundled. These optional executable paths enable external tools. On Windows, Magic requires a separately configured Linux/WSL worker; automatic WSL management is not included.')
        if vals:
            for key,path in vals.items():
                if path and not Path(path).is_file():raise ValueError(f'{key}: executable path does not exist.')
            for key,path in vals.items():self.settings.setValue('engine/'+key,path)
            self.console.appendPlainText('\n'.join(d['name']+': '+d['status'] for d in diagnostics(vals)))
    def import_technology(self):
        path,_=QFileDialog.getOpenFileName(self,'Import technology descriptor','','JSON descriptor (*.json)')
        if not path:return
        tech=json.loads(Path(path).read_text());tech['status']='unqualified'
        if any(s['layer'] not in {l['name'] for l in tech['layers']} for c in self.project['cells'] for s in c['shapes']):raise ValueError('Technology lacks layers already used by this project. Import into an empty project or provide an explicit layer mapping.')
        self.commit(lambda p:p.update(pdk=tech),'Import technology');self.layer_combo.clear();self.layer_combo.addItems([l['name'] for l in tech['layers']]);self.layout.visible_layers={l['name'] for l in tech['layers']};self.refresh()
    def pdk_status(self):
        text=json.dumps(self.project['pdk'],indent=2)+'\n\nSKY130, GF180MCU, IHP SG13G2: not qualified or bundled. A layer descriptor does not install device models, rule decks, or extraction. Generic MOS geometry is illustrative only.';self.text_dialog('Technology status',text)
    def magic_dialog(self):
        if os.name=='nt':raise ValueError('Magic requires a managed Linux worker on Windows. This preview provides a Linux CLI adapter; automatic WSL integration is not implemented.')
        vals=self.simple_form('Magic native conversion',{'GDS file':'','Magic technology file':'','Top cell':self.cell['name'],'Output directory':''},'Runs an installed Magic executable with the chosen technology. Review conversion.log and resulting geometry in Magic; conversion is not signoff.')
        if not vals:return
        exe=self.settings.value('engine/magic','') or shutil.which('magic')
        if not exe:raise ValueError('Configure the Magic executable in Engine diagnostics.')
        for key in ('GDS file','Magic technology file'):
            if not Path(vals[key]).is_file():raise ValueError(key+' is missing.')
        if not vals['Output directory']:raise ValueError('Choose an output directory.')
        args=['magic','--executable',exe,'--gds',vals['GDS file'],'--technology',vals['Magic technology file'],'--top',vals['Top cell'],'--output',vals['Output directory']];self.start_cli_job(args,'Magic conversion')
    def lvs_dialog(self):
        vals=self.simple_form('Netgen LVS comparison',{'Schematic SPICE':'','Schematic cell':self.cell['name'],'Extracted SPICE':'','Layout cell':self.cell['name'],'Setup Tcl file':'','Output directory':''},'Provide a PDK-qualified setup and an already extracted layout netlist. This adapter preserves the raw Netgen report; it does not assert fabrication signoff.')
        if not vals:return
        exe=self.settings.value('engine/netgen','') or shutil.which('netgen')
        if not exe:raise ValueError('Configure the Netgen executable in Engine diagnostics.')
        for k in ('Schematic SPICE','Extracted SPICE','Setup Tcl file'):
            if not Path(vals[k]).is_file():raise ValueError(k+' is missing.')
        if not vals['Output directory']:raise ValueError('Choose an output directory.')
        self.start_cli_job(['lvs','--executable',exe,'--schematic',vals['Schematic SPICE'],'--schematic-cell',vals['Schematic cell'],'--extracted',vals['Extracted SPICE'],'--layout-cell',vals['Layout cell'],'--setup',vals['Setup Tcl file'],'--output',vals['Output directory']],'Netgen LVS')
    def start_cli_job(self,args,label):
        if self.process:raise ValueError('A job is already running.')
        path=self.jobs_dir/self.project['id']/('external_'+uid());path.mkdir(parents=True);self.active_job=path;job_store.state(path,'running');self.cancelled=False;self.job_buffer='';self.process=QProcess(self);self.process.setProcessChannelMode(QProcess.MergedChannels);self.process.readyReadStandardOutput.connect(self.read_job_output)
        def finished(code,status):
            if not self.process:return
            self.read_job_output();job_store.state(path,'cancelled' if self.cancelled else 'complete' if code==0 else 'failed',exit_code=code);self.console.appendPlainText(label+(' finished; inspect its report.' if code==0 else ' failed or cancelled.'));self.process.deleteLater();self.process=None;self.progress.hide();self.run_action.setEnabled(True);self.cancel_action.setEnabled(False)
        self.process.finished.connect(finished);self.process.errorOccurred.connect(lambda error:finished(-1,QProcess.CrashExit) if error==QProcess.FailedToStart else None);argv=['--cli']+args
        if not getattr(sys,'frozen',False):argv=[str(Path(__file__).parent.parent/'main.py')]+argv
        self.process.start(sys.executable,argv);self.progress.show();self.progress.setValue(0);self.run_action.setEnabled(False);self.cancel_action.setEnabled(True);self.results_tabs.setCurrentIndex(2);self.results_dock.show()
    def text_dialog(self,title,text):
        dlg=QDialog(self);dlg.setWindowTitle(title);dlg.resize(780,620);v=QVBoxLayout(dlg);search=QLineEdit();search.setPlaceholderText('Find in this document…');v.addWidget(search);edit=QPlainTextEdit(text);edit.setReadOnly(True);v.addWidget(edit)
        def find():
            cursor=edit.textCursor();cursor.movePosition(type(cursor).Start);edit.setTextCursor(cursor);edit.find(search.text())
        search.textChanged.connect(find);buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(dlg.reject);v.addWidget(buttons);dlg.exec()
    def help_dialog(self):
        path=Path(getattr(sys,'_MEIPASS',Path(__file__).parent.parent))/'docs'/'USER_GUIDE.md';self.text_dialog('IC Design Studio help',path.read_text() if path.exists() else 'Open docs/USER_GUIDE.md in the source package.')
    def about(self):
        self.text_dialog('About IC Design Studio',f'IC Design Studio {__version__}\nStandalone engineering preview\n\nNative Qt 6 desktop interface (PySide6), C++20 matrix solver, KLayout geometry library. No web server, account, or cloud connection is required.\n\nImplemented: manual wires, placed net labels and ground, whole-net inspection, session recovery, undo/redo, simulation/studies, layout editing, PDK bindings and a verified SKY130 standard-cell reference flow.\n\nNot a professional 1.0 or tapeout tool. General PDK qualification, unrestricted scripted-library exchange, million-shape performance, signed distribution, Windows execution and external pilot gates remain open. See the release notes for the exact verified reference flow.\n\nNative core: '+('loaded' if __import__('icstudio.simulation',fromlist=['CORE']).CORE else 'Python fallback')+'\n\nQt / PySide6: LGPLv3 and component licenses. KLayout: GPLv2 or later. See THIRD_PARTY_NOTICES.md and bundled licenses. Application source is GPLv3-or-later.')
    def command_palette(self):
        dlg=QDialog(self);dlg.setWindowTitle('Command palette');dlg.resize(520,440);v=QVBoxLayout(dlg);q=QLineEdit();q.setPlaceholderText('Search commands…');v.addWidget(q);lst=QListWidget();v.addWidget(lst);actions=[a for a in self.findChildren(QAction) if a.text() and not a.menu() and a.isEnabled() and not a.text().startswith('&')]
        def fill():
            lst.clear()
            for a in actions:
                if q.text().lower() in a.text().lower():it=QListWidgetItem(a.text().replace('&','')+'   '+a.shortcut().toString());it.setData(Qt.UserRole,actions.index(a));lst.addItem(it)
            if lst.count():lst.setCurrentRow(0)
        def choose():
            it=lst.currentItem()
            if it:dlg.accept();actions[it.data(Qt.UserRole)].trigger()
        q.textChanged.connect(fill);q.returnPressed.connect(choose);lst.itemActivated.connect(lambda _:choose());fill();dlg.exec()
    def closeEvent(self,e):
        if self.process:
            ans=QMessageBox.question(self,'Job running','Cancel the active job and close?',QMessageBox.Yes|QMessageBox.No)
            if ans!=QMessageBox.Yes:e.ignore();return
            self.cancel_job();self.process.waitForFinished(3000)
        if not self.maybe_save():e.ignore();return
        try:
            if getattr(self,'_recovery_queue',None):self._recovery_queue.shutdown()
        except RuntimeError as exc:
            self.error(str(exc));e.ignore();return
        self.settings.setValue('geometry',self.saveGeometry());e.accept()


from .workspace import WorkspaceMixin
from .feature_ui import FeatureMixin
from .schematic_ui import SchematicMixin

from .project_ui import ProjectMixin
from .lifecycle_ui import LifecycleMixin
from .layout_ui import LayoutMixin
from .silicon_ui import SiliconMixin

from .hierarchy_ui import HierarchyMixin
from .analog_ui import AnalogMixin
from .layout_tools_ui import LayoutToolsMixin
from .editor_workspace import EditorWorkspaceMixin

from .capture_workspace import CaptureWorkspaceMixin
from .consistency_workspace import ConsistencyWorkspaceMixin
from .human_workspace import HumanWorkspaceMixin
from .simulation_workspace import SimulationWorkspaceMixin

from .engineering_workspace import EngineeringWorkspaceMixin

from .physical_workspace import PhysicalWorkspaceMixin

from .verification_workspace import VerificationWorkspaceMixin

from .xschem_workflow import XschemWorkflowMixin

from .native_workspace import NativeWorkspaceMixin
from .onboarding import OnboardingMixin
from .layout_development_ui import LayoutDevelopmentMixin

from .interoperability_ui import InteroperabilityMixin

from .layout_collaboration_ui import CollaborationMixin
from .live_ui import LiveCollaborationMixin

class Studio(LiveCollaborationMixin,CollaborationMixin,InteroperabilityMixin,LayoutDevelopmentMixin,OnboardingMixin,NativeWorkspaceMixin,XschemWorkflowMixin,VerificationWorkspaceMixin,PhysicalWorkspaceMixin,EngineeringWorkspaceMixin,SimulationWorkspaceMixin,HumanWorkspaceMixin,ConsistencyWorkspaceMixin,CaptureWorkspaceMixin,EditorWorkspaceMixin, LayoutToolsMixin, AnalogMixin, HierarchyMixin, SiliconMixin, LifecycleMixin, LayoutMixin, ProjectMixin, SchematicMixin, FeatureMixin, WorkspaceMixin, StudioCore):
    """Standalone desktop application with the document-focused workspace."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        from .editing_assistant import install
        install(self)
        from .test_plan_ui import install as install_test_plans
        install_test_plans(self)
        from .design_workflow import install as install_workflow
        install_workflow(self)
        self.reindex_commands()
    connect = SchematicMixin.connect
    move = LayoutDevelopmentMixin.move
