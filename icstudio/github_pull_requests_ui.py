"""Document-modal GitHub pull requests, review, and merge confirmation."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QSplitter, QTabWidget, QVBoxLayout)

from .github_pull_requests import GitHubPullRequests, MERGE_METHODS, REVIEW_EVENTS
from .project_hub_ui import HubWorker, label
from .project_versions_ui import configure_dialog


def text_view(name):
    text = QPlainTextEdit()
    text.setReadOnly(True)
    text.setAccessibleName(name)
    return text


def combo(name, options):
    widget = QComboBox()
    widget.setAccessibleName(name)
    for display, value in options:
        widget.addItem(display, value)
    return widget


def action_button(title, fn):
    button = QPushButton(title)
    button.setAutoDefault(False)
    button.setProperty('role', 'secondary')
    button.clicked.connect(fn)
    return button


def form_dialog(parent, studio, title, action, *, explicit=False):
    dialog = QDialog(parent)
    configure_dialog(dialog, studio, title)
    dialog.resize(530, 180 if explicit else 335)
    outer = QVBoxLayout(dialog)
    form = QFormLayout()
    outer.addLayout(form, 1)
    if explicit:
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(action_button('Cancel', dialog.reject))
        submit = action_button(action, dialog.accept)
        submit.setProperty('role', 'primary')
        actions.addWidget(submit)
        outer.addLayout(actions)
        return dialog, form, submit
    box = QDialogButtonBox(QDialogButtonBox.Cancel)
    submit = box.addButton(action, QDialogButtonBox.AcceptRole)
    submit.setProperty('role', 'primary')
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    submit.setDefault(True)
    outer.addWidget(box)
    return dialog, form, submit


def merge_status(request):
    if not request.open or request.draft:
        return request.status
    if request.mergeable is None:
        return 'GitHub is checking mergeability. Refresh to check again.'
    if not request.mergeable:
        return 'GitHub found merge conflicts. Update the head branch and refresh.'
    messages = {
        'blocked': 'GitHub reports branch requirements that may block merging.',
        'behind': 'The head branch is behind the base branch.',
        'unstable': 'GitHub reports checks that may need attention.',
    }
    return messages.get(request.merge_state, 'GitHub reports that the branches can merge.')


class PatchHighlight(QSyntaxHighlighter):
    def __init__(self, document, dark):
        super().__init__(document)
        colors = ('#91dcaf', '#ffa6ae', '#a8bbff') if dark else ('#176746', '#a52a45', '#3856a8')
        self.styles = {}
        for prefix, color in zip(('+', '-', '@'), colors):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            self.styles[prefix] = fmt

    def highlightBlock(self, text):
        fmt = self.styles.get(text[:1])
        if fmt is not None:
            self.setFormat(0, len(text), fmt)


class PullRequestsDialog(QDialog):
    def __init__(self, studio, client, suggested_head=''):
        super().__init__(studio, Qt.Window)
        self.studio = studio
        self.client = client
        self.suggested_head = suggested_head
        self.default_branch = ''
        self.methods = []
        self.page = 1
        self.more = False
        self.detail = None
        self.worker = None
        self.loading_detail = False
        self.first_load = True
        self.new_draft = None
        self.review_drafts = {}
        configure_dialog(self, studio, 'GitHub Pull Requests')
        self.resize(940, 590)
        outer = QVBoxLayout(self)
        outer.addWidget(label(client.repository, 'title'))
        actions = QHBoxLayout()
        self.filter = combo('Pull request status filter', [('Open', 'open'), ('Closed', 'closed'), ('All', 'all')])
        filter_label = QLabel('&Status')
        filter_label.setBuddy(self.filter)
        actions.addWidget(filter_label)
        actions.addWidget(self.filter)
        self.refresh_button = action_button('Refresh', self.refresh)
        actions.addWidget(self.refresh_button)
        actions.addStretch()
        self.new_button = action_button('New Pull Request…', self.new_request)
        actions.addWidget(self.new_button)
        outer.addLayout(actions)

        split = QSplitter()
        split.setChildrenCollapsible(False)
        self.requests = QListWidget()
        self.requests.setAccessibleName('Pull requests')
        self.requests.setMinimumWidth(200)
        self.requests.setWordWrap(True)
        split.addWidget(self.requests)
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName('Pull request details')
        self.overview = text_view('Pull request overview')
        self.tabs.addTab(self.overview, 'Overview')
        files = QSplitter()
        files.setChildrenCollapsible(False)
        self.files = QListWidget()
        self.files.setAccessibleName('Changed files')
        self.files.setMinimumWidth(125)
        self.patch = text_view('Changes in selected file')
        self.patch.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.patch.setStyleSheet('QPlainTextEdit { font-family: "Consolas", "Liberation Mono", monospace; }')
        self.patch_highlight = PatchHighlight(self.patch.document(), studio.dark)
        files.addWidget(self.files)
        files.addWidget(self.patch)
        files.setStretchFactor(1, 1)
        files.setSizes([155, 500])
        self.tabs.addTab(files, 'Changes')
        self.reviews = text_view('Submitted reviews')
        self.tabs.addTab(self.reviews, 'Reviews')
        split.addWidget(self.tabs)
        split.setStretchFactor(1, 1)
        split.setSizes([265, 660])
        outer.addWidget(split, 1)

        self.message = label('')
        outer.addWidget(self.message)
        bottom = QHBoxLayout()
        self.more_button = action_button('Load More', self.load_more)
        bottom.addWidget(self.more_button)
        bottom.addStretch()
        self.review_button = action_button('Submit Review…', self.submit_review)
        self.merge_button = action_button('Merge Pull Request…', self.merge_request)
        self.done_button = action_button('Done', self.reject)
        self.done_button.setProperty('role', 'primary')
        for button in (self.review_button, self.merge_button, self.done_button):
            bottom.addWidget(button)
        outer.addLayout(bottom)
        self.filter.currentIndexChanged.connect(self.refresh)
        self.requests.currentItemChanged.connect(self.load_selected)
        self.files.currentItemChanged.connect(self.show_patch)
        self.overview.setPlainText('Select a pull request to review.')
        self.controls()
        self.requests.setFocus()
        QTimer.singleShot(0, self.refresh)

    def selected_number(self):
        item = self.requests.currentItem()
        return item.data(Qt.UserRole) if item else None

    def controls(self):
        ready = self.worker is None
        request = self.detail.request if self.detail else None
        self.filter.setEnabled(ready)
        self.requests.setEnabled(ready or self.loading_detail)
        self.refresh_button.setEnabled(ready)
        self.new_button.setEnabled(ready)
        self.more_button.setVisible(self.more)
        self.more_button.setEnabled(ready and self.more)
        self.review_button.setEnabled(ready and bool(request and request.open))
        self.merge_button.setEnabled(ready and bool(request and request.can_merge and self.methods))
        self.done_button.setEnabled(ready)

    def run(self, fn, message, success, *, detail_for=None, prior_result=''):
        if self.worker is not None:
            return
        worker = HubWorker(fn, self)
        self.worker = worker
        self.loading_detail = detail_for is not None
        self.message.setText(message)
        self.controls()

        def finished():
            self.worker = None
            self.loading_detail = False
            self.controls()
            try:
                if detail_for is not None and self.selected_number() != detail_for:
                    self.load_selected()
                elif worker.error:
                    self.message.setText((prior_result + ' ' + worker.error).strip())
                else:
                    success(worker.result)
            except (OSError, ValueError, KeyError) as exc:
                self.message.setText(str(exc))
            finally:
                worker.deleteLater()

        worker.finished.connect(finished)
        worker.start()

    def done(self, result):
        if self.worker is None:
            super().done(result)

    def populate(self, rows, preferred=None, *, append=False):
        self.requests.blockSignals(True)
        if not append:
            self.requests.clear()
        existing = {self.requests.item(i).data(Qt.UserRole) for i in range(self.requests.count())}
        for request in rows:
            if request.number in existing:
                continue
            item = self.request_item(request)
            self.requests.addItem(item)
            if request.number == preferred:
                self.requests.setCurrentItem(item)
        if self.requests.count() and self.requests.currentRow() < 0:
            self.requests.setCurrentRow(0)
        self.requests.blockSignals(False)

    def request_item(self, request):
        item = QListWidgetItem(self.request_summary(request))
        item.setToolTip(item.text())
        item.setData(Qt.UserRole, request.number)
        return item

    def request_summary(self, request):
        return f'#{request.number}  {request.title}\n{request.status} · {request.head} → {request.base}'

    def refresh(self, *_):
        if self.worker is not None:
            return
        preferred, state = self.selected_number(), self.filter.currentData()
        self.detail = None
        self.more = False
        self.populate([])
        self.clear_detail('Loading pull requests…')

        def fetch():
            return self.client.repository_info(), self.client.list(state)

        def loaded(result):
            metadata, listing = result
            self.default_branch, self.methods = metadata
            rows, self.more = listing
            self.page = 1
            self.populate(rows, preferred)
            if self.first_load:
                (self.requests if rows else self.new_button).setFocus()
                self.first_load = False
            self.load_selected()

        self.run(fetch, 'Loading pull requests…', loaded)

    def load_more(self):
        page, state = self.page + 1, self.filter.currentData()

        def loaded(listing):
            rows, self.more = listing
            self.page = page
            self.populate(rows, append=True)
            self.message.clear()
            self.controls()

        self.run(lambda: self.client.list(state, page), 'Loading more pull requests…', loaded)

    def clear_detail(self, text):
        self.detail = None
        self.overview.setPlainText(text)
        self.files.clear()
        self.patch.clear()
        self.reviews.clear()

    def load_selected(self, *_, announcement=''):
        number = self.selected_number()
        if number is None:
            self.clear_detail('No pull requests match this filter.')
            self.message.clear()
            self.controls()
            return
        self.clear_detail(f'Loading pull request #{number}…')
        if self.worker is None:
            self.run(lambda: self.client.detail(number), announcement or f'Loading pull request #{number}…',
                     lambda detail: self.present(detail, announcement), detail_for=number, prior_result=announcement)

    def present(self, detail, announcement=''):
        self.detail = detail
        request = detail.request
        item = self.requests.currentItem()
        if item:
            item.setText(self.request_summary(request))
            item.setToolTip(item.text())
        fields = [f'#{request.number}  {request.title}', f'{request.status} · {request.author}',
                  f'{request.head} → {request.base}', '', request.body or 'No description.']
        self.overview.setPlainText('\n'.join(fields))
        self.files.blockSignals(True)
        self.files.clear()
        for row in detail.files:
            name = row['filename']
            item = QListWidgetItem(f'{name}\n{row["status"].capitalize()} · +{row["additions"]} / −{row["deletions"]}')
            item.setToolTip(name)
            item.setData(Qt.UserRole, row)
            self.files.addItem(item)
        self.files.setCurrentRow(0)
        self.files.blockSignals(False)
        self.show_patch()
        reviews = []
        for row in detail.reviews:
            user = (row.get('user') or {}).get('login', 'Unknown reviewer')
            state = row['state'].replace('_', ' ').capitalize()
            when = row.get('submitted_at') or ''
            reviews.append(f'{user} · {state}' + (f' · {when}' if when else '') + '\n' + (row.get('body') or ''))
        self.reviews.setPlainText('\n\n'.join(reviews) if reviews else 'No submitted reviews.')
        self.message.setText(announcement or merge_status(request))
        self.controls()

    def show_patch(self, *_):
        item = self.files.currentItem()
        if item is None:
            self.patch.setPlainText('No changed files to show.' if self.detail else '')
            return
        row = item.data(Qt.UserRole)
        patch = row.get('patch')
        self.patch.setPlainText(patch if patch else 'GitHub did not include a text patch for this file.')

    def new_request(self):
        self.run(self.client.branch_names, 'Loading published branches…', self.compose_request)

    def compose_request(self, names):
        if len(names) < 2:
            self.message.setText('Publish a base branch and a head branch before creating a pull request.')
            return
        names = sorted(names, key=lambda name: (name != self.default_branch, name))
        draft_base, draft_head, draft_title, draft_body = self.new_draft or ('', '', '', '')
        dialog, form, submit = form_dialog(self, self.studio, 'New Pull Request', 'Create Pull Request')
        base = combo('Base branch', [(name, name) for name in names])
        base.setCurrentIndex(max(0, base.findData(draft_base)))
        head = combo('Head branch', [(name, name) for name in names])
        preferred = draft_head or self.suggested_head
        if preferred not in names or preferred == base.currentData():
            preferred = next(name for name in names if name != base.currentData())
        head.setCurrentIndex(head.findData(preferred))
        title = QLineEdit(draft_title)
        title.setMaxLength(256)
        title.setAccessibleName('Pull request title')
        body = QPlainTextEdit(draft_body)
        body.setAccessibleName('Pull request description')
        form.addRow('&Base', base)
        form.addRow('&Head', head)
        form.addRow('&Title', title)
        form.addRow('&Description', body)

        def valid(*_):
            submit.setEnabled(bool(title.text().strip()) and base.currentData() != head.currentData())

        title.textChanged.connect(valid)
        base.currentIndexChanged.connect(valid)
        head.currentIndexChanged.connect(valid)
        valid()
        title.setFocus()
        try:
            if dialog.exec() != QDialog.Accepted:
                self.message.clear()
                return
            self.new_draft = (base.currentData(), head.currentData(), title.text(), body.toPlainText())
        finally:
            dialog.deleteLater()
        base_name, head_name, title_text, body_text = self.new_draft
        self.run(lambda: self.client.create(title_text, body_text, base_name, head_name),
                 'Creating pull request…', self.request_created)

    def request_created(self, request):
        self.new_draft = None
        self.requests.blockSignals(True)
        if self.filter.currentData() == 'closed':
            self.requests.clear()
            self.more = False
            self.page = 1
            self.filter.blockSignals(True)
            self.filter.setCurrentIndex(0)
            self.filter.blockSignals(False)
        item = self.request_item(request)
        self.requests.insertItem(0, item)
        self.requests.setCurrentItem(item)
        self.requests.blockSignals(False)
        self.tabs.setCurrentIndex(0)
        self.load_selected(announcement=f'Created pull request #{request.number}.')

    def submit_review(self):
        if self.detail is None:
            return
        request = self.detail.request
        dialog, form, submit = form_dialog(self, self.studio, f'Review Pull Request #{request.number}', 'Submit Review')
        previous = self.review_drafts.get(request.number, ('COMMENT', ''))
        event = combo('Review action', [(title, key) for key, title in REVIEW_EVENTS.items()])
        event.setCurrentIndex(event.findData(previous[0]))
        comment = QPlainTextEdit(previous[1])
        comment.setAccessibleName('Review comment')
        form.addRow('&Action', event)
        form.addRow('&Comment', comment)

        def valid(*_):
            submit.setEnabled(event.currentData() == 'APPROVE' or bool(comment.toPlainText().strip()))

        event.currentIndexChanged.connect(valid)
        comment.textChanged.connect(valid)
        valid()
        event.setFocus()
        try:
            if dialog.exec() != QDialog.Accepted:
                return
            choice = event.currentData(), comment.toPlainText()
            self.review_drafts[request.number] = choice
        finally:
            dialog.deleteLater()

        def submitted(_):
            self.review_drafts.pop(request.number, None)
            self.tabs.setCurrentIndex(2)
            self.load_selected(announcement='Submitted review to GitHub.')

        self.run(lambda: self.client.review(request, *choice), 'Submitting review…', submitted)

    def merge_request(self):
        if self.detail is None or not self.detail.request.can_merge:
            return
        request = self.detail.request
        dialog, form, submit = form_dialog(self, self.studio, f'Merge Pull Request #{request.number}',
                                           'Merge Pull Request', explicit=True)
        form.addRow(label(f'Merge {request.head} into {request.base} on {self.client.repository}?'))
        method = combo('Merge method', [(MERGE_METHODS[key], key) for key in self.methods])
        form.addRow('&Method', method)
        form.addRow(label('GitHub applies this change to the base branch.'))
        method.setFocus()
        try:
            if dialog.exec() != QDialog.Accepted:
                return
            choice = method.currentData()
        finally:
            dialog.deleteLater()

        def merged(_):
            self.tabs.setCurrentIndex(0)
            self.load_selected(announcement=f'Merged pull request #{request.number} into {request.base} on GitHub.')

        self.run(lambda: self.client.merge(request, choice), 'Merging pull request…', merged)


def show_pull_requests(studio, url, suggested_head=''):
    dialog = PullRequestsDialog(studio, GitHubPullRequests(url), suggested_head)
    try:
        dialog.exec()
    finally:
        dialog.deleteLater()
