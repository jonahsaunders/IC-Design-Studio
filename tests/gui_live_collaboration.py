"""Three actual Qt editors against an HTTP server; UI sharing, reconnect and undo evidence."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QSettings, QStandardPaths
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton
    from PySide6.QtGui import QFontDatabase
    from icstudio.gui import Studio
    from icstudio.layout import rect
    from icstudio.live_client import LiveClient
    from icstudio.live_protocol import LiveError, parse_invitation
    from icstudio.live_server import Server
    from icstudio.live_store import Store
    from icstudio.model import clone, save_project

    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(out / 'profile/settings'))
    # Keep all Windows known-folder writes in the test's explicit evidence directory.
    QStandardPaths.writableLocation = staticmethod(lambda kind: str(out / 'profile' / str(kind.value)))
    app = QApplication([])
    if os.name == 'nt' and not QFontDatabase.families():
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    app.setStyle('Fusion')
    key = 'gui-test-key-' + 'x' * 40
    store = Store(out / 'server/database.sqlite3', key)
    server = Server(('127.0.0.1', 0), store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = 'http://127.0.0.1:' + str(server.server_port)
    windows, checks = [], []

    def wait(predicate, description, seconds=12):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            QTest.qWait(20)
        raise AssertionError(description + ' · ' + ' / '.join(w.live_client.message for w in windows if w.live_client))

    def button(dlg, text):
        return next(b for b in dlg.findChildren(QPushButton) if b.text() == text)

    def settled(w):
        return w.live_client and not w.live_client.pending and not w.live_client.busy

    def move(w, index, dx):
        def edit(p):
            s = p['cells'][0]['shapes'][index]
            s['points'] = [[x + dx, y] for x, y in s['points']]
        w.commit(edit, 'Move layout shape')

    try:
        for name in ('Alice', 'Bob', 'Viewer'):
            w = Studio(recover=False)
            w.maybe_save = lambda: True
            w.error = lambda text: (_ for _ in ()).throw(AssertionError(text))
            w.live_check.setChecked(False)
            w.show()
            windows.append(w)
        a, b, v = windows
        from icstudio.model import example
        p = example('empty')
        p['name'] = 'Shared analog layout'
        p['cells'][0]['shapes'] = [rect('metal1', 0, 0, 1600, 900), rect('metal1', 2400, 0, 1600, 900), rect('metal2', 700, 1700, 2600, 650)]
        a.set_project(p)
        dlg = a.live_share_dialog()
        fields = dlg.findChildren(QLineEdit)
        fields[0].setText(url)
        fields[1].setText(key)
        fields[2].setText('Alice')
        button(dlg, 'Start sharing').click()
        wait(lambda: a.live_client is not None, 'Share UI did not connect')
        wait(lambda: settled(a), 'Owner did not synchronize')
        a.live_role.setCurrentIndex(1)
        a.live_invite()
        wait(lambda: QApplication.clipboard().text().startswith(url + '/join#'), 'Edit invitation not copied')
        edit_link = QApplication.clipboard().text()
        assert parse_invitation(edit_link)[0] == url
        dlg = b.live_join_dialog(edit_link)
        dlg.findChildren(QLineEdit)[1].setText('Bob')
        button(dlg, 'Join layout').click()
        wait(lambda: settled(b), 'Edit invitation did not join')
        a.live_role.setCurrentIndex(0)
        a.live_invite()
        wait(lambda: QApplication.clipboard().text() != edit_link, 'View invitation not copied')
        view_link = QApplication.clipboard().text()
        dlg = v.live_join_dialog(view_link)
        dlg.findChildren(QLineEdit)[1].setText('Viewer')
        button(dlg, 'Join layout').click()
        wait(lambda: settled(v), 'View invitation did not join')
        checks.append('Share UI and view/edit invitation links join actual desktop windows')

        a.move([a.cell['shapes'][0]['id']], 100, 0, 'layout')
        move(b, 1, 200)
        wait(lambda: settled(a) and settled(b) and a.live_client.revision == b.live_client.revision == 2, 'Disjoint edits failed')
        wait(lambda: v.live_client.revision == 2, 'Viewer did not receive live edits')
        assert a.project['cells'] == b.project['cells'] == v.project['cells']
        try:
            move(v, 0, 100)
            raise AssertionError('Viewer was allowed to edit')
        except LiveError:
            pass
        a.undo()
        wait(lambda: settled(a) and a.live_client.revision == 3, 'Personal undo failed')
        assert [s['points'][0][0] for s in a.cell['shapes'][:2]] == [0, 2600]
        a.redo()
        wait(lambda: settled(a) and a.live_client.revision == 4, 'Personal redo failed')
        wait(lambda: b.live_client.revision == 4, 'Bob did not receive redo')
        checks.append('Same-cell same-layer edits update automatically; personal undo preserves the other editor')

        cid, sid = a.cid, a.cell['shapes'][0]['id']
        a.live_client.presence = lambda: dict(cell=cid, selection=[sid], cursor=[100, 500])
        b.live_client.presence = lambda: dict(cell=cid, selection=[b.cell['shapes'][1]['id']], cursor=[2900, 900])
        wait(lambda: len(a.live_client.info.get('participants', [])) == 3 and len(b.layout.live_presence) >= 2, 'Presence did not synchronize')
        wait(lambda: any(l['actor'] == a.live_client.info['actor'] for l in b.live_client.info.get('leases', [])), 'Reservation missing')
        move(b, 0, 300)
        wait(lambda: b.live_client.conflict is not None, 'Reserved-object edit was not rejected')
        assert b.live_client.conflict['proposed']['cells'][0]['shapes'][0]['points'][0][0] == 400
        save_project(b.live_client.conflict['proposed'], out / 'retained-conflict.icproj')
        b.live_discard_conflict()
        wait(lambda: b.live_client.connected and settled(b), 'Conflict did not recover')
        wait(lambda: any(p['name'] == 'Bob' and p.get('cursor') == [2900, 900] and p.get('selection') for p in a.layout.live_presence), 'Remote cursor and selection did not reach the owner canvas')
        a.raise_()
        a.layout.fit()
        QTest.qWait(100)
        assert a.grab().save(str(out / 'live-participants.png'))
        checks.append('Colored presence and reservations synchronize; rejected edits remain available to save')

        # Simulate the server committing an edit whose acknowledgement is lost.
        a.live_client.presence = lambda: {}
        b.live_client.presence = lambda: {}
        wait(lambda: not a.live_client.info.get('leases') and settled(a), 'Reservations did not release')
        original_post = a.live_client.transport.post
        dropped = []
        def lose_ack(server_url, path, token, body, callback):
            def response(status, data):
                if path.endswith('/edit') and not dropped and status == 200:
                    dropped.append(data['revision'])
                    callback(0, {'error': 'Simulated lost acknowledgement'})
                else:
                    callback(status, data)
            return original_post(server_url, path, token, body, response)
        a.live_client.transport.post = lose_ack
        move(a, 2, 100)
        wait(lambda: bool(dropped) and not a.live_client.busy, 'Lost-ack scenario did not execute')
        journal = a.live_client.journal
        assert a.live_client.pending
        a.live_leave()
        resumed = LiveClient.resume(journal, a)
        assert resumed.pending
        a.live_attach(resumed)
        wait(lambda: settled(a) and a.live_client.revision == dropped[0], 'Saved request did not recover idempotently')
        assert not a.live_client.pending and a.cell['shapes'][2]['points'][0][0] == 800
        checks.append('Restarting a desktop session replays an unacknowledged edit exactly once')

        wait(lambda: any(i['role'] == 'view' for i in a.live_client.info.get('invitations', [])), 'Invitations not restored')
        index = next(i for i in range(a.live_invitations.count()) if a.live_invitations.item(i).text().startswith('view'))
        a.live_invitations.setCurrentRow(index)
        a.live_revoke()
        wait(lambda: not v.live_client.connected and 'revoked' in v.live_client.message, 'Revoked viewer remained connected')
        checks.append('Owner revocation disconnects an already joined viewer')
        # Never retain invitation/session secrets in screenshots or tracked evidence.
        (out / 'report.json').write_text(json.dumps(dict(status='passed',platform=app.platformName(),checks=checks), indent=2))
        print(json.dumps(checks))
    except BaseException:
        for i, w in enumerate(windows):
            w.grab().save(str(out / ('failure-' + str(i) + '.png')))
        raise
    finally:
        QApplication.clipboard().clear()
        for w in windows:
            if w.live_client:
                w.live_leave()
            w.close()
        app.processEvents()
        server.shutdown()
        server.server_close()
        thread.join(5)
        store.close()


if __name__ == '__main__':
    main()
