"""Project lifecycle, explicit technology linking, and project-aware device libraries."""
from pathlib import Path
from PySide6.QtCore import Qt,QPointF,QSize,QTimer,QThread,Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,QLineEdit,QComboBox,QListWidget,QListWidgetItem,QDialogButtonBox,QFileDialog,QMessageBox,QMenu,QInputDialog,QTreeWidgetItem,QApplication,QWidget)
from .model import clone,example,digest,uid,load_project,device
from .pdks import PDKRegistry
from .project_manager import ProjectIndex,delete_cell
from .catalog import create_device,binding_for,link_technology
from .workspace import DEVICE_NAMES,DEVICE_ICONS,label
from .ui_style import icon,palette

class PDKScanThread(QThread):
    succeeded=Signal(str);failed=Signal(str);progress=Signal(str)
    def __init__(self,registry,path,parent):super().__init__(parent);self.registry=registry;self.path=path
    def run(self):
        try:self.succeeded.emit(self.registry.register_local(self.path,self.progress.emit))
        except Exception as e:self.failed.emit(str(e))

class ProjectMixin:
    def make_analysis_panel(self):
        page=super().make_analysis_panel();self.corner_combo=QComboBox();self.corner_combo.setAccessibleName('PDK model corner');page.widget().layout().insertWidget(1,QLabel('PDK model corner'));page.widget().layout().insertWidget(2,self.corner_combo);self.corner_combo.activated.connect(self.select_corner);return page
    def select_corner(self,index):
        value=self.corner_combo.itemData(index)
        if value and self.flush_inspector():self.commit(lambda p:p['analysis'].update(corner=value),'Model corner')
    def make_ui(self):
        self.project_index=ProjectIndex(self.data_dir/'workspace');self.pdk_registry=PDKRegistry(self.data_dir/'pdks');self._catalog_signature=None
        super().make_ui()
        pv=self.navtabs.widget(0).layout();row=QHBoxLayout()
        self.projects_button=self.button('Projects',fn=self.project_manager);row.addWidget(self.projects_button)
        row.addWidget(self.button('Settings',fn=self.project_settings));pv.insertLayout(0,row)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu);self.tree.customContextMenuRequested.connect(self.project_context)
        lv=self.navtabs.widget(1).layout();self.library_category=QComboBox();self.library_category.addItems(['All devices','NMOS','PMOS','Resistors','Capacitors','Bipolar','Diodes','Other','Generic','Custom cells']);self.library_category.currentTextChanged.connect(self.filter_library);lv.insertWidget(1,self.library_category)
        self.library_source=QComboBox();self.library_source.setAccessibleName('Component source library');self.library_source.addItem('All sources',None);self.library_source.currentIndexChanged.connect(self.filter_library);lv.insertWidget(1,self.library_source)
        self.library_info=QLabel();self.library_info.setWordWrap(True);lv.insertWidget(3,self.library_info);self.library_list.currentItemChanged.connect(self.library_selected)
        row=QHBoxLayout();row.addWidget(self.button('PDK manager…',fn=self.pdk_manager));row.addWidget(self.button('New symbol…',fn=self.new_symbol));lv.addLayout(row)
        self.refresh_library()
    def make_actions(self):
        super().make_actions()
        menus={a.text().replace('&',''):a.menu() for a in self.menuBar().actions() if a.menu()}
        for title,entries in {'File':[('Import Magic layout…',self.import_magic_dialog),('Import SPICE circuit…',self.import_spice_dialog),('Projects…',self.project_manager),('Project settings…',self.project_settings),('Close project',self.close_project),('Delete project…',self.delete_project_dialog)],'Design':[('New custom symbol…',self.new_symbol),('Edit selected symbol…',self.edit_selected_symbol),('Rename active cell…',self.rename_cell),('Delete active cell…',self.delete_cell_dialog)],'Tools':[('PDK manager…',self.pdk_manager)]}.items():
            for text,fn in entries:self.action(menus[title],text,fn)
    def refresh(self,fit=False):
        super().refresh(fit)
        if hasattr(self,'library_category'):self.refresh_library()
        if hasattr(self,'tech_detail'):
            lock=self.project['pdk'].get('package_lock',{});catalog=self.project['pdk'].get('simulation',{}).get('catalog',{})
            self.tech_detail.setText((lock.get('revision','')+' · '+str(sum(not e.get('unavailable') for e in catalog.values()))+' placeable devices') if catalog else ('Locked reference models' if lock else 'No PDK linked · generic models'))
        # Every cell exposes all three document types in one consistent tree.
        for i in range(self.tree.topLevelItemCount()):
            item=self.tree.topLevelItem(i);cid=item.data(0,Qt.UserRole)[1];sub=QTreeWidgetItem(item,['Symbol']);sub.setData(0,Qt.UserRole,('symbol',cid,-1));sub.setIcon(0,icon('cell'))
        if hasattr(self,'corner_combo'):
            self.corner_combo.setEnabled(True)
            sets=[set(i['sections']) for i in self.project['pdk'].get('simulation',{}).get('includes',[]) if i.get('sections')];corners=sorted(set.intersection(*sets)) if sets else ['nominal'];self.corner_combo.blockSignals(True);self.corner_combo.clear()
            for corner in corners:self.corner_combo.addItem(corner,corner)
            self.corner_combo.setCurrentIndex(max(0,self.corner_combo.findData(self.project['analysis'].get('corner','nominal'))));self.corner_combo.blockSignals(False)
        if hasattr(self,'analysis_caption'):
            self.analysis_caption.setText('Linked PDK models require ngspice. Select a model corner above.' if self.project['pdk'].get('package_lock') else 'Generic circuit models. Configure external engines in Tools → Engine diagnostics.')
    def tree_clicked(self,item,col=0):
        data=item.data(0,Qt.UserRole)
        if data and data[0]=='symbol':
            if not self.flush_inspector():return
            self.cid=data[1];self.selection=[];self.refresh();self.symbol_dialog();return
        return super().tree_clicked(item,col)
    def set_project(self,p,path=None):
        for dlg in (getattr(self,'_symbol_dialog',None),getattr(self,'_settings_dialog',None)):
            if dlg and dlg.isVisible():dlg.close()
        result=super().set_project(p,path)
        if hasattr(self,'project_index') and path:self.project_index.remember(self.project,path)
        return result
    def save(self,as_new=False):
        if not self.flush_inspector():return False
        result=super().save(as_new)
        if result:self.project_index.remember(self.project,self.path)
        return result
    def refresh_library(self):
        catalog=self.project['pdk'].get('simulation',{}).get('catalog',{})
        signature=digest([self.cid,catalog,[(c['id'],c['name'],c['ports']) for c in self.project['cells']]])
        if signature==self._catalog_signature:return
        self._catalog_signature=signature;self.library_list.clear()
        from .component_sources import library_name
        source_by_key={key:library_name(key) for key in catalog}
        source_by_key={key:(self.project['pdk']['name'] if source=='Project definitions' else source) for key,source in source_by_key.items()}
        current=self.library_source.currentData();self.library_source.blockSignals(True);self.library_source.clear();self.library_source.addItem('All sources',None)
        for source in ['Generic components','Project cells']+sorted(set(source_by_key.values())):self.library_source.addItem(source,source)
        self.library_source.setCurrentIndex(max(0,self.library_source.findData(current)));self.library_source.blockSignals(False)
        for i,kind in enumerate(('R','C','L','V','I','NMOS','PMOS'),1):
            it=QListWidgetItem(DEVICE_NAMES[kind]+'\nGeneric model');it.setData(Qt.UserRole,i);it.setData(Qt.UserRole+1,kind);it.setData(Qt.UserRole+2,'Generic');it.setData(Qt.UserRole+4,'Generic components');it.setIcon(icon(DEVICE_ICONS[kind]));self.library_list.addItem(it)
        for key,e in sorted(catalog.items(),key=lambda pair:(pair[1].get('category','Other'),pair[1]['label'])):
            it=QListWidgetItem(e['label']+'\n'+e.get('model',''));it.setData(Qt.UserRole,key);it.setData(Qt.UserRole+1,e.get('kind','PDK'));it.setData(Qt.UserRole+2,e.get('category','Other'));it.setData(Qt.UserRole+3,e.get('unavailable',''));it.setData(Qt.UserRole+4,source_by_key[key]);it.setIcon(icon('chip'));it.setToolTip(e.get('unavailable') or 'Model: '+e['model']+'\nPins: '+', '.join(e.get('pin_order',[])))
            if e.get('unavailable'):it.setForeground(QColor(palette(self.dark)['muted']))
            self.library_list.addItem(it)
        for c in self.project['cells']:
            if c['id']==self.cid or not c['ports']:continue
            it=QListWidgetItem(c['name']+'\nCustom cell · '+str(len(c['ports']))+' terminals');it.setData(Qt.UserRole,{'cell':c['id']});it.setData(Qt.UserRole+1,'X');it.setData(Qt.UserRole+2,'Custom cells');it.setData(Qt.UserRole+4,'Project cells');it.setIcon(icon('cell'));self.library_list.addItem(it)
        self.filter_library()
    def filter_library(self,*args):
        if not hasattr(self,'library_category'):return super().filter_library(*args)
        query=self.library_search.text().lower();category=self.library_category.currentText();first=None
        source=self.library_source.currentData() if hasattr(self,'library_source') else None
        for i in range(self.library_list.count()):
            it=self.library_list.item(i);hidden=query not in it.text().lower() or (category!='All devices' and it.data(Qt.UserRole+2)!=category) or (source is not None and it.data(Qt.UserRole+4)!=source);it.setHidden(hidden)
            if not hidden and first is None:first=it
        self.library_list.setCurrentItem(first);self.library_selected(first)
    def library_selected(self,item,*args):
        if not hasattr(self,'library_info'):return
        reason=item.data(Qt.UserRole+3) if item else ''
        self.place_library_button.setEnabled(bool(item) and not reason)
        self.library_info.setText(('Unavailable: '+reason) if reason else (item.toolTip() if item else 'No matching devices. Link a PDK in Project settings.'))
    def begin_placement(self,index):
        if isinstance(index,int):
            super().begin_placement(index)
            if self.schematic.placement and not self.project['pdk'].get('simulation',{}).get('devices'):self.schematic.placement['model_mode']='generic'
            return
        if not self.flush_inspector():return
        self.mode_combo.setCurrentIndex(0);self.cancel_tool()
        if isinstance(index,dict):
            child=next(c for c in self.project['cells'] if c['id']==index['cell']);d=device('X',self.next_device_name('X'),cell=child['id'],nets={pin:'open_'+pin for pin in child['ports']})
            if child.get('symbol'):d['symbol']=clone(child['symbol'])
        else:
            e=self.project['pdk']['simulation']['catalog'][index];d=create_device(self.project['pdk'],index,self.next_device_name(e['kind']))
        self.schematic.placement=d;self.schematic.tool='place';self.schematic.drag=self.schematic.snap(self.schematic.model(self.schematic.rect().center()));self.schematic.setFocus();self.schematic.update();self.tool_hint.setText('Place '+d['name']+' · R rotates · click to place · Esc cancels');self.sync_tools()
    def build_inspector(self):
        super().build_inspector()
        if not hasattr(self,'form'):return
        d=next((d for d in self.cell['devices'] if d['id'] in self.selection),None)
        if not d or len(self.selection)!=1:return
        binding=binding_for(self.project['pdk'],d)
        # Insert above the existing stretch; inspector commits all fields atomically.
        if binding:
            text=QLabel('PDK model\n'+binding['model']);text.setWordWrap(True);text.setTextInteractionFlags(Qt.TextSelectableByMouse);self.form.insertWidget(2,text)
            from .workspace import Section
            section=Section('PDK parameters',self._sections.get('PDK parameters',False),lambda on:self._sections.update({'PDK parameters':on}))
            self.form.insertWidget(max(0,self.form.count()-2),section)
            for key,meta in binding.get('parameters',{}).items():
                if d['kind'] in ('NMOS','PMOS') and key in ('w','l'):continue
                edit=QLineEdit(str(d.get('model_params',{}).get(key,meta['default'])));edit.setAccessibleName('PDK parameter '+key);edit.textEdited.connect(self.inspector_changed);section.form.addRow(key,edit);self.form_fields['modelparam:'+key]=edit
        self.form.insertWidget(self.form.count()-1,self.button('Edit symbol…',fn=self.edit_selected_symbol))
    def new_project(self):
        return self.new_pdk_template(None)
    def fill_pdk_choices(self,combo):
        combo.addItem('No PDK · generic models',None)
        for e in self.pdk_registry.entries():
            if e.get('error'):continue
            key=e['id']+'@'+e['revision'];combo.addItem(e['technology']['name']+' · '+e['revision'],key)
        lock=self.project['pdk'].get('package_lock',{});key=lock.get('id','')+'@'+lock.get('revision','');idx=combo.findData(key)
        if lock and idx<0:combo.addItem(self.project['pdk']['name']+' · project-local lock','current');idx=combo.count()-1
        combo.setCurrentIndex(max(0,idx))
    def project_settings(self):
        if not self.flush_inspector():return
        dlg=QDialog(self);dlg.setWindowTitle('Project settings');dlg.resize(660,350);v=QVBoxLayout(dlg);f=QFormLayout();v.addLayout(f);name=QLineEdit(self.project['name']);f.addRow('Name',name);pdk=QComboBox();self.fill_pdk_choices(pdk);f.addRow('Linked PDK',pdk);root=QComboBox()
        for c in self.project['cells']:root.addItem(c['name'],c['id'])
        root.setCurrentIndex(root.findData(self.project['top']));f.addRow('Root cell',root);path=QLabel(str(self.path or 'Not saved yet'));path.setWordWrap(True);f.addRow('Project file',path)
        note=QLabel('A project locks one PDK revision. Existing devices must match. Layout layers map only to identical GDS layer/datatype pairs.');note.setWordWrap(True);v.addWidget(note);v.addWidget(self.button('Open PDK manager…',fn=self.pdk_manager));error=QLabel();error.setWordWrap(True);v.addWidget(error);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);v.addWidget(buttons)
        def apply():
            try:
                if self.process:raise ValueError('Stop the active job before changing project technology.')
                key=pdk.currentData();tech=self.project['pdk'] if key=='current' else self.pdk_registry.technology(key) if key else example('empty')['pdk']
                def edit(p):
                    p.update(name=name.text().strip(),top=root.currentData())
                    if tech!=p['pdk']:link_technology(p,tech)
                self.commit(edit,'Project settings');self.sync_technology();dlg.accept()
            except Exception as e:error.setText(str(e))
        buttons.accepted.connect(apply);buttons.rejected.connect(dlg.reject);self._settings_dialog=dlg;dlg.show()
    def sync_technology(self):
        names=[l['name'] for l in self.project['pdk']['layers']];self.layer_combo.clear();self.layer_combo.addItems(names);self.layout.visible_layers=set(names);self.refresh()
    def close_project(self):
        if self.process:raise ValueError('Stop the active job before closing the project.')
        if self.flush_inspector() and self.maybe_save():self.set_project(example('empty'))
    def project_manager(self):
        dlg=QDialog(self);dlg.setWindowTitle('Projects');dlg.resize(780,520);v=QVBoxLayout(dlg);v.addWidget(QLabel('PROJECT WORKSPACE'));search=QLineEdit();search.setPlaceholderText('Search projects or linked PDK…');v.addWidget(search);items=QListWidget();v.addWidget(items,1);error=QLabel();error.setWordWrap(True);v.addWidget(error)
        def fill():
            items.clear()
            for e in self.project_index.entries():
                it=QListWidgetItem(e['name']+'  ·  '+e['pdk']+'\n'+e['path']+('  [missing]' if not Path(e['path']).exists() else ''));it.setData(Qt.UserRole,e);items.addItem(it)
        def open_selected():
            if not items.currentItem():return
            try:
                path=items.currentItem().data(Qt.UserRole)['path'];p=load_project(path)
                if self.process:raise ValueError('Stop the active job before switching projects.')
                if self.flush_inspector() and self.maybe_save():self.set_project(p,path);dlg.accept()
            except Exception as e:error.setText(str(e))
        def remove():
            if items.currentItem():self.project_index.forget(items.currentItem().data(Qt.UserRole)['path']);fill()
        def trash():
            if items.currentItem():self.delete_project_dialog(items.currentItem().data(Qt.UserRole)['path']);fill()
        def locate():
            if not items.currentItem():return
            record=items.currentItem().data(Qt.UserRole)
            path,_=QFileDialog.getOpenFileName(dlg,'Locate moved project','','Studio projects (*.icproj *.icstudio)')
            if path:
                try:
                    from .lifecycle import relocate_project
                    relocate_project(self.project_index,record['path'],path);fill();error.setText('Project location updated.')
                except Exception as exc:error.setText(str(exc))
        def restore():
            records=self.project_index.deleted()
            if not records:error.setText('No deleted projects to restore.');return
            choice,ok=QInputDialog.getItem(dlg,'Restore project','Deleted project',[r['original'] for r in records],0,False)
            if ok:
                try:self.project_index.restore(next(r for r in records if r['original']==choice));fill()
                except Exception as e:error.setText(str(e))
        row=QHBoxLayout()
        for title,fn in [('Open',open_selected),('New…',lambda:(dlg.accept(),self.new_project())),('Browse…',lambda:(dlg.accept(),self.open_project())),('Forget',remove),('Delete…',trash),('Restore…',restore),('Locate…',locate)]:
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        v.addLayout(row);items.itemDoubleClicked.connect(lambda _:open_selected());search.textChanged.connect(lambda q:[items.item(i).setHidden(q.lower() not in items.item(i).text().lower()) for i in range(items.count())]);fill();self._projects_dialog=dlg;dlg.show()
    def delete_project_dialog(self,path=None):
        if self.process:raise ValueError('Stop the active job before deleting a project.')
        path=Path(path or self.path) if (path or self.path) else None
        if path is None:raise ValueError('This project has no file yet. Use Close project to discard it.')
        active=self.path and path.resolve()==self.path.resolve()
        if QMessageBox.question(self,'Delete project?',f'Delete {path.name}?\n\nThe project file will be retained for Restore in Projects. Folder contents and PDK installations are retained.',QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Yes:return
        if active and not self.flush_inspector():return
        if active and self.saved_hash!=digest(self.project) and not self.save():return
        self.project_index.trash(path,self._disk_hash if active else None)
        if active:self.clear_recovery();self.settings.remove('last_project');self.set_project(example('empty'))
    def project_context(self,pos):
        item=self.tree.itemAt(pos)
        if not item:return
        data=item.data(0,Qt.UserRole)
        if data:self.cid=data[1]
        menu=QMenu(self);menu.addAction('Edit symbol…',self.symbol_dialog);menu.addAction('Rename cell…',self.rename_cell);menu.addAction('Delete cell…',lambda:self.guard(self.delete_cell_dialog));menu.addSeparator();menu.addAction('Project settings…',self.project_settings);menu.exec(self.tree.viewport().mapToGlobal(pos))
    def rename_cell(self):
        name,ok=QInputDialog.getText(self,'Rename cell','Cell name',text=self.cell['name'])
        if ok:self.commit(lambda p:next(c for c in p['cells'] if c['id']==self.cid).update(name=name.strip()),'Rename cell')
    def delete_cell_dialog(self):
        candidate=clone(self.project);delete_cell(candidate,self.cid)
        if QMessageBox.question(self,'Delete cell?',f'Delete {self.cell["name"]}? Undo restores it.',QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)==QMessageBox.Yes:self.commit(lambda p:delete_cell(p,self.cid),'Delete cell')
    def pdk_status(self):self.project_settings()
    def pdk_manager(self):
        dlg=QDialog(self);dlg.setWindowTitle('PDK manager');dlg.resize(900,590);v=QVBoxLayout(dlg);v.addWidget(QLabel('PROCESS DESIGN KITS'));note=QLabel('Register an installed PDK folder to index its devices, models and layout layers. Projects keep an explicit revision link.');note.setWordWrap(True);v.addWidget(note);items=QListWidget();v.addWidget(items,1);details=QLabel();details.setWordWrap(True);details.setTextInteractionFlags(Qt.TextSelectableByMouse);v.addWidget(details);state=QLabel();state.setWordWrap(True);v.addWidget(state);row=QHBoxLayout();v.addLayout(row);buttons=[]
        def fill():
            items.clear();entries=self.pdk_registry.entries();families=set()
            for e in entries:
                families.add(e.get('family'));catalog=e.get('technology',{}).get('simulation',{}).get('catalog',{});count=sum(not d.get('unavailable') for d in catalog.values());it=QListWidgetItem(e.get('technology',{}).get('name',e['id'])+'\n'+e['revision']+f' · {count} placeable / {len(catalog)} indexed symbols');it.setData(Qt.UserRole,e['id']+'@'+e['revision']);items.addItem(it)
            from .pdk_import import FAMILIES
            for family,data in FAMILIES.items():
                if family not in families:
                    it=QListWidgetItem(data['name']+'\nNot registered · select its local installation folder');it.setData(Qt.UserRole,None);it.setToolTip(data['docs']);items.addItem(it)
            items.setCurrentRow(0)
        def selected(*args):
            it=items.currentItem();key=it.data(Qt.UserRole) if it else None
            if not key:details.setText(it.toolTip() if it else '');return
            try:
                from .process_adapters import capability_text
                e=self.pdk_registry.manifest(key);root=Path(e.get('source_root',self.pdk_registry.root/key));technology=clone(e['technology']);technology['package_lock']={k:e[k] for k in ('id','revision','files')};details.setText(str(root)+'\n'+capability_text(technology,True))
            except Exception as e:details.setText(str(e))
        items.currentItemChanged.connect(selected)
        def set_busy(busy):
            for button in buttons:button.setEnabled(not busy)
            dlg.setProperty('scanning',busy)
        def register():
            path=QFileDialog.getExistingDirectory(dlg,'Select a stock PDK folder (contains libs.tech)')
            if not path:return
            set_busy(True);state.setText('Scanning PDK…');thread=PDKScanThread(self.pdk_registry,path,dlg);dlg.scan_thread=thread;self._pdk_scan=thread;thread.progress.connect(state.setText)
            thread.succeeded.connect(lambda key:(state.setText('Registered '+key),fill()));thread.failed.connect(state.setText);thread.finished.connect(lambda:set_busy(False));thread.start()
        def package():
            path,_=QFileDialog.getOpenFileName(dlg,'Install checksummed PDK package','','Package manifest (*.json)')
            if path:
                try:key=self.pdk_registry.install(path);state.setText('Installed '+key);fill()
                except Exception as e:state.setText(str(e))
        def relocate():
            key=items.currentItem().data(Qt.UserRole) if items.currentItem() else None
            if not key:return
            path=QFileDialog.getExistingDirectory(dlg,'Locate moved PDK folder')
            if path:
                try:self.pdk_registry.relocate(key,path);state.setText('Registered folder updated. Use Tools → Relink project PDK folder for an already open project.');selected()
                except Exception as exc:state.setText(str(exc))
        def verify():
            key=items.currentItem().data(Qt.UserRole) if items.currentItem() else None
            if key:
                try:self.pdk_registry.verify(key);state.setText('All locked files match the registered revision.')
                except Exception as e:state.setText(str(e))
        def link():
            key=items.currentItem().data(Qt.UserRole) if items.currentItem() else None
            if not key:return
            try:
                if self.process:raise ValueError('Stop the active job before linking a PDK.')
                tech=self.pdk_registry.technology(key);self.commit(lambda p:link_technology(p,tech),'Link project to PDK');self.sync_technology();state.setText('Linked '+self.project['name']+' to '+key)
            except Exception as e:state.setText(str(e))
        def remove():
            key=items.currentItem().data(Qt.UserRole) if items.currentItem() else None
            if not key:return
            lock=self.project['pdk'].get('package_lock',{})
            if key==lock.get('id','')+'@'+lock.get('revision',''):state.setText('Unlink this PDK in Project settings before removing its registration.');return
            users=[e['name'] for e in self.project_index.entries() if e.get('pdk','')+'@'+e.get('revision','')==key and Path(e['path']).exists()]
            if users:state.setText('Registered projects still use this revision: '+', '.join(users)+'. Migrate those projects first.');return
            if QMessageBox.question(dlg,'Remove PDK registration?','Remove '+key+' from the manager? Assets are retained in their current location or the registration archive.',QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)==QMessageBox.Yes:
                self.pdk_registry.remove(key);fill()
        for text,fn in [('Add folder…',register),('Install package…',package),('Verify',verify),('Locate…',relocate),('Link to project',link),('Remove…',remove)]:
            b=QPushButton(text);b.clicked.connect(fn);buttons.append(b);row.addWidget(b)
        # The worker owns no widgets. Prevent destruction while its scan is active.
        original_close=dlg.closeEvent
        def close(event):
            if dlg.property('scanning'):state.setText('Wait for the PDK scan to finish before closing.');event.ignore()
            else:original_close(event)
        dlg.closeEvent=close;dlg.reject=lambda:dlg.close();fill();self._pdk_dialog=dlg;dlg.show()
    def new_symbol(self):
        name,ok=QInputDialog.getText(self,'New custom symbol','Unique cell name')
        if not ok:return
        ports,ok=QInputDialog.getText(self,'Symbol terminals','Space-separated terminal names',text='in out vdd vss')
        if not ok:return
        from .symbol_editor import default_symbol
        c={'id':uid(),'name':name.strip(),'ports':ports.split(),'devices':[],'shapes':[],'symbol':default_symbol(ports.split())};self.commit(lambda p:p['cells'].append(c),'Create symbol cell');self.cid=c['id'];self.selection=[];self.refresh();self.symbol_dialog()
    def edit_selected_symbol(self):
        d=next((d for d in self.cell['devices'] if d['id'] in self.selection),None)
        if not d:return self.symbol_dialog()
        if d['kind']=='X':
            cell=next(c for c in self.project['cells'] if c['id']==d['cell']);return self.open_symbol_editor(cell)
        cell={'name':d['name'],'ports':list(d['nets']),'symbol':d.get('symbol')}
        if cell['symbol'] is None:
            from .symbol_io import device_symbol
            cell['symbol']=device_symbol(d)
        self.open_symbol_editor(cell,device_id=d['id'])
    def symbol_dialog(self):self.open_symbol_editor(self.cell)
    def open_symbol_editor(self,cell,device_id=None):
        from .symbol_editor import SymbolEditor
        project_id=self.project['id'];cid=self.cid if device_id else cell['id']
        def save(symbol):
            if self.project['id']!=project_id:raise ValueError('The symbol belongs to a different project.')
            def edit(p):
                c=next(c for c in p['cells'] if c['id']==cid)
                if device_id:next(d for d in c['devices'] if d['id']==device_id)['symbol']=symbol
                else:
                    c['symbol']=symbol
                    for parent in p['cells']:
                        for instance in parent['devices']:
                            if instance.get('cell')==cid:instance['symbol']=clone(symbol)
            self.commit(edit,'Edit symbol')
        dlg=SymbolEditor(cell,self.dark,save,self);dlg.setWindowModality(Qt.WindowModal);self._symbol_dialog=dlg;dlg.show()
    def import_spice_dialog(self):
        path,_=QFileDialog.getOpenFileName(self,'Import editable SPICE circuit','','SPICE (*.cir *.spice *.sp)')
        if not path:return
        from .spice_import import import_spice
        p,report=import_spice(path,self.project['pdk'] if self.project['pdk'].get('package_lock') else None)
        if self.flush_inspector() and self.maybe_save():self.set_project(p);self.console.appendPlainText('\n'.join(report))
    def import_magic_dialog(self):
        import shutil
        source,_=QFileDialog.getOpenFileName(self,'Import Magic layout','','Magic cell (*.mag)')
        if not source:return
        tech,_=QFileDialog.getOpenFileName(self,'Matching Magic technology file','','Magic technology (*.tech)')
        if not tech:return
        exe=self.settings.value('engine/magic','') or shutil.which('magic')
        if not exe:raise ValueError('Configure the Magic executable in Engine diagnostics first.')
        output=self.data_dir/'imports'/uid()
        self.start_cli_job(['magic-import','--source',source,'--technology',tech,'--executable',exe,'--output',str(output)],'Magic import')
        process=self.process
        def opened(code,status):
            if code==0 and not self.cancelled and (output/'imported.icproj').exists():
                if self.flush_inspector() and self.maybe_save():self.set_project(load_project(output/'imported.icproj'));self.console.appendPlainText('Imported Magic layout. Save to choose your project location.')
        process.finished.connect(opened)

    def closeEvent(self,event):
        if getattr(self,'_pdk_scan',None) and self._pdk_scan.isRunning():self.statusBar().showMessage('Wait for the PDK scan to finish before closing.');event.ignore();return
        super().closeEvent(event)
