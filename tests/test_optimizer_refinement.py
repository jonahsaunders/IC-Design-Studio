"""Numerical and lifecycle regressions for richer device data and search."""
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from icstudio import analog_optimizer as opt,analog_adaptive as adaptive,analog_characterization as lib
from icstudio.model import clone,design_digest
from icstudio.operating_data import extras,mos_vectors
from tests.test_analog_optimizer import mos_project,setup,prepare_job,search_spec,completed
from tests.test_analog_experiments import library_spec


class DeviceDataTests(unittest.TestCase):
    def test_teaching_gds_matches_square_law_for_both_polarities(self):
        for polarity in ('NMOS','PMOS'):
            p=mos_project(polarity);m=lib.prepare(p,p['top'],'M1',library_spec(),prepare_job);table=lib.collect(m,completed(m))
            point=table['points'][-1];values=point['values'];lam=float(p['cells'][0]['devices'][0]['params']['lambda'])
            expected=abs(values['id'])*lam/(1+lam*point['condition']['vds'])
            self.assertAlmostEqual(values['gds']/expected,1,places=6)
            self.assertAlmostEqual(values['intrinsic_gain'],abs(values['gm'])/values['gds'])
            self.assertNotIn('cgg',values);self.assertNotIn('ft_estimate',values)

    def test_signed_capacitances_and_speed_contract(self):
        variables=['@m1[id]','v(@m1[gm])','@m1[gds]','@m1[cgg]','@m1[cgs]','@m1[cgd]','@m1[cgb]']
        _,_,devices=extras(variables,[[-1e-5,1e-4,1e-6,2e-15,-1.2e-15,-.5e-15,-.3e-15]],aliases={'m1':'M1'})
        p=mos_project('PMOS');point=opt.read_gmid(dict(project=p,cell=p['top']),dict(device_operating_point=devices),'M1')
        self.assertAlmostEqual(point['intrinsic_gain'],100);self.assertEqual(point['cgs'],-1.2e-15)
        self.assertAlmostEqual(point['ft_estimate']/(1e-4/(2*math.pi*2e-15)),1)
        self.assertNotIn('intrinsic_gain',opt.device_metrics(dict(gm=1,gds=0,cgg=-1)))
        self.assertFalse(any('[cgg]' in v for v in mos_vectors('M1','M1',{},{})))
        self.assertTrue(any('[cgg]' in v for v in mos_vectors('X1','M1',dict(operating_point_device='mcore',characterization_capacitances=True),{})))

    def test_interpolation_never_partially_invents_missing_capacitance(self):
        p=mos_project();m=lib.prepare(p,p['top'],'M1',library_spec(),prepare_job);table=lib.collect(m,completed(m))
        for point in table['points']:point['values']['cgg']=2e-15
        query=dict(length=.75e-6,vgs=.6,vds=1.4,vsb=0,temperature=27,corner='nominal')
        self.assertIn('ft_estimate',lib.interpolate(table,query))
        table['points'][0]['values'].pop('cgg')
        interpolated=lib.interpolate(table,query)
        self.assertNotIn('cgg',interpolated);self.assertNotIn('ft_estimate',interpolated)
        self.assertIn('intrinsic_gain',interpolated)

    def test_sizing_verification_is_separate_spice_snapshot_with_real_dimensions(self):
        p=mos_project();before=clone(p);m=lib.prepare(p,p['top'],'M1',library_spec(),prepare_job);table=lib.collect(m,completed(m))
        query=dict(length=1e-6,vds=1.8,vsb=0,temperature=27,corner='nominal')
        estimate=lib.size(table,query,10,'10u')[0]
        # Unit test inspects construction; real executable qualification is separate.
        with patch('icstudio.run_environment.stamp',return_value={'engine':'ngspice','executable_sha256':'test'}):
            verification=lib.prepare_verification(m,estimate,prepare_job)
        self.assertEqual(p,before);job=verification['jobs'][0];self.assertEqual(job['engine'],'ngspice')
        device=job['project']['cells'][0]['devices'][0];self.assertEqual(float(device['params']['w']),estimate['width'])
        rows=completed(verification)
        rows[0]['result'].update(engine='ngspice (test result)',engine_hash='test')
        result=lib.verification_result(verification,rows)
        self.assertIn(result['state'],('Verified','Outside tolerance'))
        rows[0]['result']['device_operating_point']['MCHAR']['id']*=2
        self.assertEqual(lib.verification_result(verification,rows)['state'],'Outside tolerance')
        rows[0]['result']['design_hash']='wrong'
        self.assertEqual(lib.verification_result(verification,rows)['state'],'Failed')


