import json
from pathlib import Path
import tempfile
import unittest
from scripts.check_ihp_magic_warnings import audit


class NativeWarningAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.paths=[self.root/n for n in ('top.ext','feedback.txt','instances.json','labels.json')]
        devices=[];warnings=[]
        for x,model,rail,gate,width in [(10,'nmos','NET000001','NET000000',84),(300,'pmos','NET000000','NET000001',200)]:
            devices.append(f'device msubckt sg13_lv_{model} {x} 10 {x+1} 11 l=200 w={width} "{rail}" "{gate}" 400 0 "{rail}" 0 0 "{rail}" 168 5712,304')
            warnings.append(f'box {x} 10 {x+200} {10+width}\nfeedback add "device missing 1 terminal;\n connecting remainder to node {rail}" pale\n')
        self.paths[0].write_text('scale 1000 1 0.5\n'+'\n'.join(devices)+'\n')
        self.paths[1].write_text(''.join(warnings))
        self.paths[2].write_text(json.dumps([dict(name='decap',master='sg13g2_decap_4',box_nm=[0,0,5000,5000])]))
        self.paths[3].write_text(json.dumps(dict(nets=[dict(net='VDD',alias='NET000000'),dict(net='VSS',alias='NET000001')])))

    def test_exact_decap_geometry_and_four_terminals(self):
        result=audit(*self.paths)
        self.assertTrue(result['passed']);self.assertEqual(result['warning_count'],2)

    def test_changed_body_or_width_is_rejected(self):
        original=self.paths[0].read_text()
        for old,new in [('w=84','w=85'),('"NET000001" "NET000000"','"NET000000" "NET000000"')]:
            self.paths[0].write_text(original.replace(old,new))
            with self.assertRaisesRegex(ValueError,'dimensions|connections'):audit(*self.paths)

    def test_nondecap_and_unrecognized_diagnostics_are_rejected(self):
        self.paths[2].write_text(self.paths[2].read_text().replace('sg13g2_decap_4','sg13g2_inv_1'))
        with self.assertRaisesRegex(ValueError,'outside'):audit(*self.paths)

    def test_missing_duplicate_or_extra_feedback_is_rejected(self):
        original=self.paths[1].read_text()
        for content in ('',original+original,original+'unexpected warning\n'):
            self.paths[1].write_text(content)
            with self.assertRaises(ValueError):audit(*self.paths)

    def test_ambiguous_rail_identity_is_rejected(self):
        self.paths[3].write_text(self.paths[3].read_text().replace('NET000001','NET000000'))
        with self.assertRaisesRegex(ValueError,'ambiguous'):audit(*self.paths)


if __name__=='__main__':unittest.main()
