import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import klayout.db as k
from icstudio import digital_sky130_oxide_density as checks
from icstudio import digital_sky130_rules as integration
from icstudio.model import file_digest

ROOT = Path(__file__).resolve().parents[1]
BOUNDS = [0, 0, 700000, 700000]


def layout():
    obj = k.Layout(); obj.dbu = .001
    return obj, obj.create_cell('density_control')


def controls():
    # Rectangular stripe areas are analytic after positive square growth.
    # Each metal/profile has a one-nm failing, exact and passing example.
    for profile, growth in checks.PROFILES.items():
        for metal, amount in growth.items():
            for delta in (-1, 0, 1):
                obj, top = layout()
                top.shapes(obj.layer(*checks.LAYERS[metal][0])).insert(
                    k.Box(-2000, -2000, 560000-amount+delta, 702000))
                yield f'{profile}-{metal}-{delta}', obj, profile, metal, delta


class OxideDensityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'input.gds'
        self.layout, self.top = layout()

    def add(self, box, metal='m1', fill=False, cell=None):
        (cell or self.top).shapes(self.layout.layer(*checks.LAYERS[metal][int(fill)])).insert(box)

    def audit(self, bounds=BOUNDS):
        opt = k.SaveLayoutOptions(); opt.gds2_write_timestamps = False
        self.layout.write(str(self.path), opt)
        return checks.audit(self.path, bounds)

    def sample(self, report, metal='m1', profile='tinytapeout-margin', index=0):
        return report['observations'][metal][profile][index]

    def test_source_blobs_license_and_parameters_are_pinned(self):
        root = ROOT/'tests/fixtures/sky130-tt-density-v1'
        lock = json.loads((root/'source-lock.json').read_bytes())
        self.assertEqual(lock['license'], 'Apache-2.0')
        self.assertEqual(lock['revision'], checks.SOURCE['revision'])
        for item in lock['files']:
            raw = (root/item['path']).read_bytes()
            self.assertEqual(len(raw), item['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item['sha256'])
            self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(), item['blob'])
        raw = (root/'met_density_tiled.drc').read_text()
        self.assertEqual(file_digest(root/'met_density_tiled.drc'), checks.SOURCE['sha256'])
        for metal, growth in checks.PROFILES['tinytapeout-margin'].items():
            self.assertIn(f'{metal}.sized({growth}) | {metal}fill.sized({growth})', raw)
            for fill, pair in zip(('', 'fill'), checks.LAYERS[metal]):
                self.assertIn(f'input("{metal}{fill}", layout.top_cell().begin_shapes_rec(layout.layer({pair[0]},{pair[1]})', raw)
        self.assertIn('if met_tiled_density < 0.80', raw)
        self.assertIn('window_size = 700', raw); self.assertIn('step_size = 70', raw)

    def test_twenty_four_analytic_threshold_controls(self):
        count = 0
        for label, obj, profile, metal, delta in controls():
            with self.subTest(label=label):
                self.layout = obj; report = self.audit(); count += 1
                row = self.sample(report, metal, profile)
                self.assertEqual(row['grown_metal_area_nm2'], (560000+delta)*700000)
                self.assertEqual(row['below_minimum'], delta < 0)
                self.assertEqual(report['full_windows'], 1)
                self.assertFalse(report['qualified']); self.assertFalse(report['acceptance_established'])
                checks.validate_saved(report, self.path, BOUNDS)
        self.assertEqual(count, 24)

    def test_exact_endpoint_windows_translation_and_negative_origin(self):
        for size, count in ((699999, 0), (700000, 1), (769999, 1), (770000, 4), (840000, 9)):
            bounds = [-123456, 10987, -123456+size, 10987+size]
            rows = checks.windows(bounds)
            self.assertEqual(sum(r['kind'] == 'full' for r in rows), count)
            self.assertEqual(rows[0]['bounds_nm'][:2], bounds[:2])
        last = [r for r in checks.windows([100, 200, 770100, 770200]) if r['kind'] == 'full'][-1]
        self.assertEqual(last['bounds_nm'], [70100, 70200, 770100, 770200])

    def test_one_square_nm_below_threshold_is_not_rounded(self):
        report = self.audit(); measurements = copy.deepcopy(report['measurements'])
        for delta in (-1, 0, 1):
            measurements['layers']['m1']['raw_shapes'] = [1, 0]
            for areas in measurements['layers']['m1']['areas_nm2'].values():
                areas[0] = 700000**2*80//100+delta
            result = checks.expected(measurements, report['top'], report['gds_sha256'])
            self.assertEqual(self.sample(result)['below_minimum'], delta < 0)

    def test_small_or_missing_context_never_passes(self):
        self.add(k.Box(-2000, -2000, 1000000, 1000000))
        for bounds in (None, [0, 0, 100000, 150000]):
            report = self.audit(bounds)
            self.assertEqual(report['full_windows'], 0)
            self.assertTrue(all(s['status'] == 'no-full-windows' for s in report['summaries'].values()))
            self.assertEqual(report['status'], 'review-required')
            self.assertFalse(report['acceptance_established'])

    def test_overlapping_drawn_fill_and_duplicate_shapes_are_unioned(self):
        for fill in (False, True, False): self.add(k.Box(1000, 1000, 2000, 2000), fill=fill)
        report = self.audit()
        self.assertEqual(self.sample(report)['grown_metal_area_nm2'], 1850**2)
        self.assertEqual(self.sample(report, profile=list(checks.PROFILES)[1])['grown_metal_area_nm2'], 2200**2)

    def test_holes_shrink_and_are_not_filled_or_double_counted(self):
        p = k.Polygon(k.Box(-2000, -2000, 702000, 702000))
        p.insert_hole(list(k.Polygon(k.Box(100000, 100000, 200000, 200000)).each_point_hull()))
        self.add(p); report = self.audit()
        self.assertEqual(self.sample(report)['grown_metal_area_nm2'], 700000**2-(100000-2*425)**2)

    def test_external_geometry_grows_into_window_before_clipping(self):
        self.add(k.Box(-1000, -1000, -100, 701000))
        self.assertEqual(self.sample(self.audit())['grown_metal_area_nm2'], 325*700000)

    def test_independent_windows_do_not_average_away_a_local_failure(self):
        self.add(k.Box(-2000, -2000, 700000, 702000))
        report = self.audit([0, 0, 1400000, 700000])
        full = [r for r in report['observations']['m1']['tinytapeout-margin'] if r['kind'] == 'full']
        self.assertFalse(full[0]['below_minimum']); self.assertTrue(full[-1]['below_minimum'])
        self.assertGreater(report['summaries']['tinytapeout-margin']['full_window_findings'], 0)

    def test_nested_arrays_reflections_and_flattening_preserve_area(self):
        child = self.layout.create_cell('renamed_child')
        self.add(k.Box(2000, 2000, 4000, 4000), cell=child)
        self.top.insert(k.CellInstArray(child.cell_index(), k.Trans(k.Trans.M90, 10000, 20000),
            k.Vector(10000, 0), k.Vector(0, 10000), 2, 3))
        before = self.audit()['observations']; self.top.flatten(True)
        self.assertEqual(before, self.audit()['observations'])
        self.assertEqual(before['m1']['tinytapeout-margin'][0]['grown_metal_area_nm2'], 6*2850**2)

    def test_orthogonal_even_width_paths_match_polygons(self):
        path = k.Path([k.Point(2000, 2000), k.Point(5000, 2000), k.Point(5000, 6000)], 1000)
        self.add(path); first = self.audit()['observations']
        self.top.shapes(self.layout.layer(*checks.LAYERS['m1'][0])).clear(); self.add(path.polygon())
        self.assertEqual(first, self.audit()['observations'])

    def test_text_degenerate_diagonal_and_inexact_paths_are_rejected(self):
        for shape in (k.Text('not area', k.Trans()), k.Box(0, 0, 0, 1000),
                      k.Polygon([k.Point(0,0), k.Point(1000,0), k.Point(0,1000)]),
                      k.Path([k.Point(0,0), k.Point(1000,0)], 3)):
            with self.subTest(shape=str(shape)):
                self.top.shapes(self.layout.layer(*checks.LAYERS['m1'][0])).clear(); self.add(shape)
                with self.assertRaises(ValueError): self.audit()

    def test_magnification_rotation_and_other_dbu_are_not_silently_rounded(self):
        child = self.layout.create_cell('child'); self.add(k.Box(0,0,1000,1000), cell=child)
        for transform in (k.ICplxTrans(2,0,False,0,0), k.ICplxTrans(1,45,False,0,0)):
            self.top.clear_insts(); self.top.insert(k.CellInstArray(child.cell_index(),transform))
            with self.assertRaisesRegex(ValueError, 'transform'): self.audit()
        self.top.clear_insts(); self.top.insert(k.CellInstArray(child.cell_index(), k.Trans()))
        self.layout.dbu = .005
        with self.assertRaisesRegex(ValueError, 'database'): self.audit()

    def test_invalid_bounds_and_huge_allocations_are_rejected(self):
        for b in ([0,0,0,1], [0,0,1.,1], [False,0,1,1], [0,0,1], [0,0,10**10,10**10]):
            with self.subTest(bounds=b), self.assertRaises(ValueError): checks.windows(b)

    def test_forged_report_rehashed_areas_bounds_and_changed_layout_are_rejected(self):
        self.add(k.Box(0,0,1000,1000)); report = self.audit()
        bad = copy.deepcopy(report); bad['acceptance_established'] = True
        with self.assertRaises(ValueError): checks.evaluate(bad, report['gds_sha256'], report['top'])
        measurements = copy.deepcopy(report['measurements'])
        measurements['layers']['m1']['areas_nm2']['tinytapeout-margin'][0] += 1
        forged = checks.expected(measurements, report['top'], report['gds_sha256'])
        with self.assertRaises(ValueError): checks.validate_saved(forged, self.path, BOUNDS)
        with self.assertRaises(ValueError): checks.validate_saved(report, self.path, [0,0,700001,700000])
        self.add(k.Box(10000,10000,20000,20000)); self.audit()
        with self.assertRaises(ValueError): checks.validate_saved(report, self.path, BOUNDS)

    def test_inventory_bounds_require_digest_top_and_checkpoint_binding(self):
        root = Path(self.temp.name); inv = root/'inventory.json'
        record = dict(schema=1, top='top', checkpoint_sha256='a'*64, die_nm=BOUNDS)
        inv.write_text(json.dumps(record)); files = dict(sky130_pin_inventory=dict(path=inv.name, sha256=file_digest(inv)))
        self.assertEqual(integration.density_bounds(files, root, 'top', 'a'*64), BOUNDS)
        for top, digest in (('other', 'a'*64), ('top', 'b'*64)):
            with self.assertRaises(ValueError): integration.density_bounds(files, root, top, digest)
        inv.write_text('{}')
        with self.assertRaises(ValueError): integration.density_bounds(files, root, 'top', 'a'*64)

    def test_cli_is_unqualified_and_never_overwrites_input(self):
        self.audit(); output = self.path.with_suffix('.json')
        command = [sys.executable, '-m', 'scripts.check_sky130_oxide_density', str(self.path),
                   '--bounds-nm', *map(str, BOUNDS), '--output']
        result = subprocess.run(command+[str(output)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr); self.assertTrue(output.exists())
        digest = file_digest(self.path)
        result = subprocess.run(command+[str(self.path)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2); self.assertIn('overwrite', result.stderr)
        self.assertEqual(file_digest(self.path), digest)


if __name__ == '__main__': unittest.main()
