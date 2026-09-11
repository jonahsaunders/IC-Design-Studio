"""Version 1 live-layout transactions and invitation links; no Qt or networking."""
import ipaddress
import json
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from .layout_collaboration import FIELDS, _changes, _entities
from .model import clone, validate

MAX_BYTES = 16 * 1024 * 1024
MAX_OBJECTS = 20000
MAX_CHANGES = 2000
ID = re.compile(r'^[A-Za-z0-9_-]{1,80}$')


class LiveError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def bounded_project(project):
    if len(json.dumps(project, allow_nan=False).encode()) > MAX_BYTES // 2:
        raise LiveError('Live projects must be smaller than 8 MiB.', 413)
    if sum(len(c.get(f, [])) for c in project.get('cells', []) for f in FIELDS) > MAX_OBJECTS:
        raise LiveError('Live projects support up to 20,000 stored layout objects.', 413)
    return validate(project)


def changes(before, after):
    result = [dict(cell=c, field=f, key=k, before=a, after=b) for c, f, k, a, b in _changes(before, after)]
    return checked_changes(result)


def checked_changes(rows):
    if not isinstance(rows, list) or len(rows) > MAX_CHANGES:
        raise LiveError('Use at most 2,000 changed objects per edit.', 413)
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'cell', 'field', 'key', 'before', 'after'}:
            raise LiveError('Invalid layout transaction.', 400)
        c, f, k = row['cell'], row['field'], row['key']
        if not isinstance(c, str) or not ID.fullmatch(c) or not isinstance(k, str) or len(k) > 128 or f not in FIELDS:
            raise LiveError('Invalid layout object identity.', 400)
        identity = (c, f, k)
        if identity in seen or row['before'] == row['after']:
            raise LiveError('Duplicate or unchanged transaction object.', 400)
        seen.add(identity)
        for value in (row['before'], row['after']):
            if value is None:
                continue
            if f == 'layout_texts':
                if k != 'texts' or not isinstance(value, list):
                    raise LiveError('Invalid layout text collection.', 400)
            elif not isinstance(value, dict) or value.get(FIELDS[f]) != k:
                raise LiveError('An edit cannot change object identity.', 400)
    return rows


def resource(cell, field, key):
    return json.dumps([cell, field, key], separators=(',', ':'))


def resources(rows):
    """Reserve related generated geometry together; serialize edits to one net."""
    result = set()
    for row in rows:
        c, f, k = row['cell'], row['field'], row['key']
        result.add(resource(c, f, k))
        values = [v for v in (row['before'], row['after']) if isinstance(v, dict)]
        if f != 'shapes' or any(v.get('generated_device') or v.get('pcell_id') for v in values):
            result.add(resource(c, '*', '*'))
        for value in values:
            if value.get('net'):
                result.add(resource(c, 'net', value['net']))
    return result


def overlaps(a, b):
    ac, af, ak = json.loads(a)
    bc, bf, bk = json.loads(b)
    return ac == bc and (af == '*' or bf == '*' or (af, ak) == (bf, bk))


def apply_changes(project, rows):
    q = clone(project)
    cells = {c['id']: c for c in q['cells']}
    for row in checked_changes(rows):
        c = cells.get(row['cell'])
        if c is None:
            raise LiveError('The edited cell no longer exists.')
        field, key = row['field'], row['key']
        values = _entities(c, field)
        if values.get(key) != row['before']:
            raise LiveError('Another editor changed this object. Your proposed edit has been retained locally.')
        if row['after'] is None:
            values.pop(key, None)
        else:
            values[key] = clone(row['after'])
        c[field] = values.get('texts', []) if FIELDS[field] is None else list(values.values())
    # Recompute changes to prohibit metadata edits hidden inside object payloads.
    changes(project, q)
    return bounded_project(q)


def inverse(rows):
    return [dict(r, before=r['after'], after=r['before']) for r in rows]


def server_url(value):
    if not isinstance(value, str) or len(value) > 2000:
        raise LiveError('Enter a collaboration server URL.', 400)
    u = urlsplit(value.strip())
    try:
        loopback = u.hostname == 'localhost' or ipaddress.ip_address(u.hostname or '').is_loopback
    except ValueError:
        loopback = False
    if u.scheme != 'https' and not (u.scheme == 'http' and loopback):
        raise LiveError('Use HTTPS for remote servers. HTTP is allowed only on localhost.', 400)
    if not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('', '/'):
        raise LiveError('Use the server origin without a path, credentials, query or fragment.', 400)
    try:
        u.port
    except ValueError:
        raise LiveError('Invalid server port.', 400) from None
    return urlunsplit((u.scheme, u.netloc, '', '', ''))


def invitation_link(server, workspace, secret):
    return server_url(server) + '/join#' + urlencode(dict(workspace=workspace, invite=secret))


def parse_invitation(link):
    if not isinstance(link, str) or len(link) > 4096:
        raise LiveError('Invalid invitation link.', 400)
    u = urlsplit(link.strip())
    if u.scheme == 'icstudio' and u.netloc == 'join' and u.path in ('', '/'):
        query = parse_qs(u.query, strict_parsing=True)
        if set(query) != {'server'} or len(query['server']) != 1:
            raise LiveError('Invalid desktop invitation.', 400)
        server = server_url(query['server'][0])
    elif u.scheme in ('https', 'http') and u.path == '/join' and not u.query:
        server = server_url(urlunsplit((u.scheme, u.netloc, '', '', '')))
    else:
        raise LiveError('Paste a complete IC Design Studio invitation link.', 400)
    data = parse_qs(u.fragment, strict_parsing=True)
    if set(data) != {'workspace', 'invite'} or any(len(v) != 1 for v in data.values()):
        raise LiveError('The invitation fragment is incomplete.', 400)
    workspace, secret = data['workspace'][0], data['invite'][0]
    if not ID.fullmatch(workspace) or not re.fullmatch(r'[A-Za-z0-9_-]{32,100}', secret):
        raise LiveError('Invalid invitation credentials.', 400)
    return server, workspace, secret
