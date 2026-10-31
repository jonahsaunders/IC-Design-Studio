import tempfile
import unittest
from pathlib import Path
import klayout.db as k
from scripts.prepare_ihp_block_fill import (LAYERS, validate_input, merge_fill, substrate_implant,
                                           masks, exclusion_region, generation_settings)


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

    def test_p_type_changes_the_delivered_implant_and_preserves_original_circuit(self):
        layout=self.fixture();before,bounds,_=validate_input(layout,'top',[0,0,20000,20000])
        fill=k.Layout();fill.dbu=.001;top=fill.create_cell('fill')
        for layer in LAYERS:
            top.shapes(fill.layer(layer,22)).insert(k.Box(11000,11000,14400,14400))
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'filled.gds'
            counts,_=merge_fill(layout,fill,target,before,bounds,'p-substrate')
            readback=k.Layout();readback.read(str(target));after=masks(readback)
        self.assertEqual(counts['14/0'],1)
        self.assertTrue((after[14,0]^k.Region(k.Box(10820,10820,14580,14580))).is_empty())
        for pair,region in before.items():
            self.assertTrue((region-after[pair]).is_empty())
        self.assertEqual(readback.top_cell().bbox(),bounds)

    def test_p_type_cannot_reimplant_circuit_or_isolated_well_material(self):
        active=k.Region(k.Box(1000,1000,4400,4400));bounds=k.Box(0,0,20000,20000)
        for pair in ((1,0),(5,0),(6,0),(7,0),(7,21),(14,0),(26,0),(28,0),(31,0),(32,0),(44,0),(46,21),(111,0)):
            with self.subTest(layer=pair):
                with self.assertRaisesRegex(ValueError,'process modifier'):
                    substrate_implant(active,{pair:k.Region(k.Box(900,900,1050,1050))},bounds)

    def test_pwell_implant_clipping_covers_fill_without_resizing_die(self):
        active=k.Region(k.Box(0,0,3400,3400));bounds=k.Box(0,0,20000,20000)
        added=substrate_implant(active,{},bounds)
        self.assertTrue((active-added).is_empty())
        self.assertTrue((added-k.Region(bounds)).is_empty())
        self.assertEqual(added.bbox(),k.Box(0,0,3580,3580))

    def test_nonrectangular_and_outside_active_cannot_be_hidden_by_clipping(self):
        bounds=k.Box(0,0,20000,20000)
        for active in (k.Region(k.Box(-5,0,3400,3400)), k.Region()):
            with self.assertRaises(ValueError):substrate_implant(active,{},bounds)
        active=k.Region(k.Box(0,0,3400,3400))-k.Region(k.Box(0,0,1000,1000))
        with self.assertRaisesRegex(ValueError,'rectangular'):substrate_implant(active,{},bounds)

    def test_exclusion_view_preserves_original_geometry_and_stays_inside_block(self):
        layout=self.fixture();view=self.fixture()
        view.top_cell().shapes(view.layer(10000,0)).insert(k.Box(10000,10000,18000,18000))
        self.assertEqual(exclusion_region(layout,view).area(),64000000)
        self.assertIsNone(layout.find_layer(10000,0))
        view.top_cell().shapes(view.layer(8,0)).insert(k.Box(500,500,1000,1000))
        with self.assertRaisesRegex(ValueError,'changed original'):exclusion_region(layout,view)
        view=self.fixture();view.top_cell().shapes(view.layer(10000,0)).insert(k.Box(0,0,21000,21000))
        with self.assertRaisesRegex(ValueError,'beyond'):exclusion_region(layout,view)

    def test_missing_preexisting_and_wrong_grid_exclusions_fail(self):
        layout=self.fixture();view=self.fixture()
        with self.assertRaisesRegex(ValueError,'Missing'):exclusion_region(layout,view)
        view.top_cell().shapes(view.layer(10000,0)).insert(k.Box(10000,10000,18000,18000))
        view.dbu=.005
        with self.assertRaisesRegex(ValueError,'grid'):exclusion_region(layout,view)
        layout=self.fixture();view=self.fixture()
        for item in (layout,view):item.top_cell().shapes(item.layer(10000,0)).insert(k.Box(10000,10000,18000,18000))
        with self.assertRaisesRegex(ValueError,'preexisting'):exclusion_region(layout,view)

    def test_bounded_settings_keep_native_rules_and_detect_macro_drift(self):
        script='fill_scope = source.extent\nwidth = 5.0\n'+'\n'.join(f"'distance_m{n}' => 1.5" for n in range(1,6))
        configured=generation_settings(script,True,1.35,8.)
        self.assertIn('source.input("10000/0")',configured)
        self.assertEqual(configured.count('=> 1.35'),5)
        self.assertIn('width = 8.0',configured)
        self.assertEqual(generation_settings(script),script)
        with self.assertRaisesRegex(ValueError,'Unsupported'):generation_settings(script,True,1.2,8.)
        with self.assertRaisesRegex(ValueError,'spacing'):generation_settings(script.replace("'distance_m2'", "'drift'"),True,1.4,8.)
