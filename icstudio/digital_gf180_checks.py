"""Combined strict native LVS and complete written-metal acceptance for GF180.

This bounded connectivity gate does not qualify fill, extracted performance,
device families, process corners or tapeout. Native diagnostics are retained.
"""
from collections import Counter
import json
import math
from pathlib import Path

from .digital_gf180_rules import LOCK
from .model import file_digest

RECIPE = 'gf180-5lm-native-connectivity-v1'
INPUTS = ('checkpoint', 'database', 'layout_preview', 'gds', 'lvs_reference', 'lvs_reference_report')
SCOPE = ('Strict native device/substrate LVS, primary device geometry and complete '
         'written-metal port/supply continuity for the captured GF180 C/D 5LM '
         '9-track implementation. Separate geometry, fill, extraction, timing, '
         'PVT, installation and tapeout acceptance remain required.')


def validate(platform):
    spec = platform.get('gf180_connectivity')
    if spec is None:
        return
    from .digital import relative_path
    from .digital_lvs_reference import validate as validate_reference
    validate_reference(platform)
    reference = platform.get('lvs_reference')
    if (not isinstance(spec, dict) or set(spec) != {'recipe', 'rules_root', 'masters'} or
            spec.get('recipe') != RECIPE or not reference or platform.get('name') not in ('gf180', 'gf180d')):
        raise ValueError('GF180 connectivity requires the captured independent reference recipe.')
    prefix = relative_path(spec['rules_root']) + '/'
    files = {f['path']: f for f in platform['files']}
    if {name[len(prefix):] for name in files if name.startswith(prefix)} != set(LOCK['files']):
        raise ValueError('Capture exactly the audited GF180 rule files and attribution.')
    for name, sha in LOCK['files'].items():
        if files.get(prefix + name, {}).get('sha256') != sha:
            raise ValueError('The complete audited GF180 rule recipe must be captured: ' + name)
    masters = spec['masters']
    if not isinstance(masters, dict) or set(masters) != set(reference['masters']):
        raise ValueError('Independent GDS and CDL master coverage must agree.')
    if any(not isinstance(p, str) or relative_path(p) not in files for p in masters.values()):
        raise ValueError('Independent GDS is missing from the captured platform.')
    if len(set(masters.values())) != len(masters):
        raise ValueError('Each independent GDS master needs a separate file.')


