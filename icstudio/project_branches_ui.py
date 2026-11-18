"""Branch management and a document-modal merge review."""
import json

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QGridLayout, QInputDialog, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
                               QTabWidget, QVBoxLayout, QWidget)

from .project_git import ProjectGit
from .project_hub_ui import HubWorker, label
from .project_merge import MISSING
from .project_versions import ProjectVersions, compare, restore_contents, same_design
from .project_versions_ui import configure_dialog, restore_blocker, save_version, working_design_ready


def read_only(name):
    text = QPlainTextEdit()
    text.setReadOnly(True)
    text.setAccessibleName(name)
    return text


def describe(value):
    if value is MISSING:
        return 'Absent in this version.'
    if isinstance(value, dict) and {'cells', 'pdk', 'name', 'revision'} <= value.keys():
        cells = ', '.join(cell['name'] for cell in value['cells'])
        return f'{value["name"]}\nRevision {value["revision"]}\n{value["pdk"]["name"]}\n\nCells\n{cells}'
    text = json.dumps(value, ensure_ascii=False, indent=2)
    return text if len(text) <= 32000 else text[:32000] + '\n\nPreview shortened.'


class MergeDialog(QDialog):
    def __init__(self, studio, review, apply, parent):
        super().__init__(parent)
        configure_dialog(self, studio, 'Review Merge')
        self.resize(860, 540)
        self.review = review
        self.apply_merge = apply
        self.choices = {}
        self.conflicts = review.resolve()[1]
        layout = QVBoxLayout(self)
        source = ('GitHub / ' if review.source.remote else '') + review.source.name
        layout.addWidget(label(f'Merge {source} into {review.target.name}', 'title'))
        self.status = label('')
        layout.addWidget(self.status)

        tabs = QTabWidget()
        tabs.setAccessibleName('Merge review')
        splitter = QSplitter()
        self.conflict_list = QListWidget()
        self.conflict_list.setMinimumWidth(180)
        self.conflict_list.setAccessibleName('Conflicts')
        splitter.addWidget(self.conflict_list)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(10, 0, 0, 0)
        sides = QSplitter()
        self.values = []
        for name in ('Current Branch', 'Incoming Branch'):
            column = QWidget()
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(0, 0, 0, 0)
            column_layout.addWidget(label(name, 'subtitle'))
            field = read_only(name + ' value')
            field.setMinimumWidth(125)
            column_layout.addWidget(field)
            self.values.append(field)
            sides.addWidget(column)
        sides.setChildrenCollapsible(False)
        detail_layout.addWidget(sides, 3)
        detail_layout.addWidget(label('Common Ancestor', 'subtitle'))
        self.base_value = read_only('Common ancestor value')
        detail_layout.addWidget(self.base_value, 1)
        self.choice = QComboBox()
        self.choice.setAccessibleName('Resolution for selected conflict')
        self.choice.addItem('Choose a resolution…', None)
        self.choice.addItem('Keep Current Value', 'current')
        self.choice.addItem('Use Incoming Value', 'incoming')
        form = QFormLayout()
        form.addRow('&Resolution', self.choice)
        detail_layout.addLayout(form)
        splitter.addWidget(detail)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([215, 625])
        if self.conflicts:
            tabs.addTab(splitter, 'Conflicts')
        else:
            splitter.setParent(self)
            splitter.hide()
        self.changes = read_only('Design changes')
        tabs.addTab(self.changes, 'Changes')
        layout.addWidget(tabs, 1)
        self.message = label('', 'error')
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.merge_button = buttons.addButton('Merge Branches', QDialogButtonBox.ActionRole)
        self.merge_button.setProperty('role', 'secondary')
        for button in buttons.buttons():
            button.setAutoDefault(False)
        self.merge_button.clicked.connect(self.finish_merge)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for row in self.conflicts:
            self.conflict_list.addItem(QListWidgetItem(row.label))
        self.conflict_list.currentRowChanged.connect(self.show_conflict)
        self.choice.currentIndexChanged.connect(self.choose)
        self.conflict_list.setCurrentRow(0)
        self.refresh()
        (self.conflict_list if self.conflicts else self.changes).setFocus()

    def show_conflict(self, index):
        if index < 0:
            return
        row = self.conflicts[index]
        for field, value in zip(self.values, (row.current, row.incoming)):
            field.setPlainText(describe(value))
        self.base_value.setPlainText(describe(row.base))
        self.choice.blockSignals(True)
        self.choice.setCurrentIndex(max(0, self.choice.findData(self.choices.get(row.path))))
        self.choice.blockSignals(False)

    def choose(self):
        index = self.conflict_list.currentRow()
        if index >= 0:
            self.choices[self.conflicts[index].path] = self.choice.currentData()
            self.refresh()

    def refresh(self):
        candidate, _, error = self.review.resolve(self.choices)
        unresolved = 0
        for i, row in enumerate(self.conflicts):
            choice = self.choices.get(row.path)
            text = {'current': 'Keep current', 'incoming': 'Use incoming'}.get(choice, 'Needs a choice')
            self.conflict_list.item(i).setText(f'{row.label}\n{text}')
            unresolved += choice is None
        if unresolved:
            suffix = '' if unresolved == 1 else 's'
            self.status.setText(f'{unresolved} conflict{suffix} to resolve')
        else:
            self.status.setText('Ready to merge' if candidate is not None else 'Review the combined design')
        if candidate is None:
            title = 'Changes on the incoming branch'
            rows = compare(self.review.ancestor, self.review.incoming)
        else:
            title = 'Changes the merge will apply'
            rows = compare(self.review.current, candidate)
        self.changes.setPlainText('\n'.join([title, '', *(rows or ['No design differences.'])]))
        self.message.setText(error)
        self.merge_button.setEnabled(candidate is not None)

    def finish_merge(self):
        try:
            self.apply_merge(self.review, self.choices)
        except (OSError, ValueError, KeyError) as exc:
            self.message.setText(str(exc))
            return
        self.accept()


