import tempfile
import unittest
from pathlib import Path
import klayout.db as k
from scripts.sky130_floating_connectivity import check, audit


def box(x1=0,y1=0,x2=100,y2=100):return k.Region(k.Box(x1,y1,x2,y2))
def marker(report,name):return next(row['violations'] for row in report['checks'] if row['rule']==name)


class FloatingConnectivityTests(unittest.TestCase):
    def test_closed_floating_stack_defeats_neighbor_contact_check_but_fails_graph(self):
        regions={(68,20):box(),(68,44):box(),(69,20):box()}
        report=check(regions)
        self.assertEqual(marker(report,'x.22'),1)
        self.assertEqual(report['floating'][0]['layers'],['m1','m2'])
        self.assertEqual(marker(report,'profile.complete_extraction'),0)

    def test_each_missing_contact_breaks_complete_path_to_gate(self):
        pairs=[(66,20),(66,44),(67,20),(67,44),(68,20),(68,44),(69,20),(69,44),(70,20),(70,44),(71,20),(71,44),(72,20)]
        regions={pair:box() for pair in pairs};regions[(65,20)]=box()
        self.assertEqual(check(regions)['status'],'PASS')
        for pair in pairs[1::2]:
            broken={p:r for p,r in regions.items() if p!=pair}
            with self.subTest(cut=pair):self.assertEqual(marker(check(broken),'x.22'),1)

    def test_diffusion_root_requires_actual_licon_path(self):
        regions={(65,20):box(),(66,44):box(),(67,20):box()}
        self.assertEqual(check(regions)['status'],'PASS')
        del regions[(66,44)]
        self.assertEqual(marker(check(regions),'x.22'),1)
        self.assertEqual(marker(check({(66,20):box()}),'x.22'),1)

    def test_wrong_layer_pin_and_fill_cannot_root_a_floating_wire(self):
        regions={(68,20):box()}
        self.assertEqual(check(regions,{(68,16):box()})['status'],'PASS')
        self.assertGreater(marker(check(regions,{(69,16):box()}),'x.22'),0)
        self.assertGreater(marker(check({**regions,(36,28):box()}),'x.22'),0)
        self.assertGreater(marker(check(regions,{(68,16):box(-1,0,100,100)}),'profile.pin_coverage.m1'),0)

    def test_pin_annotation_cannot_bridge_two_islands(self):
        metal=box(0,0,100,100)|box(200,0,300,100)
        report=check({(68,20):metal},{(68,16):box(0,0,300,100)})
        self.assertGreater(marker(report,'profile.pin_coverage.m1'),0)
        self.assertEqual(report['nets'],2)

    def test_exception_labels_and_unsupported_capacitors_remain_failures(self):
        for label in ('m1_float','M5_TIE',' poly_float '):
            self.assertGreater(marker(check({},labels=[label]),'profile.exception_labels'),0)
        for pair in ((89,44),(97,44),(74,20),(66,14),(68,15)):
            self.assertEqual(check({pair:box()})['status'],'FAIL')

    def test_gate_is_not_a_short_between_source_and_drain(self):
        # A wire touching only the remote source/drain remains a separate
        # rooted net. No graph connection is made across the gate oxide.
        regions={(65,20):box(0,0,300,100),(66,20):box(100,-100,200,200),
                 (66,44):box(0,0,50,50),(67,20):box(0,0,50,50)}
        report=check(regions)
        self.assertEqual(report['status'],'PASS');self.assertEqual(report['nets'],3)

    def test_poly_short_can_annotate_but_never_supply_missing_material_or_a_root(self):
        regions={(66,20):box(),(65,20):box()};before=check(regions)
        after=check({**regions,(66,15):box()})
        self.assertEqual(after['status'],'PASS')
        self.assertEqual(before['nets'],after['nets']);self.assertEqual(before['layer_area_nm2'],after['layer_area_nm2'])
        self.assertGreater(marker(check({**regions,(66,15):box(-1,0,100,100)}),'profile.poly_short_coverage'),0)
        self.assertEqual(marker(check({(66,20):box(),(66,15):box()}),'x.22'),1)
        broken={(66,20):box(0,0,100,100)|box(200,0,300,100),(66,15):box(0,0,300,100)}
        report=check(broken)
        self.assertEqual(report['nets'],2);self.assertEqual(marker(report,'x.22'),2)
        self.assertGreater(marker(report,'profile.poly_short_coverage'),0)

    def test_hierarchy_is_flattened_but_only_block_pins_are_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'case.gds';ly=k.Layout();ly.dbu=.001
            top=ly.create_cell('block');child=ly.create_cell('leaf')
            child.shapes(ly.layer(68,20)).insert(k.Box(0,0,100,100))
            child.shapes(ly.layer(68,16)).insert(k.Box(0,0,100,100))
            top.insert(k.CellInstArray(child.cell_index(),k.Trans(1000,1000)))
            ly.write(str(path));self.assertEqual(marker(audit(path),'x.22'),1)
            top.shapes(ly.layer(68,16)).insert(k.Box(1000,1000,1100,1100))
            ly.write(str(path));self.assertEqual(audit(path)['status'],'PASS')


if __name__=='__main__':unittest.main()
