"""Written-GDS boundary controls with literal, independently placed faults."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import klayout.db as k
from scripts import check_gf180_fill as fill
from scripts import gf180_fill_boundaries as boundary


class FillBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.layout = k.Layout(); self.layout.dbu = .001
        self.top = self.layout.create_cell('coupon')
        self.top.shapes(self.layout.layer(63, 0)).insert(k.Box(0, 0, 400000, 400000))
        self.source = self.root/'floorplan-source.json'
        self.source.write_text('{"purpose":"synthetic boundary control"}\n', encoding='utf-8')
        self.plan = dict(schema=1, gds_sha256='', top='coupon',
            floorplan_source=dict(file=self.source.name, sha256=boundary.digest(self.source)),
            regions=[dict(name='die', kind='prime_die', bounds_nm=[50000,50000,350000,350000])],
            scribe_boxes_nm=[[0,0,400000,50000],[0,350000,400000,400000],
                             [0,50000,50000,350000],[350000,50000,400000,350000]], frame_cells=[])

    def square(self, name, x, y, size=None, cell=None):
        layer = fill.LAYERS[name]; size = size or (5000 if name == 'comp' else 5600)
        (cell or self.top).shapes(self.layout.layer(layer, 4)).insert(k.Box(x,y,x+size,y+size))

    def clear(self):
        for layer in (22,30): self.layout.clear_layer(self.layout.layer(layer,4))

    def save(self):
        gds = self.root/'coupon.gds'; options = k.SaveLayoutOptions(); options.gds2_write_timestamps = False
        self.layout.write(str(gds), options)
        self.plan['gds_sha256'] = boundary.digest(gds)
        path = self.root/'boundary.json'; path.write_text(json.dumps(self.plan), encoding='utf-8')
        return gds, path

    def inspect(self, variant='C', use_plan=True):
        gds, plan = self.save()
        return fill.inspect(gds, [0,0,400,400], top_name='coupon', variant=variant,
                            boundary_plan=plan if use_plan else None)

    def failures(self, result, rule=None):
        return [c for c in result['boundary_checks'].get('checks', [])
                if c['status']=='failed' and (rule is None or c['rule']==rule)]

    def test_prime_die_exact_limits_and_five_nm_faults_on_all_sides(self):
        # Scribe inner edges are exactly 50 and 350 um; these literal squares
        # have the prescribed gap on each of the four sides.
        for variant in ('C','D'):
            for name,rule,sites in (
                    ('comp','DCF.7a',[(76000,100000),(319000,100000),(100000,76000),(100000,319000)]),
                    ('poly','DPF.7',[(75700,100000),(318700,100000),(100000,75700),(100000,318700)])):
                for index,(x,y) in enumerate(sites):
                    with self.subTest(variant=variant,layer=name,side=index):
                        self.clear(); self.square(name,x,y)
                        result=self.inspect(variant); self.assertFalse(self.failures(result))
                        self.assertFalse(result['boundary_checks']['qualified'])
                        self.assertTrue(any('complete-chip' in s for s in result['unqualified_requirements']))
                        dx,dy=[(-5,0),(5,0),(0,-5),(0,5)][index]
                        self.clear(); self.square(name,x+dx,y+dy)
                        self.assertEqual([c['rule'] for c in self.failures(self.inspect(variant))],[rule])

    def test_scribe_union_holes_and_diagonal_euclidean_clearance(self):
        # Only this coupon's southwest scribe rectangle is declared. Distance
        # from its top-right corner to the square is hypot(15.6,20.8)=26 um.
        self.plan['scribe_boxes_nm']=[[0,0,50000,50000]]
        self.square('comp',65600,70800)
        self.assertFalse(self.failures(self.inspect()))
        self.clear(); self.square('comp',65595,70800)
        self.assertTrue(self.failures(self.inspect(),'DCF.7a'))
        # The four original scribe rails merge into a polygon with a hole;
        # the die in that hole was exercised by the four-sided controls.

    def test_frame_and_both_slm_boundary_types_at_exact_limit(self):
        for kind,rule in [('frame','DCF.7b'),('slm_etest','DCF.7d'),('slm_reliability','DCF.7d')]:
            self.plan['regions']=[dict(name='test',kind=kind,bounds_nm=[100000,0,300000,50000])]
            for x,y,dx,dy in [(106000,20000,-5,0),(289000,20000,5,0),
                              (150000,6000,0,-5),(150000,39000,0,5)]:
                with self.subTest(kind=kind,x=x,y=y):
                    self.clear(); self.square('comp',x,y)
                    self.assertFalse(self.failures(self.inspect()))
                    self.clear(); self.square('comp',x+dx,y+dy)
                    self.assertEqual([c['rule'] for c in self.failures(self.inspect())],[rule])

    def test_frame_cell_clearance_and_explicit_non_et_exception(self):
        self.plan['regions']=[dict(name='frame',kind='frame',bounds_nm=[100000,0,300000,50000])]
        self.square('comp',106000,20000)
        for left,non_et,failed in [(121000,False,False),(120995,False,True),
                                   (106000,False,True),(106000,True,False)]:
            with self.subTest(left=left,non_et=non_et):
                self.plan['frame_cells']=[dict(bounds_nm=[left,20000,left+5000,25000],non_et=non_et)]
                self.assertEqual(bool(self.failures(self.inspect(),'DCF.7c')),failed)

    def test_unclassified_crossing_and_adjacent_regions_cannot_clip_a_square(self):
        for x,y in [(10000,100000),(48000,100000),(348000,100000)]:
            self.clear(); self.square('comp',x,y)
            self.assertEqual(self.failures(self.inspect(),'boundary-region-coverage')[0]['violations'],1)
        self.plan['regions']=[dict(name='a',kind='prime_die',bounds_nm=[50000,50000,200000,350000]),
                              dict(name='b',kind='prime_die',bounds_nm=[200000,50000,350000,350000])]
        self.clear(); self.square('comp',198000,100000)
        self.assertTrue(self.failures(self.inspect(),'boundary-region-coverage'))

    def test_dummy_poly_outside_prime_die_is_rejected(self):
        self.plan['regions']=[dict(name='frame',kind='frame',bounds_nm=[100000,0,300000,50000])]
        self.square('poly',150000,20000)
        self.assertTrue(self.failures(self.inspect(),'DPF.1-prime-die-scope'))

    def test_recursive_rotated_geometry_uses_written_coordinates(self):
        child=self.layout.create_cell('child'); self.square('comp',76000,100000,cell=child)
        for rotation in range(4):
            self.top.clear_insts()
            trans=[k.Trans(0,False,0,0),k.Trans(1,False,400000,0),
                   k.Trans(2,False,400000,400000),k.Trans(3,False,0,400000)][rotation]
            self.top.insert(k.CellInstArray(child.cell_index(),trans))
            result=self.inspect(); self.assertFalse(self.failures(result))
            self.assertEqual(result['boundary_checks']['regions'][0]['comp'],1)

    def test_missing_declaration_cannot_be_inferred_from_die_or_core(self):
        self.square('comp',76000,100000)
        result=self.inspect(use_plan=False)
        self.assertEqual(result['boundary_checks']['status'],'missing_boundary_plan')
        self.assertFalse(result['qualified'])
        self.assertTrue(any('scribe/frame' in s for s in result['unqualified_requirements']))

    def test_wrong_source_gds_or_top_identity_is_rejected(self):
        original=copy.deepcopy(self.plan)
        for key,value in [('gds_sha256','0'*64),('top','other')]:
            self.plan=copy.deepcopy(original); gds,path=self.save(); self.plan[key]=value
            path.write_text(json.dumps(self.plan),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'exact GDS and top'):
                fill.inspect(gds,[0,0,400,400],top_name='coupon',variant='C',boundary_plan=path)
        self.plan=original; self.source.write_text('changed',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'source does not match'): self.inspect()

    def test_malformed_or_inconsistent_floorplans_are_rejected(self):
        original=copy.deepcopy(self.plan)
        cases=[lambda p:p.update(schema=True),lambda p:p.update(scribe_boxes_nm=[]),
            lambda p:p['regions'][0].update(kind=[]),lambda p:p['regions'][0].update(bounds_nm=[0,0,0,5]),
            lambda p:p['regions'][0].update(bounds_nm=[False,50000,350000,350000]),
            lambda p:p['regions'][0].update(bounds_nm=[50000,50000,450000,350000]),
            lambda p:p['regions'].append(dict(name='b',kind='prime_die',bounds_nm=[60000,60000,70000,70000])),
            lambda p:p['regions'][0].update(bounds_nm=[40000,50000,350000,350000]),
            lambda p:p['regions'][0].update(kind='frame'),
            lambda p:p['frame_cells'].append(dict(bounds_nm=[60000,60000,70000,70000],non_et=False)),
            lambda p:p['frame_cells'].append(dict(bounds_nm=[0,0,5,5],non_et=1))]
        for change in cases:
            self.plan=copy.deepcopy(original); change(self.plan)
            with self.assertRaises(ValueError): self.inspect()

    def test_source_mutation_during_inspection_is_rejected(self):
        actual=boundary.inspect_boundaries
        def changing(*args):
            result=actual(*args); self.source.write_text('changed',encoding='utf-8'); return result
        with mock.patch.object(boundary,'inspect_boundaries',side_effect=changing):
            with self.assertRaisesRegex(ValueError,'changed during inspection'): self.inspect()


if __name__ == '__main__': unittest.main()
