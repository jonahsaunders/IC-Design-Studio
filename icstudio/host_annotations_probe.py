"""Actual Qt acceptance for encrypted hosting and direct annotation editing."""
from contextlib import ExitStack, closing
from pathlib import Path
import sqlite3
import tempfile
import time
from unittest.mock import patch

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from .live_client import Transport
from .live_protocol import parse_invitation_details
from .model import clone, device, digest, example, uid
from .network_collaboration import network_host
from . import network_tls


def wait(predicate, message):
    deadline = time.monotonic() + 15
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(20)
    assert predicate(), message


def button(dialog, title):
    return next(b for b in dialog.findChildren(QPushButton) if b.text() == title)


def position(canvas, x, y):
    return (canvas.offset + QPointF(x, y)*canvas.scale).toPoint()


def select_note(window):
    if window._collaboration_dashboard:
        window._collaboration_dashboard.hide()
    window.raise_();window.activateWindow();QTest.qWait(20)
    canvas = window.schematic
    canvas.auto_fit = False;canvas.scale = 1;canvas.offset = QPointF(40, 50)
    n = window.cell['annotations'][0]
    QTest.mouseClick(canvas, Qt.LeftButton, Qt.NoModifier, position(canvas, n['x']+8, n['y']+8))
    assert window.selection == [n['id']]
    return n


