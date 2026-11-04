"""Boundary geometry and physical fault controls use real KLayout regions."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from icstudio.layout import kdb,polygon
from icstudio.process_adapters import ADAPTERS
from scripts.qualify_standard_mos import load_technology
from scripts.qualify_mos_boundaries import contract
from scripts.qualify_mos_physical_boundaries import TARGETS,FAULTS,fixture,altered

class MosPhysicalBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.technologies={t:load_technology(t)[0] for t in TARGETS}

    def regions(self,cell,layers):
        db=kdb();result={key:db.Region() for key in layers}
        for key,region in result.items():
            for shape in cell['shapes']:
                if shape['layer']==layers[key]:region.insert(polygon(shape))
            region.merge()
        return result

    def test_published_sizes_preserve_exact_channel_geometry_and_contact_enclosure(self):
        for target in TARGETS:
            for polarity in ('n','p'):
                for width,length in contract(target)['sizes']:
                    with self.subTest(target=target,polarity=polarity,w=width,l=length):
                        p,c,layers,ref=fixture(self.technologies[target],target,polarity,width,length)
                        r=self.regions(c,layers);channel=(r['diff']&r['poly']).merged()
                        self.assertEqual(channel.count(),1)
                        self.assertEqual(channel.bbox().width(),round(length*1000))
                        self.assertEqual(channel.bbox().height(),round(width*1000))
                        self.assertEqual(channel.area(),round(width*1000)*round(length*1000))
                        self.assertTrue((r['contact'].sized(20)-(r['diff']|r['poly'])).is_empty())
                        self.assertTrue((r['contact'].sized(20)-r['m1']).is_empty())
                        self.assertEqual({pin['pin'] for pin in c['layout_pins']},{'d','g','s','b'})
                        self.assertEqual(ref['ports'],['D','G','S','B'])

    def test_contact_pad_transition_is_continuous_on_both_sides(self):
        for target in TARGETS:
            for width in (.695,.700,.705,.995,1.,1.005):
                p,c,layers,_=fixture(self.technologies[target],target,'p',width,contract(target)['sizes'][0][1])
                r=self.regions(c,layers)
                self.assertEqual((r['diff']&r['poly']).bbox().height(),round(width*1000))
                self.assertTrue((r['contact'].sized(20)-(r['diff']|r['poly'])).is_empty())

    def test_outside_supported_dimensions_and_fractional_grid_are_rejected(self):
        for target in TARGETS:
            w,l=contract(target)['sizes'][0]
            p,c,_,_=fixture(self.technologies[target],target,'n',w,l)
            implementation=ADAPTERS[target].implementation();d=c['devices'][0]
            for name,value in [('w',w-.005),('w',10.005),('l',l-.005),('l',10.005),('w',w+.001)]:
                changed=deepcopy(d);changed['params'][name]=str(value)+'u'
                with self.subTest(target=target,name=name,value=value),self.assertRaises(ValueError):
                    implementation.specification(p['pdk'],changed)

    def test_all_four_contact_faults_change_only_the_intended_cut(self):
        for target in TARGETS:
            w,l=contract(target)['sizes'][0]
            p,c,layers,_=fixture(self.technologies[target],target,'n',w,l);saved=deepcopy(p)
            for fault,pin in [('source-open','s'),('drain-open','d'),('gate-open','g'),('body-open','b')]:
                changed=altered(p,layers,fault);other=changed['cells'][0]
                removed=[s for s in c['shapes'] if s not in other['shapes']]
                self.assertEqual(len(removed),1);self.assertEqual(removed[0]['layer'],layers['contact'])
                point=next(row['point'] for row in c['layout_pins'] if row['pin']==pin)
                self.assertTrue(polygon(removed[0]).inside(kdb().Point(*point)))
                self.assertEqual(other['devices'],c['devices']);self.assertEqual(other['layout_ports'],c['layout_ports'])
                self.assertEqual(p,saved)

    def test_dimension_faults_change_the_channel_at_small_and_large_sizes(self):
        for target in TARGETS:
            for w,l in (contract(target)['sizes'][0],contract(target)['sizes'][-1]):
                p,c,layers,_=fixture(self.technologies[target],target,'n',w,l)
                baseline=self.regions(c,layers);box=(baseline['diff']&baseline['poly']).bbox()
                for fault in ('wrong-length','wrong-width'):
                    other=altered(p,layers,fault)['cells'][0];r=self.regions(other,layers);changed=(r['diff']&r['poly']).bbox()
                    self.assertLess(changed.area(),box.area())
                    self.assertEqual(changed.height() if fault=='wrong-length' else changed.width(),box.height() if fault=='wrong-length' else box.width())
                    self.assertEqual(other['devices'],c['devices'])

    def test_body_tap_identity_survives_regeneration_and_save_reopen(self):
        from icstudio.model import save_project,load_project
        from icstudio.layout_eco import regenerate
        for target in TARGETS:
            minimum,length=contract(target)['sizes'][0]
            p,c,layers,_=fixture(self.technologies[target],target,'p',1.,length)
            def tap(cell):
                point=kdb().Point(*next(pin['point'] for pin in cell['layout_pins'] if pin['pin']=='b'))
                return next(s['id'] for s in cell['shapes'] if s['layer']==layers['diff'] and polygon(s).inside(point))
            original=tap(c);pin_ids={pin['pin']:pin['id'] for pin in c['layout_pins']}
            for width in (minimum,.7,1.):
                c['devices'][0]['params']['w']=str(width)+'u';regenerate(p,c['id'],c['devices'][0]['id'])
                self.assertEqual(tap(c),original)
                self.assertEqual({pin['pin']:pin['id'] for pin in c['layout_pins']},pin_ids)
                with tempfile.TemporaryDirectory() as td:
                    path=Path(td)/'coupon.icproj';save_project(p,path);reopened=load_project(path)
                    self.assertEqual(reopened,p)

if __name__=='__main__':unittest.main()
