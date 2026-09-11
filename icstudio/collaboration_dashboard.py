"""One accessible Tools dashboard for live and shared-folder collaboration."""
from datetime import datetime
import time

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QApplication, QDialog,
    QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QTabWidget, QTreeWidget, QTreeWidgetItem, QSizePolicy,
    QVBoxLayout, QWidget)

from .live_review import recent_sessions, reservation_rows


def note(text):
    widget = QLabel(text)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.PlainText)
    return widget


def button(text, callback, parent_layout, primary=False):
    widget = QPushButton(text)
    widget.setMinimumHeight(36)
    if primary:
        widget.setProperty('role', 'primary')
    widget.clicked.connect(callback)
    parent_layout.addWidget(widget)
    return widget


def scrolling_page(widget):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setMinimumSize(0, 0)
    scroll.setWidget(widget)
    return scroll


class SessionScan(QThread):
    ready = Signal(list)

    def __init__(self, directory, parent):
        super().__init__(parent)
        self.directory = directory

    def run(self):
        self.ready.emit(recent_sessions(self.directory, self.isInterruptionRequested))


class CollaborationDashboard(QDialog):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        self.setWindowTitle('Collaboration')
        self.setObjectName('collaborationDashboard')
        self.resize(920, 700)
        self.setMinimumSize(620, 460)
        self.scan = None
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)
        heading = note('Work on a design together')
        heading.setProperty('role', 'title')
        heading.setMinimumHeight(36)
        heading.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        root.addWidget(heading)
        self.summary = note('Share a project, join your team, or pick up where you left off.')
        self.summary.setMinimumHeight(32)
        self.summary.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        root.addWidget(self.summary)
        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(160)
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.tabs.setAccessibleName('Collaboration dashboard sections')
        root.addWidget(self.tabs, 1)
        self.overview = QWidget()
        overview = QVBoxLayout(self.overview)
        overview.setSpacing(12)
        actions = QHBoxLayout()
        self.share = button('Host a session…', lambda: self.run(studio.host_session_dialog), actions, True)
        self.join = button('Join a workspace…', lambda: self.run(studio.live_join_dialog), actions)
        overview.addLayout(actions)
        overview.addWidget(note('Host a shared schematic and layout on your network with automatic encrypted setup. To join, paste the complete invitation your teammate sent you.'))
        from .network_collaboration import network_host
        self.network_host = network_host(studio)
        self.network_status = note('')
        self.network_status.setAccessibleName('Network hosting status')
        overview.addWidget(self.network_status)
        network_actions = QHBoxLayout()
        self.network_stop = button('Stop network server', self.network_host.stop, network_actions)
        overview.addLayout(network_actions)
        self.network_host.changed.connect(self.refresh_network)
        from .local_collaboration import local_host
        self.local_host = local_host(studio)
        local_group = QGroupBox('Start on this computer')
        local_layout = QVBoxLayout(local_group)
        local_layout.addWidget(note('Start the included server without commands or copying a key. Sessions are available only on this computer. For teammates on other computers, use a team HTTPS server.'))
        self.local_status = note('Server stopped. Saved workspaces are kept when you stop or close the app.')
        self.local_status.setAccessibleName('Local collaboration server status')
        local_layout.addWidget(self.local_status)
        local_actions = QHBoxLayout()
        self.local_start = button('Start local server', lambda: self.run(lambda: studio.live_share_dialog(local=True)), local_actions, True)
        self.local_stop = button('Stop local server', self.local_host.stop, local_actions)
        local_layout.addLayout(local_actions)
        overview.addWidget(local_group)
        self.local_host.changed.connect(self.refresh_local)
        recent_header = QHBoxLayout()
        recent_header.addWidget(note('Recent workspaces'))
        recent_header.addStretch()
        self.refresh_button = button('Refresh list', self.refresh_recent, recent_header)
        overview.addLayout(recent_header)
        self.recent = QListWidget()
        self.recent.setAccessibleName('Recent collaboration workspaces')
        self.recent.setMinimumHeight(130)
        self.recent.itemDoubleClicked.connect(lambda *_: self.resume_selected())
        self.recent.currentItemChanged.connect(lambda *_: self.update_recent_actions())
        overview.addWidget(self.recent, 1)
        self.empty_recent = note('No recent workspaces yet\nShare a project or join with an invitation to get started.')
        self.empty_recent.setAlignment(Qt.AlignCenter)
        self.empty_recent.setMinimumHeight(130)
        overview.addWidget(self.empty_recent, 1)
        self.empty_recent.hide()
        row = QHBoxLayout()
        self.resume_button = button('Resume workspace', self.resume_selected, row, True)
        self.recover_button = button('Recover owner access…', self.recover_selected, row)
        overview.addLayout(row)
        self.recent_note = note('Loading your saved workspaces…')
        overview.addWidget(self.recent_note)
        self.tabs.addTab(scrolling_page(self.overview), 'Start and resume')

        self.session_page = QWidget()
        session_layout = QVBoxLayout(self.session_page)
        self.session_empty = note('Share or join a workspace to see your teammates, invitations, and shared edits here.')
        session_layout.addWidget(self.session_empty)
        self.session_scroll = QScrollArea()
        self.session_scroll.setWidgetResizable(True)
        self.session_scroll.setWidget(studio.live_session_widget)
        session_layout.addWidget(self.session_scroll, 1)
        self.tabs.addTab(self.session_page, 'Live workspace')

        folder_page = QWidget()
        folder_layout = QVBoxLayout(folder_page)
        folder_layout.setSpacing(12)
        folder_layout.addWidget(note('Shared-folder workspaces'))
        folder_layout.addWidget(note('Use a folder your team can access on a filesystem with reliable file locking. Claim cells or layers, then publish your changes and refresh to receive others’ work. Cloud-sync folders are unsupported.'))
        self.folder_status = note('You have not joined a shared folder.')
        folder_layout.addWidget(self.folder_status)
        row = QHBoxLayout()
        self.folder_create = button('Create shared folder…', lambda: self.run(lambda: studio.shared_layout_start(True)), row)
        self.folder_join = button('Join shared folder…', lambda: self.run(lambda: studio.shared_layout_start(False)), row)
        folder_layout.addLayout(row)
        self.folder_active = QGroupBox('Your shared-folder session')
        folder_actions = QVBoxLayout(self.folder_active)
        for title, fn in [('Cells, layers & ownership…', studio.shared_layout_dialog),
                          ('Publish my changes', studio.shared_layout_publish),
                          ('Get shared changes', studio.shared_layout_refresh),
                          ('Leave shared folder', studio.shared_layout_leave)]:
            button(title, lambda checked=False, fn=fn: self.run(fn), folder_actions)
        folder_layout.addWidget(self.folder_active)
        folder_layout.addStretch()
        self.tabs.addTab(scrolling_page(folder_page), 'Shared folder')
        from .team_review_ui import TeamReviewPanel
        self.review_panel=TeamReviewPanel(studio,self)
        self.tabs.addTab(scrolling_page(self.review_panel),'Team review')
        footer = QHBoxLayout()
        button('Setup and help', lambda: studio.open_editor_doc('LIVE_COLLABORATION.md'), footer)
        footer.addStretch()
        button('Back to design', self.hide, footer)
        root.addLayout(footer)
        self.refresh_state()
        self.refresh_recent()

    def run(self, callback):
        self.studio.guard(callback)
        self.refresh_state()

    def refresh_state(self):
        s = self.studio
        client = s.live_client
        active = client is not None or s.layout_session is not None
        self.share.setEnabled(not active)
        self.join.setEnabled(not active)
        self.folder_create.setEnabled(not active)
        self.folder_join.setEnabled(not active)
        self.session_empty.setVisible(not client)
        self.session_scroll.setVisible(bool(client))
        self.folder_active.setVisible(s.layout_session is not None)
        if client:
            self.summary.setText(s.project['name'] + ' · ' + client.message)
        elif s.layout_session:
            self.summary.setText(s.project['name'] + ' · Shared-folder workspace')
        else:
            self.summary.setText('Share a project, join your team, or pick up where you left off.')
        self.folder_status.setText('Connected as ' + s.layout_session.editor + '\n' + str(s.layout_session.root)
                                   if s.layout_session else 'You have not joined a shared folder.')
        self.update_recent_actions()
        self.review_panel.refresh_state()
        self.refresh_local()
        self.refresh_network()

    def refresh_network(self):
        host = self.network_host
        self.network_status.setVisible(host.state != 'stopped' or bool(host.error))
        self.network_stop.setVisible(host.state in ('running', 'stopping'))
        active = any(getattr(w, 'live_client', None) and w.live_client.server == host.url for w in QApplication.topLevelWidgets())
        self.network_stop.setEnabled(host.state == 'running' and not active)
        self.network_stop.setToolTip('Leave hosted workspaces in this application before stopping. Saved workspaces are retained.')
        if host.error:
            self.network_status.setText(host.error.replace('local server', 'network server'))
        elif host.state == 'running':
            self.network_status.setText('Encrypted network hosting at ' + host.url + '. Keep this app open; use Join a workspace on the other computer to check its connection.')
        else:
            self.network_status.setText('Preparing encrypted network hosting…' if host.state == 'starting' else 'Stopping network hosting…')

    def refresh_local(self):
        host = self.local_host
        active = self.studio.live_client is not None or self.studio.layout_session is not None
        self.local_start.setEnabled(not active and host.state not in ('starting', 'stopping'))
        self.local_start.setText('Share from this computer…' if host.state == 'running' else 'Starting…' if host.state == 'starting' else 'Start local server')
        self.local_stop.setVisible(host.state in ('running', 'stopping'))
        using_host = any(getattr(w, 'live_client', None) and w.live_client.server == host.url
                         for w in QApplication.topLevelWidgets())
        self.local_stop.setEnabled(host.state == 'running' and not using_host)
        self.local_stop.setToolTip('Leave local workspaces before stopping the server.' if using_host else 'Stop hosting; keep saved workspaces.')
        if host.error:
            message = host.error
        elif host.state == 'running':
            message = 'Running at ' + host.url + ' · This computer only. Keep IC Design Studio open to host. Saved workspaces can be resumed after restarting.'
        elif host.state == 'starting':
            message = 'Starting the included server and preparing your saved workspaces…'
        elif host.state == 'stopping':
            message = 'Stopping after accepted requests finish…'
        else:
            message = 'Server stopped. Saved workspaces are kept when you stop or close the app.'
        self.local_status.setText(message)

    def refresh_recent(self):
        if self.scan and self.scan.isRunning():
            return
        self.refresh_button.setEnabled(False)
        if self.scan is None:
            self.scan = SessionScan(self.studio.data_dir / 'live-sessions', self)
            self.scan.ready.connect(self.install_recent)
            self.scan.finished.connect(lambda: self.refresh_button.setEnabled(True))
        self.scan.start()

    def install_recent(self, records):
        selected = self.selected_record()
        self.recent.clear()
        self.recent.setVisible(bool(records))
        self.empty_recent.setVisible(not records)
        for record in records:
            when = datetime.fromtimestamp(record['modified']).strftime('%d %b, %H:%M') if record['modified'] else ''
            state = ' · Unsynced work retained' if record['attention'] else ''
            item = QListWidgetItem(record['name'] + state + '\n' +
                                   ' · '.join(x for x in (record['editor'], record['role'].title(), record['server'], when) if x))
            item.setData(Qt.UserRole, record)
            self.recent.addItem(item)
            if selected and selected['path'] == record['path']:
                self.recent.setCurrentItem(item)
        if not self.recent.currentItem() and records:
            self.recent.setCurrentRow(0)
        self.recent_note.setText('Choose a workspace and select Resume. Your saved edits and personal undo travel with the session.' if records
                                else 'Your shared workspaces will appear here automatically. Start with Share or Join above.')
        self.update_recent_actions()

    def selected_record(self):
        item = self.recent.currentItem()
        return item.data(Qt.UserRole) if item else None

    def update_recent_actions(self):
        if not hasattr(self, 'resume_button'):
            return
        record = self.selected_record()
        available = not (self.studio.live_client or self.studio.layout_session)
        self.resume_button.setEnabled(bool(record) and available)
        self.recover_button.setEnabled(bool(record and record['role'] == 'owner') and available)
        self.recover_button.setVisible(bool(record and record['role'] == 'owner'))

    def resume_selected(self):
        record = self.selected_record()
        if record:
            self.run(lambda: self.studio.live_resume_path(record['path']))

    def recover_selected(self):
        record = self.selected_record()
        if record:
            self.run(lambda: self.studio.live_recover_owner(record['path']))

    def done(self, result):
        # Closing the dashboard leaves the live editing session running.
        self.hide()


def fill_reservations(studio):
    tree = studio.live_reservations
    rows = reservation_rows(studio.project, studio.live_client.info, time.time())
    values = [(r['cell'], r['scope'], r['owner'], str(r['seconds']) + ' s') for r in rows]
    if values == getattr(tree, '_last_values', None):
        return
    tree._last_values = values
    tree.clear()
    for row in values:
        tree.addTopLevelItem(QTreeWidgetItem(row))
    studio.live_reservation_note.setText('Reservations renew while selected. Choose another object or wait for your teammate to release it.' if rows
                                         else 'No objects are reserved. Your team can edit different objects at the same time.')
