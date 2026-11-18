"""Durable, document-local named versions and design comparisons."""
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .model import clone, validate


@dataclass(frozen=True)
class Version:
    id: str
    name: str
    note: str
    created: str
    revision: int | None


class ProjectVersions:
    """Store snapshots and history entries in the same SQLite transaction."""

    def __init__(self, project_path, project_id):
        path = Path(project_path).resolve()
        self.path = path.with_name(path.name + '.versions.sqlite3')
        self.project_id = project_id

    @contextmanager
    def database(self, write=False):
        if not write and not self.path.exists():
            yield None
            return
        mode = 'rwc' if write else 'ro'
        try:
            with closing(sqlite3.connect(self.path.as_uri() + '?mode=' + mode,
                                         uri=True, timeout=1.0)) as db, db:
                db.execute('PRAGMA trusted_schema=OFF')
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                schema = db.execute('PRAGMA user_version').fetchone()[0]
                if schema == 0 and write:
                    db.execute('CREATE TABLE snapshots (hash TEXT PRIMARY KEY, data BLOB NOT NULL)')
                    db.execute('''CREATE TABLE versions (
                        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL,
                        note TEXT NOT NULL, created TEXT NOT NULL, revision INTEGER NOT NULL,
                        hash TEXT NOT NULL REFERENCES snapshots(hash))''')
                    db.execute('CREATE INDEX project_versions ON versions (project_id, created)')
                    db.execute('PRAGMA user_version=1')
                    schema = 1
                if schema not in (0, 1):
                    raise ValueError('This version history requires a newer version of Studio.')
                yield db if schema == 1 else None
        except sqlite3.Error as exc:
            raise ValueError('Could not access project version history. ' + str(exc)) from exc

    def save(self, project, name, note=''):
        name, note = name.strip(), note.strip()
        if not name or len(name) > 100 or len(note) > 4000:
            raise ValueError('Enter a version name of 1–100 characters and a note of up to 4,000 characters.')
        if project['id'] != self.project_id:
            raise ValueError('This design belongs to a different project.')
        project = validate(clone(project))
        data = json.dumps(project, ensure_ascii=False, allow_nan=False,
                          sort_keys=True, separators=(',', ':')).encode('utf-8')
        design_hash = sha256(data).hexdigest()
        version = Version(uuid4().hex, name, note, datetime.now(timezone.utc).isoformat(), project['revision'])
        with self.database(write=True) as db:
            db.execute('''INSERT INTO snapshots VALUES (?, ?)
                          ON CONFLICT(hash) DO UPDATE SET data=excluded.data
                          WHERE snapshots.data <> excluded.data''', (design_hash, data))
            db.execute('INSERT INTO versions VALUES (?, ?, ?, ?, ?, ?, ?)',
                       (version.id, self.project_id, name, note, version.created, version.revision, design_hash))
        return version

    def list(self):
        with self.database() as db:
            if db is None:
                return []
            return [Version(*row) for row in db.execute(
                '''SELECT id, name, note, created, revision FROM versions
                   WHERE project_id=? ORDER BY created DESC, id DESC''', (self.project_id,))]

    def load(self, version_id):
        with self.database() as db:
            row = None if db is None else db.execute(
                '''SELECT v.hash, v.revision, s.data FROM versions v JOIN snapshots s ON s.hash=v.hash
                   WHERE v.id=? AND v.project_id=?''', (version_id, self.project_id)).fetchone()
        if row is None:
            raise ValueError('This saved version is unavailable.')
        design_hash, revision, data = row
        if not isinstance(data, bytes) or sha256(data).hexdigest() != design_hash:
            raise ValueError('This saved version failed its integrity check.')
        project = json.loads(data)
        if (not isinstance(project, dict) or project.get('id') != self.project_id
                or project.get('revision') != revision):
            raise ValueError('This saved version does not match its project or revision.')
        return validate(project)


def same_design(before, after):
    keys = (before.keys() | after.keys()) - {'revision', 'modified'}
    return all(key in before and key in after and before[key] == after[key] for key in keys)


def restore_contents(project, version):
    if project['id'] != version['id']:
        raise ValueError('Restore versions within their original project.')
    snapshot = clone(version)
    project.clear()
    project.update(snapshot)


def compare(before, after, limit=250):
    """Describe changes from the comparison design to the selected version."""
    changes = []
    omitted = 0

    def add(message):
        nonlocal omitted
        if len(changes) < limit:
            changes.append(message)
        else:
            omitted += 1

    def fields(left, right, exclude=()):
        return [key for key in sorted(left.keys() | right.keys()) if key not in exclude
                and (key not in left or key not in right or left[key] != right[key])]

    def title(key):
        return {'pdk': 'Process technology', 'analysis': 'Simulation settings',
                'simulation_setups': 'Simulation setups', 'top': 'Top cell',
                'devices': 'Components', 'shapes': 'Layout geometry', 'layout_texts': 'Layout labels',
                'digital': 'Digital design', 'electrical': 'Connectivity'}.get(key, key.replace('_', ' ').capitalize())

    def value(item):
        return '—' if item is None else str(item) if isinstance(item, (str, int, float)) and len(str(item)) <= 90 else '…'

    for key in fields(before, after, {'cells', 'revision', 'modified'}):
        left, right = before.get(key), after.get(key)
        if key in {'analysis', 'pdk'} and isinstance(left, dict) and isinstance(right, dict):
            for field in fields(left, right):
                a, b = value(left.get(field)), value(right.get(field))
                add(f'{title(key)} · {title(field)}' + (f' · {a} → {b}' if a != b else ' changed'))
        else:
            a, b = value(left), value(right)
            add(title(key) + (f' · {a} → {b}' if a != b else ' changed'))

    old = {cell['id']: cell for cell in before['cells']}
    new = {cell['id']: cell for cell in after['cells']}
    if [key for key in old if key in new] != [key for key in new if key in old]:
        add('Cell order changed')
    for key in dict.fromkeys([*old, *new]):
        left, right = old.get(key), new.get(key)
        if left is None or right is None:
            add('Added cell ' + right['name'] if right is not None else 'Removed cell ' + left['name'])
            continue
        if left == right:
            continue
        name = right['name']
        for field in fields(left, right, {'devices', 'id'}):
            add(f'{name} · {title(field)} changed' if field != 'name' else f'Renamed cell {left["name"]} → {name}')
        devices_before = {device['id']: device for device in left['devices']}
        devices_after = {device['id']: device for device in right['devices']}
        if list(devices_before) != list(devices_after) and devices_before == devices_after:
            add(f'{name} · Component order changed')
        for identity in dict.fromkeys([*devices_before, *devices_after]):
            a, b = devices_before.get(identity), devices_after.get(identity)
            if a is None or b is None:
                add(f'{name} · Added {b["name"]}' if b is not None else f'{name} · Removed {a["name"]}')
                continue
            for field in fields(a, b, {'id'}):
                prior, selected = value(a.get(field)), value(b.get(field))
                add(f'{name} · {b["name"]} · {title(field)}' +
                    (f' · {prior} → {selected}' if prior != selected else ' changed'))
    if omitted:
        changes.append(f'{omitted} more changes')
    return changes
