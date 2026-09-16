import unittest,os,tempfile
from pathlib import Path
from icstudio.model import example,clone,device,uid,validate,design_digest
from icstudio.analog_debug import contexts,operating_rows,comparison_rows,convergence_hints


def hierarchy():
    p=example('empty');top=p['cells'][0]
    child=dict(id=uid(),name='unit',ports=['p','n'],devices=[device('R','R1',nets={'p':'p','n':'local'})],shapes=[])
    p['cells'].append(child)
    top['devices']=[device('X','X1',cell=child['id'],nets={'p':'a','n':'0'}),device('X','X2',cell=child['id'],nets={'p':'b','n':'0'})]
    return p,child


class AnalogEvidenceTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('ICSTUDIO_TEST_NGSPICE'),'Set ICSTUDIO_TEST_NGSPICE for real engine qualification.')
    def test_real_ngspice_distinguishes_repeated_mos_instances(self):
        from icstudio.engines import run_ngspice
        p,child=hierarchy();p['spice']={'version':1,'assets':{}}
        child['devices']=[device('NMOS','M1',nets={'d':'p','g':'p','s':'n','b':'n'})]
        p['cells'][0]['devices'] += [device('V','V1',value='1',nets={'p':'a','n':'0'}),device('V','V2',value='1.5',nets={'p':'b','n':'0'})]
        validate(p)
        with tempfile.TemporaryDirectory() as directory:
            result=run_ngspice(p,p['top'],{**p['analysis'],'type':'op'},os.environ['ICSTUDIO_TEST_NGSPICE'],Path(directory))
        values=result['device_operating_point'];self.assertGreater(values['X2/M1']['id'],values['X1/M1']['id'])
        self.assertAlmostEqual(values['X1/M1']['vgs'],1);self.assertAlmostEqual(values['X2/M1']['vgs'],1.5)

    def test_repeated_master_never_uses_other_instance_bias(self):
        from icstudio.annotations import readouts
        p,child=hierarchy();r=dict(project_id=p['id'],cell_id=p['top'],design_hash=design_digest(p),operating_point={'a':1,'b':2,'X1/local':.1,'X2/local':.2},operating_currents={'X1/R1':.001,'X2/R1':.002})
        rows=operating_rows(p,p['top'],r)
        self.assertEqual([row['voltages']['p'] for row in rows],[1,2])
        self.assertEqual([row['values']['current'] for row in rows],[.001,.002])
        self.assertFalse(readouts(p,child['id'],r)[0])
        selected=readouts(p,child['id'],r,instance_path='X2/')[0][child['devices'][0]['id']]
        self.assertIn('p 2 V',selected);self.assertIn('I 0.002 A',selected)

    def test_native_hierarchy_saves_exact_instance_vectors(self):
        from icstudio.operating_data import native_save,extras
        p,child=hierarchy();child['devices']=[device('NMOS','M1',nets={'d':'p','g':'local','s':'n','b':'n'})]
        directive,aliases=native_save(p,p['top'])
        self.assertIn('@M.X1.M1[gm]',directive);self.assertIn('@M.X2.M1[gm]',directive)
        self.assertEqual(aliases['v:x2.local'],'X2/local')
        values=extras(['@m.x1.m1[gm]','@m.x2.m1[gm]'],[[.001,.002]],aliases=aliases)[2]
        self.assertEqual(values['X1/M1']['gm'],.001);self.assertEqual(values['X2/M1']['gm'],.002)

    def test_model_internal_path_requires_explicit_safe_metadata(self):
        from icstudio.operating_data import mos_vectors
        aliases={}
        self.assertEqual(mos_vectors('X1','DUT',{},aliases),[])
        vectors=mos_vectors('X1','DUT',{'operating_point_device':'xcore.mdevice'},aliases)
        self.assertIn('@m.X1.xcore.mdevice[gm]',vectors)
        self.assertEqual(aliases['m.x1.xcore.mdevice'],'DUT')
        for text in ('m1\n.control','../m1','m1[gm]'):
            with self.assertRaises(ValueError):mos_vectors('X1','DUT',{'operating_point_device':text},{})

    def test_comparison_joins_by_name_and_preserves_failures_and_missing(self):
        before=[dict(name='gain',value=4,unit='V/V',status='PASS'),dict(name='delay',value=2,unit='s',status='PASS')]
        after=[dict(name='delay',value=3,unit='s',status='FAIL'),dict(name='gain',value=5,unit='dB',status='PASS'),dict(name='new',value=1,unit='V',status='PASS')]
        rows=comparison_rows({'stages':[dict(name='schematic_simulation',evidence={'specifications':before}),dict(name='post_layout_simulation',evidence={'specifications':after})]})
        self.assertIsNone(rows[0]['delta']);self.assertEqual(rows[1]['delta'],1);self.assertEqual(rows[1]['after_status'],'FAIL');self.assertEqual(rows[2]['before_status'],'NOT RUN')

    def test_convergence_hints_keep_diagnostics_specific(self):
        self.assertEqual(convergence_hints('all done'),[])
        hints=convergence_hints('singular matrix: check node gate; timestep too small')
        self.assertEqual(len(hints),2);self.assertIn('DC path',hints[0]['detail'])


