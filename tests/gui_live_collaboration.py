"""Three actual Qt editors against an HTTP server; UI sharing, reconnect and undo evidence."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QSettings, QStandardPaths, Qt
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
        dashboard = a.collaboration_dashboard()
        assert a.collaboration_action in a.task_menus['Tools'].actions()
        assert not any('collaboration' in action.text().lower() or 'Concurrent editing' in action.text()
                       for action in a.task_menus['Layout'].actions())
        assert dashboard.tabs.count() == 4 and dashboard.share.isEnabled() and dashboard.join.isEnabled()
        wait(lambda: dashboard.scan.isFinished(), 'Recent workspace discovery did not finish')
        dashboard.resize(780, 600)
        QTest.qWait(100)
        assert dashboard.grab().save(str(out / 'collaboration-dashboard.png'))
        dashboard.hide()
        checks.append('Tools opens one dashboard with live and shared-folder tools, useful empty state and recent workspaces')
        dlg = a.live_share_dialog()
        fields = dlg.findChildren(QLineEdit)
        fields[0].setText(url)
        fields[1].setText(key)
        fields[2].setText('Alice')
        button(dlg, 'Start sharing').click()
        wait(lambda: a.live_client is not None, 'Share UI did not connect')
        wait(lambda: settled(a), 'Owner did not synchronize')
        a.live_role.setCurrentIndex(a.live_role.findData('edit'))
        a.live_invite()
        wait(lambda: QApplication.clipboard().text().startswith(url + '/join#'), 'Edit invitation not copied')
        edit_link = QApplication.clipboard().text()
        assert parse_invitation(edit_link)[0] == url
        dlg = b.live_join_dialog(edit_link)
        dlg.findChildren(QLineEdit)[1].setText('Bob')
        button(dlg, 'Join workspace').click()
        wait(lambda: settled(b), 'Edit invitation did not join')
        a.live_role.setCurrentIndex(a.live_role.findData('view'))
        a.live_invite()
        wait(lambda: QApplication.clipboard().text() != edit_link, 'View invitation not copied')
        view_link = QApplication.clipboard().text()
        dlg = v.live_join_dialog(view_link)
        dlg.findChildren(QLineEdit)[1].setText('Viewer')
        button(dlg, 'Join workspace').click()
        wait(lambda: settled(v), 'View invitation did not join')
        checks.append('Share UI and view/edit invitation links join actual desktop windows')

        dashboard.show();dashboard.tabs.setCurrentIndex(3);panel=dashboard.review_panel
        wait(lambda:not panel.busy and panel.loaded_version is not None and settled(a),'Team review did not load')
        with patch('icstudio.team_review_ui.QInputDialog.getText',return_value=('Initial layout',True)):panel.create()
        wait(lambda:not panel.busy and panel.checkpoints.count()==1,'Checkpoint was not saved through HTTP')
        checkpoint=panel.checkpoints.currentData();a.select([a.cell['shapes'][0]['id']],'layout')
        panel.anchor.setChecked(True);panel.comment.setPlainText('Please check this connection before approval.');panel.post_comment()
        wait(lambda:not panel.busy and panel.comments.topLevelItemCount()==1,'Object comment did not persist')
        panel.comments.setCurrentItem(panel.comments.topLevelItem(0));a.select([],'layout');panel.navigate()
        assert a.selection==[a.cell['shapes'][0]['id']]
        panel.decision.setCurrentIndex(1);panel.decide();wait(lambda:not panel.busy and 'approved' in panel.decisions.text(),'Checkpoint approval did not persist')
        other=b.collaboration_dashboard();other.tabs.setCurrentIndex(3);review=other.review_panel
        wait(lambda:not review.busy and review.comments.topLevelItemCount()==1,'Second editor did not receive team review')
        assert 'approved' in review.decisions.text()
        panel.grab().save(str(out/'team-review.png'));dashboard.hide();other.hide()
        checks.append('Named checkpoints, anchored comments, object navigation and revision-specific decisions synchronize between real desktop editors')

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
        dashboard.show();dashboard.tabs.setCurrentIndex(3)
        wait(lambda:not panel.busy,'Review was busy before comparison');panel.compare()
        wait(lambda:hasattr(panel,'comparison'),'Revision comparison did not open');assert panel.comparison.table.topLevelItemCount()>0
        panel.comparison.grab().save(str(out/'team-revision-comparison.png'));panel.comparison.close();dashboard.hide()

        cid, sid = a.cid, a.cell['shapes'][0]['id']
        a.live_client.presence = lambda: dict(cell=cid, selection=[sid], cursor=[100, 500])
        b.live_client.presence = lambda: dict(cell=cid, selection=[b.cell['shapes'][1]['id']], cursor=[2900, 900])
        wait(lambda: len(a.live_client.info.get('participants', [])) == 3 and len(b.layout.live_presence) >= 2, 'Presence did not synchronize')
        wait(lambda: any(l['actor'] == a.live_client.info['actor'] for l in b.live_client.info.get('leases', [])), 'Reservation missing')
        move(b, 0, 300)
        wait(lambda: b.live_client.conflict is not None, 'Reserved-object edit was not rejected')
        assert b.live_client.conflict['proposed']['cells'][0]['shapes'][0]['points'][0][0] == 400
        save_project(b.live_client.conflict['proposed'], out / 'retained-conflict.icproj')
        review = b.live_review_conflict()
        QTest.qWait(80)
        review.fit_views()
        assert review.views[1].scene_model.items() and review.details.topLevelItemCount() == 1
        assert any(b.live_reservations.topLevelItem(i).text(2) == 'Alice'
                   for i in range(b.live_reservations.topLevelItemCount()))
        assert review.grab().save(str(out / 'collaboration-conflict-review.png'))
        move(a, 2, 50)
        wait(lambda: b.live_client.revision == a.live_client.revision and settled(a), 'Remote edit did not reach conflict review')
        assert not review.reapply_button.isEnabled(), 'Stale comparison allowed reapply'
        a.live_client.presence = lambda: {}
        wait(lambda: not any(l['actor'] == a.live_client.info['actor'] for l in b.live_client.info.get('leases', [])), 'Owner reservation did not release')
        review.refresh_comparison()
        assert review.reapply_button.isEnabled()
        review.reapply_button.click()
        wait(lambda: not b.live_client.conflict and settled(b), 'Reviewed edit did not acknowledge')
        assert b.cell['shapes'][0]['points'][0][0] == 400
        assert b.cell['shapes'][2]['points'][0][0] == 750, 'Reapply lost the remote edit'
        checks.append('Visual review shows three versions, disables stale reapply, and preserves another editor’s accepted change')
        wait(lambda: any(p['name'] == 'Bob' and p.get('cursor') == [2900, 900] and p.get('selection') for p in a.layout.live_presence), 'Remote cursor and selection did not reach the owner canvas')
        a.raise_()
        a.layout.fit()
        QTest.qWait(100)
        # Verify a remote selection is actually painted, including the flat-cell
        # path that has no hierarchical LayoutScene cache.
        canvas_image = a.layout.grab().toImage()
        bob = next(p for p in a.layout.live_presence if p['name'] == 'Bob')
        from PySide6.QtGui import QColor
        expected = QColor(bob['color'])
        shape = a.cell['shapes'][1]
        x0 = round(shape['points'][0][0] * a.layout.scale + a.layout.offset.x())
        x1 = round(shape['points'][1][0] * a.layout.scale + a.layout.offset.x())
        y0 = round(shape['points'][0][1] * a.layout.scale + a.layout.offset.y())
        colored = 0
        for x in range(max(0, x0-5), min(canvas_image.width(), x1+5)):
            for y in range(max(0, y0-6), min(canvas_image.height(), y0+2)):
                pixel = canvas_image.pixelColor(x, y)
                colored += all(abs(a-b) < 8 for a,b in zip(pixel.getRgb()[:3], expected.getRgb()[:3]))
        assert colored > 10, 'Remote selection outline was not painted'
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
        third_before = a.cell['shapes'][2]['points'][0][0]
        move(a, 2, 100)
        wait(lambda: bool(dropped) and not a.live_client.busy, 'Lost-ack scenario did not execute')
        journal = a.live_client.journal
        assert a.live_client.pending
        a.live_leave()
        resumed = LiveClient.resume(journal, a)
        assert resumed.pending
        a.live_attach(resumed)
        wait(lambda: settled(a) and a.live_client.revision == dropped[0], 'Saved request did not recover idempotently')
        assert not a.live_client.pending and a.cell['shapes'][2]['points'][0][0] == third_before + 100
        checks.append('Restarting a desktop session replays an unacknowledged edit exactly once')

        wait(lambda: any(i['role'] == 'view' for i in a.live_client.info.get('invitations', [])), 'Invitations not restored')
        index = next(i for i in range(a.live_invitations.count()) if a.live_invitations.item(i).text().startswith('view'))
        a.live_invitations.setCurrentRow(index)
        a.live_revoke()
        wait(lambda: not v.live_client.connected and 'revoked' in v.live_client.message, 'Revoked viewer remained connected')
        checks.append('Owner revocation disconnects an already joined viewer')
        wait(lambda: settled(a), 'Owner did not settle before recovery check')
        owner_id = a.live_client.info['actor']
        journal = a.live_client.journal
        expected_undo = a.live_client.info['undo']
        a.live_leave()
        store.db.execute('UPDATE actors SET expires=0 WHERE id=?', (owner_id,))
        dashboard = a.collaboration_dashboard(0)
        wait(lambda: dashboard.scan.isFinished(), 'Recent workspace discovery failed')
        wait(lambda: any(dashboard.recent.item(i).data(Qt.UserRole)['path'] == str(journal)
                         for i in range(dashboard.recent.count())), 'Saved owner workspace missing')
        for i in range(dashboard.recent.count()):
            if dashboard.recent.item(i).data(Qt.UserRole)['path'] == str(journal):
                dashboard.recent.setCurrentRow(i)
                break
        dashboard.resume_button.click()
        wait(lambda: a.live_client and not a.live_client.connected and not a.live_client.busy, 'Expired owner did not pause')
        assert a.live_recover_button.isVisible()
        recovery = a.live_recover_owner()
        recovery.findChild(QLineEdit).setText(key)
        button(recovery, 'Restore owner access').click()
        wait(lambda: a.live_client.connected and settled(a), 'Owner recovery did not reconnect')
        assert a.live_client.info['actor'] == owner_id and a.live_client.info['undo'] == expected_undo
        a.collaboration_dashboard(1)
        QTest.qWait(100)
        assert dashboard.grab().save(str(out / 'collaboration-live-workspace.png'))
        wait(lambda: settled(a), 'Owner polling did not settle')
        journal_time = journal.stat().st_mtime_ns
        QTest.qWait(1400)
        assert journal.stat().st_mtime_ns == journal_time, 'Unchanged presence polls rewrote the project journal'
        dashboard.hide()
        assert a.live_client.active, 'Closing dashboard stopped collaboration'
        checks.append('Dashboard resume and administrator recovery preserve owner identity and personal undo; idle polls do not rewrite journals')
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
