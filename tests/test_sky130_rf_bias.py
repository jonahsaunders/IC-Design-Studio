"""Protect the RF equation domain and native-output acceptance contract."""
import math
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts.qualify_sky130_rf_bias import branches, expected, read, model_text, deck
from scripts.qualify_sky130_rf_branches import COEFFICIENTS, expected as zero_bias
from scripts.prepare_sky130_rf_qualification import public_sources, COMMON


class RFBiasTests(unittest.TestCase):
    def test_zero_bias_agrees_with_prior_independent_linear_solution(self):
        for model,c in COEFFICIENTS.items():
            for temperature in (-40,27,125):
                for area,perimeter in ((4,8),(8,12),(100,40)):
                    parts=branches(model,area,perimeter,c['aj'],c['pj'],temperature,0)
                    self.assertEqual(expected(parts,0)['dc'],0)
                    for frequency in (10,1e3,1e6,1e10):
                        old=zero_bias(model,area,perimeter,c['aj'],c['pj'],temperature,frequency)
                        self.assertLessEqual(abs(expected(parts,frequency)['ac']-old),1e-13*abs(old))

    def test_reverse_series_solution_preserves_kcl_and_depletion_direction(self):
        for model,c in COEFFICIENTS.items():
            for temperature in (-40,27,125):
                previous=branches(model,4,8,c['aj'],c['pj'],temperature,0)
                for bias in (-.05,-.1,-.5,-1,-5):
                    parts=branches(model,4,8,c['aj'],c['pj'],temperature,bias)
                    for before,after in zip(previous,parts):
                        self.assertLess(after['current'],0)
                        self.assertGreaterEqual(after['voltage'],bias)
                        self.assertLess(after['capacitance'],before['capacitance'])
                        self.assertAlmostEqual(after['voltage']+after['resistance']*after['current'],bias,delta=1e-14)
                    self.assertTrue(math.isfinite(expected(parts,1e6)['noise']))
                    self.assertGreater(expected(parts,1e6)['noise'],0)
                    previous=parts

    def test_unqualified_bias_temperature_and_nonrectangular_geometry_are_rejected(self):
        c=COEFFICIENTS['ps2nw'];base=[4,8,c['aj'],c['pj'],27,-1]
        for index,value in ((0,0),(0,100),(1,0),(2,-1),(3,float('nan')),(4,-41),(4,126),(5,.1),(5,-6)):
            args=base.copy();args[index]=value
            with self.subTest(index=index,value=value),self.assertRaises(ValueError):branches('ps2nw',*args)

    def test_native_output_cannot_hide_missing_duplicate_nonfinite_or_truncated_data(self):
        valid=(['frequency','onoise_spectrum'],[[10.,1e-20],[20.,2e-20]],False)
        with patch('scripts.qualify_sky130_rf_bias.parse_raw',return_value=valid):
            self.assertEqual(len(read(Path('native.raw'),False,2,valid[0])),2)
        for bad in ((valid[0],valid[1][:1],False),
                    (['frequency','frequency'],valid[1],False),
                    (valid[0],[[10,float('nan')],[20,2e-20]],False),
                    (valid[0],[[10],[20,2e-20]],False),
                    (valid[0],valid[1],True)):
            with self.subTest(bad=bad),patch('scripts.qualify_sky130_rf_bias.parse_raw',return_value=bad),self.assertRaises(ValueError):
                read(Path('native.raw'),False,2,valid[0])

    def test_faults_modify_the_requested_model_parameters_and_do_not_reset(self):
        _,sources=public_sources()
        for model in COEFFICIENTS:
            good=model_text(model,sources,'none')
            for fault in ('missing-perimeter','wrong-barrier','wrong-leakage'):
                self.assertNotEqual(model_text(model,sources,fault),good)
            for fault,keys in (('wrong-barrier',('pb','php')),('wrong-leakage',('js','jsw'))):
                changed=model_text(model,sources,fault)
                original_lines=good.splitlines();new_lines=changed.splitlines()
                differences=[(a,b) for a,b in zip(original_lines,new_lines) if a!=b]
                self.assertEqual(len(differences),2)
                self.assertEqual({a.split()[1] for a,b in differences},set(keys))
            text=deck(model,4,8,'+ test=1',27)
            self.assertEqual(text.count('alter Vdrive'),7)
            self.assertNotIn('\nreset',text)
            self.assertIn('X1 0 d '+COMMON+'rf_diode_'+model,text)


if __name__=='__main__':unittest.main()
