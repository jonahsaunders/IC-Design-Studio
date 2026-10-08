"""Written-geometry and independent distance controls for COMP site bounds."""
from pathlib import Path
import tempfile
import unittest

import klayout.db as k
from scripts import check_gf180_fill as fill
from scripts import gf180_comp_sites as sites


class CompSiteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def write_read(self,comp,poly=None):
        layout=k.Layout();layout.dbu=.001;top=layout.create_cell('coupon')
        top.shapes(layout.layer(22,0)).insert(comp)
        if poly is not None:top.shapes(layout.layer(30,0)).insert(poly)
        top.shapes(layout.layer(63,0)).insert(k.Box(0,0,100000,100000))
        path=self.root/'coupon.gds';layout.write(str(path))
        read=k.Layout();read.read(str(path))
        # Single-shape Regions may keep a reference to their source layout.
        # Retain the written-GDS owner while the returned geometry is tested.
        self.loaded_layout=read
        return fill.region(read,read.top_cell(),22,0),fill.region(read,read.top_cell(),30,0)

    def inspect(self,comp,poly=None,bounds=(0,0,100000,100000)):
        a,b=self.write_read(comp,poly)
        return sites.inspect_space(a,b,k.Box(*bounds))

    def test_forbidden_bound_agrees_with_independent_rectangle_distance(self):
        rect=(-10000,-5000,5000,10000)
        material,_=self.write_read(k.Region(k.Box(*rect)))
        for distance in (1500,3500):
            blocked,_=sites.forbidden_origins(material,distance)
            polygons=list(blocked.each());blocked_count=legal_count=0
            for x in range(-20000,15001,500):
                for y in range(-15000,20001,500):
                    dx=max(rect[0]-(x+5000),x-rect[2],0)
                    dy=max(rect[1]-(y+5000),y-rect[3],0)
                    legal=dx*dx+dy*dy>=distance*distance
                    forbidden=any(p.inside(k.Point(x,y)) for p in polygons)
                    blocked_count+=forbidden;legal_count+=legal
                    if legal:self.assertFalse(forbidden,(distance,x,y,dx,dy))
                    if forbidden:self.assertFalse(legal,(distance,x,y,dx,dy))
            self.assertGreater(blocked_count,100);self.assertGreater(legal_count,100)
        # The 2.5/2.5 um corner clearance is legal for 3.5 um Euclidean
        # spacing. A square keepout would incorrectly eliminate this site.
        blocked,_=sites.forbidden_origins(material,3500)
        self.assertFalse(any(p.inside(k.Point(7500,12500)) for p in blocked.each()))

    def test_both_materials_are_needed_for_the_absence_proof(self):
        comp=k.Region(k.Box(0,0,5000,10000));poly=k.Region(k.Box(10000,0,15000,10000))
        bounds=(0,0,15000,10000)
        both=self.inspect(comp,poly,bounds)
        self.assertTrue(both['no_legal_square_proven']);self.assertFalse(both['qualified'])
        for a,b in ((comp,k.Region()),(k.Region(),poly)):
            self.assertFalse(self.inspect(a,b,bounds)['no_legal_square_proven'])

    def test_exact_clearance_corridor_keeps_line_solutions_visible(self):
        comp=k.Region(k.Box(0,0,4000,10000))+k.Region(k.Box(16000,0,20000,10000))
        report=self.inspect(comp,bounds=(0,0,20000,10000))
        self.assertFalse(report['no_legal_square_proven'])
        self.assertEqual(report['status'],'possible_origins_unqualified')
        self.assertGreater(report['possible_origin_area_um2'],0)
        # A square at (7500,0) has exactly 3.5 um clearance on both sides.
        square=k.Region(k.Box(7500,0,12500,5000))
        self.assertTrue(square.separation_check(comp,3500).is_empty())

    def test_degenerate_scopes_cannot_drop_point_or_line_solutions(self):
        for bounds in ((0,0,5000,5000),(0,0,5000,10000)):
            report=self.inspect(k.Region(),bounds=bounds)
            self.assertEqual(report['status'],'unqualified_degenerate_origin_domain')
            self.assertFalse(report['no_legal_square_proven'])
        report=self.inspect(k.Region(),bounds=(0,0,4995,10000))
        self.assertEqual(report['status'],'no_legal_square_footprint')
        self.assertTrue(report['no_legal_square_proven'])

    def test_holes_and_translated_rotations_preserve_possible_sites(self):
        material=k.Region(k.Box(0,0,40000,40000))-k.Region(k.Box(10000,10000,30000,30000))
        for transform,bounds in ((k.Trans(),(0,0,40000,40000)),
                (k.Trans(1,False,65000,15000),(25000,15000,65000,55000))):
            report=self.inspect(material.transformed(transform),bounds=bounds)
            self.assertFalse(report['no_legal_square_proven'])
            self.assertEqual(report['status'],'possible_origins_unqualified')
        narrow=k.Region(k.Box(0,0,40000,40000))-k.Region(k.Box(15000,15000,25000,25000))
        self.assertTrue(self.inspect(narrow,bounds=(0,0,40000,40000))['no_legal_square_proven'])

    def test_diagonal_material_cannot_produce_an_unsupported_absence_claim(self):
        triangle=k.Region(k.Polygon([k.Point(0,0),k.Point(100000,0),k.Point(0,100000)]))
        for comp,poly in ((triangle,k.Region()),(k.Region(),triangle)):
            report=self.inspect(comp,poly)
            self.assertEqual(report['status'],'unqualified_geometry')
            self.assertFalse(report['no_legal_square_proven']);self.assertFalse(report['qualified'])

    def test_declared_core_does_not_replace_die_scope_or_density(self):
        self.write_read(k.Region(k.Box(20000,20000,80000,80000)))
        path=self.root/'coupon.gds'
        plain=fill.inspect(path,(0,0,100,100),top_name='coupon',variant='C')
        for variant in ('C','D'):
            report=fill.inspect(path,(0,0,100,100),top_name='coupon',variant=variant,core_bounds_um=(20,20,80,80))
            self.assertEqual(report['density'],plain['density'])
            self.assertEqual(report['checks'],plain['checks'])
            self.assertEqual(report['area_um2'],10000)
            self.assertTrue(report['comp_placement_space']['declared_core']['no_legal_square_proven'])
            self.assertFalse(report['comp_placement_space']['die']['no_legal_square_proven'])
            self.assertFalse(report['qualified'])
            self.assertTrue(any('DCF.1a' in s for s in report['unqualified_requirements']))

    def test_invalid_core_scope_is_rejected(self):
        self.write_read(k.Region())
        for core in ((0,0,101,100),(20,20,10,80),(0,0,50.0001,100),
                (0,0,float('nan'),100),(0,0,100)):
            with self.subTest(core=core),self.assertRaises(ValueError):
                fill.inspect(self.root/'coupon.gds',(0,0,100,100),top_name='coupon',variant='C',core_bounds_um=core)


if __name__=='__main__':unittest.main()
