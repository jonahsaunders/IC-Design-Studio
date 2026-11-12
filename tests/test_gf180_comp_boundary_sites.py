"""Reference-boundary absence proof and deliberately incomplete declarations."""
import json
from pathlib import Path
import tempfile
import unittest
import klayout.db as k
from scripts import gf180_comp_boundary_sites as sites
from scripts import gf180_fill_boundaries as boundary


class BoundarySiteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.bounds=k.Box(0,0,100000,100000)
        source=self.root/'floorplan.json';source.write_text('{"reference_die_nm":[0,0,100000,100000]}',encoding='utf-8')
        self.plan=dict(schema=1,gds_sha256='0'*64,top='reference',
            floorplan_source=dict(file=source.name,sha256=boundary.digest(source)),
            regions=[dict(name='prime',kind='prime_die',bounds_nm=[0,0,100000,100000])],
            scribe_boxes_nm=[[-10000,-10000,110000,0],[-10000,100000,110000,110000],
                             [-10000,0,0,100000],[100000,0,110000,100000]],frame_cells=[])

    def inspect(self,comp):
        path=self.root/'boundary.json';path.write_text(json.dumps(self.plan),encoding='utf-8')
        loaded=boundary.load_plan(path,'0'*64,'reference',self.bounds)
        return sites.inspect(comp,k.Region(),self.bounds,loaded)

    def test_full_domain_is_checked_and_empty_interior_does_not_pass(self):
        material=k.Region(k.Box(26000,26000,74000,74000))
        result=self.inspect(material)
        self.assertTrue(result['no_legal_square_proven']);self.assertFalse(result['qualified'])
        self.assertEqual(result['original_bounds_nm'],[0,0,100000,100000])
        self.assertEqual(result['admissible_whole_square_bounds_nm'],[26000,26000,74000,74000])
        material-=k.Region(k.Box(35000,35000,65000,65000))
        self.assertFalse(self.inspect(material)['no_legal_square_proven'])

    def test_missing_scribe_side_or_gap_cannot_excuse_edge_sites(self):
        material=k.Region(k.Box(26000,26000,74000,74000))
        self.plan['scribe_boxes_nm'].pop()
        self.assertEqual(self.inspect(material)['status'],'unqualified_scribe_geometry')
        self.plan['scribe_boxes_nm'].append([100005,0,110000,100000])
        self.assertFalse(self.inspect(material)['no_legal_square_proven'])

    def test_smaller_prime_region_cannot_shrink_the_scope(self):
        self.plan['regions'][0]['bounds_nm']=[20000,20000,80000,80000]
        result=self.inspect(k.Region(k.Box(20000,20000,80000,80000)))
        self.assertEqual(result['status'],'unqualified_boundary_scope')

    def test_exact_limit_candidate_is_preserved(self):
        # A square at x=26 um has exactly 26 um street clearance and 3.5 um
        # circuit clearance. It must survive the absence-proof construction.
        comp=k.Region(k.Box(34500,0,100000,100000))
        self.assertFalse(self.inspect(comp)['no_legal_square_proven'])

    def test_mutated_source_is_rejected(self):
        (self.root/'floorplan.json').write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'SHA-256'):self.inspect(k.Region())


if __name__=='__main__':unittest.main()
