"""Consistent numeric moves with a reversible canvas preview in either editor."""
from PySide6.QtCore import QPointF, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QLabel, QDialogButtonBox, QPushButton)
from .model import scalar


class PreciseMove(QDialog):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        self.mode = studio.current_mode
        self.canvas = studio.layout if self.mode == 'layout' else studio.schematic
        self.identity = (studio.project['id'], studio.project['revision'], studio.cid, tuple(studio.selection))
        self.owns_preview = False
        self.setWindowTitle('Move selection precisely')
        self.resize(410, 250)
        root = QVBoxLayout(self)
        unit = 'µm' if self.mode == 'layout' else 'schematic units'
        label = QLabel(f'Move {len(studio.selection)} selected objects. Positive X moves right; positive Y moves down.')
        label.setWordWrap(True); root.addWidget(label)
        form = QFormLayout(); self.x = QLineEdit('0'); self.y = QLineEdit('0')
        self.x.setAccessibleName('Horizontal move in '+unit); self.y.setAccessibleName('Vertical move in '+unit)
        form.addRow('Horizontal ('+unit+')', self.x); form.addRow('Vertical ('+unit+')', self.y); root.addLayout(form)
        self.status = QLabel('Preview the position, then apply. Connection rules are checked when applying.')
        self.status.setWordWrap(True); root.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        self.preview_button = QPushButton('Preview')
        buttons.addButton(self.preview_button, QDialogButtonBox.ActionRole)
        self.apply_button = buttons.button(QDialogButtonBox.Apply)
        self.preview_button.clicked.connect(self.preview); self.apply_button.clicked.connect(self.apply)
        buttons.rejected.connect(self.reject); root.addWidget(buttons)
        self.timer = QTimer(self); self.timer.setInterval(150); self.timer.timeout.connect(self.check_state); self.timer.start()

    def current(self):
        s = self.studio
        return self.identity == (s.project['id'], s.project['revision'], s.cid, tuple(s.selection)) and s.current_mode == self.mode

    def delta(self):
        if not self.current():raise ValueError('The selection or design changed. Close this window and start again.')
        scale = 1000 if self.mode == 'layout' else 1
        values = [scalar(w.text()) * scale for w in (self.x, self.y)]
        grid = self.studio.project['pdk']['grid'] if self.mode == 'layout' else 10
        if any(abs(v / grid - round(v / grid)) > 1e-8 for v in values):
            raise ValueError('Use a multiple of '+str(grid/scale)+(' µm.' if self.mode == 'layout' else ' schematic units.'))
        if not any(values):raise ValueError('Enter a nonzero move distance.')
        return [round(v) for v in values]

    def clear_preview(self):
        if self.owns_preview:
            self.canvas.anchor = self.canvas.drag = None; self.canvas.moving = False
            self.canvas.update(); self.owns_preview = False

    def preview(self):
        try:
            dx, dy = self.delta()
            self.canvas.cancel_gesture(); self.canvas.tool = 'select'
            self.canvas.anchor = QPointF(0, 0); self.canvas.drag = QPointF(dx, dy); self.canvas.moving = True
            self.owns_preview = True; self.canvas.update()
            self.status.setText('Position preview. Apply checks the move and creates one undo step.')
        except Exception as exc:self.status.setText(str(exc))

    def check_state(self):
        if not self.current():
            self.clear_preview(); self.apply_button.setEnabled(False); self.preview_button.setEnabled(False)
            self.status.setText('The selection or design changed. Close this window and start again.')

    def apply(self):
        try:
            dx, dy = self.delta(); self.clear_preview()
            self.studio.move(list(self.identity[3]), dx, dy, self.mode)
            if self.studio.project['revision'] != self.identity[1]:self.accept()
        except Exception as exc:self.status.setText(str(exc))

    def done(self, result):
        self.timer.stop(); self.clear_preview(); super().done(result)


def install(studio):
    def show():
        if not studio.idle_edit():return
        if not studio.selection:raise ValueError('Select the objects to move first.')
        old = getattr(studio, '_precise_move', None)
        if old:old.reject()
        studio._precise_move = PreciseMove(studio); studio._precise_move.show()
        return studio._precise_move
    studio.precise_move = show
    studio.action(studio.task_menus['Edit'], 'Move selection precisely…', show)
