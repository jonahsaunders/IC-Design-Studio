"""Process MOS width semantics, model-vector provenance and sizing regressions."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from icstudio import analog_characterization as library
from icstudio.catalog import create_device
from icstudio.model import clone, device, example, file_digest, uid
from icstudio.process_mos import dimensions, definition, corners
from tests.test_analog_optimizer import prepare_job as prepare_base


ASSETS = Path(__file__).resolve().parents[1] / 'icstudio/assets/pdks'


def prepare_job(settings, engine, project, cid):
    # Identity-only fixture; no executable result is used as simulation evidence.
    return {**prepare_base(settings,engine,project,cid),'executable':sys.executable}


def project(family='sky130A', polarity='nfet', per_finger=False):
    root = ASSETS / family
    package = json.loads((root / 'package.json').read_text())
    p = example('empty')
    p['pdk'] = package['technology']
    p['pdk'].update(package_root=str(root), package_lock={k:package[k] for k in ('id','revision','files')})
    key = ('sky130_fd_pr/' + polarity + '_01v8' + ('_nf' if per_finger else '') + '.sym'
           if family == 'sky130A' else 'symbols/' + polarity + '_03v3.sym')
    d = create_device(p['pdk'], key, 'M1')
    d['params'].update(w='4u', l='.5u')
    d['nets'] = dict(d='d',g='g',s='0',b='0')
    p['cells'][0]['devices'] = [d]
    return p, d


def spec(**changes):
    return dict(length=['.5u'], vgs=['.8','1.0'], vds=['1.5'], vsb=[0], temperature=[27], corner=['nominal'], engine='ngspice', **changes)


class ProcessMosTests(unittest.TestCase):
    def test_standard_and_per_finger_symbols_generate_identical_channel_geometry(self):
        from icstudio.sky130_layout import mos
        from icstudio.catalog import binding_for, parameter_values
        a, da = project(); b, db = project(per_finger=True)
        da['model_params']['nf'] = 4; db['model_params']['nf'] = 4
        db['params']['w'] = '1u'
        def emitted(p,d):
            binding=binding_for(p['pdk'],d);values=parameter_values(binding,d)
            return {k:values[v] for k,v in binding['emit_parameters'].items()}
        self.assertEqual(emitted(a,da),emitted(b,db))
        ga, gb = mos(a['pdk'],da), mos(b['pdk'],db)
        self.assertEqual(ga['record']['spec']['dimensions_nm'],gb['record']['spec']['dimensions_nm'])
        def geometry(data):
            return [{k:v for k,v in s.items() if k not in ('id','device_id','generated_device','pdk_role')} for s in data['shapes']]
        self.assertEqual(geometry(ga),geometry(gb))
        self.assertEqual(ga['record']['spec']['dimensions_nm']['w'],4000)
        self.assertEqual(dimensions(b['pdk'],db)['total_width'],4e-6)

    def test_width_multiplicity_is_counted_once_and_transforms_are_validated(self):
        p,d = project(per_finger=True)
        d['params']['w']='1u'; d['model_params'].update(nf=4,mult=3)
        s=dimensions(p['pdk'],d)
        self.assertEqual(s['effective_width'],12e-6)
        self.assertEqual(s['multiplicity'],3)
        d['model_params']['emit_w']='4'
        with self.assertRaisesRegex(ValueError,'width transformation'): dimensions(p['pdk'],d)
        d['model_params'].pop('emit_w'); d['model_params']['nf']=2.5
        with self.assertRaises(ValueError): dimensions(p['pdk'],d)
        d['model_params']['nf']=4; d['model_params']['mult']=1.5
        with self.assertRaisesRegex(ValueError,'multiplicity'): dimensions(p['pdk'],d)

    def test_physical_multiplicity_remains_explicitly_rejected(self):
        from icstudio.sky130_layout import specification
        p,d=project(per_finger=True);d['model_params'].update(nf=2,mult=2)
        with self.assertRaisesRegex(ValueError,'multiplicity 1'):specification(p['pdk'],d)

    def test_gf180_units_corners_and_real_model_definition(self):
        for polarity in ('nfet','pfet'):
            p,d=project('gf180mcuD',polarity);c=definition(p['pdk'],d)
            self.assertEqual(c['internal'],'m0');self.assertEqual(c['width'],4e-6)
            self.assertIn('typical',corners(p['pdk']));self.assertNotIn('tt',corners(p['pdk']))
            binding=p['pdk']['simulation']['catalog'][d['model_ref']['device']]
            binding['parameter_scale']['w']=1e6
            with self.assertRaisesRegex(ValueError,'metre'):definition(p['pdk'],d)

    def test_gf180_physical_dimensions_reject_wrong_electrical_units(self):
        from icstudio.gf180_layout import specification
        p,d=project('gf180mcuD')
        # The D bundle lacks a C physical deck. This tests only the explicit
        # generator dimension contract, not physical process qualification.
        p['pdk']['package_lock']['id']='gf180mcuC';d['model_ref']['pdk']='gf180mcuC'
        self.assertEqual(specification(p['pdk'],d)['dimensions_nm'],{'w':4000,'l':500})
        binding=p['pdk']['simulation']['catalog'][d['model_ref']['device']]
        binding['parameter_scale']={'w':1e6,'l':1e6}
        with self.assertRaisesRegex(ValueError,'metre'):specification(p['pdk'],d)

    def test_changed_model_never_receives_a_valid_readout_contract(self):
        p,d=project('gf180mcuD');rel='libs.tech/ngspice/sm141064.ngspice'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/rel;path.parent.mkdir(parents=True);path.write_text('changed model')
            p['pdk']['package_root']=tmp
            with self.assertRaisesRegex(ValueError,'missing or changed'):definition(p['pdk'],d)
            p['pdk']['package_lock']['files'][rel]=file_digest(path)
            with self.assertRaisesRegex(ValueError,'subcircuit differs'):definition(p['pdk'],d)

    def test_gf180_characterization_rejects_absent_corner_before_preparing_jobs(self):
        p,_=project('gf180mcuD');s=spec();s['corner']=['tt'];calls=[]
        with self.assertRaisesRegex(ValueError,'do not support corners'):library.prepare(p,p['top'],'M1',s,lambda *a:calls.append(a))
        self.assertFalse(calls)
        s['corner']=['typical'];m=library.prepare(p,p['top'],'M1',s,prepare_job)
        self.assertEqual(len(m['jobs']),2)
        self.assertEqual(m['library']['identity']['adapter']['internal'],'m0')

    def test_sizing_returns_symbol_width_and_reverifies_exact_nf_m(self):
        p,d=project(per_finger=True);d['params']['w']='1u';d['model_params'].update(nf=4,mult=2)
        m=library.prepare(p,p['top'],'M1',spec(),prepare_job)
        self.assertEqual(m['library']['width'],8e-6);self.assertEqual(m['library']['width_parameter_factor'],8)
        samples=m['library']['samples'];points=[]
        for voltage,gmid in ((.8,20),(1.,10)):
            condition={k:v[0] for k,v in samples.items()};condition['vgs']=voltage
            points.append(dict(condition=condition,status='Passed',run_ids=['fixture'],values=dict(id=8e-6,gm=8e-6*gmid,current_density=1.,gmid=gmid)))
        table=dict(complete=True,width=8e-6,width_parameter_factor=8,samples=samples,points=points)
        query={k:v[0] for k,v in samples.items()}
        estimate=library.size(table,query,15,'16u')[0]
        self.assertEqual(estimate['width'],2e-6);self.assertEqual(estimate['total_width'],16e-6)
        verification=library.prepare_verification(m,estimate,prepare_job)
        actual=verification['jobs'][0]['project']['cells'][0]['devices'][0]
        self.assertEqual(actual['model_params'],d['model_params'])
        self.assertEqual(float(actual['params']['w']),2e-6)

    def test_locked_process_readouts_work_in_ordinary_repeated_hierarchy(self):
        from icstudio.operating_data import native_save,save_directive
        p,d=project('gf180mcuD');before=clone(p['pdk'])
        text,aliases=save_directive(p,p['top'])
        self.assertIn('@m.X_M1.m0[gm]',text);self.assertEqual(aliases['m.x_m1.m0'],'M1')
        child=p['cells'][0];child.update(id=uid(),name='mos_cell',ports=['d','g'],parameters={'width':'4u'})
        d['params']['w']='{width}'
        top=dict(id=p['top'],name='top',ports=[],shapes=[],devices=[device('X','X1',cell=child['id'],nets={'d':'a','g':'g1'},parameters={'width':'2u'}),device('X','X2',cell=child['id'],nets={'d':'b','g':'g2'},parameters={'width':'6u'})])
        p['cells']=[top,child]
        text,aliases=native_save(p,p['top'])
        self.assertIn('@m.X1.X_M1.m0[gm]',text);self.assertIn('@m.X2.X_M1.m0[gm]',text)
        self.assertEqual(aliases['m.x1.x_m1.m0'],'X1/M1');self.assertEqual(aliases['m.x2.x_m1.m0'],'X2/M1')
        self.assertEqual(p['pdk'],before)

    @unittest.skipUnless(os.environ.get('ICSTUDIO_TEST_NGSPICE'),'Requires an actual ngspice executable.')
    def test_real_gf180_polarities_fingers_multiplicity_and_sizing(self):
        from icstudio.engines import run_ngspice
        executable=os.environ['ICSTUDIO_TEST_NGSPICE']
        def prepare(s,e,p,c): return {**prepare_job(s,e,p,c),'executable':executable}
        for polarity in ('nfet','pfet'):
            p,d=project('gf180mcuD',polarity);d['model_params']['nf']=2
            measured=[]
            for copies in (1,3):
                d['model_params']['m']=copies;s=spec();s['vgs']=['1.0']
                m=library.prepare(p,p['top'],'M1',s,prepare);job=m['jobs'][0]
                with tempfile.TemporaryDirectory() as tmp:
                    result=run_ngspice(job['project'],job['cell'],job['settings'],executable,Path(tmp))
                table=library.collect(m,[dict(id='actual',job=job,state='Complete',result=result)])
                point=table['points'][0];self.assertEqual(point['status'],'Passed',point)
                values=point['values'];self.assertGreater(values['gmid'],0);self.assertGreater(values['gds'],0)
                self.assertGreater(values['cgg'],0);measured.append(values)
                self.assertAlmostEqual(values['current_density']*table['width'],abs(values['id']))
            self.assertAlmostEqual(abs(measured[1]['id']/measured[0]['id']),3,places=5)
            self.assertAlmostEqual(measured[1]['gmid'],measured[0]['gmid'],places=5)
            self.assertAlmostEqual(measured[1]['current_density'],measured[0]['current_density'],places=5)
            estimate=dict(width=4e-6,length=.5e-6,condition=point['condition'],desired_current=abs(values['id']),desired_gmid=values['gmid'])
            verification=library.prepare_verification(m,estimate,prepare);job=verification['jobs'][0]
            with tempfile.TemporaryDirectory() as tmp:
                result=run_ngspice(job['project'],job['cell'],job['settings'],executable,Path(tmp))
            verified=library.verification_result(verification,[dict(id='verify',job=job,state='Complete',result=result)])
            self.assertEqual(verified['state'],'Verified',verified)

    @unittest.skipUnless(os.environ.get('ICSTUDIO_TEST_NGSPICE'),'Requires an actual ngspice executable.')
    def test_real_sky130_total_and_per_finger_width_agree_with_parallel_copies(self):
        from icstudio.engines import run_ngspice
        executable=os.environ['ICSTUDIO_TEST_NGSPICE']
        def prepare(s,e,p,c):return {**prepare_job(s,e,p,c),'executable':executable}
        for polarity in ('nfet','pfet'):
            measured=[]
            for per_finger in (False,True):
                p,d=project('sky130A',polarity,per_finger)
                d['params']['w']='1u' if per_finger else '4u'
                d['model_params'].update(nf=4,mult=2)
                s=spec();s['vgs']=['.8'];m=library.prepare(p,p['top'],'M1',s,prepare);job=m['jobs'][0]
                with tempfile.TemporaryDirectory() as tmp:
                    result=run_ngspice(job['project'],job['cell'],job['settings'],executable,Path(tmp))
                table=library.collect(m,[dict(id='actual',job=job,state='Complete',result=result)])
                point=table['points'][0];self.assertEqual(point['status'],'Passed',point)
                self.assertEqual(table['width'],8e-6);measured.append(point['values'])
            for key in ('id','gm','gds','gmid','current_density'):
                self.assertAlmostEqual(measured[0][key],measured[1][key],places=10)


if __name__ == '__main__': unittest.main()