class AnalogLayoutTests(unittest.TestCase):
    def mos(self):
        p=example('empty');d=device('NMOS','M1',nets={'d':'d','g':'g','s':'s','b':'b'});d['params'].update(w='8u',l='1u');p['cells'][0]['devices']=[d]
        return p,d

    def test_mos_array_preserves_electrical_width_and_stable_ids(self):
        from icstudio.parametric import install,audit
        from icstudio.analog_constraints import move_device
        p,d=self.mos();before=clone(d);cid=p['top'];spec=dict(fingers=4,contact_rows=3,dummies=1,guard=True)
        record=install(p,cid,d['id'],spec);validate(p)
        self.assertEqual(record['electrical']['width_nm'],8000);self.assertEqual(d,before)
        c=p['cells'][0];ids={s['pcell_role']:s['id'] for s in c['shapes']};pins={s['pin']:s['id'] for s in c['layout_pins']}
        self.assertTrue(any(k.startswith('guard_') for k in ids));self.assertEqual(set(pins),{'d','g','s','b'})
        self.assertFalse(audit(p,cid));move_device(p,cid,d['id'],10000,20000)
        install(p,cid,d['id'],record['spec']);self.assertEqual(ids,{s['pcell_role']:s['id'] for s in c['shapes']});self.assertEqual(pins,{s['pin']:s['id'] for s in c['layout_pins']})
        from icstudio.physical import connectivity
        self.assertFalse(connectivity(p,cid)['issues'])

    def test_invalid_mos_sizing_does_not_silently_round(self):
        from icstudio.parametric import build
        p,d=self.mos()
        for spec in (dict(fingers=3),dict(fingers=2.5),dict(contact_rows=32),dict(dummies=-1)):
            with self.assertRaises(ValueError):build(p,p['top'],d['id'],spec)

    def test_isolated_fingers_have_distinct_active_regions(self):
        from icstudio.parametric import build
        p,d=self.mos();data=build(p,p['top'],d['id'],dict(fingers=4,diffusion='isolated'))
        active=[s for s in data['shapes'] if s['pcell_role'].startswith('active')]
        self.assertEqual(len(active),4);self.assertEqual(data['record']['electrical']['width_nm'],8000)

    def centroid(self):
        from icstudio.parametric import install
        p=example('empty');c=p['cells'][0];c['devices']=[device('R','R'+str(i),value='100') for i in range(10)]
        for i,d in enumerate(c['devices']):install(p,c['id'],d['id'],dict(x=i*5000,width=1000))
        ids=[d['id'] for d in c['devices']];row=dict(kind='common_centroid',members=ids,groups=[ids[:2],ids[2:6],ids[6:]],name='2:4:4');c['analog_constraints']=[row]
        return p,row

    def test_unequal_three_group_2d_centroid(self):
        from icstudio.analog_constraints import arrange,findings,footprint
        p,row=self.centroid();arrange(p,p['top'],row,pitch=5000,columns=4)
        self.assertFalse(findings(p,p['top']));self.assertGreater(len({footprint(p,p['top'],i)[2][1] for i in row['members']}),1)

    def test_failed_placement_is_atomic(self):
        from icstudio.analog_constraints import arrange
        p,row=self.centroid();before=clone(p)
        with self.assertRaisesRegex(ValueError,'overlap'):arrange(p,p['top'],row,pitch=10,columns=4)
        self.assertEqual(p,before)
        row['groups'][1][0]=row['groups'][0][0]
        with self.assertRaises(ValueError):arrange(p,p['top'],row,columns=4)


class AnalogSetupTests(unittest.TestCase):
    def test_overrides_are_validated_and_only_touch_run_snapshot(self):
        from icstudio.test_plans import prepare,sources,validate_plans
        p=example('rc');p['parameters']={'load':'10k'};p['cells'][0]['devices'][1]['value']='{load}'
        p['simulation_setups']=[dict(name='Transient',cell=p['top'],engine='builtin',settings=p['analysis'])]
        plan=dict(id='plan',name='Plan',entries=sources(p),corners=['nominal'],temperatures=[27],voltages=[],variables={'load':'20k'})
        before=clone(p)
        jobs=prepare(p,plan,lambda settings,engine,project,cid:dict(settings=settings,engine=engine,project=project,cell=cid))
        self.assertEqual(p,before);self.assertEqual(jobs[0]['project']['parameters']['load'],'20k')
        plan['variables']={'missing':'2'}
        with self.assertRaises(ValueError):validate_plans({**p,'test_plans':[plan]})

    def test_duplicate_assignment_is_an_error(self):
        from icstudio.analog_workspace import assignments
        with self.assertRaises(ValueError):assignments('a=1\na=2')
        self.assertEqual(assignments('a = 1\nb = {a*2}'),{'a':'1','b':'{a*2}'})


if __name__=='__main__':unittest.main()
