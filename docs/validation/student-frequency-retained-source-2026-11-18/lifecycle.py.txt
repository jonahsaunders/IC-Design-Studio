"""Reviewed project copies, PDK relocation, migration, and device replacement."""
from pathlib import Path
import json, os
from .model import clone, uid, now, digest, file_digest, validate, load_project
from .catalog import create_device, binding_for, link_technology, parameter_values


def duplicate_project(project, destination, name=None):
    """Create an independent project, retaining internal references and PDK lock."""
    p = clone(project)
    p.update(id=uid(), name=name or project['name']+' copy', revision=0,
             created=now(), modified=now(), waivers=[])
    p['copied_from'] = {'project_id': project['id'], 'design_hash': digest(project)}
    validate(p)
    destination = Path(destination).resolve()
    if destination.suffix != '.icproj':
        raise ValueError('Choose a new .icproj file for the independent copy.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents overwriting even if a file appears after the dialog.
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(p, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.flush(); os.fsync(stream.fileno())
    return p


def relocate_project(index, old_path, new_path):
    old_path = str(Path(old_path).resolve())
    record = next(e for e in index.entries() if e['path'] == old_path)
    p = load_project(new_path)
    if p['id'] != record['id']:
        raise ValueError('The selected file is a different project. Use Browse to open it.')
    index.remember(p, new_path)
    if old_path != str(Path(new_path).resolve()): index.forget(old_path)
    return p


def relink_assets(project, folder):
    lock = project['pdk'].get('package_lock')
    if not lock: raise ValueError('The project has no locked PDK.')
    root = Path(folder).resolve()
    for rel, sha in lock['files'].items():
        path = (root/rel).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_digest(path) != sha:
            raise ValueError('The replacement folder does not match the locked asset: '+rel)
    project['pdk']['package_root'] = str(root)


def replacement(technology, old, key, old_binding=None):
    """Retain pin geometry/IDs so wires, labels and physical links stay attached."""
    new = create_device(technology, key, old['name'], old['x'], old['y'])
    if set(new['nets']) != set(old['nets']) or new['kind'] != old['kind']:
        raise ValueError('Replacement requires the same device kind and named terminals.')
    new.update(id=old['id'], rotation=old['rotation'], nets=clone(old['nets']))
    from .symbol_io import device_symbol
    new['symbol'] = clone(old.get('symbol') or device_symbol(old))
    for field in ('symbol', 'net_labels'):
        if field in old: new[field] = clone(old[field])
    if old['kind'] in ('NMOS', 'PMOS'):
        for field in ('w','l'): new['params'][field] = old['params'][field]
    binding = binding_for(technology, new)
    notes = []
    for param, raw in old.get('model_params', {}).items():
        if param in binding.get('parameters', {}): new['model_params'][param] = raw
        else: notes.append('Drop override '+param+'='+str(raw))
    for param, rule in binding.get('parameters', {}).items():
        before = (old_binding or {}).get('parameters', {}).get(param, {}).get('default')
        if ''.join(str(before).lower().split()) != ''.join(str(rule['default']).lower().split()) and param not in new['model_params'] and not (new['kind'] in ('NMOS','PMOS') and param in ('w','l')):
            notes.append(param+': default '+str(before)+' → '+str(rule['default']))
    if old_binding and old_binding.get('emit_parameters') != binding.get('emit_parameters'):
        notes.append('Netlist parameter mapping changes')
    parameter_values(binding, new)
    return new, notes


def migration_preview(project, technology, mapping=None):
    """Build a fully validated candidate; no mutation of the source project."""
    old_lock = project['pdk'].get('package_lock', {})
    new_lock = technology.get('package_lock', {})
    if not old_lock or old_lock.get('id') != new_lock.get('id'):
        raise ValueError('Revision migration requires the same PDK identity. Cross-process conversion needs explicit layer and device adapters.')
    candidate = clone(project); report = []
    for cell in candidate['cells']:
        for i, old in enumerate(cell['devices']):
            if not old.get('model_ref'):
                if binding_for(project['pdk'], old):
                    raise ValueError('Replace legacy kind-wide bindings with explicit catalog devices before migrating.')
                continue
            old_key = old['model_ref']['device']; key = (mapping or {}).get(old_key, old_key)
            before = binding_for(project['pdk'], old)
            new, notes = replacement(technology, old, key, before)
            cell['devices'][i] = new
            report.append({'cell': cell['name'], 'instance': old['name'], 'from': before['model'],
                           'to': binding_for(technology,new)['model'], 'notes': notes})
    # References now match the target. Existing mask numbers must still match.
    link_technology(candidate, technology)
    candidate['pdk_migration'] = {'from': old_lock, 'to': new_lock,
                                  'source_hash': digest(project), 'changes': report}
    validate(candidate)
    return candidate, report
