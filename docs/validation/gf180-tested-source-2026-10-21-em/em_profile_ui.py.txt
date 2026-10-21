"""Edit reusable physical EM data for the project's selected technology."""
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QFileDialog, QTabWidget,
    QWidget, QComboBox)

from . import em_technology as profiles
from .model import atomic_write
from .layout_vias import technology


class EMProfileDialog(QDialog):
    columns = ('name', 'kind', 'z_um', 'thickness_um', 'conductivity_s_m', 'epsilon_r', 'loss_tangent')

    def __init__(self, owner, parent=None):
        super().__init__(parent or owner); self.owner = owner; self.project_id = owner.project['id']
        self.identity = profiles.technology_identity(technology(owner.project))
        self.setWindowTitle('Physical EM profile for this PDK')
        screen = owner.screen().availableGeometry()
        self.resize(min(1000, screen.width()-40), min(700, screen.height()-60))
        layout = QVBoxLayout(self)
        title = QLabel(f"PDK: {self.identity['id']} · revision {self.identity['revision']}")
        title.setWordWrap(True); layout.addWidget(title)
        note = QLabel('Enter physical data from this process. Map layout names to physical layers below. '
                      'Required material values must be supplied; no values are copied from another PDK.')
        note.setWordWrap(True); layout.addWidget(note)
        layout.addWidget(QLabel('Source / process documentation and corner'))
        self.source = QLineEdit(); self.source.setAccessibleName('Physical data source'); layout.addWidget(self.source)
        tabs = QTabWidget(); layout.addWidget(tabs, 1)
        physical = QWidget(); box = QVBoxLayout(physical)
        self.layers = QTableWidget(0, len(self.columns)); self.layers.setAccessibleName('Physical stackup layers')
        self.layers.setHorizontalHeaderLabels(['Physical name', 'Kind', 'Bottom µm', 'Thickness µm', 'σ (S/m)', 'εr', 'Loss tan.'])
        self.layers.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.layers.setSelectionBehavior(QTableWidget.SelectRows); box.addWidget(self.layers)
        row = QHBoxLayout(); box.addLayout(row)
        for label, action in [('Add metal', lambda: self.add_layer({'kind': 'conductor'})),
                              ('Add via', lambda: self.add_layer({'kind': 'via'})),
                              ('Add dielectric / substrate', lambda: self.add_layer({'kind': 'dielectric'})),
                              ('Remove selected', self.remove_layers)]:
            button = QPushButton(label); button.clicked.connect(action); row.addWidget(button)
        tabs.addTab(physical, 'Physical layers')
        self.mapping = QTableWidget(0, 4); self.mapping.setAccessibleName('PDK to physical layer mapping')
        self.mapping.setHorizontalHeaderLabels(['Layout layer', 'GDS / datatype', 'Physical name', 'Exclude marker: reason'])
        self.mapping.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.mapping.horizontalHeader().setStretchLastSection(True); tabs.addTab(self.mapping, 'Layer mapping')
        hint = QLabel('Conductor/via layers need conductivity; dielectric/substrate layers need εr. '
                      'All layers need bottom elevation and positive thickness. Exclude only non-electrical markers, '
                      'with a reason; surrounding metal and vias must be modeled. Optional loss tangent and dielectric '
                      'conductivity default to zero; conductor εr defaults to 1.')
        hint.setWordWrap(True); layout.addWidget(hint)
        self.error = QLabel(); self.error.setWordWrap(True); layout.addWidget(self.error)
        buttons = QHBoxLayout(); layout.addLayout(buttons)
        for label, action in [('New for this PDK', self.new), ('Load profile…', self.load),
                              ('Save profile…', self.save), ('Apply to project', self.apply), ('Cancel', self.reject)]:
            button = QPushButton(label); button.clicked.connect(action); buttons.addWidget(button)
        self.populate(technology(owner.project).get('em_stackup') or profiles.template(technology(owner.project)))

    def current_technology(self):
        tech = technology(self.owner.project)
        if self.owner.project['id'] != self.project_id or profiles.technology_identity(tech) != self.identity:
            raise ValueError('The project or PDK revision changed. Reopen the EM profile editor.')
        return tech

    def new(self):
        try: self.populate(profiles.template(self.current_technology())); self.error.clear()
        except ValueError as exc: self.error.setText(str(exc))

    def add_layer(self, layer):
        row = self.layers.rowCount(); self.layers.insertRow(row)
        for col, key in enumerate(self.columns):
            if key == 'kind':
                combo = QComboBox(); combo.addItems(profiles.KINDS); combo.setCurrentText(layer.get(key, 'conductor'))
                self.layers.setCellWidget(row, col, combo)
            else:
                value = layer.get(key)
                text = '' if value is None else str(value)
                self.layers.setItem(row, col, QTableWidgetItem(text))

    def remove_layers(self):
        for row in sorted({index.row() for index in self.layers.selectedIndexes()}, reverse=True):
            self.layers.removeRow(row)

    def populate(self, stack):
        self.bound_identity = stack.get('technology'); self.source.setText(stack.get('source', ''))
        self.layers.setRowCount(0)
        for layer in stack['layers']: self.add_layer(layer)
        tech = self.current_technology(); mapping = profiles.mapping_for(tech, stack)
        exclusions = stack.get('excluded_layers', {}); self.mapping.setRowCount(len(tech['layers']))
        for row, layer in enumerate(tech['layers']):
            values = [layer['name'], f"{layer['gds']} / {layer['datatype']}",
                      mapping.get(layer['name'], ''), exclusions.get(layer['name'], '')]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col < 2: item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.mapping.setItem(row, col, item)

    def profile(self):
        tech = self.current_technology(); layers = []
        for row in range(self.layers.rowCount()):
            layer = {}
            for col, key in enumerate(self.columns):
                value = self.layers.cellWidget(row, col).currentText() if key == 'kind' else self.layers.item(row, col).text().strip()
                if key in ('name', 'kind'): layer[key] = value
                elif value:
                    try: layer[key] = float(value)
                    except ValueError as exc: raise ValueError(f'Physical layer row {row+1}: {key} needs a number.') from exc
            layers.append(layer)
        mapping = {}; excluded = {}
        for row in range(self.mapping.rowCount()):
            name, _, physical, reason = [self.mapping.item(row, col).text().strip() for col in range(4)]
            if physical: mapping[name] = physical
            if reason: excluded[name] = reason
        stack = dict(schema=2, source=self.source.text().strip(), layers=layers,
                     layout_map=mapping, excluded_layers=excluded)
        if self.bound_identity is not None: stack['technology'] = self.bound_identity
        stack = profiles.bind_stackup(tech, stack)
        # Check explicit mappings and exclusions even when a layer is unused in this cell.
        issues = profiles.readiness(tech, stack, set(mapping) | set(excluded))
        if issues: raise ValueError('\n'.join(issues))
        return stack

    def load(self):
        file, _ = QFileDialog.getOpenFileName(self, 'Load physical EM profile', '', 'JSON (*.json)')
        if not file: return
        try:
            from .inductor_em import _read
            stack = profiles.bind_stackup(self.current_technology(), json.loads(_read(file)))
            self.populate(stack); self.error.clear()
        except (ValueError, OSError, KeyError, TypeError) as exc: self.error.setText(str(exc))

    def save(self):
        try:
            stack = self.profile()
            file, _ = QFileDialog.getSaveFileName(self, 'Save reusable PDK EM profile', 'pdk-em-profile.json', 'JSON (*.json)')
            if file:
                atomic_write(Path(file), json.dumps(stack, indent=2, allow_nan=False).encode('utf-8'))
                self.error.setText('Saved ' + Path(file).name)
        except (ValueError, OSError, KeyError) as exc: self.error.setText(str(exc))

    def apply(self):
        try:
            stack = self.profile()
            if not self.owner.idle_edit(): return
            self.owner.commit(lambda p: p['pdk'].update(em_stackup=stack), 'Set PDK physical EM profile')
            self.accept()
        except (ValueError, KeyError) as exc: self.error.setText(str(exc))
