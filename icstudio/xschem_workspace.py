"""Native dependency review and repair for direct schematic import."""
from pathlib import Path
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,
    QLineEdit,QPlainTextEdit,QPushButton,QDialogButtonBox,QTabWidget,
    QTableWidgetItem,QFileDialog,QHeaderView)
from .xschem_project import review_schematic,apply_review,default_libraries
from .xschem_compat import review_project
from .xschem_paths import library_folders,reference_folder


def diagnostic_text(record):
    lines=['Xschem import review',record['source'],'', 'Search folders:']
    lines.extend(record.get('library_paths',[]))
    lines.extend(['','Dependencies:'])
    for item in record['dependencies']:
        lines.append(item['status']+' | '+item['kind']+' | '+item['reference']+' | '+item['path'])
        if item.get('hint'):lines.append('  '+item['hint'])
    lines.extend(['','Import errors:']+record['errors']+['','Review notes:']+record['warnings'])
    return '\n'.join(lines)


def show_review(window,path,library_paths=None,auto_open=False):
    dlg=QDialog(window);dlg.setWindowTitle('Import Xschem schematic');dlg.resize(1120,790)
    layout=QVBoxLayout(dlg)
    title=QLabel('Open an existing Xschem project');title.setStyleSheet('font-size:20px;font-weight:600');layout.addWidget(title)
    file=QLineEdit(str(path));file.setReadOnly(True);file.setAccessibleName('Top schematic');layout.addWidget(file)
    note=QLabel('Standard Xschem symbols and GF180 simulation libraries are included. Add a folder only for custom dependencies.');note.setWordWrap(True);layout.addWidget(note)
    if library_paths is None:
        saved=window.settings.value('xschem/library_paths',[])
        if isinstance(saved,str):saved=[saved]
        library_paths=list(dict.fromkeys(list(saved or [])+default_libraries()))
    row=QHBoxLayout();paths=QPlainTextEdit('\n'.join(library_paths));paths.setPlaceholderText('Library or installation folders — one per line');paths.setAccessibleName('Xschem library folders');paths.setMaximumHeight(78);row.addWidget(paths,1)
    add=QPushButton('Add library folder…');row.addWidget(add);scan=QPushButton('Review files');row.addWidget(scan);layout.addLayout(row)
    state=QLabel();state.setWordWrap(True);layout.addWidget(state)
    tabs=QTabWidget();layout.addWidget(tabs,1)
    dependencies=window.simulation_table(['Type','Reference','Status','Resolved file'])
    dependencies.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    dependencies.horizontalHeader().setStretchLastSection(True)
    for col,width in enumerate((125,310,80)):dependencies.setColumnWidth(col,width)
    tabs.addTab(dependencies,'Dependencies')
    cells=window.simulation_table(['Cell','Devices','Wires','Ports']);tabs.addTab(cells,'Schematics')
    changes=window.simulation_table(['Cell','Object','Change','Before','After']);tabs.addTab(changes,'Changes')
    messages=QPlainTextEdit();messages.setReadOnly(True);tabs.addTab(messages,'Review notes')
    detail=QPlainTextEdit();detail.setReadOnly(True);detail.setMaximumHeight(86);detail.setAccessibleName('Selected dependency details');layout.addWidget(detail)
    actions=QHBoxLayout();locate=QPushButton('Locate selected file…');locate.setEnabled(False);actions.addWidget(locate)
    copy=QPushButton('Copy diagnostic report');actions.addWidget(copy);actions.addStretch();layout.addLayout(actions)
    buttons=QDialogButtonBox(QDialogButtonBox.Open|QDialogButtonBox.Cancel)
    open_button=buttons.button(QDialogButtonBox.Open);open_button.setText('Open reviewed project');layout.addWidget(buttons)
    dlg.record=None;dlg.dependencies=dependencies;dlg.library_paths=paths;dlg.open_button=open_button;dlg.file_locations={};dlg.locate_button=locate;dlg.detail=detail;dlg.copy_button=copy

    def selection():
        index=dependencies.currentRow();rows=(dlg.record or {}).get('dependencies',[])
        item=rows[index] if 0<=index<len(rows) else None
        locate.setEnabled(bool(item and item['kind']!='Native metadata'))
        if item:
            text=item['reference']+'\n'+item.get('hint','')
            text+='\n'+('Using: '+item['path'] if item['path'] else 'Looked in: '+'; '.join(item.get('searched',[])))
            detail.setPlainText(text.strip())
        else:detail.setPlainText('Select a dependency to see its lookup paths and repair guidance.')

    def review():
        technology=window.project['pdk'] if window.project['pdk'].get('package_lock') else None
        roots=[s.strip() for s in paths.toPlainText().splitlines() if s.strip()]
        record=review_project(file.text(),roots,technology,dlg.file_locations);dlg.record=record
        window.settings.setValue('xschem/library_paths',roots)
        dependencies.setRowCount(len(record['dependencies']))
        for i,item in enumerate(record['dependencies']):
            for j,key in enumerate(('kind','reference','status','path')):
                widget=QTableWidgetItem(item[key]);widget.setToolTip(item.get('hint','')+'\n'+item.get('path',''));dependencies.setItem(i,j,widget)
        project=record['candidate'];cs=(project or {}).get('cells',[]);cells.setRowCount(len(cs))
        changes.setRowCount(len(record.get('changes',[])))
        for i,item in enumerate(record.get('changes',[])):
            for j,key in enumerate(('cell','object','change','before','after')):
                cell=QTableWidgetItem(item.get(key,''));cell.setToolTip(item.get(key,''));changes.setItem(i,j,cell)
        if record.get('mode')=='native':title.setText('Review edits from Xschem');tabs.setCurrentWidget(changes)
        for i,c in enumerate(cs):
            for j,value in enumerate((c['name'],len(c['devices']),len(c['wires']),', '.join(c['ports']))):cells.setItem(i,j,QTableWidgetItem(str(value)))
        messages.setPlainText(diagnostic_text(record))
        missing=sum(d['status']=='Missing' for d in record['dependencies'])
        if project:status=f"Ready to open: {len(cs)} schematics, {sum(len(c['devices']) for c in cs)} components."+(' Missing custom symbols remain visible placeholders; simulation needs their files.' if missing else ' All dependencies resolved.')
        elif missing:status=f'{missing} missing dependencies. Select a row and locate its file, or add a library folder. Review notes also list format and simulation limits.'
        else:status=f"Files located; {len(record['errors'])} import issue(s) remain. Open Review notes for the unsupported circuit or simulation constructs."
        if any('native setup conversion is not supported' in w for w in record['warnings']):status+=' This project also contains an ngspice control program that native import cannot convert.'
        state.setText(status);open_button.setEnabled(bool(project) and not record['errors'])
        tabs.setTabText(3,'Review notes'+(f" ({len(record['errors'])} issues)" if record['errors'] else ''))
        first=next((i for i,d in enumerate(record['dependencies']) if d['status']=='Missing'),0)
        if record['dependencies']:dependencies.selectRow(first)
        selection()

    def add_folder():
        directory=QFileDialog.getExistingDirectory(dlg,'Add Xschem library or installation directory',str(Path(file.text()).parent))
        if directory:
            existing=[s for s in paths.toPlainText().splitlines() if s.strip()]
            paths.setPlainText('\n'.join(library_folders(existing+[directory])));review()

    def locate_file():
        index=dependencies.currentRow()
        if not dlg.record or not 0<=index<len(dlg.record['dependencies']):return
        item=dlg.record['dependencies'][index]
        if item['kind']=='Native metadata':return
        chosen,_=QFileDialog.getOpenFileName(dlg,'Locate '+item['reference'],str(Path(file.text()).parent),'All files (*)')
        if not chosen:return
        dlg.file_locations[str(Path(item['parent']).resolve())+'::'+item['reference']]=chosen
        existing=[s for s in paths.toPlainText().splitlines() if s.strip()]
        paths.setPlainText('\n'.join(library_folders(existing+[reference_folder(item['reference'],chosen)])))
        review()

    def accept():
        p=apply_review(dlg.record)
        if window.maybe_save():window.set_project(p);window.mode_combo.setCurrentIndex(0);window.schematic.fit();dlg.accept()

    paths.textChanged.connect(lambda:open_button.setEnabled(False))
    dependencies.itemSelectionChanged.connect(selection)
    dependencies.cellDoubleClicked.connect(lambda *_:window.guard(locate_file))
    add.clicked.connect(lambda:window.guard(add_folder));scan.clicked.connect(lambda:window.guard(review));locate.clicked.connect(lambda:window.guard(locate_file))
    copy.clicked.connect(lambda:QApplication.clipboard().setText(diagnostic_text(dlg.record)))
    buttons.accepted.connect(lambda:window.guard(accept));buttons.rejected.connect(dlg.reject)
    dlg.rescan=review;dlg.locate_file=locate_file;window._import_dialog=dlg;review()
    if auto_open and dlg.record.get('mode')!='native' and dlg.record['candidate'] and not dlg.record['errors'] and not any(d['status']=='Missing' for d in dlg.record['dependencies']):accept()
    else:dlg.show()
    return dlg
