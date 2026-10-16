import unittest
import klayout.db as k
from scripts.sky130_interconnect_geometry import check, adjacent_enclosure


def region(*boxes):
    r=k.Region()
    for box in boxes:r.insert(k.Box(*box))
    return r.merged()


def counts(masks):
    return {c['rule']:c['violations'] for c in check(masks)['checks']}


class InterconnectGeometryTests(unittest.TestCase):
    def test_metal_width_spacing_and_notches_include_fill(self):
        for name,drawn,fill,width,space in (
            ('li',(67,20),(56,28),170,170),('m1',(68,20),(36,28),140,140),
            ('m2',(69,20),(41,28),140,140),('m3',(70,20),(34,28),300,300),
            ('m4',(71,20),(51,28),300,300),('m5',(72,20),(59,28),1600,1600)):
            wr=name+'.1'+('.-' if name=='li' else '');sr=name+('.3.-' if name=='li' else '.2')
            for delta in (-5,0,5):
                for pair in (drawn,fill):
                    with self.subTest(name=name,delta=delta,pair=pair):
                        self.assertEqual(counts({pair:region((0,0,width+delta,10000))})[wr]>0,delta<0)
                        u=region((0,0,2000,10000),(2000+space+delta,0,4000+space+delta,10000),
                                 (0,0,4000+space+delta,2000))
                        self.assertEqual(counts({pair:u})[sr]>0,delta<0)
                masks={drawn:region((0,0,2000,10000)),fill:region((2000+space+delta,0,4000+space+delta,10000))}
                self.assertEqual(counts(masks)[sr]>0,delta<0)

    def test_metal_area_and_hole_boundaries(self):
        for pair,rule,unit_width,height in (
            ((67,20),'li.6.-',100,561),((68,20),'m1.6',1000,83),
            ((69,20),'m2.6',100,676),((70,20),'m3.6',1000,240),
            ((71,20),'m4.4a',1000,240),((72,20),'m5.4',1000,4000)):
            for delta in (-1,0,1):
                self.assertEqual(counts({pair:region((0,0,unit_width,height+delta))})[rule]>0,delta<0)
        for pair,rule in (((68,20),'m1.7'),((69,20),'m2.7')):
            for delta in (-1,0,1):
                ring=region((-1000,-1000,3000,3000))-region((0,0,1000,140+delta))
                self.assertEqual(counts({pair:ring})[rule]>0,delta<0)

    def test_contacts_have_exact_square_dimensions_and_spacing(self):
        for name,pair,size,space in (
            ('ct',(67,44),170,190),('via',(68,44),150,170),('via2',(69,44),200,200),
            ('via3',(70,44),200,200),('via4',(71,44),800,800)):
            for delta in (-5,0,5):
                with self.subTest(name=name,delta=delta):
                    self.assertEqual(counts({pair:region((0,0,size+delta,size))})[name+'.size']>0,delta!=0)
                    shapes=region((0,0,size,size),(size+space+delta,0,2*size+space+delta,size))
                    self.assertEqual(counts({pair:shapes})[name+'.2']>0,delta<0)
            l=region((0,0,size,size//2),(0,size//2,size//2,size))
            self.assertGreater(counts({pair:l})[name+'.size'],0)

    def test_all_contact_conductor_enclosure_boundaries(self):
        for rule,outer,inner,size,margin in (
            ('m1.4',(68,20),(67,44),170,30),('via.4a',(68,20),(68,44),150,55),
            ('m2.4',(69,20),(68,44),150,55),('via2.4',(69,20),(69,44),200,40),
            ('m3.4',(70,20),(69,44),200,65),('via3.4',(70,20),(70,44),200,60),
            ('m4.3',(71,20),(70,44),200,65),('via4.4',(71,20),(71,44),800,190),
            ('m5.3',(72,20),(71,44),800,310)):
            for delta in (-5,0,5):
                m=margin+delta;masks={inner:region((0,0,size,size)),outer:region((-m,-m,size+m,size+m))}
                with self.subTest(rule=rule,delta=delta):
                    self.assertEqual(counts(masks)[rule]>0,delta<0)
            self.assertGreater(counts({inner:region((0,0,size,size))})[rule],0)

    def test_zero_enclosure_requires_complete_drawn_li_coverage(self):
        ct=region((0,0,170,170))
        self.assertEqual(counts({(67,44):ct,(67,20):ct})['ct.4'],0)
        self.assertGreater(counts({(67,44):ct,(67,20):region((5,0,170,170))})['ct.4'],0)
        self.assertGreater(counts({(67,44):ct,(56,28):ct})['ct.4'],0)

    def test_core_marker_cannot_hide_an_uncovered_contact(self):
        # The public 2025 Tiny Tapeout deck excludes areaid:core from its
        # contact-coverage check. Studio must still detect missing drawn LI.
        # Test absent, enclosing and crossing core markers and a one-nm gap.
        ct=region((0,0,170,170))
        for core in (region(),region((-1000,-1000,1000,1000)),region((85,-1000,1000,1000))):
            for li,expected in ((ct,False),(region((1,0,170,170)),True),(region(),True)):
                with self.subTest(core=str(core),li=str(li)):
                    masks={(67,44):ct,(67,20):li,(81,2):core,(56,28):ct}
                    self.assertEqual(counts(masks)['ct.4']>0,expected)

    def test_fill_cannot_replace_missing_contact_conductor(self):
        for inner,fill,size,rule in (((68,44),(36,28),150,'via.4a'),
                                    ((69,44),(34,28),200,'m3.4'),((71,44),(59,28),800,'m5.3')):
            masks={inner:region((0,0,size,size)),fill:region((-1000,-1000,size+1000,size+1000))}
            self.assertGreater(counts(masks)[rule],0)

    def test_via2_needs_both_layers(self):
        cut=region((0,0,200,200));masks={(69,44):cut,(69,20):cut,(70,20):cut}
        self.assertEqual(counts(masks)['via2.X.1'],0)
        for pair in ((69,20),(70,20)):
            self.assertGreater(counts({**masks,pair:k.Region()})['via2.X.1'],0)

    def test_every_adjacent_pair_requires_a_good_side(self):
        cut=region((0,0,170,170))
        for bits in range(16):
            good=[bool(bits&(1<<i)) for i in range(4)]
            left,bottom,right,top=[80 if x else 75 for x in good]
            metal=region((-left,-bottom,170+right,170+top))
            expected=not((good[0] and good[2]) or (good[1] and good[3]))
            for rotate in (False,True):
                a=cut.transformed(k.Trans.R90) if rotate else cut
                b=metal.transformed(k.Trans.R90) if rotate else metal
                with self.subTest(bits=bits,rotate=rotate):
                    self.assertEqual(adjacent_enclosure(a,b,80)>0,expected)
        self.assertGreater(adjacent_enclosure(cut,k.Region(),80),0)

    def test_partial_bad_sides_are_not_promoted_to_whole_edges(self):
        cut=region((0,0,170,170));metal=region((-80,-80,250,250))-region((-80,50,-75,100),(50,-80,100,-75))
        self.assertEqual(adjacent_enclosure(cut,metal,80),0)
        # Move both deficient portions to their shared corner: now it fails.
        metal=region((-80,-80,250,250))-region((-80,-80,-75,100),(-80,-80,100,-75))
        self.assertGreater(adjacent_enclosure(cut,metal,80),0)
        other=cut.transformed(k.Trans(1000,0));good=region((920,-80,1250,250))
        self.assertGreater(adjacent_enclosure(cut|other,metal|good,80),0)
        self.assertEqual(adjacent_enclosure(other,good,80),0)

    def test_nor4b_t_junction_contact_and_corner_fault(self):
        cut=region((0,0,170,170))
        for left in (75,80,85):
            metal=region((-left,0,235,170),(65,-200,235,400))
            for trans in (k.Trans.R0,k.Trans.R90,k.Trans.R180,k.Trans.R270):
                with self.subTest(left=left,trans=str(trans)):
                    self.assertEqual(adjacent_enclosure(cut.transformed(trans),metal.transformed(trans),80)>0,left<80)

    def test_adjacent_enclosure_rule_bindings_use_their_own_thresholds(self):
        for rule,inner,outer,size,margin in (
            ('licon.5c',(66,44),(65,20),170,60),('licon.7',(66,44),(65,44),170,120),
            ('licon.8a',(66,44),(66,20),170,80),('li.5.-',(66,44),(67,20),170,80),
            ('m1.5',(67,44),(68,20),170,60),('via.5a',(68,44),(68,20),150,85),
            ('m2.5',(68,44),(69,20),150,85),('via2.5',(69,44),(69,20),200,85),
            ('via3.5',(70,44),(70,20),200,90)):
            for delta in (-5,0,5):
                m=margin+delta;masks={inner:region((0,0,size,size)),outer:region((-m,-m,size+m,size+m))}
                with self.subTest(rule=rule,delta=delta):self.assertEqual(counts(masks)[rule]>0,delta<0)

    def test_tap_contact_spacing_uses_actual_abutting_portion(self):
        for gap in (55,60,65):
            masks={(65,44):region((0,0,1000,1000)),(65,20):region((1000,0,2000,1000)),
                   (66,44):region((830-gap,300,1000-gap,470))}
            self.assertEqual(counts(masks)['licon.5b']>0,gap<60)
        masks[(65,20)]=region((1000,700,2000,1000))
        masks[(66,44)]=region((775,200,945,370))
        self.assertEqual(counts(masks)['licon.5b'],0)

    def test_profile_rejects_exceptions_instead_of_disabling_checks(self):
        for pair in ((81,1),(81,2),(81,10),(81,12),(86,20),(79,20)):
            self.assertGreater(counts({pair:region((0,0,1000,1000))})['profile.absent.'+str(pair)],0)


if __name__=='__main__':unittest.main()
