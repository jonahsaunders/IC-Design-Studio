import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from icstudio.ngspice_compat import prepare
from icstudio.rf_runtime import calls, enforce, inspect_inputs

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

    def test_nested_wrapper_and_selected_library_section(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'nested').mkdir()
            (root/'corner.lib').write_text('.lib tt\n.include "nested/wrapper.inc"\n.endl tt\n.lib ss\n.include missing.inc\n.endl ss\n')
            (root/'nested/wrapper.inc').write_text('.subckt wrapper a k\nXinner a k\n+ '+MODEL+' area=4 perim=8\n.ends\n')
            result=inspect_inputs('.lib "corner.lib" TT\nX1 a k wrapper\n',root)
            self.assertEqual([c['instance'] for c in result['calls']],['Xinner'])
            self.assertEqual(len(result['dependencies']),2)
            self.assertEqual(result['uncertainty'],[])
            self.assertTrue(all(len(d['sha256'])==64 for d in result['dependencies']))

    def test_unselected_rf_corner_does_not_trigger_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'corner.lib').write_text('.lib tt\nR1 a k 1k\n.endl tt\n.lib ss\nX1 a k '+MODEL+'\n.include missing.inc\n.endl ss\n')
            with patch('icstudio.diode_runtime.verify') as probe:
                self.assertIsNone(enforce('.lib corner.lib tt\n','unused',root))
                probe.assert_not_called()

    def test_include_paths_use_engine_working_directory_first(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'sub').mkdir()
            (root/'sub/top.inc').write_text('.include inner.inc\n')
            (root/'sub/inner.inc').write_text('R1 a k 1k\n')
            (root/'inner.inc').write_text('X1 a k '+MODEL+'\n')
            result=inspect_inputs('.include sub/top.inc\n',root)
            self.assertEqual(len(result['calls']),1)
            self.assertTrue(Path(result['dependencies'][1]['path']).samefile(root/'inner.inc'))
            (root/'inner.inc').unlink()
            result=inspect_inputs('.include sub/top.inc\n',root)
            self.assertFalse(result['calls'])
            self.assertTrue(result['uncertainty'])

    def test_include_cycles_terminate_and_do_not_hide_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'a.inc').write_text('.include b.inc\nX1 a k '+MODEL+'\n')
            (root/'b.inc').write_text('.include a.inc\n')
            result=inspect_inputs('.include a.inc\n',root)
            self.assertEqual(len(result['dependencies']),2)
            self.assertEqual(len(result['calls']),1)

    def test_uninspectable_input_cannot_bypass_incompatible_runtime(self):
        for text in ('.include absent.inc\n','.include "$models/a.inc"\n',
                     '.include a.inc unsupported\n','.control\nsource other.cir\n.endc\n'):
            with self.subTest(text=text):
                root,probe=self.check(dict(status='FAIL'))
                with probe,self.assertRaisesRegex(ValueError,'geometry check'):
                    enforce(text,'engine',root)
                result=json.loads(next(Path(root).glob('*/rf-acceptance.json')).read_bytes())
                self.assertTrue(result['input_inspection']['uncertainty'])

    def test_quoted_paths_inline_comments_and_control_text(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'a ; b.inc'
            path.write_bytes(b'* legacy comment \xb5\nR1 a k 1k\n')
            result=inspect_inputs('.include "a ; b.inc" $ comment\n.control\necho X1 a k '+MODEL+'\n.endc\n',root)
            self.assertEqual(result['calls'],[])
            self.assertEqual(result['uncertainty'],[])
            self.assertEqual(len(result['dependencies']),1)

    def test_external_deck_resolves_includes_at_deck_not_output(self):
        from icstudio.engines import run_deck
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);inputs=root/'inputs';output=root/'output';inputs.mkdir();output.mkdir()
            (inputs/'model.inc').write_text('X1 a k '+MODEL+' area=4 perim=8\n')
            deck=inputs/'test.cir';deck.write_text('test\n.include model.inc\n.op\n.end\n')
            def probe(executable,directory):
                Path(directory).mkdir();return dict(status='FAIL')
            with patch('icstudio.diode_runtime.verify',side_effect=probe), patch('icstudio.engines.execute') as execute:
                with self.assertRaisesRegex(ValueError,'geometry check'):
                    run_deck({},'unused',dict(deck=str(deck)),'engine',output)
                execute.assert_not_called()
            result=json.loads(next(output.glob('*/rf-acceptance.json')).read_bytes())
            self.assertTrue(Path(result['calls'][0]['source']).samefile(inputs/'model.inc'))

    def test_missing_section_requires_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'lib.inc').write_text('.lib tt\nR1 a k 1\n.endl tt\n')
            self.assertTrue(inspect_inputs('.lib lib.inc ff',root)['uncertainty'])


if __name__ == '__main__':
    unittest.main()
