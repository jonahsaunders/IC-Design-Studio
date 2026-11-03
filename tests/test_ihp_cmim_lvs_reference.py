"""Source-bound IHP MiM physical reference projection and fail-closed controls."""
import copy
import unittest
from unittest.mock import patch

from icstudio.catalog import create_device
from icstudio.catalog_migration import emit
from icstudio.model import file_digest
from icstudio.native_spice import cmim_lvs_unique_names,lvs_defaults
from scripts.qualify_standard_mos import load_technology


class CmimReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.tech=load_technology('ihp-sg13g2')[0]

    def test_catalog_simulation_unchanged_and_lvs_bound_to_symbol(self):
        d=create_device(self.tech,'sg13g2_pr/cap_cmim.sym','C1');d['nets']={'c0':'PLUS','c1':'MINUS'}
        simulation=emit(d,self.tech);self.assertTrue(simulation.startswith('X_C1 PLUS MINUS cap_cmim '))
        converted,proof=lvs_defaults(simulation,self.tech);self.assertEqual(emit(d,self.tech,'lvs'),converted)
        self.assertTrue(converted.startswith('CX_C1 PLUS MINUS cap_cmim '));self.assertIn('A=4.9E-11',converted)
        self.assertIn('P=0.000028',converted);self.assertNotIn('mm_ok',converted)
        self.assertEqual(emit(d,self.tech),simulation);self.assertEqual(len(proof),1)
        self.assertEqual(proof[0]['proof']['sha256'],self.tech['package_lock']['files'][proof[0]['proof']['source']])
        checked,receipt=lvs_defaults(converted,self.tech);self.assertEqual(checked,converted);self.assertFalse(receipt[0]['changed'])

    def test_unit_scaling_multiplicity_order_and_continuation(self):
        text='X1 TOP BOTTOM cap_cmim w=75u\n+ l=74.98u m=3 mm_ok=0'
        actual,_=lvs_defaults(text,self.tech)
        self.assertEqual(actual,'CX1 TOP BOTTOM cap_cmim w=75u l=74.98u m=3 A=5.62350E-9 P=0.00029996')
        checked,receipt=lvs_defaults(actual,self.tech);self.assertEqual(checked,actual);self.assertFalse(receipt[0]['changed'])

    def test_explicit_physical_reference_binds_missing_area_and_rejects_contradiction(self):
        source='C1 P N cap_cmim w=75u l=74.98u m=3'
        result,proof=lvs_defaults(source,self.tech)
        self.assertEqual(result,source+' A=5.62350E-9 P=0.00029996')
        self.assertEqual(len(proof),1);checked,receipt=lvs_defaults(result,self.tech);self.assertEqual(checked,result);self.assertFalse(receipt[0]['changed'])
        for altered in (result.replace('A=5.62350E-9','A=1p'),result+' A=5p',source+' mm_ok=1',source+' P={expr}'):
            with self.subTest(altered=altered),self.assertRaises(ValueError):lvs_defaults(altered,self.tech)
        self.assertEqual(proof[0]['proof']['geometry_reader_sha256'],'c71b6713d8a62055d3d8e9e75a7f5f78140001bf76e3fa573b9883fab5e49f06')

    def test_magic_keeps_x_and_rejects_incompatible_c(self):
        source='X1 P N cap_cmim w=7u l=7u m=1 mm_ok=1'
        actual,proof=lvs_defaults(source,self.tech,lvs_extractor='magic')
        self.assertEqual(actual,source.replace(' mm_ok=1',''));self.assertEqual(len(proof),1)
        self.assertNotIn('geometry_reader',proof[0]['proof'])
        def unavailable(path):
            if path.name=='custom_reader.lvs':raise FileNotFoundError(path)
            return file_digest(path)
        with patch('icstudio.model.file_digest',side_effect=unavailable):
            self.assertEqual(lvs_defaults(source,self.tech,lvs_extractor='magic')[0],actual)
            with self.assertRaises(FileNotFoundError):lvs_defaults(source,self.tech,lvs_extractor='ihp-klayout')
        checked,receipt=lvs_defaults(actual,self.tech,lvs_extractor='magic');self.assertEqual(checked,actual);self.assertFalse(receipt[0]['changed'])
        with self.assertRaisesRegex(ValueError,'public IHP KLayout checker'):
            lvs_defaults('C1 P N cap_cmim w=7u l=7u m=1 A=49p P=28u',self.tech,lvs_extractor='magic')
        self.assertTrue(lvs_defaults(source,self.tech,lvs_extractor='ihp-klayout')[0].startswith('CX1 P N'))

    def test_high_precision_literal_does_not_round_area(self):
        text='X1 P N cap_cmim w=1.123456789012345678901234567890123456789u l=2u m=1'
        result,_=lvs_defaults(text,self.tech)
        self.assertIn('A=2.246913578024691357802469135780246913578E-12',result)

    def test_malformed_unknown_and_expression_are_rejected(self):
        base='X1 P N cap_cmim w=2u l=7u m=1 mm_ok=1'
        for text in (base+' foo=1',base+' w=2u',base.replace('w=2u','w={width}'),base.replace('w=2u','w=nan'),
                     base.replace('m=1','m=0'),base.replace('mm_ok=1','mm_ok=2'),base.replace('mm_ok=1','mm_ok={flag}'),
                     base.replace('l=7u',''),base.replace('P N cap_cmim','P N EXTRA cap_cmim'),base+' A=1p'):
            with self.subTest(text=text),self.assertRaises(ValueError):lvs_defaults(text,self.tech)
        untouched='X1 P N other w=2u l=7u m=1 mm_ok=1'
        self.assertEqual(lvs_defaults(untouched,self.tech),(untouched,[]))

    def test_changed_source_or_catalog_cannot_authorize_conversion(self):
        line='X1 P N cap_cmim w=2u l=7u m=1'
        for name in ('cap_cmim.sym','capacitors_mod.lib','custom_reader.lvs'):
            def changed(path):return '0'*64 if path.name==name else file_digest(path)
            with self.subTest(name=name),patch('icstudio.model.file_digest',side_effect=changed),self.assertRaises(ValueError):
                lvs_defaults(line,self.tech)
        tech=copy.deepcopy(self.tech);tech['simulation']['catalog']['sg13g2_pr/cap_cmim.sym']['pin_order'].reverse()
        with self.assertRaises(ValueError):lvs_defaults(line,tech)
        for kind in ('wrong-model-source','missing-model-lock'):
            tech=copy.deepcopy(self.tech)
            if kind=='wrong-model-source':tech['simulation']['catalog']['sg13g2_pr/cap_cmim.sym']['model_source']='other.lib'
            else:del tech['package_lock']['files']['libs.tech/ngspice/models/capacitors_mod.lib']
            with self.subTest(kind=kind),self.assertRaises(ValueError):lvs_defaults(line,tech)

    def test_projected_names_reject_same_scope_collisions(self):
        line='X1 P N cap_cmim w=2u l=7u m=1'
        with self.assertRaisesRegex(ValueError,'collides'):lvs_defaults('.subckt a P N\n'+line+'\nCX1 P N 1p\n.ends a',self.tech)
        lvs_defaults('.subckt a P N\n'+line+'\n.ends a\n.subckt b P N\nCX1 P N 1p\n.ends b',self.tech)
        with self.assertRaises(ValueError):cmim_lvs_unique_names('.subckt a P N\nCX1 P N cap_cmim w=2u l=7u m=1\nCX1 P N 1p\n.ends a')
        same='X_C1 P N cap_cmim w=2u l=7u m=1'
        with self.assertRaises(ValueError):lvs_defaults('.subckt a P N\n'+same+'\ncx_c1 P N 1p\n.ends a',self.tech)
        distinct='.subckt a P N\n'+same+'\n.ends a\n.subckt b P N\n'+same+'\n.ends b'
        actual,proof=lvs_defaults(distinct,self.tech);self.assertEqual(actual.count('CX_C1 P N cap_cmim'),2);self.assertEqual(len(proof),2)


if __name__=='__main__':unittest.main()
