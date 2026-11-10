import json,unittest
from pathlib import Path
from icstudio.model import clone
from scripts import qualify_ihp_guard_corner_safe as runner
from scripts import ihp_guard_corner_conditioner as c
from scripts.qualify_ihp_guard_vias import guard_access,guard_audit,fault_layout
from scripts.qualification_geometry import regions

class CornerSafeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.fixtures=json.loads((Path(__file__).parent/'fixtures/ihp-guard-raw-all100-v1.json').read_text())
    def test_exact_mask_delta_and_contact_graph(self):
        for model,p in self.fixtures.items():
            with self.subTest(model=model):
                q,r=c.condition(p,model,runner.CONTRACT['coverage_cases']['all100'],runner.CONTRACT)
                self.assertEqual((r['via1_before'],r['via1_after']),(56,54));self.assertEqual(r['m2_added_nm2'],250000)
                a,b=regions(p),regions(q)
                self.assertEqual((b[(10,0)]-a[(10,0)]).area(),250000);self.assertTrue((a[(10,0)]-b[(10,0)]).is_empty())
                for key in a:
                    if key not in ((10,0),(19,0)):self.assertTrue((a[key]^b[key]).is_empty())
                oldcuts=[x.bbox() for x in a[(19,0)].each()];newcuts=[x.bbox() for x in b[(19,0)].each()]
                oldhorizontal=sorted(str(x) for x in oldcuts if abs(x.center().x)<1400)
                self.assertEqual(oldhorizontal,sorted(str(x) for x in newcuts if abs(x.center().x)<1400))
                for side in (-1,1):self.assertEqual(sum(x.center().x*side>1400 for x in newcuts),20)
                for i,x in enumerate(newcuts):
                    for y in newcuts[i+1:]:
                        dx=max(x.left-y.right,y.left-x.right,0);dy=max(x.bottom-y.top,y.bottom-x.top,0)
                        self.assertGreaterEqual(max(dx,dy),220)
                q=guard_access(q,runner.CONTRACT['coverage_cases']['all100']);self.assertEqual(guard_audit(q)['B']['via1_cuts'],54)
                with self.assertRaises(ValueError):guard_audit(fault_layout(q,'guard-via-open'))
    def test_other_coverages_byte_equivalent(self):
        p=self.fixtures['rsil']
        for coverage in runner.CONTRACT['unchanged_coverage_cases']:
            q,r=c.condition(p,'rsil',coverage,runner.CONTRACT);self.assertEqual(q,p);self.assertFalse(r['applied'])
    def test_unreviewed_geometry_rejected(self):
        p=clone(self.fixtures['rsil']);p['cells'][0]['shapes'][0]['points'][0][0]+=5
        with self.assertRaisesRegex(ValueError,'Unreviewed raw'):c.condition(p,'rsil',runner.CONTRACT['coverage_cases']['all100'],runner.CONTRACT)
    def test_source_rule_and_declared_material_change(self):
        self.assertEqual(runner.CONTRACT['cifout_rule'],'squares-grid 5 190 220')
        self.assertFalse(runner.CONTRACT['native_equivalence'])
        self.assertEqual(c.PITCH,410)
        for p in self.fixtures.values():
            cuts=list(regions(p)[(19,0)].each());self.assertEqual(len(cuts),56)

if __name__=='__main__':unittest.main()
