"""Validate the bounded chunk-3 record; density and tapeout stay separate."""
import hashlib
import json
import math
from pathlib import Path
import re

PLATFORMS = {'sky130hd', 'gf180', 'gf180d', 'ihp-sg13g2'}
TARGETS = {'sky130A', 'gf180mcuC', 'gf180mcuD', 'ihp-sg13g2'}
RECIPES = {'gf180': ('C', 'gf180-9t-5lm-9k-geometry-v1'),
           'gf180d': ('D', 'gf180-9t-5lm-11k-geometry-v1')}
HOSTED_STEPS = {
    'Install pinned implementation toolchain',
    'Isolate the pinned implementation executables',
    'Require actual KLayout Ruby rules and deliberate geometry failure',
    'Require real mapped timing, equivalence, fault detection and RTL to GDS',
    'Require SKY130, GF180 C/D and IHP counter implementation and extracted timing',
    'Require UART and APB FIFO proof and physical closure on all four profiles',
    'Require final antenna and power-grid checks with actual layout faults',
    'Require independent SKY130 library and interconnect corner coverage',
}


def require(condition, message):
    if not condition:
        raise ValueError('GF180 geometry acceptance: ' + message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def identity(value, length=64):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value)


def counts(value):
    require(set(value) == {'main', 'antenna', 'density'}
            and all(type(n) is int and n >= 0 for n in value.values()), 'missing/invalid full-rule counts.')
    require(value['main'] == value['antenna'] == 0, 'geometry or antenna findings remain.')


def timing(value, platform):
    expected = {(c, r) for c in ('typical', 'slow', 'fast')
                for r in (('minimum', 'nominal', 'maximum') if platform == 'sky130hd' else (None,))}
    corners = value['corners']
    require(len(corners) == len(expected)
            and {(c['corner'], c.get('rc_corner')) for c in corners} == expected, 'incomplete timing pairs.')
    for result in [value, *corners]:
        require(result['status'] == 'PASS' and result['parasitics'] == 'extracted SPEF'
                and result['unconstrained'] is False and not result['incomplete_reasons'], 'timing is incomplete or failed.')
        require(type(result.get('path_count')) is int and result['path_count'] > 0, 'missing timing paths.')
        summary = result['summary']
        for prefix in ('setup', 'hold'):
            slack = summary[prefix + '_worst_slack_ns']
            require(type(slack) in (int, float) and math.isfinite(slack) and slack >= 0, 'negative/invalid timing slack.')
            total = summary[prefix + '_total_negative_slack_ns']
            violations = summary[prefix + '_reported_violations']
            require(type(total) in (int, float) and math.isfinite(total) and total == 0
                    and type(violations) is int and violations == 0, 'invalid timing totals or remaining violations.')


def checks(values, expected):
    require(len(values) == len(expected) and {v['name'] for v in values} == set(expected), 'missing/duplicate design stage.')
    result = {v['name']: v for v in values}
    for name, verdict in expected.items():
        require(identity(result[name]['result_sha256']), 'missing stage identity.')
        if verdict is not None:
            require(result[name]['verdict'] == verdict, 'unexpected design verdict: ' + name)
    return result


