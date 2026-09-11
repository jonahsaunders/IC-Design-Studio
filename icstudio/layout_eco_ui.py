"""Hierarchy-wide selectable schematic-to-layout review."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QCheckBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout, QLineEdit)
from .model import design_digest


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
    def populate():
        state['report'] = inventory(studio.project,cid,scope.isChecked()); rows = state['report']['devices']; table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            check = QTableWidgetItem(); check.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable if row['action'] else Qt.NoItemFlags); check.setCheckState(Qt.Unchecked); table.setItem(i,0,check)
            for j,value in enumerate((row['cell']+' / '+row['name'],row['status'],row['action'],row['detail']),1):
                item=QTableWidgetItem(value);item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable);table.setItem(i,j,item)
        table.resizeColumnsToContents()
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
            studio.review_dialog('Apply schematic-driven layout changes',lambda:(candidate,text));dlg.accept()
        except Exception as exc:error.setText(str(exc))
    button.clicked.connect(preview);dlg.table=table;dlg.preview_button=button;studio._layout_eco_dialog=dlg;dlg.show();return dlg
