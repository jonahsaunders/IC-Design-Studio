"""Coverage failures must not silently shrink the public qualification target."""
import copy
import unittest

from scripts.check_pdk_qualification import (
    MATRIX, TARGETS, HOSTED_TOOLCHAIN_STEPS, read, validate, validate_toolchain_record,
)


class QualificationMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = read(MATRIX)

    def test_complete_inventory_is_bookkeeping_not_qualification(self):
        report = validate(self.matrix)
        self.assertEqual(report['status'], 'matrix_consistent')
        self.assertEqual(report['process_qualification'], 'unqualified')
        self.assertEqual(report['device_entries'], 255)

    def test_omitted_unavailable_device_is_rejected(self):
        matrix = copy.deepcopy(self.matrix)
        del matrix['device_requirements']['ihp-sg13g2']['sg13g2_pr/inductor.sym']
        with self.assertRaisesRegex(ValueError, 'Device omitted'):
            validate(matrix)

    def test_variant_c_evidence_cannot_remove_variant_d_requirement(self):
        matrix = copy.deepcopy(self.matrix)
        del matrix['requirements']['gf180mcuD:digital-profile']
        with self.assertRaisesRegex(ValueError, 'Requirement coverage'):
            validate(matrix)

    def test_stale_manifest_and_partial_device_test_are_rejected(self):
        matrix = copy.deepcopy(self.matrix)
        matrix['inventory']['gf180mcuC']['revision'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'inventory is stale'):
            validate(matrix)
        matrix = copy.deepcopy(self.matrix)
        matrix['device_requirements']['sky130A']['sky130_fd_pr/nfet_01v8.sym']['tests'].remove('device-physical')
        with self.assertRaisesRegex(ValueError, 'Incomplete device coverage'):
            validate(matrix)

    def test_smoke_result_cannot_be_promoted_to_qualified(self):
        matrix = copy.deepcopy(self.matrix)
        matrix['requirements']['sky130A:device-simulation']['status'] = 'passed'
        with self.assertRaisesRegex(ValueError, 'Unsupported qualification claim'):
            validate(matrix)

    def test_unavailable_model_cannot_be_promoted(self):
        matrix = copy.deepcopy(self.matrix)
        matrix['device_requirements']['ihp-sg13g2']['sg13g2_pr/inductor.sym']['status'] = 'partial'
        with self.assertRaisesRegex(ValueError, 'Unavailable device promoted'):
            validate(matrix)

    def test_reference_pass_requires_its_own_acceptance_record(self):
        matrix = copy.deepcopy(self.matrix)
        matrix.pop('execution_acceptance', None)
        matrix['requirements']['sky130A:tool-install'].update(status='passed_reference', acceptance_chunk=2)
        with self.assertRaisesRegex(ValueError, 'Unbound reference pass'):
            validate(matrix)

    def test_changed_evidence_and_empty_acceptance_contract_are_rejected(self):
        matrix = copy.deepcopy(self.matrix)
        matrix['evidence']['gds-diagnostics']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Evidence changed'):
            validate(matrix)
        matrix = copy.deepcopy(self.matrix)
        matrix['tests']['ihp-rf']['expected_result'] = ''
        with self.assertRaisesRegex(ValueError, 'Missing test contract'):
            validate(matrix)

    def test_geometry_and_later_chunks_cannot_be_promoted_without_bound_evidence(self):
        matrix = copy.deepcopy(self.matrix)
        matrix['schema'] = 3
        matrix.get('execution_acceptance', {}).pop('3', None)
        for requirement in matrix['requirements'].values():
            if requirement.get('acceptance_chunk') == 3:
                requirement.update(status='partial')
                requirement.pop('acceptance_chunk')
        matrix['chunks']['3']['status'] = 'reference_gate_complete'
        with self.assertRaisesRegex(ValueError, 'Geometry execution gate'):
            validate(matrix)
        matrix['chunks']['3']['status'] = 'in_progress'
        matrix['requirements']['gf180mcuD:gf180-geometry'].update(status='passed_reference', acceptance_chunk=3)
        with self.assertRaisesRegex(ValueError, 'Unbound reference pass'):
            validate(matrix)
        matrix = copy.deepcopy(self.matrix)
        matrix['schema'] = 3
        matrix['chunks']['4']['status'] = 'reference_gate_complete'
        with self.assertRaisesRegex(ValueError, 'Completed execution'):
            validate(matrix)


