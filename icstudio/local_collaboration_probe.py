"""Exercise button-driven local hosting in source and installed desktop builds."""
from pathlib import Path
import socket
import tempfile
import time

from PySide6.QtCore import QLockFile
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from .local_collaboration import local_host
from .model import clone, device, example


def run(window, output):
    host = local_host(window)
    assert host.state == 'stopped'
    previous, path = clone(window.project), window.path
    previous_directory = host.directory
    previous_save = window.maybe_save
    peer = None

    def wait(predicate, message):
        deadline = time.monotonic() + 12
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(20)
        assert predicate(), message + ': ' + host.error

    def click(dialog, text):
        next(b for b in dialog.findChildren(QPushButton) if b.text() == text).click()

    with tempfile.TemporaryDirectory(prefix='local-server-', dir=output) as temp:
        host.directory = Path(temp)
        try:
            window.maybe_save = lambda: True
            window.set_project(example('empty'))
            dashboard = window.collaboration_dashboard(0)
            assert dashboard.local_start.isEnabled()
            # Another desktop instance must not open a second store/presence
            # coordinator for the same directory.
            lock = QLockFile(str(host.directory / 'server.lock'))
            assert lock.tryLock(0)
            dashboard.local_start.click()
            dialog = window._live_connect_dialog
            wait(lambda: host.state == 'stopped' and bool(host.error), 'Duplicate host did not fail visibly')
            assert 'already open' in host.error
            assert not next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Start sharing').isEnabled()
            lock.unlock()
            click(dialog, 'Start local server')
            wait(lambda: host.state == 'running', 'Local server did not start')
            url, key = host.url, host.key
            fields = dialog.findChildren(QLineEdit)
            assert fields[0].text() == url and fields[0].isReadOnly()
            assert fields[1].text() == key and not fields[1].isVisible()
            assert len(key) >= 32 and key not in dashboard.local_status.text()
            click(dialog, 'Use a team server')
            assert not fields[1].text() and not fields[0].text()
            assert not fields[0].isReadOnly() and fields[1].isVisible()
            click(dialog, 'Use local server')
            fields[0].setText('https://different-server.example')
            assert not fields[1].text(), 'Local credential followed a changed endpoint'
            click(dialog, 'Use local server')
            fields[2].setText('Local owner')
            assert dialog.grab().save(str(Path(output) / 'local-server-ready.png'))
            click(dialog, 'Start sharing')
            wait(lambda: window.live_client and window.live_client.connected and not window.live_client.busy, 'Button-created workspace did not connect')
            client = window.live_client
            workspace, journal = client.workspace, client.journal
            window.commit(lambda p: p['cells'][0]['devices'].append(device('R', 'Rlocal', 0, 0)), 'Local schematic edit')
            wait(lambda: client.pending is None and client.revision == 1, 'Local edit was not saved')
            dashboard.refresh_state()
            assert not dashboard.local_stop.isEnabled()
            assert 'only on this computer' in window.live_invitation_note.text()
            window.live_role.setCurrentIndex(window.live_role.findData('edit'))
            window.live_invite()
            wait(lambda: QApplication.clipboard().text().startswith(url + '/join#'), 'Local invitation was not created')
            peer = type(window)(recover=False)
            peer.maybe_save = lambda: True
            peer.show()
            join = peer.live_join_dialog(QApplication.clipboard().text())
            join.findChildren(QLineEdit)[1].setText('Local teammate')
            click(join, 'Join workspace')
            wait(lambda: peer.live_client and peer.live_client.connected and not peer.live_client.busy, 'Second editor could not join local server')
            assert peer.cell['devices'][0]['name'] == 'Rlocal'
            peer.live_leave()
            window.live_leave()
            QTest.qWait(100)
            dashboard.refresh_state()
            assert dashboard.local_stop.isEnabled()
            dashboard.local_stop.click()
            wait(lambda: host.state == 'stopped', 'Local server did not stop')
            assert (host.directory / 'collaboration.sqlite3').is_file()
            key_path = host.directory / 'creation-key.txt'
            key_path.write_text('invalid', encoding='utf-8')
            host.start()
            wait(lambda: host.state == 'stopped' and bool(host.error), 'Invalid key did not report a startup error')
            assert key_path.read_text(encoding='utf-8') == 'invalid', 'Saved key was silently replaced'
            key_path.write_text(key + '\n', encoding='utf-8')
            port = int(url.rsplit(':', 1)[1])
            with socket.socket() as blocker:
                option = getattr(socket, 'SO_EXCLUSIVEADDRUSE', socket.SO_REUSEADDR)
                blocker.setsockopt(socket.SOL_SOCKET, option, 1)
                blocker.bind(('127.0.0.1', port))
                blocker.listen()
                host.start()
                wait(lambda: host.state == 'stopped' and bool(host.error), 'Occupied saved address was silently changed')
                assert 'address is unavailable' in host.error, host.error
            # Resume starts the saved server; no key entry or new workspace.
            window.live_resume_path(journal)
            wait(lambda: host.state == 'running' and window.live_client and window.live_client.connected and not window.live_client.busy, 'Resume did not restart the server')
            assert host.url == url and host.key == key
            assert window.live_client.workspace == workspace and window.live_client.revision == 1
            assert window.cell['devices'][0]['name'] == 'Rlocal'
            window.undo()
            wait(lambda: window.live_client.pending is None and window.live_client.revision == 2, 'Undo did not survive server restart')
            assert not window.cell['devices']
            window.live_leave()
            dashboard.tabs.setCurrentIndex(0)
            dashboard.refresh_state()
            assert dashboard.grab().save(str(Path(output) / 'local-server-dashboard.png'))
            host.stop()
            wait(lambda: host.state == 'stopped', 'Final stop did not complete')
            callbacks = []
            host.start(lambda: callbacks.append('unexpected'))
            host.stop()
            wait(lambda: host.state == 'stopped', 'Stop during startup did not complete')
            assert not callbacks
        finally:
            if peer:
                if peer.live_client:
                    peer.live_leave()
                peer.close()
            if window.live_client:
                window.live_leave()
            QTest.qWait(100)
            host.shutdown()
            QTest.qWait(50)
            host.directory = previous_directory
            host.error = ''
            window.maybe_save = previous_save
            window.set_project(previous, path)
    return 'local server button, automatic credential isolation, second editor, startup errors, durable restart and undo'