def validate(record, production):
    """Records must follow independently audited native execution, never create it."""
    require(record['schema'] == 1 and record['chunk'] == 3
            and record['status'] == 'passed_reference_scope', 'missing completed reference gate.')
    require(record.get('scope') and record.get('limitations'), 'missing scope boundaries.')
    require(identity(record['source_commit'], 40) and identity(record['backend_sha256'])
            and identity(record['archive_sha256']) and identity(record['manifest_sha256']), 'invalid source/runtime identity.')
    require(bool(record['source_files']) and all(identity(h) for h in record['source_files'].values())
            and digest(record['source_files']) == record['backend_sha256'], 'backend source identity mismatch.')
    require(production['source_commit'] == record['source_commit']
            and production['backend'] == record['backend_sha256']
            and production['source_files'] == record['source_files']
            and production['runtime']['sha256'] == record['archive_sha256'], 'production evidence belongs to another source/runtime.')
    require(production['status'] == 'geometry-timing-equivalence-passed', 'production batch incomplete.')
    workloads = production['workloads']
    require(len(workloads) == 4 and {(d['platform'], d['design']) for d in workloads}
            == {(p, d) for p in RECIPES for d in ('uart', 'apb')}, 'independent C/D UART/APB coverage required.')
    technology = {}
    for design in workloads:
        platform = design['platform']; variant, recipe = RECIPES[platform]
        require(design['variant'] == variant, 'wrong production variant.')
        counts(design['rule_counts'])
        stages = checks(design['checks'], {'behavior': 'PASS', 'mapped': None, 'equivalent': 'PASS',
            'fault-detected': 'FAIL', 'pre-layout-timing': None, 'finished': None,
            'extracted-timing': 'PASS', 'physical-equivalent': 'PASS'})
        timing(stages['extracted-timing']['timing'], platform)
        finished = stages['finished']
        require(finished['recipe']['recipe'] == recipe and finished['physical_checks']['status'] == 'PASS'
                and finished['router_checks']['detailed_route_drc_errors'] == [0], 'incomplete production physical evidence.')
        require(identity(finished['technology_lef_sha256']) and identity(design['constraint_sha256']), 'missing technology/constraint identity.')
        technology[(platform, design['design'])] = finished['technology_lef_sha256']
        if platform == 'gf180d':
            require('1p5m_1tm_11k' in finished['extraction_rules']
                    and identity(finished['extraction_rules_sha256']), 'D extraction must use its captured 11K rules.')
    require(all(technology[('gf180', d)] != technology[('gf180d', d)] for d in ('uart', 'apb')),
            'C technology cannot substitute for D technology.')
    require(production['library_corner_checks'] == 12, 'incomplete production timing count.')
    require(set(record['operating_systems']) == {'Linux', 'Windows'}, 'both operating systems required.')
    for system, result in record['operating_systems'].items():
        require(result['audit_status'] == 'passed' and identity(result['full_runtime_audit_sha256']), 'independent runtime audit missing.')
        accepted = result['acceptance']
        require(accepted['backend'] == record['backend_sha256']
                and accepted['manifest'] == record['manifest_sha256']
                and accepted['runtime']['sha256'] == record['archive_sha256']
                and accepted['runtime']['kind'] == ('linux' if system == 'Linux' else 'wsl'), 'installed source/runtime/OS mismatch.')
        require(len(accepted['platforms']) == 4 and set(accepted['platforms']) == PLATFORMS, 'all four installed profiles required.')
        stages = ('mapped', 'equivalence', 'fault-detected', 'timing', 'floorplan', 'gds', 'extracted-timing', 'physical-equivalence')
        names = {'icarus', 'verilator-coverage'} | {p + '/' + s for p in PLATFORMS for s in stages}
        require(len(result['digital_checks']) == 34 and {c['name'] for c in result['digital_checks']} == names, 'incomplete installation checks.')
        require(result['timing_pairs'] == 18 and len(result['platforms']) == 4
                and {p['name'] for p in result['platforms']} == PLATFORMS, 'incomplete installed timing/platform coverage.')
        platforms = {}
        for platform in result['platforms']:
            name = platform['name']
            captured = checks(platform['checks'], {'mapped': None, 'equivalence': 'PASS', 'fault-detected': 'FAIL',
                'timing': None, 'floorplan': None, 'gds': None, 'extracted-timing': 'PASS', 'physical-equivalence': 'PASS'})
            timing(captured['extracted-timing']['timing'], name)
            finished = captured['gds']; platforms[name] = finished
            require(finished['physical']['checks']['status'] == 'PASS'
                    and platform['router_checks']['detailed_route_drc_errors'] == [0], 'installed physical checks failed.')
            require(identity(finished['macro_export']['sha256']) and finished['macro_export']['notices'], 'audited attributed export missing.')
            if name in RECIPES:
                require(finished['geometry_recipe']['recipe'] == RECIPES[name][1], 'installed geometry recipe mismatch.')
        controls(result, platforms, record)
        rules = result['full_rules_audit']
        require(rules['status'] == 'geometry_passed' and rules['system'] == system
                and rules['backend'] == record['backend_sha256']
                and rules['runtime_archive_sha256'] == record['archive_sha256']
                and rules['runtime_audit_sha256'] == result['full_runtime_audit_sha256'], 'installed full-rule audit mismatch.')
        require(len(rules['cases']) == 2 and {c['platform'] for c in rules['cases']} == set(RECIPES), 'both installed GF180 variants need full rules.')
        for case in rules['cases']:
            counts(case['counts']); platform = case['platform']
            require(case['variant'] == RECIPES[platform][0] and case['geometry_passed'] is True
                    and case['density_passed'] is (case['counts']['density'] == 0), 'wrong rule variant or hidden density failure.')
            require(case['result_sha256'] == platforms[platform]['result_sha256']
                    and case['gds_sha256'] == platforms[platform]['artifacts']['gds']['sha256'], 'rules refer to another installed layout.')
            require(len(case['reports']) == 3 and {r['group'] for r in case['reports']} == {'main', 'antenna', 'density'}
                    and all(r['markers'] == case['counts'][r['group']] and identity(r['sha256']) for r in case['reports']), 'native rule report coverage mismatch.')
    hosted = record['hosted']
    require(hosted['head_sha'] == record['source_commit'], 'hosted source mismatch.')
    require(len(hosted['steps']) == len(HOSTED_STEPS) and {s['name'] for s in hosted['steps']} == HOSTED_STEPS
            and all(s['status'] == 'completed' and s['conclusion'] == 'success' for s in hosted['steps']), 'required hosted execution incomplete.')
    require(isinstance(record.get('retained_failures'), list), 'failure history must remain explicit.')


