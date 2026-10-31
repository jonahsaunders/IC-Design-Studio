"""Prevent substrate/label joins, dropped models and stale native reports."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from icstudio import gf180_hv_verification as hv
from icstudio.layout_verification import reference,run
from icstudio.model import example
from scripts.qualify_gf180_hv_layouts import stream


class Gf180HvVerificationTests(unittest.TestCase):
    def test_contacts_and_metal_define_body_connections_in_every_orientation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for angle in (0,90,180,270):
                for fault in (None,'substrate-route','p-body-contact','n-body-contact','outer-body-contact'):
                    path=folder/f'{angle}-{fault}.gds';stream(path,4,.6,angle,fault)
                    result=hv.guard_connections(path,'coupon')
                    self.assertEqual(result['passed'],fault is None,(angle,fault,result))
                    if fault=='substrate-route':
                        self.assertTrue(any(f['kind']=='disconnected-body-metal' for f in result['failures']))

    def test_source_hashes_and_license_are_checked_before_private_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);hv.copy_assets(root)
            self.assertEqual(len(hv.assets(root)),5)
            original=(root/'gf180mcu.lvs').read_text(encoding='utf-8')
            recipe=hv.extraction_recipe(original)
            for forbidden in ('connect_implicit(', '\ncompare\n', '\nalign\n','netlist.simplify','netlist.purge','netlist.combine_devices'):
                self.assertNotIn(forbidden,recipe)
            self.assertIn('connect(ptap, icstudio_psub)',recipe)
            self.assertIn('dmos4("nmos_10p0_asym")',recipe)
            self.assertIn('"S" => nsd_ldmos.not(mvsd), "D" => nsd_ldmos.and(mvsd)',recipe)
            (root/'gf180mcu.lvs').write_text(original+'\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'changed'):hv.assets(root)
            with self.assertRaisesRegex(ValueError,'changed'):hv.extraction_recipe(original.replace('connect_implicit("*")',''))

    def test_conversion_preserves_terminals_dimensions_and_junction_parameters(self):
        for source,target in hv.MODELS.items():
            text=f'.subckt coupon D G S B\nM1 D G S B {source} W=4U L=.6U AS=3.2P AD=7.04P PS=9.6U PD=11.52U\n.ends coupon\n'
            converted,changes=hv.convert(text)
            self.assertEqual(converted,text.replace('M1','X1').replace(source,target));self.assertEqual(len(changes),1)
            for bad in (text.replace(source,'nmos_3p3'),text.replace('W=4U','W=4U W=5U'),text.replace('PD=11.52U',''),text.replace('M1','X1'),'.subckt coupon D G S B\n.ends coupon\n'):
                with self.subTest(bad=bad),self.assertRaises(ValueError):hv.convert(bad)

    def test_failed_guard_check_never_launches_device_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'open.gds';stream(source,4,.6,fault='substrate-route')
            with patch('icstudio.gf180_hv_verification._execute') as engine:
                with self.assertRaisesRegex(ValueError,'wiring failed'):
                    hv.extract('klayout',source,'coupon',[] ,{},root/'out')
                engine.assert_not_called()
            self.assertFalse(json.loads((root/'out/guard-connections.json').read_text())['passed'])

    def test_zero_findings_without_completed_full_drc_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('icstudio.gf180_hv_verification._execute',return_value='Partial check'):
                with self.assertRaisesRegex(ValueError,'did not complete'):
                    hv.drc('klayout','layout.gds','coupon',{'package_lock':{'id':'gf180mcuC'}},Path(tmp)/'drc')

    def test_wrong_process_cannot_select_high_voltage_route(self):
        p=example('empty');ref=reference('.subckt coupon a b\nR1 a b 1k\n.ends coupon','coupon')
        with tempfile.TemporaryDirectory() as tmp:
            result=run(p,p['top'],tmp,{},ref,lvs_extractor='gf180-hv-klayout')
            self.assertEqual(result['status'],'blocked');self.assertIn('GF180 C or D',result['error'])


if __name__=='__main__':unittest.main()
