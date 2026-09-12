"""Guided private-network hosting with an honest connection checklist."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFormLayout,
                              QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout)
from .live_protocol import invitation_link
from .model import clone
from .network_collaboration import network_host
from .network_tls import network_addresses


def note(text):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.PlainText)
    return label


class HostSessionDialog(QDialog):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        self.host = network_host(studio)
        self.client = None
        self.setWindowTitle('Host a session')
        self.setObjectName('hostSessionWizard')
        self.resize(640, 550)
        layout = QVBoxLayout(self)
        title = note('Work together on your network')
        title.setProperty('role', 'title')
        layout.addWidget(title)
        layout.addWidget(note('For computers on the same local network or a VPN that allows connections between devices. The app handles encryption and keys. Keep this app open while hosting.'))
        form = QFormLayout()
        self.address = QComboBox()
        self.address.setAccessibleName('Network to host on')
        self.refresh_addresses()
        form.addRow('Your network', self.address)
        self.name = QLineEdit(str(studio.settings.value('live/name', '')))
        self.name.setAccessibleName('Your name')
        form.addRow('Your name', self.name)
        layout.addLayout(form)
        controls = QHBoxLayout()
        self.start_button = QPushButton('Start hosting and share project')
        self.start_button.setProperty('role', 'primary')
        self.start_button.clicked.connect(self.start)
        controls.addWidget(self.start_button)
        self.refresh_button = QPushButton('Refresh networks')
        self.refresh_button.clicked.connect(self.refresh_addresses)
        controls.addWidget(self.refresh_button)
        layout.addLayout(controls)
        self.status = note('Choose your network and enter your name to start.')
        self.status.setAccessibleName('Hosting connection status')
        layout.addWidget(self.status)
        self.connection = note('A successful check here verifies this computer. A teammate must join before we can confirm their connection.')
        self.connection.setAccessibleName('Teammate connection status')
        layout.addWidget(self.connection)
        self.help = note('If a teammate cannot connect: check that both computers use the same network or VPN, allow IC Design Studio through the host firewall on that trusted network, and check whether guest Wi-Fi blocks connections between devices.')
        layout.addWidget(self.help)
        self.role = QComboBox()
        self.role.setAccessibleName('Invitation permission')
        for title, role in [('Can edit schematics and layouts', 'edit'), ('Can review and comment', 'review'), ('Can view', 'view')]:
            self.role.addItem(title, role)
        layout.addWidget(self.role)
        self.invite_button = QPushButton('Create and copy invitation')
        self.invite_button.clicked.connect(self.invite)
        layout.addWidget(self.invite_button)
        self.role.hide();self.invite_button.hide()
        layout.addStretch()
        team = self.team_button = QPushButton('Use an existing team server…')
        team.clicked.connect(self.team_server)
        layout.addWidget(team)
        layout.addWidget(note('For computers on different networks, use a reachable team HTTPS server or a suitable VPN. This setup does not configure your router or provide an internet relay.'))
        close = QPushButton('Back to design')
        close.clicked.connect(self.close)
        layout.addWidget(close)
        self.host.changed.connect(self.host_changed)
        self._connected_signals = True
        self.finished.connect(self.closed)
        self.host_changed()

    def refresh_addresses(self):
        selected = self.address.currentData()
        self.address.clear()
        for address, name in network_addresses():
            self.address.addItem(name + ' · ' + address, address)
        if self.host.state == 'running':
            selected = self.host.worker_options['address']
        index = self.address.findData(selected)
        if index >= 0:
            self.address.setCurrentIndex(index)
        if hasattr(self, 'start_button'):
            self.host_changed()

    def host_changed(self):
        busy = self.host.state in ('starting', 'stopping')
        self.start_button.setEnabled(not busy and self.client is None and self.address.count() > 0)
        self.address.setEnabled(not busy and self.client is None and self.host.state != 'running')
        self.refresh_button.setEnabled(not busy and self.client is None)
        self.name.setEnabled(self.client is None and not busy)
        if self.host.error:
            self.status.setText(self.host.error.replace('local server', 'network server'))
        elif not self.address.count():
            self.status.setText('No private network address found. Connect to your local network or VPN, then choose Refresh networks.')
        elif busy:
            self.status.setText('Preparing encrypted hosting…' if self.host.state == 'starting' else 'Stopping the server…')

    def start(self):
        try:
            if not self.studio.live_available() or not self.studio.flush_inspector():
                return
            if not self.name.text().strip():
                self.name.setFocus()
                raise ValueError('Enter your name so teammates can recognize you.')
            if not self.address.currentData():
                raise ValueError('Connect to your local network or VPN and refresh the network list.')
            self.host.configure(self.address.currentData())
            self.host.start(self.check_started)
        except Exception as exc:
            self.status.setText(str(exc))

    def check_started(self):
        if not self.isVisible():
            return
        self.status.setText('The encrypted server has started. Checking its connection…')
        self.studio.live_check_server(self.host.url, self.host.certificate, self.start_button, self.status, self.checked)

    def checked(self, good):
        if not good or not self.isVisible():
            return
        if self.studio.live_client or self.studio.layout_session:
            self.status.setText('Another workspace was opened during setup. Leave it before sharing here.')
            return
        try:
            self.studio.live_connect(self.host.url, '/v2/workspaces', self.host.key,
                                     dict(project=clone(self.studio.project), name=self.name.text()), self,
                                     self.start_button, self.status, certificate=self.host.certificate,
                                     on_connected=self.connected)
        except Exception as exc:
            self.start_button.setEnabled(True)
            self.status.setText(str(exc))

    def connected(self, client):
        self.client = client
        self.status.setText('Hosting at ' + client.server + '. Encryption and this computer’s connection are verified.')
        self.help.setText('Teammates: open Tools → Collaboration → Join a workspace, paste the complete invitation, and choose Check connection first. If blocked, allow the host’s port ' + client.server.rsplit(':', 1)[1] + ' through its firewall on your trusted network. Guest Wi-Fi may isolate devices.')
        self.role.show();self.invite_button.show()
        self.team_button.setText('Manage invitations…')
        self.start_button.hide();self.refresh_button.hide();self.address.setEnabled(False);self.name.setEnabled(False)
        client.status_changed.connect(self.update_peers)
        self.update_peers()
        self.show();self.raise_()

    def update_peers(self, *_):
        if self.studio.live_client is not self.client or not self.client.active:
            self.connection.setText('This workspace session has ended. Reopen Host a session to share again.')
            self.invite_button.setEnabled(False)
            return
        peers = [p for p in self.client.info.get('participants', []) if p['id'] != self.client.info['actor']]
        self.connection.setText('Teammate connection confirmed: ' + ', '.join(p['name'] for p in peers) if peers else 'Waiting for the first teammate to join. Their connection has not yet been confirmed.')

    def invite(self):
        client = self.client
        if not client or self.studio.live_client is not client:
            return
        self.invite_button.setEnabled(False)
        def done(status, result):
            self.invite_button.setEnabled(True)
            if status != 200:
                self.status.setText(result.get('error', 'Could not create an invitation. Retry when connected.'))
                return
            QApplication.clipboard().setText(invitation_link(client.server, client.workspace, result['invite'], client.server_certificate))
            self.status.setText('Invitation copied with ' + result['role'] + ' permission. It expires in 7 days. Send it to your teammate; they can paste it into Join a workspace.')
        client.transport.post(client.server, client.path+'/invite', client.token, dict(role=self.role.currentData(), days=7), done)

    def team_server(self):
        if self.client:
            self.studio.live_manage_access()
        else:
            self.close()
            self.studio.live_share_dialog()

    def closed(self, *_):
        if not self._connected_signals:
            return
        self._connected_signals = False
        self.host.changed.disconnect(self.host_changed)
        if self.client:
            self.client.status_changed.disconnect(self.update_peers)
