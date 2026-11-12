import json,tempfile,unittest
from pathlib import Path
import klayout.db as db
from icstudio.ihp_contact_rules import check,RULE_PATH
from icstudio.model import clone,example
from icstudio.layout_import import read_layout
from icstudio.verification_navigation import collect
ROOT=Path(__file__).resolve().parents[1]


class ContactRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=ROOT/'icstudio/assets/pdks/ihp-sg13g2';p=json.loads((root/'package.json').read_bytes())
        cls.tech=dict(package_root=str(root),package_lock={k:p[k] for k in ('id','revision','files')})

    def stream(self,root,width=160,height=160,rotation=0,dbu=.001,empty=False):
        ly=db.Layout();ly.dbu=dbu;c=ly.create_cell('coupon')
        if not empty:c.shapes(ly.layer(6,0)).insert(db.Box(0,0,width,height))
        c.transform(db.Trans(rotation));path=root/'input.gds';ly.write(str(path));return path

    def test_exact_threshold_both_axes_and_rotations(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for w,h in ((160,160),(159,160),(160,159),(80,80),(160,1000)):
                for rotation in (db.Trans.R0,db.Trans.R90):
                    with self.subTest(w=w,h=h,rotation=rotation):
                        r=check(self.stream(root,w,h,rotation),'coupon',self.tech)
                        self.assertEqual(r['status'],'PASS' if min(w,h)>=160 else 'FAIL')
                        self.assertEqual(bool(r['boxes_nm']),min(w,h)<160)

    def test_exact_units_empty_mask_and_changed_rule(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            self.assertEqual(check(self.stream(root,320,320,dbu=.0005),'coupon',self.tech)['status'],'PASS')
            self.assertEqual(check(self.stream(root,319,320,dbu=.001),'coupon',self.tech)['status'],'PASS')
            self.assertEqual(check(self.stream(root,empty=True),'coupon',self.tech)['violations'],0)
            with self.assertRaisesRegex(ValueError,'exact IHP'):check(self.stream(root,dbu=.003),'coupon',self.tech)
            bad=clone(self.tech);bad['package_lock']['files'][RULE_PATH]='0'*64
            with self.assertRaisesRegex(ValueError,'source is missing or changed'):check(self.stream(root),'coupon',bad)

    def test_written_findings_are_navigable_to_real_shapes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=self.stream(root,80,160);r=check(path,'coupon',self.tech)
            p,_=read_layout(path);(root/'drc').mkdir();(root/'drc/ihp-contact-width.json').write_text(json.dumps(r))
            issues=collect(p,p['top'],root)
            self.assertTrue(issues);self.assertTrue(all(v['code']=='IHP.Cnt.a' and v['objects'] for v in issues))


if __name__=='__main__':unittest.main()
