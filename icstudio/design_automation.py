"""Versioned, revision-checked design commands shared by scripts and the editor.

Commands address stable master-cell/object IDs. Editing a reused master affects
every occurrence; hierarchy paths are for navigation, not implicit uniquification.
No arbitrary Python or expression evaluation is performed by this API.
"""
from dataclasses import asdict

from .model import History, clone, design_digest, digest, validate


API_VERSION = '1.0'
MAX_COMMANDS = 10000
COMMAND_FIELDS = {
    'add_shape': {'cell_id', 'shape'},
    'add_device': {'cell_id', 'device'},
    'set_parameter': {'cell_id', 'device_id', 'name', 'value', 'namespace'},
    'set_source': {'cell_id', 'device_id', 'values'},
    'set_cell_parameters': {'cell_id', 'values'},
    'rename_device': {'cell_id', 'device_id', 'name'},
    'move_device': {'cell_id', 'device_id', 'x', 'y', 'rotation', 'mirror'},
    'connect_pin': {'cell_id', 'device_id', 'pin', 'net'},
    'switch_cell_view': {'cell_id', 'device_id', 'view_cell_id'},
}


def capabilities():
    return {'api_version': API_VERSION, 'commands': sorted(COMMAND_FIELDS),
            'parameter_namespaces': ['auto', 'intrinsic', 'model', 'native', 'instance'],
            'max_commands': MAX_COMMANDS, 'atomic': True, 'undo_steps_per_batch': 1,
            'scope': 'master cell; all occurrences share edits',
            'cell_views': 'explicit interface-compatible schematic master substitution'}


def envelope(project, commands, label='Automation batch'):
    """Create the optimistic concurrency token before a script starts editing."""
    return {'api_version': API_VERSION, 'project_id': project['id'],
            'base_revision': project['revision'], 'base_design_hash': design_digest(project),
            'label': label, 'commands': clone(commands)}


def _cell(project, ident):
    result = next((c for c in project['cells'] if c['id'] == ident), None)
    if result is None:
        raise ValueError('Unknown cell ID: ' + str(ident))
    return result


def _device(cell, ident):
    result = next((d for d in cell['devices'] if d['id'] == ident), None)
    if result is None:
        raise ValueError('Unknown device ID in ' + cell['name'] + ': ' + str(ident))
    return result


def resolve_path(project, instance_path=(), root_cell_id=None):
    """Resolve a list of stable instance IDs, returning the master and breadcrumbs."""
    if not isinstance(instance_path, (list, tuple)) or len(instance_path) > 12:
        raise ValueError('Hierarchy paths contain at most 12 instance IDs.')
    cell = _cell(project, root_cell_id or project['top'])
    breadcrumbs = [{'cell_id': cell['id'], 'name': cell['name']}]
    for ident in instance_path:
        instance = _device(cell, ident)
        if instance['kind'] != 'X':
            raise ValueError(instance['name'] + ' is not a hierarchical instance.')
        cell = _cell(project, instance['cell'])
        breadcrumbs.append({'instance_id': ident, 'instance_name': instance['name'],
                            'cell_id': cell['id'], 'name': cell['name']})
    return cell, breadcrumbs


def inspect(project, instance_path=(), root_cell_id=None):
    """Return navigable cell views, interfaces, stable references and revision token."""
    p = validate(clone(project))
    active, breadcrumbs = resolve_path(p, instance_path, root_cell_id)
    parents = {c['id']: [] for c in p['cells']}
    for c in p['cells']:
        for d in c['devices']:
            if d['kind'] == 'X':
                parents[d['cell']].append({'cell_id': c['id'], 'device_id': d['id'], 'name': d['name']})
    cells = []
    for c in p['cells']:
        cells.append({'id': c['id'], 'name': c['name'], 'ports': c['ports'],
                      'parameters': c.get('parameters', {}), 'parents': parents[c['id']],
                      'views': ['schematic'] + (['layout'] if c['shapes'] or c.get('layout_instances') else []),
                      'devices': len(c['devices']), 'shapes': len(c['shapes'])})
    devices = []
    for d in active['devices']:
        row = {k: clone(d[k]) for k in ('id', 'name', 'kind', 'nets', 'x', 'y', 'rotation',
                                      'value', 'params', 'model_params', 'parameters', 'cell') if k in d}
        if d.get('native_spice'):
            row['native_parameters'] = clone(d['native_spice'].get('parameters', {}))
        if d['kind'] == 'X':
            child = _cell(p, d['cell'])
            row['compatible_views'] = [c['id'] for c in p['cells']
                if c['id'] != active['id'] and c['ports'] == child['ports']
                and set(c.get('parameters', {})) == set(child.get('parameters', {}))]
        devices.append(row)
    return {'api_version': API_VERSION, 'project_id': p['id'], 'revision': p['revision'],
            'design_hash': design_digest(p), 'top': p['top'], 'cell_id': active['id'],
            'breadcrumbs': breadcrumbs, 'cells': cells, 'devices': devices,
            'edit_scope': 'Edits to this master affect every occurrence.'}


