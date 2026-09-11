"""Authenticated, durable live-layout coordination. All mutations use SQLite transactions."""
from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid

from .model import clone, digest, now
from .live_protocol import (LiveError, ID, apply_changes, bounded_project,
                            checked_changes, inverse, overlaps, resources)

LEASE_SECONDS = 12
PRESENCE_SECONDS = 20
SESSION_SECONDS = 7 * 86400


def encode(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False)


def token_hash(value):
    if not isinstance(value, str) or len(value) > 128:
        raise LiveError('Invalid credential format.', 400)
    return hashlib.sha256(value.encode()).hexdigest()


class Store:
    def __init__(self, path, create_key):
        if len(create_key) < 32:
            raise ValueError('Use a creation key with at least 32 characters.')
        self.create_key = create_key
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.presence = {}
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        if self.db.execute('PRAGMA user_version').fetchone()[0] not in (0, 1):
            raise ValueError('Unsupported collaboration database version.')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY, project TEXT, revision INTEGER);
            CREATE TABLE IF NOT EXISTS invitations(id TEXT PRIMARY KEY, workspace TEXT, secret TEXT UNIQUE,
                role TEXT, expires REAL, revoked INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS actors(id TEXT PRIMARY KEY, workspace TEXT, secret TEXT UNIQUE,
                name TEXT, role TEXT, invitation TEXT, expires REAL, undo TEXT, redo TEXT);
            CREATE TABLE IF NOT EXISTS events(workspace TEXT, request TEXT, actor TEXT, fingerprint TEXT,
                revision INTEGER, changes TEXT, label TEXT, created REAL, PRIMARY KEY(workspace, request));
            CREATE TABLE IF NOT EXISTS versions(workspace TEXT, resource TEXT, actor TEXT, revision INTEGER,
                PRIMARY KEY(workspace, resource, actor));
            CREATE TABLE IF NOT EXISTS leases(workspace TEXT, resource TEXT, actor TEXT, expires REAL,
                PRIMARY KEY(workspace, resource));
            CREATE INDEX IF NOT EXISTS events_revision ON events(workspace, revision);
            PRAGMA user_version=1;
        ''')
        path.chmod(0o600)

    def close(self):
        with self.lock:
            self.db.close()

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise

    def _workspace(self, wid):
        row = self.db.execute('SELECT * FROM workspaces WHERE id=?', (wid,)).fetchone()
        if row is None:
            raise LiveError('Workspace unavailable.', 404)
        return row

    def _actor(self, wid, secret, owner=False, edit=False):
        row = self.db.execute('SELECT * FROM actors WHERE workspace=? AND secret=?',
                              (wid, token_hash(secret))).fetchone()
        if row is None or row['expires'] <= time.time():
            raise LiveError('Session expired or unavailable. Join with a valid invitation.', 401)
        if row['invitation']:
            inv = self.db.execute('SELECT * FROM invitations WHERE id=?', (row['invitation'],)).fetchone()
            if inv is None or inv['revoked'] or inv['expires'] <= time.time():
                raise LiveError('This invitation has expired or been revoked.', 403)
        if owner and row['role'] != 'owner':
            raise LiveError('Only the workspace owner can manage invitations.', 403)
        if edit and row['role'] == 'view':
            raise LiveError('This session can view the layout. An edit invitation is required to change it.', 403)
        return row

    def _new_actor(self, wid, name, role, invitation=None):
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ord(c) < 32 for c in name):
            raise LiveError('Enter an editor name of 1–80 printable characters.', 400)
        count = self.db.execute('SELECT count(*) FROM actors WHERE workspace=? AND expires>?',
                                (wid, time.time())).fetchone()[0]
        if count >= 100:
            raise LiveError('This workspace has reached its 100-session limit.', 429)
        ident, secret = uuid.uuid4().hex, secrets.token_urlsafe(32)
        self.db.execute('INSERT INTO actors VALUES(?,?,?,?,?,?,?,?,?)',
                        (ident, wid, token_hash(secret), name.strip(), role, invitation,
                         time.time() + SESSION_SECONDS, '[]', '[]'))
        return ident, secret

    def create(self, secret, project, name):
        if not hmac.compare_digest(secret, self.create_key):
            raise LiveError('Invalid workspace creation key.', 403)
        project = bounded_project(clone(project))
        with self.transaction():
            if self.db.execute('SELECT count(*) FROM workspaces').fetchone()[0] >= 100:
                raise LiveError('This server has reached its 100-workspace limit.', 429)
            wid = uuid.uuid4().hex
            self.db.execute('INSERT INTO workspaces VALUES(?,?,0)', (wid, encode(project)))
            _, token = self._new_actor(wid, name, 'owner')
            result = self._snapshot(wid, self._actor(wid, token), -1)
            return dict(result, workspace=wid, token=token)

    def invite(self, wid, token, role, days=7):
        if role not in ('view', 'edit') or type(days) is not int or not 1 <= days <= 30:
            raise LiveError('Choose view/edit permission and an expiry of 1–30 days.', 400)
        with self.transaction():
            self._actor(wid, token, owner=True)
            count = self.db.execute('SELECT count(*) FROM invitations WHERE workspace=? AND revoked=0 AND expires>?',
                                    (wid, time.time())).fetchone()[0]
            if count >= 100:
                raise LiveError('Revoke an existing invitation before creating more.', 429)
            ident, secret = uuid.uuid4().hex, secrets.token_urlsafe(32)
            expiry = time.time() + days * 86400
            self.db.execute('INSERT INTO invitations VALUES(?,?,?,?,?,0)', (ident, wid, token_hash(secret), role, expiry))
            return dict(id=ident, invite=secret, role=role, expires=expiry)

    def revoke(self, wid, token, invitation):
        with self.transaction():
            self._actor(wid, token, owner=True)
            self.db.execute('UPDATE invitations SET revoked=1 WHERE id=? AND workspace=?', (invitation, wid))
            self.db.execute('DELETE FROM leases WHERE actor IN (SELECT id FROM actors WHERE invitation=? AND workspace=?)',
                            (invitation, wid))
            return {'revoked': True}

    def join(self, wid, secret, name):
        with self.transaction():
            inv = self.db.execute('SELECT * FROM invitations WHERE workspace=? AND secret=?', (wid, token_hash(secret))).fetchone()
            if inv is None or inv['revoked'] or inv['expires'] <= time.time():
                raise LiveError('Invitation unavailable, expired or revoked.', 403)
            _, token = self._new_actor(wid, name, inv['role'], inv['id'])
            result = self._snapshot(wid, self._actor(wid, token), -1)
            return dict(result, workspace=wid, token=token)

    def _snapshot(self, wid, actor, since):
        w = self._workspace(wid)
        result = dict(revision=w['revision'], actor=actor['id'], name=actor['name'], role=actor['role'],
                      undo=len(json.loads(actor['undo'])), redo=len(json.loads(actor['redo'])))
        if since != w['revision']:
            result['project'] = json.loads(w['project'])
        timestamp = time.time()
        # Validate invitation state before exposing presence or renewing an expired session.
        active = [a['id'] for a in self.db.execute('''SELECT a.id FROM actors a LEFT JOIN invitations i ON a.invitation=i.id
            WHERE a.workspace=? AND a.expires>? AND (a.invitation IS NULL OR (i.revoked=0 AND i.expires>?)) ORDER BY a.rowid''', (wid, timestamp, timestamp))]
        colors = ['#64dfc0', '#ffba73', '#bca5ff', '#f18bbb', '#7bbfff', '#d5db75']
        result['participants'] = [dict(p, id=ident, color=colors[active.index(ident) % len(colors)]) for (workspace, ident), p in self.presence.items()
                                  if workspace == wid and ident in active and p['seen'] > timestamp - PRESENCE_SECONDS]
        result['leases'] = [dict(r) for r in self.db.execute('SELECT resource,actor,expires FROM leases WHERE workspace=? AND expires>?', (wid, timestamp))
                            if r['actor'] in active]
        result['history'] = [dict(r) for r in self.db.execute('''SELECT e.revision,e.label,e.created,a.name FROM events e
            JOIN actors a ON e.actor=a.id WHERE e.workspace=? ORDER BY e.revision DESC LIMIT 20''', (wid,))]
        if actor['role'] == 'owner':
            result['invitations'] = [dict(r) for r in self.db.execute('SELECT id,role,expires,revoked FROM invitations WHERE workspace=? ORDER BY expires DESC', (wid,))]
        return result

    def sync(self, wid, token, since=-1, presence=None):
        if type(since) is not int or since < -1:
            raise LiveError('Invalid revision.', 400)
        presence = presence or {}
        with self.transaction():
            a = self._actor(wid, token)
            if since > self._workspace(wid)['revision']:
                raise LiveError('Server revision moved backwards. Save a copy and contact the owner.')
            self.db.execute('UPDATE actors SET expires=? WHERE id=?', (time.time() + SESSION_SECONDS, a['id']))
            self.db.execute('DELETE FROM leases WHERE expires<=?', (time.time(),))
            cell, selection, cursor = presence.get('cell'), presence.get('selection', []), presence.get('cursor')
            if cell is not None and (not isinstance(cell, str) or not ID.fullmatch(cell)):
                raise LiveError('Invalid presence cell.', 400)
            if not isinstance(selection, list) or len(selection) > 100 or any(not isinstance(s, str) or not ID.fullmatch(s) for s in selection):
                raise LiveError('Presence supports at most 100 selected objects.', 400)
            if cursor is not None and (not isinstance(cursor, list) or len(cursor) != 2 or any(type(n) not in (int, float) or not -2**31 < n < 2**31 for n in cursor)):
                raise LiveError('Invalid cursor position.', 400)
            self.presence[(wid, a['id'])] = dict(name=a['name'], role=a['role'], cell=cell, selection=selection,
                                                 cursor=cursor, seen=time.time())
            wanted = set()
            if a['role'] != 'view' and selection:
                project = json.loads(self._workspace(wid)['project'])
                c = next((c for c in project['cells'] if c['id'] == cell), None)
                if c:
                    for field, key in (('shapes', 'id'), ('layout_instances', 'id')):
                        for obj in c.get(field, []):
                            if obj[key] in selection:
                                wanted.update(resources([dict(cell=cell, field=field, key=obj[key], before=obj, after=obj)]))
            self.db.execute('DELETE FROM leases WHERE workspace=? AND actor=?', (wid, a['id']))
            leases = list(self.db.execute('SELECT * FROM leases WHERE workspace=? AND expires>?', (wid, time.time())))
            denied = any(overlaps(r, l['resource']) for r in wanted for l in leases)
            if not denied:
                for r in wanted:
                    self.db.execute('INSERT OR REPLACE INTO leases VALUES(?,?,?,?)', (wid, r, a['id'], time.time() + LEASE_SECONDS))
            # Bound transient memory to recent presence only.
            self.presence = {key: p for key, p in self.presence.items() if p['seen'] > time.time() - PRESENCE_SECONDS}
            return dict(self._snapshot(wid, a, since), reservation_denied=denied)

    def edit(self, wid, token, request):
        if not isinstance(request, dict) or set(request) - {'id', 'revision', 'changes', 'label', 'action'}:
            raise LiveError('Invalid edit request.', 400)
        opid = request.get('id', '')
        if not isinstance(opid, str) or not ID.fullmatch(opid):
            raise LiveError('An edit needs a stable request ID.', 400)
        fingerprint = digest(request)
        with self.transaction():
            actor = self._actor(wid, token, edit=True)
            previous = self.db.execute('SELECT * FROM events WHERE workspace=? AND request=?', (wid, opid)).fetchone()
            if previous:
                if previous['actor'] != actor['id'] or previous['fingerprint'] != fingerprint:
                    raise LiveError('Request ID was already used for another edit.')
                return dict(self._snapshot(wid, actor, -1), acknowledged=opid)
            undo, redo = json.loads(actor['undo']), json.loads(actor['redo'])
            action = request.get('action', 'edit')
            if action in ('undo', 'redo'):
                stack = undo if action == 'undo' else redo
                if not stack:
                    raise LiveError('There is no personal ' + action + ' available.')
                entry = stack[-1]
                rows, base = entry['changes'], entry['revision']
                label = action.title() + ' · ' + entry['label']
            elif action == 'edit':
                rows = checked_changes(request.get('changes'))
                base = request.get('revision')
                label = request.get('label', 'Layout edit')
            else:
                raise LiveError('Unknown edit action.', 400)
            w = self._workspace(wid)
            if type(base) is not int or not 0 <= base <= w['revision']:
                raise LiveError('Invalid or restored server revision.')
            if not rows or not isinstance(label, str) or not 1 <= len(label) <= 160:
                raise LiveError('Empty edit or invalid edit label.', 400)
            touched = resources(rows)
            for version in self.db.execute('SELECT * FROM versions WHERE workspace=? AND revision>?', (wid, base)):
                if action != 'edit' and version['actor'] == actor['id']:
                    continue
                if any(overlaps(r, version['resource']) for r in touched):
                    raise LiveError('Another edit changed an affected object or connected group. Refresh and review; personal undo never overwrites another editor.')
            for lease in self.db.execute('SELECT * FROM leases WHERE workspace=? AND actor!=? AND expires>?', (wid, actor['id'], time.time())):
                if any(overlaps(r, lease['resource']) for r in touched):
                    raise LiveError('An affected object or connected group is temporarily reserved by another editor.')
            q = apply_changes(json.loads(w['project']), rows)
            revision = w['revision'] + 1
            q['revision'] += 1
            q['modified'] = now()
            self.db.execute('UPDATE workspaces SET project=?,revision=? WHERE id=?', (encode(q), revision, wid))
            self.db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?)', (wid, opid, actor['id'], fingerprint, revision, encode(rows), label, time.time()))
            for r in touched:
                self.db.execute('INSERT OR REPLACE INTO versions VALUES(?,?,?,?)', (wid, r, actor['id'], revision))
            item = dict(changes=inverse(rows), revision=revision, label=entry['label'] if action != 'edit' else label)
            if action == 'undo':
                undo.pop()
                redo.append(item)
            elif action == 'redo':
                redo.pop()
                undo.append(item)
            else:
                undo.append(item)
                redo = []
            self.db.execute('UPDATE actors SET undo=?,redo=? WHERE id=?', (encode(undo[-100:]), encode(redo[-100:]), actor['id']))
            return dict(self._snapshot(wid, self._actor(wid, token), -1), acknowledged=opid)

    def leave(self, wid, token):
        with self.transaction():
            a = self._actor(wid, token)
            self.db.execute('DELETE FROM leases WHERE workspace=? AND actor=?', (wid, a['id']))
            self.presence.pop((wid, a['id']), None)
            return {'left': True}
