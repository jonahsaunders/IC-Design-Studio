"""Versioned electrical/physical contracts shared by external-tool adapters.

The contract records meaning; upstream technology and extraction decks remain
authoritative. No process capabilities are inferred from a display name.
"""
import json
import math
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree

from .model import clone, digest, file_digest, atomic_write


def technology_contract(technology):
    lock = technology.get('package_lock', {})
    declared = clone(technology.get('interoperability', {}))
    if declared.get('version', 1) != 1:
        raise ValueError('Unsupported interoperability contract version.')
    layers = []
    for layer in technology['layers']:
        purpose = declared.get('layer_purposes', {}).get(layer['name'], layer.get('purpose', 'unspecified'))
        layers.append({'name': layer['name'], 'layer': layer['gds'],
                       'datatype': layer['datatype'], 'purpose': purpose})
    devices = {}
    for key, binding in technology.get('simulation', {}).get('catalog', {}).items():
        if binding.get('unavailable'):
            continue
        devices[key] = {'model': binding['model'], 'prefix': binding['prefix'],
                        'terminals': list(binding['pin_order']),
                        'parameter_scale': clone(binding.get('parameter_scale', {})),
                        'emit_parameters': clone(binding.get('emit_parameters', {})),
                        'parameters': clone(binding.get('parameters', {})),
                        'semantics': clone(declared.get('devices', {}).get(key, {}))}
    result = {'version': 1, 'pdk': {'id': lock.get('id', 'generic'),
               'revision': lock.get('revision', technology.get('revision', '')),
               'files_hash': digest(lock.get('files', {}))},
              'dbu_um': technology['dbu_um'], 'grid_nm': technology['grid'],
              'layers': layers, 'devices': devices,
              'global_nets': declared.get('global_nets', ['0']),
              'net_aliases': declared.get('net_aliases', {}),
              'tools': declared.get('tools', {})}
    validate_contract(result)
    return result


def validate_contract(contract):
    from .model import NET
    names = {row['name'] for row in contract['layers']}
    if len(names) != len(contract['layers']):
        raise ValueError('Interoperability layers must have unique names.')
    aliases = contract['net_aliases']
    if not isinstance(aliases, dict):
        raise ValueError('Net aliases must be an explicit mapping.')
    for name in list(contract['global_nets']) + list(aliases) + list(aliases.values()):
        if not isinstance(name, str) or not NET.fullmatch(name):
            raise ValueError('Invalid interoperability net name: ' + str(name))
    for name in aliases:
        seen = set()
        while name in aliases:
            if name in seen:
                raise ValueError('Cyclic interoperability net aliases.')
            seen.add(name); name = aliases[name]
    for key, device in contract['devices'].items():
        terminals = device['terminals']
        if len(terminals) != len(set(terminals)):
            raise ValueError(key + ': duplicate electrical terminals.')
        semantics = device['semantics']
        if semantics.get('body_terminal') and semantics['body_terminal'] not in terminals:
            raise ValueError(key + ': body terminal is absent from the device.')
        for value in device['parameter_scale'].values():
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(key + ': parameter scales must be positive and finite.')
    return contract


def project_contract(project):
    return {'version': 1, 'project_id': project['id'],
            'technology': technology_contract(project['pdk']),
            'cells': [{'id': c['id'], 'name': c['name'], 'ports': list(c['ports']),
                       'instances': [{'id': d['id'], 'name': d['name'], 'cell': d.get('cell'),
                                      'terminals': clone(d['nets']), 'model_ref': d.get('model_ref')}
                                     for d in c['devices']]} for c in project['cells']]}


def tool_asset(technology, tool, role, fallback=None):
    """Resolve a declared asset only through the exact PDK file lock."""
    relative = technology.get('interoperability', {}).get('tools', {}).get(tool, {}).get(role, fallback)
    if not relative:
        raise ValueError('This PDK has no ' + tool + ' ' + role + ' binding. Configure its interoperability contract.')
    root = Path(technology.get('package_root', '')).resolve()
    path = (root / relative).resolve()
    expected = technology.get('package_lock', {}).get('files', {}).get(relative)
    if not path.is_relative_to(root) or not expected:
        raise ValueError('Physical engine asset is absent from the PDK lock: '+str(relative))
    if not path.is_file() or file_digest(path) != expected:
        raise ValueError('Missing or changed locked ' + tool + ' asset: ' + str(relative))
    return path


def export_technology(technology, directory):
    """Produce a portable KLayout technology alongside the shared contract."""
    root = Path(directory); root.mkdir(parents=True, exist_ok=True)
    contract = technology_contract(technology)
    props = Element('layer-properties')
    for layer in technology['layers']:
        row = SubElement(props, 'properties')
        for key, value in [('name', layer['name']), ('source', f"{layer['gds']}/{layer['datatype']}@1"),
                           ('fill-color', layer['color']), ('frame-color', layer['color']), ('visible', 'true')]:
            SubElement(row, key).text = value
    ElementTree(props).write(root / 'layers.lyp', encoding='utf-8', xml_declaration=True)
    tech = Element('technology')
    for key, value in [('name', contract['pdk']['id']), ('description', technology['name']),
                       ('dbu', str(technology['dbu_um'])), ('layer-properties_file', 'layers.lyp'),
                       ('add-other-layers', 'true')]:
        SubElement(tech, key).text = value
    ElementTree(tech).write(root / 'technology.lyt', encoding='utf-8', xml_declaration=True)
    atomic_write(root / 'interoperability.json', json.dumps(contract, indent=2))
    return contract


def compare_interfaces(expected, actual, aliases=None):
    aliases = aliases or {}
    def resolve(name):
        seen = set()
        while name in aliases:
            if name in seen: raise ValueError('Cyclic net alias.')
            seen.add(name); name = aliases[name]
        return name
    left, right = [resolve(n) for n in expected], [resolve(n) for n in actual]
    return {'equal': left == right, 'expected': list(expected), 'actual': list(actual),
            'same_members': sorted(left) == sorted(right),
            'permutation': [right.index(n) for n in left] if len(set(right)) == len(right) and sorted(left) == sorted(right) else None}
