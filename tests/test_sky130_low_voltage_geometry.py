import tempfile
from pathlib import Path
import unittest
import klayout.db as k
from scripts.sky130_low_voltage_geometry import check, audit


def region(*boxes):
    r=k.Region()
    for box in boxes:r.insert(k.Box(*box))
    return r.merged()


def counts(masks):
    return {r['rule']:r['violations'] for r in check(masks)['checks']}


def transistor(width=420,length=150,drain=250,endcap=130):
    return {(65,20):region((-drain,0,length+drain,width)),
            (66,20):region((0,-endcap,length,width+endcap))}


class LowVoltageGeometryTests(unittest.TestCase):
    def test_width_and_notch_limits(self):
        for pair,width,space,wr,sr in (
            ((64,20),840,1270,'nwell.1','nwell.2a'),
            ((65,20),150,270,'difftap.1.diff','difftap.3'),
            ((65,44),150,270,'difftap.1.tap','difftap.3'),
            ((66,20),150,210,'poly.1a','poly.2'),
            ((95,20),270,270,'npc.1','npc.2')):
            for delta in (-5,0,5):
                with self.subTest(pair=pair,delta=delta):
                    self.assertEqual(counts({pair:region((0,0,width+delta,5000))})[wr]>0,delta<0)
                    u=region((0,0,2000,5000),(2000+space+delta,0,4000+space+delta,5000),
                             (0,0,4000+space+delta,2000))
                    self.assertEqual(counts({pair:u})[sr]>0,delta<0)

    def test_each_merged_well_needs_its_own_contacted_tap(self):
        masks={(64,20):region((0,0,2000,2000),(4000,0,6000,2000)),
               (65,44):region((500,500,1000,1000),(4500,500,5000,1000)),
               (66,44):region((600,600,770,770))}
        self.assertEqual(counts(masks)['nwell.4'],1)
        masks[(66,44)]|=region((4600,600,4770,770))
        self.assertEqual(counts(masks)['nwell.4'],0)
        self.assertEqual(counts({**masks,(65,44):k.Region()})['nwell.4'],2)
        self.assertEqual(counts({**masks,(66,44):k.Region()})['nwell.4'],2)

    def test_channel_width_and_orientation(self):
        for sc,minimum,rule in ((False,420,'difftap.2'),(True,360,'difftap.2b')):
            for delta in (-5,0,5):
                for rotate in (False,True):
                    masks=transistor(width=minimum+delta)
                    if sc:masks[(81,4)]=region((-2000,-2000,2000,2000))
                    if rotate:masks={p:r.transformed(k.Trans.R90) for p,r in masks.items()}
                    with self.subTest(sc=sc,delta=delta,rotate=rotate):
                        c=counts(masks);self.assertEqual(c['profile.crossing_gate'],0)
                        self.assertEqual(c[rule]>0,delta<0)
                        self.assertEqual(c['poly.1a'],0)

    def test_partial_standard_cell_marker_is_rejected(self):
        masks=transistor();masks[(81,4)]=region((-2000,100,2000,2000))
        self.assertGreater(counts(masks)['profile.sc_straddle'],0)

    def test_nonabut_active_spacing_and_butting(self):
        for gap in (0,265,270,275):
            masks={(65,20):region((0,0,1000,1000)),(65,44):region((1000+gap,0,2000+gap,1000))}
            self.assertEqual(counts(masks)['difftap.3']>0,0<gap<270)
        self.assertGreater(counts({(65,20):region((0,0,1000,1000)),
                                  (65,44):region((995,0,2000,1000))})['profile.active_overlap'],0)

    def test_active_well_enclosure_and_outside_spacing(self):
        for pair,enc,gap,inside_rule,outside_rule in (
            ((65,20),180,340,'difftap.8','difftap.9'),((65,44),180,130,'difftap.10','difftap.11')):
            for delta in (-5,0,5):
                m=enc+delta;masks={pair:region((0,0,1000,1000)),(64,20):region((-m,-m,1000+m,1000+m))}
                with self.subTest(pair=pair,delta=delta):
                    self.assertEqual(counts(masks)[inside_rule]>0,delta<0)
                    masks[(64,20)]=region((1000+gap+delta,0,3000,3000))
                    self.assertEqual(counts(masks)[outside_rule]>0,delta<0)
        masks={(65,44):region((0,0,1000,1000)),(64,20):region((500,-500,2000,2000))}
        self.assertGreater(counts(masks)['profile.active_well_straddle'],0)

    def test_gate_drain_and_endcap_limits(self):
        for delta in (-5,0,5):
            for rotate in (False,True):
                for target,rule,kwargs in [('drain','poly.7',dict(drain=250+delta)),
                                           ('endcap','poly.8',dict(endcap=130+delta))]:
                    masks=transistor(**kwargs)
                    if rotate:masks={p:r.transformed(k.Trans.R90) for p,r in masks.items()}
                    with self.subTest(target=target,delta=delta,rotate=rotate):
                        self.assertEqual(counts(masks)[rule]>0,delta<0)

    def test_gate_termination_and_bends_cannot_evade_enclosure(self):
        masks=transistor();masks[(66,20)]=region((0,100,150,1000))
        self.assertGreater(counts(masks)['profile.crossing_gate'],0)
        self.assertGreater(counts(masks)['poly.11'],0)
        masks[(66,20)]=region((0,-1000,150,250),(0,100,1000,250))
        self.assertGreater(counts(masks)['profile.rectangular_gate'],0)
        self.assertGreater(counts(masks)['poly.11'],0)

    def test_two_adjacent_ends_do_not_make_a_crossing_gate(self):
        masks={(65,20):region((0,0,1000,1000)),(66,20):region((500,500,1500,1500))}
        self.assertGreater(counts(masks)['profile.crossing_gate'],0)
        self.assertGreater(counts(masks)['poly.11'],0)

    def test_field_poly_checks_only_original_parallel_edges(self):
        for gap in (70,75,80):
            masks={(65,20):region((0,0,1000,1000)),(66,20):region((1000+gap,0,1500,1000))}
            self.assertEqual(counts(masks)['poly.4']>0,gap<75)
        self.assertEqual(counts(transistor())['poly.4'],0)
        # Corner-only proximity has no projected parallel overlap.
        self.assertEqual(counts({(65,20):region((0,0,1000,1000)),
                                 (66,20):region((1010,1010,1500,1500))})['poly.4'],0)

    def test_field_poly_to_tap_and_gate_to_abutting_tap(self):
        for delta in (-5,0,5):
            masks={(65,44):region((0,0,1000,1000)),(66,20):region((1055+delta,0,2000,1000))}
            self.assertEqual(counts(masks)['poly.5']>0,delta<0)
            masks=transistor(drain=300+delta)
            masks[(65,44)]=region((-1000,0,-300-delta,420))
            self.assertEqual(counts(masks)['poly.6']>0,delta<0)

    def test_inner_corner_uses_concave_not_convex_vertices(self):
        l=region((0,0,1000,500),(0,500,500,1000))
        masks={(65,20):l,(66,20):region((400,400,600,600))}
        self.assertGreater(counts(masks)['poly.10'],0)
        masks[(66,20)]=region((-100,-100,100,100))
        self.assertEqual(counts(masks)['poly.10'],0)
        masks[(66,20)]=region((501,501,700,700))
        self.assertEqual(counts(masks)['poly.10'],0)

    def test_poly_tap_overlap_depends_on_well(self):
        masks={(65,44):region((0,0,1000,1000)),(66,20):region((100,100,300,300))}
        self.assertGreater(counts(masks)['poly.12'],0)
        masks[(64,20)]=region((-2000,-2000,3000,3000))
        self.assertEqual(counts(masks)['poly.12'],0)

    def test_npc_gate_distance_and_full_overlap(self):
        for gap in (85,90,95):
            masks=transistor();masks[(95,20)]=region((150+gap,0,1000,420))
            self.assertEqual(counts(masks)['npc.4']>0,gap<90)
        masks[(95,20)]=region((-1000,-1000,2000,2000))
        self.assertGreater(counts(masks)['npc.4'],0)

    def test_licon_exact_size_spacing_and_non_rectangle(self):
        for size in (165,170,175):
            self.assertEqual(counts({(66,44):region((0,0,size,170))})['licon.1']>0,size!=170)
        for gap in (165,170,175):
            masks={(66,44):region((0,0,170,170),(170+gap,0,340+gap,170))}
            self.assertEqual(counts(masks)['licon.2']>0,gap<170)
        l=region((0,0,170,85),(0,85,85,170))
        self.assertGreater(counts({(66,44):l})['licon.1'],0)

    def test_contact_overlap_and_straddle(self):
        contact=region((0,0,170,170));masks={(66,44):contact,(67,20):contact,(65,44):contact}
        self.assertEqual(counts(masks)['licon.4'],0)
        for pair in ((67,20),(65,44)):
            self.assertGreater(counts({**masks,pair:k.Region()})['licon.4'],0)
        self.assertGreater(counts({**masks,(65,44):region((5,0,200,200))})['licon.6'],0)
        # Edge touching alone is not electrical overlap.
        self.assertGreater(counts({**masks,(67,20):region((170,0,340,170))})['licon.4'],0)

    def test_diff_poly_npc_contact_enclosure_and_missing_masks(self):
        for pair,margin,rule in (((65,20),40,'licon.5a'),((66,20),50,'licon.8'),((95,20),100,'licon.15')):
            for delta in (-5,0,5):
                m=margin+delta;masks={(66,44):region((0,0,170,170)),pair:region((-m,-m,170+m,170+m))}
                self.assertEqual(counts(masks)[rule]>0,delta<0)
        # Derived poly_licon persists even when poly or NPC is missing.
        for rule in ('licon.8','licon.15','licon.18'):
            self.assertGreater(counts({(66,44):region((0,0,170,170))})[rule],0)

    def test_contact_to_implant_active_and_npc_spacing(self):
        for rule,pair,gap in (('licon.9',(94,20),110),('licon.14',(65,44),190)):
            for delta in (-5,0,5):
                masks={(66,44):region((0,0,170,170)),pair:region((170+gap+delta,0,1000,1000))}
                self.assertEqual(counts(masks)[rule]>0,delta<0)
        for delta in (-5,0,5):
            masks={(66,44):region((0,0,170,170)),(65,20):region((-50,-50,220,220)),
                   (95,20):region((260+delta,0,1000,1000))}
            self.assertEqual(counts(masks)['licon.13']>0,delta<0)
        masks[(95,20)]=region((-500,-500,1000,1000))
        self.assertGreater(counts(masks)['licon.13'],0)

    def test_gate_contact_spacing_respects_standard_cell_selector(self):
        for sc,gap,rule in ((False,55,'licon.11'),(True,50,'licon.11ab')):
            for delta in (-5,0,5):
                masks=transistor(drain=1000)
                masks[(66,44)]=region((150+gap+delta,100,320+gap+delta,270))
                if sc:masks[(81,4)]=region((-2000,-2000,2000,2000))
                self.assertEqual(counts(masks)[rule]>0,delta<0)

    def test_each_tap_and_source_requires_contained_contact(self):
        masks={(65,20):region((0,0,1000,1000)),(65,44):region((1000,0,2000,1000)),
               (66,44):region((200,200,370,370),(1200,200,1370,370))}
        self.assertEqual(counts(masks)['licon.16'],0)
        masks[(66,44)]=region((200,200,370,370))
        self.assertEqual(counts(masks)['licon.16'],1)
        masks[(66,44)]=region((950,200,1120,370))
        self.assertEqual(counts(masks)['licon.16'],2)
        masks[(66,44)]=k.Region()
        self.assertEqual(counts(masks)['licon.16'],2)

    def test_contact_cannot_bridge_poly_and_active(self):
        masks={(65,20):region((0,0,1000,1000)),(66,20):region((0,1100,1000,1300)),
               (66,44):region((100,950,270,1120))}
        self.assertGreater(counts(masks)['licon.17'],0)

    def test_unsupported_process_and_non_manhattan_fail(self):
        self.assertGreater(counts({(75,20):region((0,0,1000,1000))})['profile.absent.(75, 20)'],0)
        self.assertGreater(counts({(74,22):region((0,0,1000,1000))})['profile.absent.(74, 22)'],0)
        triangle=k.Region(k.Polygon([k.Point(0,0),k.Point(1000,0),k.Point(0,1000)]))
        self.assertGreater(counts({(66,20):triangle})['profile.manhattan.poly'],0)

    def test_hierarchy_is_checked_and_database_units_are_not_assumed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.gds';layout=k.Layout();layout.dbu=.001
            top=layout.create_cell('TOP');child=layout.create_cell('CHILD')
            child.shapes(layout.layer(66,44)).insert(k.Box(0,0,165,170))
            top.insert(k.CellInstArray(child.cell_index(),k.Trans(1000,2000)))
            layout.write(str(path));r=audit(path)
            self.assertEqual(r['status'],'FAIL');self.assertFalse(r['qualified'])
            self.assertEqual(next(c['violations'] for c in r['checks'] if c['rule']=='licon.1'),1)
            layout.dbu=.005;layout.write(str(path))
            with self.assertRaisesRegex(ValueError,'database grid'):audit(path)


if __name__=='__main__':unittest.main()
