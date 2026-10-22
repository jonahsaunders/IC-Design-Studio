"""Threshold recognition masks, model semantics and regeneration contracts."""
from pathlib import Path
import os
import tempfile
import unittest

from icstudio.catalog import create_device
from icstudio.layout import kdb,polygon
from icstudio.layout_eco import regenerate
from icstudio.model import clone,save_project,load_project
from icstudio.process_mos import definition,dimensions
from icstudio.sky130_layout import specification,audit
from scripts.qualify_sky130_threshold_layouts import MODELS,sizes,fixture,altered,selected,audit_native,rejected
from tests.test_sky130_devices import technology


class ThresholdLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.tech=technology()

    def region(self,p,pair):
        db=kdb();name=next(v['name'] for v in p['pdk']['layers'] if (v['gds'],v['datatype'])==pair)
        return db.Region([polygon(s) for s in p['cells'][0]['shapes'] if s['layer']==name]).merged()

    def test_all_variants_and_finger_views_keep_real_geometry_and_model_contract(self):
        for model in MODELS:
            for size in sizes(model):
                with self.subTest(model=model,size=size):
                    p=fixture(self.tech,model,size);d=p['cells'][0]['devices'][0]
                    proof=definition(p['pdk'],d);w,l,nf,copies,per_finger=size
                    self.assertEqual(proof['model'],'sky130_fd_pr__'+model)
                    self.assertEqual(proof['internal'],'msky130_fd_pr__'+model)
                    self.assertAlmostEqual(proof['effective_width']*1e6,w*(nf if per_finger else 1)*copies)
                    gates=self.region(p,(65,20))&self.region(p,(66,20))
                    implant=self.region(p,(78,44) if model.endswith('hvt') else (125,44))
                    self.assertEqual(gates.count(),nf*copies)
                    self.assertTrue((gates.sized(180)-implant).is_empty())
                    self.assertAlmostEqual(gates.area()*1e-6,w*(nf if per_finger else 1)*copies*l)
                    if model=='pfet_01v8_lvt':self.assertTrue((implant.sized(380)-self.region(p,(64,20))).is_empty())
                    self.assertFalse(audit(p,p['top']))

    def test_pmos_lvt_minimum_length_missing_masks_and_other_models_fail(self):
        p=fixture(self.tech,'pfet_01v8_lvt',sizes('pfet_01v8_lvt')[0]);d=p['cells'][0]['devices'][0]
        d['params']['l']='.345u'
        with self.assertRaisesRegex(ValueError,'0.35'):specification(p['pdk'],d)
        d['params']['l']='.35u';t=clone(self.tech);t['layers']=[v for v in t['layers'] if (v['gds'],v['datatype'])!=(125,44)]
        with self.assertRaisesRegex(ValueError,'implant'):specification(t,d)
        other=create_device(self.tech,'sky130_fd_pr/nfet_g5v0d16v0.sym','HV')
        with self.assertRaises(ValueError):specification(self.tech,other)
        with self.assertRaises(ValueError):dimensions(self.tech,other)

    def test_save_reopen_resize_preserves_implant_and_pin_identity(self):
        for model in MODELS:
            p=fixture(self.tech,model,sizes(model)[-1]);c=p['cells'][0];d=c['devices'][0]
            pins={r['pin']:r['id'] for r in c['layout_pins']}
            d['params']['w']='2u';self.assertTrue(audit(p,c['id']))
            regenerate(p,c['id'],d['id'])
            self.assertEqual(pins,{r['pin']:r['id'] for r in c['layout_pins']})
            with tempfile.TemporaryDirectory() as tmp:
                dest=Path(tmp)/'p.icproj';save_project(p,dest);q=load_project(dest)
                self.assertFalse(audit(q,q['top']))
                pair=(78,44) if model.endswith('hvt') else (125,44)
                self.assertTrue((self.region(p,pair)^self.region(q,pair)).is_empty())

    def test_physical_controls_remove_actual_contacts_and_implants(self):
        for model in MODELS:
            for size in sizes(model):
                p=fixture(self.tech,model,size)
                for fault in ('implant-missing','implant-wrong','drain-open','gate-open','body-open'):
                    q=altered(p,fault);pair=(78,44) if model.endswith('hvt') else (125,44)
                    delta=self.region(p,pair if fault.startswith('implant') else (66,44)) ^ self.region(q,pair if fault.startswith('implant') else (66,44))
                    self.assertFalse(delta.is_empty(),(model,size,fault))
                    self.assertEqual(p['cells'][0]['devices'],q['cells'][0]['devices'])

    def test_native_audit_requires_model_topology_length_and_total_width(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'native.cir';text='.subckt vt_coupon D G S B\nX0 D G S B sky130_fd_pr__nfet_01v8_lvt w=2 l=.5 m=3\n.ends\n'
            path.write_text(text);self.assertEqual(audit_native(path,MODELS[0],(1,.5,2,3,True))['total_width_um'],6)
            for wrong in (text.replace('_lvt',''),text.replace('D G S B sky','D B S G sky'),text.replace('w=2','w=3'),text.replace('l=.5','l=.6'),
                          text.replace('w=2','w=nan'),text.replace('w=2','w=2 w=2'),text.replace('w=2','w=2 q=1'),text.replace('.ends','.include extra.cir\n.ends'),
                          '.subckt vt_coupon D G S B\n.ends\n'):
                path.write_text(wrong)
                with self.assertRaises(ValueError):audit_native(path,MODELS[0],(1,.5,2,3,True))

    def test_pin_fault_requires_completed_extraction_and_native_pin_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'lvs').mkdir();log=folder/'lvs/lvs.log'
            report=dict(status='failed',stages=[dict(name=n,status='passed') for n in ('preflight','layout_export','lvs_extraction')]+[dict(name='lvs',status='failed')])
            log.write_text('Final result: Top level cell failed pin matching.')
            self.assertTrue(rejected(report,folder))
            for name in ('preflight','layout_export','lvs_extraction'):
                bad=clone(report);next(s for s in bad['stages'] if s['name']==name)['status']='failed'
                self.assertFalse(rejected(bad,folder))
            log.write_text('Tool crashed');self.assertFalse(rejected(report,folder))

    @unittest.skipUnless(os.environ.get('ICSTUDIO_TEST_NGSPICE'),'Requires actual ngspice.')
    def test_native_threshold_readouts_agree_for_total_and_per_finger_views(self):
        from icstudio import analog_characterization as library
        from icstudio.engines import run_ngspice
        from tests.test_process_mos import prepare_job,spec
        executable=os.environ['ICSTUDIO_TEST_NGSPICE']
        def prepare(s,e,p,c):return {**prepare_job(s,e,p,c),'executable':executable}
        for model in MODELS:
            measured=[]
            for per_finger in (False,True):
                p=fixture(self.tech,model,(1. if per_finger else 4.,.5,4,2,per_finger))
                s=spec();s['vgs']=['.8']
                manifest=library.prepare(p,p['top'],'M1',s,prepare);job=manifest['jobs'][0]
                with tempfile.TemporaryDirectory() as tmp:
                    result=run_ngspice(job['project'],job['cell'],job['settings'],executable,Path(tmp))
                table=library.collect(manifest,[dict(id='actual',job=job,state='Complete',result=result)])
                point=table['points'][0];self.assertEqual(point['status'],'Passed',point)
                self.assertEqual(table['width'],8e-6);measured.append(point['values'])
            for key in ('id','gm','gds','gmid','current_density'):
                self.assertAlmostEqual(measured[0][key],measured[1][key],places=10)


if __name__=='__main__':unittest.main()
