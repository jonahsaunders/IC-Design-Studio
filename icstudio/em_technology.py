"""PDK-independent physical EM profiles. No process values are inferred."""
import math
import xml.etree.ElementTree as ET

from .model import clone, digest


KINDS = ('conductor', 'via', 'dielectric', 'substrate')


def technology_identity(tech):
    """Portable revision binding; installation paths and simulation settings are excluded."""
    lock = tech.get('package_lock', {})
    from .layout_routing import via_recipes
    physical = {k: tech.get(k) for k in ('grid', 'dbu_um')}
    # Generator installation can materialize already-effective connectivity.
    # Bind equivalent declarations identically so setup before creation works.
    physical['routing_vias'] = sorted(via_recipes(tech), key=lambda row: row['name'])
    physical['layer_kinds'] = layer_kinds(tech)
    physical['layers'] = sorted(
        [{k: layer.get(k) for k in ('name', 'gds', 'datatype', 'width', 'space')}
         for layer in tech['layers']], key=lambda row: row['name'])
    physical['locked_files'] = lock.get('files', {})
    return dict(id=lock.get('id') or tech.get('id') or tech['name'],
                revision=lock.get('revision') or tech.get('revision'),
                physical_hash=digest(physical))


def layer_kinds(tech):
    from .layout_routing import via_recipes
    kinds = {name: 'conductor' for name in tech.get('connectivity', {}).get('conductors', [])}
    for lower, cut, upper in tech.get('connectivity', {}).get('vias', []):
        kinds.update({lower: 'conductor', cut: 'via', upper: 'conductor'})
    for via in via_recipes(tech):
        kinds.update({via['lower']: 'conductor', via['cut']: 'via', via['upper']: 'conductor'})
    return kinds


def template(tech):
    """Draft data entry aid. Nulls deliberately cannot pass physical validation."""
    kinds = layer_kinds(tech)
    layers = [dict(name=row['name'], kind=kinds[row['name']], z_um=None,
                   thickness_um=None, conductivity_s_m=None)
              for row in tech['layers'] if row['name'] in kinds]
    return dict(schema=2, source='', technology=technology_identity(tech), layers=layers,
                layout_map={row['name']: row['name'] for row in layers}, excluded_layers={})


def validate_stackup(stack):
    if not isinstance(stack, dict) or not isinstance(stack.get('source'), str) or not stack['source'].strip():
        raise ValueError('EM stackup needs a named source and explicit physical layers.')
    if stack.get('schema', 2) != 2:
        raise ValueError('Use EM profile schema 2, or a legacy source/layers stackup.')
    layers = stack.get('layers')
    if not isinstance(layers, list) or not 1 <= len(layers) <= 2048:
        raise ValueError('EM stackup needs 1–2,048 layers.')
    names = set()
    for layer in layers:
        if not isinstance(layer, dict): raise ValueError('Each stackup layer must be an object.')
        name = layer.get('name'); kind = layer.get('kind')
        if not isinstance(name, str) or not name.strip() or name in names or len(name) > 128:
            raise ValueError('Stackup layer names must be unique, nonempty and at most 128 characters.')
        names.add(name)
        if set(layer) - {'name', 'kind', 'z_um', 'thickness_um', 'conductivity_s_m', 'epsilon_r', 'loss_tangent'}:
            raise ValueError(name + ': unsupported material/layer fields. This profile supports uniform isotropic layers; use a solver-specific model for other properties.')
        if kind not in KINDS:
            raise ValueError(name + ': choose conductor, via, dielectric or substrate.')
        for key in ('z_um', 'thickness_um'):
            value = layer.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or (key == 'thickness_um' and value <= 0):
                raise ValueError(name + ': declare finite elevation and positive thickness in µm.')
        if not math.isfinite(layer['z_um'] + layer['thickness_um']):
            raise ValueError(name + ': top elevation must be finite.')
        required = ('conductivity_s_m',) if kind in ('conductor', 'via') else ('epsilon_r',)
        for key in required:
            value = layer.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(name + ': declare positive ' + key + '.')
        for key in ('loss_tangent', 'conductivity_s_m'):
            if key in layer and (type(layer[key]) not in (int, float) or not math.isfinite(layer[key]) or layer[key] < 0):
                raise ValueError(name + ': ' + key + ' must be finite and nonnegative.')
        if 'epsilon_r' in layer and (type(layer['epsilon_r']) not in (int, float) or
                not math.isfinite(layer['epsilon_r']) or layer['epsilon_r'] <= 0):
            raise ValueError(name + ': epsilon_r must be finite and positive.')
    for key in ('layout_map', 'excluded_layers'):
        mapping = stack.get(key, {})
        if not isinstance(mapping, dict) or any(not isinstance(k, str) or not k.strip() or
                not isinstance(v, str) or not v.strip() for k, v in mapping.items()):
            raise ValueError(key + ': use layout layer names and nonempty text values.')
    physical = {l['name'] for l in layers if l['kind'] in ('conductor', 'via')}
    if set(stack.get('layout_map', {}).values()) - physical:
        raise ValueError('Map drawn layers to a declared physical conductor or via.')
    if set(stack.get('layout_map', {})) & set(stack.get('excluded_layers', {})):
        raise ValueError('A layout layer cannot be both mapped and excluded.')
    return clone(stack)


