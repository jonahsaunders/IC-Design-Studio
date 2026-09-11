"""Small real-network acceptance exercised inside installed/frozen application builds."""
from pathlib import Path
import tempfile
import threading
import time

from PySide6.QtTest import QTest

from .layout import rect
from .live_client import LiveClient
from .live_protocol import invitation_link, parse_invitation
from .live_server import Server
from .live_store import Store
from .model import clone, example


def run(window, output):
    previous, path = clone(window.project), window.path
    with tempfile.TemporaryDirectory(prefix='live-probe-', dir=output) as temp:
        root = Path(temp)
        store = Store(root / 'server.sqlite3', 'packaged-probe-key-' + 'x' * 32)
        server = Server(('127.0.0.1', 0), store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = 'http://127.0.0.1:' + str(server.server_port)
        try:
            p = example('empty')
            p['cells'][0]['shapes'] = [rect('metal1', 0, 0, 1600, 900)]
            snapshot = store.create(store.create_key, p, 'Packaged editor')
            invitation = store.invite(snapshot['workspace'], snapshot['token'], 'view')
            link = invitation_link(url, snapshot['workspace'], invitation['invite'])
            assert parse_invitation(link) == (url, snapshot['workspace'], invitation['invite'])
            client = LiveClient(url, snapshot['workspace'], snapshot['token'], snapshot, root / 'session.json', window)
            window.live_attach(client)
            def wait(predicate):
                deadline = time.monotonic() + 12
                while not predicate() and time.monotonic() < deadline:
                    QTest.qWait(20)
                assert predicate(), client.message
            wait(lambda: not client.busy and client.connected)
            window.commit(lambda q: q['cells'][0]['shapes'].append(rect('metal2', 400, 1500, 1400, 700)), 'Packaged live edit')
            wait(lambda: client.pending is None and client.revision == 1)
            assert len(window.cell['shapes']) == 2
            window.undo()
            wait(lambda: client.pending is None and client.revision == 2)
            assert len(window.cell['shapes']) == 1
            window.redo()
            wait(lambda: client.pending is None and client.revision == 3)
            assert len(window.cell['shapes']) == 2
            window.layout.fit()
            QTest.qWait(50)
            assert window.grab().save(str(Path(output) / 'live-collaboration.png'))
        finally:
            if window.live_client:
                window.live_leave()
            QTest.qWait(100)
            server.shutdown()
            server.server_close()
            thread.join(5)
            store.close()
            window.set_project(previous, path)
    return 'packaged live HTTP server/client, invitation parsing, accepted edits and personal undo/redo'
