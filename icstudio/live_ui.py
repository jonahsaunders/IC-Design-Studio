"""Share/join controls, participant presence and recovery for desktop live layouts."""
import hashlib
import json
from pathlib import Path
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QPen, QPolygonF
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog,
    QFormLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QSpinBox, QVBoxLayout, QWidget, QTreeWidget, QMessageBox, QHBoxLayout)

from .live_client import LiveClient, LiveHistory, Transport, check_session
from .live_protocol import ID, PROTOCOL, LiveError, invitation_link, parse_invitation_details, server_url
from .model import History, clone, digest, save_project

COLORS = ['#64dfc0', '#ffba73', '#bca5ff', '#f18bbb', '#7bbfff', '#d5db75']


def person_color(ident):
    return COLORS[int(hashlib.sha256(ident.encode()).hexdigest()[:8], 16) % len(COLORS)]


def paint_presence(canvas, painter):
    if not canvas.cell:
        return
    painter.save()
    painter.resetTransform()
    scene = canvas.cell.get('_layout_scene')
    for person in getattr(canvas, 'live_presence', []):
        if person.get('view', 'layout') != canvas.mode or person.get('cell') != canvas.cell['id'] or person.get('seen', 0) < time.time() - 20:
            continue
        color = QColor(person.get('color', person_color(person['id'])))
        pen = QPen(color, 2)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        if canvas.mode == 'schematic':
            selected = set(person.get('selection', []))
            for obj in [*canvas.cell['devices'], *canvas.cell.get('wires', []), *canvas.cell.get('labels', []), *canvas.cell.get('annotations', []), *canvas.cell.get('buses', [])]:
                if obj['id'] in selected:
                    b = canvas.bounds(obj)
                    painter.drawRect(QRectF(b.left()*canvas.scale+canvas.offset.x(), b.top()*canvas.scale+canvas.offset.y(), b.width()*canvas.scale, b.height()*canvas.scale).adjusted(-3,-3,3,3))
        elif scene:
            for ident in person.get('selection', [])[:100]:
                if ident not in scene.sources and ident not in scene.instances:
                    continue
                b = scene.owner_bounds(ident)
                rect = QRectF(b.left * canvas.scale + canvas.offset.x(), b.bottom * canvas.scale + canvas.offset.y(),
                              b.width() * canvas.scale, b.height() * canvas.scale).adjusted(-3, -3, 3, 3)
                painter.drawRect(rect)
        else:
            selected = set(person.get('selection', [])[:100])
            for shape in canvas.cell.get('shapes', []):
                if shape['id'] in selected:
                    b = canvas.bounds(shape)
                    rect = QRectF(b.left() * canvas.scale + canvas.offset.x(), b.top() * canvas.scale + canvas.offset.y(),
                                  b.width() * canvas.scale, b.height() * canvas.scale).adjusted(-3, -3, 3, 3)
                    painter.drawRect(rect)
        point = person.get('cursor')
        if point is not None:
            x, y = point[0] * canvas.scale + canvas.offset.x(), point[1] * canvas.scale + canvas.offset.y()
            painter.setPen(QPen(color, 1))
            painter.setBrush(color)
            painter.drawPolygon(QPolygonF([QPointF(x, y), QPointF(x + 4, y + 15), QPointF(x + 8, y + 9), QPointF(x + 15, y + 7)]))
            painter.setFont(QFont('Sans Serif', 10))
            painter.drawText(QPointF(x + 18, y + 16), person['name'])
    painter.restore()


