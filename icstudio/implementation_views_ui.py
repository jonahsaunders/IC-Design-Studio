"""Saved-bench implementation selection; imported netlists stay project-owned."""
from pathlib import Path
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QComboBox,
    QPushButton, QFileDialog, QInputDialog)
from .implementation_views import capture, describe, subcircuits, MAX_BYTES


def editor(project, seed, bench_combo):
    page=QWidget();layout=QVBoxLayout(page)
    note=QLabel('Choose the circuit implementation for Simulate. Imported netlists travel with the project. Verify layout still runs fresh process checks and extraction.');note.setWordWrap(True);layout.addWidget(note)
    combo=QComboBox();combo.setAccessibleName('Saved circuit implementation');layout.addWidget(combo)
    button=QPushButton('Import implementation…');layout.addWidget(button)
    detail=QLabel();detail.setWordWrap(True);layout.addWidget(detail)
    error=QLabel();error.setWordWrap(True);error.setProperty('role','error');layout.addWidget(error);layout.addStretch()
    page.pending=[];page.combo=combo;page.import_button=button;page.error=error
    by={c['id']:c for c in project['cells']}
    def cell_id():
        return next(d['cell'] for d in by[bench_combo.currentData()]['devices'] if d['kind']=='X')
    def records():return project.get('implementation_views',[])+page.pending
    def selected():
        view=next((v for v in records() if v['id']==combo.currentData()),None)
        detail.setText((view['source_name']+'\n'+view['qualification']) if view else 'Use the editable schematic and its current parameters.')
    def refresh(preferred=None):
        ident=preferred or combo.currentData();combo.blockSignals(True);combo.clear();combo.addItem('Schematic',None)
        for view in records():
            if view['cell_id']==cell_id():combo.addItem(describe(project,view),view['id'])
        combo.setCurrentIndex(max(0,combo.findData(ident)));combo.blockSignals(False);selected()
    def import_file():
        try:
            error.clear();path,_=QFileDialog.getOpenFileName(page,'Import circuit implementation','','SPICE netlists (*.spice *.sp *.cir);;All files (*)')
            if not path:return
            source=Path(path)
            if source.stat().st_size>MAX_BYTES:raise ValueError('Implementation netlists are limited to 16 MiB.')
            text=source.read_text(encoding='utf-8');interfaces=subcircuits(text)
            top,ok=QInputDialog.getItem(page,'Implementation interface','Top subcircuit',[s['name'] for s in interfaces],0,False)
            if not ok:return
            name,ok=QInputDialog.getText(page,'Implementation name','Name',text='extracted')
            if not ok:return
            kind,ok=QInputDialog.getItem(page,'Implementation contents','Extraction model',['External implementation','Extracted capacitance','Extracted RC'],0,False)
            if not ok:return
            view=capture(project,cell_id(),name.strip(),text,top,{'External implementation':'external','Extracted capacitance':'capacitance','Extracted RC':'rc'}[kind],path)
            if any(v['cell_id']==view['cell_id'] and v['name'].casefold()==view['name'].casefold() for v in records()):raise ValueError('Choose a new implementation name for this cell.')
            page.pending.append(view);refresh(view['id'])
        except (ValueError,OSError,UnicodeError) as exc:error.setText(str(exc))
    combo.currentIndexChanged.connect(selected);bench_combo.currentIndexChanged.connect(lambda:refresh())
    button.clicked.connect(import_file);page.value=combo.currentData;page.refresh=refresh
    refresh(seed.get('implementation_view'));return page
