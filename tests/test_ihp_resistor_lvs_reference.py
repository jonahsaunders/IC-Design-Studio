"""Pinned resistor LVS projection never changes physical or unknown tokens."""
import unittest
from unittest.mock import patch
from scripts.qualify_standard_mos import load_technology
from icstudio.model import file_digest
from icstudio.native_spice import lvs_defaults

class IhpResistorLvsReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.tech=load_technology('ihp-sg13g2')[0]
    def test_all_three_models_boolean_values_project_only_selector(self):
        for model in ('rsil','rppd','rhigh'):
            for value in ('0','1','0.0','1.00'):
                line=f'X1 PLUS MINUS BODY {model} w=2u l=7u m=3 b=9 mm_ok={value} unknown=keep'
                actual,proof=lvs_defaults(line,self.tech)
                self.assertEqual(actual,line.replace(' mm_ok='+value,''));self.assertEqual(len(proof),1)
                self.assertEqual(proof[0]['proof']['source'],f'libs.tech/xschem/sg13g2_pr/{model}.sym')
                self.assertEqual(proof[0]['proof']['sha256'],self.tech['package_lock']['files'][proof[0]['proof']['source']])
    def test_unknown_duplicate_expression_prefix_and_terminal_cases_stay_unchanged(self):
        lines=['X1 P M B other w=2u l=7u mm_ok=1','X1 P M B rsil w=2u l=7u mm_ok=2',
               'X1 P M B rsil w=2u l=7u mm_ok={flag}','X1 P M B rsil w=2u l=7u mm_ok=1 mm_ok=0',
               'R1 P M B rsil w=2u l=7u mm_ok=1','X1 P M EXTRA B rsil w=2u l=7u mm_ok=1',
               'X1 P M rsil w=2u l=7u mm_ok=1','X1 P M B rsil w=2u l=7u mm_ok=1e0']
        for line in lines:
            with self.subTest(line=line):self.assertEqual(lvs_defaults(line,self.tech),(line,[]))
    def test_changed_or_missing_resistor_symbol_rejects_projection(self):
        line='X1 P M B rsil w=2u l=7u mm_ok=1'
        for replacement in ('0'*64,None):
            def changed(path):
                if path.name=='rsil.sym':
                    if replacement is None:raise FileNotFoundError(path)
                    return replacement
                return file_digest(path)
            with patch('icstudio.model.file_digest',side_effect=changed):
                with self.assertRaises((ValueError,FileNotFoundError)):lvs_defaults(line,self.tech)
    def test_existing_mos_projection_is_unchanged(self):
        text='XM D G S B sg13_lv_nmos w=2u l=.13u ng=1 m=1 mm_ok=1'
        actual,proof=lvs_defaults(text,self.tech)
        self.assertEqual(actual,text.replace(' mm_ok=1',''));self.assertEqual(len(proof),1)
        self.assertIn('core',__import__('icstudio.native_spice',fromlist=['ihp_lvs_defaults']).ihp_lvs_defaults.__doc__)

if __name__=='__main__':unittest.main()
