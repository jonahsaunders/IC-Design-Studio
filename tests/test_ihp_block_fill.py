import tempfile
import unittest
from pathlib import Path
import klayout.db as k
from scripts.prepare_ihp_block_fill import LAYERS, validate_input, merge_fill


class IHPFillTests(unittest.TestCase):
    def fixture(self):
        layout=k.Layout();layout.dbu=.001;top=layout.create_cell('top')
        top.shapes(layout.layer(5,0)).insert(k.Box(0,0,10000,10000))
        top.shapes(layout.layer(8,0)).insert(k.Box(19000,19000,20000,20000))
        top.shapes(layout.layer(8,0)).insert(k.Box(0,0,100,100))
        return layout

    def test_missing_poly_density_is_not_hidden_by_new_dummy_transistors(self):
        layout=self.fixture();layout.top_cell().shapes(layout.layer(5,0)).clear()
        with self.assertRaisesRegex(ValueError,'Existing poly'):
            validate_input(layout,'top',[0,0,20000,20000])

    def test_resized_die_and_already_filled_layout_are_rejected(self):
        layout=self.fixture()
        with self.assertRaisesRegex(ValueError,'exact original'):
            validate_input(layout,'top',[0,0,25000,25000])
        layout.top_cell().shapes(layout.layer(1,22)).insert(k.Box(11000,11000,14000,14000))
        with self.assertRaisesRegex(ValueError,'already contains fill'):
            validate_input(layout,'top',[0,0,20000,20000])

    def test_current_and_historical_chip_boundary_mappings_are_rejected(self):
        for layer in (39,189,235):
            layout=self.fixture();layout.top_cell().shapes(layout.layer(layer,0)).insert(k.Box(0,0,20000,20000))
            with self.assertRaisesRegex(ValueError,'Chip seal/boundary'):
                validate_input(layout,'top',[0,0,20000,20000])

    def test_unexpected_circuit_mask_and_new_mos_gate_are_rejected(self):
        for pair in ((5,22),(8,0),(1,22)):
            with self.subTest(layer=pair):
                layout=self.fixture();before,bounds,_=validate_input(layout,'top',[0,0,20000,20000])
                fill=k.Layout();fill.dbu=.001;top=fill.create_cell('fill')
                for layer in LAYERS:
                    top.shapes(fill.layer(layer,22)).insert(k.Box(11000,11000,14000,14000))
                top.shapes(fill.layer(*pair)).insert(k.Box(1000,1000,4000,4000))
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(ValueError):
                        merge_fill(layout,fill,Path(directory)/'filled.gds',before,bounds)

    def test_serialized_fill_preserves_every_original_mask(self):
        layout=self.fixture();before,bounds,_=validate_input(layout,'top',[0,0,20000,20000])
        fill=k.Layout();fill.dbu=.001;top=fill.create_cell('fill')
        for layer in LAYERS:
            top.shapes(fill.layer(layer,22)).insert(k.Box(11000,11000,14000,14000))
        with tempfile.TemporaryDirectory() as directory:
            counts,density=merge_fill(layout,fill,Path(directory)/'filled.gds',before,bounds)
        self.assertEqual(len(counts),8)
        self.assertEqual(density['5'],25)
