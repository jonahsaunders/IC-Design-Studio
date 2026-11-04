"""Incomplete, stale and overclaimed IHP acceptance must fail closed."""
import copy
import json
from pathlib import Path
import unittest
from scripts.check_ihp_fill_closure import ROOT, bound, validate, validate_reference


class IHPClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record=json.loads((ROOT/'docs/validation/ihp-fill-closure-2026-10-11.json').read_text())
        cls.row=bound(cls.record['references'][0],ROOT)
        cls.snapshot=json.loads((ROOT/'docs/qualification/pdk-matrix.json').read_text())['execution_acceptance']['5'].get('historical_source_snapshot')

    def test_exact_reference_gate_does_not_qualify_the_process(self):
        result=validate(self.record,source_snapshot=self.snapshot)
        self.assertTrue(result['chunk_complete'])
        self.assertEqual(result['process_qualification'],'unqualified')

    def test_stale_missing_archive_and_process_promotion_rejected(self):
        mutations={
            'missing-case':lambda r:r['references'].pop(),
            'changed-source':lambda r:r['source_files'].update({'icstudio/digital_ihp_fill.py':'0'*64}),
            'stale-evidence':lambda r:r['references'][0].update(sha256='0'*64),
            'escaping-dependency':lambda r:r['references'][0].update(path='../outside.json'),
            'missing-os':lambda r:r['audits'].pop('linux'),
            'archive-unverified':lambda r:r['archive'].update(verified=False),
            'process-signoff':lambda r:r.update(qualified=True),
            'invented-transient':lambda r:r.update(full_transistor_rc_acceptance='passed'),
        }
        for name,change in mutations.items():
            data=copy.deepcopy(self.record);change(data)
            with self.subTest(name=name),self.assertRaises(ValueError):validate(data,source_snapshot=self.snapshot)

    def test_historical_acceptance_does_not_claim_a_current_production_run(self):
        if self.snapshot:
            with self.assertRaisesRegex(ValueError,'changed source'):validate(self.record)
            self.assertEqual(validate(self.record,source_snapshot=self.snapshot)['source_scope'],'historical-tested-source-only')

    def test_changed_source_snapshot_is_rejected(self):
        if self.snapshot:
            changed=copy.deepcopy(self.snapshot);changed['sha256']='0'*64
            with self.assertRaises(ValueError):validate(self.record,source_snapshot=changed)

    def test_changed_circuit_rules_fields_timing_and_export_rejected(self):
        mutations={
            'changed-spef':lambda r:r['artifacts'].update(spef='0'*64),
            'changed-layout':lambda r:r['worker'].update(filled_gds_sha256='0'*64),
            'drc-marker':lambda r:r['worker'].update(markers=1),
            'disabled-rule':lambda r:r['supplement']['checks'].pop(),
            'shrunk-footprint':lambda r:r['supplement'].update(bounds_nm=[0,0,100000,100000]),
            'changed-cell-capacitance':lambda r:r['worker']['capacitance'].update(maximum_raw_change_af=1e-12),
            'missing-corrected-extractor':lambda r:r['invariance']['results'].pop(),
            'changed-local-field':lambda r:r['field'].update(maximum_change_af=1),
            'nonfinite-field':lambda r:r['field'].update(maximum_change_af=float('nan')),
            'missing-local-pair':lambda r:r['field'].update(pairs=1),
            'lvs-failed':lambda r:r['lvs'].update(matched=False),
            'rejected-capture':lambda r:r['lvs'].update(invalid_for_acceptance=True),
            'different-proof':lambda r:r['formal'].update(netlist_sha256='0'*64),
            'antenna-failed':lambda r:r['physical_checks'].update(status='FAIL'),
            'abstract-gap':lambda r:r['lef']['layers']['Metal1'].update(missing_area_nm2=1),
            'missing-timing-corner':lambda r:r['timing']['results'].pop(),
            'fault-passed':lambda r:next(x for x in r['timing']['results'] if x['state']=='fault')['timing'].update(status='PASS'),
            'app-timing-failed':lambda r:r['application_timing'].update(status='FAIL'),
            'unannotated-app':lambda r:r['application_timing']['corners'][0]['parasitic_annotation'].update(connected_unannotated_drivers=['wire']),
        }
        for name,change in mutations.items():
            data=copy.deepcopy(self.row);change(data)
            with self.subTest(name=name),self.assertRaises(ValueError):validate_reference(data)


if __name__=='__main__':unittest.main()
