"""Project version commands and their document-modal dialogs."""
from datetime import datetime

from PySide6.QtCore import Qt, QDateTime, QLocale
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPlainTextEdit, QSplitter,
                               QVBoxLayout, QWidget)

from .model import History
from .project_versions import ProjectVersions, compare, restore_contents, same_design
from .ui_style import palette
from .workspace import label


def working_design_ready(studio):
    window = getattr(studio, '_digital_window', None)
    if window and window.dirty and not window.attempt(window.apply):
        return False
    experiment = getattr(studio, '_mixed_signal_dialog', None)
    if experiment and experiment.project_id == studio.project['id'] and not experiment.resolve_draft():
        return False
    return studio.flush_inspector() and studio.flush_analysis()


def restore_blocker(studio):
    if studio.live_client or studio.layout_session or not isinstance(studio.history, History):
        return 'Leave the collaboration session to restore a local version.'
    if studio.process or studio.run_manager.busy:
        return 'Stop the active job to restore a version.'
    return ''


def dated_title(version):
    date = datetime.fromisoformat(version.created).astimezone()
    formatted = QLocale().toString(QDateTime(date), QLocale.FormatType.ShortFormat)
    return f'{formatted} · Revision {version.revision}' if version.revision is not None else formatted


class BranchVersions:
    def __init__(self, history, branches):
        self.history = history
        self.branches = branches

    def list(self):
        self.branches.verify()
        return sorted([*self.history.list(), *self.branches.list()],
                      key=lambda row: datetime.fromisoformat(row.created), reverse=True)

    def load(self, version_id):
        return self.branches.load(version_id) if len(version_id) == 40 else self.history.load(version_id)

    def save(self, project, name, note=''):
        return self.branches.save(project, name, note)


def version_store(studio):
    from .project_git import ProjectGit
    project_id = studio.project['id']
    history = ProjectVersions(studio.path, project_id)
    branches = ProjectGit(studio.path, project_id)
    return BranchVersions(history, branches) if branches.path.exists() else history


def configure_dialog(dialog, studio, title):
    dialog.setWindowTitle(title)
    dialog.setWindowModality(Qt.WindowModal)
    colors = palette(studio.dark)
    dialog.setStyleSheet(f'''
        QPlainTextEdit:focus, QPushButton[role="secondary"]:focus {{ border-color: {colors['accent']}; }}
        QPushButton[role="primary"]:focus {{ border-color: {colors['text']}; }}
    ''')