def inspect_database(path, reference):
    """Check native matching, full net mapping and every primary device field."""
    import klayout.db as k
    path = Path(path); sha = file_digest(path)
    db = k.LayoutVsSchematic(); db.read(str(path)); xref = db.xref()
    if xref is None:
        raise ValueError('Native LVS produced no comparison cross-reference.')
    pairs = list(xref.each_circuit_pair())
    issues = []
    if len(pairs) != 1 or pairs[0].first() is None or pairs[0].second() is None:
        raise ValueError('Native LVS must contain the complete captured top circuit.')
    pair = pairs[0]; left, right = pair.first(), pair.second()
    if left.name.casefold() != reference['top'].casefold() or right.name.casefold() != reference['top'].casefold():
        raise ValueError('Native LVS comparison belongs to another top circuit.')
    if str(pair.status()) != 'Match':
        issues.append('Native circuit comparison did not match.')
    logs = [dict(severity=str(e.severity), category=e.category_name, cell=e.cell_name, message=e.message)
            for e in db.each_log_entry()]
    if logs:
        issues.append('Native extraction has unresolved diagnostics.')
    rows = {name: list(method(left)) for name, method in
            [('net', xref.each_net_pair), ('device', xref.each_device_pair),
             ('pin', xref.each_pin_pair), ('instance', xref.each_subcircuit_pair)]}
    counts = {name: dict(Counter(str(p.status()) for p in items)) for name, items in rows.items()}
    mapping = {}
    for net in rows['net']:
        a, b = net.first(), net.second()
        if a is None or b is None or str(net.status()) not in ('Match', 'MatchWithWarning'):
            issues.append('Native net mapping is incomplete.'); continue
        mapping[a.expanded_name()] = b.expanded_name()
    if len(mapping) != len(rows['net']) or len(set(mapping.values())) != len(mapping):
        issues.append('Native net mapping is not one-to-one.')
    if rows['instance'] or list(left.each_subcircuit()) or list(right.each_subcircuit()):
        issues.append('Native reference comparison must be fully flattened.')
    expected_devices = sum(reference['device_counts'].values())
    if counts['device'] != {'Match': expected_devices} or counts['pin'] != {'Match': reference['top_ports']}:
        issues.append('Native device or top-port coverage differs from the captured reference.')
    checked_terminals = checked_parameters = 0
    kinds = Counter()
    for item in rows['device']:
        a, b = item.first(), item.second()
        if a is None or b is None or str(item.status()) != 'Match':
            continue
        ac, bc = a.device_class(), b.device_class()
        if isinstance(ac, k.DeviceClassMOS4Transistor) and isinstance(bc, k.DeviceClassMOS4Transistor):
            kind, terminals, primary = 'm', {'D', 'G', 'S', 'B'}, {'W', 'L'}
        elif isinstance(ac, k.DeviceClassDiode) and isinstance(bc, k.DeviceClassDiode):
            kind, terminals, primary = 'd', {'A', 'C'}, {'A', 'P'}
        else:
            issues.append('Unsupported native device class.'); continue
        kinds[kind] += 1
        if ac.name.casefold() != bc.name.casefold():
            issues.append('Native device models differ.')
        if ({t.name for t in ac.terminal_definitions()} != terminals or
                {t.name for t in bc.terminal_definitions()} != terminals or
                {p.name for p in ac.parameter_definitions() if p.is_primary} != primary or
                {p.name for p in bc.parameter_definitions() if p.is_primary} != primary):
            issues.append('Native device terminals or primary parameter coverage changed.'); continue
        at = {t: a.net_for_terminal(t) for t in terminals}
        bt = {t: b.net_for_terminal(t) for t in terminals}
        if any(n is None for n in [*at.values(), *bt.values()]):
            issues.append('Native device terminal is absent.'); continue
        mapped = {t: mapping.get(n.expanded_name()) for t, n in at.items()}
        expected = {t: n.expanded_name() for t, n in bt.items()}
        if mapped != expected and kind == 'm':
            mapped['D'], mapped['S'] = mapped['S'], mapped['D']
        if mapped != expected:
            issues.append('Native matched device disagrees with the complete net mapping.')
        checked_terminals += len(terminals)
        for name in sorted(primary):
            values = a.parameter(name), b.parameter(name)
            if not all(math.isfinite(v) and v > 0 for v in values) or not math.isclose(*values, rel_tol=1e-9, abs_tol=1e-12):
                issues.append('Native primary geometry differs: ' + ac.name + '/' + name)
            checked_parameters += 1
    if dict(kinds) != reference['device_counts']:
        issues.append('Native primitive coverage differs from the independent CDL.')
    for item in rows['pin']:
        a, b = item.first(), item.second()
        if a is None or b is None:
            continue
        an, bn = left.net_for_pin(a.id()), right.net_for_pin(b.id())
        if (a.name().casefold() != b.name().casefold() or an is None or bn is None or
                mapping.get(an.expanded_name()) != bn.expanded_name()):
            issues.append('Native top-port mapping differs.')
    if file_digest(path) != sha:
        raise ValueError('Native comparison changed during readback.')
    return dict(schema=1, passed=not issues, database_sha256=sha, top=reference['top'],
        circuit_status=str(pair.status()), counts=counts, device_counts=dict(kinds),
        checked_device_terminals=checked_terminals, checked_primary_parameters=checked_parameters,
        extraction_logs=logs, issues=list(dict.fromkeys(issues)))


def inspect_metal(gds, database, preview, library, *, top, variant):
    from . import gf180_connectivity as metal
    terminals = metal.capture(gds, database, preview, library, top_name=top, variant=variant)
    result = metal.inspect(gds, terminals)
    # Artifact bindings below retain portable paths. Absolute engine-host paths
    # must not prevent authenticated saved-job readback on another OS.
    for source in result['sources']:
        source.pop('path')
    return canonical_metal(result)