def bind_stackup(tech, stack):
    stack = validate_stackup(stack); identity = technology_identity(tech)
    if stack.get('technology') is not None and stack['technology'] != identity:
        raise ValueError('This EM profile belongs to a different PDK revision or layer map. '
                         'Create a profile for the selected technology and verify its physical data.')
    names = {l['name'] for l in tech['layers']}
    unknown = (set(stack.get('layout_map', {})) | set(stack.get('excluded_layers', {}))) - names
    if unknown: raise ValueError('Profile references unknown layout layers: ' + ', '.join(sorted(unknown)))
    stack['schema'] = 2; stack['technology'] = identity
    return stack


def mapping_for(tech, stack):
    if 'layout_map' in stack: return dict(stack['layout_map'])
    physical = {l['name'] for l in stack['layers'] if l['kind'] in ('conductor', 'via')}
    return {l['name']: l['name'] for l in tech['layers'] if l['name'] in physical}


def readiness(tech, stack, used, required=()):
    """Report every unmapped selected layer, including neighboring metal."""
    if not stack:
        return ['physical stackup with materials and substrate/dielectrics']
    try: checked = bind_stackup(tech, stack)
    except ValueError as exc: return [str(exc)]
    mapping = mapping_for(tech, checked); excluded = checked.get('excluded_layers', {})
    physical = {l['name']: l for l in checked['layers']}
    try: kinds = layer_kinds(tech)
    except ValueError as exc: return [str(exc)]
    missing = []
    for name in sorted(set(used) | set(required)):
        if name in excluded:
            if name in required or name in kinds:
                missing.append(name + ': conductors, vias and inductor layers cannot be excluded')
        elif name not in mapping:
            missing.append(name + ': map to a physical layer (or explicitly exclude a non-electrical marker)')
        elif name in kinds and physical[mapping[name]]['kind'] != kinds[name]:
            missing.append(name + ': expected physical ' + kinds[name])
    if not any(l['kind'] in ('dielectric', 'substrate') for l in checked['layers']):
        missing.append('dielectric/substrate environment')
    return missing


def capabilities(tech):
    from .layout_routing import via_recipes
    try:
        geometry = bool(via_recipes(tech)); kinds = layer_kinds(tech)
        reason = '' if geometry else 'Declare routing_vias and layer width/spacing rules.'
    except (ValueError, KeyError, TypeError) as exc:
        geometry = False; kinds = {}; reason = str(exc)
    issues = readiness(tech, tech.get('em_stackup'), kinds)
    return dict(geometry=geometry, geometry_reason=reason, profile_ready=not issues,
                profile_issues=issues, solver_integrated=False)


def solver_stackup(stack, mapping):
    """Absolute-position XML for the documented gds2openEMS/gds2palace subset.

    Each physical drawn layer receives a unique number. The companion GDS must
    use this table: upstream stackup XML does not distinguish GDS datatypes.
    """
    stack = validate_stackup(stack)
    layers = {l['name']: l for l in stack['layers']}
    environment = sorted([l for l in layers.values() if l['kind'] in ('dielectric', 'substrate')],
                         key=lambda l: l['z_um'])
    if not environment: raise ValueError('Declare a dielectric/substrate environment before XML export.')
    for a, b in zip(environment, environment[1:]):
        top = a['z_um'] + a['thickness_um']
        if not math.isclose(top, b['z_um'], abs_tol=1e-9, rel_tol=1e-12):
            raise ValueError('XML export needs contiguous, non-overlapping dielectric slabs: '
                             + a['name'] + ' / ' + b['name'] + '. Declare any air gap explicitly.')
    root = ET.Element('Stackup', schemaVersion='2.0')
    materials = ET.SubElement(root, 'Materials'); elayers = ET.SubElement(root, 'ELayers', LengthUnit='um')
    dielectric_xml = ET.SubElement(elayers, 'Dielectrics'); drawn_xml = ET.SubElement(elayers, 'Layers')
    selected = set(mapping.values()); numbers = {name: i + 1 for i, name in enumerate(sorted(selected))}
    for name in selected:
        layer = layers[name]
        if layer['z_um'] < environment[0]['z_um'] - 1e-9 or layer['z_um'] + layer['thickness_um'] > environment[-1]['z_um'] + environment[-1]['thickness_um'] + 1e-9:
            raise ValueError(name + ': declare dielectric or air slabs covering the complete conductor height for XML export.')
    material_names = {name: 'em_material_' + str(i) for i, name in
                      enumerate(sorted(selected | {l['name'] for l in environment}))}
    for name in sorted(selected | {l['name'] for l in environment}):
        layer = layers[name]; kind = layer['kind']
        attrs = dict(Name=material_names[name], Type='Conductor' if kind in ('conductor', 'via') else
                     'Semiconductor' if kind == 'substrate' else 'Dielectric',
                     Permittivity=str(layer.get('epsilon_r', 1)),
                     Conductivity=str(layer.get('conductivity_s_m', 0)),
                     DielectricLossTangent=str(layer.get('loss_tangent', 0)))
        ET.SubElement(materials, 'Material', **attrs)
    for layer in reversed(environment):
        ET.SubElement(dielectric_xml, 'Dielectric', Name=layer['name'], Material=material_names[layer['name']],
                      Zmin=str(layer['z_um']), Zmax=str(layer['z_um'] + layer['thickness_um']))
    for name, number in numbers.items():
        layer = layers[name]
        ET.SubElement(drawn_xml, 'Layer', Name=name, Type=layer['kind'], Material=material_names[name],
                      Layer=str(number), Zmin=str(layer['z_um']),
                      Zmax=str(layer['z_um'] + layer['thickness_um']))
    ET.indent(root)
    return ET.tostring(root, encoding='unicode', xml_declaration=True), numbers