class SaveVersionDialog(QDialog):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        self.version = None
        configure_dialog(self, studio, 'Save Version')
        self.resize(450, 260)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText('e.g. RC baseline')
        self.name.setMaxLength(100)
        self.name.setAccessibleName('Version name')
        form.addRow('&Name', self.name)
        self.note = QPlainTextEdit()
        self.note.setAccessibleName('Version note')
        self.note.setPlaceholderText('What changed or why this version matters')
        form.addRow('N&ote (optional)', self.note)
        layout.addLayout(form)
        self.message = label('', 'error')
        self.message.setTextFormat(Qt.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.save_button = buttons.addButton('Save Version', QDialogButtonBox.AcceptRole)
        self.save_button.setProperty('role', 'primary')
        self.save_button.setDefault(True)
        self.save_button.setEnabled(False)
        self.name.textChanged.connect(lambda text: self.save_button.setEnabled(bool(text.strip())))
        buttons.accepted.connect(self.save_version)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.name.setFocus()

    def save_version(self):
        try:
            if not working_design_ready(self.studio):
                self.message.setText('Resolve the pending project edits, then try saving the version again.')
                return
            if self.studio.path is None and not self.studio.save():
                return
            project = self.studio.project
            store = version_store(self.studio)
            self.version = store.save(project, self.name.text(), self.note.toPlainText())
        except (OSError, ValueError, OverflowError) as exc:
            self.message.setText(str(exc))
            return
        self.studio.statusBar().showMessage(f'Saved version “{self.version.name}”.', 6000)
        self.accept()


def save_version(studio):
    dialog = SaveVersionDialog(studio)
    try:
        dialog.exec()
        return dialog.version
    finally:
        dialog.deleteLater()


class VersionHistoryDialog(QDialog):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        configure_dialog(self, studio, 'Version History')
        self.resize(760, 480)
        layout = QVBoxLayout(self)
        heading = label(studio.project['name'], 'title')
        heading.setTextFormat(Qt.PlainText)
        heading.setWordWrap(True)
        layout.addWidget(heading)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        self.versions = QListWidget()
        self.versions.setAccessibleName('Saved versions')
        self.versions.setMinimumWidth(180)
        splitter.addWidget(self.versions)

        detail = QWidget()
        right = QVBoxLayout(detail)
        right.setContentsMargins(12, 0, 0, 0)
        self.comparison = QComboBox()
        self.comparison.setAccessibleName('Compare with')
        self.comparison.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.comparison.setMinimumContentsLength(16)
        compare_label = QLabel('Compare &with')
        compare_label.setBuddy(self.comparison)
        compare_row = QHBoxLayout()
        compare_row.addWidget(compare_label)
        compare_row.addWidget(self.comparison, 1)
        right.addLayout(compare_row)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setAccessibleName('Version notes and design changes')
        right.addWidget(self.preview)
        splitter.addWidget(detail)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 490])
        layout.addWidget(splitter, 1)

        self.message = label('', 'muted')
        self.message.setTextFormat(Qt.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        buttons = QDialogButtonBox()
        self.save_button = buttons.addButton('Save Version…', QDialogButtonBox.ActionRole)
        self.restore_button = buttons.addButton('Restore Version', QDialogButtonBox.ActionRole)
        done = buttons.addButton('Done', QDialogButtonBox.RejectRole)
        self.save_button.setProperty('role', 'secondary')
        self.restore_button.setProperty('role', 'secondary')
        done.setProperty('role', 'primary')
        for button in (self.save_button, self.restore_button, done):
            button.setAutoDefault(False)
        self.save_button.clicked.connect(self.save_new)
        self.restore_button.clicked.connect(self.restore)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.versions.currentItemChanged.connect(self.selection_changed)
        self.comparison.currentIndexChanged.connect(self.show_comparison)
        self.reload()
        (self.versions if self.versions.count() else self.save_button).setFocus()

    def reload(self, selected=None):
        self.versions.blockSignals(True)
        self.versions.clear()
        self.records = {}
        path = self.studio.path
        self.store = version_store(self.studio) if path else None
        error = ''
        try:
            for version in self.store.list() if self.store else ():
                self.records[version.id] = version
                item = QListWidgetItem(f'{version.name}\n{dated_title(version)}')
                item.setData(Qt.UserRole, version.id)
                item.setToolTip(version.name + '\n' + dated_title(version))
                self.versions.addItem(item)
                if version.id == selected:
                    self.versions.setCurrentItem(item)
        except (OSError, ValueError) as exc:
            error = str(exc)
        if self.versions.count() and not self.versions.currentItem():
            self.versions.setCurrentRow(0)
        self.versions.blockSignals(False)
        self.selection_changed()
        if error:
            self.message.setText(error)

    def selection_changed(self, *_):
        self.comparison.blockSignals(True)
        previous = self.comparison.currentData()
        self.comparison.clear()
        self.comparison.addItem('Working Design', None)
        item = self.versions.currentItem()
        self.selected = self.records[item.data(Qt.UserRole)] if item else None
        for version in self.records.values():
            if version != self.selected:
                self.comparison.addItem(f'{version.name} · {dated_title(version)}', version.id)
        self.comparison.setCurrentIndex(max(0, self.comparison.findData(previous)))
        self.comparison.blockSignals(False)
        self.comparison.setEnabled(bool(self.selected and len(self.records) > 1))
        self.show_comparison()

    def show_comparison(self, *_):
        self.restore_button.setEnabled(False)
        self.message.clear()
        if self.selected is None:
            self.preview.setPlainText('No saved versions. Save a version to keep a point you can return to.'
                                      if self.store else 'Save this project to start keeping versions.')
            self.versions.setEnabled(False)
            return
        self.versions.setEnabled(True)
        try:
            saved = self.store.load(self.selected.id)
            working = self.studio.project
            other = self.comparison.currentData()
            baseline = self.store.load(other) if other else working
            changes = compare(baseline, saved)
        except (OSError, ValueError) as exc:
            self.preview.clear()
            self.message.setText(str(exc))
            return
        content = [self.selected.name, dated_title(self.selected)]
        if self.selected.note:
            content.extend(['', self.selected.note])
        content.extend(['', 'Changes in the selected version'])
        content.extend(changes or ['No design differences.'])
        self.preview.setPlainText('\n'.join(content))
        reason = restore_blocker(self.studio)
        if reason:
            self.message.setText(reason)
        elif same_design(working, saved):
            self.message.setText('The working design already matches this version.')
        else:
            self.restore_button.setEnabled(True)
            self.message.setText('Restoring keeps a copy of your current design in Version History.')

    def save_new(self):
        version = save_version(self.studio)
        if version:
            self.reload(version.id)
            self.versions.setFocus()

    def restore(self):
        if self.selected is None:
            return
        studio = self.studio
        try:
            reason = restore_blocker(studio)
            if reason:
                raise ValueError(reason)
            if not working_design_ready(studio):
                raise ValueError('Resolve the pending project edits before restoring a version.')
            saved = self.store.load(self.selected.id)
            if same_design(studio.project, saved):
                self.show_comparison()
                return
            title = self.selected.name
            self.store.save(studio.project, f'Before restoring {title[:80]}',
                            f'Working design before restoring “{title}”.')
            studio.cancel_tool()
            studio.selection = []
            studio.net = ''
            studio.commit(lambda p: restore_contents(p, saved), 'Restore version')
        except (OSError, ValueError) as exc:
            self.message.setText(str(exc))
            return
        studio.show_design_workspace()
        studio.statusBar().showMessage(f'Restored “{title}”. Use Undo to return to the previous design.', 9000)
        self.accept()


def show_history(studio):
    if not working_design_ready(studio):
        return
    dialog = VersionHistoryDialog(studio)
    try:
        dialog.exec()
    finally:
        dialog.deleteLater()


def install(studio):
    from .project_branches_ui import show_branches
    file_menu = studio.task_menus['File']
    menu = QMenu('Versions', file_menu)
    file_menu.insertMenu(studio.command_actions['Close project'], menu)
    studio.action(menu, 'Save Version…', lambda: save_version(studio))
    studio.action(menu, 'Browse Versions…', lambda: show_history(studio))
    studio.action(menu, 'Branches and GitHub…', lambda: show_branches(studio))
