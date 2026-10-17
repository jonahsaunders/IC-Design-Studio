"""Synthetic record mutations test rejection logic; these are not EDA evidence."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.check_gf180_geometry_acceptance import HOSTED_STEPS, PLATFORMS, RECIPES, TARGETS, bound_production, digest, validate


def fixture():
    def timing(platform):
        base = {'status': 'PASS', 'parasitics': 'extracted SPEF', 'unconstrained': False,
                'incomplete_reasons': [], 'path_count': 1,
                'summary': {key: 0 for key in ('setup_worst_slack_ns', 'hold_worst_slack_ns',
                    'setup_total_negative_slack_ns', 'hold_total_negative_slack_ns',
                    'setup_reported_violations', 'hold_reported_violations')}}
        pairs = [(c, r) for c in ('typical', 'slow', 'fast')
                 for r in (('minimum', 'nominal', 'maximum') if platform == 'sky130hd' else (None,))]
        return {**base, 'corners': [{**copy.deepcopy(base), 'corner': c, 'rc_corner': r} for c, r in pairs]}
    def stages(names):
        return [{'name': name, 'verdict': verdict, 'result_sha256': '1' * 64} for name, verdict in names.items()]
    source = {'synthetic-fixture.py': 'a' * 64}; backend = digest(source)
    record = {'schema': 1, 'chunk': 3, 'status': 'passed_reference_scope', 'scope': 'SYNTHETIC TEST ONLY',
              'limitations': ['Never written as qualification.'], 'source_files': source,
              'source_commit': 'b' * 40, 'backend_sha256': backend, 'archive_sha256': 'c' * 64,
              'manifest_sha256': 'd' * 64, 'operating_systems': {}, 'retained_failures': [],
              'hosted': {'head_sha': 'b' * 40, 'steps': [{'name': name, 'status': 'completed', 'conclusion': 'success'}
                                                      for name in sorted(HOSTED_STEPS)]}}
    production = {'source_commit': record['source_commit'], 'source_files': source, 'backend': backend,
                  'runtime': {'sha256': 'c' * 64}, 'status': 'geometry-timing-equivalence-passed',
                  'library_corner_checks': 12, 'workloads': []}
    for platform in RECIPES:
        for design in ('uart', 'apb'):
            values = stages({'behavior': 'PASS', 'mapped': None, 'equivalent': 'PASS', 'fault-detected': 'FAIL',
                'pre-layout-timing': 'FAIL', 'finished': None, 'extracted-timing': 'PASS', 'physical-equivalent': 'PASS'})
            next(c for c in values if c['name'] == 'extracted-timing')['timing'] = timing(platform)
            next(c for c in values if c['name'] == 'finished').update(
                recipe={'recipe': RECIPES[platform][1]}, physical_checks={'status': 'PASS'},
                router_checks={'detailed_route_drc_errors': [0]}, technology_lef_sha256=('e' if platform == 'gf180' else 'f') * 64,
                extraction_rules='openROAD/rcx/gf180mcu_1p5m_1tm_11k_wst.rules', extraction_rules_sha256='2' * 64)
            production['workloads'].append({'platform': platform, 'variant': RECIPES[platform][0], 'design': design,
                'rule_counts': {'main': 0, 'antenna': 0, 'density': 555}, 'checks': values, 'constraint_sha256': '3' * 64})
    for system, kind in (('Linux', 'linux'), ('Windows', 'wsl')):
        runtime = {'kind': kind, 'sha256': 'c' * 64}
        tools = [{'name': n, 'status': 'passed'} for n in ('drc-legal', 'drc-narrow', 'lvs-equal', 'lvs-wrong', 'ngspice')]
        tools[0]['count'] = 0; tools[1]['count'] = 1
        tools += [{'name': 'klayout-' + n, 'status': 'passed', 'markers': c, 'converted_edges': c,
                   'version': 'KLayout 0.30.5'} for n, c in (('legal', 0), ('narrow', 1))]
        native = {'mapped': None, 'equivalence': 'PASS', 'fault-detected': 'FAIL', 'timing': 'FAIL',
                  'floorplan': None, 'gds': None, 'extracted-timing': 'PASS', 'physical-equivalence': 'PASS'}
        result = {'audit_status': 'passed', 'full_runtime_audit_sha256': '4' * 64,
                  'acceptance': {'backend': backend, 'runtime': runtime, 'manifest': 'd' * 64, 'platforms': sorted(PLATFORMS)},
                  'digital_checks': [{'name': n} for n in ('icarus', 'verilator-coverage')]
                    + [{'name': p + '/' + s} for p in sorted(PLATFORMS) for s in native],
                  'timing_pairs': 18, 'physical_tool_checks': tools, 'platforms': [],
                  'process_audit': {'status': 'passed', 'backend': backend, 'runtime': runtime, 'cases': [
                      {'target': p, 'case': k + '-' + s, 'native_status': 'failed' if s == 'fault' else 'passed',
                       'drc_count': int(s == 'fault')} for p in sorted(TARGETS) for k in ('drc', 'lvs') for s in ('fault', 'repaired')]},
                  'digital_audit': {'status': 'passed', 'native_cases': 12, 'cases': [
                      {'platform': p, 'case': c, 'status': 'passed', 'expected_check_status': 'PASS' if c == 'baseline' else 'FAIL',
                       'source': {'result_sha256': '1' * 64}} for p in sorted(PLATFORMS) for c in ('baseline', 'removed-grid', 'antenna-route')]},
                  'full_rules_audit': {'status': 'geometry_passed', 'system': system, 'backend': backend,
                      'runtime_archive_sha256': 'c' * 64, 'runtime_audit_sha256': '4' * 64, 'cases': []}}
        for platform in sorted(PLATFORMS):
            values = stages(native)
            next(c for c in values if c['name'] == 'extracted-timing')['timing'] = timing(platform)
            finished = next(c for c in values if c['name'] == 'gds')
            finished.update(physical={'checks': {'status': 'PASS'}}, macro_export={'sha256': '5' * 64, 'notices': ['test notice']},
                            artifacts={'gds': {'sha256': '6' * 64}})
            result['platforms'].append({'name': platform, 'checks': values, 'router_checks': {'detailed_route_drc_errors': [0]}})
            if platform in RECIPES:
                finished['geometry_recipe'] = {'recipe': RECIPES[platform][1]}
                counts = {'main': 0, 'antenna': 0, 'density': 555}
                result['full_rules_audit']['cases'].append({'platform': platform, 'variant': RECIPES[platform][0],
                    'counts': counts, 'geometry_passed': True, 'density_passed': False,
                    'result_sha256': '1' * 64, 'gds_sha256': '6' * 64,
                    'reports': [{'group': name, 'markers': count, 'sha256': '7' * 64} for name, count in counts.items()]})
        record['operating_systems'][system] = result
    return record, production


class GeometryAcceptanceTests(unittest.TestCase):
    def test_production_record_requires_exact_bytes_inside_the_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / 'fixture.json'
            path.write_bytes(b'{"synthetic":true}')
            reference = {'path': 'fixture.json', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            self.assertEqual(bound_production(reference, root), {'synthetic': True})
            path.write_bytes(b'{"synthetic":false}')
            with self.assertRaisesRegex(ValueError, 'hash changed'): bound_production(reference, root)
            reference['path'] = '../outside.json'
            with self.assertRaisesRegex(ValueError, 'escapes'): bound_production(reference, root)

    def test_complete_reference_shape_preserves_failed_density_and_pre_layout_timing(self):
        record, production = fixture()
        validate(record, production)
        self.assertEqual(production['workloads'][0]['rule_counts']['density'], 555)
        self.assertEqual(production['workloads'][0]['checks'][4]['verdict'], 'FAIL')

    def test_incomplete_or_misbound_reference_evidence_is_rejected(self):
        def system(r): return r['operating_systems']['Windows']
        def timing(r):
            return next(c for c in system(r)['platforms'][0]['checks'] if c['name'] == 'extracted-timing')['timing']
        changes = {
            'missing-os': lambda r, p: r['operating_systems'].pop('Windows'),
            'stale-backend': lambda r, p: system(r)['acceptance'].update(backend='0' * 64),
            'wrong-runtime': lambda r, p: system(r)['acceptance']['runtime'].update(sha256='0' * 64),
            'wrong-manifest': lambda r, p: system(r)['acceptance'].update(manifest='0' * 64),
            'wrong-os': lambda r, p: system(r)['acceptance']['runtime'].update(kind='linux'),
            'changed-source-files': lambda r, p: r['source_files'].update(extra='0' * 64),
            'old-production': lambda r, p: p.update(backend='0' * 64),
            'missing-d-workload': lambda r, p: p['workloads'].pop(),
            'wrong-variant': lambda r, p: p['workloads'][2].update(variant='C'),
            'c-tech-for-d': lambda r, p: p['workloads'][2]['checks'][5].update(technology_lef_sha256='e' * 64),
            'wrong-extraction': lambda r, p: p['workloads'][2]['checks'][5].update(extraction_rules='9k.rules'),
            'geometry-findings': lambda r, p: p['workloads'][0]['rule_counts'].update(main=1),
            'missing-density': lambda r, p: p['workloads'][0]['rule_counts'].pop('density'),
            'hidden-density': lambda r, p: system(r)['full_rules_audit']['cases'][0].update(density_passed=True),
            'missing-counter-d': lambda r, p: system(r)['full_rules_audit']['cases'].pop(),
            'wrong-rule-gds': lambda r, p: system(r)['full_rules_audit']['cases'][0].update(gds_sha256='0' * 64),
            'missing-native-rule-group': lambda r, p: system(r)['full_rules_audit']['cases'][0]['reports'].pop(),
            'missing-stage': lambda r, p: system(r)['platforms'][0]['checks'].pop(),
            'missing-corner': lambda r, p: timing(r)['corners'].pop(),
            'unconstrained': lambda r, p: timing(r).update(unconstrained=True),
            'no-parasitics': lambda r, p: timing(r).update(parasitics='pre-layout'),
            'negative-slack': lambda r, p: timing(r)['corners'][0]['summary'].update(setup_worst_slack_ns=-1),
            'nan-slack': lambda r, p: timing(r)['summary'].update(hold_worst_slack_ns=float('nan')),
            'boolean-total-slack': lambda r, p: timing(r)['summary'].update(setup_total_negative_slack_ns=False),
            'boolean-violation-count': lambda r, p: timing(r)['summary'].update(hold_reported_violations=False),
            'missing-paths': lambda r, p: timing(r).update(path_count=0),
            'missing-export': lambda r, p: system(r)['platforms'][0]['checks'][5]['macro_export'].update(sha256=None),
            'missing-notices': lambda r, p: system(r)['platforms'][0]['checks'][5]['macro_export'].update(notices=[]),
            'missing-process-control': lambda r, p: system(r)['process_audit']['cases'].pop(),
            'false-process-fault': lambda r, p: system(r)['process_audit']['cases'][0].update(native_status='passed'),
            'missing-digital-control': lambda r, p: system(r)['digital_audit']['cases'].pop(),
            'wrong-control-layout': lambda r, p: system(r)['digital_audit']['cases'][0]['source'].update(result_sha256='0' * 64),
            'wrong-engine-version': lambda r, p: system(r)['physical_tool_checks'][5].update(version='KLayout 0.28'),
            'empty-native-fault': lambda r, p: system(r)['physical_tool_checks'][6].update(markers=0),
            'missing-hosted-step': lambda r, p: r['hosted']['steps'].pop(),
            'pending-hosted-step': lambda r, p: r['hosted']['steps'][0].update(status='in_progress', conclusion=''),
            'wrong-hosted-head': lambda r, p: r['hosted'].update(head_sha='0' * 40),
        }
        for name, change in changes.items():
            record, production = fixture(); change(record, production)
            with self.subTest(name=name), self.assertRaises(ValueError): validate(record, production)


if __name__ == '__main__': unittest.main()
