import unittest
import tempfile
from pathlib import Path
import klayout.db as k
from scripts.ihp_fill_capacitance_input import METALS,MODIFIERS,prepare,write


class FillElectricalInputTests(unittest.TestCase):
    def fixture(self):
        ly=k.Layout();ly.dbu=.001;c=ly.create_cell('block')
        for n in (1,*METALS.values()):c.shapes(ly.layer(n,22)).insert(k.Box(5000,5000,8400,8400))
        c.shapes(ly.layer(8,0)).insert(k.Box(0,0,1000,1000))
        labels=dict(nets=[dict(net='signal',alias='NET000000',pins=[dict(layer='Metal1',box_nm=[0,0,1000,1000])])])
        return ly,c,labels

    def test_active_and_metal_have_explicit_separate_coverage(self):
        for state,expected in [('original',0),('metal',7),('active',8)]:
            ly,c,labels=self.fixture();r=prepare(ly,labels,state)
            self.assertEqual(sum(p['mapped'] for p in r['fill']),expected)
            active=next(p for p in r['fill'] if p['layer']==1)
            self.assertEqual((active['junction_model'],active['width_um'],active['length_um']),('dantenna',3.4,3.4))

    def test_every_process_modifier_is_rejected(self):
        for pair in MODIFIERS:
            with self.subTest(pair=pair):
                ly,c,labels=self.fixture();c.shapes(ly.layer(*pair)).insert(k.Box(5100,5100,5200,5200))
                with self.assertRaisesRegex(ValueError,'modifier'):prepare(ly,labels,'active')

    def test_wrong_terminal_or_colliding_identity_is_rejected(self):
        ly,c,labels=self.fixture();labels['nets'][0]['pins'][0]['box_nm']=[2000,2000,3000,3000]
        with self.assertRaisesRegex(ValueError,'contained'):prepare(ly,labels,'active')
        ly,c,labels=self.fixture();labels['nets']*=2
        with self.assertRaisesRegex(ValueError,'identity'):prepare(ly,labels,'active')

    def test_does_not_convert_poly_dummy_transistors(self):
        ly,c,labels=self.fixture();c.shapes(ly.layer(5,22)).insert(k.Box(0,5000,1000,6000))
        with self.assertRaisesRegex(ValueError,'Poly fill'):prepare(ly,labels,'active')

    def test_fill_contact_with_circuit_is_rejected(self):
        for layer in (1,*METALS.values()):
            ly,c,labels=self.fixture();c.shapes(ly.layer(layer,0)).insert(k.Box(8400,5000,9000,6000))
            with self.assertRaisesRegex(ValueError,'touches'):prepare(ly,labels,'active')

    def test_written_masks_and_alias_labels_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            ly,c,labels=self.fixture();source=Path(folder)/'input.gds';target=Path(folder)/'output.gds';ly.write(str(source))
            result=write(source,labels,'active',target)
            self.assertTrue(result['physical_masks_and_labels_readback_verified'])
            with self.assertRaisesRegex(ValueError,'new'):write(source,labels,'active',target)


if __name__=='__main__':unittest.main()
