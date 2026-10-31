"""Boundary and negative controls for supplemental grid/window diagnostics."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as k

from scripts import sky130_grid_geometry as grid
from scripts import sky130_density_windows as density


def layout():
    result = k.Layout()
    result.dbu = .001
    return result, result.create_cell('TOP')


def counts(result):
    return {row['rule']: row['violations'] for row in result['checks']}


class GridTests(unittest.TestCase):
    def test_every_ordinary_boundary_accepts_five_nm_and_rejects_one_nm_shift(self):
        known, _ = grid.layer_metadata()
        for pair in sorted(known - grid.FINE_GRID):
            with self.subTest(pair=pair):
                ly, top = layout()
                shapes = top.shapes(ly.layer(*pair))
                shapes.insert(k.Box(-100, -100, 100, 100))
                self.assertEqual(grid.check(ly)['status'], 'PASS')
                shapes.insert(k.Box(1, 0, 101, 100))
                self.assertGreater(counts(grid.check(ly))['grid.boundaries'], 0)

    def test_only_explicit_fine_grid_purposes_accept_one_nm(self):
        for pair in sorted(grid.FINE_GRID):
            with self.subTest(pair=pair):
                ly, top = layout()
                top.shapes(ly.layer(*pair)).insert(k.Box(1, 1, 101, 101))
                self.assertEqual(grid.check(ly)['status'], 'PASS')
        ly, top = layout()
        top.shapes(ly.layer(68, 20)).insert(k.Box(1, 1, 101, 101))
        self.assertEqual(grid.check(ly)['status'], 'FAIL')

    def test_internal_overlap_and_holes_cannot_hide_grid_errors(self):
        ly, top = layout()
        shapes = top.shapes(ly.layer(68, 20))
        shapes.insert(k.Box(-100, -100, 1000, 1000))
        shapes.insert(k.Box(1, 1, 101, 101))
        polygon = k.Polygon(k.Box(2000, 2000, 3000, 3000))
        polygon.insert_hole([k.Point(2101, 2100), k.Point(2200, 2100), k.Point(2200, 2200)])
        shapes.insert(polygon)
        self.assertGreaterEqual(counts(grid.check(ly))['grid.boundaries'], 5)

    def test_nested_mirror_rotation_and_array_origins(self):
        ly, top = layout()
        child = ly.create_cell('child')
        child.shapes(ly.layer(68, 20)).insert(k.Box(0, 0, 100, 100))
        middle = ly.create_cell('middle')
        middle.insert(k.CellInstArray(child.cell_index(), k.Trans(1, True, -200, 300)))
        top.insert(k.CellInstArray(middle.cell_index(), k.Trans(), k.Vector(1001, 0), k.Vector(0, 1000), 2, 2))
        self.assertEqual(counts(grid.check(ly))['grid.boundaries'], 8)

    def test_complex_transforms_are_rejected_before_fractional_rounding(self):
        for trans in (k.ICplxTrans(.5, 0, False, 0, 0), k.ICplxTrans(1, 45, False, 0, 0)):
            ly, top = layout()
            child = ly.create_cell('child')
            child.shapes(ly.layer(68, 20)).insert(k.Box(1, 1, 101, 101))
            top.insert(k.CellInstArray(child.cell_index(), trans))
            result = grid.check(ly)
            self.assertEqual(result['status'], 'FAIL')
            self.assertEqual(counts(result)['profile.transforms'], 1)

    def test_path_edges_not_just_centerlines_are_checked(self):
        for width, expected in ((10, 'PASS'), (12, 'FAIL')):
            ly, top = layout()
            top.shapes(ly.layer(68, 20)).insert(k.Path([k.Point(0, 0), k.Point(100, 0)], width))
            self.assertEqual(grid.check(ly)['status'], expected)

    def test_fractional_diagonal_and_round_paths_fail_closed(self):
        paths = [k.Path([k.Point(0, 0), k.Point(100, 0)], 11),
                 k.Path([k.Point(0, 0), k.Point(100, 100)], 10),
                 k.Path([k.Point(0, 0), k.Point(100, 0)], 10, 5, 5, True)]
        for path in paths:
            ly, top = layout()
            top.shapes(ly.layer(68, 20)).insert(path)
            self.assertEqual(counts(grid.check(ly))['profile.path_semantics'], 1)

    def test_path_end_extensions_are_checked(self):
        ly, top = layout()
        top.shapes(ly.layer(68, 20)).insert(k.Path([k.Point(0, 0), k.Point(100, 0)], 10, 1, 0))
        self.assertGreater(counts(grid.check(ly))['grid.boundaries'], 0)

    def test_text_anchors_are_reported_separately(self):
        ly, top = layout()
        top.shapes(ly.layer(68, 20)).insert(k.Box(0, 0, 100, 100))
        top.shapes(ly.layer(68, 5)).insert(k.Text('signal', k.Trans(51, 50)))
        result = counts(grid.check(ly))
        self.assertEqual(result['grid.boundaries'], 0)
        self.assertEqual(result['grid.text_anchors'], 1)

    def test_unknown_purpose_empty_layout_and_bad_units_fail(self):
        ly, top = layout()
        self.assertEqual(grid.check(ly)['status'], 'FAIL')
        top.shapes(ly.layer(900, 900)).insert(k.Box(0, 0, 100, 100))
        self.assertEqual(counts(grid.check(ly))['profile.known_purposes'], 1)
        ly.dbu = .002
        with self.assertRaises(ValueError):
            grid.check(ly)

    def test_gds_readback_binds_exact_bytes(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / 'layout.gds'
            ly, top = layout()
            top.shapes(ly.layer(68, 20)).insert(k.Box(0, 0, 100, 100))
            ly.write(str(path))
            result = grid.audit(path)
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(result['gds_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertFalse(result['qualified'])

    def test_capture_cannot_change_or_omit_source_bytes(self):
        original = json.loads(grid.SOURCES.read_text())
        for mutation in ('changed', 'missing'):
            capture = deepcopy(original)
            name = 'docs/rules/assumptions/01-general.csv'
            if mutation == 'changed':
                capture['files'][name]['content'] = capture['files'][name]['content'].replace('0.005', '0.001')
                capture['files'][name]['sha256'] = hashlib.sha256(capture['files'][name]['content'].encode()).hexdigest()
            else:
                del capture['files'][name]
            with TemporaryDirectory() as temp:
                path = Path(temp) / 'capture.json'
                path.write_text(json.dumps(capture))
                with patch.object(grid, 'SOURCES', path), self.assertRaises(ValueError):
                    grid.source_metadata()


class DensityTests(unittest.TestCase):
    def test_small_reference_dies_are_blocked_without_full_windows(self):
        for side, clips in ((200_000, 9), (400_000, 36)):
            result = density.check({}, [0, 0, side, side])
            self.assertEqual(result['status'], 'BLOCKED')
            self.assertEqual(result['full_windows'], 0)
            self.assertEqual(result['clipped_windows'], clips)
            self.assertTrue(any('parent-chip' in item for item in result['blockers']))

    def test_full_windows_at_exact_size_and_step_boundaries(self):
        for side, expected in ((699_999, 0), (700_000, 1), (769_999, 1), (770_000, 4)):
            result = density.check({}, [0, 0, side, side])
            self.assertEqual(result['full_windows'], expected)
            self.assertEqual(result['status'], 'BLOCKED')
            self.assertFalse(result['qualified'])

    def test_translated_die_and_clipped_denominator_are_exact(self):
        die = [-100_000, 30_000, 600_000, 730_000]
        result = density.check({(68, 20): k.Region(k.Box(*die))}, die)
        self.assertEqual(result['full_windows'], 1)
        rows = result['layers'][0]['windows']
        self.assertTrue(all(row['metal_fraction'] == 1 for row in rows))
        self.assertEqual(rows[-1]['bounds_nm'], [530_000, 660_000, 600_000, 730_000])
        self.assertEqual(rows[-1]['area_nm2'], 70_000 ** 2)

    def test_overlap_fill_and_holes_use_union_area(self):
        box = k.Box(0, 0, 700_000, 700_000)
        polygon = k.Polygon(box)
        polygon.insert_hole([k.Point(0, 0), k.Point(350_000, 0), k.Point(350_000, 700_000), k.Point(0, 700_000)])
        regions = {(68, 20): k.Region(polygon), (36, 28): k.Region(k.Box(350_000, 0, 700_000, 700_000))}
        result = density.check(regions, [0, 0, 700_000, 700_000])
        window = result['layers'][0]['windows'][0]
        self.assertEqual(window['metal_area_nm2'], 245_000_000_000)
        self.assertEqual(window['metal_fraction'], .5)
        self.assertEqual(result['layers'][1]['windows'][0]['metal_fraction'], 0)

    def test_each_metal_uses_its_own_fill_purpose(self):
        for metal, pairs in density.METALS.items():
            for pair in pairs:
                result = density.check({pair: k.Region(k.Box(0, 0, 700_000, 700_000))}, [0, 0, 700_000, 700_000])
                for row in result['layers']:
                    self.assertEqual(row['windows'][0]['metal_fraction'], 1 if row['metal'] == metal else 0)

    def test_outside_die_metal_is_not_silently_dropped(self):
        result = density.check({(68, 20): k.Region(k.Box(-5, 0, 700_000, 700_000))}, [0, 0, 700_000, 700_000])
        self.assertEqual(result['layers'][0]['outside_die_area_nm2'], 3_500_000)
        self.assertTrue(any('outside' in text for text in result['blockers']))

    def test_diagonal_boundaries_cannot_be_rounded_during_window_clipping(self):
        triangle = k.Region(k.Polygon([k.Point(0, 0), k.Point(700_005, 0), k.Point(0, 700_000)]))
        # Even a triangle hidden in a larger box must be refused before merge
        # or integer window clipping can erase its unsupported boundary.
        triangle.insert(k.Box(-5, -5, 800_000, 800_000))
        with self.assertRaisesRegex(ValueError, 'Manhattan'):
            density.check({(68, 20): triangle}, [0, 0, 700_000, 700_000])

    def test_invalid_die_bounds_are_rejected(self):
        for die in ([0, 0, 0, 1], [0, 0, 1, -1], [0, 0, 1], [0, 0, 1.1, 2], [False, 0, 1, 2]):
            with self.assertRaises(ValueError):
                density.check({}, die)

    def test_hierarchy_readback_and_fractional_path_rejection(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / 'layout.gds'
            ly, top = layout()
            child = ly.create_cell('child')
            child.shapes(ly.layer(68, 20)).insert(k.Box(0, 0, 350_000, 700_000))
            top.insert(k.CellInstArray(child.cell_index(), k.Trans(350_000, 0)))
            ly.write(str(path))
            result = density.audit(path, [0, 0, 700_000, 700_000])
            self.assertEqual(result['layers'][0]['windows'][0]['metal_fraction'], .5)
            child.shapes(ly.layer(68, 20)).insert(k.Path([k.Point(0, 0), k.Point(100, 0)], 11))
            ly.write(str(path))
            with self.assertRaisesRegex(ValueError, 'snapping'):
                density.audit(path, [0, 0, 700_000, 700_000])

    def test_cli_never_returns_success_for_unqualified_density(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / 'layout.gds'
            output = Path(temp) / 'result.json'
            ly, top = layout()
            top.shapes(ly.layer(68, 20)).insert(k.Box(0, 0, 700_000, 700_000))
            ly.write(str(path))
            with patch('sys.argv', ['density', str(path), '--die-nm', '0', '0', '700000', '700000', '--output', str(output)]):
                self.assertEqual(density.main(), 2)
            self.assertEqual(json.loads(output.read_text())['status'], 'BLOCKED')


if __name__ == '__main__':
    unittest.main()
