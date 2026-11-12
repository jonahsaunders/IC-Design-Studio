import copy
import csv
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

import klayout.db as k
from icstudio import digital_sky130_waffle_windows as checks

ROOT = Path(__file__).resolve().parents[1]
WINDOW = [0, 0, 700000, 700000]


def new_layout():
    layout = k.Layout(); layout.dbu = .001
    return layout, layout.create_cell('control')


def controls():
    # Analytic stripes give exactly known areas, independently of the region
    # clipping code. Each threshold is exercised at, below and above the limit.
    for name, pairs in checks.LAYERS.items():
        for drop, minimum in ((30, 30), (40, 40), (50, 50), (60, 60), (80, 65), (100, 70)):
            for delta in (-1, 0, 1):
                layout, top = new_layout()
                top.shapes(layout.layer(*pairs['drop'])).insert(k.Box(0, 0, drop*7000, 700000))
                top.shapes(layout.layer(*pairs['drawing'])).insert(k.Box(0, 0, minimum*7000+delta, 700000))
                yield f'{name}-drop-{drop}-metal-{minimum}-delta-{delta}', layout, name, drop, minimum, delta


class WaffleWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'layout.gds'; self.layout, self.top = new_layout()

    def box(self, name, operand, bounds, cell=None):
        (cell or self.top).shapes(self.layout.layer(*checks.LAYERS[name][operand])).insert(k.Box(*bounds))

    def audit(self, windows=None):
        self.layout.write(str(self.path)); return checks.audit(self.path, windows)

    def test_every_threshold_with_one_nm_below_exact_and_above_on_four_metals(self):
        count = 0
        for label, layout, name, drop, minimum, delta in controls():
            with self.subTest(label=label):
                self.layout = layout; report = self.audit([WINDOW]); count += 1
                value = report['observations'][name][0]
                self.assertEqual(value['drop_area_nm2'], drop*7000*700000)
                self.assertEqual(value['metal_area_nm2'], (minimum*7000+delta)*700000)
                self.assertEqual(any(p['triggered'] for p in value['predicates']), delta < 0)
                self.assertEqual(report['unreviewed'], 12)
                self.assertFalse(report['acceptance_established'])
                checks.validate_saved(report, self.path)
        self.assertEqual(count, 72)

    def test_shared_endpoints_apply_both_bands_and_full_coverage_applies_seventy(self):
        area = checks.AREA_NM2
        for coverage, indexes in ((30, [5]), (40, [4, 5]), (50, [3, 4]),
                                  (60, [2, 3]), (80, [1, 2]), (100, [0, 1])):
            result = checks.predicates(area*coverage//100, 0)
            self.assertEqual([i for i, p in enumerate(result) if p['antecedent']], indexes)
        result = checks.predicates(area, area*65//100)
        self.assertTrue(result[0]['triggered']); self.assertFalse(result[1]['triggered'])

    def test_fraction_oracle_across_all_coverage_and_density_percentages(self):
        area = checks.AREA_NM2
        for drop in range(101):
            for metal in range(101):
                result = checks.predicates(area*drop//100, area*metal//100)
                for row, (low, high, minimum) in zip(result, checks.BANDS):
                    oracle = Fraction(low, 100) <= Fraction(drop, 100) <= Fraction(high, 100)
                    self.assertEqual(row['triggered'], oracle and Fraction(metal, 100) < Fraction(minimum, 100))

    def test_one_square_nm_boundary_not_rounded_into_wrong_band_or_density(self):
        area = checks.AREA_NM2
        for threshold in (30, 40, 50, 60, 80, 100):
            for delta in (-1, 0, 1):
                value = area*threshold//100 + delta
                if 0 <= value <= area:
                    result = checks.predicates(value, 0)
                    self.assertEqual([p['antecedent'] for p in result],
                        [Fraction(low, 100) <= Fraction(value, area) <= Fraction(high, 100)
                         for low, high, _ in checks.BANDS])
        for _, _, minimum in checks.BANDS:
            for delta in (-1, 0, 1):
                result = checks.predicates(area, area*minimum//100+delta)
                row = next(p for p in result if p['minimum_metal_percent'] == minimum)
                self.assertEqual(row['below_minimum'], delta < 0)

    def test_no_drop_proves_absence_without_inventing_window_or_cell_exemption(self):
        self.box('m1', 'drawing', WINDOW); report = self.audit()
        self.assertEqual(len(report['rows']), 48); self.assertEqual(report['unreviewed'], 0)
        self.assertEqual(report['window_policy'], 'not-supplied')
        self.assertTrue(all(r['disposition'] == 'absent-operand' for r in report['rows']))

    def test_present_drop_without_windows_and_tiny_cell_remain_unreviewed(self):
        self.box('m2', 'drop', [0, 0, 1, 1]); report = self.audit()
        self.assertEqual(report['unreviewed'], 12); self.assertEqual(report['status'], 'review-required')
        self.assertEqual(report['triggered_observations'], 0)
        self.assertFalse(report['acceptance_established'])

    def test_drop_text_is_presence_and_cannot_be_silently_measured_as_zero_area(self):
        self.top.shapes(self.layout.layer(*checks.LAYERS['m1']['drop'])).insert(k.Text('drop', k.Trans()))
        self.assertEqual(self.audit()['unreviewed'], 12)
        with self.assertRaisesRegex(ValueError, 'Text'): self.audit([WINDOW])

    def test_empty_samples_do_not_hide_drop_outside_the_selected_windows(self):
        self.box('m3', 'drop', [900000, 0, 910000, 10000]); report = self.audit([WINDOW])
        self.assertEqual(report['observations']['m3'][0]['drop_area_nm2'], 0)
        self.assertEqual(report['unreviewed'], 12); self.assertFalse(report['qualified'])

    def test_fill_and_drawn_union_do_not_double_count_and_clip_to_window(self):
        self.box('m1', 'drop', [-1000, -1000, 800000, 800000])
        self.box('m1', 'drawing', [-100000, 0, 300000, 700000])
        self.box('m1', 'drawing', [0, 0, 300000, 700000])
        self.box('m1', 'fill', [200000, 0, 490000, 800000])
        value = self.audit([WINDOW])['observations']['m1'][0]
        self.assertEqual(value['metal_area_nm2'], 490000*700000)
        self.assertEqual(value['drop_area_nm2'], checks.AREA_NM2)
        self.assertFalse(any(r['triggered'] for r in value['predicates']))

    def test_polygon_holes_reduce_drop_and_conductor_area(self):
        for operand in ('drop', 'drawing'):
            polygon = k.Polygon(k.Box(*WINDOW))
            polygon.insert_hole(list(k.Polygon(k.Box(100000, 100000, 200000, 200000)).each_point_hull()))
            self.top.shapes(self.layout.layer(*checks.LAYERS['m4'][operand])).insert(polygon)
        value = self.audit([WINDOW])['observations']['m4'][0]
        self.assertEqual(value['drop_area_nm2'], checks.AREA_NM2-100000**2)
        self.assertEqual(value['metal_area_nm2'], checks.AREA_NM2-100000**2)

    def test_separate_windows_are_not_averaged(self):
        self.box('m1', 'drop', [0, 0, 1400000, 700000]); self.box('m1', 'drawing', WINDOW)
        r = self.audit([WINDOW, [700000, 0, 1400000, 700000]])
        self.assertEqual([w['metal_area_nm2'] for w in r['observations']['m1']], [checks.AREA_NM2, 0])
        self.assertGreater(r['triggered_observations'], 0)

    def test_hierarchy_arrays_reflections_and_translated_negative_window(self):
        child = self.layout.create_cell('child')
        self.box('m1', 'drop', [0, 0, 350000, 350000], child)
        self.box('m1', 'drawing', [0, 0, 245000, 350000], child)
        self.top.insert(k.CellInstArray(child.cell_index(), k.Trans(k.Trans.M90, -700000, 0),
            k.Vector(350000, 0), k.Vector(0, 350000), 2, 2))
        r = self.audit([[-1050000, 0, -350000, 700000]])
        self.assertEqual(r['measurements']['layers']['m1']['raw_drop_shapes'], 4)
        self.assertEqual(r['observations']['m1'][0]['drop_area_nm2'], checks.AREA_NM2)
        self.assertEqual(r['observations']['m1'][0]['metal_area_nm2'], checks.AREA_NM2*70//100)

    def test_exact_orthogonal_paths_match_their_polygon(self):
        path = k.Path([k.Point(0, 350000), k.Point(700000, 350000)], 400000)
        shapes = self.top.shapes(self.layout.layer(*checks.LAYERS['m2']['drop']))
        shapes.insert(path); before = self.audit([WINDOW])['measurements']
        shapes.clear(); shapes.insert(path.polygon())
        self.assertEqual(before, self.audit([WINDOW])['measurements'])

    def test_unsupported_geometry_and_rounding_paths_are_not_silently_accepted(self):
        shapes = self.top.shapes(self.layout.layer(*checks.LAYERS['m1']['drop']))
        for shape in (k.Polygon([k.Point(0, 0), k.Point(100, 0), k.Point(0, 100)]),
                      k.Path([k.Point(0, 0), k.Point(100, 0)], 99)):
            shapes.clear(); shapes.insert(shape)
            self.assertEqual(self.audit()['unreviewed'], 12)
            with self.assertRaises(ValueError): self.audit([WINDOW])

    def test_unsupported_transform_units_and_multiple_tops_are_rejected(self):
        child = self.layout.create_cell('child'); self.box('m1', 'drop', WINDOW, child)
        self.top.insert(k.CellInstArray(child.cell_index(), k.ICplxTrans(1, 45, False, 0, 0)))
        with self.assertRaises(ValueError): self.audit([WINDOW])
        self.layout, self.top = new_layout(); self.layout.dbu = .002
        with self.assertRaises(ValueError): self.audit([WINDOW])
        self.layout.create_cell('other')
        with self.assertRaises(ValueError): self.audit()

    def test_invalid_windows_and_areas_rejected(self):
        for windows in ([WINDOW, WINDOW], [[0, 0, 699999, 700000]], [[False, 0, 700000, 700000]],
                        [[0, 0, 700000., 700000]], [list(reversed(WINDOW))], 'automatic'):
            with self.subTest(windows=windows), self.assertRaises(ValueError): checks.validate_windows(windows)
        for areas in ((True, 0), (-1, 0), (0, checks.AREA_NM2+1), (1.5, 0)):
            with self.assertRaises(ValueError): checks.predicates(*areas)
        with self.assertRaises(ValueError): checks.predicates(0, 0, 1)

    def test_drawing_labels_have_no_metal_area(self):
        self.top.shapes(self.layout.layer(*checks.LAYERS['m1']['drawing'])).insert(k.Text('metal', k.Trans()))
        self.assertEqual(self.audit([WINDOW])['observations']['m1'][0]['metal_area_nm2'], 0)

    def test_saved_evidence_recomputed_and_unqualified_even_after_rehash(self):
        self.box('m1', 'drop', WINDOW); before = self.audit([WINDOW])
        checks.validate_saved(before, self.path)
        self.box('m1', 'drawing', WINDOW); after = self.audit([WINDOW])
        before['gds_sha256'] = after['gds_sha256']
        with self.assertRaisesRegex(ValueError, 'actual layout'): checks.validate_saved(before, self.path)

    def test_report_mutation_missing_areas_boolean_counts_and_acceptance_rejected(self):
        report = self.audit([WINDOW])
        for mutate in (lambda r: r.pop('measurements'), lambda r: r['rows'].pop(),
                       lambda r: r.update(acceptance_established=True), lambda r: r.update(qualified=True),
                       lambda r: r['measurements']['layers']['m1'].update(raw_drop_shapes=False),
                       lambda r: r['measurements']['layers']['m1']['samples'][0].pop('metal_area_nm2')):
            bad = copy.deepcopy(report); mutate(bad)
            with self.assertRaises(ValueError): checks.evaluate(bad, report['gds_sha256'], report['top'])

    def test_reordered_measurement_keys_do_not_rebind_metal_catalog_ids(self):
        self.box('m1', 'drop', WINDOW); report = self.audit()
        measured = copy.deepcopy(report['measurements'])
        measured['layers'] = dict(reversed(list(measured['layers'].items())))
        self.assertEqual(checks.expected(measured, report['top'], report['gds_sha256']), report)

    def test_primary_sources_bind_all_48_predicates_and_published_drop_purposes(self):
        with zipfile.ZipFile(ROOT/'tests/fixtures/sky130-filled-references-v1.zip') as z:
            source = {p: z.read('sources/'+p) for p in checks.SOURCE['files']}
        for p, raw in source.items(): self.assertEqual(hashlib.sha256(raw).hexdigest(), checks.SOURCE['files'][p])
        errors = {r['ID']: r for r in csv.DictReader(io.StringIO(source['docs/rules/errors.csv'].decode()))}
        layers = list(csv.DictReader(io.StringIO(source['docs/rules/gds_layers.csv'].decode())))
        for index, (name, pairs) in enumerate(checks.LAYERS.items()):
            filename = next(p for p in source if p.endswith(f'-{name}_dotdash.csv'))
            parent = next(csv.DictReader(io.StringIO(source[filename].decode())))
            self.assertEqual((parent['Name'], parent['Flags']), (f'({name}.-)', 'RC'))
            self.assertIn('Exclude cells whose area is below 40Kum2.', parent['Description'])
            for offset, (low, high, minimum) in enumerate(checks.BANDS):
                coverage = '100%' if low == high else f'{low}-{high}%'
                text = f'<{minimum}% metal density when 700x700 window {coverage} covered by m{name}.waffledrop'
                for key in (f'r{1210+6*index+offset}', f's{44+6*index+offset}'):
                    self.assertEqual((errors[key]['Name'], errors[key]['Description']), (f'{name}.x.1', text))
            pair = '%s:%s' % pairs['drop']
            self.assertTrue(any(r['GDS layer:datatype'] == pair and r['Layer name'] == 'cm'+name and r['Purpose'] == 'waffle drop' for r in layers))
        native = (ROOT/checks.SOURCE['native_fill']['path']).read_bytes()
        self.assertEqual(hashlib.sha256(native).hexdigest(), checks.SOURCE['native_fill']['sha256'])


if __name__ == '__main__':
    unittest.main()