def canonical_metal(result):
    """Retain net equality and every finding without engine-local cluster IDs."""
    from copy import deepcopy
    result = deepcopy(result)
    names = {}
    def cluster(value):
        if value is None:
            return None
        if value not in names:
            names[value] = len(names) + 1
        return names[value]
    result['port_nets'] = {name: cluster(value) for name, value in sorted(result['port_nets'].items())}
    # Stable physical pin ordering names otherwise disconnected islands. Two
    # pins on the same island keep the same name; a split/short changes the
    # partition and therefore cannot be hidden by cluster renumbering.
    for finding in sorted(result['failures'], key=lambda f: json.dumps(f.get('pin', {}), sort_keys=True)):
        if 'ports' in finding:
            finding['ports'] = {name: cluster(value) for name, value in sorted(finding['ports'].items())}
        for key in ('actual_net', 'expected_net'):
            if key in finding:
                finding[key] = cluster(finding[key])
    result['net_identity'] = 'canonical-port-and-failure-partition-v1'
    return result


def verdict(native, metal):
    passed = native['passed'] and metal['passed']
    return dict(schema=1, status='connectivity_checks_passed' if passed else 'connectivity_checks_failed',
                passed=passed, qualified=False, scope=SCOPE, native=native, metal=metal)


def verify_layout(source, target, top):
    """Require identical physical masks and top texts, with no child labels."""
    import klayout.db as k
    paths = [Path(source), Path(target)]; hashes = [file_digest(p) for p in paths]
    layouts = []
    for path in paths:
        layout = k.Layout(); layout.read(str(path)); cells = list(layout.top_cells())
        if layout.dbu != .001 or len(cells) != 1 or cells[0].name != top:
            raise ValueError('Verification layout must retain the original top and 1 nm grid.')
        layouts.append((layout, cells[0]))
    def masks(layout, cell):
        return {(layout.get_info(i).layer, layout.get_info(i).datatype):k.Region(cell.begin_shapes_rec(i)).merged()
                for i in layout.layer_indexes()}
    a, b = [masks(*item) for item in layouts]; empty = k.Region()
    if any(not (a.get(layer, empty) ^ b.get(layer, empty)).is_empty() for layer in a.keys() | b.keys()):
        raise ValueError('Verification preparation changed a physical mask.')
    def top_text(layout, cell):
        return sorted((str(layout.get_info(i)), s.text.to_s()) for i in layout.layer_indexes()
                      for s in cell.shapes(i).each() if s.is_text())
    if top_text(*layouts[0]) != top_text(*layouts[1]):
        raise ValueError('Verification preparation changed top-level labels.')
    def children(layout, top):
        return sum(s.is_text() for c in layout.each_cell() if c != top
                   for i in layout.layer_indexes() for s in c.shapes(i).each())
    removed = children(*layouts[0])
    if children(*layouts[1]):
        raise ValueError('Verification layout retains child-cell labels in flat mode.')
    if [file_digest(p) for p in paths] != hashes:
        raise ValueError('Verification layout changed during mask readback.')
    return dict(source_sha256=hashes[0], verification_sha256=hashes[1], removed_child_labels=removed,
                all_physical_masks_unchanged=True, top_labels_unchanged=True, layers=len(a.keys() | b.keys()))


def prepare_layout(source, target, top):
    """Keep port labels at their own hierarchy scope during flat native LVS."""
    import klayout.db as k
    target = Path(target)
    if target.exists():
        raise ValueError('Preserve the existing verification layout.')
    layout = k.Layout(); layout.read(str(source)); tops = list(layout.top_cells())
    if len(tops) != 1 or tops[0].name != top:
        raise ValueError('Verification layout needs the captured top cell.')
    for cell in layout.each_cell():
        if cell == tops[0]:
            continue
        for layer in layout.layer_indexes():
            shapes = cell.shapes(layer)
            for shape in list(shapes.each()):
                if shape.is_text():
                    shapes.erase(shape)
    options = k.SaveLayoutOptions(); options.gds2_write_timestamps = False
    layout.write(str(target), options)
    return verify_layout(source, target, top)


