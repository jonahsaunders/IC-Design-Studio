"""Independent written-GDS controls for the declared staggered fill recipe."""
import json
from pathlib import Path
import tempfile
import unittest

import klayout.db as k

from scripts import check_gf180_fill as fill


class FillPatternTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.layout = k.Layout(); self.layout.dbu = .001
        self.top = self.layout.create_cell('coupon')
        self.top.shapes(self.layout.layer(63, 0)).insert(k.Box(0, 0, 100000, 100000))
        self.plan = {'schema': 1, 'recipe': 'alternating-stagger-v1', 'layers': {}}

    def declare(self, name, origin=(20000, 20000), signs=(1, 1)):
        self.plan['layers'][name] = dict(origin_nm=list(origin), stagger_sign=list(signs))

    def box(self, layer, x, y, size=2000, cell=None):
        (cell or self.top).shapes(self.layout.layer(layer, 4)).insert(k.Box(x, y, x+size, y+size))

    def inspect(self, variant='C', use_plan=True):
        gds = self.root/'coupon.gds'; self.layout.write(str(gds))
        recipe = self.root/'recipe.json'; recipe.write_text(json.dumps(self.plan), encoding='utf-8')
        return fill.inspect(gds, (0, 0, 100, 100), top_name='coupon', variant=variant,
                            pattern_plan=recipe if use_plan else None)

    def test_four_phase_templates_and_cropped_holes_for_all_layer_families(self):
        # Explicit four-square templates, independent of the checker's residue
        # construction; repeat in separated tiles, omitting sites for blockages.
        templates = [('comp', 22, 5000, 16000, [(0,0),(8000,1600),(1600,8000),(9600,9600)]),
                     ('poly', 30, 5600, 16000, [(0,0),(8000,1600),(1600,8000),(9600,9600)])]
        templates += [(f'm{i}', layer, 2000, 6400, [(0,0),(3200,500),(500,3200),(3700,3700)])
                      for i, layer in enumerate((34,36,42,46,81), 1)]
        for name, layer, size, period, sites in templates:
            with self.subTest(layer=name):
                self.declare(name)
                for tx, ty in [(0,0), (2*period,0), (0,2*period)]:
                    for index, (x,y) in enumerate(sites):
                        if (tx or ty) and index == 2: continue
                        self.box(layer, 20000+tx+x, 20000+ty+y, size)
                for variant in ('C', 'D'):
                    report = self.inspect(variant)
                    item = report['drawing_patterns']['layers'][name]
                    self.assertEqual(item['status'], 'declared_recipe_passed')
                    self.assertEqual(item['polygons'], 10)
                    self.assertEqual(sum(p['polygons'] for p in item['phase_counts']), 10)
                    self.assertFalse(report['qualified'])
                    self.assertTrue(any('empty-field' in s for s in report['unqualified_requirements']))
                self.layout.clear_layer(self.layout.layer(layer,4))
                self.plan['layers'].clear()

    def test_missing_stagger_can_pass_drc_spacing_but_fails_drawing_recipe(self):
        self.declare('m1')
        for x,y in [(20000,20000),(23200,20000),(20000,23200),(23200,23200)]: self.box(34,x,y)
        report = self.inspect()
        self.assertEqual(report['drawing_patterns']['layers']['m1']['violations'], 3)
        self.assertEqual(next(c['status'] for c in report['checks']
                              if c['rule']=='DM.2b' and c['layer']=='m1'), 'passed')

    def test_pitch_and_five_nm_phase_faults_are_rejected_without_relaxing_drc(self):
        self.declare('m1'); index=self.layout.layer(34,4)
        for x,y in [(23205,20500),(23200,20505),(23300,20500),(23700,23800)]:
            with self.subTest(point=(x,y)):
                self.layout.clear_layer(index); self.box(34,20000,20000); self.box(34,x,y)
                report=self.inspect(); self.assertEqual(report['drawing_patterns']['layers']['m1']['violations'],1)
                for rule in ('DM.2b','5-nm-grid'):
                    self.assertEqual(next(c['status'] for c in report['checks']
                        if c['rule']==rule and c['layer']=='m1'),'passed')

    def test_legal_diagonal_gaps_are_not_replaced_by_drawing_space(self):
        # A legal stagger produces a 0.7/0.7 um diagonal gap (~0.99 um),
        # smaller than the 1.2 um drawing space but larger than DRC's 0.98.
        self.declare('m1');self.box(34,23200,20500);self.box(34,20500,23200)
        report=self.inspect()
        self.assertEqual(report['drawing_patterns']['layers']['m1']['violations'],0)
        self.assertEqual(next(c['status'] for c in report['checks']
            if c['rule']=='DM.2b' and c['layer']=='m1'),'passed')

    def test_shifted_negative_index_sites_preserve_declared_origin(self):
        self.declare('m1', origin=(26935,28710))
        # These four literal points include negative column/row indices and a
        # nonzero 5 nm-grid phase. Whole 6.4 um translations retain membership.
        for x,y in [(26935,28710),(23735,29210),(27435,25510),(24235,26010),(33335,28710)]:
            self.box(34,x,y)
        self.assertEqual(self.inspect()['drawing_patterns']['layers']['m1']['violations'],0)
        self.plan['layers']['m1']['origin_nm'][0] += 5
        self.assertEqual(self.inspect()['drawing_patterns']['layers']['m1']['violations'],5)

    def test_recursive_rotations_and_reflections(self):
        child=self.layout.create_cell('fill_tile')
        for x,y in [(20000,20000),(23200,20500),(20500,23200),(23700,23700)]:
            self.box(34,x,y,cell=child)
        transforms=[(k.Trans(0,False,0,0),(20000,20000),(1,1)),
                    (k.Trans(1,False,100000,0),(78000,20000),(-1,1)),
                    (k.Trans(2,False,100000,100000),(78000,78000),(-1,-1)),
                    (k.Trans(3,False,0,100000),(20000,78000),(1,-1)),
                    (k.Trans(0,True,0,100000),(20000,78000),(1,-1))]
        for transform,origin,signs in transforms:
            with self.subTest(transform=str(transform)):
                self.top.clear_insts()
                self.top.insert(k.CellInstArray(child.cell_index(),transform))
                self.declare('m1',origin,signs)
                item=self.inspect()['drawing_patterns']['layers']['m1']
                self.assertEqual((item['polygons'],item['violations']),(4,0))

    def test_each_disconnected_region_must_use_the_declared_phase(self):
        self.declare('m1');self.box(34,20000,20000);self.box(34,52000,52000)
        self.assertEqual(self.inspect()['drawing_patterns']['layers']['m1']['violations'],0)
        self.box(34,84005,84000)
        self.assertEqual(self.inspect()['drawing_patterns']['layers']['m1']['violations'],1)

    def test_wrong_size_and_nonrectangular_shapes_do_not_gain_membership(self):
        self.declare('m1');self.box(34,20000,20000,size=1995)
        triangle=k.Polygon([k.Point(26400,20000),k.Point(28400,20000),k.Point(26400,22000)])
        self.top.shapes(self.layout.layer(34,4)).insert(triangle)
        self.assertEqual(self.inspect()['drawing_patterns']['layers']['m1']['violations'],2)

    def test_missing_recipe_and_omitted_plan_remain_visible(self):
        self.declare('m1');self.box(34,20000,20000);self.box(81,40000,40000);self.box(36,40000,40000)
        report=self.inspect()
        self.assertEqual(report['drawing_patterns']['layers']['m5']['status'],'missing_recipe')
        self.assertTrue(any(c['rule']=='drawing-pattern-plan' and c['status']=='failed' for c in report['checks']))
        self.assertEqual(report['drawing_patterns']['adjacent_layers'][0]['status'],'unqualified_invalid_or_missing_recipe')
        self.assertFalse(any(c['rule']=='DM.9-replicated-pattern' for c in report['checks']))
        # A declared but geometrically false recipe is also insufficient to
        # report a successful comparison of the two actual arrays.
        self.declare('m2')
        report=self.inspect()
        self.assertEqual(report['drawing_patterns']['layers']['m2']['status'],'failed')
        self.assertEqual(report['drawing_patterns']['adjacent_layers'][0]['status'],'unqualified_invalid_or_missing_recipe')
        self.assertFalse(any(c['rule']=='DM.9-replicated-pattern' for c in report['checks']))
        report=self.inspect(use_plan=False)
        self.assertIsNone(report['drawing_patterns']);self.assertIsNone(report['pattern_plan_sha256'])
        self.assertTrue(any('Required drawing patterns' in s for s in report['unqualified_requirements']))

    def test_replicated_adjacent_arrays_fail_even_with_different_cropped_sites(self):
        self.declare('m1');self.declare('m2',origin=(26400,20000))
        self.box(34,20000,20000);self.box(36,29600,20500)
        report=self.inspect()
        self.assertEqual(report['drawing_patterns']['adjacent_layers'][0]['status'],'replicated_pattern')
        self.assertTrue(any(c['rule']=='DM.9-replicated-pattern' and c['status']=='failed' for c in report['checks']))

    def test_nonreplicated_adjacent_arrays_do_not_claim_offset_acceptance(self):
        self.declare('m1');self.declare('m2',origin=(20500,20500))
        self.box(34,20000,20000);self.box(36,26900,26900)
        report=self.inspect()
        self.assertEqual(report['drawing_patterns']['adjacent_layers'][0]['status'],'offset_acceptance_unqualified')
        self.assertTrue(any('DM.9 qualified' in s for s in report['unqualified_requirements']))
        self.assertFalse(report['qualified'])

    def test_malformed_recipe_metadata_is_rejected(self):
        self.declare('m1'); original=json.loads(json.dumps(self.plan))
        cases=[lambda p:p.update(schema=True),lambda p:p.update(recipe='arbitrary'),
               lambda p:p['layers'].update(m6=p['layers'].pop('m1')),
               lambda p:p['layers']['m1'].update(origin_nm=[20001,20000]),
               lambda p:p['layers']['m1'].update(origin_nm=[True,20000]),
               lambda p:p['layers']['m1'].update(stagger_sign=[0,1]),
               lambda p:p['layers']['m1'].update(stagger_sign=[True,1]),
               lambda p:p['layers']['m1'].update(pitch_nm=3205)]
        for change in cases:
            self.plan=json.loads(json.dumps(original));change(self.plan)
            with self.assertRaises(ValueError):self.inspect()


if __name__ == '__main__': unittest.main()
