"""Plan reviewed PDK changes while preserving the original design."""
from .catalog import binding_for, link_technology
from .collaboration_document import LAYOUT_FIELDS
from .lifecycle import replacement
from .model import clone, digest, validate

PHYSICAL_FIELDS = (*LAYOUT_FIELDS, 'routing_records')


def technology_label(technology):
    lock = technology.get('package_lock')
    if lock:
        return f"{lock['id']}@{lock['revision']}"
    return f"{technology['name']} · {technology['revision']}"


def same_family(source, target):
    lock = source.get('package_lock')
    return bool(lock and lock['id'] == target.get('package_lock', {}).get('id'))


def mapping_groups(project, target):
    """Group instances that share a source model and named terminal interface."""
    used = {}
    for cell in project['cells']:
        for device in cell['devices']:
            binding = binding_for(project['pdk'], device)
            if not binding:
                continue
            ref = device.get('model_ref')
            key = (ref['device'] if ref else '', device['kind'], tuple(sorted(device['nets'])))
            group = used.setdefault(key, {'label': ref['device'] if ref else binding['model'], 'count': 0})
            group['count'] += 1
    catalog = target.get('simulation', {}).get('catalog', {})
    available = {}
    for key, entry in catalog.items():
        if not entry.get('unavailable'):
            interface = entry['kind'], tuple(sorted(entry['pin_order']))
            available.setdefault(interface, []).append((key, entry['label'], entry['model']))
    return [(key, group, sorted(available.get(key[1:], []), key=lambda row: (row[1].casefold(), row[0])))
            for key, group in used.items()]


def needs_copy(project, target, shared=False, lesson=False):
    if shared or lesson:
        return True
    return not same_family(project['pdk'], target) and (
        any(cell.get(field) for cell in project['cells'] for field in PHYSICAL_FIELDS)
        or bool(project.get('implementation_views'))
        or any(binding_for(project['pdk'], d) for cell in project['cells'] for d in cell['devices'])
    )


def switch_preview(project, target, mapping, use_target_defaults=False):
    """Return a validated design and an explicit list of process-dependent changes."""
    source = project['pdk']
    in_family = same_family(source, target)
    if (target == source or (source.get('package_lock') and
            source['package_lock'] == target.get('package_lock'))):
        raise ValueError('This is the active PDK. Choose another revision or process.')
    candidate, changes, effects = _change_bindings(project, target, mapping, use_target_defaults, in_family)
    if in_family:
        effects.append('Layout remains linked to this process family. Rerun physical verification and extraction.')
    _reset_analysis(candidate, effects, in_family)
    if candidate.get('waivers'):
        candidate['waivers'] = []
        effects.append('Verification waivers cleared. Review findings against the target decks.')
    candidate['pdk_migration'] = dict(from_pdk=technology_label(source), to_pdk=technology_label(target),
                                      source_hash=digest(project), changes=changes)
    validate(candidate)
    return candidate, changes, effects


def _change_bindings(project, target, mapping, use_target_defaults, in_family):
    if not in_family and (
        project.get('spice', {}).get('assets') or project.get('spice', {}).get('library_lock')
        or any(d['kind'] in ('XS', 'SPICE') or d.get('native_spice')
               for cell in project['cells'] for d in cell['devices'])
        or any(cell.get('spice_statements') for cell in project['cells'])
        or any(s['settings']['type'] in ('xschem', 'program') for s in project.get('simulation_setups', []))
    ):
        raise ValueError('This design has native SPICE or Xschem dependencies. Reimport its source against the target PDK in a separate project so its includes and models can be reviewed.')
    candidate = clone(project)
    changes, effects = [], []
    removed = 0
    for cell in candidate['cells']:
        if not in_family:
            for field in PHYSICAL_FIELDS:
                removed += len(cell.pop(field, []))
            cell['shapes'] = []
        for index, old in enumerate(cell['devices']):
            before = binding_for(project['pdk'], old)
            if not before:
                if binding_for(target, old):
                    old['model_mode'] = 'generic'
                    changes.append(dict(cell=cell['name'], instance=old['name'], **{
                        'from': 'generic', 'to': 'generic', 'notes': ['Kept the original generic model.']}))
                continue
            ref = old.get('model_ref')
            key = (ref['device'] if ref else '', old['kind'], tuple(sorted(old['nets'])))
            if key not in mapping:
                raise ValueError(f"Choose a target model for {cell['name']}/{old['name']}.")
            try:
                new, notes = replacement(target, old, mapping[key], before,
                                         use_target_defaults=use_target_defaults, project=candidate, cell=cell)
            except (ValueError, KeyError, ArithmeticError, SyntaxError) as exc:
                raise ValueError(f"{cell['name']}/{old['name']}: {exc}") from exc
            cell['devices'][index] = new
            changes.append(dict(cell=cell['name'], instance=old['name'], **{
                'from': before['model'], 'to': binding_for(target, new)['model'], 'notes': notes}))
    # Devices now use target references. Validate layer compatibility for revisions.
    candidate['pdk'] = target if not in_family else candidate['pdk']
    link_technology(candidate, target)
    if removed:
        effects.append(f'{removed} layout objects and routing records stay with the source project.')
    return candidate, changes, effects


def _reset_analysis(candidate, effects, in_family):
    effects.append('Analysis uses the nominal corner. Review bias, supplies, corners, and design targets before running.')
    if not in_family:
        views = candidate.pop('implementation_views', [])
        if views:
            effects.append(f'{len(views)} saved implementation views stay with the source project.')
        if candidate.pop('simulation_runtime', None):
            effects.append('Custom simulation runtime settings stay with the source project.')
    for bench in candidate.get('testbenches', []):
        bench['analysis']['corner'] = 'nominal'
        if not in_family:
            bench.pop('implementation_view', None)
            if 'characterization' in bench:
                bench['characterization']['compare_layout'] = False
    for setup in candidate.get('simulation_setups', []):
        if setup['settings']['type'] in ('op', 'tran', 'dc', 'ac', 'noise'):
            setup['settings']['corner'] = 'nominal'
    for plan in candidate.get('test_plans', []):
        plan['corners'] = ['nominal']
        if not in_family:
            plan['compare_layout'] = False
        for entry in plan['entries']:
            if entry['engine'] != 'digital':
                entry['settings']['corner'] = 'nominal'