class SearchTests(unittest.TestCase):
    def setUp(self):self.p=mos_project();self.plan=opt.source_plan(setup(self.p));self.spec=search_spec()
    def prepare(self):return opt.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job)

    def test_eight_axes_do_not_materialize_cartesian_product(self):
        self.p['parameters']={f'p{i}':'1' for i in range(8)}
        self.spec.update(strategy='adaptive',budget=30,axes=[dict(target='@p'+str(i),lower=.5,upper=2,count=500) for i in range(8)])
        m=self.prepare();self.assertLessEqual(len(m['jobs']),17);self.assertEqual(len(m['adaptive']['coordinates'][0]),8)
        self.assertEqual(m['adaptive']['max_candidates'],30)
        self.spec['strategy']='grid'
        with self.assertRaisesRegex(ValueError,'500'):self.prepare()

    def test_log_and_integer_domains_and_linked_fingers(self):
        values=opt.axis_values(dict(lower='1n',upper='1u',count=4,scale='log'))
        for a,b in zip(values,(1e-9,1e-8,1e-7,1e-6)):self.assertAlmostEqual(a/b,1)
        self.assertEqual(opt.axis_values(dict(lower=1,upper=4,count=10,scale='integer')),[1,2,3,4])
        for axis in (dict(lower=0,upper=10,count=3,scale='log'),dict(lower=.5,upper=4,count=3,scale='integer')):
            with self.assertRaises(ValueError):opt.axis_values(axis)
        self.p['parameters']={'nf':'1'}
        self.spec['axes']=[dict(target='@nf',lower=1,upper=4,count=4,scale='integer')]
        self.assertEqual([j['case']['changes']['@nf'] for j in self.prepare()['jobs']],[1,2,3,4])

    def test_joint_moves_batches_and_replay_stay_inside_budget(self):
        self.spec.update(strategy='adaptive',budget=11,batch_size=3,axes=[dict(target='VG.value',lower=.6,upper=1,count=11),dict(target='VD.value',lower=1,upper=2.6,count=11)])
        m=self.prepare();rows=completed(m);next_m,batch=adaptive.advance(m,rows,prepare_job)
        self.assertEqual(len(batch),3)
        center=m['adaptive']['coordinates'][0];proposal=next_m['adaptive']['coordinates'][5]
        self.assertEqual(sum(a!=b for a,b in zip(center,proposal)),2)
        again,_=adaptive.advance(clone(m),clone(rows),prepare_job);self.assertEqual(again['adaptive']['coordinates'],next_m['adaptive']['coordinates'])
        while not opt.evaluate(next_m,completed(next_m))['complete']:next_m,_=adaptive.advance(next_m,completed(next_m),prepare_job)
        self.assertEqual(len(next_m['jobs']),11);self.assertEqual(len(set(map(tuple,next_m['adaptive']['coordinates']))),11)

    def test_catalog_finger_counts_use_declared_model_parameters(self):
        import json
        from icstudio.catalog import create_device,parameter_values,binding_for
        from icstudio.model import example
        root=Path(__file__).resolve().parents[1]/'icstudio/assets/pdks/sky130A';package=json.loads((root/'package.json').read_text())
        p=example('empty');p['pdk']=clone(package['technology']);p['pdk'].update(package_root=str(root),package_lock={k:package[k] for k in ('id','revision','files')})
        d=create_device(p['pdk'],'sky130_fd_pr/nfet_01v8.sym','M1');p['cells'][0]['devices']=[d]
        self.assertIn('M1.model_params.nf',opt.targets(p,p['top']))
        axis=dict(target='M1.model_params.nf',lower=1,upper=4,count=4,scale='integer')
        self.assertEqual(len(opt.grid(p,p['top'],[axis])),4)
        opt.set_target(p,p['top'],'M1.model_params.nf',3)
        self.assertEqual(parameter_values(binding_for(p['pdk'],d),d)['nf'],3)
        axis['count']=5;axis['scale']='linear'
        with self.assertRaisesRegex(ValueError,'positive integers'):opt.grid(p,p['top'],[axis])

    def test_screening_saves_expensive_runs_and_never_passes_partial_results(self):
        self.p['cells'][0]['specifications']=[dict(name='Gate minimum',expression='final(V("g"))',min='.7',unit='V')]
        self.plan['entries'].append({**clone(self.plan['entries'][0]),'id':'tran','name':'Transient','settings':{**self.p['analysis'],'type':'tran','stop':'1u','step':'1u'}})
        self.spec['screen_op']=True;m=self.prepare();ready=opt.ready_jobs(m,[])
        self.assertEqual(len(ready),3);self.assertTrue(all(j['settings']['type']=='op' for j in ready))
        rows=completed({**m,'jobs':ready});report=opt.evaluate(m,rows)
        self.assertEqual(report['skipped'],1);self.assertFalse(report['complete']);self.assertEqual(report['candidates'][0]['state'],'Screened out')
        with self.assertRaises(ValueError):opt.apply_candidate(self.p,m,rows,2)
        ready=opt.ready_jobs(m,rows);self.assertEqual(len(ready),2);self.assertTrue(all(j['settings']['type']=='tran' for j in ready))
        rows+=completed({**m,'jobs':ready});report=opt.evaluate(m,rows)
        self.assertTrue(report['complete']);self.assertEqual(report['terminal'],5);self.assertEqual(report['best']['candidate'],2)
        self.assertFalse(opt.ready_jobs(m,rows))
        with self.assertRaises(ValueError):opt.apply_candidate(self.p,m,rows,1)

    def test_interrupted_screening_can_resume_without_running_expensive_tests(self):
        self.plan['entries'].append({**clone(self.plan['entries'][0]),'id':'ac','settings':{**self.p['analysis'],'type':'ac'}})
        self.spec['screen_op']=True;m=self.prepare();rows=completed({**m,'jobs':opt.ready_jobs(m,[])})
        for row in rows:row['state']='Interrupted'
        self.assertFalse(opt.ready_jobs(m,rows));self.assertFalse(opt.evaluate(m,rows)['complete'])
        from icstudio.variation_runs import pending
        self.assertTrue(all(j['settings']['type']=='op' for j in opt.eligible_jobs(m,pending(m,rows),rows)))

    def test_surrogate_reproducibility_no_unsimulated_pass_and_budget(self):
        self.spec.update(strategy='surrogate',budget=12,batch_size=2);self.spec['axes'][0]['count']=101
        m=self.prepare();rows=completed(m);a,_=adaptive.advance(m,rows,prepare_job);b,_=adaptive.advance(m,rows,prepare_job)
        self.assertEqual(a['adaptive']['coordinates'],b['adaptive']['coordinates'])
        self.assertTrue(all(c['state']=='Pending' for c in opt.evaluate(a,rows)['candidates'][3:]))
        while not opt.evaluate(a,completed(a))['complete']:a,_=adaptive.advance(a,completed(a),prepare_job)
        self.assertEqual(len(a['jobs']),12)
        from icstudio.analog_surrogate import GaussianProcess
        gp=GaussianProcess([[0],[.5],[1]],[0,1,0]);mean,uncertainty=gp.predict([.5])
        self.assertAlmostEqual(mean,1,places=4);self.assertLess(uncertainty,.01)


if __name__=='__main__':unittest.main()
