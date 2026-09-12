"""A project hub with visible PDK versions, local setup and circuit templates."""
from pathlib import Path
from PySide6.QtCore import Qt,QSize,QThread
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,
    QLabel,QLineEdit,QComboBox,QPushButton,QListWidget,QListWidgetItem,QStackedWidget,
    QDialogButtonBox,QFileDialog,QSplitter,QScrollArea)
from . import __version__
from .model import load_project
from .ui_style import palette,icon
from .project_templates import TEMPLATES,model_choices
from .project_hub import inventory,preview,build_project


def label(text='',role=None):
    widget=QLabel(text);widget.setWordWrap(True);widget.setTextFormat(Qt.PlainText)
    if role:widget.setProperty('role',role)
    return widget


class HubWorker(QThread):
    def __init__(self,operation,parent):
        super().__init__(parent);self.operation=operation;self.result=None;self.error=''
    def run(self):
        try:self.result=self.operation()
        except Exception as exc:self.error=str(exc)


class ProjectHub(QDialog):
    def __init__(self,window,page='new',initial_kind=None):
        super().__init__(window);self.window=window;self.worker=None;self.rows=[];self.checked={};self._filling=False
        self.setWindowTitle('Project Hub · IC Design Studio');self.setWindowModality(Qt.WindowModal)
        self.resize(1160,790);self.setMinimumSize(960,690)
        t=palette(window.dark)
        self.setStyleSheet(f'QListWidget#hubNav {{ background:{t["bg"]}; border:0; }} '
            f'QListWidget#hubNav::item {{ padding:13px 12px; border-radius:6px; }} '
            f'QListWidget#hubPDKs::item {{ padding:13px; margin:3px; border:1px solid {t["line"]}; border-radius:8px; }} '
            f'QListWidget#hubPDKs::item:selected {{ background:{t["tint"]}; border-color:{t["accent"]}; }}')
        outer=QHBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        sidebar=QWidget();sidebar.setObjectName('sidebarBody');sidebar.setFixedWidth(190);sv=QVBoxLayout(sidebar);sv.setContentsMargins(18,24,18,18)
        sv.addWidget(label('IC DESIGN\nSTUDIO','title'));sv.addWidget(label('Project Hub','muted'));sv.addSpacing(28)
        self.nav=QListWidget();self.nav.setObjectName('hubNav');self.nav.setAccessibleName('Hub navigation')
        for title,key,glyph in [('Projects','projects','folder'),('PDKs','pdks','chip'),('New project','new','plus')]:
            item=QListWidgetItem(icon(glyph,t['muted']),title);item.setData(Qt.UserRole,key);self.nav.addItem(item)
        sv.addWidget(self.nav,1);sv.addWidget(label('Studio '+__version__,'muted'))
        close=QPushButton('Back to workspace');close.clicked.connect(self.reject);sv.addWidget(close);outer.addWidget(sidebar)
        main=QWidget();mv=QVBoxLayout(main);mv.setContentsMargins(26,22,26,18);mv.setSpacing(12);outer.addWidget(main,1)
        heading=QHBoxLayout();self.title=label('','title');heading.addWidget(self.title,1)
        self.refresh_button=QPushButton('Refresh');self.refresh_button.clicked.connect(self.refresh);heading.addWidget(self.refresh_button);mv.addLayout(heading)
        self.caption=label('','muted');mv.addWidget(self.caption)
        self.pages=QStackedWidget();mv.addWidget(self.pages,1)
        self.make_projects();self.make_pdks(initial_kind)
        self.state=label();self.state.setTextInteractionFlags(Qt.TextSelectableByMouse);mv.addWidget(self.state)
        for button in self.findChildren(QPushButton):button.setAutoDefault(False)
        self.nav.currentRowChanged.connect(self.change_page)
        self.refresh();self.show_page(page)

    def make_projects(self):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(0,0,0,0)
        self.project_search=QLineEdit();self.project_search.setPlaceholderText('Search projects, PDKs or revisions…');v.addWidget(self.project_search)
        self.projects=QListWidget();self.projects.setAccessibleName('Hub recent projects');self.projects.setSpacing(5);v.addWidget(self.projects,1)
        self.projects_empty=label('No saved projects yet. Create a project or open an existing .icproj file.','muted');v.addWidget(self.projects_empty)
        row=QHBoxLayout();self.open_button=QPushButton('Open selected');self.open_button.clicked.connect(self.open_selected);row.addWidget(self.open_button)
        browse=QPushButton('Open from disk…');browse.clicked.connect(self.browse_project);row.addWidget(browse)
        manage=QPushButton('Manage project files…');manage.clicked.connect(self.manage_files);row.addWidget(manage)
        row.addStretch();new=QPushButton('New project');new.clicked.connect(lambda:self.show_page('new'));row.addWidget(new);v.addLayout(row)
        self.projects.itemDoubleClicked.connect(lambda *_:self.open_selected());self.projects.currentRowChanged.connect(self.project_selection)
        self.project_search.textChanged.connect(self.filter_projects);self.pages.addWidget(page)

    def make_pdks(self,initial_kind):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(0,0,0,0)
        toolbar=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Find a PDK or revision…');self.search.setAccessibleName('Find a PDK revision');toolbar.addWidget(self.search,1)
        self.filter=QComboBox();self.filter.addItems(['All PDKs','Installed','Available offline']);toolbar.addWidget(self.filter)
        self.setup_button=QPushButton('Add PDK…');self.setup_button.clicked.connect(self.open_setup);toolbar.addWidget(self.setup_button);v.addLayout(toolbar)
        split=QSplitter();v.addWidget(split,1)
        left=QWidget();lv=QVBoxLayout(left);lv.setContentsMargins(0,0,10,0)
        self.pdks=QListWidget();self.pdks.setObjectName('hubPDKs');self.pdks.setAccessibleName('PDK revisions');self.pdks.setIconSize(QSize(28,28));lv.addWidget(self.pdks)
        self.empty=label('No matching revisions. Clear the search or add a PDK.','muted');lv.addWidget(self.empty);split.addWidget(left)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.NoFrame)
        right=QWidget();rv=QVBoxLayout(right);rv.setContentsMargins(18,8,8,8);rv.setSpacing(10);scroll.setWidget(right);split.addWidget(scroll);split.setSizes([385,460])
        self.pdk_title=label('','title');rv.addWidget(self.pdk_title);self.revision=label();self.revision.setTextInteractionFlags(Qt.TextSelectableByMouse);rv.addWidget(self.revision)
        self.pdk_status=label('','badge');rv.addWidget(self.pdk_status)
        self.summary=label('','muted');rv.addWidget(self.summary)
        self.details=QStackedWidget();rv.addWidget(self.details,1)
        installed=QWidget();iv=QVBoxLayout(installed);iv.setContentsMargins(0,12,0,0)
        self.location_title=label('INSTALLATION','section');iv.addWidget(self.location_title);self.location=label();self.location.setTextInteractionFlags(Qt.TextSelectableByMouse);iv.addWidget(self.location)
        self.runtime=label();iv.addWidget(self.runtime);self.integrity=label('','muted');iv.addWidget(self.integrity);iv.addStretch()
        self.install_button=QPushButton('Install selected PDK');self.install_button.clicked.connect(self.install_selected);iv.addWidget(self.install_button)
        self.verify_button=QPushButton('Verify installed files');self.verify_button.clicked.connect(self.verify_selected);iv.addWidget(self.verify_button)
        self.locate_button=QPushButton('Locate installation folder…');self.locate_button.clicked.connect(self.locate_selected);iv.addWidget(self.locate_button)
        self.use_button=QPushButton('New project with this revision');self.use_button.clicked.connect(lambda:self.show_page('new'));iv.addWidget(self.use_button)
        self.details.addWidget(installed)
        create=QWidget();cv=QVBoxLayout(create);cv.setContentsMargins(0,8,0,0);self.form=QFormLayout();self.form.setSpacing(12);self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow);cv.addLayout(self.form)
        self.name=QLineEdit('Untitled circuit');self.name.setAccessibleName('New project name');self.form.addRow('Project name',self.name)
        self.template=QComboBox();self.template.setAccessibleName('Circuit template')
        for key,title in {'empty':'Empty circuit','rc':'RC low-pass',**TEMPLATES}.items():self.template.addItem(title,key)
        self.template.setCurrentIndex(max(0,self.template.findData(initial_kind)));self.form.addRow('Template',self.template)
        self.nmos=QComboBox();self.pmos=QComboBox();self.supply=QLineEdit('1.8')
        for title,widget in [('NMOS model',self.nmos),('PMOS model',self.pmos),('Supply (V)',self.supply)]:widget.setAccessibleName(title);self.form.addRow(title,widget)
        for combo in (self.nmos,self.pmos):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);combo.setMinimumContentsLength(18)
            combo.currentTextChanged.connect(combo.setToolTip)
        self.template_note=label('','muted');cv.addWidget(self.template_note);cv.addStretch()
        cv.addWidget(label('The project keeps this exact revision. Save the new project from the workspace to choose its file location.','muted'))
        self.buttons=QDialogButtonBox(QDialogButtonBox.Ok);self.create_button=self.buttons.button(QDialogButtonBox.Ok);self.create_button.setText('Create project');self.create_button.setProperty('role','primary');self.buttons.accepted.connect(self.create_project);cv.addWidget(self.buttons)
        self.details.addWidget(create);self.pages.addWidget(page)
        self.pdks.currentRowChanged.connect(self.selection);self.search.textChanged.connect(self.filter_pdks);self.filter.currentIndexChanged.connect(self.filter_pdks)
        self.template.currentIndexChanged.connect(self.selection);self.name.textChanged.connect(self.update_create)

    def show_page(self,page):
        self.nav.setCurrentRow({'projects':0,'pdks':1,'new':2}[page]);self.change_page()

    def change_page(self,*_):
        item=self.nav.currentItem()
        if not item:return
        page=item.data(Qt.UserRole);self.pages.setCurrentIndex(0 if page=='projects' else 1);self.details.setCurrentIndex(1 if page=='new' else 0)
        self.title.setText({'projects':'Your projects','pdks':'PDK installations','new':'Create a project'}[page])
        count=sum(r['status']=='Installed' for r in self.rows)
        self.caption.setText({'projects':'Recent designs and their linked process revisions.',
            'pdks':f'{count} installed revision(s) · Included packages can be installed offline.',
            'new':'Choose a process revision, then a starting circuit.'}[page])
        self.selection()

    def current_pdk(self):
        item=self.pdks.currentItem();return item.data(Qt.UserRole) if item and not item.isHidden() else None

    def select_pdk(self,key):
        for i in range(self.pdks.count()):
            if self.pdks.item(i).data(Qt.UserRole)['key']==key:
                self.search.clear();self.filter.setCurrentIndex(0);self.pdks.setCurrentRow(i);return True
        return False

    def refresh(self,*_):
        if self.busy():return
        old=self.current_pdk();lock=self.window.project['pdk'].get('package_lock',{})
        key=old['key'] if old else self.window.settings.value('hub/last_pdk',lock.get('id','')+'@'+lock.get('revision',''))
        self._filling=True;self.pdks.clear();self.rows,notes=inventory(self.window.pdk_registry)
        for row in self.rows:
            status=row['status'];item=QListWidgetItem(icon('chip',palette(self.window.dark)['accent']),row['id']+'\n'+row['revision']+'\n'+status)
            item.setData(Qt.UserRole,row);item.setToolTip(row['name']+'\n'+row['revision']+'\n'+row['path']);self.pdks.addItem(item)
            if row['key']==key:self.pdks.setCurrentItem(item)
        if self.pdks.currentRow()<0:
            # Never silently choose an installed revision when creating a generic project.
            self.pdks.setCurrentRow(next(i for i,r in enumerate(self.rows) if r['key']=='generic'))
        self.projects.clear()
        try:
            for project in self.window.project_index.entries():
                item=QListWidgetItem(project['name']+'\n'+project['pdk']+' · '+(project.get('revision') or 'Built in')+'\n'+project['path'])
                item.setData(Qt.UserRole,project);item.setToolTip(project['path']);self.projects.addItem(item)
        except (ValueError,OSError,KeyError) as exc:notes.append('Recent projects: '+str(exc))
        self._filling=False;self.filter_pdks();self.filter_projects();self.change_page();self.state.setText('\n'.join(notes))

    def filter_pdks(self,*_):
        if self._filling:return
        query=self.search.text().casefold();scope=self.filter.currentText();first=None;count=0
        for i in range(self.pdks.count()):
            item=self.pdks.item(i);row=item.data(Qt.UserRole)
            visible=query in (' '.join(str(row[k]) for k in ('id','name','family','revision'))).casefold() and (scope=='All PDKs' or row['status']==scope)
            item.setHidden(not visible)
            if visible:count+=1;first=i if first is None else first
        if self.current_pdk() is None:self.pdks.setCurrentRow(first if first is not None else -1)
        self.empty.setVisible(count==0);self.selection()

    def filter_projects(self,*_):
        query=self.project_search.text().casefold();visible=[]
        for i in range(self.projects.count()):
            item=self.projects.item(i);item.setHidden(query not in item.text().casefold())
            if not item.isHidden():visible.append(i)
        self.projects_empty.setVisible(not visible)
        if self.projects.currentRow() not in visible:self.projects.setCurrentRow(visible[0] if visible else -1)
        self.project_selection()

    def project_selection(self,*_):
        item=self.projects.currentItem();self.open_button.setEnabled(bool(item and not item.isHidden()))

    def selection(self,*_):
        if self._filling:return
        row=self.current_pdk();self.ready=False
        old_models=(self.nmos.currentData(),self.pmos.currentData()) if row and getattr(self,'_selected_key',None)==row['key'] else (None,None)
        self._selected_key=row['key'] if row else None
        for button in (self.install_button,self.verify_button,self.locate_button,self.use_button):button.setEnabled(False)
        self.nmos.clear();self.pmos.clear()
        if not row:
            self.pdk_title.setText('Choose a PDK');self.revision.clear();self.pdk_status.clear();self.summary.clear();self.location.clear();self.runtime.clear();self.integrity.clear();self.update_create();return
        self.pdk_title.setText(row['id']);self.revision.setText('Revision  '+row['revision'])
        lock=self.window.project['pdk'].get('package_lock',{});current=row['key']==lock.get('id','')+'@'+lock.get('revision','')
        self.pdk_status.setText(row['status']+(' · Used by current project' if current else ''))
        self.location_title.setText('INCLUDED PACKAGE' if row['status']=='Available offline' else 'INSTALLATION')
        self.location.setText(row['path'] or 'No installation folder')
        self.integrity.setText(self.checked.get(row['key'],'Verify files to check this installation against its registered revision.') if row['status']=='Installed' else
                               'Install this package to register its revision locally.' if row['status']=='Available offline' else
                               'Included with Studio. No PDK installation needed.' if row['key']=='generic' else '')
        available=row['status'] in ('Installed','Available offline','Built in');self.use_button.setEnabled(available)
        self.install_button.setEnabled(row['status']=='Available offline');self.verify_button.setEnabled(row['status']=='Installed')
        self.locate_button.setEnabled(row['status'] in ('Installed','Folder missing'))
        self.install_button.setVisible(row['status']=='Available offline');self.verify_button.setVisible(row['status']=='Installed');self.locate_button.setVisible(row['status'] in ('Installed','Folder missing'))
        self.runtime.setText('Add a local installation or adapter package with Add PDK.')
        try:
            technology=preview(row);kind=self.template.currentData()
            from .getting_started import readiness
            from .spice_program import find_ngspice
            info=readiness(technology,find_ngspice(self.window.settings.value('engine/ngspice','')))
            self.summary.setText(row['name']+'\n'+str(row['models'])+' placeable models · '+str(len(info['corners']))+' model corner(s)')
            self.summary.setToolTip('Corners: '+', '.join(info['corners']))
            self.runtime.setText('Built-in solver or configured ngspice.' if row['key']=='generic' else info['runtime'])
            for combo,polarity in ((self.nmos,'NMOS'),(self.pmos,'PMOS')):
                if row['key']=='generic':combo.addItem('Generic teaching model',None)
                for key,entry in model_choices(technology,polarity):combo.addItem(entry['model']+' · '+key,key)
            for combo,old in zip((self.nmos,self.pmos),old_models):
                if old and combo.findData(old)>=0:combo.setCurrentIndex(combo.findData(old))
            self.ready=kind not in TEMPLATES or self.nmos.count()>0 and (kind not in ('inverter','ring','amplifier') or self.pmos.count()>0)
            self.template_note.setText('Choose models and a supply appropriate for this process.' if self.ready and kind in TEMPLATES else '' if self.ready else 'This revision has no required four-terminal MOS models. Choose an empty circuit or another revision.')
        except (ValueError,OSError,KeyError) as exc:self.summary.setText(str(exc));self.template_note.setText(str(exc))
        kind=self.template.currentData()
        self.form.setRowVisible(self.nmos,kind in TEMPLATES);self.form.setRowVisible(self.pmos,kind in ('inverter','ring','amplifier'));self.form.setRowVisible(self.supply,kind in TEMPLATES)
        self.create_button.setText('Install PDK & create project' if row['status']=='Available offline' else 'Create project');self.update_create()

    def update_create(self,*_):self.create_button.setEnabled(getattr(self,'ready',False) and bool(self.name.text().strip()) and not self.busy())
    def busy(self):return bool(self.worker and self.worker.isRunning())

    def run_operation(self,fn,done,message):
        if self.busy():return
        self.state.setText(message);self.pages.setEnabled(False);self.nav.setEnabled(False);self.refresh_button.setEnabled(False)
        worker=HubWorker(fn,self);self.worker=worker;self.window._project_hub_worker=worker
        def finished():
            self.pages.setEnabled(True);self.nav.setEnabled(True);self.refresh_button.setEnabled(True)
            if worker.error:self.state.setText(worker.error);self.update_create();return
            try:done(worker.result)
            except (ValueError,OSError,KeyError) as exc:self.state.setText(str(exc))
            self.update_create()
        worker.finished.connect(finished);worker.start()

    def create_project(self):
        row=self.current_pdk()
        if not row or not self.ready or self.busy():return
        def done(result):
            # Candidate and PDK checks are complete before asking to save existing work.
            self.refresh();self.select_pdk(row['key'])
            if not self.window.flush_analysis() or not self.window._replace_document():return
            self.window.set_project(result['project'])
            if result['cell']:self.window.cid=result['cell'];self.window._selected_testbench=result['testbench'];self.window.refresh(True)
            self.window.settings.setValue('hub/last_pdk',row['key']);self.accept()
        name,kind,supply,nmos,pmos=self.name.text(),self.template.currentData(),self.supply.text(),self.nmos.currentData(),self.pmos.currentData()
        self.run_operation(lambda:build_project(self.window.pdk_registry,row,name,kind,supply,nmos,pmos),done,'Checking the selected PDK revision and preparing your project…')

    def install_selected(self):
        row=self.current_pdk()
        if not row or row['status']!='Available offline':return
        from .model import digest
        import json
        def install():
            path=Path(row['path'])/'package.json'
            if digest(json.loads(path.read_text(encoding='utf-8')))!=digest(row['manifest']):raise ValueError('Package changed. Refresh before installing.')
            return self.window.pdk_registry.install(path)
        def done(key):self.refresh();self.select_pdk(key);self.state.setText('Installed '+key+'. Your open project keeps its existing PDK.')
        self.run_operation(install,done,'Installing the selected included package offline…')

    def verify_selected(self):
        row=self.current_pdk()
        if not row or row['status']!='Installed':return
        def done(_):self.checked[row['key']]='All registered files matched when checked in this session.';self.selection();self.state.setText('Verified '+row['key'])
        self.run_operation(lambda:self.window.pdk_registry.verify(row['key']),done,'Verifying installed files…')

    def locate_selected(self):
        row=self.current_pdk()
        if not row:return
        folder=QFileDialog.getExistingDirectory(self,'Locate '+row['id'],row['path'])
        if not folder:return
        def done(_):self.refresh();self.state.setText('Installation location updated. Existing project locks remain unchanged.')
        self.run_operation(lambda:self.window.pdk_registry.relocate(row['key'],folder),done,'Checking the selected folder against the registered revision…')

    def open_setup(self):
        if self.busy():return
        setup=self.window.pdk_manager();setup.setParent(self,Qt.Dialog);setup.setWindowModality(Qt.WindowModal)
        setup.finished.connect(lambda *_:self.refresh());setup.show()

    def manage_files(self):
        self.window.manage_project_files();dialog=self.window._projects_dialog
        dialog.setParent(self,Qt.Dialog);dialog.setWindowModality(Qt.WindowModal)
        dialog.finished.connect(lambda *_:self.refresh());dialog.show()

    def open_selected(self):
        item=self.projects.currentItem()
        if item and not item.isHidden():self.open_path(item.data(Qt.UserRole)['path'])

    def browse_project(self):
        path,_=QFileDialog.getOpenFileName(self,'Open project','','Studio projects (*.icproj *.icstudio)')
        if path:self.open_path(path)

    def open_path(self,path):
        try:
            project=load_project(path)
            if self.window.flush_analysis() and self.window._replace_document():self.window.set_project(project,path);self.accept()
        except (ValueError,OSError,KeyError) as exc:self.state.setText(str(exc))

    def reject(self):
        if self.busy():self.state.setText('Finishing the current PDK operation…');return
        super().reject()

    def closeEvent(self,event):
        if self.busy():self.state.setText('Finishing the current PDK operation…');event.ignore()
        else:super().closeEvent(event)


def show(window,page='new',initial_kind=None):
    existing=getattr(window,'_project_hub',None)
    if existing and existing.isVisible():
        if initial_kind:existing.template.setCurrentIndex(existing.template.findData(initial_kind))
        existing.show_page(page);existing.raise_();return existing
    dialog=ProjectHub(window,page,initial_kind);window._project_hub=dialog;window._template_dialog=dialog
    dialog.show();return dialog
