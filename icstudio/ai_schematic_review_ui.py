"""Side-by-side property values and a switchable schematic for one reviewed edit."""
from PySide6.QtCore import Qt, QEvent, QPointF, QTimer
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit,
                               QPushButton, QSplitter, QTabBar, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from .analog_widgets import table
from .canvas import Canvas


class PreviewCanvas(Canvas):
    def __init__(self, panel, proposal):
        super().__init__('schematic')
        self.dark = panel.studio.dark
        self.proposal = proposal
        self.pdk = panel.pinned.project['pdk']
        ids = set(panel.pinned.selection) | {e.part_id for e in proposal.edits}
        self.frame = None
        self.set_data(proposal.after,self.pdk)
        for group in ('devices','wires','labels'):
            for obj in proposal.after.get(group,[]):
                if obj['id'] in ids:
                    box = self.fit_bounds(obj)
                    self.frame = self.frame.united(box) if self.frame is not None else box
        self.setAccessibleName('Schematic change preview')

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and not self.space:
            event.accept()
            return
        super().mousePressEvent(event)

    def fit(self):
        if self.frame is None:
            return super().fit()
        box = self.frame.adjusted(-55,-55,55,55)
        self.scale = min(self.width()/box.width(),self.height()/box.height())
        self.offset = QPointF(self.width()/2,self.height()/2) - box.center()*self.scale
        self.update()


class ChangeReview(QDialog):
    def __init__(self, panel, proposal):
        super().__init__(panel.studio)
        self.panel, self.proposal = panel, proposal
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle('Review Schematic Changes')
        self.resize(830,650)
        root = QVBoxLayout(self)
        root.setContentsMargins(16,14,16,12)
        root.setSpacing(8)
        ctx = panel.pinned
        shared = any(d['kind']=='X' and d.get('cell')==ctx.cid for c in ctx.project['cells'] for d in c['devices'])
        count = len(proposal.edits)
        title = QLabel(f"{count} proposed {'change' if count == 1 else 'changes'}")
        title.setProperty('role','title')
        root.addWidget(title)
        context = QLabel(f"{ctx.cell['name']} · revision {ctx.project['revision']}" +
                       (' · edits affect every instance of this cell' if shared else ''))
        context.setTextFormat(Qt.PlainText)
        context.setWordWrap(True)
        context.setProperty('role','muted')
        root.addWidget(context)
        question = getattr(panel,'pending_question','')
        if question:
            request = QLabel(question if len(question)<=180 else question[:179]+'…')
            request.setTextFormat(Qt.PlainText)
            request.setWordWrap(True)
            request.setToolTip(question)
            request.setAccessibleDescription(question)
            root.addWidget(request)
        split = QSplitter(Qt.Vertical)
        root.addWidget(split,1)
        self.tabs = QTabWidget()
        split.addWidget(self.tabs)
        schematic = QWidget()
        view = QVBoxLayout(schematic)
        view.setContentsMargins(0,6,0,0)
        self.states = QTabBar()
        self.states.setObjectName('schematicComparison')
        self.states.setAccessibleName('Schematic version')
        self.states.setExpanding(False)
        self.states.addTab('Before')
        self.states.addTab('Proposed')
        view.addWidget(self.states, 0, Qt.AlignLeft)
        self.canvas = PreviewCanvas(panel,proposal)
        view.addWidget(self.canvas,1)
        self.tabs.addTab(schematic,'Schematic')
        self.diff = QPlainTextEdit()
        self.diff.setReadOnly(True)
        self.diff.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.diff.setAccessibleName('Exact changes to the saved schematic fields')
        self.diff.setObjectName('schematicDiff')
        self.tabs.addTab(self.diff,'Exact Changes')
        self.tabs.currentChanged.connect(self.show_diff)
        self.changes = table(['Component','Property / operation','Before','Proposed'])
        self.changes.setAccessibleName('Proposed schematic edits with original and new values')
        self.changes.setRowCount(len(proposal.edits))
        self.changes.setShowGrid(False)
        self.changes.verticalHeader().setDefaultSectionSize(max(30,self.fontMetrics().height()+12))
        self.changes.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.changes.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.changes.horizontalHeader().setStretchLastSection(True)
        kinds = {d['id']:d['kind'] for d in proposal.after['devices']}
        values = {'R':'Resistance (Ω)','C':'Capacitance (F)','L':'Inductance (H)','V':'Voltage (V)','I':'Current (A)'}
        for i,edit in enumerate(proposal.edits):
            field = values.get(kinds[edit.part_id],'Value') if edit.field=='value' else edit.field
            for j,value in enumerate((edit.name,field,edit.before,edit.after)):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.changes.setItem(i,j,item)
        split.addWidget(self.changes)
        split.setSizes([380,145])
        self.states.currentChanged.connect(self.show_state)
        self.changes.itemSelectionChanged.connect(self.show_state)
        self.states.setCurrentIndex(1)
        self.message = QLabel()
        self.message.setTextFormat(Qt.PlainText)
        self.message.setWordWrap(True)
        root.addWidget(self.message)
        controls = QHBoxLayout()
        root.addLayout(controls)
        controls.addStretch()
        self.discard = QPushButton('Discard')
        self.apply = QPushButton('Apply Changes')
        self.apply.setProperty('role','primary')
        for button in (self.discard,self.apply):
            button.setAutoDefault(False)
            controls.addWidget(button)
        self.discard.clicked.connect(panel.discard_change)
        self.apply.clicked.connect(self.commit)
        self.watch = QTimer(self,interval=300)
        self.watch.timeout.connect(self.check_current)
        self.watch.start()
        self.check_current()

    def show_state(self, *_):
        cell = self.proposal.after if self.states.currentIndex()==1 else self.proposal.before
        rows = self.changes.selectionModel().selectedRows()
        edits = [self.proposal.edits[r.row()] for r in rows] if rows else self.proposal.edits
        self.canvas.set_data(cell,self.canvas.pdk,[e.part_id for e in edits])
        self.canvas.fit()

    def show_diff(self,index):
        if index==1 and not self.diff.toPlainText():
            self.diff.setPlainText(self.proposal.details())

    def changeEvent(self,event):
        if event.type()==QEvent.PaletteChange and hasattr(self,'canvas'):
            self.canvas.dark = self.panel.studio.dark
            self.canvas.update()
        super().changeEvent(event)

    def check_current(self):
        panel, studio = self.panel, self.panel.studio
        ctx = panel.pinned
        current = (panel.change is self.proposal and ctx is not None and studio.current_mode=='schematic'
                   and studio.cid==ctx.cid and studio.project['id']==ctx.project['id']
                   and studio.project['revision']==ctx.project['revision'] and set(studio.selection)==set(ctx.selection)
                   and studio.net==ctx.net)
        self.apply.setEnabled(current)
        if not current:
            self.message.setText('The selection or design changed. Return to the original selection or request a new preview.')
        elif not getattr(self,'apply_error',False):
            self.message.setText('Apply these edits together. Edit → Undo reverses them in one step.')
        return current

    def commit(self):
        studio = self.panel.studio
        if not studio.flush_inspector() or not self.check_current():
            return
        try:
            if studio.capture_commit(self.proposal.apply,'Apply AI schematic changes'):
                self.panel.change_applied()
        except (ValueError, RuntimeError, OSError) as exc:
            self.apply_error = True
            self.message.setText(str(exc))
