"""Producer boundary checks; generated fixtures are never acceptance evidence."""
import copy
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch
import uuid

from scripts import qualify_installed_metal_parallel as producer


class ProducerTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((producer.ROOT/producer.original.CONTRACT).read_bytes())
        self.row = dict(model='m1', width_um=2, length_um=5, multiplicity=3, rotation=90)
        self.key = 'm1-m3-r90'
        self.normalized = {kind: dict(normalized_path='/evidence/'+kind+'.spice') for kind in ('application','native')}
        self.execution = dict(root='/C:/evidence', nonce='a'*32)
        self.gui_nonce = 'b'*32

    def deck(self, analysis='dc'):
        return producer.deck(self.spec,self.row,self.key,analysis,{'tt':'.lib models tt'},self.normalized,self.execution,self.gui_nonce)

    def test_each_actual_array_is_included_and_instantiated_once(self):
        for analysis in ('dc','ac'):
            text=self.deck(analysis)
            for kind in ('application','native'):
                self.assertEqual(text.count('.include /evidence/'+kind+'.spice'),1)
            self.assertEqual(text.count('X_BODY a b coupon'),2)
            self.assertEqual(sum(line.startswith('XA ') for line in text.splitlines()),1)
            self.assertEqual(sum(line.startswith('XN ') for line in text.splitlines()),1)
            self.assertNotIn('sky130_fd_pr__res_generic_',text)
            self.assertNotIn(' m=',text)
            self.assertIn('RC in_c out_c '+format(producer.original.resistance(self.spec,self.row),'.17g'),text)

    def test_native_array_count_is_not_reapplied_as_wrapper_multiplicity(self):
        for count in (2,3,16):
            self.row['multiplicity']=count
            text=self.deck()
            self.assertEqual(text.count('X_BODY a b coupon'),2)
            self.assertIn('RC in_c out_c '+format(producer.original.resistance(self.spec,self.row),'.17g'),text)

    def test_fixed_conditions_channels_and_grids(self):
        self.assertIn('.dc VDRIVE -.001 .001 .0001',self.deck())
        self.assertIn('.ac dec 3 1k 10g',self.deck('ac'))
        for analysis in ('dc','ac'):
            text=self.deck(analysis)
            self.assertIn('.temp 27',text)
            self.assertIn('reltol=1e-7 abstol=1e-15 vntol=1e-12 method=gear',text)
            for tag in ('a','n','c'):
                self.assertIn(f'VS_{tag} input in_{tag} DC 0 AC 0',text)
                self.assertIn(f'CL_{tag} out_{tag} 0 1n',text)
                self.assertIn(f'i(vs_{tag})',text)
            for key in producer.original.coefficients(self.spec):
                self.assertIn(f'VP_{key} par_{key} 0 DC {{{key}}} AC {{{key}}}',text)

    def test_execution_title_prevents_cross_run_case_or_analysis_reuse(self):
        title=producer.title(self.execution,self.gui_nonce,self.key,'dc')
        variants=[producer.title({**self.execution,'root':'/different'},self.gui_nonce,self.key,'dc'),
            producer.title({**self.execution,'nonce':'c'*32},self.gui_nonce,self.key,'dc'),
            producer.title(self.execution,'d'*32,self.key,'dc'),
            producer.title(self.execution,self.gui_nonce,'m1-m2-r90','dc'),
            producer.title(self.execution,self.gui_nonce,self.key,'ac')]
        self.assertNotIn(title,variants)
        self.assertEqual(len(set(variants)),5)

    def test_unsupported_analysis_and_unsafe_include_reject(self):
        with self.assertRaisesRegex(ValueError,'DC/AC'): self.deck('noise')
        self.normalized['native']['normalized_path']='/evidence with spaces/native.spice'
        with self.assertRaisesRegex(ValueError,'whitespace'): self.deck()

    def test_full_received_input_selection_required_before_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'thirty'):
                producer.retain_inputs({'cases':{}},Path(temp))
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_invalid_output_or_workers_fail_before_prerequisite_access(self):
        root=Path(tempfile.gettempdir())/('array-uncreated-'+uuid.uuid4().hex)
        for gui,out,workers,pattern in ((root/'gui',root/'gui',2,'disjoint'),
                (root/'gui',root/'gui/out',2,'disjoint'),(root/'gui/sub',root/'gui',2,'disjoint'),
                (root/'gui',root/'has spaces',2,'whitespace'),(root/'gui',root/'out',5,'workers')):
            with self.subTest(out=out,workers=workers),patch.object(producer.inputs,'bind_gui') as bind:
                with self.assertRaisesRegex(ValueError,pattern): producer.run(gui,out,source_pilot=True,workers=workers)
                bind.assert_not_called()
        self.assertFalse(root.exists())

    def test_native_timeout_retains_partial_output_and_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'electrical').mkdir()
            failure=subprocess.TimeoutExpired(['ngspice'],90,output=b'partial native output\n',stderr=b'last diagnostic\n')
            with patch.object(producer.subprocess,'run',side_effect=failure):
                result=producer.execute_case(self.spec,self.row,self.key,'dc',{'tt':'.lib models tt'},
                    {self.key:self.normalized},self.execution,self.gui_nonce,root,Path('ngspice'),{})
            self.assertEqual(result['status'],'FAIL');self.assertTrue(result['timed_out'])
            self.assertEqual((root/'electrical'/f'{self.key}-dc'/'console.log').read_text(),
                'partial native output\nlast diagnostic\n')
            self.assertNotIn('observation',result)


if __name__=='__main__': unittest.main()
