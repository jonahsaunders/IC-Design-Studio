"""Nonmodal 3D snapshot of the active layout; never edits project geometry."""
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
                               QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QSplitter, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from .layout_3d import build_mesh
from .layout_3d_view import OpenGLView, SoftwareView, opengl_available


class Layout3DDialog(QDialog):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio, self.snapshot, self.mesh = studio, None, None
        self.setWindowTitle('3D layout viewer')
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(1240, 740)
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel('Region'))
        self.region = QComboBox()
        self.region.addItems(['Whole active cell', 'Current 2D viewport'])
        bar.addWidget(self.region)
        self.refresh_button = QPushButton('Refresh from layout')
        self.refresh_button.clicked.connect(lambda: self.refresh_mesh())
        bar.addWidget(self.refresh_button)
        bar.addStretch()
        for name in ('Isometric', 'Top', 'Front', 'Fit'):
            button = QPushButton(name)
            button.clicked.connect(lambda checked=False, n=name: self.view.fit() if n == 'Fit' else self.view.preset(n))
            bar.addWidget(button)
        self.save_button = QPushButton('Save PNG…')
        self.save_button.clicked.connect(self.save_image)
        bar.addWidget(self.save_button)
        root.addLayout(bar)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.split = QSplitter()
        self.view_host = QWidget()
        self.view_layout = QVBoxLayout(self.view_host)
        self.view_layout.setContentsMargins(0, 0, 0, 0)
        self.view = OpenGLView() if opengl_available() else SoftwareView()
        self.view_layout.addWidget(self.view)
        if isinstance(self.view, OpenGLView):
            self.view.failed.connect(self.use_software)
        self.split.addWidget(self.view_host)
        side = QWidget()
        side.setMinimumWidth(390)
        controls = QVBoxLayout(side)
        controls.setContentsMargins(12, 0, 0, 0)
        controls.addWidget(QLabel('LAYER STACK'))
        self.stack_note = QLabel()
        self.stack_note.setWordWrap(True)
        controls.addWidget(self.stack_note)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Layer', 'Base µm', 'Thick. µm', 'Basis'])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        for column, width in enumerate((100, 88, 94, 92)):
            self.table.setColumnWidth(column, width)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setMinimumWidth(376)
        self.table.itemChanged.connect(self.visibility_changed)
        controls.addWidget(self.table, 1)
        for label, attr, low, high, value in [('Vertical scale', 'z_scale', .1, 100., 1.),
                                             ('Explode gap (µm)', 'explode', 0., 1000., 0.)]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            spin = QDoubleSpinBox()
            spin.setRange(low, high)
            spin.setValue(value)
            spin.setDecimals(2)
            spin.setSingleStep(.5)
            spin.setAccessibleName(label)
            spin.valueChanged.connect(lambda val, a=attr: self.set_display(a, val))
            setattr(self, attr + '_spin', spin)
            row.addWidget(spin)
            controls.addLayout(row)
        reset = QPushButton('Reset heights to PDK / defaults')
        reset.clicked.connect(self.reset_stack)
        controls.addWidget(reset)
        self.backend = QLabel()
        self.backend.setWordWrap(True)
        controls.addWidget(self.backend)
        note = QLabel('Heights and visibility are local to this viewer. Refresh updates geometry; closing discards display overrides.')
        note.setWordWrap(True)
        controls.addWidget(note)
        self.split.addWidget(side)
        self.split.setStretchFactor(0, 1)
        self.split.setSizes([800, 400])
        root.addWidget(self.split, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.check_stale)
        self.timer.start()
        self.backend_note()
        self.region.currentIndexChanged.connect(lambda: self.refresh_mesh())
        self.refresh_mesh()
        QTimer.singleShot(250, self.check_context)

    def backend_note(self):
        self.backend.setText('OpenGL · depth-buffered solids' if isinstance(self.view, OpenGLView) else
                             'Software preview · intersecting solids may show face-order artifacts.')

    def check_context(self):
        if isinstance(self.view, OpenGLView) and self.isVisible() and not self.view.isValid():
            self.use_software('No usable OpenGL widget context.')

    def use_software(self, reason):
        if isinstance(self.view, SoftwareView):
            return
        old = self.view
        self.view = SoftwareView()
        self.view_layout.replaceWidget(old, self.view)
        self.view.z_scale, self.view.explode = old.z_scale, old.explode
        self.view.set_mesh(self.mesh)
        self.view.yaw, self.view.pitch = old.yaw, old.pitch
        old.hide()
        old.cleanup()
        old.deleteLater()
        self.backend_note()
        self.backend.setToolTip(reason)

    def current_revision(self):
        p = self.studio.project
        return p['id'], p['revision'], self.studio.cid

    def check_stale(self):
        if self.snapshot and self.snapshot != self.current_revision():
            self.status.setText(f'Snapshot r{self.snapshot[1]}: layout changed. Refresh from layout to view the current active cell.')

    def refresh_mesh(self, preserve=True):
        previous = {layer.name: layer for layer in self.mesh.layers} if self.mesh and preserve else {}
        # A different project or PDK must not inherit another process's heights.
        pdk = self.studio.project['pdk']
        stack_key = (self.studio.project['id'], repr(pdk.get('stack_3d')), repr(pdk['layers']))
        if getattr(self, 'stack_key', None) != stack_key:
            previous = {}
        box = None
        if self.region.currentIndex() == 1:
            canvas = self.studio.layout
            a, b = canvas.model(QPointF(0, 0)), canvas.model(QPointF(canvas.width(), canvas.height()))
            box = (a.x(), a.y(), b.x(), b.y())
        try:
            mesh = build_mesh(self.studio.project, self.studio.cid, box)
        except (ValueError, RuntimeError) as exc:
            # Clear an old view on failure so it cannot look like the new cell.
            self.mesh, self.snapshot = None, None
            self.view.set_mesh(None)
            self.table.setRowCount(0)
            self.stack_note.clear()
            self.save_button.setEnabled(False)
            self.status.setText(str(exc))
            return False
        for layer in mesh.layers:
            old = previous.get(layer.name)
            if old:
                layer.z_um, layer.thickness_um = old.z_um, old.thickness_um
                layer.visible, layer.illustrative = old.visible, old.illustrative
                layer.custom = old.custom
        self.mesh, self.stack_key = mesh, stack_key
        self.snapshot = self.current_revision()
        self.view.set_mesh(mesh)
        self.populate_layers()
        self.save_button.setEnabled(bool(mesh.triangle_count))
        b = mesh.bounds_um
        self.status.setText(f"{self.studio.cell['name']} · r{self.snapshot[1]} · {mesh.shape_count:,} shapes · "
                            f'{mesh.triangle_count:,} triangles · {b[2]-b[0]:.3f} × {b[3]-b[1]:.3f} µm'
                            + (' · Clipped to the 2D viewport' if mesh.cropped else ''))
        return True

    def populate_layers(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.mesh.layers))
        for i, layer in enumerate(self.mesh.layers):
            item = QTableWidgetItem(layer.name)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            item.setCheckState(Qt.Checked if layer.visible else Qt.Unchecked)
            item.setForeground(QColor(layer.color))
            item.setToolTip(f'{len(layer.triangles):,} triangles')
            self.table.setItem(i, 0, item)
            for column, attr, minimum in [(1, 'z_um', -100000.), (2, 'thickness_um', .001)]:
                spin = QDoubleSpinBox()
                spin.setDecimals(3)
                spin.setRange(minimum, 100000.)
                spin.setSingleStep(.1)
                spin.setValue(getattr(layer, attr))
                spin.setKeyboardTracking(False)
                spin.setAccessibleName(layer.name + (' elevation in micrometres' if column == 1 else ' thickness in micrometres'))
                spin.valueChanged.connect(lambda value, row=i, name=attr: self.edit_height(row, name, value))
                self.table.setCellWidget(i, column, spin)
            basis = QTableWidgetItem('Custom' if layer.custom else 'Illustrative' if layer.illustrative else 'PDK')
            basis.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(i, 3, basis)
        self.table.blockSignals(False)
        self.stack_note.setText('Custom display heights. These changes do not alter the PDK or project.' if any(layer.custom for layer in self.mesh.layers) else
                                'Illustrative heights: layer order is not a fabrication stack.' if any(layer.illustrative for layer in self.mesh.layers) else
                                'PDK-supplied heights. Source: ' + (self.mesh.source or 'unspecified'))

    def visibility_changed(self, item):
        if self.mesh and item.column() == 0:
            self.mesh.layers[item.row()].visible = item.checkState() == Qt.Checked
            self.view.update()

    def edit_height(self, row, name, value):
        if self.mesh:
            setattr(self.mesh.layers[row], name, value)
            self.mesh.layers[row].illustrative = True
            self.mesh.layers[row].custom = True
            self.table.item(row, 3).setText('Custom')
            self.stack_note.setText('Custom display heights. These changes do not alter the PDK or project.')
            self.view.fit()

    def set_display(self, attr, value):
        setattr(self.view, attr, value)
        self.view.fit()

    def reset_stack(self):
        self.z_scale_spin.setValue(1.)
        self.explode_spin.setValue(0.)
        self.refresh_mesh(preserve=False)

    def save_image(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save 3D layout image', 'layout-3d.png', 'PNG image (*.png)')
        if not path:
            return
        if not path.lower().endswith('.png'):
            path += '.png'
        # Include stack provenance, region and snapshot revision in the image.
        if not self.grab().save(path, 'PNG'):
            self.status.setText('Could not save the PNG. Choose a writable location.')

    def closeEvent(self, event):
        self.timer.stop()
        if isinstance(self.view, OpenGLView):
            self.view.cleanup()
        if getattr(self.studio, '_layout_3d_dialog', None) is self:
            self.studio._layout_3d_dialog = None
        super().closeEvent(event)


def show(studio):
    dialog = getattr(studio, '_layout_3d_dialog', None)
    if dialog is None:
        dialog = Layout3DDialog(studio)
        studio._layout_3d_dialog = dialog
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog
