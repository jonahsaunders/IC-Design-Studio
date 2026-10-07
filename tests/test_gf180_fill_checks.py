"""Written GDS controls for checks missing from the pinned native GF180 deck."""
from pathlib import Path
import tempfile
import unittest

import klayout.db as k
from scripts import check_gf180_fill as fill


class FillChecksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.layout = k.Layout(); self.layout.dbu = .001
        self.top = self.layout.create_cell('coupon')
        self.shape(63, 0, (0, 0, 100000, 100000))

    def shape(self, layer, datatype, box):
        self.top.shapes(self.layout.layer(layer, datatype)).insert(k.Box(*box))

    def inspect(self, bounds=(0, 0, 100, 100), variant='C'):
        path = self.root/'coupon.gds'; self.layout.write(str(path))
        return fill.inspect(path, bounds, top_name='coupon', variant=variant)

    def failed(self, report, rule, layer):
        return any(x['rule'] == rule and x['layer'] == layer and x['status'] == 'failed' for x in report['checks'])

    def test_absent_layers_are_density_failures(self):
        report = self.inspect()
        self.assertEqual(report['failed_checks'], 7)
        self.assertTrue(all(self.failed(report, 'global-density', n) for n in fill.LAYERS))
        self.assertFalse(report['qualified'])

    def test_correct_size_controls_and_corresponding_faults(self):
        for layer, name, size, rule in [(22,'comp',5000,'DCF.1c/10'),
                (30,'poly',5600,'DPF.1/10'),(34,'m1',2000,'DM.1')]:
            with self.subTest(layer=name):
                self.layout.clear_layer(self.layout.layer(layer,4))
                self.shape(layer,4,(50000,50000,50000+size,50000+size))
                self.assertFalse(self.failed(self.inspect(),rule,name))
                self.layout.clear_layer(self.layout.layer(layer,4))
                self.shape(layer,4,(50000,50000,51000,51000))
                self.assertTrue(self.failed(self.inspect(),rule,name))

    def test_dummy_poly_must_match_comp_but_comp_can_exist_alone(self):
        self.shape(22,4,(50000,50000,55000,55000))
        self.assertFalse(self.failed(self.inspect(),'DPF.1-enclosure','poly'))
        self.shape(30,4,(49700,49700,55300,55300))
        self.assertFalse(self.failed(self.inspect(),'DPF.1-enclosure','poly'))
        self.layout.clear_layer(self.layout.layer(22,4))
        self.assertTrue(self.failed(self.inspect(),'DPF.1-enclosure','poly'))

    def test_metal_spacing_limit_and_overlap_are_detected(self):
        self.shape(34,4,(20000,20000,22000,22000))
        for gap, failed in [(2000,False),(1995,True),(0,True),(-1000,True)]:
            with self.subTest(gap=gap):
                self.layout.clear_layer(self.layout.layer(34,0))
                self.shape(34,0,(22000+gap,20000,26000+gap,22000))
                self.assertEqual(self.failed(self.inspect(),'DM.3','m1'),failed)

    def test_dummy_spacing_and_grid_faults_are_detected(self):
        self.shape(34,4,(20000,20000,22000,22000))
        self.shape(34,4,(22975,20000,24975,22000))
        self.assertTrue(self.failed(self.inspect(),'DM.2b','m1'))
        self.shape(81,4,(20001,20000,22001,22000))
        self.assertTrue(self.failed(self.inspect(),'5-nm-grid','m5'))

    def test_density_is_union_of_circuit_and_dummy_including_poly(self):
        self.shape(30,0,(10000,10000,15000,15000))
        self.shape(30,4,(10000,10000,15600,15600))
        self.assertAlmostEqual(self.inspect()['density']['poly']['total_percent'],.3136)

    def test_empty_die_margins_remain_in_density_denominator(self):
        self.shape(34,0,(0,0,60000,50000))
        report=self.inspect(bounds=(0,0,200,200))
        self.assertAlmostEqual(report['density']['m1']['total_percent'],7.5)
        self.assertEqual(report['geometry_extent_um'],[0,0,100,100])

    def test_extent_and_stack_mismatch_rejected(self):
        for bounds in [(0,0,50,50),(0,0,100.0001,100),(0,0,float('nan'),100),(100,0,0,100)]:
            with self.subTest(bounds=bounds), self.assertRaises(ValueError): self.inspect(bounds)
        with self.assertRaisesRegex(ValueError,'five-metal'): self.inspect(variant='A')
        self.shape(53,0,(10000,10000,15000,15000))
        with self.assertRaisesRegex(ValueError,'sixth metal'): self.inspect()

    def test_density_passing_layout_does_not_claim_complete_qualification(self):
        for layer in fill.LAYERS.values(): self.shape(layer,0,(0,0,60000,50000))
        for variant in ('C','D'):
            report=self.inspect(variant=variant)
            self.assertEqual(report['status'],'checks_passed_coverage_incomplete')
            self.assertFalse(report['qualified']); self.assertTrue(report['unqualified_requirements'])


if __name__ == '__main__': unittest.main()
