"""Real HTTP clients, simultaneous edits, durable retries, permissions and personal undo."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
import uuid

from icstudio.layout import rect
from icstudio.live_protocol import LiveError, changes, invitation_link, parse_invitation, resources, server_url
from icstudio.live_server import Server
from icstudio.live_store import Store
from icstudio.model import clone, digest, example


KEY = 'test-creation-key-' + 'x' * 32


def post(url, path, data, token='', headers=None):
    req = Request(url + path, json.dumps(data).encode(),
                  {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token, **(headers or {})})
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


class LiveCollaborationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'live.sqlite3'
        self.start_server()
        self.p = example('empty')
        self.p['cells'][0]['shapes'] = [rect('metal1', 0, 0, 600, 600), rect('metal1', 2000, 0, 600, 600)]
        status, self.a = post(self.url, '/v1/workspaces', dict(project=self.p, name='Alice'), KEY)
        self.assertEqual(status, 200)
        self.wid = self.a['workspace']
        self.base = '/v1/workspaces/' + self.wid
        _, self.inv = self.api('invite', dict(role='edit'), self.a)
        _, self.b = self.api('join', dict(invite=self.inv['invite'], name='Bob'))

    def start_server(self):
        self.store = Store(self.path, KEY)
        self.server = Server(('127.0.0.1', 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.store.close()

    def tearDown(self):
        self.stop_server()
        self.temp.cleanup()

    def api(self, action, data, actor=None):
        return post(self.url, self.base + '/' + action, data, actor['token'] if actor else '')

    def move_request(self, snapshot, index=0, dx=100):
        q = clone(snapshot['project'])
        shape = q['cells'][0]['shapes'][index]
        shape['points'] = [[x + dx, y] for x, y in shape['points']]
        return dict(id=uuid.uuid4().hex, revision=snapshot['revision'], changes=changes(snapshot['project'], q), label='Move shape')

    def history(self, who, action):
        return self.api('edit', dict(id=uuid.uuid4().hex, action=action), who)

    def test_two_clients_edit_different_objects_on_same_layer_simultaneously(self):
        barrier = threading.Barrier(2)
        def edit(actor, index):
            request = self.move_request(actor, index)
            barrier.wait()
            return self.api('edit', request, actor)
        with ThreadPoolExecutor(2) as pool:
            jobs = [pool.submit(edit, self.a, 0), pool.submit(edit, self.b, 1)]
            self.assertEqual([j.result()[0] for j in jobs], [200, 200])
        status, state = self.api('sync', {}, self.a)
        self.assertEqual((status, state['revision']), (200, 2))
        self.assertEqual([s['points'][0][0] for s in state['project']['cells'][0]['shapes']], [100, 2100])

    def test_same_object_stale_edit_rejected_without_lost_update(self):
        self.assertEqual(self.api('edit', self.move_request(self.a), self.a)[0], 200)
        self.assertEqual(self.api('edit', self.move_request(self.b, dx=200), self.b)[0], 409)
        _, state = self.api('sync', {}, self.b)
        self.assertEqual(state['revision'], 1)
        self.assertEqual(state['project']['cells'][0]['shapes'][0]['points'][0][0], 100)

    def test_personal_undo_and_redo_preserve_other_editor(self):
        _, a1 = self.api('edit', self.move_request(self.a), self.a)
        self.assertEqual(self.api('edit', self.move_request(self.b, 1), self.b)[0], 200)
        self.assertEqual(self.api('edit', self.move_request(a1, dx=200), self.a)[0], 200)
        self.assertEqual(self.history(self.a, 'undo')[0], 200)
        status, reverted = self.history(self.a, 'undo')
        self.assertEqual(status, 200)
        self.assertEqual([s['points'][0][0] for s in reverted['project']['cells'][0]['shapes']], [0, 2100])
        self.assertEqual(self.history(self.a, 'redo')[0], 200)
        status, redone = self.history(self.a, 'redo')
        self.assertEqual(status, 200)
        self.assertEqual([s['points'][0][0] for s in redone['project']['cells'][0]['shapes']], [300, 2100])

    def test_undo_refuses_foreign_change_even_if_geometry_returns_to_same_value(self):
        _, a1 = self.api('edit', self.move_request(self.a), self.a)
        _, b1 = self.api('edit', self.move_request(a1, dx=200), self.b)
        self.assertEqual(self.api('edit', self.move_request(b1, dx=-200), self.b)[0], 200)
        self.assertEqual(self.history(self.a, 'undo')[0], 409)
        self.assertEqual(self.api('edit', self.move_request(a1), self.a)[0], 409)

    def test_redo_refuses_foreign_change(self):
        self.api('edit', self.move_request(self.a), self.a)
        _, undone = self.history(self.a, 'undo')
        self.api('edit', self.move_request(undone), self.b)
        self.assertEqual(self.history(self.a, 'redo')[0], 409)

    def test_view_permission_enforced_by_server_and_revoke_disconnects_sessions(self):
        _, invitation = self.api('invite', dict(role='view'), self.a)
        _, viewer = self.api('join', dict(invite=invitation['invite'], name='Viewer'))
        self.assertEqual(self.api('sync', {}, viewer)[0], 200)
        self.assertEqual(self.api('edit', self.move_request(viewer), viewer)[0], 403)
        self.assertEqual(self.api('invite', dict(role='edit'), viewer)[0], 403)
        self.assertEqual(self.api('revoke', dict(invitation=invitation['id']), self.b)[0], 403)
        self.assertEqual(self.api('revoke', dict(invitation=invitation['id']), self.a)[0], 200)
        self.assertEqual(self.api('sync', {}, viewer)[0], 403)
        self.assertEqual(self.api('join', dict(invite=invitation['invite'], name='Late'))[0], 403)
        _, owner = self.api('sync', {}, self.a)
        self.assertNotIn(viewer['actor'], [p['id'] for p in owner['participants']])

    def test_expired_invitation_and_invalid_credentials_are_rejected(self):
        self.store.db.execute('UPDATE invitations SET expires=0 WHERE id=?', (self.inv['id'],))
        self.assertEqual(self.api('sync', {}, self.b)[0], 403)
        self.assertEqual(self.api('join', dict(invite=self.inv['invite'], name='Late'))[0], 403)
        self.assertEqual(self.api('sync', {})[0], 401)
        self.assertEqual(post(self.url, '/v1/workspaces', dict(project=self.p, name='X'), 'wrong')[0], 403)

    def test_selection_reservations_expire_and_disjoint_objects_remain_editable(self):
        cid, sid = self.p['top'], self.p['cells'][0]['shapes'][0]['id']
        _, state = self.api('sync', dict(presence=dict(cell=cid, selection=[sid], cursor=[100, 200])), self.a)
        self.assertEqual(state['participants'][0]['cursor'], [100, 200])
        self.assertTrue(state['leases'])
        _, b = self.api('sync', dict(presence=dict(cell=cid, selection=[sid])), self.b)
        self.assertTrue(b['reservation_denied'])
        self.assertEqual(self.api('edit', self.move_request(self.b), self.b)[0], 409)
        self.assertEqual(self.api('edit', self.move_request(self.b, 1), self.b)[0], 200)
        self.store.db.execute('UPDATE leases SET expires=0')
        self.assertEqual(self.api('edit', self.move_request(self.b), self.b)[0], 200)

    def test_connected_net_edits_are_serialized_and_generated_resources_grouped(self):
        p = clone(self.p)
        for s in p['cells'][0]['shapes']:
            s['net'] = 'signal'
        status, a = post(self.url, '/v1/workspaces', dict(project=p, name='Alice'), KEY)
        self.assertEqual(status, 200)
        base = '/v1/workspaces/' + a['workspace']
        _, inv = post(self.url, base + '/invite', dict(role='edit'), a['token'])
        _, b = post(self.url, base + '/join', dict(invite=inv['invite'], name='Bob'))
        self.assertEqual(post(self.url, base + '/edit', self.move_request(a), a['token'])[0], 200)
        self.assertEqual(post(self.url, base + '/edit', self.move_request(b, 1), b['token'])[0], 409)
        row = self.move_request(a)['changes'][0]
        row['before']['generated_device'] = 'mos1'
        self.assertTrue(any(json.loads(r)[1] == '*' for r in resources([row])))

    def test_commit_retry_after_server_restart_is_idempotent_and_history_survives(self):
        request = self.move_request(self.a)
        self.assertEqual(self.api('edit', request, self.a)[0], 200)
        self.stop_server()
        self.start_server()
        status, result = self.api('edit', request, self.a)
        self.assertEqual((status, result['revision'], result['undo']), (200, 1, 1))
        self.assertEqual(result['acknowledged'], request['id'])
        request['label'] = 'Changed payload'
        self.assertEqual(self.api('edit', request, self.a)[0], 409)
        self.assertEqual(self.history(self.a, 'undo')[0], 200)

    def test_failed_publication_rolls_back_project_event_and_undo_together(self):
        request = self.move_request(self.a)
        with patch.object(self.store, '_snapshot', side_effect=RuntimeError('disk failure')):
            self.assertEqual(self.api('edit', request, self.a)[0], 500)
        _, result = self.api('sync', {}, self.a)
        self.assertEqual((result['revision'], result['undo']), (0, 0))
        self.assertEqual(digest(result['project']), digest(self.a['project']))
        self.assertEqual(self.api('edit', request, self.a)[0], 200)

    def test_invalid_batches_and_structural_project_changes_are_rejected(self):
        req = self.move_request(self.a)
        req['changes'].append(clone(req['changes'][0]))
        self.assertEqual(self.api('edit', req, self.a)[0], 400)
        req = self.move_request(self.a)
        req['changes'][0]['after']['id'] = 'another'
        self.assertEqual(self.api('edit', req, self.a)[0], 400)
        q = clone(self.p)
        q['name'] = 'Changed schematic metadata'
        with self.assertRaises(ValueError):
            changes(self.p, q)
        _, result = self.api('sync', {}, self.a)
        self.assertEqual(result['revision'], 0)

    def test_incremental_sync_omits_unchanged_project_and_rejects_rollback(self):
        _, result = self.api('sync', dict(revision=0), self.a)
        self.assertNotIn('project', result)
        self.assertEqual(self.api('sync', dict(revision=10), self.a)[0], 409)

    def test_owner_recovery_rotates_expired_session_and_preserves_undo_and_retries(self):
        request = self.move_request(self.a)
        self.assertEqual(self.api('edit', request, self.a)[0], 200)
        self.store.db.execute('UPDATE actors SET expires=0 WHERE id=?', (self.a['actor'],))
        self.assertEqual(self.api('sync', {}, self.a)[0], 401)
        endpoint = self.base + '/recover-owner'
        self.assertEqual(post(self.url, endpoint, dict(actor=self.a['actor']), self.a['token'])[0], 403)
        self.assertEqual(post(self.url, endpoint, dict(actor=self.b['actor']), KEY)[0], 403)
        status, recovered = post(self.url, endpoint, dict(actor=self.a['actor']), KEY)
        self.assertEqual((status, recovered['actor'], recovered['role'], recovered['undo']),
                         (200, self.a['actor'], 'owner', 1))
        self.assertNotEqual(recovered['token'], self.a['token'])
        self.assertEqual(self.api('sync', {}, self.a)[0], 401)
        self.assertEqual(self.api('edit', request, recovered)[1]['revision'], 1)
        self.assertEqual(self.history(recovered, 'undo')[0], 200)
        self.assertEqual(self.api('invite', dict(role='view'), recovered)[0], 200)

    def test_workspace_delete_requires_owner_and_reviewed_revision_and_frees_capacity(self):
        self.api('edit', self.move_request(self.a), self.a)
        self.assertEqual(self.api('delete', dict(revision=1), self.b)[0], 403)
        self.assertEqual(self.api('delete', dict(revision=0), self.a)[0], 409)
        # Reach the documented workspace count using actual API-created projects.
        for i in range(99):
            self.store.create(KEY, self.p, 'Host')
        with self.assertRaises(LiveError):
            self.store.create(KEY, self.p, 'Host')
        self.assertEqual(self.api('delete', dict(revision=1), self.a)[0], 200)
        for table in ('actors', 'invitations', 'events', 'versions', 'leases'):
            self.assertEqual(self.store.db.execute('SELECT count(*) FROM ' + table + ' WHERE workspace=?', (self.wid,)).fetchone()[0], 0)
        self.store.create(KEY, self.p, 'Host')
        self.assertNotEqual(self.api('sync', {}, self.b)[0], 200)
        self.assertEqual(self.api('join', dict(invite=self.inv['invite'], name='Late'))[0], 403)

    def test_reservations_name_owner_without_presence(self):
        cid, sid = self.p['top'], self.p['cells'][0]['shapes'][0]['id']
        self.api('sync', dict(presence=dict(cell=cid, selection=[sid])), self.a)
        self.store.presence.clear()
        _, state = self.api('sync', {}, self.b)
        self.assertEqual(state['leases'][0]['name'], 'Alice')

    def test_network_boundary_rejects_browser_posts_and_non_json(self):
        self.assertEqual(post(self.url, self.base + '/sync', {}, self.a['token'], {'Origin': 'https://untrusted.example'})[0], 403)
        self.assertEqual(post(self.url, self.base + '/sync', {}, self.a['token'], {'Content-Type': 'text/plain'})[0], 415)
        with urlopen(self.url + '/join') as response:
            page = response.read().decode()
            self.assertIn('frame-ancestors', response.headers['Content-Security-Policy'])
            self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
            self.assertNotIn(self.inv['invite'], page)
            self.assertIn('icstudio://join', page)

    def test_secrets_hashed_and_links_require_secure_remote_transport(self):
        for table in ('actors', 'invitations'):
            text = str([tuple(r) for r in self.store.db.execute('SELECT * FROM ' + table)])
            self.assertNotIn(self.a['token'], text)
            self.assertNotIn(self.inv['invite'], text)
        link = invitation_link(self.url, self.wid, self.inv['invite'])
        self.assertEqual(parse_invitation(link), (self.url, self.wid, self.inv['invite']))
        desktop = 'icstudio://join?server=' + quote(self.url, safe='') + '#' + link.split('#')[1]
        self.assertEqual(parse_invitation(desktop), parse_invitation(link))
        for url in ('http://example.com', 'https://user:secret@example.com', 'file:///tmp/a', 'https://example.com/path', 'http://127.0.0.1.evil.test'):
            with self.assertRaises(LiveError):
                server_url(url)
        self.assertEqual(server_url('https://example.com'), 'https://example.com')

    def test_source_archive_excludes_private_session_and_server_material(self):
        import importlib.util
        import zipfile
        script = Path(__file__).resolve().parents[1] / 'scripts/release_archives.py'
        spec = importlib.util.spec_from_file_location('live_archive_test', script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        root = Path(self.temp.name) / 'source'
        for name in ('README.md', 'creation-key.txt', 'server.sqlite3', 'docs/server.sqlite3-wal',
                     'icstudio/live-sessions/session.json', 'icstudio/private-live-data/state.json',
                     'icstudio/creation-key.txt', 'icstudio/live_client.py'):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture')
        with patch.object(module, 'ROOT', root):
            archive = module.source_archive(Path(self.temp.name), repository=True)
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(set(z.namelist()), {'IC-Design-Studio/README.md', 'IC-Design-Studio/icstudio/live_client.py'})


if __name__ == '__main__':
    unittest.main()
