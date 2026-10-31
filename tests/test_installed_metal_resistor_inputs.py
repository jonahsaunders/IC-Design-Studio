import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import installed_metal_resistor_inputs as inputs


TOP='metal_m1_g1_r0_0123456789ab'
ROW=dict(model='m1',width_um=2,length_um=5)


def reference(*,native=False,ending=True):
    line='R0 R2 R1 sky130_fd_pr__res_generic_m1 w=2 l=5' if native else 'R_R1 R1 R2 sky130_fd_pr__res_generic_m1 l=5 m=1 w=2'
    return ('* unchanged \N{GREEK SMALL LETTER MU}m comment\r\n.subckt '+TOP+' R1 R2\r\n'+line+'\r\n.ends'+(' '+TOP if ending else '')+'\r\n').encode()


class InstalledMetalInputsTest(unittest.TestCase):
    def test_top_only_bytes_keep_comments_crlf_and_device(self):
        for native in (False,True):
            raw=reference(native=native);data,proof=inputs.normalize_top(raw,TOP)
            self.assertEqual(data,raw.replace(TOP.encode(),b'coupon'))
            self.assertEqual(inputs.apply_edits(raw,proof['edits']),data)
            self.assertEqual(proof['original_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(proof['normalized_sha256'],hashlib.sha256(data).hexdigest())
            inputs.resistor_tokens(data,ROW,application=not native)

    def test_unnamed_ends_remains_unnamed(self):
        raw=reference(ending=False);data,proof=inputs.normalize_top(raw,TOP)
        self.assertEqual(len(proof['edits']),1);self.assertTrue(data.endswith(b'.ends\r\n'))

    def test_unreviewed_directives_and_multiple_interfaces_reject(self):
        raw=reference()
        bad=[raw+raw,raw+b'.include /other\r\n',raw.replace(b' R1 R2\r\n',b' R1 R2 R3\r\n',1),
             raw.replace(b'.ends '+TOP.encode(),b'.ends wrong'),raw.replace(b'.subckt '+TOP.encode(),b'.subckt wrong')]
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):inputs.normalize_top(value,TOP)

    def test_each_fault_changes_exactly_one_reviewed_token(self):
        data,_=inputs.normalize_top(reference(),TOP)
        expected={'wrong-width':b'w=2.3999999999999999','wrong-length':b'l=6',
            'wrong-model':b'sky130_fd_pr__res_generic_m3','wrong-multiplicity':b'm=2','disconnected-terminal':b' 0 R2 '}
        for fault,value in expected.items():
            altered,proof=inputs.fault_copy(data,ROW,fault)
            self.assertEqual(len(proof['edits']),1);self.assertIn(value,altered)
            self.assertEqual(inputs.apply_edits(data,proof['edits']),altered)
            self.assertEqual(proof['mutated_sha256'],hashlib.sha256(altered).hexdigest())
        self.assertEqual(reference().replace(TOP.encode(),b'coupon'),data)

    def test_duplicate_nonfinite_and_extra_device_reject(self):
        data,_=inputs.normalize_top(reference(),TOP)
        bad=[data.replace(b'm=1',b'm=nan'),data.replace(b'm=1',b'w=2'),data.replace(b'm=1',b'm=1 m=1'),
             data.replace(b'w=2',b'w=1e999'),data.replace(b'w=2',b'w=2u'),data+b'R_hidden R1 R2 10\r\n',
             data.replace(b'm=1',b'm=3'),data.replace(b' R1 R2 sky',b' R1 R1 sky')]
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):inputs.resistor_tokens(value,ROW,application=True)

    def test_mutation_span_detects_changed_original(self):
        data,_=inputs.normalize_top(reference(),TOP);_,proof=inputs.fault_copy(data,ROW,'wrong-width')
        with self.assertRaises(ValueError):inputs.apply_edits(data.replace(b'w=2',b'w=3'),proof['edits'])

    def test_unknown_fault_rejects(self):
        data,_=inputs.normalize_top(reference(),TOP)
        with self.assertRaises(ValueError):inputs.fault_copy(data,ROW,'disable-model')

    def test_installed_engine_override_rejects(self):
        with self.assertRaisesRegex(ValueError,'forbids'):
            inputs.select_engine({'mode':'installed'},Path('source-ngspice'))

    def test_all_gui_cases_and_primitive_references_bound(self):
        installed,spec,_=inputs.contracts();cases=inputs.expected_cases(installed)
        self.assertEqual(len(cases),30);self.assertEqual(cases[0],'l1-g0-r0');self.assertEqual(cases[-1],'m4-g2-r90')
        for name,row in spec['engine_sources'].items():
            self.assertEqual(inputs.sha(inputs.ROOT/'docs/qualification/ngspice42-metal-reference'/name),row['sha256'])


if __name__=='__main__':unittest.main()