class ToolchainRecordTests(unittest.TestCase):
    def fixture(self):
        # Synthetic schema fixture only; it is never written as qualification.
        platforms = ['sky130hd', 'gf180', 'ihp-sg13g2']
        tools = [{'name': n, 'status': 'passed'} for n in
                 ('drc-legal', 'drc-narrow', 'lvs-equal', 'lvs-wrong', 'ngspice')]
        tools[0]['count'] = 0; tools[1]['count'] = 1
        tools += [{'name': 'klayout-' + n, 'status': 'passed', 'markers': c,
                   'converted_edges': c, 'version': 'KLayout 0.30.5'} for n, c in [('legal', 0), ('narrow', 1)]]
        analog = [{'target': target, 'case': kind + '-' + state,
                   'native_status': 'failed' if state == 'fault' else 'passed',
                   'drc_count': int(state == 'fault')}
                  for target in TARGETS for kind in ('drc', 'lvs') for state in ('fault', 'repaired')]
        digital = [{'platform': p, 'case': c, 'status': 'passed',
                    'expected_check_status': 'PASS' if c == 'baseline' else 'FAIL'}
                   for p in platforms for c in ('baseline', 'removed-grid', 'antenna-route')]
        return {'chunk': 2, 'status': 'passed_reference_scope', 'source_commit': 'a'*40,
                'backend_sha256': 'b'*64, 'archive_sha256': 'c'*64,
                'scope': 'test fixture', 'limitations': ['Not engine evidence.'],
                'operating_systems': {system: {
                    'acceptance': {'backend': 'b'*64, 'runtime': {'sha256': 'c'*64, 'kind': kind}, 'platforms': platforms},
                    'installation_checks': 26, 'timing_pairs': 15, 'macro_exports': 3,
                    'physical_tool_checks': copy.deepcopy(tools), 'process_rule_controls': copy.deepcopy(analog),
                    'digital_controls': copy.deepcopy(digital), 'audit_status': 'passed'}
                    for system, kind in [('Linux', 'linux'), ('Windows', 'wsl')]},
                'hosted': {'head_sha': 'a'*40, 'steps': [{'name': n, 'status': 'completed', 'conclusion': 'success'}
                                                      for n in sorted(HOSTED_TOOLCHAIN_STEPS)]},
                'old_cli_control': {'exit': 1, 'missing_interface': 'RBA::EdgePairToEdgeOperator'}}

    def test_reference_record_demands_both_os_current_source_and_all_cases(self):
        validate_toolchain_record(self.fixture())
        changes = {
            'pending': lambda r: r.update(status='awaiting_hosted_steps'),
            'missing-windows': lambda r: r['operating_systems'].pop('Windows'),
            'stale-backend': lambda r: r['operating_systems']['Windows']['acceptance'].update(backend='d'*64),
            'wrong-os': lambda r: r['operating_systems']['Windows']['acceptance']['runtime'].update(kind='linux'),
            'missing-process-case': lambda r: r['operating_systems']['Linux']['process_rule_controls'].pop(),
            'missing-digital-fault': lambda r: r['operating_systems']['Windows']['digital_controls'].pop(),
            'false-fault': lambda r: r['operating_systems']['Linux']['process_rule_controls'][0].update(native_status='passed'),
            'negative-clean-count': lambda r: r['operating_systems']['Linux']['process_rule_controls'][1].update(drc_count=-1),
            'boolean-count': lambda r: r['operating_systems']['Linux']['physical_tool_checks'][6].update(markers=True),
            'empty-native-fault': lambda r: r['operating_systems']['Linux']['physical_tool_checks'][1].update(count=0),
            'stale-hosted-head': lambda r: r['hosted'].update(head_sha='d'*40),
            'pending-hosted-step': lambda r: r['hosted']['steps'][0].update(status='in_progress', conclusion=''),
            'failed-hosted-step': lambda r: r['hosted']['steps'][0].update(conclusion='failure'),
            'missing-hosted-step': lambda r: r['hosted']['steps'].pop(),
            'no-independent-audit': lambda r: r['operating_systems']['Linux'].update(audit_status='pending'),
            'old-engine-passed': lambda r: r['old_cli_control'].update(exit=0),
        }
        for name, change in changes.items():
            record = self.fixture(); change(record)
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_toolchain_record(record)


if __name__ == '__main__':
    unittest.main()
