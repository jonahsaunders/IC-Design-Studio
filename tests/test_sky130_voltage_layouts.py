"""Process identification and source-backed native geometry contracts."""
import os
from pathlib import Path
import re
import tempfile
import unittest
from icstudio.catalog import create_device
from icstudio.model import clone,save_project,load_project
from icstudio.layout import kdb,polygon
from icstudio.layout_eco import regenerate
from icstudio.process_mos import definition,dimensions
from icstudio.sky130_layout import NATIVE_SIZES,specification,audit
from scripts.qualify_sky130_voltage_layouts import MODELS,NATIVE,sizes,fixture,altered
from tests.test_sky130_devices import technology

class VoltageLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.tech=technology()

    def region(self,p,pair):
        db=kdb();layer=next(v['name'] for v in p['pdk']['layers'] if (v['gds'],v['datatype'])==pair)
        return db.Region([polygon(s) for s in p['cells'][0]['shapes'] if s['layer']==layer]).merged()

    def test_native_nominal_sizes_are_exact_centers_of_locked_source_bins(self):
        for model,expected in NATIVE.items():
            path=Path(self.tech['package_root'])/'libs.ref/sky130_fd_pr/spice'/('sky130_fd_pr__'+model+'.pm3.spice')
            bins=re.findall(r'^\+ lmin = (\S+) lmax = (\S+) wmin = (\S+) wmax = (\S+)',path.read_text(),re.M)
            actual={(round((float(wmin)+float(wmax))*5e8),round((float(lmin)+float(lmax))*5e8)) for lmin,lmax,wmin,wmax in bins}
            self.assertEqual(actual,set(NATIVE_SIZES['sky130_fd_pr__'+model]))
            self.assertEqual(actual,{(round(w*1000),round(l*1000)) for w,l in expected})
            d=create_device(self.tech,'sky130_fd_pr/'+model+'.sym','M1')
            self.assertEqual(definition(self.tech,d)['model'],'sky130_fd_pr__'+model)

    def test_all_configurations_keep_channel_geometry_and_identification(self):
        for model in MODELS:
            for size in sizes(model):
                with self.subTest(model=model,size=size):
                    p=fixture(self.tech,model,size);w,l,nf,copies,per_finger=size
                    channels=self.region(p,(65,20))&self.region(p,(66,20))
                    self.assertEqual(channels.count(),nf*copies)
                    self.assertAlmostEqual(channels.area()*1e-6,w*(nf if per_finger else 1)*copies*l)
                    self.assertTrue((self.region(p,(65,20)).sized(180)-self.region(p,(75,20))).is_empty())
                    if model.startswith('nfet'):
                        self.assertTrue((self.region(p,(65,20)).sized(185)-self.region(p,(125,20))).is_empty())
                    if model in NATIVE:self.assertTrue((channels.sized(180)-self.region(p,(125,44))).is_empty())
                    if model=='nfet_03v3_nvt':self.assertTrue((channels.sized(100)-self.region(p,(81,60))).is_empty())
                    self.assertFalse(audit(p,p['top']))

    def test_missing_process_layers_and_out_of_bin_native_dimensions_reject(self):
        for model in MODELS:
            p=fixture(self.tech,model,sizes(model)[0]);d=p['cells'][0]['devices'][0]
            t=clone(self.tech);t['layers']=[v for v in t['layers'] if (v['gds'],v['datatype'])!=(75,20)]
            with self.assertRaisesRegex(ValueError,'voltage'):specification(t,d)
            d['params']['l']='.495u'
            with self.assertRaises(ValueError):specification(self.tech,d)
        for model in NATIVE:
            p=fixture(self.tech,model,sizes(model)[0]);d=p['cells'][0]['devices'][0]
            d['params']['w']='.8u'
            with self.assertRaisesRegex(ValueError,'model bin'):specification(self.tech,d)
        d=create_device(self.tech,'sky130_fd_pr/nfet_g5v0d16v0.sym','X')
        with self.assertRaises(ValueError):dimensions(self.tech,d)
        with self.assertRaisesRegex(ValueError,'one finger'):
            fixture(self.tech,'nfet_05v0_nvt',(1,25,2,1,True))

    def test_long_channel_taps_have_real_cut_stacks_and_connected_body_metal(self):
        p=fixture(self.tech,'nfet_05v0_nvt',(1,25,1,1,False));c=p['cells'][0]
        added={s['generator_role']:s for s in c['shapes'] if s.get('generator_role','').startswith('long_channel_body_')}
        self.assertEqual(set(added),{'long_channel_body_'+n for n in ('tap','psdm','licon','li','mcon','m1','rail')})
        # The gate lies between the two diffusion regions. Each end now has
        # a nearby tap, with a real contact stack to the original body terminal.
        db=kdb();tap=db.Region(polygon(added['long_channel_body_tap']))
        self.assertTrue((db.Region(polygon(added['long_channel_body_licon']))-tap).is_empty())
        for mask in ('li','mcon','m1'):
            self.assertFalse((db.Region(polygon(added['long_channel_body_'+mask]))&tap).is_empty())
        metal=self.region(p,(68,20));body=next(v['point'] for v in c['layout_pins'] if v['pin']=='b')
        connected=[s for s in metal.each() if s.inside(db.Point(*body))]
        self.assertEqual(len(connected),1)
        self.assertTrue((db.Region(polygon(added['long_channel_body_m1']))-db.Region(connected[0])).is_empty())
        broken=altered(p,'long-tap-missing');self.assertEqual(len(broken['cells'][0]['shapes']),len(c['shapes'])-7)

    def test_regeneration_preserves_pins_and_actual_mask_faults(self):
        for model in MODELS:
            p=fixture(self.tech,model,sizes(model)[-1]);c=p['cells'][0];d=c['devices'][0]
            pins={v['pin']:v['id'] for v in c['layout_pins']}
            d['params']['w']='.7u' if model in NATIVE else '2u'
            regenerate(p,c['id'],d['id']);self.assertFalse(audit(p,c['id']))
            self.assertEqual(pins,{v['pin']:v['id'] for v in c['layout_pins']})
            for fault,pair in [('oxide-missing',(75,20))]+([('native-implant-missing',(125,44))] if model in NATIVE else []):
                broken=altered(p,fault);self.assertFalse(self.region(p,pair).is_empty());self.assertTrue(self.region(broken,pair).is_empty())
                self.assertEqual(c['devices'],broken['cells'][0]['devices'])
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'voltage.icproj';save_project(p,path);q=load_project(path)
                self.assertEqual(p['cells'],q['cells']);self.assertFalse(audit(q,q['top']))

    @unittest.skipUnless(os.environ.get('ICSTUDIO_TEST_NGSPICE'),'Requires actual ngspice.')
    def test_real_operating_readouts_preserve_total_and_per_finger_width(self):
        from icstudio import analog_characterization as library
        from icstudio.engines import run_ngspice
        from tests.test_process_mos import prepare_job,spec
        executable=os.environ['ICSTUDIO_TEST_NGSPICE']
        def prepare(s,e,p,c):return {**prepare_job(s,e,p,c),'executable':executable}
        for model in MODELS:
            measured=[]
            for per_finger in (False,True):
                p=fixture(self.tech,model,(1 if per_finger else 4,.9 if model.endswith('5v0_nvt') else .5,4,2,per_finger))
                s=spec();s['vgs']=['1.5'];s['length']=[p['cells'][0]['devices'][0]['params']['l']]
                manifest=library.prepare(p,p['top'],'M1',s,prepare);job=manifest['jobs'][0]
                with tempfile.TemporaryDirectory() as tmp:result=run_ngspice(job['project'],job['cell'],job['settings'],executable,Path(tmp))
                table=library.collect(manifest,[dict(id='actual',job=job,state='Complete',result=result)])
                point=table['points'][0];self.assertEqual(point['status'],'Passed',point);self.assertEqual(table['width'],8e-6)
                measured.append(point['values'])
            for key in ('id','gm','gds','gmid','current_density'):self.assertAlmostEqual(measured[0][key],measured[1][key],places=10)

if __name__=='__main__':unittest.main()