def execute(r, reference):
    """Run both checks before accepting a configured physical finish result."""
    spec = r.platform.get('gf180_connectivity')
    if spec is None:
        return None
    validate(r.platform)
    if not reference or reference.get('status') != 'reference_generated':
        raise ValueError('Generate the complete captured reference before native connectivity checks.')
    keys = list(INPUTS)
    for key in keys:
        if file_digest(r.root/r.artifacts[key]['path']) != r.artifacts[key]['sha256']:
            raise ValueError('Captured connectivity input changed: ' + key)
    reference_report = json.loads((r.root/r.artifacts['lvs_reference_report']['path']).read_text(encoding='utf-8'))
    from .digital_lvs_reference import summary as reference_summary
    if (reference_summary(reference_report) != reference or reference_report['top'] != r.config['top'] or
            reference_report['reference_sha256'] != r.artifacts['lvs_reference']['sha256'] or
            reference_report['checkpoint_sha256'] != r.artifacts['checkpoint']['sha256'] or
            reference_report['platform_fingerprint'] != r.platform['fingerprint']):
        raise ValueError('Native connectivity needs the exact completed reference-generation result.')
    files = {f['path']: f for f in r.platform['files']}
    rule_root = r.root/'platform'/spec['rules_root']
    sources = {}
    for index, (name, sha) in enumerate(LOCK['files'].items()):
        path = rule_root/name
        if file_digest(path) != sha:
            raise ValueError('Audited native rule changed: ' + name)
        key = 'gf180_check_rule_' + str(index); r.add_artifact(key, path); sources[name] = key
    library = {}; library_artifacts = {}
    for index, name in enumerate(sorted({i['cell'] for i in reference_report['instances']})):
        path = spec['masters'][name]; key = 'gf180_check_master_' + str(index)
        library[name] = dict(path=r.root/'platform'/path, sha256=files[path]['sha256'])
        r.add_artifact(key, library[name]['path']); library_artifacts[name] = key
    output = r.root/'gf180-connectivity'
    output.mkdir(exist_ok=False)
    gds = r.root/r.artifacts['gds']['path']
    metal = inspect_metal(gds, r.root/r.artifacts['database']['path'], r.root/r.artifacts['layout_preview']['path'],
        library, top=r.config['top'], variant='C' if r.platform['name']=='gf180' else 'D')
    r.save_json('gf180_check_metal', metal, 'gf180-connectivity/metal.json')
    layout = prepare_layout(gds, output/'verification.gds', r.config['top'])
    r.add_artifact('gf180_check_gds', output/'verification.gds')
    switches = dict(thr='2', run_mode='flat', metal_top='9K' if r.platform['name']=='gf180' else '11K',
        mim_option='B', metal_level='5LM', poly_res='1k', mim_cap='2', lvs_sub='VSS', verbose='false',
        spice_net_names='true', spice_comments='false', scale='false', schematic_simplify='false',
        net_only='true', top_lvl_pins='true', combine='false', purge='false', purge_nets='false',
        topcell=r.config['top'], input=str(output/'verification.gds'), schematic=str(r.root/r.artifacts['lvs_reference']['path']),
        report=str(output/'comparison.lvsdb'), target_netlist=str(output/'extracted.cir'))
    command = [r.tools['klayout'], '-b', '-r', str(rule_root/LOCK['entry'])]
    for name, value in switches.items():
        command += ['-rd', name+'='+value]
    r.save_json('gf180_check_command', command, 'gf180-connectivity/command.json')
    r.command(command, 'Checking final circuit and substrate connections', cwd=rule_root/'klayout/lvs', fraction=.98)
    r.add_artifact('gf180_check_database', output/'comparison.lvsdb')
    r.add_artifact('gf180_check_extracted', output/'extracted.cir')
    native = inspect_database(output/'comparison.lvsdb', reference_report)
    result = verdict(native, metal)
    result.update(recipe=RECIPE, rules_revision=LOCK['revision'], platform_fingerprint=r.platform['fingerprint'], verification_layout=layout,
        variant='C' if r.platform['name']=='gf180' else 'D', top=r.config['top'],
        inputs={key:r.artifacts[key] for key in keys}, rule_artifacts=sources, library_artifacts=library_artifacts)
    # Recheck source files after engine execution; all native warnings stay in
    # the job log and comparison database, including failed jobs.
    for key in [*keys, *sources.values(), *library_artifacts.values()]:
        if file_digest(r.root/r.artifacts[key]['path']) != r.artifacts[key]['sha256']:
            raise ValueError('Connectivity input changed during native execution: ' + key)
    r.save_json('gf180_connectivity', result, 'gf180-connectivity/report.json')
    if not result['passed']:
        raise ValueError('Final GF180 connectivity failed. Inspect the native and metal reports.')
    return result