class LiveCollaborationMixin:
    def make_ui(self):
        self.live_client = None
        super().make_ui()
        self.live_transport = Transport(self)
        self._collaboration_dashboard = None
        host = self.live_session_widget = QWidget(self)
        host.hide()
        v = QVBoxLayout(host)
        self.live_status = QLabel('No live session')
        self.live_status.setWordWrap(True)
        self.live_status.setAccessibleName('Live connection status')
        v.addWidget(self.live_status)
        self.live_impact = QLabel('Schematic and layout share one revision. Recheck verification after changing the design.')
        self.live_impact.setWordWrap(True);self.live_impact.setAccessibleName('Shared design verification status');v.addWidget(self.live_impact)
        checks = QHBoxLayout()
        erc = QPushButton('Check schematic');erc.clicked.connect(lambda: self.guard(lambda: self.check('ERC')));checks.addWidget(erc)
        workflow = QPushButton('Review schematic and layout');workflow.clicked.connect(lambda: self.guard(self.design_workflow));checks.addWidget(workflow)
        v.addLayout(checks)
        self.live_recover_button = QPushButton('Recover owner access…')
        self.live_recover_button.clicked.connect(lambda: self.guard(lambda: self.live_recover_owner()))
        v.addWidget(self.live_recover_button)
        self.live_recover_button.hide()
        top_actions = QHBoxLayout()
        self.live_manage_button = QPushButton('Invite people and manage access…')
        self.live_manage_button.setProperty('role', 'primary')
        self.live_manage_button.clicked.connect(lambda: self.guard(self.live_manage_access))
        top_actions.addWidget(self.live_manage_button)
        leave = QPushButton('Leave workspace')
        leave.setToolTip('Keep the displayed design as an independent local copy')
        leave.clicked.connect(lambda: self.guard(self.live_leave))
        top_actions.addWidget(leave)
        v.addLayout(top_actions)
        activity = QHBoxLayout()
        people = QVBoxLayout()
        people.addWidget(QLabel('Your teammates'))
        self.live_people = QListWidget()
        self.live_people.itemDoubleClicked.connect(lambda item: self.guard(lambda: self.live_go_to_person(item)))
        self.live_people.setAccessibleName('Live participants')
        self.live_people.setMinimumHeight(80)
        self.live_people.setMaximumHeight(120)
        people.addWidget(self.live_people)
        activity.addLayout(people, 1)
        edits = QVBoxLayout()
        edits.addWidget(QLabel('Recent shared edits'))
        self.live_history = QListWidget()
        self.live_history.setAccessibleName('Shared edit history')
        self.live_history.setMinimumHeight(80)
        self.live_history.setMaximumHeight(120)
        edits.addWidget(self.live_history)
        activity.addLayout(edits, 2)
        v.addLayout(activity)
        v.addWidget(QLabel('Reserved objects'))
        self.live_reservations = QTreeWidget()
        self.live_reservations.setHeaderLabels(['Cell', 'Reserved scope', 'Reserved by', 'Renews in'])
        self.live_reservations.setAccessibleName('Object reservations and their owners')
        self.live_reservations.setRootIsDecorated(False)
        self.live_reservations.setMinimumHeight(90)
        self.live_reservations.setMaximumHeight(140)
        self.live_reservations.setColumnWidth(1, 260)
        v.addWidget(self.live_reservations)
        self.live_reservation_note = QLabel()
        self.live_reservation_note.setWordWrap(True)
        v.addWidget(self.live_reservation_note)
        self.live_manage = QDialog(self)
        self.live_manage.setWindowTitle('Invite people and manage access')
        self.live_manage.resize(560, 480)
        management = QVBoxLayout(self.live_manage)
        self.live_owner = QWidget(self.live_manage)
        management.addWidget(self.live_owner)
        ov = QVBoxLayout(self.live_owner)
        ov.setContentsMargins(0, 0, 0, 0)
        invitation_note = self.live_invitation_note = QLabel('Choose what your teammate can do, then copy an invitation to send them. You can revoke access here at any time.')
        invitation_note.setWordWrap(True)
        ov.addWidget(invitation_note)
        form = QFormLayout()
        self.live_role = QComboBox()
        self.live_role.addItem('Can view', 'view')
        self.live_role.addItem('Can review · comment and approve', 'review')
        self.live_role.addItem('Can edit', 'edit')
        self.live_days = QSpinBox()
        self.live_days.setRange(1, 30)
        self.live_days.setValue(7)
        form.addRow('Invitation permission', self.live_role)
        form.addRow('Expires in days', self.live_days)
        ov.addLayout(form)
        invite = QPushButton('Create and copy invitation')
        invite.clicked.connect(lambda: self.guard(self.live_invite))
        ov.addWidget(invite)
        self.live_invitations = QListWidget()
        self.live_invitations.setAccessibleName('Revocable invitations')
        self.live_invitations.setMinimumHeight(80)
        self.live_invitations.setMaximumHeight(120)
        ov.addWidget(self.live_invitations)
        revoke = QPushButton('Revoke selected invitation')
        revoke.clicked.connect(lambda: self.guard(self.live_revoke))
        ov.addWidget(revoke)
        self.live_review = QPushButton('Review conflicting edit…')
        self.live_review.setProperty('role', 'primary')
        self.live_review.clicked.connect(lambda: self.guard(self.live_review_conflict))
        v.addWidget(self.live_review)
        self.live_copy = QPushButton('Save retained conflicting edit…')
        self.live_copy.clicked.connect(lambda: self.guard(self.live_save_conflict))
        v.addWidget(self.live_copy)
        self.live_discard = QPushButton('Use shared version…')
        self.live_discard.clicked.connect(lambda: self.guard(self.live_confirm_discard))
        v.addWidget(self.live_discard)
        self.live_delete = QPushButton('Save a copy and delete workspace…')
        self.live_delete.clicked.connect(lambda: self.guard(self.live_delete_workspace))
        ov.addWidget(self.live_delete)
        close_manage = QPushButton('Done')
        close_manage.clicked.connect(self.live_manage.hide)
        management.addWidget(close_manage)
        self.collaboration_button = QPushButton('Collaboration')
        self.collaboration_button.setToolTip('Open Tools → Collaboration')
        self.collaboration_button.clicked.connect(lambda: self.guard(self.collaboration_dashboard))
        self.statusBar().addPermanentWidget(self.collaboration_button)

    def make_actions(self):
        super().make_actions()
        self.collaboration_action = self.action(self.task_menus['Tools'], 'Collaboration…', self.collaboration_dashboard)
        self.reindex_commands()

    def collaboration_dashboard(self, tab=None):
        from .collaboration_dashboard import CollaborationDashboard
        if self._collaboration_dashboard is None:
            self._collaboration_dashboard = CollaborationDashboard(self)
        dlg = self._collaboration_dashboard
        dlg.refresh_state()
        if tab is not None:
            dlg.tabs.setCurrentIndex(tab)
        dlg.refresh_recent()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

    def live_show(self):
        return self.collaboration_dashboard(1 if self.live_client else 0)

    def live_manage_access(self):
        if not self.live_client or self.live_client.info['role'] != 'owner':
            raise LiveError('Only the workspace owner can manage invitations.')
        self.live_manage.show()
        self.live_manage.raise_()
        return self.live_manage

    def shared_layout_start(self, create):
        if self.live_client:
            raise LiveError('Leave the live session before joining a shared-folder workspace.')
        return super().shared_layout_start(create)

    def set_project(self, p, path=None):
        if getattr(self, 'live_client', None):
            self.live_leave()
        return super().set_project(p, path)

    def closeEvent(self, event):
        super().closeEvent(event)
        if event.isAccepted() and self.live_client:
            self.live_leave()
        if event.isAccepted() and self._collaboration_dashboard:
            scan = self._collaboration_dashboard.scan
            if scan and scan.isRunning():
                scan.requestInterruption()
                scan.wait()

    def live_available(self):
        if self.live_client or self.layout_session:
            raise LiveError('Leave the current collaboration session before starting another.')
        if not self.idle_edit():
            return False
        return True

    def live_share_dialog(self, local=False):
        if self.live_client:
            return self.live_show()
        if not self.live_available():
            return
        dlg = QDialog(self)
        dlg.setWindowTitle('Share this project')
        dlg.resize(570, 300)
        v = QVBoxLayout(dlg)
        note = QLabel('Share this project through your team’s server. Teammates can edit schematics and layouts, review changes, and share results. Everyone needs the current collaboration update. PDK settings stay fixed.')
        note.setWordWrap(True)
        v.addWidget(note)
        from .local_collaboration import local_host
        host = local_host(self)
        local_mode = False
        setup = QHBoxLayout()
        local_button = QPushButton('Start local server')
        local_button.setObjectName('startLocalServer')
        team_button = QPushButton('Use a team server')
        team_button.hide()
        setup.addWidget(local_button)
        setup.addWidget(team_button)
        network_button = QPushButton('Host a session…')
        network_button.clicked.connect(lambda: (dlg.reject(), self.host_session_dialog()))
        setup.addWidget(network_button)
        v.addLayout(setup)
        form = QFormLayout()
        server = QLineEdit(str(self.settings.value('live/server', 'http://127.0.0.1:8765')))
        key = QLineEdit()
        key.setEchoMode(QLineEdit.Password)
        name = QLineEdit(str(self.settings.value('live/name', '')))
        form.addRow('Server URL', server)
        form.addRow('Workspace creation key', key)
        form.addRow('Your name', name)
        v.addLayout(form)
        error = QLabel()
        error.setWordWrap(True)
        error.setTextFormat(Qt.PlainText)
        v.addWidget(error)
        button = QPushButton('Start sharing')
        v.addWidget(button)
        check_button = QPushButton('Check server connection')
        v.addWidget(check_button)
        def check_server():
            try:
                self.live_check_server(server_url(server.text()), '', check_button, error)
            except Exception as exc:
                error.setText(str(exc))
        check_button.clicked.connect(check_server)

        def update_local():
            local_button.setEnabled(host.state not in ('starting', 'stopping'))
            local_button.setText('Use local server' if host.state == 'running' else 'Starting…' if host.state == 'starting' else 'Start local server')
            if not local_mode:
                return
            button.setEnabled(host.state == 'running')
            if host.state == 'running':
                server.setText(host.url)
                key.setText(host.key)
                error.setText('Ready. Enter your name and choose Start sharing. Invitations work only on this computer.')
            else:
                key.clear()
                error.setText(host.error or ('Starting the included server…' if host.state == 'starting' else 'Local server stopped. Choose Start local server to continue.'))

        def choose_local():
            nonlocal local_mode
            local_mode = True
            server.setReadOnly(True)
            key.setReadOnly(True)
            form.setRowVisible(key, False)
            team_button.show()
            note.setText('Host on this computer with automatic setup. Keep IC Design Studio open while hosting. Workspaces are saved for next time. Other computers need a team HTTPS server.')
            host.start()
            update_local()
            name.setFocus()

        def choose_team():
            nonlocal local_mode
            local_mode = False
            key.clear()
            server.clear()
            server.setPlaceholderText('https://your-team-server')
            server.setReadOnly(False)
            key.setReadOnly(False)
            form.setRowVisible(key, True)
            team_button.hide()
            note.setText('Use the HTTPS address and workspace creation key supplied by your team’s server administrator.')
            error.clear()
            button.setEnabled(True)
            server.setFocus()

        # Never carry the automatically supplied key to a different endpoint.
        def address_changed():
            if local_mode and server.text() != host.url:
                key.clear()
        server.textChanged.connect(address_changed)
        local_button.clicked.connect(choose_local)
        team_button.clicked.connect(choose_team)
        host.changed.connect(update_local)
        dlg.finished.connect(lambda *_: host.changed.disconnect(update_local))

        def start():
            try:
                url = server_url(server.text())
                if local_mode and (host.state != 'running' or url != host.url):
                    raise LiveError('Start the local server before sharing.')
                if not name.text().strip():
                    name.setFocus()
                    raise LiveError('Enter your name so teammates can recognize you.')
                if len(key.text()) < 32:
                    raise LiveError('Enter the creation key supplied by your server administrator.')
                if not self.flush_inspector():
                    return
                self.live_connect(url, '/v2/workspaces', key.text(), dict(project=clone(self.project), name=name.text()), dlg, button, error)
            except Exception as exc:
                error.setText(str(exc))
        button.clicked.connect(start)
        dlg.show()
        self._live_connect_dialog = dlg
        if local:
            choose_local()
        return dlg

    def live_join_dialog(self, link=''):
        if not self.live_available():
            return
        dlg = QDialog(self)
        dlg.setWindowTitle('Join a workspace')
        dlg.resize(570, 240)
        v = QVBoxLayout(dlg)
        form = QFormLayout()
        invitation = QLineEdit(link if isinstance(link, str) else '')
        invitation.setEchoMode(QLineEdit.Password)
        name = QLineEdit(str(self.settings.value('live/name', '')))
        form.addRow('Invitation link', invitation)
        form.addRow('Your name', name)
        v.addLayout(form)
        error = QLabel('Joining downloads the project and opens a shared schematic and layout session.')
        error.setWordWrap(True)
        v.addWidget(error)
        button = QPushButton('Join workspace')
        v.addWidget(button)
        check_button = QPushButton('Check connection first')
        v.addWidget(check_button)
        def check():
            try:
                server, _, _, certificate = parse_invitation_details(invitation.text())
                self.live_check_server(server, certificate, check_button, error)
            except Exception as exc:
                error.setText(str(exc))
        check_button.clicked.connect(check)

        def join():
            try:
                server, wid, secret, certificate = parse_invitation_details(invitation.text())
                if not self.maybe_save():
                    return
                self.live_connect(server, '/v2/workspaces/' + wid + '/join', '', dict(invite=secret, name=name.text()), dlg, button, error, certificate=certificate)
            except Exception as exc:
                error.setText(str(exc))
        button.clicked.connect(join)
        dlg.show()
        self._live_connect_dialog = dlg
        return dlg

    def host_session_dialog(self):
        from .network_host_ui import HostSessionDialog
        if not self.live_available():
            return
        previous = getattr(self, '_host_session_dialog', None)
        if previous:
            previous.close()
        self._host_session_dialog = HostSessionDialog(self)
        self._host_session_dialog.show()
        return self._host_session_dialog

    def live_check_server(self, server, certificate, button, message, completed=None):
        button.setEnabled(False)
        message.setText('Checking the connection from this computer…')
        def done(status, result):
            button.setEnabled(True)
            good = status == 200 and result.get('service') == 'IC Design Studio' and result.get('protocol') == PROTOCOL
            message.setText('Connection verified from this computer. You can join or share now.' if good else result.get('error', 'This address did not return a compatible IC Design Studio server. Check the address and server version.'))
            if completed:
                completed(good)
        try:
            self.live_transport.post(server, '/v2/check', '', {}, done, certificate=certificate)
        except Exception:
            button.setEnabled(True)
            raise

    def live_connect(self, server, path, token, body, dlg, button, error, certificate='', on_connected=None):
        original = digest(self.project)
        button.setEnabled(False)
        error.setText('Connecting…')

        def done(status, snapshot):
            button.setEnabled(True)
            if status != 200:
                error.setText(snapshot.get('error', 'Could not connect.'))
                return
            try:
                client = self.live_new_client(server, snapshot, certificate)
                if self.live_client or digest(self.project) != original:
                    client.active = False
                    error.setText('Your open project changed while connecting. The session is saved; use Resume saved live session to open it.')
                    return
                self.settings.setValue('live/server', server)
                self.settings.setValue('live/name', snapshot['name'])
                self.live_attach(client)
                if on_connected:
                    on_connected(client)
                else:
                    dlg.accept()
            except Exception as exc:
                error.setText(str(exc))
        self.live_transport.post(server, path, token, body, done, certificate=certificate)

    def live_new_client(self, server, snapshot, certificate=''):
        check_session(snapshot['workspace'], snapshot['token'], snapshot)
        path = self.data_dir / 'live-sessions' / (snapshot['workspace'] + '-' + snapshot['actor'] + '.json')
        return LiveClient(server, snapshot['workspace'], snapshot['token'], snapshot, path, self, server_certificate=certificate)

    def live_attach(self, client):
        self.set_project(clone(client.project))
        self.live_client = client
        self.history = LiveHistory(client)
        self._live_schematic_state = {}
        client.presence = self.live_presence_data
        client.can_install = self.live_can_install
        client.changed.connect(self.live_document_changed)
        client.status_changed.connect(self.live_update_panel)
        self.live_document_changed()
        self.live_show()
        client.start()

    def live_presence_data(self):
        canvas = self.schematic if self.mode_combo.currentIndex() == 0 else self.layout
        pos = canvas.mapFromGlobal(QCursor.pos())
        point = canvas.model(QPointF(pos)) if canvas.rect().contains(pos) else None
        return dict(cell=self.cid, view=canvas.mode, selection=[s.removeprefix('pin:') for s in self.selection if isinstance(s, str) and ID.fullmatch(s.removeprefix('pin:'))][:100],
                    cursor=[point.x(), point.y()] if point is not None else None)

    def live_can_install(self):
        if any(dialog.isVisible() and dialog.windowModality() != Qt.NonModal
               for dialog in self.findChildren(QDialog)):
            return False  # A symbol/settings dialog must commit against its starting revision.
        return not getattr(self, '_inspector_dirty', False) and not any(
            canvas.anchor is not None or canvas.drawing or canvas._rect_pending or canvas.moving
            or canvas.wire_points or canvas.wire_drag or canvas.placement
            for canvas in (self.schematic, self.layout))

    def live_go_to_person(self, item):
        person = item.data(Qt.UserRole)
        if not person or not self.flush_inspector(): return
        if not self.live_can_install():
            self.statusBar().showMessage('Finish or cancel your current edit before visiting a teammate.', 8000)
            return
        if person['cell'] not in {c['id'] for c in self.project['cells']}: return
        self.cid = person['cell']; self.selection = []
        self.mode_combo.setCurrentIndex(0 if person.get('view') == 'schematic' else 1)
        self.refresh(True)
        canvas = self.schematic if person.get('view') == 'schematic' else self.layout
        if person.get('cursor'):
            canvas.auto_fit = False
            canvas.offset = QPointF(canvas.width()/2, canvas.height()/2) - QPointF(*person['cursor'])*canvas.scale
            canvas.update()
        if self._collaboration_dashboard: self._collaboration_dashboard.hide()

    def live_document_changed(self):
        if not self.live_client:
            return
        from .collaboration_document import SCHEMATIC_FIELDS
        state = {c['id']: digest({k:v for k,v in c.items() if k in set(SCHEMATIC_FIELDS)|{'ports','symbol','parameters'}}) for c in self.project['cells']}
        previous = getattr(self, '_live_schematic_state', {})
        if previous and state != previous:
            names = [c['name'] for c in self.project['cells'] if previous.get(c['id']) != state[c['id']]]
            self.live_impact.setText('Schematic updated: ' + (', '.join(names[:4]) or 'cell removed') + '. Review electrical checks and linked layout; previous verification may need to be rerun.')
        self._live_schematic_state = state
        self.refresh()
        self.save_recovery()
        self.live_update_panel(self.live_client.message)

    def live_update_panel(self, message):
        client = self.live_client
        if not client:
            return
        self.live_status.setText(message)
        from urllib.parse import urlsplit
        local = urlsplit(client.server).hostname in ('127.0.0.1', 'localhost', '::1')
        self.live_invitation_note.setText('This workspace is available only on this computer. Invitations can join from another IC Design Studio window here. For other computers, share through a team HTTPS server.' if local else 'Choose what your teammate can do, then copy an invitation to send them. You can revoke access here at any time.')
        self.collaboration_button.setText('Collaboration · ' + ('Needs review' if client.conflict else 'Connected' if client.connected else 'Reconnecting'))
        self.live_recover_button.setVisible(client.info['role'] == 'owner' and not client.connected)
        self.live_people.clear()
        people = client.info.get('participants', [])
        cells = {c['id']: c['name'] for c in self.project['cells']}
        for p in people:
            item = QListWidgetItem(p['name'] + ' · ' + p.get('view', 'layout').title() + ' · ' + cells.get(p['cell'], '') + ' · ' + p['role'] + (' · you' if p['id'] == client.info['actor'] else ''))
            item.setData(Qt.UserRole, p)
            item.setToolTip('Double-click to visit this teammate’s view')
            item.setForeground(QColor(p.get('color', person_color(p['id']))))
            self.live_people.addItem(item)
        self.layout.live_presence = [p for p in people if p['id'] != client.info['actor']]
        self.schematic.live_presence = self.layout.live_presence
        self.schematic.update()
        self.layout.update()
        self.live_history.clear()
        for event in client.info.get('history', []):
            self.live_history.addItem(str(event['revision']) + ' · ' + event['name'] + ' · ' + event['label'])
        self.live_owner.setVisible(client.info['role'] == 'owner')
        self.live_manage_button.setVisible(client.info['role'] == 'owner')
        current = self.live_invitations.currentItem()
        selected = current.data(Qt.UserRole) if current else None
        self.live_invitations.clear()
        for inv in client.info.get('invitations', []):
            state = 'revoked' if inv['revoked'] else 'expired' if inv['expires'] <= time.time() else 'active'
            item = QListWidgetItem(inv['role'] + ' · ' + state + ' · ' + inv['id'][:8])
            item.setData(Qt.UserRole, inv['id'])
            self.live_invitations.addItem(item)
            if inv['id'] == selected:
                self.live_invitations.setCurrentItem(item)
        self.live_copy.setVisible(bool(client.conflict and client.conflict.get('proposed')))
        self.live_discard.setVisible(bool(client.conflict))
        self.live_review.setVisible(bool(client.conflict and client.conflict.get('proposed')))
        self.live_review.setEnabled(not client.pending)
        self.live_copy.setEnabled(not client.pending)
        self.live_discard.setEnabled(not client.pending)
        self.live_delete.setVisible(client.info['role'] == 'owner')
        self.live_delete.setEnabled(client.connected and not client.pending and not client.conflict and not client.managing)
        from .collaboration_dashboard import fill_reservations
        fill_reservations(self)
        if self._collaboration_dashboard:
            self._collaboration_dashboard.refresh_state()
        editable = client.connected and client.info['role'] in ('owner', 'edit') and not client.pending and not client.conflict
        self.undo_action.setEnabled(editable and bool(client.info.get('undo')))
        self.redo_action.setEnabled(editable and bool(client.info.get('redo')))

    def live_invite(self):
        client = self.live_client
        if not client or client.info['role'] != 'owner':
            raise LiveError('Only the owner can create invitations.')
        def done(status, result):
            if status != 200:
                self.error(result.get('error', 'Invitation creation failed.'))
                return
            link = invitation_link(client.server, client.workspace, result['invite'], client.server_certificate)
            QApplication.clipboard().setText(link)
            self.statusBar().showMessage('Invitation copied · ' + result['role'] + ' permission', 15000)
            client.tick()
        client.transport.post(client.server, client.path + '/invite', client.token,
                              dict(role=self.live_role.currentData(), days=self.live_days.value()), done)

    def live_revoke(self):
        client, item = self.live_client, self.live_invitations.currentItem()
        if not client or item is None:
            raise LiveError('Select an invitation to revoke.')
        def done(status, result):
            if status != 200:
                self.error(result.get('error', 'Revocation failed.'))
            else:
                self.statusBar().showMessage('Invitation revoked; sessions using it can no longer access the workspace.', 15000)
                client.tick()
        client.transport.post(client.server, client.path + '/revoke', client.token, dict(invitation=item.data(Qt.UserRole)), done)

    def live_save_conflict(self):
        client = self.live_client
        if not client or client.pending or not client.conflict or not client.conflict.get('proposed'):
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save retained edit as an independent project', '', 'IC Studio project (*.icproj)')
        if path:
            save_project(client.conflict['proposed'], path)
            self.live_discard_conflict()

    def live_discard_conflict(self):
        client = self.live_client
        if client:
            if client.pending:
                raise LiveError('Wait for the reviewed edit to finish syncing before resolving this conflict.')
            retained = client.conflict
            client.conflict = None
            try:
                client.save_journal()
            except Exception:
                client.conflict = retained
                raise
            client.tick()
            self.live_update_panel(client.message)

    def live_confirm_discard(self):
        if QMessageBox.question(self, 'Use shared version?',
                'This discards your retained conflicting edit. Save a separate copy first if you want to keep it.',
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Yes:
            self.live_discard_conflict()

    def live_review_conflict(self):
        from .collaboration_review_ui import ConflictReview
        if not self.live_client or not self.live_client.conflict:
            raise LiveError('There is no conflicting edit to review.')
        previous = getattr(self, '_live_conflict_review', None)
        if previous:
            previous.close()
        dlg = ConflictReview(self)
        self._live_conflict_review = dlg
        dlg.show()
        return dlg

    def live_resume_dialog(self):
        return self.collaboration_dashboard(0)

    def live_resume_path(self, path):
        if self.live_available() and self.maybe_save():
            client = LiveClient.resume(path, self)
            from .local_collaboration import local_host
            host = local_host(self)
            from .network_collaboration import network_host
            network = network_host(self)
            network_owned = network.owns_url(client.server) and client.server_certificate and client.server_certificate == network.saved_certificate()
            original = digest(self.project)
            def attach():
                if self.isVisible() and not self.live_client and not self.layout_session and digest(self.project) == original:
                    if network_owned:
                        client.server = network.url
                        client.transport.origin = network.url
                        client.save_journal()
                    self.live_attach(client)
            if host.owns_url(client.server):
                host.start(attach)
            elif network_owned:
                network.resume_address()
                network.start(attach)
            else:
                attach()

    def live_recover_owner(self, path=None):
        client = self.live_client
        if path is not None:
            if not self.live_available() or not self.maybe_save():
                return
            client = LiveClient.resume(path, self)
        if client is None or client.info['role'] != 'owner':
            raise LiveError('Choose one of your owned workspaces to recover access.')
        if client.busy:
            raise LiveError('Wait for the current connection attempt to finish, then try again.')
        dlg = QDialog(self)
        dlg.setWindowTitle('Recover workspace ownership')
        dlg.resize(520, 240)
        layout = QVBoxLayout(dlg)
        note = QLabel('Restore access to ' + client.project['name'] + '. Ask your server administrator for the workspace creation key. Your saved edits and personal undo are preserved.')
        note.setWordWrap(True)
        note.setTextFormat(Qt.PlainText)
        layout.addWidget(note)
        key = QLineEdit()
        key.setEchoMode(QLineEdit.Password)
        key.setAccessibleName('Workspace creation key')
        from .local_collaboration import local_host
        host = local_host(self)
        if host.state == 'running' and client.server == host.url:
            key.setText(host.key)
            key.setReadOnly(True)
            note.setText('Restore access to ' + client.project['name'] + '. The local server key is supplied automatically. Your saved edits and personal undo are preserved.')
        from .network_collaboration import network_host
        network = network_host(self)
        if network.state == 'running' and client.server == network.url and client.server_certificate == network.certificate:
            key.setText(network.key);key.setReadOnly(True)
            note.setText('The host key is supplied automatically. Restore owner access to ' + client.project['name'] + ' while preserving saved edits and personal undo.')
        form = QFormLayout()
        form.addRow('Administrator key', key)
        layout.addLayout(form)
        error = QLabel()
        error.setWordWrap(True)
        error.setTextFormat(Qt.PlainText)
        layout.addWidget(error)
        restore = QPushButton('Restore owner access')
        layout.addWidget(restore)
        original = digest(self.project)
        def start():
            if client.busy:
                error.setText('A connection attempt is finishing. Please try again in a moment.')
                return
            client.busy = True
            restore.setEnabled(False)
            def completed(status, result):
                client.busy = False
                restore.setEnabled(True)
                if status != 200:
                    error.setText(result.get('error', 'Could not recover access.'))
                    return
                try:
                    check_session(client.workspace, result['token'], result)
                    if result['actor'] != client.info['actor'] or result['role'] != 'owner':
                        raise LiveError('The server returned a different owner identity.')
                    client.token = result['token']
                    client.save_journal()
                    if self.live_client is client:
                        client.active = True
                        client.start()
                    elif self.live_client is None and digest(self.project) == original:
                        self.live_attach(client)
                    else:
                        error.setText('Access restored. Resume this workspace from the dashboard when you are ready.')
                        return
                    dlg.accept()
                except Exception as exc:
                    error.setText(str(exc))
            try:
                client.transport.post(client.server, client.path + '/recover-owner', key.text(),
                                         dict(actor=client.info['actor']), completed)
            except Exception as exc:
                client.busy = False
                restore.setEnabled(True)
                error.setText(str(exc))
        restore.clicked.connect(start)
        self._live_recover_dialog = dlg
        dlg.show()
        return dlg

    def live_delete_workspace(self):
        client = self.live_client
        if not client or client.pending or client.conflict or not client.connected or client.info['role'] != 'owner':
            raise LiveError('Finish syncing and resolve retained edits before deleting your workspace.')
        if QMessageBox.question(self, 'Delete shared workspace?',
                'You will save a local copy first. The workspace and its shared history will then be permanently removed from the server, and everyone will lose access.',
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save a copy before deleting', '', 'IC Studio project (*.icproj)')
        if not path:
            return
        revision = client.revision
        save_project(client.project, path)
        client.managing = True
        self.live_update_panel(client.message)
        def completed(status, result):
            client.managing = False
            if status != 200:
                if self.live_client is client:
                    self.live_update_panel(client.message)
                self.error(result.get('error', 'Could not delete the workspace. Your local copy is saved.'))
                return
            if self.live_client is client:
                self.live_leave()
            client.journal.unlink(missing_ok=True)
            self.statusBar().showMessage('Shared workspace deleted. Your saved local copy is ready to open.', 12000)
            if self._collaboration_dashboard:
                self._collaboration_dashboard.refresh_recent()
        try:
            client.transport.post(client.server, client.path + '/delete', client.token, dict(revision=revision), completed)
        except Exception:
            client.managing = False
            raise

    def live_leave(self):
        client = self.live_client
        if client:
            client.stop()
            self.live_client = None
            self.history = History(clone(client.project))
            self.layout.live_presence = []
            self.schematic.live_presence = []
            self.schematic.update()
            self.collaboration_button.setText('Collaboration')
            self.live_manage.hide()
            self.refresh()
            if self._collaboration_dashboard:
                self._collaboration_dashboard.refresh_state()
                self._collaboration_dashboard.refresh_recent()
            self.statusBar().showMessage('Left live session. This local copy can be saved and edited independently.', 12000)
