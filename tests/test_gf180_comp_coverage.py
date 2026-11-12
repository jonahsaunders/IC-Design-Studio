"""Whole-array coverage compared with explicit square-to-rectangle oracles."""
import unittest
from unittest import mock
import klayout.db as k
from scripts import gf180_comp_coverage as coverage
from scripts import check_gf180_fill as fill


class CompCoverageTests(unittest.TestCase):
    entry = dict(origin_nm=[1600, 1600], stagger_sign=[1, 1])

    def inspect(self, comp=None, poly=None, dummy=None, wells=None, markers=None, bounds=None):
        w = {n: k.Region() for n in fill.WELLS}; w.update(wells or {})
        m = {n: k.Region() for n in fill.MARKERS}; m.update(markers or {})
        return coverage.inspect(comp if comp is not None else k.Region(),
            poly if poly is not None else k.Region(), dummy if dummy is not None else k.Region(),
            w, m, bounds or k.Box(0, 0, 40000, 40000), self.entry)

    def test_all_sites_match_independent_row_column_enumeration(self):
        for bounds in (k.Box(0, 0, 40000, 40000), k.Box(-13000, 1000, 71000, 67000)):
            for signs in ([1, 1], [-1, 1], [-1, -1], [1, -1]):
                entry = dict(origin_nm=[1600, 1600], stagger_sign=signs)
                expected = set()
                for row in range(-20, 20):
                    for col in range(-20, 20):
                        x = 1600+col*8000+(row % 2)*signs[0]*1600
                        y = 1600+row*8000+(col % 2)*signs[1]*1600
                        if x >= bounds.left and y >= bounds.bottom and x+5000 <= bounds.right and y+5000 <= bounds.top:
                            expected.add((x, y, x+5000, y+5000))
                self.assertEqual({(b.left, b.bottom, b.right, b.top) for b in coverage.sites(bounds, entry)}, expected)

    def test_missing_site_is_not_hidden_by_neighbors_or_partial_fill(self):
        # Four edge sites of the 5-by-5 index range cross the fixed footprint.
        first, missing = self.inspect(); self.assertEqual(first['candidate_sites'], 21)
        complete, _ = self.inspect(dummy=missing); self.assertEqual(complete['missing_sites'], 0)
        b = missing[0].bbox(); damaged = missing-k.Region(b)
        damaged.insert(k.Box(b.left, b.bottom, b.right-5, b.top))
        result, _ = self.inspect(dummy=damaged)
        self.assertEqual(result['missing_sites'], 1); self.assertFalse(result['qualified'])

    def test_euclidean_clearance_matches_rectangle_distance_including_corners(self):
        rect = k.Box(10000, 10000, 16000, 16000)
        for key, distance in (('comp', 3500), ('poly', 1500)):
            result, _ = self.inspect(**{key: k.Region(rect)})
            expected = []
            for b in coverage.sites(k.Box(0, 0, 40000, 40000), self.entry):
                dx = max(rect.left-b.right, b.left-rect.right, 0)
                dy = max(rect.bottom-b.top, b.bottom-rect.top, 0)
                if dx*dx+dy*dy >= distance*distance:
                    expected.append([b.left, b.bottom, b.right, b.top])
            self.assertEqual(sorted(result['missing_boxes_nm']), sorted(expected))

    def test_exact_limit_is_legal_but_five_nm_less_is_blocked(self):
        for gap, expected in ((3500, True), (3495, False)):
            row, _ = self.inspect(comp=k.Region(k.Box(6600+gap, 1600, 16000, 6600)))
            self.assertEqual([1600, 1600, 6600, 6600] in row['missing_boxes_nm'], expected)

    def test_well_inside_outside_crossing_and_hole_boundaries(self):
        site = [1600, 1600, 6600, 6600]
        for name, distance in (('Nwell', 1300), ('DNWELL', 4000), ('LVPWELL', 1300), ('Dualgate', 1300)):
            for d, expected in ((distance, True), (distance-5, False)):
                inside = k.Region(k.Box(1600-d, 1600-d, 6600+d, 6600+d))
                outside = k.Region(k.Box(6600+d, 1600, 30000, 20000))
                hole = k.Region(k.Box(-10000, -10000, 50000, 50000))-inside
                for well in (inside, outside, hole):
                    row, _ = self.inspect(wells={name: well})
                    self.assertEqual(site in row['missing_boxes_nm'], expected, (name, d, well))
            row, _ = self.inspect(wells={name: k.Region(k.Box(3000, 0, 50000, 50000))})
            self.assertNotIn(site, row['missing_boxes_nm'])

    def test_marker_containment_and_scope_are_not_omitted(self):
        for name in ('RES_MK', 'NDMY', 'IND_MK', 'Pad'):
            row, _ = self.inspect(markers={name: k.Region(k.Box(0, 0, 40000, 40000))})
            self.assertEqual(row['unblocked_sites'], 0)
        # Markers for poly/metal do not silently excuse COMP coverage.
        row, _ = self.inspect(markers={'PMNDMY': k.Region(k.Box(0, 0, 40000, 40000))})
        self.assertEqual(row['missing_sites'], 21)
        with mock.patch.object(coverage, 'MAX_SITES', 3):
            with self.assertRaisesRegex(ValueError, 'site budget'): self.inspect()


if __name__ == '__main__': unittest.main()
