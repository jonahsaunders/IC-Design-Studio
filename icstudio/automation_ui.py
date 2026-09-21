"""Native hierarchy navigation and reviewed, single-undo automation batches."""
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .design_automation import envelope, inspect, install_preview, preview


class AutomationDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.project_id = owner.project['id']
        self.root_cell_id = owner.cid
        self.instance_path = []
        self.proposal = None
        self.setWindowTitle('Hierarchy and design automation')
        self.setWindowModality(Qt.WindowModal)
        self.resize(960, 720)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        navigation = QWidget()
        nav = QVBoxLayout(navigation)
        bar = QHBoxLayout()
        self.master = QComboBox()
        for c in owner.project['cells']:
            self.master.addItem(c['name'], c['id'])
        self.master.setCurrentIndex(self.master.findData(owner.cid))
        bar.addWidget(QLabel('Root cell'))
        bar.addWidget(self.master, 1)
        self.back = QPushButton('Parent')
        self.back.setToolTip('Return to the parent occurrence (Alt+Up)')
        bar.addWidget(self.back)
        nav.addLayout(bar)
        self.breadcrumb = QLabel()
        self.breadcrumb.setWordWrap(True)
        nav.addWidget(self.breadcrumb)
        self.instances = QTableWidget(0, 4)
        self.instances.setHorizontalHeaderLabels(['Instance', 'Kind', 'Cell / value', 'Stable ID'])
        self.instances.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.instances.setSelectionMode(QAbstractItemView.SingleSelection)
        self.instances.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.instances.horizontalHeader().setStretchLastSection(True)
        nav.addWidget(self.instances, 1)
        actions = QHBoxLayout()
        for title, callback in [('Enter instance', self.enter), ('Open schematic', lambda: self.open_view(0)),
                                ('Open layout', lambda: self.open_view(1))]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            actions.addWidget(button)
        nav.addLayout(actions)
        views = QHBoxLayout()
        views.addWidget(QLabel('Schematic master'))
        self.views = QComboBox()
        views.addWidget(self.views, 1)
        self.switch = QPushButton('Review cell substitution')
        self.switch.clicked.connect(self.switch_view)
        views.addWidget(self.switch)
        nav.addLayout(views)
        scope = QLabel('Master edits affect every occurrence. Cell substitution keeps the instance identity and requires the same ordered ports and parameter interface.')
        scope.setWordWrap(True)
        nav.addWidget(scope)
        self.tabs.addTab(navigation, 'Hierarchy')
        batch_page = QWidget()
        batch_layout = QVBoxLayout(batch_page)
        note = QLabel('Load a versioned command batch or edit the JSON below. Preview checks the complete design; Apply creates one undo step. The project, revision and content must still match the batch.')
        note.setWordWrap(True)
        batch_layout.addWidget(note)
        buttons = QHBoxLayout()
        for title, callback in [('Load batch…', self.load_batch), ('Use selected device', self.selected_template), ('Preview changes', self.preview_changes)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        batch_layout.addLayout(buttons)
        self.editor = QPlainTextEdit()
        self.editor.setAccessibleName('Automation command batch JSON')
        self.editor.setPlainText(json.dumps(envelope(owner.project, []), indent=2))
        batch_layout.addWidget(self.editor, 2)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setAccessibleName('Automation change preview')
        batch_layout.addWidget(self.report, 1)
        self.tabs.addTab(batch_page, 'Batch editor')
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        self.apply_button = self.buttons.button(QDialogButtonBox.Apply)
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply_changes)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.editor.textChanged.connect(self.invalidate)
        self.master.currentIndexChanged.connect(self.change_root)
        self.back.clicked.connect(self.parent_cell)
        self.instances.itemSelectionChanged.connect(self.update_views)
        self.instances.itemActivated.connect(lambda *_: self.enter())
        QShortcut(QKeySequence('Alt+Up'), self, activated=self.parent_cell)
        self.refresh_navigation()

    def ensure_project(self):
        if self.owner.project['id'] != self.project_id:
            raise ValueError('The open project changed. Reopen design automation.')

    def show_error(self, exc):
        self.error.setText(str(exc))

    def invalidate(self):
        self.proposal = None
        self.apply_button.setEnabled(False)
        self.report.clear()

    def refresh_navigation(self):
        try:
            self.ensure_project()
            self.info = inspect(self.owner.project, self.instance_path, self.root_cell_id)
            self.breadcrumb.setText(' / '.join(r.get('instance_name', r['name']) for r in self.info['breadcrumbs']))
            cells = {c['id']: c['name'] for c in self.info['cells']}
            self.instances.setRowCount(len(self.info['devices']))
            for row, device in enumerate(self.info['devices']):
                values = [device['name'], device['kind'], cells.get(device.get('cell'), device.get('value', '')), device['id']]
                for column, value in enumerate(values):
                    self.instances.setItem(row, column, QTableWidgetItem(str(value)))
            self.back.setEnabled(bool(self.instance_path))
            self.error.clear()
            self.update_views()
        except (ValueError, KeyError) as exc:
            self.show_error(exc)

    def change_root(self, *_):
        self.root_cell_id = self.master.currentData()
        self.instance_path = []
        self.refresh_navigation()

    def parent_cell(self):
        if self.instance_path:
            self.instance_path.pop()
            self.refresh_navigation()

    def selected_device(self):
        row = self.instances.currentRow()
        if not 0 <= row < len(self.info['devices']):
            raise ValueError('Select a device in the hierarchy table.')
        return self.info['devices'][row]

    def enter(self):
        try:
            device = self.selected_device()
            if device['kind'] != 'X':
                raise ValueError('Select a hierarchical instance to enter its cell.')
            self.instance_path.append(device['id'])
            self.refresh_navigation()
        except ValueError as exc:
            self.show_error(exc)

    def open_view(self, mode):
        try:
            self.ensure_project()
            if not self.owner.flush_inspector():
                return
            self.owner.cid = self.info['cell_id']
            self.owner.selection = []
            self.owner.mode_combo.setCurrentIndex(mode)
            self.owner.refresh(True)
        except ValueError as exc:
            self.show_error(exc)

    def update_views(self):
        self.views.clear()
        try:
            device = self.selected_device()
            cells = {c['id']: c for c in self.info['cells']}
            for cid in device.get('compatible_views', []):
                self.views.addItem(cells[cid]['name'], cid)
            self.views.setCurrentIndex(self.views.findData(device.get('cell')))
        except ValueError:
            pass
        self.switch.setEnabled(self.views.count() > 1)

    def set_batch(self, commands, label):
        self.editor.setPlainText(json.dumps(envelope(self.owner.project, commands, label), indent=2))
        self.tabs.setCurrentIndex(1)

    def switch_view(self):
        try:
            self.ensure_project()
            device = self.selected_device()
            if not self.views.currentData() or self.views.currentData() == device.get('cell'):
                raise ValueError('Choose a different compatible schematic master.')
            self.set_batch([{'type': 'switch_cell_view', 'cell_id': self.info['cell_id'],
                            'device_id': device['id'], 'view_cell_id': self.views.currentData()}],
                           'Substitute cell view for ' + device['name'])
            self.preview_changes()
        except ValueError as exc:
            self.show_error(exc)

    def selected_template(self):
        try:
            self.ensure_project()
            device = self.selected_device()
            self.set_batch([{'type': 'move_device', 'cell_id': self.info['cell_id'],
                            'device_id': device['id'], 'x': device['x'], 'y': device['y']}],
                           'Move ' + device['name'])
        except ValueError as exc:
            self.show_error(exc)

    def load_batch(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Load command batch', '', 'JSON (*.json)')
        if not path:
            return
        try:
            file = Path(path)
            if file.stat().st_size > 10 * 1024 * 1024:
                raise ValueError('Automation batch exceeds 10 MiB.')
            request = json.loads(file.read_text(encoding='utf-8'))
            self.editor.setPlainText(json.dumps(request, indent=2))
        except (OSError, ValueError) as exc:
            self.show_error(exc)

    def preview_changes(self):
        self.invalidate()
        try:
            self.ensure_project()
            if not self.owner.flush_inspector():
                return
            request = json.loads(self.editor.toPlainText())
            self.proposal = preview(self.owner.project, request)
            report = self.proposal['report']
            self.report.setPlainText('Validated ' + str(report['commands']) + ' commands. One undo step.\n'
                + 'Revision ' + str(report['base_revision']) + ' → ' + str(report['revision']) + '\n'
                + str(len(report['change']['cells'])) + ' cells and ' + str(len(report['change']['objects']))
                + ' objects changed. Existing analysis results become stale.\n\n'
                + json.dumps(request['commands'], indent=2))
            self.apply_button.setEnabled(True)
            self.error.clear()
        except (ValueError, KeyError, TypeError) as exc:
            self.show_error(exc)

    def apply_changes(self):
        if not self.proposal:
            return
        try:
            self.ensure_project()
            if not self.owner.idle_edit():
                return
            proposal = self.proposal
            if self.owner.capture_commit(lambda p: install_preview(p, proposal), proposal['report']['change']['label']):
                self.owner.statusBar().showMessage('Automation batch applied. Undo restores the complete previous design.', 8000)
                self.accept()
        except (ValueError, KeyError, TypeError) as exc:
            self.apply_button.setEnabled(False)
            self.show_error(exc)


def install(studio):
    def show():
        if not studio.flush_inspector():
            return
        studio._automation_dialog = AutomationDialog(studio)
        studio._automation_dialog.show()
    studio.action(studio.task_menus['Tools'], 'Hierarchy and design automation…', show, 'Ctrl+Shift+H')
