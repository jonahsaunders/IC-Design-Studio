"""Version 2 schematic/layout transactions and invitation links; no Qt."""
import ipaddress
import json
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from .collaboration_document import FIELDS, STRUCTURE, diff, install, resource, resources, overlaps
from .model import clone, validate

MAX_BYTES = 16 * 1024 * 1024
MAX_OBJECTS = 20000
MAX_CHANGES = 2000
PROTOCOL = 2
ID = re.compile(r'^[A-Za-z0-9_-]{1,80}$')


class LiveError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def bounded_project(project):
    if len(json.dumps(project, allow_nan=False).encode()) > MAX_BYTES // 2:
        raise LiveError('Live projects must be smaller than 8 MiB.', 413)
    if sum(len(c.get(f, [])) for c in project.get('cells', []) for f in FIELDS) > MAX_OBJECTS:
        raise LiveError('Live projects support up to 20,000 stored schematic and layout objects.', 413)
    return validate(project)


def changes(before, after):
    return checked_changes(diff(before, after))


def checked_changes(rows):
    if not isinstance(rows, list) or len(rows) > MAX_CHANGES:
        raise LiveError('Use at most 2,000 changed objects per edit.', 413)
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'cell', 'field', 'key', 'before', 'after'}:
            raise LiveError('Invalid layout transaction.', 400)
        c, f, k = row['cell'], row['field'], row['key']
        if not isinstance(c, str) or not ID.fullmatch(c) or not isinstance(k, str) or len(k) > 128 or f not in set(FIELDS) | STRUCTURE:
            raise LiveError('Invalid layout object identity.', 400)
        identity = (c, f, k)
        if identity in seen or row['before'] == row['after']:
            raise LiveError('Duplicate or unchanged transaction object.', 400)
        seen.add(identity)
        for value in (row['before'], row['after']):
            if value is None:
                continue
            if f in STRUCTURE:
                if k != c or not isinstance(value, dict) or (f != 'project' and value.get('id') != c):
                    raise LiveError('Invalid cell or project identity.', 400)
            elif FIELDS[f] is None:
                if k != ('texts' if f == 'layout_texts' else f) or not isinstance(value, list):
                    raise LiveError('Invalid shared collection.', 400)
            elif not isinstance(value, dict) or value.get(FIELDS[f]) != k:
                raise LiveError('An edit cannot change object identity.', 400)
    replaced = {r['cell'] for r in rows if r['field'] == 'cells'}
    if any(r['cell'] in replaced and r['field'] != 'cells' for r in rows):
        raise LiveError('A cell replacement cannot also contain object edits.', 400)
    if any(r['field'] in ('cell', 'project') and (r['before'] is None or r['after'] is None) for r in rows):
        raise LiveError('Cell and project metadata cannot be removed.', 400)
    return rows


def apply_changes(project, rows):
    try:
        q = install(project, checked_changes(rows))
        changes(project, q)
        return bounded_project(q)
    except LiveError:
        raise
    except (ValueError, KeyError, TypeError) as exc:
        raise LiveError(str(exc)) from exc


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


def invitation_link(server, workspace, secret, certificate=''):
    origin = server_url(server)
    data = dict(workspace=workspace, invite=secret)
    if certificate:
        from .network_tls import decode_certificate
        decode_certificate(certificate)
        if not origin.startswith('https://'):
            raise LiveError('Certificate invitations require HTTPS.', 400)
        data['cert'] = certificate
        return 'icstudio://join?' + urlencode(dict(server=origin)) + '#' + urlencode(data)
    return origin + '/join#' + urlencode(data)


def parse_invitation(link):
    return parse_invitation_details(link)[:3]


def parse_invitation_details(link):
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
    if set(data) not in ({'workspace', 'invite'}, {'workspace', 'invite', 'cert'}) or any(len(v) != 1 for v in data.values()):
        raise LiveError('The invitation fragment is incomplete.', 400)
    workspace, secret = data['workspace'][0], data['invite'][0]
    if not ID.fullmatch(workspace) or not re.fullmatch(r'[A-Za-z0-9_-]{32,100}', secret):
        raise LiveError('Invalid invitation credentials.', 400)
    certificate = data.get('cert', [''])[0]
    if certificate:
        from .network_tls import decode_certificate
        decode_certificate(certificate)
        if not server.startswith('https://'):
            raise LiveError('Certificate invitations require HTTPS.', 400)
    return server, workspace, secret, certificate
