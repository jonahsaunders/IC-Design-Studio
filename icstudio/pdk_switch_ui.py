"""Search installed revisions and review a technology change before applying it."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .lifecycle import duplicate_project
from .model import clone, digest, example
from .pdk_switch import mapping_groups, needs_copy, same_family, switch_preview, technology_label
from .project_hub_ui import HubWorker, label


class PDKSwitchDialog(QDialog):
    def __init__(self, studio, preferred=None, revisions_only=False):
        super().__init__(studio)
        self.studio = studio
        self.project_id = studio.project['id']
        self.revisions_only = revisions_only
        self.setWindowTitle('Switch Project PDK')
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(740, 640)
        self.worker = None
        self.target = None
        self.plan = None
        self.models = {}
        self.setup = None

        root = QVBoxLayout(self)
        self.current = label('Active technology · ' + technology_label(studio.project['pdk']))
        root.addWidget(self.current)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search processes or revisions…')
        self.search.setAccessibleName('Search installed PDKs')
        self.search.setClearButtonEnabled(True)
        row.addWidget(self.search, 1)
        setup = QPushButton('Add PDK…')
        setup.clicked.connect(self.open_setup)
        row.addWidget(setup)
        root.addLayout(row)
        self.choices = QListWidget()
        self.choices.setAccessibleName('Target PDK revision')
        self.choices.setMaximumHeight(150)
        root.addWidget(self.choices)
        self.mapping = QScrollArea()
        self.mapping.setWidgetResizable(True)
        self.mapping.setMinimumHeight(100)
        self.mapping.setMaximumHeight(240)
        self.mapping.setAccessibleName('Map process devices')
        root.addWidget(self.mapping)
        self.mapping.hide()
        self.defaults = QCheckBox('Use target width and length defaults for mapped MOS devices')
        self.defaults.toggled.connect(self.mapping_changed)
        root.addWidget(self.defaults)
        self.defaults.hide()
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setAccessibleName('PDK change preview')
        root.addWidget(self.preview, 1)
        self.status = label('')
        self.status.setAccessibleName('PDK switch status')
        root.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.review = buttons.addButton('Review Changes', QDialogButtonBox.ActionRole)
        self.apply_button = buttons.addButton('Switch PDK', QDialogButtonBox.AcceptRole)
        self.apply_button.setProperty('role', 'primary')
        self.apply_button.setEnabled(False)
        self.review.clicked.connect(self.review_changes)
        self.apply_button.clicked.connect(self.apply_change)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        for button in buttons.buttons():
            button.setAutoDefault(False)
        self.choices.currentItemChanged.connect(self.selection_changed)
        self.choices.itemActivated.connect(self.review_changes)
        self.search.textChanged.connect(self.filter_choices)
        self.search.returnPressed.connect(self.review_changes)
        self.load_choices(preferred)
        self.search.setFocus()

    def selected(self):
        item = self.choices.currentItem()
        return item.data(Qt.UserRole) if item else None

    def load_choices(self, preferred=None):
        current = self.studio.project['pdk']
        lock = current.get('package_lock', {})
        active_key = lock.get('id', '') + '@' + lock.get('revision', '')
        previous = self.selected()
        preferred = preferred or (previous and previous['key'])
        self.choices.blockSignals(True)
        self.choices.clear()
        rows = []
        if not self.revisions_only and current != example('empty')['pdk']:
            rows.append({'key': '', 'name': 'Generic teaching process'})
        for entry in self.studio.pdk_registry.entries():
            if entry.get('error') or (self.revisions_only and entry['id'] != lock.get('id')):
                continue
            key = entry['id'] + '@' + entry['revision']
            if key != active_key:
                rows.append({'key': key, 'name': entry['technology']['name']})
        for row in sorted(rows, key=lambda row: (row['name'].casefold(), row['key'])):
            item = QListWidgetItem(' · '.join(part for part in (row['name'], row['key']) if part))
            item.setData(Qt.UserRole, row)
            self.choices.addItem(item)
            if row['key'] == preferred:
                self.choices.setCurrentItem(item)
        self.choices.blockSignals(False)
        self.filter_choices()
        self.selection_changed()

    def filter_choices(self):
        query = self.search.text().casefold().split()
        first = None
        for index in range(self.choices.count()):
            item = self.choices.item(index)
            item.setHidden(not all(word in item.text().casefold() for word in query))
            if first is None and not item.isHidden():
                first = item
        current = self.choices.currentItem()
        if current is None or current.isHidden():
            self.choices.setCurrentItem(first)
        self.update_review()
        if not self.worker and not self.selected():
            self.status.setText('No matching alternate PDKs. Clear the search or add a PDK.')

    def open_setup(self):
        setup = self.studio.pdk_manager()
        if setup and setup is not self.setup:
            self.setup = setup
            setup.finished.connect(self.load_choices_after_setup)

    def load_choices_after_setup(self, _result):
        self.load_choices()
        self.activateWindow()
        self.search.setFocus()

    def selection_changed(self, *_):
        self.target = None
        self.models = {}
        self.mapping.hide()
        self.defaults.hide()
        self.defaults.setChecked(False)
        self.invalidate()
        if not self.worker:
            self.status.setText('Review the selected PDK to see model and layout changes.' if self.selected()
                                else 'No matching alternate PDKs. Clear the search or add a PDK.')
        self.update_review()

    def invalidate(self, *_):
        self.plan = None
        self.preview.clear()
        self.apply_button.setEnabled(False)

    def update_review(self):
        self.review.setEnabled(self.worker is None and self.selected() is not None)

    def prepare_source(self):
        s = self.studio
        if s.project['id'] != self.project_id:
            raise ValueError('The open project changed. Reopen Switch Project PDK for this design.')
        if s.process or s.run_manager.busy:
            raise ValueError('Wait for active design jobs before switching PDK.')
        if not s.flush_inspector() or not s.flush_analysis():
            raise ValueError('Resolve pending schematic or analysis edits, then review again.')
        digital = getattr(s, '_digital_window', None)
        if digital and digital.dirty and not digital.attempt(digital.apply):
            raise ValueError('Resolve pending RTL edits, then review again.')
        return s.project

    def copy_required(self, project, technology):
        s = self.studio
        hub = getattr(s, '_student_hub', None)
        lesson = ((hub and any(record['project_id'] == project['id']
                               for record in hub.portfolio.state['workspaces'].values()))
                  or (s.path and Path(s.path).is_relative_to(s.data_dir / 'student-hub' / 'projects')))
        return needs_copy(project, technology, shared=bool(s.live_client or s.layout_session),
                          lesson=bool(lesson))

    def review_changes(self, *_):
        if self.worker or self.selected() is None:
            return
        try:
            project = self.prepare_source()
            if self.target and self.target[0] == self.selected()['key']:
                self.build_preview(project)
                return
            key = self.selected()['key']
            if not key:
                self.install_target(project, key, example('empty')['pdk'])
                return
            registry = self.studio.pdk_registry
            worker = self.worker = HubWorker(lambda: registry.technology(key), QApplication.instance())
            worker.key = key
            worker.finished.connect(self.verified)
            worker.finished.connect(worker.deleteLater)
            self.invalidate()
            self.status.setText('Verifying the selected revision’s files…')
            self.update_review()
            worker.start()
        except (ValueError, OSError, KeyError, ArithmeticError, SyntaxError) as exc:
            self.status.setText(str(exc))

    def verified(self):
        worker, self.worker = self.worker, None
        self.update_review()
        if self.selected() is None or self.selected()['key'] != worker.key:
            self.selection_changed()
        elif worker.error:
            self.status.setText(worker.error)
        else:
            try:
                self.install_target(self.prepare_source(), worker.key, worker.result)
            except (ValueError, OSError, KeyError, ArithmeticError, SyntaxError) as exc:
                self.status.setText(str(exc))

    def install_target(self, project, key, technology):
        self.target = (key, technology, digest(project))
        host = QWidget()
        form = QFormLayout(host)
        in_family = same_family(project['pdk'], technology)
        has_mos = False
        self.models = {}
        for group, info, choices in mapping_groups(project, technology):
            title = f"{info['label']} ({info['count']})"
            combo = QComboBox()
            combo.setAccessibleName('Target model for ' + title)
            combo.setMinimumContentsLength(14)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.addItem('Choose a model…' if choices else 'No model with matching terminals', None)
            for model, display, spice in choices:
                combo.addItem(f'{display} · {spice}', model)
                combo.setItemData(combo.count() - 1, model, Qt.ToolTipRole)
            if in_family and combo.findData(group[0]) > 0:
                combo.setCurrentIndex(combo.findData(group[0]))
            combo.currentIndexChanged.connect(self.mapping_changed)
            form.addRow(label(title), combo)
            self.models[group] = combo
            has_mos = has_mos or group[1] in ('NMOS', 'PMOS')
        self.mapping.setWidget(host)
        self.mapping.setVisible(bool(self.models))
        self.defaults.setVisible(has_mos and not in_family)
        self.build_preview(project)

    def mapping_changed(self, *_):
        self.invalidate()
        self.status.setText('Review the updated mapping to continue.')

    def build_preview(self, project):
        key, technology, source_hash = self.target
        if digest(project) != source_hash:
            self.install_target(project, key, technology)
            return
        self.invalidate()
        if any(combo.currentData() is None for combo in self.models.values()):
            self.status.setText('Choose a target for every source model. Models need the same device kind and named terminals.')
            return
        candidate, changes, effects = switch_preview(project, technology,
            {group: combo.currentData() for group, combo in self.models.items()}, self.defaults.isChecked())
        copy = self.copy_required(project, technology)
        action = 'Save as a separate project. Open the new file from Projects.' if copy else 'Switch this project. Undo restores the previous revision.'
        lines = [technology_label(project['pdk']) + ' → ' + technology_label(technology),
                 '', action, *effects, '', f'{len(changes)} device changes']
        for change in changes:
            lines.append(f"{change['cell']}/{change['instance']} · {change['from']} → {change['to']}")
            lines.extend('  ' + note for note in change['notes'])
        self.preview.setPlainText('\n'.join(lines))
        self.apply_button.setText('Save Project Copy…' if copy else 'Switch PDK')
        self.apply_button.setEnabled(True)
        self.plan = (source_hash, candidate, copy)
        self.status.setText('Review the effects above, then apply when ready.')

    def apply_change(self):
        if not self.plan:
            return
        try:
            source_hash, candidate, copy = self.plan
            s = self.studio
            path = None
            name = s.project['name'][:100] + ' PDK copy'
            if copy:
                path, _ = QFileDialog.getSaveFileName(self, 'Save Project Copy', name + '.icproj',
                                                       'Studio projects (*.icproj)')
                if not path:
                    return
            project = self.prepare_source()
            if digest(project) != source_hash or copy != self.copy_required(project, candidate['pdk']):
                self.invalidate()
                raise ValueError('The project changed. Review the latest version before applying.')
            if copy:
                result = duplicate_project(candidate, path, name, source=project)
                s.project_index.remember(result, path)
                s.statusBar().showMessage('Saved ' + result['name'] + ' · open it from Projects', 8000)
            else:
                def install(p):
                    p.clear()
                    p.update(clone(candidate))
                s.commit(install, 'Switch project PDK')
                s.sync_technology()
                s.load_analysis()
                s.statusBar().showMessage('Active PDK · ' + technology_label(candidate['pdk']), 8000)
            self.accept()
        except (ValueError, OSError, KeyError, ArithmeticError, SyntaxError) as exc:
            self.status.setText(str(exc))
