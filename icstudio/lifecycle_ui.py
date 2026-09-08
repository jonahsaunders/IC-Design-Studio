"""Desktop workflows for reusable components and reviewed dependency changes."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,
    QComboBox,QPlainTextEdit,QDialogButtonBox,QFileDialog,QInputDialog,QTableWidget,QTableWidgetItem)
from .model import clone,digest,load_project
from .catalog import binding_for
from .lifecycle import duplicate_project,relink_assets,replacement,migration_preview


class LifecycleMixin:
    def make_actions(self):
        super().make_actions()
        menus={a.text().replace('&',''):a.menu() for a in self.menuBar().actions() if a.menu()}
        for menu,entries in {
            'File':[('Duplicate project…',self.duplicate_project_dialog),('Import SPICE component…',self.import_component_dialog)],
            'Design':[('Component properties…',self.component_dialog),('Replace selected PDK device…',self.replace_model_dialog)],
            'Tools':[('Relink project PDK folder…',self.relink_pdk_dialog),('Migrate PDK revision…',self.migrate_pdk_dialog),('Simulation runtime…',self.runtime_dialog)]
        }.items():
            for title,fn in entries:self.action(menus[menu],title,fn)

    def build_inspector(self):
        super().build_inspector()
        if not hasattr(self,'form'):return
        d=next((d for d in self.cell['devices'] if d['id'] in self.selection),None)
        if not d or len(self.selection)!=1 or d['kind']!='X':return
        from PySide6.QtWidgets import QWidget
        child=next(c for c in self.project['cells'] if c['id']==d['cell'])
        for key,raw in child.get('parameters',{}).items():
            host=QWidget();row=QHBoxLayout(host);row.setContentsMargins(0,0,0,0);row.addWidget(QLabel(key));edit=QLineEdit(str(d.get('parameters',{}).get(key,raw)));edit.setAccessibleName('Component parameter '+key);edit.textEdited.connect(self.inspector_changed);row.addWidget(edit);self.form.insertWidget(self.form.count()-1,host);self.form_fields['instanceparam:'+key]=edit

    def idle_edit(self):
        if self.process:raise ValueError('Stop the active job before changing project dependencies.')
        return self.flush_inspector()

    def duplicate_project_dialog(self):
        if not self.idle_edit():return
        path,_=QFileDialog.getSaveFileName(self,'Create independent project copy',self.project['name']+' copy.icproj','Studio project (*.icproj)')
        if not path:return
        p=duplicate_project(self.project,path)
        self.project_index.remember(p,path)
        self.statusBar().showMessage('Created '+str(path)+' · open it from Projects',8000)

    def relink_pdk_dialog(self):
        if not self.idle_edit():return
        path=QFileDialog.getExistingDirectory(self,'Locate the exact locked PDK folder (contains libs.tech)')
        if path:
            self.commit(lambda p:relink_assets(p,path),'Relink PDK assets')
            self.statusBar().showMessage('PDK folder relinked; every locked file matches.',8000)

    def review_dialog(self,title,build,controls=None):
        """Preview and apply the same candidate; reject stale previews."""
        dlg=QDialog(self);dlg.setWindowTitle(title);dlg.resize(800,540);dlg.setWindowModality(Qt.WindowModal)
        layout=QVBoxLayout(dlg)
        if controls:layout.addWidget(controls)
        text=QPlainTextEdit();text.setReadOnly(True);text.setAccessibleName('Change preview');layout.addWidget(text,1)
        error=QLabel();error.setWordWrap(True);layout.addWidget(error)
        buttons=QDialogButtonBox(QDialogButtonBox.Apply|QDialogButtonBox.Cancel);layout.addWidget(buttons)
        apply=buttons.button(QDialogButtonBox.Apply);apply.setEnabled(False);state={}
        def preview():
            apply.setEnabled(False)
            try:
                candidate,report=build();state.update(candidate=candidate,source=digest(self.project))
                text.setPlainText(report);error.clear();apply.setEnabled(True)
            except Exception as exc:error.setText(str(exc))
        def commit():
            try:
                if not self.idle_edit():return
                if digest(self.project)!=state['source']:raise ValueError('Project changed. Preview again before applying.')
                self.commit(lambda p:(p.clear(),p.update(clone(state['candidate']))),title)
                self.sync_technology();dlg.accept()
            except Exception as exc:error.setText(str(exc))
        layout.insertWidget(layout.count()-1,self.button('Preview changes',fn=preview))
        apply.clicked.connect(commit);buttons.rejected.connect(dlg.reject)
        if controls:
            for combo in controls.findChildren(QComboBox):combo.currentIndexChanged.connect(lambda *_:apply.setEnabled(False))
        preview();self._review_dialog=dlg;dlg.show()

    def replace_model_dialog(self):
        if not self.idle_edit():return
        old=next((d for d in self.cell['devices'] if d['id'] in self.selection),None)
        if old is None or len(self.selection)!=1:raise ValueError('Select one schematic device.')
        from PySide6.QtWidgets import QWidget
        host=QWidget();form=QFormLayout(host);combo=QComboBox();form.addRow('Replacement model',combo)
        for key,e in self.project['pdk'].get('simulation',{}).get('catalog',{}).items():
            if not e.get('unavailable') and e['kind']==old['kind'] and set(e['pin_order'])==set(old['nets']):combo.addItem(e['label']+' · '+e['model'],key)
        if not combo.count():raise ValueError('No compatible catalog devices in the linked PDK.')
        def build():
            p=clone(self.project);d,notes=replacement(p['pdk'],old,combo.currentData(),binding_for(p['pdk'],old))
            cell=next(c for c in p['cells'] if c['id']==self.cid);cell['devices'][next(i for i,v in enumerate(cell['devices']) if v['id']==old['id'])]=d
            from .model import validate
            validate(p)
            return p,old['name']+' → '+binding_for(p['pdk'],d)['model']+'\n\nInstance ID, terminal nets, pin positions, rotation and physical links are retained.\nMOS width and length retain their physical values.\n\n'+('\n'.join(notes) or 'No parameter defaults or overrides change.')
        self.review_dialog('Replace PDK device',build,host)

    def migrate_pdk_dialog(self):
        if not self.idle_edit():return
        lock=self.project['pdk'].get('package_lock',{})
        options=[e for e in self.pdk_registry.entries() if e.get('id')==lock.get('id') and not e.get('error')]
        if not options:raise ValueError('Register a revision of this project’s PDK in PDK manager first.')
        labels=[e['id']+'@'+e['revision'] for e in options]
        key,ok=QInputDialog.getItem(self,'Migrate PDK revision','Target revision',labels,0,False)
        if not ok:return
        tech=self.pdk_registry.technology(key);catalog=tech['simulation']['catalog']
        used={d['model_ref']['device']:d for c in self.project['cells'] for d in c['devices'] if d.get('model_ref')}
        table=QTableWidget(len(used),2);table.setHorizontalHeaderLabels(['Current catalog device','Target device']);table.horizontalHeader().setStretchLastSection(True);table.setColumnWidth(0,330);combos={}
        for row,(old_key,d) in enumerate(used.items()):
            item=QTableWidgetItem(old_key);item.setFlags(item.flags() & ~Qt.ItemIsEditable);table.setItem(row,0,item);combo=QComboBox()
            for k,e in catalog.items():
                if not e.get('unavailable') and e['kind']==d['kind'] and set(e['pin_order'])==set(d['nets']):combo.addItem(e['label'],k)
            combo.setCurrentIndex(combo.findData(old_key));table.setCellWidget(row,1,combo);combos[old_key]=combo
        def build():
            if any(c.currentIndex()<0 for c in combos.values()):raise ValueError('Choose a compatible target for every current device.')
            p,report=migration_preview(self.project,tech,{k:c.currentData() for k,c in combos.items()})
            text=lock['id']+'@'+lock['revision']+' → '+key+'\n\n'
            text+='\n'.join(r['cell']+'/'+r['instance']+': '+r['from']+' → '+r['to']+'\n  '+'; '.join(r['notes']) for r in report)
            text+='\n\nModel files and revision change. Layout masks retain their GDS layer/datatype. Corner resets to nominal. Run simulation and physical verification again. Undo restores the prior project.'
            return p,text
        self.review_dialog('Migrate PDK revision',build,table)

    def component_dialog(self):
        if not self.idle_edit():return
        from .components import configure_component
        cid=self.cid;cell=self.cell
        def submit(values):
            from .spice_import import assignments
            defaults=assignments([line.strip() for line in values['defaults'].splitlines() if line.strip()])
            self.commit(lambda p:configure_component(p,cid,values['name'].strip(),values['ports'].split(),defaults),'Component properties')
        self.workflow_form('Component properties',[
            ('name','Component name',cell['name']),('ports','SPICE terminal order',' '.join(cell['ports'])),
            ('defaults','Parameter defaults',('\n'.join(k+'='+str(v) for k,v in cell.get('parameters',{}).items()),))],submit,
            'The active cell schematic is this component’s electrical implementation. Terminal order controls SPICE calls. Use {parameter} in device values; override defaults on each placed instance.')

    def import_component_dialog(self):
        if not self.idle_edit():return
        path,_=QFileDialog.getOpenFileName(self,'Import reusable SPICE subcircuit','','SPICE (*.cir *.spice *.sp)')
        if not path:return
        from .spice_import import import_spice
        from .components import import_component
        p,_=import_spice(path,self.project['pdk'] if self.project['pdk'].get('package_lock') else None)
        names=[c['name'] for c in p['cells'] if c['ports']]
        if not names:raise ValueError('No subcircuit with explicit terminals was found.')
        selected,ok=QInputDialog.getItem(self,'Select component','Subcircuit',names,0,False)
        if not ok:return
        result=[]
        self.commit(lambda q:result.append(import_component(q,path,selected)),'Import SPICE component')
        self.cid=result[0];self.selection=[];self.refresh(True);self.component_dialog()

    def runtime_dialog(self):
        if not self.idle_edit():return
        from .osdi import configure,verified
        dlg=QDialog(self);dlg.setWindowTitle('Simulation runtime');dlg.resize(760,480);v=QVBoxLayout(dlg)
        note=QLabel('OSDI libraries contain compiled device models for this computer. IHP uses PSP, resistor, varicap and capacitor libraries. Select the compiled .osdi files from your PDK installation.');note.setWordWrap(True);v.addWidget(note)
        listing=QPlainTextEdit();listing.setReadOnly(True);v.addWidget(listing,1);error=QLabel();error.setWordWrap(True);v.addWidget(error)
        def refresh():
            listing.setPlainText('\n'.join(e['path']+'\nSHA256 '+e['sha256'] for e in self.project.get('simulation_runtime',{}).get('osdi',[])))
        def choose():
            paths,_=QFileDialog.getOpenFileNames(dlg,'Select compiled device model libraries','','OSDI models (*.osdi)')
            if paths:
                try:
                    entries=configure(paths);self.commit(lambda p:p.setdefault('simulation_runtime',{}).update(osdi=entries),'Configure OSDI runtime');refresh();error.setText('Libraries recorded. Run a circuit to verify simulator compatibility.')
                except Exception as exc:error.setText(str(exc))
        def check():
            try:verified(self.project);error.setText('Library hashes and platform match. Simulator compatibility is established by a successful simulation.')
            except Exception as exc:error.setText(str(exc))
        def folder():
            path=QFileDialog.getExistingDirectory(dlg,'Select the folder produced by compile_ihp_osdi.py')
            if not path:return
            try:
                paths=sorted(Path(path).glob('*.osdi'))
                if not paths:raise ValueError('No compiled .osdi libraries found in this folder.')
                entries=configure(paths);self.commit(lambda p:p.setdefault('simulation_runtime',{}).update(osdi=entries),'Configure OSDI folder');refresh();error.setText(str(len(entries))+' libraries recorded. Run a circuit to verify simulator compatibility.')
            except Exception as exc:error.setText(str(exc))
        row=QHBoxLayout()
        for title,fn in [('Select libraries…',choose),('Load folder…',folder),('Verify files',check),('Clear',lambda:(self.commit(lambda p:p.pop('simulation_runtime',None),'Clear OSDI runtime'),refresh()))]:row.addWidget(self.button(title,fn=fn))
        v.addLayout(row);refresh();self._runtime_dialog=dlg;dlg.show()