def validate_saved(data, root):
    root = Path(root); artifacts = data['artifacts']; declared = data.get('physical', {}).get('gf180_connectivity')
    policy = data.get('environment', {}).get('gf180_connectivity')
    if (declared is None and 'gf180_connectivity' not in artifacts and policy is None and
            not any(key.startswith('gf180_check_') for key in artifacts)):
        return None
    if not isinstance(declared, dict) or 'gf180_connectivity' not in artifacts:
        raise ValueError('Saved combined connectivity evidence is incomplete.')
    report = json.loads((root/artifacts['gf180_connectivity']['path']).read_text(encoding='utf-8'))
    if report != declared or not report.get('passed') or report.get('platform_fingerprint') != data.get('platform', {}).get('fingerprint'):
        raise ValueError('Saved combined connectivity does not match the implementation.')
    if (not policy or policy.get('recipe') != RECIPE or report.get('recipe') != RECIPE or
            report.get('rules_revision') != LOCK['revision']):
        raise ValueError('Saved connectivity has a different captured rule policy.')
    variant = {'gf180': 'C', 'gf180d': 'D'}.get(data.get('platform', {}).get('name'))
    if report.get('variant') != variant or variant is None or set(report.get('inputs', {})) != set(INPUTS):
        raise ValueError('Saved connectivity stack or input coverage changed.')
    for key, item in report['inputs'].items():
        if artifacts.get(key) != item:
            raise ValueError('Saved connectivity inputs differ from the captured artifacts.')
    if set(report['rule_artifacts']) != set(LOCK['files']):
        raise ValueError('Saved connectivity rule coverage is incomplete.')
    for name, key in report['rule_artifacts'].items():
        if (artifacts[key]['sha256'] != LOCK['files'][name] or
                artifacts[key]['path'] != 'platform/'+policy['rules_root']+'/'+name):
            raise ValueError('Saved connectivity rules differ from the audited recipe.')
    library = {}
    for master, key in report['library_artifacts'].items():
        if artifacts[key]['path'] != 'platform/'+policy['masters'].get(master, ''):
            raise ValueError('Saved independent GDS differs from the captured policy.')
        library[master] = dict(path=root/artifacts[key]['path'], sha256=artifacts[key]['sha256'])
    reference = json.loads((root/artifacts['lvs_reference_report']['path']).read_text(encoding='utf-8'))
    if set(library) != {i['cell'] for i in reference['instances']} or report['top'] != reference['top']:
        raise ValueError('Saved GDS and CDL reference coverage differ.')
    native = inspect_database(root/artifacts['gf180_check_database']['path'], reference)
    layout = verify_layout(root/artifacts['gds']['path'], root/artifacts['gf180_check_gds']['path'], report['top'])
    if report.get('verification_layout') != layout:
        raise ValueError('Saved verification layout differs from its captured preparation.')
    metal = inspect_metal(root/artifacts['gds']['path'], root/artifacts['database']['path'], root/artifacts['layout_preview']['path'],
        library, top=report['top'], variant=report['variant'])
    expected = verdict(native, metal)
    if not expected['passed'] or any(report.get(key) != value for key, value in expected.items()):
        raise ValueError('Saved combined connectivity no longer reproduces its native and metal checks.')
    return report
