"""Application-owned HTTPS host for a chosen LAN/VPN interface."""
import json
from urllib.parse import urlsplit
from PySide6.QtWidgets import QApplication

from .local_collaboration import LocalCollaborationHost, saved_port
from .network_tls import private_address, network_addresses, load_pair, encode_certificate


class NetworkCollaborationHost(LocalCollaborationHost):
    def configure(self, address):
        address = private_address(address)
        if self.state in ('starting', 'running', 'stopping') and self.worker_options.get('address') != address:
            raise ValueError('Stop the network server before changing its network address.')
        self.worker_options = dict(address=address, encrypted=True)

    def saved_certificate(self):
        path = self.directory / 'authority.pem'
        return encode_certificate(load_pair(path)[1]) if path.exists() else ''

    def owns_url(self, url):
        try:
            record = json.loads((self.directory / 'server.json').read_text(encoding='utf-8'))
            u = urlsplit(url)
            return u.scheme == 'https' and u.port == saved_port(self.directory) and u.hostname in record.get('addresses', [])
        except (OSError, ValueError, TypeError):
            return False

    def resume_address(self):
        choices = network_addresses()
        if not choices:
            raise ValueError('Connect to your local network or VPN before resuming this hosted workspace.')
        record = json.loads((self.directory / 'server.json').read_text(encoding='utf-8'))
        self.configure(next((a for a, _ in choices if a == record.get('address')), choices[0][0]))


def network_host(studio):
    app = QApplication.instance()
    if not hasattr(app, '_network_collaboration_hosts'):
        app._network_collaboration_hosts = {}
    directory = (studio.data_dir / 'network-collaboration').resolve()
    if directory not in app._network_collaboration_hosts:
        host = NetworkCollaborationHost(directory, app)
        app.aboutToQuit.connect(host.shutdown)
        app._network_collaboration_hosts[directory] = host
    return app._network_collaboration_hosts[directory]
