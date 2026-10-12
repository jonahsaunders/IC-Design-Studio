import tempfile
import unittest
from pathlib import Path
import klayout.db as k
from scripts.sky130_global_geometry import check, audit, edge_errors, layer_metadata, mask_purposes


def box(*values):return k.Region(k.Box(*values))
def counts(regions):return {r['rule']:r['violations'] for r in check(regions)['checks']}
def triangle(x=100,y=100):return k.Region(k.Polygon([k.Point(0,0),k.Point(x,0),k.Point(0,y)]))


class GlobalGeometryTests(unittest.TestCase):
    def test_all_three_orthogonal_groups_reject_diagonal_edges(self):
        groups={'x.2.diff':[(65,20)],'x.2.active_interconnect':[(65,44),(66,20),(67,20),(66,44),(89,44),(67,44),(68,44),(69,44)],
                'x.2.upper_via':[(70,44),(71,44)]}
        for rule,pairs in groups.items():
            for pair in pairs:
                with self.subTest(pair=pair):
                    self.assertEqual(counts({pair:box(0,0,100,100)})[rule],0)
                    self.assertGreater(counts({pair:triangle()})[rule],0)

    def test_other_layers_accept_45_and_reject_one_nm_slope_error(self):
        for pair in ((68,20),(64,20),(36,28),(74,20),(81,2)):
            self.assertEqual(counts({pair:triangle()})['x.3a'],0)
            self.assertGreater(counts({pair:triangle(100,101)})['x.3a'],0)

    def test_unmerged_internal_edges_and_holes_are_checked(self):
        region=box(-100,-100,1000,1000);region.insert(triangle(100,101))
        self.assertEqual(edge_errors(region,45),1)
        polygon=k.Polygon(k.Box(-100,-100,1000,1000))
        polygon.insert_hole([k.Point(0,0),k.Point(100,0),k.Point(0,101)])
        self.assertEqual(edge_errors(k.Region(polygon),45),1)

    def test_explicit_pins_require_their_own_drawn_purpose(self):
        # Public pins plus installed contact/tap/RDL purposes and old text
        # aliases: polygon data is never silently ignored on any pin purpose.
        cases=[((67,16),(67,20)),((68,16),(68,20)),((69,16),(69,20)),
               ((70,16),(70,20)),((71,16),(71,20)),((72,16),(72,20)),
               ((66,16),(66,20)),((65,16),(65,20)),((64,16),(64,20)),
               ((76,16),(76,20)),((65,48),(65,44)),((66,58),(66,44)),
               ((67,48),(67,44)),((68,58),(68,44)),((69,58),(69,44)),
               ((70,48),(70,44)),((71,48),(71,44)),((74,16),(74,20)),
               ((68,0),(68,20)),((64,0),(64,20))]
        for pin,drawing in cases:
            with self.subTest(pin=pin):
                self.assertEqual(counts({pin:box(0,0,100,100),drawing:box(0,0,100,100)})['x.5'],0)
                self.assertGreater(counts({pin:box(-1,0,100,100),drawing:box(0,0,100,100)})['x.5'],0)
                self.assertGreater(counts({pin:box(0,0,100,100)})['x.5'],0)

    def test_fill_and_other_metal_cannot_cover_a_pin(self):
        for pair in ((36,28),(69,20)):
            self.assertGreater(counts({(68,16):box(0,0,100,100),pair:box(-100,-100,200,200)})['x.5'],0)

    def test_unreviewed_purposes_are_rejected(self):
        self.assertGreater(counts({(900,900):box(0,0,100,100)})['profile.known_purposes'],0)
        known,pins=layer_metadata()
        self.assertEqual(len(known),442)
        self.assertIn((80,20),known);self.assertIn((65,8),known)
        self.assertEqual(pins[(74,16)],(74,20))
        for pair in ((23,28),(34,28),(36,28),(41,28),(51,28),(56,28),(59,28),(236,0)):
            self.assertIn(pair,known)

    def test_substrate_pin_uses_complement_of_nwell_without_artificial_bounds(self):
        for pair in ((122,16),(122,0)):
            self.assertEqual(counts({pair:box(0,0,100,100),(64,20):box(100,0,200,100)})['x.5'],0)
            self.assertGreater(counts({pair:box(0,0,101,100),(64,20):box(100,0,200,100)})['x.5'],0)
            self.assertEqual(counts({pair:box(-1000000,-1000000,-999000,-999000)})['x.5'],0)

    def test_isolated_pwell_pin_requires_dnw_and_excludes_nwell(self):
        pin={(44,16):box(0,0,100,100)}
        self.assertGreater(counts(pin)['x.5'],0)
        self.assertEqual(counts({**pin,(64,18):box(0,0,100,100)})['x.5'],0)
        self.assertGreater(counts({**pin,(64,18):box(1,0,100,100)})['x.5'],0)
        self.assertGreater(counts({**pin,(64,18):box(0,0,100,100),(64,20):box(99,0,200,100)})['x.5'],0)
        self.assertGreater(counts({**pin,(64,44):box(0,0,100,100)})['x.5'],0)

    def test_mask_edit_purposes_require_actual_core_coverage(self):
        edits,_=mask_purposes()
        for pair in ((22,21),(22,22),(109,43),(109,42),(33,43),(33,42),(117,21),(117,22)):
            self.assertIn(pair,edits)
            self.assertGreater(counts({pair:box(0,0,100,100)})['x.9'],0)
            self.assertEqual(counts({pair:box(0,0,100,100),(81,2):box(0,0,100,100)})['x.9'],0)
            self.assertGreater(counts({pair:box(-1,0,100,100),(81,2):box(0,0,100,100)})['x.9'],0)

    def test_mask_and_drawn_compatible_data_need_exact_allowed_region(self):
        _,restricted=mask_purposes()
        for pair in ((23,0),(17,0),(96,44),(91,44),(22,20),(33,44),(93,0),(22,24),(117,4)):
            self.assertIn(pair,restricted)
            self.assertGreater(counts({pair:box(0,0,100,100)})['x.15a'],0)
            for marker in ((81,10),(81,1),(81,12)):
                self.assertEqual(counts({pair:box(0,0,100,100),marker:box(0,0,100,100)})['x.15a'],0)
                ring=box(-100,-100,200,200)-box(0,0,100,100)
                self.assertGreater(counts({pair:box(0,0,100,100),marker:ring})['x.15a'],0)
        # Native physical fill is distinct from waffleDrop override data.
        for pair in ((23,28),(34,28),(36,28),(41,28),(51,28),(56,28),(59,28)):
            self.assertNotIn(pair,restricted)
            self.assertEqual(counts({pair:box(0,0,100,100)})['x.15a'],0)

    def test_hierarchy_cross_level_containment_and_text_distinction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'case.gds';layout=k.Layout();layout.dbu=.001
            top=layout.create_cell('top');child=layout.create_cell('child')
            child.shapes(layout.layer(68,16)).insert(k.Box(0,0,100,100))
            # Floating text is a different requirement (x.17), not a polygon.
            child.shapes(layout.layer(68,16)).insert(k.Text('floating',k.Trans(10000,10000)))
            top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.R90,1000,2000)))
            top.shapes(layout.layer(68,20)).insert(k.Box(900,2000,1000,2100))
            layout.write(str(path));self.assertEqual(audit(path)['status'],'PASS')
            child.shapes(layout.layer(68,16)).insert(k.Box(-1,0,100,100))
            layout.write(str(path));self.assertEqual(audit(path)['status'],'FAIL')


if __name__=='__main__':unittest.main()
