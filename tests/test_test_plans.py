import unittest
from icstudio.model import clone, example, uid, validate
from icstudio.test_plans import prepare, matrix, compare, sources


class TestPlansTests(unittest.TestCase):
    def project(self):
        p=example('rc');c=p['cells'][0]
        c['specifications']=[dict(name='Output',expression='final(V("out"))',min='0',max='1',unit='V')]
        p['simulation_setups']=[dict(name='Transient',cell=c['id'],engine='builtin',settings=clone(p['analysis']))]
        plan=dict(id=uid(),name='Regression',entries=sources(p),corners=['nominal'],temperatures=[0,27,85],voltages=[])
        p['test_plans']=[plan];return validate(p),plan

    def jobs(self):
        p,plan=self.project()
        return prepare(p,plan,lambda settings,engine,project,cid:dict(settings=settings,engine=engine,project=project,cell=cid))

    def test_conditions_are_isolated_and_source_project_is_unchanged(self):
        p,plan=self.project();before=clone(p)
        jobs=prepare(p,plan,lambda settings,engine,project,cid:dict(settings=settings,engine=engine,project=project,cell=cid))
        self.assertEqual(p,before);self.assertEqual(len(jobs),3)
        self.assertEqual([j['settings']['temperature'] for j in jobs],[0,27,85])
        jobs[0]['project']['name']='Changed';self.assertNotEqual(jobs[1]['project']['name'],'Changed')
        plan['voltages']=[1.8]
        with self.assertRaisesRegex(ValueError,'DC supply'):prepare(p,plan,lambda *_:None)

    def test_failed_and_missing_results_remain_visible(self):
        jobs=self.jobs();rows=[dict(id=str(i),job=j,state='Complete' if i==0 else 'Failed' if i==1 else 'Queued',log='engine failed') for i,j in enumerate(jobs)]
        m=matrix(rows,jobs[0]['case']['group']);self.assertEqual(len(m['conditions']),3)
        self.assertEqual([v['status'] for v in m['rows'][0]['values'].values()],['ERROR','ERROR','QUEUED'])
        self.assertEqual(matrix(rows,None)['rows'],[])

    def test_baseline_requires_same_definition_and_condition(self):
        job=self.jobs()[0];group=job['case']['group']
        def row(value,status):return dict(id=uid(),job=clone(job),state='Complete',result={'specifications':[dict(name='Output',value=value,status=status,margin=1-value)]})
        old=matrix([row(.5,'PASS')],group);new=matrix([row(1.2,'FAIL')],group)
        cell=next(iter(compare(new,old)['rows'][0]['values'].values()))
        self.assertAlmostEqual(cell['delta'],.7);self.assertTrue(cell['regressed'])
        changed=row(1.2,'PASS');changed['job']['project']['cells'][0]['specifications'][0]['max']='2'
        cell=next(iter(compare(matrix([changed],group),old)['rows'][0]['values'].values()))
        self.assertNotIn('delta',cell)

    def test_pre_and_post_layout_measurements_and_failed_stages_are_visible(self):
        from icstudio.analog import reference
        from tests.test_silicon import technology
        p,cid,key=reference(technology());plan=dict(id='physical',name='Physical',entries=sources(p)[:1],corners=['nominal'],temperatures=[27],compare_layout=True)
        def prepare_job(settings,engine,project,cid):return dict(settings=settings,engine=engine,project=project,cell=cid,executable='local')
        job=prepare(p,plan,prepare_job)[0];self.assertEqual(job['settings']['type'],'silicon')
        stages=[dict(name=stage,status='passed',evidence={'measurements':[dict(name='output_current',status='passed',value=value)]}) for stage,value in [('schematic_simulation',50e-6),('post_layout_simulation',51e-6)]]
        stages.append(dict(name='lvs',status='failed',error='Circuit mismatch'))
        rows=[dict(id='run',state='Complete',job=job,result={'silicon_report':{'stages':stages}})]
        result=matrix(rows,job['case']['group']);by={r['name']:next(iter(r['values'].values())) for r in result['rows']}
        self.assertEqual(by['output_current · schematic']['value'],50e-6);self.assertEqual(by['output_current · post-layout']['value'],51e-6)
        self.assertEqual(by['lvs']['status'],'FAIL');self.assertEqual(by['drc']['status'],'ERROR')