def run(window, output):
    original, path = clone(window.project), window.path
    original_save = window.maybe_save
    host = network_host(window)
    assert host.state == 'stopped'
    previous_directory = host.directory
    peer = wizard = None
    with tempfile.TemporaryDirectory(prefix='host-annotations-', dir=output) as temp, ExitStack() as stack:
        root = Path(temp)
        host.directory = root / 'host'
        # Isolated loopback adapter: tests real HTTPS and both editors without
        # requiring a LAN/firewall in CI. Production rejects loopback choices.
        validate_address = network_tls.private_address
        test_address = lambda v: v if v == '127.0.0.1' else validate_address(v)
        stack.enter_context(patch('icstudio.network_tls.private_address', test_address))
        stack.enter_context(patch('icstudio.network_collaboration.private_address', test_address))
        choices = lambda: [('127.0.0.1', 'Isolated acceptance network')]
        stack.enter_context(patch('icstudio.network_host_ui.network_addresses', choices))
        stack.enter_context(patch('icstudio.network_collaboration.network_addresses', choices))
        try:
            window.maybe_save = lambda: True
            p = example('empty');p['name'] = 'Annotation review'
            cell = p['cells'][0]
            cell['devices'] = [device('R', 'R1', 460, 80)]
            cell['annotations'] = [dict(id=uid(), x=40, y=30, text='Review this bias point\nThen check the layout.')]
            window.set_project(p);window.mode_combo.setCurrentIndex(0);QTest.qWait(50)
            n = select_note(window)
            assert 'annotation:text' in window.form_fields
            canvas = window.schematic
            start = position(canvas, n['x']+8, n['y']+8)
            end = start + position(canvas, 40, 20) - position(canvas, 0, 0)
            QTest.mousePress(canvas, Qt.LeftButton, Qt.NoModifier, start)
            QTest.mouseMove(canvas, end, 20)
            QTest.mouseRelease(canvas, Qt.LeftButton, Qt.NoModifier, end)
            assert (window.cell['annotations'][0]['x'], window.cell['annotations'][0]['y']) == (80, 50)
            window.undo();assert window.cell['annotations'][0]['x'] == 40
            window.redo();assert window.cell['annotations'][0]['x'] == 80
            n = select_note(window)
            QTest.mouseDClick(canvas, Qt.LeftButton, Qt.NoModifier, position(canvas, n['x']+8, n['y']+8))
            QTest.qWait(30)
            text = window.form_fields['annotation:text']
            assert text.hasFocus()
            before = digest(window.project)
            window.form_fields['annotation:x'].setText('nan')
            assert not window.apply_inspector(False) and digest(window.project) == before
            window.form_fields['annotation:x'].setText('80')
            text.setPlainText('Updated directly on the canvas\nReady for review.')
            assert window.apply_inspector(False)
            assert window.cell['annotations'][0]['text'].startswith('Updated directly')
            text = window.form_fields['annotation:text'];text.setFocus();text.selectAll()
            QTest.keyClick(text, Qt.Key_Delete)
            assert len(window.cell['annotations']) == 1
            window.build_inspector()  # Discard the uncommitted text draft.
            select_note(window);QTest.keyClick(canvas, Qt.Key_Delete)
            assert not window.cell['annotations'] and len(window.cell['devices']) == 1
            window.undo();select_note(window);window.duplicate()
            assert len(window.cell['annotations']) == 2
            assert len({n['id'] for n in window.cell['annotations']}) == 2
            window.select([], 'schematic')
            canvas.auto_fit = False;canvas.scale = 1;canvas.offset = QPointF(40, 50)
            QTest.mousePress(canvas, Qt.LeftButton, Qt.NoModifier, position(canvas, 60, 20))
            QTest.mouseMove(canvas, position(canvas, 410, 180), 20)
            QTest.mouseRelease(canvas, Qt.LeftButton, Qt.NoModifier, position(canvas, 410, 180))
            assert {n['id'] for n in window.cell['annotations']} <= set(window.selection)
            window.delete();assert not window.cell['annotations']
            window.undo();assert len(window.cell['annotations']) == 2
            window.schematic.capture_filters.discard('annotations')
            assert all('text' not in o for o in canvas.capture_candidates(QPointF(88,58)))
            window.schematic.capture_filters.add('annotations')
            select_note(window);QTest.qWait(30)
            assert window.grab().save(str(Path(output) / 'annotation-inspector.png'))

            wizard = window.host_session_dialog()
            wizard.name.setText('Host designer')
            wizard.start_button.click()
            wait(lambda: wizard.client is not None or bool(host.error), 'Hosting wizard did not complete: ' + wizard.status.text())
            assert wizard.client is not None, host.error + ' ' + wizard.status.text()
            owner = window.live_client
            wait(lambda: owner.connected and not owner.busy, 'Host did not synchronize')
            assert host.url.startswith('https://') and host.certificate == owner.server_certificate
            assert 'not yet been confirmed' in wizard.connection.text()
            wizard.invite_button.click()
            wait(lambda: QApplication.clipboard().text().startswith('icstudio://join?'), 'Encrypted invitation not copied')
            link = QApplication.clipboard().text()
            assert parse_invitation_details(link)[3] == host.certificate
            assert host.key not in link and 'PRIVATE KEY' not in link
            url, authority = host.url, host.certificate

            # Wrong, absent and wrong-hostname trust cannot send an authorized
            # create request, even after a successful connection to this origin.
            wrong_dir = root / 'wrong';wrong_dir.mkdir()
            _, wrong = network_tls.host_certificates(wrong_dir, '127.0.0.1')
            transport = Transport(window)
            for address, certificate in ((url, wrong), (url, ''), (url.replace('127.0.0.1', 'localhost'), authority)):
                replies = []
                transport.post(address, '/v2/workspaces', host.key, dict(project=clone(window.project), name='Must not create'), lambda status, result: replies.append((status, result)), certificate=certificate)
                wait(lambda: bool(replies), 'TLS rejection did not finish')
                assert replies[0][0] != 200, 'Untrusted or mismatched TLS peer accepted credentials'
                assert 'secure connection could not be verified' in replies[0][1].get('error', ''), replies[0]
            with closing(sqlite3.connect(host.directory/'collaboration.sqlite3')) as db:
                assert db.execute('SELECT count(*) FROM workspaces').fetchone()[0] == 1

            peer = type(window)(recover=False);peer.maybe_save = lambda: True;peer.show()
            join = peer.live_join_dialog(link)
            join.findChildren(QLineEdit)[1].setText('Review partner')
            check = button(join, 'Check connection first');check.click()
            wait(lambda: check.isEnabled(), 'Peer connection check did not finish')
            assert any('Connection verified' in label.text() for label in join.findChildren(__import__('PySide6.QtWidgets', fromlist=['QLabel']).QLabel))
            button(join, 'Join workspace').click()
            wait(lambda: peer.live_client and peer.live_client.connected and not peer.live_client.busy, 'Peer did not join encrypted host')
            wait(lambda: 'Review partner' in wizard.connection.text(), 'Host did not confirm actual teammate join')
            assert wizard.grab().save(str(Path(output) / 'network-host-connected.png'))
            peer.mode_combo.setCurrentIndex(0);QTest.qWait(30);select_note(peer)
            peer.form_fields['annotation:text'].setPlainText('Reviewed together over HTTPS')
            assert peer.apply_inspector(False)
            wait(lambda: not peer.live_client.pending and window.cell['annotations'][0]['text'] == 'Reviewed together over HTTPS', 'Annotation text did not synchronize')
            select_note(peer);QTest.keyClick(peer.schematic, Qt.Key_Delete)
            assert len(peer.cell['annotations']) == 1, (peer.selection, peer.live_client.message, type(QApplication.focusWidget()).__name__)
            wait(lambda: not peer.live_client.pending and len(window.cell['annotations']) == 1, 'Shared annotation deletion did not synchronize')
            peer.undo()
            wait(lambda: not peer.live_client.pending and len(window.cell['annotations']) == 2, 'Shared annotation undo did not synchronize')
            assert window.cell['devices'][0]['name'] == 'R1'
            owner_journal = owner.journal
            peer_journal = peer.live_client.journal
            peer.live_leave();window.live_leave();QTest.qWait(100)
            host.stop();wait(lambda: host.state == 'stopped', 'Encrypted host did not stop')
            window.live_resume_path(owner_journal)
            wait(lambda: host.state == 'running' and window.live_client and window.live_client.connected and not window.live_client.busy, 'Hosted workspace did not restart')
            assert host.url == url and host.certificate == authority
            peer.live_resume_path(peer_journal)
            wait(lambda: peer.live_client and peer.live_client.connected and not peer.live_client.busy, 'Peer certificate/session did not survive restart')
            assert peer.live_client.server_certificate == authority
        finally:
            if wizard:
                wizard.close()
            if peer:
                peer.build_inspector()
                if peer.live_client:peer.live_leave()
                peer.close()
            if window.live_client:window.live_leave()
            QTest.qWait(100)
            host.shutdown();QTest.qWait(50)
            host.directory = previous_directory;host.error = '';host.worker_options = {}
            window.maybe_save = original_save
            window.set_project(original, path)
    return 'HTTPS hosting wizard, peer connection check, isolated certificate trust, restart, direct annotation editing/deletion/undo and two-editor synchronization'
