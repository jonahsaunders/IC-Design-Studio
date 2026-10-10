"""A bounded density pass must retain its complete, source-bound evidence."""
import copy
import unittest

from scripts.check_pdk_qualification import ROOT, read
from scripts.check_gf180_density_acceptance import validate


class DensityAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = read(ROOT / 'docs/validation/gf180-density-2026-10-09.json')

    def test_record_accepts_only_reference_scope(self):
        report = validate(self.record, ROOT)
        self.assertEqual(report['status'], 'reference_checks_passed')
        self.assertFalse(report['chunk_complete'])
        self.assertEqual(report['process_qualification'], 'unqualified')

    def test_missing_stale_and_failed_evidence_is_rejected(self):
        changes = {
            'qualified': lambda r: r.update(qualified=True),
            'wrong-source': lambda r: r.update(backend_sha256='0'*64),
            'changed-dependency': lambda r: r['dependencies'][0].update(sha256='0'*64),
            'missing-design': lambda r: r['references'].pop(),
            'duplicate-design': lambda r: r['references'][1].update(case=r['references'][0]['case']),
            'density-markers': lambda r: r['references'][0]['rules'].update(density=1),
            'boolean-marker-count': lambda r: r['references'][0]['rules'].update(density=False),
            'changed-model': lambda r: r['references'][0].update(identical_independent_finite_rc_model=False),
            'pre-fill-abstract': lambda r: r['references'][0].update(filled_lef_coverage=False),
            'missed-logic-fault': lambda r: r['references'][0].update(logic_fault='PASS'),
            'negative-slack': lambda r: r['references'][0]['timing']['corners'][0]['summary'].update(setup_worst_slack_ns=-1),
            'missing-corner': lambda r: r['references'][0]['timing']['corners'].pop(),
            'missing-paths': lambda r: r['references'][0]['timing']['corners'][0].update(paths=[]),
            'missing-annotation': lambda r: r['references'][0]['timing']['corners'][0].pop('parasitic_annotation'),
            'partial-annotation': lambda r: r['references'][0]['timing']['corners'][0]['parasitic_annotation'].update(partially_unannotated_drivers=['clk']),
            'missing-os': lambda r: r['audits'].pop('windows'),
            'different-audit': lambda r: r['audits']['linux'].update(case_digest='0'*64),
            'stale-installation': lambda r: r['installed']['windows'].update(backend='0'*64),
            'missing-installed-audit': lambda r: r['installed']['linux'].update(audit_status='running'),
            'unverified-installation-archive': lambda r: r['installed']['windows'].update(archive_verified=False),
            'unverified-archive': lambda r: r['archive'].update(verified=False),
            'stale-hosted-source': lambda r: r['hosted_runtime'].update(head_sha='0'*40),
            'failed-hosted-runtime': lambda r: r['hosted_runtime'].update(conclusion='failure'),
            'incomplete-suite': lambda r: r['tests'].update(count=10),
        }
        for name, change in changes.items():
            record = copy.deepcopy(self.record)
            change(record)
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate(record, ROOT)


if __name__ == '__main__':
    unittest.main()
