"""The chunk-6 completion label cannot outgrow its evidence or approved scope."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from scripts.check_sky130_public_baseline import validate
from scripts.check_pdk_qualification import MATRIX, read, validate as validate_matrix


class PublicAcceptanceTests(unittest.TestCase):
    def baseline(self):
        return json.loads((Path(__file__).resolve().parents[1]/'docs/validation/sky130-public-baseline-2026-10-16.json').read_bytes())

    def test_complete_public_baseline_does_not_qualify_the_process(self):
        result=validate(self.baseline())
        self.assertTrue(result['chunk_complete']);self.assertTrue(result['public_baseline_qualified'])
        self.assertFalse(result['qualified']);self.assertFalse(result['foundry_signoff'])

    def test_missing_checks_context_or_exclusions_prevent_completion(self):
        changes={
            'consent':lambda r:r.pop('acceptance_change'),
            'scope':lambda r:r['profile']['exclusions'].clear(),
            'foundry':lambda r:r.update(foundry_signoff=True),
            'source':lambda r:r['source_files'].pop('icstudio/digital_macro.py'),
            'controls':lambda r:r['prior_evidence'].pop('sky130-generic-native-2026-10-16'),
            'reference':lambda r:r['fresh_runs'].pop('apb'),
            'check':lambda r:r['fresh_runs']['counter']['baseline']['evidence'].pop('sky130_lvs'),
            'density':lambda r:r['fresh_runs']['counter']['baseline'].update(full_windows=0),
            'small-block':lambda r:r['fresh_runs']['uart']['baseline'].update(density_context_complete=True),
            'export':lambda r:r['windows_exports']['counter'].update(rehashed_frame_exemption_rejected=False),
            'tests':lambda r:r['tests']['linux'].update(errors=1),
            'catalog':lambda r:r['historical_catalog'].update(dispositions_changed=302),
        }
        for name,change in changes.items():
            record=self.baseline();change(record)
            with self.subTest(fault=name),self.assertRaises(ValueError):validate(record)

    def test_matrix_completion_needs_this_acceptance_record(self):
        matrix=deepcopy(read(MATRIX));matrix['execution_acceptance'].pop('6',None)
        matrix['chunks']['6']['status']='public_reference_gate_complete'
        with self.assertRaisesRegex(ValueError,'SKY130 public baseline'):validate_matrix(matrix)


if __name__=='__main__':unittest.main()
