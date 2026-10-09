"""Validate coverage bookkeeping, never infer process qualification from it."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / 'docs/qualification/pdk-matrix.json'
TARGETS = ('sky130A', 'gf180mcuC', 'gf180mcuD', 'ihp-sg13g2')
STATUSES = {'not_run', 'partial', 'failed', 'needs_definition', 'unsupported', 'passed_reference'}
HOSTED_TOOLCHAIN_STEPS = {
    'Install pinned implementation toolchain',
    'Isolate the pinned implementation executables',
    'Require actual KLayout Ruby rules and deliberate geometry failure',
    'Require real mapped timing, equivalence, fault detection and RTL to GDS',
    'Require SKY130, GF180 and IHP counter implementation and extracted timing',
    'Require UART and APB FIFO proof and physical closure on all three profiles',
    'Require final antenna and power-grid checks with actual layout faults',
    'Require independent SKY130 library and interconnect corner coverage',
}
COMMON_TESTS = {
    'inventory', 'operating-envelope', 'tool-install', 'rule-controls',
    'device-interface', 'device-simulation', 'device-physical', 'source-completeness',
    'rc-reference', 'rc-corners', 'coupling', 'analog-mirror', 'analog-differential',
    'analog-amplifier', 'analog-reference', 'analog-oscillator', 'analog-noise',
    'analog-statistics', 'digital-controller', 'mixed-signal', 'clock-reset',
    'chip-assembly', 'chip-erc', 'chip-esd-latchup', 'chip-em-ir', 'chip-io-package',
    'desktop', 'independent-export', 'foundry-acceptance',
}
EXTRA_TESTS = {
    'sky130A': {'sky130-full-rules'},
    'gf180mcuC': {'gf180-geometry', 'gf180-density'},
    'gf180mcuD': {'gf180-geometry', 'gf180-density', 'digital-profile'},
    'ihp-sg13g2': {'ihp-fill', 'ihp-bipolar', 'ihp-rf'},
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def family(name, device):
    """Qualification batches; keep the original catalog category separately."""
    name = name.lower()
    if 'annotate' in name or name.endswith(('/corner.sym', '/gallery.sym')):
        return 'utility'
    if any(s in name for s in ('npn', 'pnp')):
        return 'bipolar'
    if any(s in name for s in ('nfet', 'pfet', 'nmoscl', 'sg13_lv_', 'sg13_hv_')):
        return 'mos'
    if any(s in name for s in ('cap', 'varicap')):
        return 'capacitor'
    if 'inductor' in name:
        return 'inductor'
    if device['category'] == 'Resistors' or Path(name).stem in {
        'nplus_u', 'pplus_u', 'nwell', 'npolyf_s', 'npolyf_u', 'ppolyf_s',
        'ppolyf_u', 'ppolyf_u_1k', 'ppolyf_u_1k_6p0', 'ppolyf_u_2k',
        'ppolyf_u_2k_6p0', 'ppolyf_u_3k', 'rm1', 'rm2', 'rm3',
        'rhigh', 'rppd', 'rsil', 'res_generic_li',
    }:
        return 'resistor'
    if device['category'] == 'Diodes':
        return 'diode'
    return 'other'


def inventory(root=ROOT):
    base = Path(root) / 'icstudio/assets/pdks'
    collection = read(base / 'collection.json')
    entries = {e['variant']: e for e in collection['packages']}
    if set(entries) != set(TARGETS):
        raise ValueError('Bundled target inventory changed; review qualification scope.')
    result = {}
    for target in TARGETS:
        folder = base / target
        p = read(folder / 'package.json')
        if sha(folder / 'package.json') != entries[target]['manifest_sha256']:
            raise ValueError('Bundled manifest hash differs: ' + target)
        for name, digest in p['files'].items():
            asset = (folder / name).resolve()
            if not asset.is_relative_to(folder.resolve()) or sha(asset) != digest:
                raise ValueError('Bundled asset changed: ' + target + '/' + name)
        sim = p['technology']['simulation']
        devices = {}
        for name, device in sorted(sim['catalog'].items()):
            devices[name] = {k: device.get(k) for k in (
                'category', 'model', 'model_source', 'source', 'pin_order',
                'parameters', 'emit_parameters', 'parameter_scale', 'unavailable')}
            devices[name]['family'] = family(name, device)
            devices[name]['rf_batch'] = ('rf' in name.lower() or 'inductor' in name.lower()
                                        or 'varicap' in name.lower())
        locks = {name: {'sha256': sha(folder / name), 'content': read(folder / name)}
                 for name in ('UPSTREAM-LOCK.json', 'PHYSICAL-SOURCE-LOCK.json')
                 if (folder / name).is_file()}
        # Individual file identities already live in the hash-locked package.
        for lock in locks.values():
            lock['content'].pop('files', None)
            if isinstance(lock['content'].get('models'), dict):
                lock['content']['models'].pop('files', None)
        result[target] = {
            'revision': p['revision'], 'manifest_sha256': sha(folder / 'package.json'),
            'asset_count': len(p['files']), 'indexed_count': len(devices),
            'placeable_count': sum(not d['unavailable'] for d in devices.values()),
            'source_locks': locks, 'model_includes': sim['includes'],
            'requires_osdi': sim.get('requires_osdi', False),
            'physical': p['technology']['physical'], 'devices': devices,
        }
    return result


def validate_toolchain_record(record):
    """Require the entire declared reference gate; no full-PDK claim follows."""
    def require(condition, message):
        if not condition:
            raise ValueError('Toolchain acceptance: ' + message)
    require(record.get('chunk') == 2 and record.get('status') == 'passed_reference_scope',
            'missing completed reference gate.')
    for key, length in (('source_commit', 40), ('backend_sha256', 64), ('archive_sha256', 64)):
        require(isinstance(record.get(key), str)
                and bool(re.fullmatch('[0-9a-f]{' + str(length) + '}', record[key])),
                'invalid source/runtime identity: ' + key)
    require(bool(record.get('scope')) and bool(record.get('limitations')), 'missing scope boundaries.')
    require(set(record.get('operating_systems', {})) == {'Linux', 'Windows'}, 'both operating systems required.')
    platforms = {'sky130hd', 'gf180', 'ihp-sg13g2'}
    analog_cases = {(t, c) for t in TARGETS for c in ('drc-fault', 'drc-repaired', 'lvs-fault', 'lvs-repaired')}
    digital_cases = {(p, c) for p in platforms for c in ('baseline', 'removed-grid', 'antenna-route')}
    tool_names = {'drc-legal', 'drc-narrow', 'lvs-equal', 'lvs-wrong', 'ngspice', 'klayout-legal', 'klayout-narrow'}
    for system, result in record['operating_systems'].items():
        acceptance = result['acceptance']
        require(acceptance['backend'] == record['backend_sha256']
                and acceptance['runtime']['sha256'] == record['archive_sha256'], system + ' identity mismatch.')
        require(acceptance['runtime']['kind'] == ('linux' if system == 'Linux' else 'wsl'), system + ' execution platform mismatch.')
        require(set(acceptance['platforms']) == platforms, system + ' missing digital platform.')
        require(result['installation_checks'] == 26 and result['timing_pairs'] == 15
                and result['macro_exports'] == 3, system + ' incomplete installation evidence.')
        tools = result['physical_tool_checks']
        require(len(tools) == len(tool_names) and {t['name'] for t in tools} == tool_names
                and all(t['status'] == 'passed' for t in tools), system + ' missing/failed engine control.')
        by_name = {t['name']: t for t in tools}
        for name, count in (('legal', 0), ('narrow', 1)):
            drc = by_name['drc-' + name]
            require(type(drc.get('count')) is int and drc['count'] == count,
                    system + ' invalid native width-rule evidence.')
            check = by_name['klayout-' + name]
            require(type(check.get('markers')) is int and type(check.get('converted_edges')) is int
                    and check['markers'] == check['converted_edges'] == count
                    and check['version'] == 'KLayout 0.30.5', system + ' invalid KLayout rule evidence.')
        analog = result['process_rule_controls']
        require(len(analog) == len(analog_cases) and {(c['target'], c['case']) for c in analog} == analog_cases,
                system + ' incomplete process controls.')
        for case in analog:
            require(case['native_status'] == ('failed' if case['case'].endswith('-fault') else 'passed'),
                    system + ' unexpected process control outcome.')
            if case['case'].startswith('drc-'):
                require(type(case.get('drc_count')) is int and case['drc_count'] >= 0
                        and (case['drc_count'] > 0) == case['case'].endswith('-fault'),
                        system + ' missing actual DRC finding.')
        digital = result['digital_controls']
        require(len(digital) == len(digital_cases) and {(c['platform'], c['case']) for c in digital} == digital_cases,
                system + ' incomplete physical digital controls.')
        for case in digital:
            require(case['status'] == 'passed'
                    and case['expected_check_status'] == ('PASS' if case['case'] == 'baseline' else 'FAIL'),
                    system + ' unexpected digital control outcome.')
        require(result['audit_status'] == 'passed', system + ' independent audit missing.')
    hosted = record['hosted']
    require(hosted['head_sha'] == record['source_commit'], 'hosted result is for another source.')
    steps = hosted['steps']
    require(len(steps) == len(HOSTED_TOOLCHAIN_STEPS)
            and {s['name'] for s in steps} == HOSTED_TOOLCHAIN_STEPS
            and all(s['status'] == 'completed' and s['conclusion'] == 'success' for s in steps),
            'required hosted execution has not passed.')
    require(type(record['old_cli_control'].get('exit')) is int and record['old_cli_control']['exit'] != 0
            and record['old_cli_control']['missing_interface'] == 'RBA::EdgePairToEdgeOperator',
            'incompatible-engine negative control missing.')


def validate(matrix, root=ROOT):
    root = Path(root)
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    require(matrix['schema'] in (1, 2, 3, 4), 'Unsupported matrix schema.')
    require(matrix['inventory'] == inventory(root), 'Matrix inventory is stale or incomplete.')
    require(set(matrix['targets']) == set(TARGETS), 'Missing or extra qualification target.')
    tests = matrix['tests']
    needed = COMMON_TESTS | set.union(*EXTRA_TESTS.values())
    require(set(tests) == needed, 'Test definitions are incomplete or unexpected.')
    for name, test in tests.items():
        require(1 <= test['chunk'] <= 12, 'Invalid chunk: ' + name)
        for field in ('fixture', 'procedure', 'expected_result', 'conditions', 'automation_gap'):
            require(bool(test.get(field)), 'Missing test contract ' + name + ':' + field)
        for path in test['existing_runners']:
            require((root / path).is_file(), 'Missing runner: ' + path)
    requirements = matrix['requirements']
    chunk2 = matrix.get('execution_acceptance', {}).get('2')
    if chunk2:
        require(matrix['schema'] in (2, 3, 4), 'Execution acceptance needs schema 2, 3 or 4.')
        require(sha(root / chunk2['path']) == chunk2['sha256'], 'Toolchain acceptance record changed.')
        validate_toolchain_record(read(root / chunk2['path']))
    chunk3 = matrix.get('execution_acceptance', {}).get('3')
    if chunk3:
        require(matrix['schema'] in (3, 4) and bool(chunk2), 'Geometry acceptance needs schema 3 or 4 and the preceding toolchain gate.')
        require(sha(root / chunk3['path']) == chunk3['sha256'], 'Geometry acceptance record changed.')
        # Keep script invocation and package imports working without importing
        # application code into this evidence-only validator.
        if __package__:
            from .check_gf180_geometry_acceptance import bound_production, validate as validate_geometry
        else:
            from check_gf180_geometry_acceptance import bound_production, validate as validate_geometry
        record = read(root / chunk3['path'])
        validate_geometry(record, bound_production(record['production_evidence'], root))
    chunk4 = matrix.get('execution_acceptance', {}).get('4')
    if chunk4:
        require(matrix['schema'] == 4 and bool(chunk3), 'Density acceptance needs schema 4 and the preceding geometry gate.')
        require(sha(root / chunk4['path']) == chunk4['sha256'], 'Density acceptance record changed.')
        if __package__:
            from .check_gf180_density_acceptance import validate as validate_density
        else:
            from check_gf180_density_acceptance import validate as validate_density
        validate_density(read(root / chunk4['path']), root)
    expected = {target + ':' + test for target in TARGETS
                for test in COMMON_TESTS | EXTRA_TESTS[target]}
    require(set(requirements) == expected, 'Requirement coverage differs from required targets/tests.')
    for identity, req in requirements.items():
        target, test = identity.split(':')
        require(req['target'] == target and req['test'] == test, 'Misbound requirement: ' + identity)
        require(req['status'] in STATUSES, 'Unsupported qualification claim: ' + identity)
        if req['status'] == 'passed_reference':
            require((bool(chunk2) and test in ('tool-install', 'rule-controls') and req.get('acceptance_chunk') == 2)
                    or (bool(chunk3) and target in ('gf180mcuC', 'gf180mcuD')
                        and test in ('gf180-geometry', 'digital-profile') and req.get('acceptance_chunk') == 3)
                    or (bool(chunk4) and target in ('gf180mcuC', 'gf180mcuD')
                        and test == 'gf180-density' and req.get('acceptance_chunk') == 4),
                    'Unbound reference pass: ' + identity)
        require(bool(req['remaining']), 'Missing coverage gap: ' + identity)
        for evidence in req['historical_evidence']:
            require(evidence in matrix['evidence'], 'Unknown evidence: ' + evidence)
    for target in TARGETS:
        info = matrix['targets'][target]
        for field in ('metal_stack', 'digital_profile', 'operating_conditions', 'uncovered_scope'):
            require(bool(info.get(field)), 'Missing target definition: ' + target + ':' + field)
        devices = matrix['device_requirements'][target]
        require(set(devices) == set(matrix['inventory'][target]['devices']),
                'Device omitted or added: ' + target)
        for name, device in devices.items():
            require(set(device['tests']) == {'device-interface', 'device-simulation', 'device-physical'},
                    'Incomplete device coverage: ' + target + '/' + name)
            require(device['status'] in STATUSES - {'passed_reference'} and bool(device['remaining']),
                    'Unsupported device claim: ' + target + '/' + name)
            if matrix['inventory'][target]['devices'][name]['unavailable']:
                require(device['status'] == 'unsupported', 'Unavailable device promoted: ' + name)
    for name, evidence in matrix['evidence'].items():
        require(sha(root / evidence['path']) == evidence['sha256'], 'Evidence changed: ' + name)
        require(bool(evidence['scope_limit']), 'Missing evidence scope: ' + name)
    require(set(matrix['chunks']) == {str(n) for n in range(1, 13)}, 'Missing chunk.')
    require(matrix['chunks']['1']['status'] == 'matrix_defined', 'Chunk 1 definition missing.')
    require(matrix['chunks']['2']['status'] in ('pending', 'in_progress') or
            (bool(chunk2) and matrix['chunks']['2']['status'] == 'reference_gate_complete'),
            'Toolchain execution gate needs its complete acceptance record.')
    require(matrix['chunks']['3']['status'] in ('pending', 'in_progress') or
            (bool(chunk3) and matrix['chunks']['3']['status'] == 'reference_gate_complete'),
            'Geometry execution gate needs its complete acceptance record.')
    require(matrix['chunks']['4']['status'] in ('pending', 'in_progress') or
            (bool(chunk4) and matrix['chunks']['4']['status'] == 'reference_gate_complete'),
            'Completed execution requires the bound density acceptance record.')
    require(all(matrix['chunks'][str(n)]['status'] in ('pending', 'in_progress') for n in range(5, 13)),
            'Completed execution requires a new, reviewed evidence schema.')
    return {'status': 'matrix_consistent', 'process_qualification': 'unqualified',
            'targets': len(TARGETS), 'requirements': len(requirements),
            'device_entries': sum(len(d) for d in matrix['device_requirements'].values()),
            'requirement_statuses': dict(Counter(r['status'] for r in requirements.values()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', type=Path, default=MATRIX)
    args = parser.parse_args()
    print(json.dumps(validate(read(args.matrix)), indent=2))


if __name__ == '__main__':
    main()
