"""Share/join controls, participant presence and recovery for desktop live layouts."""
import hashlib
import json
from pathlib import Path
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QPen, QPolygonF
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDockWidget, QFileDialog,
    QFormLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QSpinBox, QVBoxLayout, QWidget)

from .live_client import LiveClient, LiveHistory, Transport, check_session
from .live_protocol import ID, LiveError, invitation_link, parse_invitation, server_url
from .model import History, clone, digest, save_project

COLORS = ['#64dfc0', '#ffba73', '#bca5ff', '#f18bbb', '#7bbfff', '#d5db75']


def person_color(ident):
    return COLORS[int(hashlib.sha256(ident.encode()).hexdigest()[:8], 16) % len(COLORS)]


def paint_presence(canvas, painter):
    if canvas.mode != 'layout' or not canvas.cell:
        return
    painter.save()
    painter.resetTransform()
    scene = canvas.cell.get('_layout_scene')
    for person in getattr(canvas, 'live_presence', []):
        if person.get('cell') != canvas.cell['id'] or person.get('seen', 0) < time.time() - 20:
            continue
        color = QColor(person.get('color', person_color(person['id'])))
        pen = QPen(color, 2)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        if scene:
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
        self.live_dock = QDockWidget('LIVE COLLABORATION', self)
        self.live_dock.setObjectName('liveCollaboration')
        host = QWidget()
        v = QVBoxLayout(host)
        self.live_status = QLabel('No live session')
        self.live_status.setWordWrap(True)
        self.live_status.setAccessibleName('Live connection status')
        v.addWidget(self.live_status)
        self.live_people = QListWidget()
        self.live_people.setAccessibleName('Live participants')
        self.live_people.setMinimumHeight(96)
        self.live_people.setMaximumHeight(120)
        v.addWidget(self.live_people)
        self.live_history = QListWidget()
        self.live_history.setAccessibleName('Shared edit history')
        self.live_history.setMinimumHeight(96)
        self.live_history.setMaximumHeight(180)
        v.addWidget(self.live_history)
        self.live_owner = QWidget()
        ov = QVBoxLayout(self.live_owner)
        ov.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.live_role = QComboBox()
        self.live_role.addItem('Can view', 'view')
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
        v.addWidget(self.live_owner)
        self.live_copy = QPushButton('Save retained conflicting edit…')
        self.live_copy.clicked.connect(lambda: self.guard(self.live_save_conflict))
        v.addWidget(self.live_copy)
        self.live_discard = QPushButton('Discard retained conflicting edit')
        self.live_discard.clicked.connect(lambda: self.guard(self.live_discard_conflict))
        v.addWidget(self.live_discard)
        leave = QPushButton('Leave and keep local copy')
        leave.clicked.connect(lambda: self.guard(self.live_leave))
        v.addWidget(leave)
        self.live_dock.setWidget(host)
        self.live_dock.setMinimumWidth(320)
        self.addDockWidget(Qt.RightDockWidgetArea, self.live_dock)
        self.live_dock.hide()

    def make_actions(self):
        super().make_actions()
        menu = self.task_menus['Layout'].addMenu('Live collaboration')
        for title, fn in [('Share layout…', self.live_share_dialog), ('Join with invitation…', self.live_join_dialog),
                          ('Resume saved live session…', self.live_resume_dialog), ('Participants and sharing', self.live_show),
                          ('Leave and keep local copy', self.live_leave),
                          ('Server setup and collaboration guide', lambda: self.open_editor_doc('LIVE_COLLABORATION.md'))]:
            self.action(menu, title, fn)
        self.reindex_commands()

    def live_show(self):
        if not self.live_client:
            raise LiveError('Share a layout or join with an invitation first.')
        self.tabifyDockWidget(self.inspector, self.live_dock)
        self.live_dock.show()
        self.live_dock.raise_()

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

    def live_available(self):
        if self.live_client or self.layout_session:
            raise LiveError('Leave the current collaboration session before starting another.')
        if not self.idle_edit():
            return False
        return True

    def live_share_dialog(self):
        if self.live_client:
            return self.live_show()
        if not self.live_available():
            return
        dlg = QDialog(self)
        dlg.setWindowTitle('Share layout')
        dlg.resize(570, 300)
        v = QVBoxLayout(dlg)
        note = QLabel('Share a snapshot of this project through your collaboration server. Participants edit layout; schematic and PDK settings remain fixed during the session.')
        note.setWordWrap(True)
        v.addWidget(note)
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
        v.addWidget(error)
        button = QPushButton('Start sharing')
        v.addWidget(button)

        def start():
            try:
                url = server_url(server.text())
                if len(key.text()) < 32:
                    raise LiveError('Enter the creation key supplied by your server administrator.')
                if not self.flush_inspector():
                    return
                self.live_connect(url, '/v1/workspaces', key.text(), dict(project=clone(self.project), name=name.text()), dlg, button, error)
            except Exception as exc:
                error.setText(str(exc))
        button.clicked.connect(start)
        dlg.show()
        self._live_connect_dialog = dlg
        return dlg

    def live_join_dialog(self, link=''):
        if not self.live_available():
            return
        dlg = QDialog(self)
        dlg.setWindowTitle('Join live layout')
        dlg.resize(570, 240)
        v = QVBoxLayout(dlg)
        form = QFormLayout()
        invitation = QLineEdit(link if isinstance(link, str) else '')
        invitation.setEchoMode(QLineEdit.Password)
        name = QLineEdit(str(self.settings.value('live/name', '')))
        form.addRow('Invitation link', invitation)
        form.addRow('Your name', name)
        v.addLayout(form)
        error = QLabel('Joining downloads the project and opens a desktop layout session.')
        error.setWordWrap(True)
        v.addWidget(error)
        button = QPushButton('Join layout')
        v.addWidget(button)

        def join():
            try:
                server, wid, secret = parse_invitation(invitation.text())
                if not self.maybe_save():
                    return
                self.live_connect(server, '/v1/workspaces/' + wid + '/join', '', dict(invite=secret, name=name.text()), dlg, button, error)
            except Exception as exc:
                error.setText(str(exc))
        button.clicked.connect(join)
        dlg.show()
        self._live_connect_dialog = dlg
        return dlg

    def live_connect(self, server, path, token, body, dlg, button, error):
        original = digest(self.project)
        button.setEnabled(False)
        error.setText('Connecting…')

        def done(status, snapshot):
            button.setEnabled(True)
            if status != 200:
                error.setText(snapshot.get('error', 'Could not connect.'))
                return
            try:
                client = self.live_new_client(server, snapshot)
                if self.live_client or digest(self.project) != original:
                    client.active = False
                    error.setText('Your open project changed while connecting. The session is saved; use Resume saved live session to open it.')
                    return
                self.settings.setValue('live/server', server)
                self.settings.setValue('live/name', snapshot['name'])
                self.live_attach(client)
                dlg.accept()
            except Exception as exc:
                error.setText(str(exc))
        self.live_transport.post(server, path, token, body, done)

    def live_new_client(self, server, snapshot):
        check_session(snapshot['workspace'], snapshot['token'], snapshot)
        path = self.data_dir / 'live-sessions' / (snapshot['workspace'] + '-' + snapshot['actor'] + '.json')
        return LiveClient(server, snapshot['workspace'], snapshot['token'], snapshot, path, self)

    def live_attach(self, client):
        self.set_project(clone(client.project))
        self.live_client = client
        self.history = LiveHistory(client)
        client.presence = self.live_presence_data
        client.can_install = lambda: not (self.layout.anchor is not None or self.layout.drawing or self.layout._rect_pending or getattr(self, '_inspector_dirty', False))
        client.changed.connect(self.live_document_changed)
        client.status_changed.connect(self.live_update_panel)
        self.mode_combo.setCurrentIndex(1)
        self.live_document_changed()
        self.live_show()
        client.start()

    def live_presence_data(self):
        pos = self.layout.mapFromGlobal(QCursor.pos())
        point = self.layout.model(QPointF(pos)) if self.layout.rect().contains(pos) else None
        return dict(cell=self.cid, selection=[s for s in self.selection if isinstance(s, str) and ID.fullmatch(s)][:100],
                    cursor=[point.x(), point.y()] if point is not None else None)

    def live_document_changed(self):
        if not self.live_client:
            return
        self.refresh()
        self.save_recovery()
        self.live_update_panel(self.live_client.message)

    def live_update_panel(self, message):
        client = self.live_client
        if not client:
            return
        self.live_status.setText(message)
        self.live_people.clear()
        people = client.info.get('participants', [])
        for p in people:
            item = QListWidgetItem(p['name'] + ' · ' + p['role'] + (' · you' if p['id'] == client.info['actor'] else ''))
            item.setForeground(QColor(p.get('color', person_color(p['id']))))
            self.live_people.addItem(item)
        self.layout.live_presence = [p for p in people if p['id'] != client.info['actor']]
        self.layout.update()
        self.live_history.clear()
        for event in client.info.get('history', []):
            self.live_history.addItem(str(event['revision']) + ' · ' + event['name'] + ' · ' + event['label'])
        self.live_owner.setVisible(client.info['role'] == 'owner')
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
        editable = client.connected and client.info['role'] != 'view' and not client.pending and not client.conflict
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
            link = invitation_link(client.server, client.workspace, result['invite'])
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
        if not client or not client.conflict or not client.conflict.get('proposed'):
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save retained edit as an independent project', '', 'IC Studio project (*.icproj)')
        if path:
            save_project(client.conflict['proposed'], path)
            self.live_discard_conflict()

    def live_discard_conflict(self):
        client = self.live_client
        if client:
            client.conflict = None
            client.save_journal()
            client.tick()
            self.live_update_panel(client.message)

    def live_resume_dialog(self):
        if not self.live_available():
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Resume a saved live session', str(self.data_dir / 'live-sessions'), 'Live session (*.json)')
        if path and self.maybe_save():
            self.live_attach(LiveClient.resume(path, self))

    def live_leave(self):
        client = self.live_client
        if client:
            client.stop()
            self.live_client = None
            self.history = History(clone(client.project))
            self.layout.live_presence = []
            self.live_dock.hide()
            self.refresh()
            self.statusBar().showMessage('Left live session. This local copy can be saved and edited independently.', 12000)
