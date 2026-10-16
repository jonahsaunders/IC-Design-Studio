"""Physical negative controls must alter the intended device geometry."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from icstudio.layout import kdb,polygon
from scripts.qualify_standard_mos import PROFILES,GEOMETRIES,load_technology
from scripts.qualify_standard_mos_layout import altered,fault_detected,fixture


class StandardMosLayoutQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.technologies={target:load_technology(target)[0] for target in PROFILES}

    def region(self,p,layer):
        region=kdb().Region()
        for shape in p['cells'][0]['shapes']:
            if shape['layer']==layer:region.insert(polygon(shape))
        return region.merged()

    def test_length_control_changes_channel_even_when_contact_pad_is_narrower(self):
        for target,tech in self.technologies.items():
            for polarity in ('n','p'):
                for shape in GEOMETRIES[:-1]:
                    with self.subTest(target=target,polarity=polarity,geometry=shape):
                        p,c,layers=fixture(tech,target,polarity,shape)
                        changed=altered(p,layers,'wrong-length')
                        before=self.region(p,layers['poly']) & self.region(p,layers['diff'])
                        after=self.region(changed,layers['poly']) & self.region(changed,layers['diff'])
                        self.assertEqual(after.bbox().width(),before.bbox().width()+50)
                        self.assertEqual(after.bbox().height(),before.bbox().height())
                        self.assertEqual(after.area()-before.area(),50*before.bbox().height())
                        self.assertEqual(c['devices'],changed['cells'][0]['devices'])
                        self.assertEqual(c['layout_pins'],changed['cells'][0]['layout_pins'])
                        for layer in {s['layer'] for s in c['shapes']} - {layers['poly']}:
                            self.assertTrue((self.region(p,layer)^self.region(changed,layer)).is_empty())

    def test_open_control_removes_drain_cuts_without_altering_other_layers(self):
        for target,tech in self.technologies.items():
            p,c,layers=fixture(tech,target,'n','interior');changed=altered(p,layers,'drain-open')
            cuts={layers[k] for k in ('contact','licon','mcon') if k in layers}
            for layer in {s['layer'] for s in c['shapes']}:
                delta=self.region(p,layer)^self.region(changed,layer)
                with self.subTest(target=target,layer=layer):
                    self.assertEqual(delta.is_empty(),layer not in cuts)
            self.assertEqual(c['devices'],changed['cells'][0]['devices'])
            self.assertEqual(c['layout_pins'],changed['cells'][0]['layout_pins'])

    def test_short_control_connects_gate_and_drain_metal(self):
        db=kdb()
        for target,tech in self.technologies.items():
            p,c,layers=fixture(tech,target,'p','interior');changed=altered(p,layers,'gate-drain-short')
            points={r['pin']:db.Point(*r['point']) for r in c['layout_pins']}
            def connected(project):
                return any(poly.inside(points['d']) and poly.inside(points['g'])
                    for poly in self.region(project,layers['m1']).each())
            with self.subTest(target=target):
                self.assertFalse(connected(p));self.assertTrue(connected(changed))

    def test_generator_rejects_outside_dimensions_and_off_grid_values(self):
        from icstudio.process_adapters import ADAPTERS
        bounds={'sky130A':(.42,30,.15,10),'gf180mcuC':(1,10,.28,2),
            'gf180mcuD':(1,10,.28,2),'ihp-sg13g2':(1,10,.13,2)}
        for target,tech in self.technologies.items():
            p,c,_=fixture(tech,target,'n','interior');d=c['devices'][0]
            wmin,wmax,lmin,lmax=bounds[target]
            for key,value in [('w',wmin-.005),('w',wmax+.005),('l',lmin-.005),
                ('l',lmax+.005),('w',wmin+.001),('l',lmin+.001)]:
                changed=deepcopy(d);changed['params'][key]=str(value)+'u'
                with self.subTest(target=target,parameter=key,value=value),self.assertRaises(ValueError):
                    ADAPTERS[target].implementation().specification(p['pdk'],changed)

    def test_native_mismatch_required_and_setup_failures_do_not_count(self):
        report={'status':'failed','stages':[{'name':key,'status':status} for key,status in
            [('preflight','passed'),('layout_export','passed'),('lvs_extraction','passed'),('lvs','failed')]]}
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'lvs-extraction').mkdir();(folder/'lvs').mkdir()
            (folder/'lvs/lvs.log').write_text('Netlists do not match.')
            self.assertFalse(fault_detected(report,folder))
            (folder/'lvs-extraction/extracted.spice').write_text('.subckt coupon D G S B\n.ends\n')
            self.assertTrue(fault_detected(report,folder))
            (folder/'lvs/lvs.log').write_text('Could not load verification tool.')
            self.assertFalse(fault_detected(report,folder))
            (folder/'lvs/lvs.log').write_text('Netlists do not match.')
            for stage in ('preflight','layout_export'):
                changed=deepcopy(report)
                next(r for r in changed['stages'] if r['name']==stage)['status']='failed'
                self.assertFalse(fault_detected(changed,folder))
            changed=deepcopy(report);changed['status']='passed'
            self.assertFalse(fault_detected(changed,folder))


if __name__=='__main__':unittest.main()
