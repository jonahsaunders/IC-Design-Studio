"""Portable, revision-bound extracted cell views for saved electrical fixtures.

A captured netlist is an implementation to simulate, not proof of DRC or LVS.
The source fingerprint binds it to the circuit, physical hierarchy and technology
present at capture. Stale views remain readable but cannot silently be simulated.
"""
import hashlib
import re
from pathlib import Path

from .model import clone, digest, uid, NAME, atomic_write

MAX_BYTES = 16 * 1024 * 1024
KINDS = {'capacitance': 'Extracted capacitance', 'rc': 'Extracted RC',
         'external': 'External implementation'}


def subcircuits(text):
    """Read interfaces without executing simulator commands or resolving files."""
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_BYTES or '\x00' in text:
        raise ValueError('An implementation netlist must be UTF-8 text of at most 16 MiB.')
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('*'):
            continue
        if line.startswith('+'):
            if not lines:
                raise ValueError('Netlist continuation has no preceding statement.')
            lines[-1] += ' ' + line[1:].strip()
        else:
            lines.append(line)
    found = {}; active = None
    for line in lines:
        words = line.split(); directive = words[0].lower()
        if directive == '.subckt':
            if active or len(words) < 3:
                raise ValueError('Implementation views need complete, non-nested subcircuits.')
            name = words[1]
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.$-]*', name) or name.lower() in found:
                raise ValueError('Invalid or duplicate implementation subcircuit name.')
            pins = []
            for word in words[2:]:
                if '=' in word or word.lower() == 'params:':
                    break
                pins.append(word)
            if not pins or len({pin.lower() for pin in pins}) != len(pins):
                raise ValueError('Implementation subcircuit ports must be distinct.')
            active = name; found[name.lower()] = {'name': name, 'ports': pins}
        elif directive == '.ends':
            if not active or len(words) > 2 or len(words) == 2 and words[1].lower() != active.lower():
                raise ValueError('Implementation subcircuit ending does not match its declaration.')
            active = None
        elif directive == '.end':
            raise ValueError('Remove the top-level .end; import subcircuit definitions only.')
        elif directive.startswith('.'):
            if directive not in ('.model', '.param', '.global'):
                raise ValueError('Implementation views cannot contain '+words[0]+'. Capture dependent subcircuits in the same file; keep models in the project PDK.')
        elif not active or directive[0] not in 'rcldmqxvefghbik':
            raise ValueError('Unsupported or out-of-subcircuit implementation statement: '+words[0])
    if active or not found:
        raise ValueError('Implementation netlist has an incomplete or missing subcircuit.')
    return list(found.values())


def source_fingerprint(project, cell_id):
    """Include both hierarchies and model contents, excluding unrelated benches."""
    by = {c['id']: c for c in project['cells']}; cells = {}; pending = [cell_id]
    while pending:
        ident = pending.pop()
        if ident in cells:
            continue
        if ident not in by:
            raise ValueError('Implementation view references a missing source cell.')
        cell = by[ident]
        # Conservative invalidation includes drawing/constraint edits. It is
        # preferable to rerun extraction than to accept a changed physical source.
        cells[ident] = cell
        pending.extend(d['cell'] for d in cell['devices'] if d['kind'] == 'X')
        pending.extend(i['cell'] for i in cell.get('layout_instances', []))
    technology=clone(project['pdk'])
    # A locked package is identified by its contents, not its installation path.
    if technology.get('package_lock'):technology.pop('package_root',None)
    return digest({'cells': cells, 'pdk': technology,
                   'spice': project.get('spice'), 'parameters': project.get('parameters'),
                   'global_nets': project.get('global_nets')})


def capture(project, cell_id, name, text, top, kind='external', source_name=''):
    """Create a record; callers install it using the ordinary edit transaction."""
    from .model import validate
    project=validate(clone(project))
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError('Use an identifier for the implementation name.')
    if kind not in KINDS:
        raise ValueError('Choose capacitance, RC or external implementation.')
    cell = next((c for c in project['cells'] if c['id'] == cell_id), None)
    if cell is None:
        raise ValueError('Choose an existing circuit cell.')
    interfaces = subcircuits(text)
    interface = next((s for s in interfaces if s['name'].lower() == top.lower()), None)
    if interface is None:
        raise ValueError('The chosen top subcircuit is absent from the netlist.')
    if (len(interface['ports']) != len(cell['ports']) or
            {p.lower() for p in interface['ports']} != {p.lower() for p in cell['ports']}):
        raise ValueError('Implementation ports must match the circuit ports by name. Their order may differ.')
    if len({p.lower() for p in cell['ports']}) != len(cell['ports']):
        raise ValueError('Circuit ports collide in case-insensitive SPICE.')
    return {'id': uid(), 'name': name, 'cell_id': cell_id, 'kind': kind,
            'top': interface['name'], 'ports': interface['ports'], 'netlist': text,
            'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'source_fingerprint': source_fingerprint(project, cell_id),
            'source_name': Path(source_name).name, 'qualification': 'External netlist; DRC/LVS and extraction accuracy are not established by import.'}


def validate_views(project, objid=lambda _: None):
    records = project.get('implementation_views', [])
    if not isinstance(records, list) or len(records) > 50:
        raise ValueError('A project supports at most 50 implementation views.')
    names = set(); cells = {c['id']: c for c in project['cells']}
    for view in records:
        if not isinstance(view, dict):
            raise ValueError('Invalid implementation view.')
        objid(view['id']); key = (view.get('cell_id'), str(view.get('name', '')).casefold())
        if key in names or key[0] not in cells or not NAME.fullmatch(view.get('name', '')):
            raise ValueError('Implementation names must be unique within an existing cell.')
        names.add(key)
        if view.get('kind') not in KINDS or not re.fullmatch('[0-9a-f]{64}', view.get('source_fingerprint', '')):
            raise ValueError('Invalid implementation kind or source fingerprint.')
        text = view.get('netlist')
        interfaces = subcircuits(text)
        interface = next((s for s in interfaces if s['name'] == view.get('top')), None)
        if interface is None or interface['ports'] != view.get('ports'):
            raise ValueError('Implementation interface differs from its captured netlist.')
        if hashlib.sha256(text.encode('utf-8')).hexdigest() != view.get('sha256'):
            raise ValueError('Implementation netlist checksum changed.')


def get(project, ident, cell_id=None, *, require_current=True):
    view = next((v for v in project.get('implementation_views', []) if v['id'] == ident), None)
    if view is None or cell_id is not None and view['cell_id'] != cell_id:
        raise ValueError('Choose an implementation view belonging to this circuit.')
    validate_views(project)
    if require_current and source_fingerprint(project, view['cell_id']) != view['source_fingerprint']:
        raise ValueError('This implementation is stale: the circuit, layout or technology changed. Regenerate and capture its netlist again.')
    return view


def stage(project, ident, cell_id, directory):
    view = get(project, ident, cell_id)
    path = Path(directory) / 'implementation.spice'
    atomic_write(path, view['netlist'])
    cell = next(c for c in project['cells'] if c['id'] == cell_id)
    pins = {p.lower(): p for p in cell['ports']}
    return path, [pins[p.lower()] for p in view['ports']], view['top']


def describe(project, view):
    current = source_fingerprint(project, view['cell_id']) == view['source_fingerprint']
    return f"{view['name']} · {KINDS[view['kind']]}" + ('' if current else ' · Stale')
