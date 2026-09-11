"""Read-only three-version geometry review for retained live edits."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QGraphicsScene,
    QGraphicsView, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget)

from .collaboration_dashboard import button, note
from .live_protocol import LiveError, changes
from .live_review import conflict_rows, reapply_conflict
from .model import clone


class GeometryView(QGraphicsView):
    def __init__(self, title, color):
        super().__init__()
        self.color = QColor(color)
        self.scene_model = QGraphicsScene(self)
        self.setScene(self.scene_model)
        self.setAccessibleName(title + ' geometry; mouse wheel zooms and dragging pans')
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setMinimumSize(170, 190)
        self.bounds = QRectF(-1, -1, 2, 2)

    def show_shapes(self, shapes, bounds):
        self.scene_model.clear()
        for shape in shapes:
            path = QPainterPath()
            points = shape['points']
            if shape['kind'] == 'rect':
                path.addRect(QRectF(points[0][0], points[0][1], points[1][0] - points[0][0], points[1][1] - points[0][1]).normalized())
            else:
                for loop in [points, *shape.get('holes', [])]:
                    if not loop:
                        continue
                    path.moveTo(*loop[0])
                    for p in loop[1:]:
                        path.lineTo(*p)
                    if shape['kind'] != 'path':
                        path.closeSubpath()
            path.setFillRule(Qt.OddEvenFill)
            pen = QPen(self.color)
            if shape['kind'] == 'path':
                pen.setWidthF(shape['width'])
                pen.setCapStyle(Qt.SquareCap)
                pen.setJoinStyle(Qt.MiterJoin)
                self.scene_model.addPath(path, pen)
            else:
                pen.setCosmetic(True)
                pen.setWidth(2)
                fill = QColor(self.color)
                fill.setAlpha(70)
                self.scene_model.addPath(path, pen, fill)
        self.bounds = bounds
        self.scene_model.setSceneRect(bounds)
        self.fitInView(bounds, Qt.KeepAspectRatio)

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        if 1e-8 < self.transform().m11() * factor < 1e6:
            self.scale(factor, factor)
        event.accept()


def description(value):
    if value is None:
        return 'Not present'
    if isinstance(value, list):
        return str(len(value)) + ' items'
    if 'points' in value:
        points = value['points']
        return (value.get('kind', 'Shape').title() + ' · ' + value.get('layer', '') +
                '\nOrigin ' + str(min(p[0] for p in points)) + ', ' + str(min(p[1] for p in points)) + ' nm' +
                ('\nNet ' + value['net'] if value.get('net') else ''))
    return ' · '.join(str(value[k]) for k in ('name', 'cell', 'layer', 'net') if k in value) or 'Structured layout object'


class ConflictReview(QDialog):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        self.client = studio.live_client
        self.retained = self.client.conflict
        self.setWindowTitle('Review conflicting edit')
        self.resize(1050, 730)
        self.setMinimumSize(660, 520)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.addWidget(note('Your edit is saved. Compare it with the shared layout before choosing what to keep.'))
        self.status = note('')
        root.addWidget(self.status)
        controls = QHBoxLayout()
        controls.addWidget(note('Cell'))
        self.cells = QComboBox()
        self.cells.setAccessibleName('Cell to compare')
        controls.addWidget(self.cells, 1)
        button('Refresh comparison', self.refresh_comparison, controls)
        button('Fit views', self.fit_views, controls)
        root.addLayout(controls)
        geometry = QHBoxLayout()
        self.views = []
        for title, color in [('Before your edit', '#8493a5'), ('Shared now', '#427ce8'), ('Your retained edit', '#d58b2b')]:
            panel = QWidget()
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(0, 0, 0, 0)
            label = note(title)
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
            view = GeometryView(title, color)
            self.views.append(view)
            layout.addWidget(view)
            geometry.addWidget(panel, 1)
        root.addLayout(geometry, 1)
        self.geometry_note = note('')
        root.addWidget(self.geometry_note)
        self.details = QTreeWidget()
        self.details.setHeaderLabels(['Object', 'Before', 'Shared now', 'Your edit'])
        self.details.setRootIsDecorated(False)
        self.details.setAccessibleName('Changed object comparison')
        self.details.setMinimumHeight(100)
        self.details.setMaximumHeight(190)
        for i in range(4):
            self.details.setColumnWidth(i, 215)
        root.addWidget(self.details)
        self.explanation = note('')
        root.addWidget(self.explanation)
        actions = QHBoxLayout()
        self.reapply_button = button('Reapply to shared layout', self.reapply, actions, True)
        button('Save my version…', self.save_copy, actions)
        button('Use shared version…', self.use_shared, actions)
        button('Decide later', self.close, actions)
        root.addLayout(actions)
        self.cells.currentIndexChanged.connect(self.draw_comparison)
        self.client.status_changed.connect(self.session_changed)
        self.refresh_comparison()

    def refresh_comparison(self):
        try:
            if self.studio.live_client is not self.client or self.client.conflict is not self.retained:
                raise LiveError('This conflict has changed or the workspace was closed. Open a new review from the dashboard.')
            self.revision = self.client.revision
            self.current = clone(self.client.project)
            self.rows = conflict_rows(self.retained, self.current)
            selected = self.cells.currentData()
            self.cells.blockSignals(True)
            self.cells.clear()
            by_id = {c['id']: c['name'] for c in self.current['cells']}
            for cid in dict.fromkeys(r['cell'] for r in self.rows):
                self.cells.addItem(by_id.get(cid, 'Cell'), cid)
            index = self.cells.findData(selected or self.studio.cid)
            self.cells.setCurrentIndex(max(0, index))
            self.cells.blockSignals(False)
            self.draw_comparison()
            try:
                proposed = reapply_conflict(self.retained, self.current)
                self.can_reapply = bool(changes(self.current, proposed))
                self.explanation.setText('Reapply keeps other editors’ changes and applies supported moves to the current geometry. The server checks the complete transaction again. Run physical checks after combining edits.' if self.can_reapply
                                         else 'Your changes are already in the shared layout. Choose Use shared version to finish.')
            except LiveError as exc:
                self.can_reapply = False
                self.explanation.setText(str(exc))
            self.session_changed()
        except Exception as exc:
            self.reapply_button.setEnabled(False)
            self.status.setText(str(exc))

    def draw_comparison(self):
        rows = [r for r in getattr(self, 'rows', []) if r['cell'] == self.cells.currentData()]
        self.details.clear()
        groups = [[], [], []]
        for row in rows:
            self.details.addTopLevelItem(QTreeWidgetItem([
                row['field'].replace('layout_', '').replace('_', ' ').title(),
                description(row['before']), description(row['shared']), description(row['after'])]))
            if row['field'] == 'shapes':
                for i, key in enumerate(('before', 'shared', 'after')):
                    if row[key] is not None:
                        groups[i].append(row[key])
        count = sum(len(s['points']) + sum(len(h) for h in s.get('holes', [])) for group in groups for s in group)
        if count > 60000:
            groups = [[], [], []]
            self.geometry_note.setText('This edit exceeds the comparison drawing budget. Save your version to inspect the complete layout.')
        elif any(groups):
            self.geometry_note.setText('Only affected shapes are shown, on the same scale. Wheel to zoom; drag to pan. Structured changes are listed below.')
        else:
            self.geometry_note.setText('This edit changes structured layout objects. Review the details below or save a copy to inspect the complete layout.')
        bounds = None
        for group in groups:
            for shape in group:
                xs, ys = zip(*shape['points'])
                pad = shape.get('width', 0) / 2
                b = QRectF(min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad)
                bounds = b if bounds is None else bounds.united(b)
        bounds = bounds or QRectF(-100, -100, 200, 200)
        margin = max(bounds.width(), bounds.height(), 100) * .12
        bounds = bounds.adjusted(-margin, -margin, margin, margin)
        for view, group in zip(self.views, groups):
            view.show_shapes(group, bounds)

    def fit_views(self):
        for view in self.views:
            view.fitInView(view.bounds, Qt.KeepAspectRatio)

    def session_changed(self, *_):
        valid = self.studio.live_client is self.client and self.client.conflict is self.retained
        fresh = getattr(self, 'revision', None) == self.client.revision
        ready = valid and fresh and self.client.connected and not self.client.pending and self.client.info['role'] != 'view'
        self.reapply_button.setEnabled(ready and getattr(self, 'can_reapply', False))
        self.status.setText('Comparing shared revision ' + str(getattr(self, 'revision', '')) if ready
                            else 'The shared layout changed or is syncing. Refresh the comparison when connected.' if valid
                            else 'This review is no longer active. Return to the collaboration dashboard.')

    def reapply(self):
        try:
            if self.studio.live_client is not self.client or self.client.conflict is not self.retained:
                raise LiveError('Open the current conflict from the dashboard.')
            self.client.reapply(self.revision)
            self.accept()
        except Exception as exc:
            self.status.setText(str(exc))
            self.reapply_button.setEnabled(False)

    def save_copy(self):
        if self.studio.live_client is self.client and self.client.conflict is self.retained:
            self.studio.guard(self.studio.live_save_conflict)
            if not self.client.conflict:
                self.accept()

    def use_shared(self):
        if self.studio.live_client is self.client and self.client.conflict is self.retained:
            self.studio.guard(self.studio.live_confirm_discard)
            if not self.client.conflict:
                self.accept()
