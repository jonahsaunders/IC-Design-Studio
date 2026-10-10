"""Full reference closure requires the supplemental evidence, not just native counts."""
import copy
import unittest
from scripts.check_pdk_qualification import ROOT, read
from scripts.check_gf180_fill_closure import validate, validate_supplement


class FillClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record=read(ROOT/'docs/validation/gf180-fill-closure-2026-10-09.json')
        cls.native=read(ROOT/cls.record['native_acceptance']['path'])

    def test_complete_reference_acceptance_does_not_qualify_process(self):
        result=validate(self.record,ROOT)
        self.assertTrue(result['chunk_complete'])
        self.assertEqual(result['references'],6)
        self.assertEqual(result['process_qualification'],'unqualified')

    def test_missing_changed_and_falsely_promoted_closure_rejected(self):
        changes={
            'old-schema':lambda r:r.update(schema=1),
            'native-only':lambda r:r['references'].clear(),
            'changed-backend':lambda r:r.update(backend_sha256='0'*64),
            'different-native':lambda r:r['native_acceptance'].update(sha256='0'*64),
            'partial-os':lambda r:r['os_audits'].pop('linux'),
            'mismatched-os':lambda r:r['os_audits']['linux'].update(references_sha256='0'*64),
            'mutated-report':lambda r:r['references'][0]['files']['report'].update(sha256='0'*64),
            'wrong-macro':lambda r:r['references'][0].update(macro_sha256='0'*64),
            'invented-local-rule':lambda r:r.update(local_density_policy='thirty-percent-local'),
            'invented-waveform-pass':lambda r:r.update(full_transistor_rc_acceptance='passed'),
            'unverified-retention':lambda r:r['archive'].update(verified=False),
            'process-promotion':lambda r:r.update(qualified=True),
        }
        for name,change in changes.items():
            altered=copy.deepcopy(self.record);change(altered)
            with self.subTest(name=name),self.assertRaises(ValueError):validate(altered,ROOT)

    def test_failed_checks_missing_sites_and_unchecked_operands_rejected(self):
        row=self.record['references'][0]
        data={name:read(ROOT/item['path']) for name,item in row['files'].items()}
        changes={
            'violation':lambda d:d['report']['checks'][0].update(status='failed',violations=1),
            'omitted-rule':lambda d:d['report']['checks'].pop(),
            'unknown-gap':lambda d:d['report']['unqualified_requirements'].append('missing COMP'),
            'marker-present':lambda d:d['report']['rule_applicability']['rules'][0].update(status='requires_exclusion_edge_row_check'),
            'open-comp-site':lambda d:d['report']['boundary_comp_space'].update(no_legal_square_proven=False),
            'reduced-die':lambda d:d['floorplan'].update(prime_die_nm=[20000,20000,180000,180000]),
            'missing-street':lambda d:d['boundary']['scribe_boxes_nm'].pop(),
            'fault-passed':lambda d:d['negative'].update(status='declared_boundary_checks_passed'),
            'missing-window':lambda d:d['report']['metal_density_windows']['m1']['windows'].pop(),
            'invented-threshold':lambda d:d['report']['metal_density_windows']['m1'].update(local_limits_percent=[30,100]),
            'bad-measurement':lambda d:d['report']['metal_density_windows']['m1']['windows'][0].update(measured_percent=0),
        }
        for name,change in changes.items():
            d=copy.deepcopy(data);change(d)
            with self.subTest(name=name),self.assertRaises(ValueError):
                validate_supplement(d['report'],d['floorplan'],d['boundary'],row['files']['pattern']['sha256'],
                                    d['negative'],row,self.native['references'][0])


if __name__=='__main__':unittest.main()