def _check_base(project, request):
    if not isinstance(request, dict) or request.get('api_version') != API_VERSION:
        raise ValueError('Automation requires api_version ' + API_VERSION + '.')
    if request.get('project_id') != project['id']:
        raise ValueError('Automation batch belongs to a different project.')
    if type(request.get('base_revision')) is not int or request['base_revision'] != project['revision']:
        raise ValueError('Stale automation batch: project revision changed. Inspect and preview again.')
    if request.get('base_design_hash') != design_digest(project):
        raise ValueError('Stale automation batch: design content changed. Inspect and preview again.')


def _check_request(project, request):
    _check_base(project, request)
    allowed = {'api_version', 'project_id', 'base_revision', 'base_design_hash', 'label', 'commands'}
    if set(request) - allowed:
        raise ValueError('Unknown automation batch fields: ' + ', '.join(sorted(set(request) - allowed)))
    commands = request.get('commands')
    if not isinstance(commands, list) or not 1 <= len(commands) <= MAX_COMMANDS:
        raise ValueError('An automation batch needs 1–10,000 commands.')
    if not isinstance(request.get('label', 'Automation batch'), str) or not 1 <= len(request.get('label', 'Automation batch')) <= 128:
        raise ValueError('Batch label must be 1–128 characters.')
    for i, command in enumerate(commands):
        if not isinstance(command, dict) or command.get('type') not in COMMAND_FIELDS:
            raise ValueError('Command ' + str(i + 1) + ': unsupported command type.')
        unknown = set(command) - COMMAND_FIELDS[command['type']] - {'type'}
        if unknown:
            raise ValueError('Command ' + str(i + 1) + ': unknown fields: ' + ', '.join(sorted(unknown)))


def _set_parameter(project, device, command):
    name, value = command['name'], command['value']
    namespace = command.get('namespace', 'auto')
    if namespace == 'auto':
        namespace = 'native' if name in device.get('native_spice', {}).get('parameters', {}) else 'intrinsic'
    if namespace == 'intrinsic':
        if device.get('native_spice'):
            raise ValueError('Native devices require the native parameter namespace.')
        if name == 'value' and device['kind'] in ('R', 'C', 'L', 'V', 'I'):
            device['value'] = value
        elif device['kind'] in ('NMOS', 'PMOS') and name in ('w', 'l', 'vto', 'kp', 'lambda'):
            device['params'][name] = value
        else:
            raise ValueError('Unsupported intrinsic parameter: ' + str(name))
    elif namespace == 'native':
        parameters = device.get('native_spice', {}).get('parameters', {})
        if name not in parameters:
            raise ValueError('Unknown native parameter: ' + str(name))
        parameters[name] = str(value)
    elif namespace == 'model':
        from .catalog import binding_for
        binding = binding_for(project['pdk'], device)
        if not binding or name not in binding.get('parameters', {}):
            raise ValueError('Unknown PDK model parameter: ' + str(name))
        if device['kind'] in ('NMOS', 'PMOS') and name in ('w', 'l'):
            raise ValueError('MOS width and length use the intrinsic namespace and SI units.')
        device.setdefault('model_params', {})[name] = value
    elif namespace == 'instance':
        if device['kind'] != 'X' or name not in _cell(project, device['cell']).get('parameters', {}):
            raise ValueError('Unknown hierarchical instance parameter: ' + str(name))
        device.setdefault('parameters', {})[name] = value
    else:
        raise ValueError('Unsupported parameter namespace: ' + str(namespace))


