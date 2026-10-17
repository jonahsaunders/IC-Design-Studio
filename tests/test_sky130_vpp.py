import copy
import csv
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

import klayout.db as k
from icstudio import digital_sky130_vpp as vpp

ROOT = Path(__file__).resolve().parents[1]


class VppTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'layout.gds'
        self.layout = k.Layout(); self.layout.dbu = .001; self.top = self.layout.create_cell('control')

    def shapes(self, name, cell=None):
        return (cell or self.top).shapes(self.layout.layer(*vpp.LAYERS[name]))

    def box(self, name, bounds, cell=None):
        self.shapes(name, cell).insert(k.Box(*bounds))

    def valid(self, size=2000):
        self.box('capacitor', (0, 0, size, size)); self.box('nwell', (-1500, -1500, size+1500, size+1500))

    def audit(self):
        self.layout.write(str(self.path)); return vpp.audit(self.path)

    def test_absent_subjects_are_four_absences_without_density_acceptance(self):
        self.box('met3', (0, 0, 100, 100)); report = self.audit()
        self.assertEqual(len(report['rows']), 4)
        self.assertTrue(all(r['disposition'] == 'absent-operand' for r in report['rows']))
        self.assertFalse(report['density']['acceptance_established'])
        self.assertEqual(vpp.validate_saved(report, self.path), report)

    def test_minimum_width_and_enclosure_boundaries(self):
        self.valid(1430); report = self.audit(); self.assertEqual(report['violations'], 0)
        self.assertTrue(all(r['disposition'] == 'executed-reviewed' for r in report['rows']))
        self.shapes('capacitor').clear(); self.box('capacitor', (0, 0, 1429, 1430))
        report = self.audit(); self.assertGreater(report['measurements']['violations']['r1145'], 0)
        with self.assertRaisesRegex(ValueError, 'geometry checks failed'):
            vpp.evaluate(report, report['gds_sha256'], report['top'])

    def test_nwell_enclosure_fails_at_one_nanometre_short_on_every_side(self):
        self.valid(); self.assertEqual(self.audit()['violations'], 0)
        for bounds in ((-1499, -1500, 3500, 3500), (-1500, -1499, 3500, 3500),
                       (-1500, -1500, 3499, 3500), (-1500, -1500, 3500, 3499)):
            self.shapes('nwell').clear(); self.box('nwell', bounds)
            with self.subTest(bounds=bounds):
                self.assertGreater(self.audit()['measurements']['violations']['r1153'], 0)

    def test_missing_nwell_does_not_claim_enclosure_acceptance_or_force_placement(self):
        self.box('capacitor', (0, 0, 2000, 2000)); r = self.audit()
        self.assertEqual(r['measurements']['violations']['r1153'], 0)
        self.assertEqual(r['rows'][-1]['disposition'], 'unreviewed')
        self.assertEqual(r['status'], 'review-required')
        self.assertEqual(r['measurements']['violations']['r1151'], 0)

    def test_mixed_nwell_context_preserves_unresolved_outside_capacitor(self):
        self.valid(); self.box('capacitor', (10000, 0, 12000, 2000))
        r = self.audit()
        self.assertEqual(r['measurements']['nwell_context'], dict(contained=1, outside=1, straddling=0))
        self.assertEqual(r['rows'][-1]['disposition'], 'unreviewed')

    def test_straddling_each_well_is_separate_from_inside_and_outside(self):
        self.valid()
        for name, key in (('nwell', 'r1151'), ('dnwell', 'r1152')):
            for bounds, count in (((-1500, -1500, 3500, 3500), 0), ((4000, 0, 5000, 1000), 0),
                                   ((1000, -1000, 5000, 5000), 1)):
                self.shapes(name).clear(); self.box(name, bounds)
                with self.subTest(name=name, bounds=bounds):
                    self.assertEqual(self.audit()['measurements']['violations'][key], count)

    def test_nwell_hole_is_an_actual_missing_enclosure(self):
        self.valid(); self.shapes('nwell').clear()
        polygon = k.Polygon(k.Box(-1500, -1500, 3500, 3500))
        polygon.insert_hole([k.Point(900, 900), k.Point(900, 1100), k.Point(1100, 1100), k.Point(1100, 900)])
        self.shapes('nwell').insert(polygon); r = self.audit()['measurements']['violations']
        self.assertGreater(r['r1153'], 0); self.assertEqual(r['r1151'], 1)

    def test_density_uses_unions_and_clipped_intersections_not_summed_boxes(self):
        self.valid(10000)
        self.box('met3', (-1000, 0, 2500, 10000)); self.box('met3', (0, 0, 2500, 10000))
        self.box('met4', (0, 0, 3000, 10000)); self.box('met5', (0, 0, 4000, 10000))
        self.box('poly', (0, 0, 10000, 10000)); self.box('diff', (0, 0, 8700, 10000))
        r = self.audit(); ratios = r['density']['observations'][0]['ratios']
        self.assertEqual(r['measurements']['density'][0]['covered_nm2'],
                         dict(met3=25000000, met4=30000000, met5=40000000, gate=87000000))
        self.assertTrue(all(v['within_ordinary_limit'] for v in ratios.values()))
        self.assertFalse(r['density']['acceptance_established']); self.assertFalse(r['qualified'])
        self.box('met3', (2500, 0, 2501, 10000))
        self.assertFalse(self.audit()['density']['observations'][0]['ratios']['met3']['within_ordinary_limit'])

    def test_gate_density_uses_poly_intersection_with_diffusion(self):
        self.valid(10000); self.box('poly', (0, 0, 10000, 10000)); self.box('diff', (0, 0, 8699, 10000))
        r = self.audit(); self.assertFalse(r['density']['observations'][0]['ratios']['gate']['within_ordinary_limit'])
        self.assertEqual(r['violations'], 0)  # Selector remains unreviewed; an observation is not a rule failure.

    def test_published_drawing_texts_do_not_add_density_area(self):
        self.valid()
        for name in ('poly', 'met3', 'met4', 'met5'):
            self.shapes(name).insert(k.Text('annotation', k.Trans()))
        r = self.audit()
        self.assertTrue(all(v == 0 for v in r['measurements']['density'][0]['covered_nm2'].values()))
        self.assertEqual(r['measurements']['raw_shapes']['met3'], 1)

    def test_multiple_regions_are_not_averaged_into_one_density(self):
        self.valid(10000); self.box('capacitor', (20000, 0, 30000, 10000))
        self.box('nwell', (18500, -1500, 31500, 11500)); self.box('met3', (0, 0, 10000, 10000))
        r = self.audit(); self.assertEqual(r['measurements']['components'], 2)
        self.assertEqual([x['ratios']['met3']['numerator_nm2'] for x in r['density']['observations']], [100000000, 0])

    def test_hierarchy_array_and_reflection_preserve_geometry_measurements(self):
        child = self.layout.create_cell('cap'); self.box('capacitor', (0, 0, 2000, 2000), child)
        self.box('nwell', (-1500, -1500, 3500, 3500), child)
        self.top.insert(k.CellInstArray(child.cell_index(), k.Trans(k.Trans.M90, 1000, 2000),
                                       k.Vector(10000, 0), k.Vector(0, 10000), 2, 3))
        r = self.audit(); self.assertEqual(r['measurements']['components'], 6); self.assertEqual(r['violations'], 0)

    def test_unsupported_shapes_and_transforms_do_not_disappear(self):
        for shape in (k.Text('unexpected', k.Trans()), k.Path([k.Point(0, 0), k.Point(2000, 0)], 1999),
                      k.Polygon([k.Point(0, 0), k.Point(2000, 0), k.Point(1000, 2000)])):
            self.shapes('capacitor').clear(); self.shapes('capacitor').insert(shape)
            with self.assertRaises(ValueError): self.audit()
        self.shapes('capacitor').clear(); child = self.layout.create_cell('child')
        self.box('capacitor', (0, 0, 2000, 2000), child)
        self.top.insert(k.CellInstArray(child.cell_index(), k.ICplxTrans(1, 45, False, 0, 0)))
        with self.assertRaisesRegex(ValueError, 'transform'): self.audit()

    def test_exact_orthogonal_path_matches_its_polygon(self):
        self.valid(); path = k.Path([k.Point(0, 1000), k.Point(2000, 1000)], 1000)
        self.shapes('met3').insert(path); first = self.audit()['measurements']
        self.shapes('met3').clear(); self.shapes('met3').insert(path.polygon())
        self.assertEqual(self.audit()['measurements'], first)

    def test_missing_or_altered_evidence_is_rejected(self):
        self.valid(); report = self.audit()
        for key in ('rows', 'source', 'density', 'measurements'):
            bad = copy.deepcopy(report); bad.pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError): vpp.evaluate(bad, report['gds_sha256'], 'control')
        for field in ('components',):
            bad = copy.deepcopy(report); bad['measurements'][field] = True
            with self.assertRaises(ValueError): vpp.evaluate(bad, report['gds_sha256'], 'control')

    def test_rehashed_failing_layout_cannot_reuse_passing_measurements(self):
        self.valid(); report = self.audit(); self.shapes('capacitor').clear()
        self.box('capacitor', (0, 0, 1000, 1000)); self.layout.write(str(self.path))
        report['gds_sha256'] = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'actual layout'): vpp.validate_saved(report, self.path)

    def test_source_bindings_are_exact_and_density_stays_conditional(self):
        inventory = json.loads((ROOT/'docs/qualification/sky130-rule-inventory.json').read_bytes())
        with zipfile.ZipFile(ROOT/'tests/fixtures/sky130-filled-references-v1.zip') as z:
            raw = {p: z.read('sources/'+p) for p in vpp.SOURCE['files']}
        for p, value in raw.items():
            self.assertEqual(hashlib.sha256(value).hexdigest(), vpp.SOURCE['files'][p])
            self.assertEqual(inventory['source_files'][p]['sha256'], vpp.SOURCE['files'][p])
        catalog = {r['ID']: r for r in csv.DictReader(io.StringIO(raw['docs/rules/errors.csv'].decode()))}
        for key, text in {'r1145': '1.43 min. width of capacitor',
                          'r1151': 'capacitor must not straddle nwell',
                          'r1152': 'capacitor must not straddle dnwell',
                          'r1153': '1.5 min. enclosure of capacitor by nwell'}.items():
            self.assertEqual(catalog[key]['Description'], text)
            self.assertEqual(catalog[key]['Name'], vpp.CHECKS[key])
        rows = {r['Name']: r for r in csv.DictReader(io.StringIO(raw['docs/rules/periphery/p037-vpp_dotdash.csv'].decode()))}
        for key, description, value, unit in (
            ('(vpp.1)', 'Min width of capacitor:dg', '1.430', 'µm'),
            ('(vpp.4)', 'capacitor:dg must not straddle (nwell or dnwell)', '', ''),
            ('(vpp.8)', 'Min enclosure of capacitor:dg by nwell', '1.500', 'µm')):
            self.assertEqual([rows[key][k] for k in ('Description', 'Value', 'Unit')], [description, value, unit])
        for key in ('(vpp.5a)', '(vpp.5b)', '(vpp.5c)', '(vpp.11)'):
            self.assertIn('vpp_', rows[key]['Description'])
        layers = list(csv.DictReader(io.StringIO(raw['docs/rules/gds_layers.csv'].decode())))
        for name, pair in vpp.LAYERS.items():
            matches = [r for r in layers if r['Layer name'] == name and 'drawing' in r['Purpose'].split(', ')]
            self.assertEqual([r['GDS layer:datatype'] for r in matches], ['%s:%s' % pair])


if __name__ == '__main__':
    unittest.main()
