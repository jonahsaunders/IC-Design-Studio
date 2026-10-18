import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from icstudio.ngspice_compat import prepare
from icstudio.rf_runtime import calls, enforce

MODEL = 'sky130_fd_pr__model__parasitic__rf_diode_ps2nw'


class RFRuntimeTests(unittest.TestCase):
    def test_exact_calls_case_continuation_and_comments(self):
        self.assertEqual(calls('* Xignored a k '+MODEL+'\n.subckt '+MODEL+' a k\n'), [])
        text='X1 A K\n+ '+MODEL.upper()+' area=4 perim=8\nX2 a k '+MODEL+'_other\n'
        self.assertEqual(calls(text), [dict(instance='X1', model=MODEL)])
        with self.assertRaisesRegex(ValueError, 'subcircuit'):
            calls('D1 a k '+MODEL)

    def test_ordinary_circuits_do_not_run_the_rf_probe(self):
        with patch('icstudio.diode_runtime.verify') as probe:
            text='V1 a 0 1\nR1 a 0 1000\n.end\n'
            self.assertEqual(prepare(text, 'unused', 'unused'), text)
            probe.assert_not_called()

    def check(self, result):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        def probe(executable, directory):
            Path(directory).mkdir();return result
        return tmp.name, patch('icstudio.diode_runtime.verify', side_effect=probe)

    def test_verified_runtime_preserves_model_and_program_bytes(self):
        text='X1 a k '+MODEL+' area=4 perim=8\n.control\nop\ndc V1 0 .6 .1\nac dec 5 1k 1g\n.endc\n'
        root, probe=self.check(dict(status='PASS', behavior=dict(mode='unscaled-explicit-area')))
        with probe as called:
            self.assertEqual(prepare(text, 'engine', root), text)
            self.assertEqual(prepare(text, 'engine', root), text)
            self.assertEqual(called.call_count, 2)
        reports=list(Path(root).glob('rf-runtime-*/rf-acceptance.json'))
        self.assertEqual(len(reports), 2)
        self.assertTrue(all(json.loads(p.read_bytes())['status']=='PASS' for p in reports))

    def test_incompatible_or_incomplete_engine_proof_rejects_before_circuit_run(self):
        for record in (dict(status='FAIL', behavior=dict(mode='unscaled-explicit-area')),
                       dict(status='PASS', behavior=dict(mode='scales-explicit-area')),
                       dict(status='PASS')):
            with self.subTest(record=record):
                root, probe=self.check(record)
                with probe, self.assertRaisesRegex(ValueError, 'geometry check'):
                    enforce('X1 a k '+MODEL, 'engine', root)
                self.assertEqual(json.loads(next(Path(root).glob('*/rf-acceptance.json')).read_bytes())['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
