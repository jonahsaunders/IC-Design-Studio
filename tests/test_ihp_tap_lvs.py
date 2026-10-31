import importlib.util,json,sys,unittest
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
from icstudio.model import clone
from icstudio.catalog import create_device
from icstudio.catalog_migration import emit
from icstudio import ihp_tap_lvs as draft


class TapLvsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder=repo/'icstudio/assets/pdks/ihp-sg13g2';p=json.loads((folder/'package.json').read_bytes());cls.tech=clone(p['technology']);cls.tech.update(package_root=str(folder),package_lock={k:p[k] for k in ('id','revision','files')})

    def test_simulation_reference_preserves_roles_and_area_perimeter(self):
        for model in ('ntap1','ptap1'):
            text=f'.subckt t tie body\nX1 tie body {model} w=2u l=2u r=81.6666666667\n.ends t\n'
            converted,records=draft.reference_geometry(text,self.tech)
            self.assertIn(f'X1 tie body {model} A=4e-12 P=8e-06',converted);self.assertEqual(len(records),1)

    def test_live_catalog_formula_is_recognized_but_modified_expressions_are_not(self):
        d=create_device(self.tech,'sg13g2_pr/ntap1.sym','TAP');d['nets']={'p':'tie','m':'body'};d['model_params'].update(w=2e-6,l=2e-6)
        text=emit(d,self.tech);converted,records=draft.reference_geometry(text,self.tech)
        self.assertIn('tie body ntap1 A=4e-12 P=8e-06',converted)
        with self.assertRaises(ValueError):draft.reference_geometry(text.replace('9.8e-10','9.9e-10'),self.tech)

    def test_public_lvs_input_and_native_geometry_keep_values(self):
        text='.subckt t tie body\nR1 tie body ptap1 A=4p P=8u\n.ends t\n'
        ref,proof=draft.reference_geometry(text,self.tech);native,changes=draft.extracted_geometry(text)
        self.assertEqual(ref,native);self.assertIn('XICSTUDIO_TAP_R1 tie body ptap1 A=4p P=8u',native)

    def test_all_simulation_faults_require_rejection(self):
        for parameters in ('w=2u l=2u r=82','w=0 l=2u r=1','w=2u l=2u r=81.6666666667 m=2',
                           'w=2u l=2u','w=2u l=2u r=81.6666666667 w=2u','w=2u l=2u r={r}',
                           'w=nan l=2u r=1','w=1e200 l=1e200 r=1'):
            with self.subTest(parameters=parameters),self.assertRaises(ValueError):
                draft.reference_geometry('X1 tie body ntap1 '+parameters+'\n',self.tech)

    def test_changed_symbol_identity_and_unknown_parameters_are_refused(self):
        bad=clone(self.tech);entry=bad['simulation']['catalog']['sg13g2_pr/ntap1.sym'];bad['package_lock']['files'][entry['source']]='0'*64
        with self.assertRaisesRegex(ValueError,'Changed IHP tap'):draft.reference_geometry('X1 a b ntap1 w=2u l=2u r=81.6666666667',bad)
        with self.assertRaises(ValueError):draft.extracted_geometry('R1 a b ntap1 A=4p P=8u r=42')

    def test_duplicate_names_after_conversion_are_refused(self):
        text='R1 a b ntap1 A=4p P=8u\nXICSTUDIO_TAP_R1 a b other A=4p P=8u\n'
        with self.assertRaisesRegex(ValueError,'Duplicate instance'):draft.extracted_geometry(text)
        with self.assertRaisesRegex(ValueError,'Duplicate instance'):draft.reference_geometry(text,self.tech)

    def test_instance_names_are_local_to_each_reference_subcircuit(self):
        text=''.join(f'.subckt {name} a b\nR1 a b ntap1 A=4p P=8u\n.ends {name}\n' for name in ('first','second'))
        converted,records=draft.reference_geometry(text,self.tech)
        self.assertEqual(len(records),2);self.assertEqual(converted.count('XICSTUDIO_TAP_R1'),2)

    def test_unrelated_models_and_other_pdks_remain_untouched(self):
        text='R1 a b rsil w=2u l=5u\nX2 a b other r=1\n'
        self.assertEqual(draft.extracted_geometry(text),(text,[]));self.assertEqual(draft.reference_geometry(text,self.tech),(text,[]))
        text='X1 a b ntap1 w=2u l=2u r=1\n';self.assertEqual(draft.reference_geometry(text,{}),(text,[]))

    def test_strict_setup_removes_only_tap_permutation_and_reduction_membership(self):
        source=(repo/'icstudio/assets/pdks/ihp-sg13g2/libs.tech/netgen/ihp-sg13g2_setup.tcl').read_bytes();result=draft.strict_setup(source)
        for name in ('ntap1','ptap1'):self.assertNotIn(('lappend devices '+name+'\n').encode(),result)
        self.assertIn(b'lappend devices rsil\n',result)
        with self.assertRaises(ValueError):draft.strict_setup(result)


if __name__=='__main__':unittest.main()
