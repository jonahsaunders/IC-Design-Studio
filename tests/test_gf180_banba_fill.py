"""Check real written fill, including faults an empty upstream report cannot catch."""
from pathlib import Path
import tempfile
import unittest

import klayout.db as k

from scripts import fill_gf180_banba as fill


class FillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        layout = k.Layout(); layout.dbu = .001
        top = layout.create_cell('banba_layout')
        top.shapes(layout.layer(34, 0)).insert(k.Box(0, 0, 5000, 5000))
        cls.source = cls.root/'core.gds'; layout.write(str(cls.source))
        cls.report = fill.build(cls.source, cls.root/'filled', halo_um=300)
        cls.gds = cls.root/'filled/banba-density.gds'
        cls.bounds = k.Box(-300000, -300000, 305000, 305000)

    def test_written_density_includes_full_expanded_boundary(self):
        report = self.report
        self.assertTrue(report['core_masks_unchanged'])
        self.assertAlmostEqual(report['area_mm2'], .605**2)
        self.assertFalse(report['signoff'])
        self.assertGreater(report['density_percent']['comp'], 25)
        self.assertGreater(report['density_percent']['poly'], 14)
        self.assertTrue(all(report['density_percent'][name] > 30 for name in ('m1', 'm2', 'm3', 'm4')))
        self.assertEqual(report['fill']['poly']['tiles'], report['fill']['comp']['tiles'])

    def check_fault(self, name, mutate, error):
        layout = k.Layout(); layout.read(str(self.gds))
        mutate(layout, layout.top_cell())
        output = self.root/('fault-'+name+'.gds'); layout.write(str(output))
        with self.assertRaisesRegex(ValueError, error):
            fill.inspect(self.source, output, self.bounds)

    def test_circuit_edits_and_missing_boundary_are_rejected(self):
        self.check_fault('core', lambda layout, top:
            top.shapes(layout.layer(34, 0)).insert(k.Box(0, 0, 5010, 5000)), 'Circuit mask changed')
        self.check_fault('boundary', lambda layout, top:
            top.shapes(layout.layer(*fill.BORDER)).clear(), 'density denominator')

    def test_missing_poly_and_intrusive_fill_are_rejected(self):
        self.check_fault('no-poly', lambda layout, top:
            layout.clear_layer(layout.layer(30, 4)), 'Missing poly fill')
        self.check_fault('intrusion', lambda layout, top:
            top.shapes(layout.layer(22, 4)).insert(k.Box(0, 0, 5000, 5000)), 'keepout')

    def test_arrays_preserve_staggered_tiles_and_holes(self):
        expected = fill.candidates(k.Box(0, 0, 100000, 100000), 2000, 3200, 500)
        expected = expected.not_interacting(k.Region(k.Box(45000, 45000, 55000, 55000)))
        layout = k.Layout(); top = layout.create_cell('test')
        fill.insert_arrays(layout, top, 'test', expected, [((34, 4), (0, 0, 2000, 2000))], 3200)
        actual = fill.region(layout, top, (34, 4))
        self.assertTrue((actual ^ expected).is_empty())
        self.assertTrue(actual.space_check(980).is_empty())

    def test_subgrid_halo_and_refilling_are_rejected(self):
        for i, halo in enumerate([0, float('nan'), 300.0001, 300.001]):
            with self.subTest(halo=halo), self.assertRaisesRegex(ValueError, 'Halo'):
                fill.build(self.source, self.root/f'bad-{i}', halo)
        with self.assertRaisesRegex(ValueError, 'already contains fill'):
            fill.build(self.gds, self.root/'refilled')


if __name__ == '__main__':
    unittest.main()
