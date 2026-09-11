"""Concurrent layout publication over a filesystem with reliable OS file locks.

This is coordination between trusted editors with access to the same directory,
not a network authentication service. A single atomic journal contains the
project, claims and publication revision; abandoned claims expire.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
import uuid
from .model import atomic_write, clone, digest, validate

from .collaboration_document import (FIELDS, LAYOUT_FIELDS, STRUCTURE,
    entities as _entities, diff, merge)


def _changes(base, local):
    return [(r['cell'], r['field'], r['key'], r['before'], r['after']) for r in diff(base, local)]


@contextmanager
def _lock(root):
    root = Path(root)
    with (root / 'workspace.lock').open('a+b') as f:
        if f.tell() == 0: f.write(b'0'); f.flush()
        end = time.monotonic()+5
        while True:
            try:
                f.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= end: raise ValueError('The shared workspace is busy. Retry after the other publication finishes.')
                time.sleep(.05)
        try: yield
        finally:
            f.seek(0)
            if os.name == 'nt': msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _read(root):
    s = json.loads((Path(root) / 'workspace.json').read_text(encoding='utf-8'))
    if s.get('schema') not in (1, 2) or digest(s['project']) != s['project_hash']: raise ValueError('Shared workspace format or project checksum is invalid.')
    validate(s['project'])
    s['claims'] = [c for c in s['claims'] if c['expires'] > time.time()]
    return s


def _write(root, state):
    state['project_hash'] = digest(state['project'])
    atomic_write(Path(root) / 'workspace.json', json.dumps(state, indent=2))


def _allowed(claims, cid, field, old, new):
    if any(c['cell_id'] == '*' for c in claims): return True
    if field in STRUCTURE: return False
    own = [c for c in claims if c['cell_id'] == cid]
    if any(c['layers'] is None for c in own): return True
    if field not in LAYOUT_FIELDS or field in ('layout_instances', 'pdk_layouts', 'parametric_devices'): return False
    values = [v for v in (old, new) if v is not None]
    if field == 'layout_texts': values = [v for group in values for v in group]
    if any(v.get('generated_device') or v.get('pcell_id') for v in values): return False
    layers = {l for c in own for l in c['layers']}
    return all(v.get('layer') in layers for v in values)


class Session:
    def __init__(self, root, editor, state, lease_seconds=300):
        if not isinstance(editor, str) or not editor.strip() or len(editor) > 100: raise ValueError('Enter an editor name of 1–100 characters.')
        if not 10 <= lease_seconds <= 3600: raise ValueError('Claim leases must last 10–3600 seconds.')
        self.root = Path(root); self.editor = editor.strip(); self.token = uuid.uuid4().hex
        self.workspace_id = state['id']; self.base = clone(state['project']); self.revision = state['revision']; self.lease_seconds = lease_seconds

    @classmethod
    def create(cls, root, project, editor, lease_seconds=300):
        validate(project); root = Path(root); root.mkdir(parents=True, exist_ok=True)
        with _lock(root):
            if (root / 'workspace.json').exists(): raise ValueError('This directory already contains a shared workspace. Join it instead.')
            state = dict(schema=2, id=uuid.uuid4().hex, revision=0, project=clone(project), claims=[], publications=[])
            session = cls(root, editor, state, lease_seconds); _write(root, state)
        return session

    @classmethod
    def join(cls, root, editor, lease_seconds=300):
        with _lock(root):
            state = _read(root)
            if state['schema'] == 1:
                state['schema'] = 2
                _write(root, state)
        return cls(root, editor, state, lease_seconds)

    def _state(self):
        s = _read(self.root)
        if s['id'] != self.workspace_id: raise ValueError('The shared workspace was replaced. Save your local project before joining it again.')
        if type(s['revision']) is not int or s['revision'] < self.revision: raise ValueError('The shared workspace revision moved backwards. Save local work and resolve the restored journal before rejoining.')
        if s['revision'] == self.revision and digest(s['project']) != digest(self.base): raise ValueError('The shared project changed without a publication revision. Restore the journal or join a new workspace.')
        return s

    def status(self):
        with _lock(self.root): return self._state()

    def claim(self, cid, layers=None):
        with _lock(self.root):
            s = self._state()
            if cid != '*' and cid not in {c['id'] for c in s['project']['cells']}: raise ValueError('The claimed cell is missing.')
            if cid == '*' and layers is not None: raise ValueError('A whole-project claim cannot be restricted to layers.')
            if layers is not None:
                layers = sorted(set(layers))
                if not layers or not set(layers) <= {l['name'] for l in s['project']['pdk']['layers']}: raise ValueError('Select known layout layers for this claim.')
            for c in s['claims']:
                if c['token'] != self.token and (c['cell_id'] == cid or cid == '*' or c['cell_id'] == '*') and (layers is None or c['layers'] is None or set(layers) & set(c['layers'])):
                    raise ValueError('This partition is claimed by '+c['editor']+'. Choose another cell/layer or wait for its release.')
            s['claims'] = [c for c in s['claims'] if not (c['token'] == self.token and c['cell_id'] == cid and c['layers'] == layers)]
            s['claims'].append(dict(token=self.token, editor=self.editor, cell_id=cid, layers=layers, expires=time.time()+self.lease_seconds))
            _write(self.root, s)

    def renew(self):
        with _lock(self.root):
            s = self._state(); count = 0
            for c in s['claims']:
                if c['token'] == self.token: c['expires'] = time.time()+self.lease_seconds; count += 1
            _write(self.root, s)
            return count

    def release(self, cid=None):
        with _lock(self.root):
            s = self._state(); s['claims'] = [c for c in s['claims'] if not (c['token'] == self.token and (cid is None or c['cell_id'] == cid))]; _write(self.root, s)

    def preview(self, local):
        with _lock(self.root): s = self._state()
        return merge(self.base, local, s['project']), s['revision']

    def refresh(self, local):
        with _lock(self.root): s = self._state()
        q = merge(self.base, local, s['project'])
        self.base = clone(s['project']); self.revision = s['revision']
        return q

    def publish(self, local):
        validate(local)
        with _lock(self.root):
            s = self._state(); changes = _changes(self.base, local)
            own = [c for c in s['claims'] if c['token'] == self.token]
            for cid, field, key, old, new in changes:
                if not _allowed(own, cid, field, old, new): raise ValueError('Change outside an active claim: '+cid+' / '+field+' / '+key+'. Claim the whole cell for schematic edits, or the whole project for cell creation, interfaces and settings.')
            q = merge(self.base, local, s['project'])
            if changes:
                q['revision'] = max(q['revision'], s['project']['revision'])+1
                s['revision'] += 1; s['project'] = q
                s['publications'] = (s['publications']+[dict(revision=s['revision'], editor=self.editor, timestamp=time.time(), objects=len(changes), project_hash=digest(q))])[-100:]
                _write(self.root, s)
        self.base = clone(q); self.revision = s['revision']
        return q
