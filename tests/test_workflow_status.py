import unittest
from icstudio.model import clone,design_digest,uid
from icstudio.test_plans import prepare
from icstudio.workflow_status import plan_status,bench_status
from tests import test_test_plans


class WorkflowStatusTests(unittest.TestCase):
    def fixture(self):
        project,plan=test_test_plans.TestPlansTests().project()
        jobs=prepare(project,plan,lambda settings,engine,project,cid:
                     dict(settings=settings,engine=engine,project=project,cell=cid))
        rows=[dict(id=uid(),name='Case',job=job,state='Complete',result={
            'project_id':project['id'],'design_hash':design_digest(job['project']),
            'specifications':[dict(name='Output',status='PASS',value=.5)]}) for job in jobs]
        return project,plan,rows

    def test_all_conditions_and_requirements_must_pass(self):
        p,plan,rows=self.fixture()
        self.assertEqual(plan_status(p,plan,rows)['status'],'Passed')
        self.assertEqual(plan_status(p,plan,rows[:2])['status'],'Blocked')
        rows[-1]['result']['specifications'][0]['status']='FAIL'
        result=plan_status(p,plan,rows)
        self.assertEqual(result['status'],'Failed');self.assertEqual(result['run_id'],rows[-1]['id'])
        self.assertEqual(result['requirement'],'Output')
        rows[-1]['result']['specifications']=[]
        self.assertEqual(plan_status(p,plan,rows)['status'],'Blocked')

    def test_new_run_and_retry_supersede_old_evidence_without_mixing_groups(self):
        p,plan,rows=self.fixture();new=clone(rows[0]);new['id']=uid();new['state']='Running';new['job']['case']['group']='new'
        self.assertEqual(plan_status(p,plan,rows+[new])['status'],'Running')
        new['state']='Complete'
        self.assertEqual(plan_status(p,plan,rows+[new])['status'],'Blocked')
        retry=clone(rows[0]);retry['id']=uid();retry['state']='Failed'
        self.assertEqual(plan_status(p,plan,rows+[retry])['status'],'Failed')
        retry['state']='Complete'
        self.assertEqual(plan_status(p,plan,rows+[retry])['status'],'Passed')

    def test_changed_inputs_missing_identity_and_foreign_results_never_pass(self):
        for mutation in ('requirements','temperature','seed','revision'):
            with self.subTest(mutation=mutation):
                p,plan,rows=self.fixture()
                if mutation=='requirements':p['cells'][0]['specifications'][0]['max']='.4'
                elif mutation=='temperature':plan['temperatures'].append(100)
                elif mutation=='seed':plan['variables']={'missing':'1'}
                else:p['revision']+=1
                self.assertNotEqual(plan_status(p,plan,rows)['status'],'Passed')
        p,plan,rows=self.fixture();rows[0]['result']['design_hash']='foreign'
        self.assertEqual(plan_status(p,plan,rows)['status'],'Blocked')
        rows[0]['job']['case']['base_design_hash']='foreign'
        self.assertEqual(plan_status(p,plan,rows)['status'],'Stale')

    def test_legacy_plan_definition_and_absent_requirements(self):
        p,plan,rows=self.fixture()
        for row in rows:row['job']['case'].pop('plan_hash')
        self.assertEqual(plan_status(p,plan,rows)['status'],'Passed')
        for row in rows:row['job']['project']['test_plans']=[]
        self.assertEqual(plan_status(p,plan,rows)['status'],'Stale')
        p,plan,rows=self.fixture();p['cells'][0]['specifications']=[]
        jobs=prepare(p,plan,lambda settings,engine,project,cid:dict(settings=settings,engine=engine,project=project,cell=cid))
        for row,job in zip(rows,jobs):
            row['job']=job;row['result']['design_hash']=design_digest(job['project'])
        self.assertEqual(plan_status(p,plan,rows)['status'],'Blocked')

    def test_cancelled_interrupted_and_missing_plan(self):
        p,plan,rows=self.fixture()
        self.assertEqual(plan_status(p,None,rows)['status'],'Not run')
        self.assertEqual(plan_status(p,plan,[])['status'],'Not run')
        for execution in ('Cancelled','Interrupted'):
            rows[0]['state']=execution
            self.assertEqual(plan_status(p,plan,rows)['status'],'Blocked')

    def test_physical_block_and_running_are_not_lost_behind_previous_pass(self):
        p,_,_=self.fixture();bench={'id':'bench','dut_cell':p['top'],'name':'Bench'}
        job=dict(project=clone(p),settings={'testbench':'bench','type':'silicon'})
        row=dict(id='run',job=job,state='Complete',result={'project_id':p['id'],'design_hash':design_digest(p),
                 'silicon_report':{'cell_id':p['top'],'status':'blocked','error':'Missing process deck'}})
        self.assertEqual(bench_status(p,bench,[row],physical=True)['status'],'Blocked')
        new={**row,'id':'new','state':'Running'}
        self.assertEqual(bench_status(p,bench,[row,new],physical=True)['status'],'Running')


if __name__=='__main__':unittest.main()
