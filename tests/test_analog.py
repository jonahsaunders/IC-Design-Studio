import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.model import clone, validate, History, digest, design_digest
from icstudio.analog import reference
from icstudio.characterization import prepared_cases, run, read_case, csv_text
from icstudio.testbenches import measure, spice_testbench
from icstudio.process_adapters import capabilities, adapter, audit
from icstudio.physical_cells import transform_selection, ports, terminals
from icstudio.sky130_layout import generate_inverter, reference_project
from test_silicon import technology


class AnalogTests(unittest.TestCase):
    def test_recipe_identity_body_units_and_roundtrip(self):
        for kind in ('current_mirror','differential_pair'):
            p,cid,key=reference(technology(),kind)
            c=next(c for c in p['cells'] if c['id']==cid)
            self.assertEqual(len(c['devices']),2)
            self.assertTrue(all(d['nets']['b']=='VSS' and d['params']['w']=='10u' and d['params']['l']=='1u' for d in c['devices']))
            self.assertEqual(set(c['symbol']['pins']),set(c['ports']))
            self.assertEqual(len(p['testbenches']),2)
            self.assertEqual(validate(json.loads(json.dumps(p))),p)

    def test_generic_and_missing_models_rejected(self):
        t=technology();t['package_lock']['id']='unknown'
        with self.assertRaises(ValueError):reference(t)
        t=technology();t['simulation']['catalog']={}
        with self.assertRaises(ValueError):reference(t)

    def test_current_and_differential_signed_measurements(self):
        p,_,_=reference(technology(),'current_mirror');t=p['testbenches'][0]
        r={'x':[0],'traces':{'ref':[.7]},'currents':{'vsense':[51e-6]}}
        rows=measure(r,t)['measurements'];self.assertEqual(rows[0]['unit'],'A');self.assertEqual(rows[0]['status'],'passed')
        r['currents']['vsense']=[-51e-6];self.assertEqual(measure(r,t)['status'],'failed')
        p,_,_=reference(technology(),'differential_pair');t=p['testbenches'][0]
        r={'x':[0],'traces':{'outp':[1.2],'outn':[1.4]}}
        self.assertAlmostEqual(measure(r,t)['measurements'][0]['value'],-.2)

    def test_ac_difference_uses_complex_phases(self):
        t={'analysis':{'type':'ac'},'probes':['a','b'],'measurements':[{'name':'difference','kind':'voltage','node':'a','reference':'b'}]}
        r={'x':[10,100],'traces':{'a':[1,1],'b':[1,1]},'phase':{'a':[0,0],'b':[180,180]}}
        self.assertAlmostEqual(measure(r,t)['measurements'][0]['value'],2)

    def test_current_interpolates_descending_dc_and_rejects_nonfinite(self):
        t={'analysis':{'type':'dc'},'probes':['a'],'measurements':[{'name':'current','kind':'current','source':'VSENSE','at':'.5'}]}
        r={'x':[1,0],'traces':{},'currents':{'vsense':[2e-6,0]}}
        self.assertAlmostEqual(measure(r,t)['measurements'][0]['value'],1e-6)
        r['currents']['vsense']=[float('nan'),0];self.assertEqual(measure(r,t)['status'],'failed')

    def test_saved_current_source_and_reference_are_validated(self):
        p,_,_=reference(technology())
        p['testbenches'][0]['measurements'][0]['source']='NOPE'
        with self.assertRaisesRegex(ValueError,'voltage source'):validate(p)
        p,_,_=reference(technology(),'differential_pair')
        p['testbenches'][0]['measurements'][0]['reference']='unknown'
        with self.assertRaisesRegex(ValueError,'reference'):validate(p)

    def test_spec_preflight_uses_fixture_and_preserves_source(self):
        p,_,_=reference(technology());t=p['testbenches'][0];before=clone(p)
        jobs=prepared_cases(p,t,t['characterization'])
        self.assertEqual(len(jobs),3);self.assertEqual(p,before)
        for labels,changes,sample,bench in jobs:
            fixture=next(c for c in sample['cells'] if c['id']==t['bench_cell'])
            self.assertEqual(float(next(d for d in fixture['devices'] if d['name']=='VOUT')['value']),labels['value'])
            self.assertEqual(bench['analysis']['type'],'op')
        with self.assertRaisesRegex(ValueError,'Target device'):prepared_cases(p,t,{'kind':'sweep','target':'MREF.params.w','values':['1u']})

    def test_pvt_updates_saved_bench_and_seeded_tolerances(self):
        p,_,_=reference(technology(),'differential_pair');t=p['testbenches'][1]
        jobs=prepared_cases(p,t,t['characterization']);self.assertEqual([b['analysis']['temperature'] for _,_,_,b in jobs],[0,27,85]);self.assertEqual([b['analysis']['type'] for _,_,_,b in jobs],['dc']*3)
        s={'kind':'monte_carlo','count':3,'seed':12,'variations':[{'target':'RL1.value','relative_sigma':.05}]}
        first=prepared_cases(p,t,s);second=prepared_cases(p,t,s)
        self.assertEqual([j[1] for j in first],[j[1] for j in second]);self.assertNotEqual(first[0][1],first[1][1])

    def test_failed_cases_are_retained_and_evidence_checked(self):
        p,_,_=reference(technology());t=p['testbenches'][0];count=[0]
        def simulated(sample,bench,exe,work,progress):
            count[0]+=1
            if count[0]==2:raise RuntimeError('deliberate engine failure')
            r={'project_id':sample['id'],'cell_id':bench['bench_cell'],'design_hash':design_digest(sample),'engine_hash':'test', 'measurements':{'status':'passed','measurements':[{'name':'output_current','unit':'A','value':50e-6,'status':'passed'}]},'x':[0],'traces':{'ref':[.7]}}
            (work/'result.json').write_text(json.dumps(r));return r
        with tempfile.TemporaryDirectory() as tmp,patch('icstudio.characterization.simulate',simulated):
            r=run(p,t['id'],t['characterization'],'fake',Path(tmp)/'study')
            self.assertEqual(r['summary'],{'runs':3,'passed':2,'failed':1});self.assertEqual(r['status'],'failed')
            self.assertEqual(r['design_hash'],design_digest(p));self.assertEqual(r['cell_id'],t['bench_cell'])
            self.assertEqual(read_case(r,0)['traces'],{'ref':[.7]})
            with self.assertRaisesRegex(ValueError,'deliberate'):read_case(r,1)
            self.assertIn('deliberate engine failure',csv_text(r))
            path=Path(r['evidence_directory'])/r['characterization_rows'][0]['result_file'];path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'missing or changed'):read_case(r,0)

    def test_measurement_failure_is_not_a_success(self):
        p,_,_=reference(technology());t=p['testbenches'][0]
        def simulated(sample,bench,exe,work,progress):
            r={'engine_hash':'test','measurements':{'status':'failed','measurements':[{'name':'output_current','unit':'A','value':1,'status':'failed','error':'over limit'}]}}
            (work/'result.json').write_text(json.dumps(r));return r
        with tempfile.TemporaryDirectory() as tmp,patch('icstudio.characterization.simulate',simulated):
            r=run(p,t['id'],t['characterization'],'fake',Path(tmp)/'study')
            self.assertEqual(r['summary']['failed'],3);self.assertIn('over limit',csv_text(r))

    def test_no_measurements_and_nonempty_output_rejected(self):
        p,_,_=reference(technology());t=p['testbenches'][0]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'keep').write_text('existing')
            with self.assertRaisesRegex(ValueError,'empty'):run(p,t['id'],t['characterization'],'fake',tmp)
        t['measurements']=[]
        with self.assertRaisesRegex(ValueError,'at least one'):prepared_cases(p,t,t['characterization'])

    def test_annotations_transform_once_with_undo_and_partial_rejection(self):
        p,cid=reference_project(technology());generate_inverter(p,cid);c=next(c for c in p['cells'] if c['id']==cid);ids=[s['id'] for s in c['shapes']];before=clone(p);history=History(p)
        history.commit(lambda q:transform_selection(q,cid,ids,1000,2000,90,False,include_annotations=True),'Move complete layout')
        after=next(c for c in history.project['cells'] if c['id']==cid)
        for old,new in zip(c['layout_ports'],after['layout_ports']):self.assertEqual(new['point'],[1000-old['point'][1],2000+old['point'][0]])
        for old,new in zip(c['layout_pins'],after['layout_pins']):self.assertEqual(new['point'],[1000-old['point'][1],2000+old['point'][0]])
        for old,new in zip(c['layout_texts'],after['layout_texts']):self.assertEqual([new['x'],new['y']],[1000-old['y'],2000+old['x']])
        history.undo();self.assertEqual(history.project['cells'],before['cells']);history.redo();self.assertEqual(history.project['cells'][1],after)
        with self.assertRaisesRegex(ValueError,'Select all'):transform_selection(p,cid,ids[:1],1000,0,include_annotations=True)
        self.assertEqual(p,before)

    def test_capabilities_do_not_trust_catalog_or_metadata(self):
        t=technology();c=capabilities(t);self.assertEqual(c['native_layout'],['mos','inverter','ring','current_mirror']);self.assertIn('No release',c['physical_evidence'])
        t['package_lock']['id']='ihp-sg13g2';t['physical']={'native_generators':['pretend']}
        self.assertEqual(capabilities(t)['native_layout'],[])
        with self.assertRaisesRegex(ValueError,'not implemented'):adapter(t)
        t=technology();t['layers']=[];self.assertFalse(capabilities(t)['native_layout'])

    def test_physical_assets_require_lock(self):
        t=technology()
        with self.assertRaisesRegex(ValueError,'absent from the PDK lock'):adapter(t).engine_assets(t)

    def test_current_source_uses_emitted_spice_name(self):
        p,_,_=reference(technology());t=p['testbenches'][0]
        fixture=next(c for c in p['cells'] if c['id']==t['bench_cell']);next(d for d in fixture['devices'] if d['name']=='VSENSE')['name']='sense'
        for bench in p['testbenches']:bench['measurements'][0]['source']='sense'
        self.assertIn('i(V_sense)',spice_testbench(p,t))

    def test_pvt_accepts_locked_model_sections_without_generic_overrides(self):
        p,_,_=reference(technology(),'differential_pair');t=p['testbenches'][1]
        p['pdk']['simulation']['includes']=[{'path':'models.spice','sections':{'nominal':'tt','ss':'ss','ff':'ff'}}]
        spec={**t['characterization'],'corners':['ss','ff'],'temperatures':[27]}
        self.assertEqual([b['analysis']['corner'] for _,_,_,b in prepared_cases(p,t,spec)],['ss','ff'])
        spec['corners']=['undeclared']
        with self.assertRaisesRegex(ValueError,'Corner is not declared'):prepared_cases(p,t,spec)


if __name__=='__main__':unittest.main()
