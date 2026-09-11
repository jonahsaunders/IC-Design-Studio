"""Hierarchy-wide selectable schematic-to-layout review."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QCheckBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout, QLineEdit, QHBoxLayout,
    QAbstractItemView, QWidget)
from .model import clone, design_digest


def show(studio):
    if not studio.idle_edit(): return
    from .layout_eco_hierarchy import inventory, propose
    from .layout_development_ui import point, nm
    cid = studio.cid; dlg = QDialog(studio); dlg.setWindowTitle('Schematic-driven layout'); dlg.resize(1050,680)
    layout = QVBoxLayout(dlg)
    note = QLabel('Select the changes to preview. Shared cell masters are updated once. Missing devices use declared recipes; unsupported devices need an explicit physical implementation.'); note.setWordWrap(True); layout.addWidget(note)
    scope = QCheckBox('Include schematic hierarchy'); scope.setChecked(True); layout.addWidget(scope)
    variants=QPushButton('Resolve parameter variants…');layout.addWidget(variants)
    def specialize():
        try:
            from .physical_variants import propose as specialize_project
            candidate,report=specialize_project(studio.project,cid)
            details='\n'.join(r['instance']+' → '+r['variant'] for r in report['instances'])
            details+='\n\n'+str(report['variants'])+' explicit cell variants. Resolved electrical values and nets match the original hierarchy. Existing geometry is retained; review its parameter updates and routing afterward.'
            studio.review_dialog('Create physical parameter variants',lambda:(candidate,details));dlg.accept()
        except Exception as exc:error.setText(str(exc))
    variants.clicked.connect(specialize)
    table = QTableWidget(0, 5); table.setHorizontalHeaderLabels(['Apply', 'Cell / device', 'State', 'Action', 'Details']); table.horizontalHeader().setSectionResizeMode(4,QHeaderView.Stretch); layout.addWidget(table,1)
    table.setAccessibleName('Schematic-driven layout changes'); state = {}
    table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection)
    impact=QLabel('Select a device to inspect its schematic, physical implementation and connected nets.');impact.setWordWrap(True);impact.setAccessibleName('Selected device change impact');layout.addWidget(impact)
    inspect_row=QHBoxLayout();schematic_button=QPushButton('Show in schematic');physical_button=QPushButton('Show in layout')
    inspect_row.addWidget(schematic_button);inspect_row.addWidget(physical_button);layout.addLayout(inspect_row)
    def selected_row():
        index=table.currentRow()
        return state['report']['devices'][index] if 0<=index<len(state['report']['devices']) else None
    def inspect():
        row=selected_row();schematic_button.setEnabled(False);physical_button.setEnabled(False)
        if not row:return
        from .layout_eco_review import device_impact
        info=device_impact(studio.project,row['cell_id'],row['device_id']);state['impact']=info
        impact.setText(info['summary']);schematic_button.setEnabled(bool(info['device']))
        physical_button.setEnabled(bool(info['layout_objects']))
    def navigate(mode):
        try:
            if not studio.flush_inspector():return
            row=selected_row()
            if row is None:return
            from .layout_eco_review import device_impact
            info=device_impact(studio.project,row['cell_id'],row['device_id'])
            studio.cid=row['cell_id'];studio.selection=[];studio.mode_combo.setCurrentIndex(0 if mode=='schematic' else 1);studio.refresh(True)
            ids=([row['device_id']] if info['device'] else [])+info['layout_objects']
            studio.select(ids,mode)
            studio.statusBar().showMessage(info['summary'],15000)
        except Exception as exc:error.setText(str(exc))
    table.itemSelectionChanged.connect(inspect)
    schematic_button.clicked.connect(lambda:navigate('schematic'));physical_button.clicked.connect(lambda:navigate('layout'))
    def populate():
        state['report'] = inventory(studio.project,cid,scope.isChecked()); rows = state['report']['devices']; table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            check = QTableWidgetItem(); check.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable if row['action'] else Qt.NoItemFlags); check.setCheckState(Qt.Unchecked); table.setItem(i,0,check)
            for j,value in enumerate((row['cell']+' / '+row['name'],row['status'],row['action'],row['detail']),1):
                item=QTableWidgetItem(value);item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable);table.setItem(i,j,item)
        table.resizeColumnsToContents()
        if rows:table.selectRow(0)
    scope.toggled.connect(populate); populate()
    select_missing=QPushButton('Select missing and changed devices');layout.addWidget(select_missing)
    def select_actionable():
        for i,row in enumerate(state['report']['devices']):
            table.item(i,0).setCheckState(Qt.Checked if row['action'] in ('add','update','rebind') else Qt.Unchecked)
    select_missing.clicked.connect(select_actionable)
    form = QFormLayout(); origin=QLineEdit('0, 0'); pitch=QLineEdit('20');form.addRow('New footprint origin X, Y (µm)',origin);form.addRow('New footprint pitch (µm)',pitch);layout.addLayout(form)
    preserve=QCheckBox('Preserve attached routes and surviving terminal connectivity');preserve.setChecked(True);layout.addWidget(preserve)
    error=QLabel();error.setWordWrap(True);layout.addWidget(error);button=QPushButton('Preview selected changes');layout.addWidget(button)
    def preview():
        try:
            if state['report']['design_hash'] != design_digest(studio.project): raise ValueError('The project changed. Reopen this review.')
            chosen=[(r['cell_id'],r['device_id']) for i,r in enumerate(state['report']['devices']) if table.item(i,0).checkState()==Qt.Checked]
            candidate,report=propose(studio.project,cid,chosen,studio.layout.locked_layers,preserve.isChecked(),point(origin.text()),nm(pitch.text()),scope.isChecked())
            text='\n'.join(r['cell']+' / '+r['name']+': '+r['action'] for r in report['changes'])
            text+='\n\n'+str(len(report['affected_cells']))+' edited masters; '+str(len(report['adjusted_routes']))+' adjusted routes.\n'
            text+='\n'.join(next(c['name'] for c in candidate['cells'] if c['id']==k)+': '+str(len(v))+' connectivity findings' for k,v in report['connectivity'].items())
            text+='\n\nApply is one undoable transaction. Independent routes remain after orphan removal. Run full DRC/LVS after reviewing every affected parent.'
            from .layout_eco_review import proposal_summary
            text+='\n\n'+proposal_summary(studio.project,candidate,report)
            before=clone(studio.project)
            controls=QWidget();controls_layout=QHBoxLayout(controls);compare=QPushButton('Inspect geometry before and after');controls_layout.addWidget(compare)
            def comparison():
                from .team_review_ui import RevisionComparison
                studio._eco_comparison=RevisionComparison(studio._review_dialog,before,candidate);studio._eco_comparison.view_mode.setCurrentIndex(0);studio._eco_comparison.show()
            compare.clicked.connect(comparison)
            studio.review_dialog('Apply schematic-driven layout changes',lambda:(candidate,text),controls);dlg.accept()
        except Exception as exc:error.setText(str(exc))
    def check_revision():
        stale=state['report']['design_hash']!=design_digest(studio.project)
        button.setEnabled(not stale);variants.setEnabled(not stale)
        if stale:error.setText('The design changed. Reopen this review before previewing changes.');timer.stop()
    # Cheap revision identity check during polling; the apply path still checks
    # the full design hash, including edits made by legacy metadata callers.
    starting=(id(studio.project),studio.project['revision'])
    timer=QTimer(dlg);timer.setInterval(300)
    timer.timeout.connect(lambda:check_revision() if starting!=(id(studio.project),studio.project['revision']) else None);timer.start()
    button.clicked.connect(preview);dlg.table=table;dlg.preview_button=button;dlg.schematic_button=schematic_button;dlg.physical_button=physical_button;dlg.impact=impact;studio._layout_eco_dialog=dlg;dlg.show();return dlg