def controls(result, platforms, record):
    tools = result['physical_tool_checks']
    expected = {'drc-legal', 'drc-narrow', 'lvs-equal', 'lvs-wrong', 'ngspice', 'klayout-legal', 'klayout-narrow'}
    require(len(tools) == 7 and {t['name'] for t in tools} == expected
            and all(t['status'] == 'passed' for t in tools), 'engine controls incomplete.')
    by_name = {t['name']: t for t in tools}
    for name, count in (('legal', 0), ('narrow', 1)):
        require(type(by_name['drc-' + name]['count']) is int and by_name['drc-' + name]['count'] == count, 'invalid Magic rule control.')
        klayout = by_name['klayout-' + name]
        require(type(klayout['markers']) is int and type(klayout['converted_edges']) is int
                and klayout['markers'] == klayout['converted_edges'] == count
                and klayout['version'] == 'KLayout 0.30.5', 'invalid KLayout native rule control.')
    process = result['process_audit']
    require(process['status'] == 'passed' and process['backend'] == record['backend_sha256']
            and process['runtime'] == result['acceptance']['runtime'], 'process-control source/runtime mismatch.')
    expected = {(t, k + '-' + s) for t in TARGETS for k in ('drc', 'lvs') for s in ('fault', 'repaired')}
    require(len(process['cases']) == 16 and {(c['target'], c['case']) for c in process['cases']} == expected, 'process controls incomplete.')
    for case in process['cases']:
        faulty = case['case'].endswith('-fault')
        require(case['native_status'] == ('failed' if faulty else 'passed'), 'process fault/repair outcome is wrong.')
        if case['case'].startswith('drc-'):
            require(type(case['drc_count']) is int and case['drc_count'] >= 0
                    and (case['drc_count'] > 0) == faulty, 'missing actual process-rule finding.')
    digital = result['digital_audit']
    expected = {(p, c) for p in PLATFORMS for c in ('baseline', 'removed-grid', 'antenna-route')}
    require(digital['status'] == 'passed' and digital['native_cases'] == 12 and len(digital['cases']) == 12
            and {(c['platform'], c['case']) for c in digital['cases']} == expected, 'digital fault controls incomplete.')
    for case in digital['cases']:
        require(case['status'] == 'passed' and case['expected_check_status'] == ('PASS' if case['case'] == 'baseline' else 'FAIL'), 'digital fault verdict is wrong.')
        require(case['source']['result_sha256'] == platforms[case['platform']]['result_sha256'], 'fault control uses another installed layout.')


def bound_production(reference, root):
    root = Path(root).resolve(); path = (root / reference['path']).resolve()
    require(path.is_relative_to(root), 'production evidence escapes the repository.')
    require(hashlib.sha256(path.read_bytes()).hexdigest() == reference['sha256'], 'production evidence hash changed.')
    return json.loads(path.read_text(encoding='utf-8'))