class BranchesDialog(QDialog):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        self.document = studio.history
        self.path = studio.path
        self.git = ProjectGit(studio.path, studio.project['id'])
        self.worker = None
        self.published = set()
        configure_dialog(self, studio, 'Branches and GitHub')
        self.resize(720, 465)
        layout = QVBoxLayout(self)
        layout.addWidget(label(studio.project['name'], 'title'))
        self.summary = label('')
        layout.addWidget(self.summary)
        self.list = QListWidget()
        self.list.setAccessibleName('Local and GitHub branches')
        self.list.currentItemChanged.connect(lambda *_: self.controls())
        layout.addWidget(self.list, 1)
        self.buttons = {}
        actions = QGridLayout()
        for index, (key, title, fn) in enumerate((
            ('start', 'Enable Branches', self.start), ('new', 'New Branch…', self.create),
            ('version', 'Save Version…', self.capture), ('switch', 'Switch Branch', self.switch),
            ('tip', 'Load Saved Version', self.load_tip), ('merge', 'Review Merge…', self.review),
            ('connect', 'Connect to GitHub…', self.connect), ('fetch', 'Fetch GitHub Branches', self.fetch),
            ('push', 'Publish Branch…', self.publish), ('pr', 'Compare on GitHub…', self.pull_request),
            ('disconnect', 'Disconnect GitHub', self.disconnect),
        )):
            button = QPushButton(title)
            button.setAutoDefault(False)
            button.setProperty('role', 'secondary')
            button.clicked.connect(lambda checked=False, fn=fn: self.perform(fn))
            actions.addWidget(button, index // 3, index % 3)
            self.buttons[key] = button
        layout.addLayout(actions)
        self.message = label('')
        layout.addWidget(self.message)
        buttons = QDialogButtonBox()
        self.done_button = buttons.addButton('Done', QDialogButtonBox.RejectRole)
        self.done_button.setAutoDefault(False)
        self.done_button.setProperty('role', 'primary')
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.active = None
        self.remote = ''
        self.local_names = set()
        self.remote_names = set()
        self.reload()
        (self.list if self.list.count() else self.buttons['start']).setFocus()

    def perform(self, fn):
        try:
            fn()
        except (OSError, ValueError, KeyError) as exc:
            self.message.setText(str(exc))

    def selected(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def reload(self, name=None):
        selected = self.selected()
        branches = self.git.entries()
        self.active = self.git.active() if self.git.path.exists() else None
        self.remote = self.git.remote_url() if self.active else ''
        self.local_names = {branch.name for branch in branches if not branch.remote}
        self.remote_names = {branch.name for branch in branches if branch.remote}
        parts = [f'Current branch · {self.active.name}' if self.active and self.active.head else 'No active branch version']
        parts.append(self.remote.removesuffix('.git') if self.remote else 'GitHub is disconnected')
        self.summary.setText('\n'.join(parts))
        self.list.blockSignals(True)
        self.list.clear()
        preferred = name or (selected.ref if selected else '') or (self.active.ref if self.active else '')
        for branch in branches:
            prefix = 'GitHub / ' if branch.remote else ''
            badge = '  ·  Current' if branch == self.active else ''
            item = QListWidgetItem(prefix + branch.name + badge)
            item.setData(Qt.UserRole, branch)
            item.setToolTip(branch.head)
            self.list.addItem(item)
            if preferred == branch.ref:
                self.list.setCurrentItem(item)
        if self.list.count() and self.list.currentRow() < 0:
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self.controls()

    def controls(self):
        branch = self.selected()
        head = bool(self.active and self.active.head)
        ready = self.worker is None
        enabled = {
            'start': not head and not self.remote_names, 'new': head,
            'version': bool(self.active), 'switch': branch is not None and branch != self.active
            and (not branch.remote or branch.name not in self.local_names),
            'tip': head and branch == self.active, 'merge': head and branch is not None and branch != self.active,
            'connect': not self.remote, 'fetch': bool(self.remote),
            'disconnect': bool(self.remote),
            'push': bool(self.remote and branch and not branch.remote),
            'pr': bool(self.remote and branch and branch.name in self.remote_names | self.published
                       and (self.remote_names | self.published) - {branch.name}),
        }
        visible = {'fetch', 'push', 'pr', 'disconnect'} if self.remote else {'connect'}
        if head:
            visible.update(('new', 'version', 'switch', 'tip', 'merge'))
        elif self.remote_names:
            visible.add('switch')
        else:
            visible.add('start')
        for key, button in self.buttons.items():
            button.setEnabled(ready and enabled[key])
            button.setVisible(key in visible)
        self.list.setEnabled(ready)
        self.done_button.setEnabled(ready)

    def working(self, require_saved=True):
        if self.studio.history is not self.document or self.studio.path != self.path:
            raise ValueError('The open project changed. Reopen Branches and GitHub to continue.')
        blocker = restore_blocker(self.studio)
        if blocker:
            raise ValueError(blocker)
        if not working_design_ready(self.studio):
            raise ValueError('Resolve the pending edits before changing branches.')
        design = self.studio.project
        active = self.git.active() if self.active else None
        if active != self.active:
            self.reload()
            raise ValueError('Branch history changed. Review the branch list and try again.')
        if require_saved and active and active.head and not same_design(design, self.git.load(active.head)):
            raise ValueError('Save a version of your working design before switching or merging branches.')
        return design

    def apply_design(self, design, title):
        studio = self.studio
        if not same_design(studio.project, design):
            studio.cancel_tool()
            studio.selection = []
            studio.net = ''
            studio.commit(lambda project: restore_contents(project, design), title)
        studio.show_design_workspace()

    def start(self):
        project = self.working(require_saved=False)
        self.git.initialize()
        self.git.save(project, 'Start project branch history')
        self.reload()
        self.message.setText('Branch history is ready. Save Version records changes on the current branch.')

    def capture(self):
        if save_version(self.studio):
            self.reload()
            self.message.setText('Saved a version on ' + self.active.name + '.')

    def create(self):
        name, accepted = QInputDialog.getText(self, 'New Branch', 'Branch name')
        if accepted:
            self.working()
            branch = self.git.create(name, self.active.head)
            self.apply_design(self.git.switch(branch), 'Switch branch')
            self.reload(branch.ref)
            self.message.setText('Now on ' + branch.name + '.')

    def save_safety_copy(self, project, name):
        ProjectVersions(self.studio.path, project['id']).save(project, name)

    def switch(self):
        project = self.working()
        source = self.selected()
        if not self.active.head and not same_design(project, self.git.load(source.head)):
            self.save_safety_copy(project, 'Before joining a GitHub branch')
        design = self.git.switch(source)
        self.apply_design(design, 'Switch branch')
        self.reload(self.git.active().ref)
        self.message.setText(f'Now on {source.name}. Save to update the project file.')

    def load_tip(self):
        project = self.working(require_saved=False)
        recorded = self.git.load(self.active.head)
        if not same_design(project, recorded):
            self.save_safety_copy(project, 'Before loading the current branch version')
            self.apply_design(recorded, 'Load branch version')
        self.message.setText(f'Working design matches the latest version on {self.active.name}.')

    def review(self):
        self.working()
        review = self.git.review(self.selected())
        dialog = MergeDialog(self.studio, review, self.apply_merge, self)
        try:
            if dialog.exec() == QDialog.Accepted:
                self.reload(review.target.ref)
                self.message.setText('Merged into ' + review.target.name + '. Save to update the project file.')
        finally:
            dialog.deleteLater()

    def apply_merge(self, review, choices):
        self.working()
        design = self.git.merge(review, choices, self.studio.history.serial + 1)
        self.apply_design(design, 'Merge branches')

    def run_network(self, operation, message, done):
        self.message.setText(message)
        worker = HubWorker(operation, self)
        self.worker = worker
        self.controls()

        def finished():
            self.worker = None
            self.controls()
            if worker.error:
                self.message.setText(worker.error)
            else:
                self.perform(done)
            worker.deleteLater()

        worker.finished.connect(finished)
        worker.start()

    def done(self, result):
        if self.worker is None:
            super().done(result)

    def connect(self):
        url, accepted = QInputDialog.getText(self, 'Connect to GitHub', 'GitHub repository URL')
        if accepted:
            self.git.initialize()

            def connected():
                self.reload()
                self.fetch()

            self.run_network(lambda: self.git.connect(url), 'Connecting to GitHub…', connected)

    def fetch(self):
        def fetched():
            self.reload()
            self.message.setText('Fetched branch versions from GitHub.')

        self.run_network(self.git.fetch, 'Fetching branches…', fetched)

    def disconnect(self):
        self.git.disconnect()
        self.published.clear()
        self.reload()
        self.message.setText('Disconnected GitHub. Your local branches are available.')

    def publish(self):
        branch = self.selected()
        notice = QMessageBox(QMessageBox.Question, 'Publish Branch',
                             f'Publish “{branch.name}” to {self.remote.removesuffix(".git")}?', parent=self)
        notice.setInformativeText('GitHub will receive the saved design and its branch history, including files embedded in the project.')
        publish = notice.addButton('Publish Branch', QMessageBox.AcceptRole)
        notice.addButton(QMessageBox.Cancel)
        publish.setAutoDefault(False)
        notice.exec()
        if notice.clickedButton() is publish:
            def complete():
                self.published.add(branch.name)
                self.controls()
                self.message.setText(f'Published {branch.name} to GitHub.')

            self.run_network(lambda: self.git.publish(branch), 'Publishing branch…', complete)

    def pull_request(self):
        head = self.selected().name
        targets = sorted((self.remote_names | self.published) - {head}, key=lambda name: (name != 'main', name))
        base, accepted = QInputDialog.getItem(self, 'Compare on GitHub', 'Base branch', targets, 0, False)
        if accepted and not QDesktopServices.openUrl(QUrl(self.git.pull_request_url(base, head), QUrl.StrictMode)):
            raise ValueError('Could not open GitHub in the browser.')


def show_branches(studio):
    if studio.path is None and not studio.save():
        return
    dialog = BranchesDialog(studio)
    try:
        dialog.exec()
    finally:
        dialog.deleteLater()
