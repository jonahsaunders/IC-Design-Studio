"""One review for source repair, catalog matching and native project creation."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
    QCheckBox,QPushButton,QTabWidget,QTableWidgetItem,QFileDialog,QDialogButtonBox)
from .model import clone, file_digest, save_project


def show(window,source=None,libraries=None,project=None,initial=None):
    dlg=QDialog(window);dlg.setWindowTitle('Migrate to native project');dlg.setWindowModality(Qt.WindowModal);dlg.resize(1120,760)
    layout=QVBoxLayout(dlg);title=QLabel('Review native migration');title.setStyleSheet('font-size:22px;font-weight:600');layout.addWidget(title)
    note=QLabel('Link missing files, then optionally match devices to an installed PDK catalog. Model files and simulation programs stay with the project. Conversion checks do not replace simulation comparison.')
    note.setWordWrap(True);layout.addWidget(note)
    options=QHBoxLayout();options.addWidget(QLabel('Target device library'))
    technology=QComboBox();technology.setAccessibleName('Migration PDK catalog');technology.addItem('Preserve native SPICE definitions',None)
    for entry in window.pdk_registry.entries():
        if not entry.get('error'):technology.addItem(entry.get('name',entry['id'])+' · '+entry['revision'],entry['id']+'@'+entry['revision'])
    options.addWidget(technology,1);complete=QCheckBox('Require all model devices to match');complete.setChecked(True);options.addWidget(complete);layout.addLayout(options)
    tabs=QTabWidget();layout.addWidget(tabs,1)
    table=window.simulation_table(['Object','Migration','Details','Catalog match']);table.setColumnWidth(2,490);tabs.addTab(table,'Devices')
    deps=window.simulation_table(['Type','Reference','Status','Resolved file']);deps.setColumnWidth(1,310);tabs.addTab(deps,'Missing files / dependencies')
    detail=QLabel();detail.setWordWrap(True);layout.addWidget(detail)
    actions=QHBoxLayout();locate=QPushButton('Link selected file…');folder=QPushButton('Add library folder…');scan=QPushButton('Review again')
    for button in (locate,folder,scan):actions.addWidget(button)
    actions.addStretch();layout.addLayout(actions)
    status=QLabel();status.setWordWrap(True);layout.addWidget(status)
    buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);layout.addWidget(buttons)
    save=buttons.button(QDialogButtonBox.Save);save.setText('Save native project…')
    dlg.table=table;dlg.dependencies=deps;dlg.technology=technology;dlg.require_complete=complete;dlg.locate_button=locate
    dlg.file_locations={};dlg.choices={};dlg.library_paths=list(libraries or []);dlg.result_data=initial or {};dlg._reviewing=False

    def refresh():
        if dlg._reviewing:return
        dlg._reviewing=True
        try:
            tech=window.pdk_registry.technology(technology.currentData()) if technology.currentData() else None
            if source:
                from .native_migration import review_path
                result=review_path(source,dlg.library_paths,dlg.file_locations,tech,dlg.choices,complete.isChecked())
            else:
                from .native_spice import native
                from .native_migration import review
                result={'candidate':clone(project),'status':project.get('native_migration',{}).get('status','Complete'),'items':project.get('native_migration',{}).get('items',[])} if native(project) else review(project)
                if result['candidate'] and tech:
                    from .catalog_migration import review as catalog_review
                    result=catalog_review(result['candidate'],tech,dlg.choices,complete.isChecked())
            dlg.result_data=result;items=result['items'];table.setRowCount(len(items))
            for i,item in enumerate(items):
                for j,key in enumerate(('subject','status','detail')):
                    widget=QTableWidgetItem(item.get(key,''));widget.setToolTip(item.get('detail',''));table.setItem(i,j,widget)
                table.removeCellWidget(i,3)
                if item.get('choices'):
                    combo=QComboBox();combo.addItem('Choose matching model…','')
                    for key in item['choices']:combo.addItem(key,key)
                    combo.setCurrentIndex(max(0,combo.findData(item.get('selected',''))))
                    # Capture selection by source cell/name, stable across re-import.
                    identity=item.get('source_key',item['object'])
                    def choose(index,combo=combo,identity=identity):
                        dlg.choices[identity]=combo.currentData();refresh()
                    combo.activated.connect(choose);table.setCellWidget(i,3,combo)
            dependencies=result.get('dependencies',[]);deps.setRowCount(len(dependencies))
            for i,item in enumerate(dependencies):
                for j,key in enumerate(('kind','reference','status','path')):deps.setItem(i,j,QTableWidgetItem(item.get(key,'')))
            missing=sum(d['status']=='Missing' for d in dependencies)
            first=next((i for i,d in enumerate(dependencies) if d['status']=='Missing'),0)
            if dependencies:deps.selectRow(first)
            if missing:tabs.setCurrentWidget(deps)
            save.setEnabled(result.get('candidate') is not None)
            save.setText('Save native project…' if result['status']=='Complete' else 'Save migration draft…')
            title.setText('Migration '+result['status'].lower())
            status.setText(str(missing)+' missing file(s). '+str(result.get('converted',0))+' catalog device(s) matched. '+str(result.get('unmatched',0))+' model device(s) need attention.' if tech or missing else 'Review the conversion details before saving.')
        except (ValueError,OSError,KeyError) as exc:
            save.setEnabled(False);status.setText(str(exc));dlg.result_data={'candidate':None,'status':'Needs attention','items':[],'dependencies':[]}
        finally:dlg._reviewing=False;selection()

    def selection():
        rows=dlg.result_data.get('dependencies',[]);index=deps.currentRow();item=rows[index] if 0<=index<len(rows) else None
        locate.setEnabled(bool(source and item));folder.setEnabled(bool(source))
        detail.setText((item['reference']+'\nReferenced by: '+item['parent']+'\n'+item.get('hint','')) if item else 'Double-click a dependency to link its local file. Linked folders are searched for related symbols too.')

    def link_file():
        rows=dlg.result_data.get('dependencies',[]);index=deps.currentRow()
        if not 0<=index<len(rows):return
        item=rows[index];chosen,_=QFileDialog.getOpenFileName(dlg,'Link '+item['reference'],str(Path(source).parent),'All files (*)')
        if not chosen:return
        dlg.file_locations[str(Path(item['parent']).resolve())+'::'+item['reference']]=chosen
        from .xschem_paths import reference_folder
        inferred=reference_folder(item['reference'],chosen)
        if inferred not in dlg.library_paths:dlg.library_paths.append(inferred)
        refresh()

    def add_folder():
        chosen=QFileDialog.getExistingDirectory(dlg,'Locate symbol or model library',str(Path(source).parent))
        if chosen:
            if chosen not in dlg.library_paths:dlg.library_paths.append(chosen)
            refresh()

    def accept():
        result=dlg.result_data
        if result.get('candidate') is None:return
        for path,sha in result.get('stamp',{}).items():
            if not Path(path).is_file() or file_digest(path)!=sha:
                status.setText('A source file changed after review. Review again before saving.');save.setEnabled(False);return
        candidate=result['candidate']
        target,_=QFileDialog.getSaveFileName(dlg,'Save native project',candidate['name']+'-native.icproj','IC Studio project (*.icproj)')
        if not target:return
        if window.path and Path(target).resolve()==Path(window.path).resolve():raise ValueError('Choose a new filename to preserve the source project.')
        if not window.maybe_save():return
        save_project(candidate,target)
        from .native_migration import export_report
        export_report(candidate,Path(target).with_suffix('.migration.json'))
        window.settings.setValue('xschem/library_paths',dlg.library_paths)
        window.set_project(candidate,target);window.schematic.fit();dlg.accept()

    technology.currentIndexChanged.connect(lambda *_:refresh());complete.toggled.connect(lambda *_:refresh())
    deps.itemSelectionChanged.connect(selection);deps.cellDoubleClicked.connect(lambda *_:window.guard(link_file))
    locate.clicked.connect(lambda:window.guard(link_file));folder.clicked.connect(lambda:window.guard(add_folder));scan.clicked.connect(refresh)
    buttons.accepted.connect(lambda:window.guard(accept));buttons.rejected.connect(dlg.reject)
    dlg.rescan=refresh;dlg.link_file=link_file;window._migration_dialog=dlg;refresh();dlg.show();return dlg
