import unittest
import klayout.db as k
from scripts.check_ihp_fill_rules import audit_layout


class IHPFillRulesTests(unittest.TestCase):
    def layout(self):
        ly=k.Layout();ly.dbu=.001;c=ly.create_cell('test')
        c.shapes(ly.layer(1,22)).insert(k.Box(0,0,3400,3400))
        return ly,c

    def test_active_poly_clearance_threshold_and_overlap(self):
        for gap,passed in ((1100,True),(1099,False),(-100,False)):
            ly,c=self.layout();c.shapes(ly.layer(5,0)).insert(k.Box(3400+gap,0,6000+gap,1000))
            r=audit_layout(ly);self.assertEqual('AFil.c.GatPoly' not in r['failed_rules'],passed)

    def test_well_boundary_inside_and_outside(self):
        for box,passed in ((k.Box(4400,0,6000,3400),True),(k.Box(4399,0,6000,3400),False),
                           (k.Box(-1000,-1000,4400,4400),True),(k.Box(-999,-1000,4400,4400),False)):
            ly,c=self.layout();c.shapes(ly.layer(31,0)).insert(box)
            self.assertEqual('AFil.d.NWell' not in audit_layout(ly)['failed_rules'],passed)

    def test_conditional_enclosure_is_not_vacuously_passed(self):
        ly,c=self.layout();r=audit_layout(ly)
        self.assertEqual(next(x for x in r['checks'] if x['rule']=='AFil.j.SalBlock')['status'],'not_applicable')
        c.shapes(ly.layer(46,21)).insert(k.Box(-2000,-2000,5400,5400))
        r=audit_layout(ly);self.assertIn('AFil.j.SalBlock',r['failed_rules'])
        for pair in ((7,21),(28,0)):c.shapes(ly.layer(*pair)).insert(k.Box(-250,-250,3650,3650))
        self.assertNotIn('AFil.j.SalBlock',audit_layout(ly)['failed_rules'])

    def test_nofill_and_chip_scope_reject(self):
        ly,c=self.layout();c.shapes(ly.layer(1,23)).insert(k.Box(0,0,100,100))
        self.assertIn('exclusion.1.nofill',audit_layout(ly)['failed_rules'])
        c.shapes(ly.layer(189,0)).insert(k.Box(0,0,200000,200000))
        self.assertIn('scope.block_boundaries',audit_layout(ly)['failed_rules'])

    def test_inside_pwell_edge_requires_full_clearance(self):
        for distance in (1500,1499):
            ly,c=self.layout();c.shapes(ly.layer(46,21)).insert(k.Box(-distance,-1500,4900,4900))
            result=audit_layout(ly)
            self.assertEqual('AFil.i.clearance' in result['failed_rules'],distance<1500)


if __name__=='__main__':unittest.main()