def _execute(project, command):
    from . import wiring
    from .electrical_identity import require_preserved
    cell = _cell(project, command['cell_id'])
    kind = command['type']
    if kind == 'add_shape':
        cell['shapes'].append(clone(command['shape']))
        return
    if kind == 'add_device':
        device = clone(command['device'])
        if 'wires' in cell:
            device['net_labels'] = clone(device['nets'])
        cell['devices'].append(device)
        wiring.rebuild(cell, project)
        return
    if kind == 'set_cell_parameters':
        values = command['values']
        if not isinstance(values, dict) or set(values) - set(cell.get('parameters', {})):
            raise ValueError('Only declared cell parameters can be updated.')
        cell.setdefault('parameters', {}).update(clone(values))
        return
    device = _device(cell, command['device_id'])
    if kind == 'set_parameter':
        _set_parameter(project, device, command)
    elif kind == 'set_source':
        if device['kind'] not in ('V', 'I') or device.get('native_spice'):
            raise ValueError('Source editing requires a generic V or I source.')
        values = command['values']
        if not isinstance(values, dict) or set(values) - set(device['source']):
            raise ValueError('Unknown source waveform fields.')
        device['source'].update(clone(values))
    elif kind == 'rename_device':
        device['name'] = command['name']
    elif kind == 'move_device':
        before = clone(cell)
        positions = wiring.pins(cell, project) if 'wires' in cell else None
        for key in ('x', 'y', 'rotation', 'mirror'):
            if key in command:
                device[key] = command[key]
        if positions is not None:
            wiring.keep_connections(cell, positions, project)
            wiring.rebuild(cell, project)
            require_preserved(before, cell)
    elif kind == 'connect_pin':
        if command['pin'] not in device['nets']:
            raise ValueError('Unknown device pin: ' + str(command['pin']))
        if 'wires' in cell:
            wiring.set_label(cell, device['id'], command['pin'], command['net'], project)
        else:
            device['nets'][command['pin']] = command['net']
    elif kind == 'switch_cell_view':
        if device['kind'] != 'X':
            raise ValueError('Cell view switching requires a hierarchical instance.')
        old = _cell(project, device['cell'])
        new = _cell(project, command['view_cell_id'])
        if old['ports'] != new['ports'] or set(old.get('parameters', {})) != set(new.get('parameters', {})):
            raise ValueError('Cell views require the same ordered ports and parameter interface.')
        if any(i.get('device_id') == device['id'] for i in cell.get('layout_instances', [])):
            raise ValueError('This instance has a linked physical placement. Reconcile its physical view before substituting a schematic master.')
        device['cell'] = new['id']


def apply_to_project(project, request):
    """Mutator for an existing History.commit/capture_commit transaction only."""
    _check_request(project, request)
    physical_cells = {c['cell_id'] for c in request['commands'] if c['type'] == 'add_shape'}
    before = clone(project) if physical_cells else None
    for i, command in enumerate(request['commands']):
        try:
            _execute(project, command)
        except (ValueError, KeyError, TypeError, StopIteration) as exc:
            raise ValueError('Command ' + str(i + 1) + ' (' + command['type'] + '): ' + str(exc)) from exc
    if physical_cells:
        # Check the complete candidate, including physical ancestors of reused
        # masters. Schematic sizing may intentionally require a later layout ECO.
        validate(project)
        from .route_constraints import enforce_affected
        enforce_affected(before, project, physical_cells)


def commit_batch(history, request):
    """Commit all commands as one undoable edit, or preserve every history field."""
    request = clone(request)
    _check_request(history.project, request)
    before_hash = design_digest(history.project)
    before_revision = history.project['revision']
    history.commit(lambda p: apply_to_project(p, request), request.get('label', 'Automation batch'))
    return {'api_version': API_VERSION, 'project_id': history.project['id'],
            'base_revision': before_revision, 'revision': history.project['revision'],
            'before_hash': before_hash, 'design_hash': design_digest(history.project),
            'commands': len(request['commands']), 'change': asdict(history.last_change),
            'results_stale': before_hash != design_digest(history.project)}


def preview(project, request):
    """Build the exact candidate, including generated wire IDs, without side effects."""
    _check_request(project, request)
    history = History(clone(project))
    report = commit_batch(history, request)
    return {'base': {k: request[k] for k in ('api_version', 'project_id', 'base_revision', 'base_design_hash')},
            'project': history.project, 'candidate_hash': digest(history.project), 'report': report}


def install_preview(project, proposal):
    """Install a reviewed candidate inside an editor transaction, rejecting staleness."""
    _check_base(project, proposal['base'])
    candidate = proposal['project']
    if digest(candidate) != proposal['candidate_hash']:
        raise ValueError('Automation preview content changed. Preview again.')
    if candidate['id'] != project['id'] or candidate['revision'] != project['revision'] + 1:
        raise ValueError('Automation preview has an invalid project or revision.')
    candidate = validate(clone(candidate))
    project.clear()
    project.update(candidate)


def dispatch(method, params):
    """JSON-RPC adapter; the caller owns transport and error envelopes."""
    if method == 'automation.capabilities':
        return capabilities()
    if method == 'automation.inspect':
        return inspect(params['project'], params.get('instance_path', []), params.get('root_cell_id'))
    if method == 'automation.preview':
        return preview(params['project'], params['batch'])
    if method == 'automation.apply':
        # This stateless RPC returns a new project; it cannot mutate a GUI session.
        proposal = preview(params['project'], params['batch'])
        return {'project': proposal['project'], 'report': proposal['report']}
    raise ValueError('Unsupported automation method: ' + method)
