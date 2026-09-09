import unittest,math,tempfile,json
from pathlib import Path
from icstudio.model import example,device,clone,validate,digest,design_digest,atomic_write
from icstudio.wavecalc import evaluate,plot_result,VOLT,AMP,ONE,SECOND
from icstudio.specifications import evaluate_rows


def waveform():
    return {'x':[0.,1.,2.,3.],'x_label':'Time (s)','settings':{'type':'tran'},'traces':{'out':[0.,1.,2.,3.],'ref':[1.,1.,1.,1.]},'currents':{'V1':[2.,2.,2.,2.]},'phase':{}}


def rc_design():
    from icstudio.layout import rect
    from icstudio.parametric import install
    p=example('empty');c=p['cells'][0];c['devices']=[device('V','V1',value='1',nets={'p':'vin','n':'0'}),device('R','R1',value='1k',nets={'p':'vin','n':'vout'}),device('C','C1',value='10f',nets={'p':'vout','n':'0'})]
    
    for d,(x,y) in zip(c['devices'],[(180,260),(420,180),(650,260)]):d.update(x=x,y=y)
    c['devices'][1]['rotation']=270
    c['devices'][0]['source'].update(type='pulse',high='1',low='0',period='10n',delay='0.2n');install(p,c['id'],c['devices'][1]['id'],{'x':0,'y':0,'width':1000});install(p,c['id'],c['devices'][2]['id'],{'x':30000,'y':0})
    pins={(r['device_id'],r['pin']):r for r in c['layout_pins']};r=pins[c['devices'][1]['id'],'n'];cap=pins[c['devices'][2]['id'],'p'];a,b=r['point'],cap['point'];c['shapes'].append({'id':'route1','kind':'path','layer':'metal1','points':[a,[b[0],a[1]],b],'width':400,'net':'vout','device_id':''})
    c['ports']=['vout'];c['layout_ports']=[{'name':'vout','layer':'metal1','point':b}];p['analysis'].update(type='tran',step='0.05n',stop='2n');p['pdk']['parasitics']={'metal1':{'sheet_ohm':2,'cap_f_per_um2':.1e-15,'edge_f_per_um':.01e-15,'coupling_f_per_um':.02e-15}}
    c['specifications']=[{'name':'Output','expression':'final(V("vout"))','min':'.5','max':'1.1','unit':'V'}];return validate(p)


class CalculatorTests(unittest.TestCase):
    def test_differential_power_units(self):
        r=waveform();a=evaluate('V("out")-V("ref")',r);self.assertEqual(a.values,[-1,0,1,2]);self.assertEqual(a.unit,VOLT);p=evaluate('V("out")*I("V1")',r);self.assertEqual(p.values,[0,2,4,6]);self.assertEqual(p.unit,(1,1,0))
    def test_complex_gain_phase(self):
        r=waveform();r.update(x=[1,10,100,1000],settings={'type':'ac'},phase={'out':[90]*4},traces={'out':[2]*4,'ref':[1]*4});self.assertAlmostEqual(evaluate('final(phase(V("out")/V("ref")))',r).values[0],math.pi/2);self.assertAlmostEqual(evaluate('final(db20(V("out")/V("ref")))',r).values[0],20*math.log10(2))
    def test_integral_derivative(self):
        self.assertEqual(evaluate('integ(V("out"))',waveform()).values,[0,.5,2,4.5]);self.assertEqual(evaluate('deriv(V("out"))',waveform()).values,[1]*4)
    def test_crossing_settling_at(self):
        r=waveform();self.assertEqual(evaluate('at(V("out"),1.5)',r).values,[1.5]);self.assertEqual(evaluate('crossing(V("out"),1.5,1)',r).values,[1.5]);r['traces']['out']=[0,1,1,1];self.assertEqual(evaluate('settling(V("out"),1,0.1)',r).values,[1])
    def test_no_crossing_or_settling_is_error(self):
        for exp in ['crossing(V("out"),10,1)','settling(V("out"),10,0.1)','at(V("out"),4)']:
            with self.assertRaises(ValueError):evaluate(exp,waveform())
    def test_fft_amplitude_and_axis(self):
        n=256;r=waveform();r.update(x=[i/256 for i in range(n)],traces={'out':[2*math.sin(2*math.pi*16*i/n) for i in range(n)]});a=evaluate('fft(V("out"))',r);self.assertAlmostEqual(a.values[16],2,places=3);self.assertEqual(a.x[16],16);self.assertEqual(plot_result(r,'fft(V("out"))')['settings']['type'],'fft')
    def test_adaptive_fft_rejected(self):
        r=waveform();r['x']=[0,.2,1,3]
        with self.assertRaises(ValueError):evaluate('fft(V("out"))',r)
    def test_expression_sandbox(self):
        for expr in ['__import__("os")','V("out").values','[x for x in x]','open("a")','V("out")[0]','min','2**1000']:
            with self.subTest(expr=expr),self.assertRaises(ValueError):evaluate(expr,waveform())
    def test_wrong_units_and_nonfinite(self):
        for expr in ['V("out")+I("V1")','V("out")/0','exp(V("out"))','db20(V("out"))','crossing(V("out"),final(I("V1")),1)']:
            with self.subTest(expr=expr),self.assertRaises(ValueError):evaluate(expr,waveform())
    def test_spec_pass_fail_and_errors(self):
        rows=[{'name':'limit','expression':'final(V("out"))','unit':'V','min':2,'max':4}];a=evaluate_rows(rows,waveform())[0];self.assertEqual(a['status'],'PASS');self.assertEqual(a['margin'],1);rows[0]['max']=2;self.assertEqual(evaluate_rows(rows,waveform())[0]['status'],'FAIL');rows[0]['expression']='final(V("missing"))';self.assertEqual(evaluate_rows(rows,waveform())[0]['status'],'ERROR')
    def test_spec_dimensions_and_model_validation(self):
        row={'name':'unit','expression':'rms(V("out"))','min':0,'unit':'A'};self.assertEqual(evaluate_rows([row],waveform())[0]['status'],'ERROR');p=example();p['cells'][0]['specifications']=[row,row]
        with self.assertRaises(ValueError):validate(p)


class VariationTests(unittest.TestCase):
    def test_repeatable_cases_and_resume(self):
        from icstudio.variation_runs import prepare,pending,save,load,summary
        p=example();job={'project':p,'cell':p['top'],'settings':p['analysis'],'engine':'builtin'};spec={'kind':'monte_carlo','count':3,'seed':42,'variations':[{'target':'R1.value','relative_sigma':.1}]};a=prepare(job,spec);b=prepare(job,spec);self.assertEqual([j['case']['changes'] for j in a['jobs']],[j['case']['changes'] for j in b['jobs']]);self.assertEqual(p['cells'][0]['devices'][1]['value'],'10k')
        rows=[{'job':a['jobs'][0],'state':'Complete','result':{'specifications':[{'name':'out','value':1,'margin':.2,'status':'PASS'}]}},{'job':a['jobs'][1],'state':'Failed'}];self.assertEqual(len(pending(a,rows)),2);self.assertEqual(summary(a,rows)['yield'],1/3)
        with tempfile.TemporaryDirectory() as t:save(a,t);self.assertEqual(load(t,p['id'])[0],a)
    def test_all_cases_valid_before_enqueue(self):
        from icstudio.variation_runs import prepare
        p=example();job={'project':p,'cell':p['top'],'settings':p['analysis'],'engine':'builtin'}
        with self.assertRaises(ValueError):prepare(job,{'kind':'sweep','target':'R1.value','values':['1k','-1']})
    def test_model_mismatch_requires_evidence(self):
        from icstudio.variation_runs import prepare
        p=example()
        with self.assertRaises(ValueError):prepare({'project':p,'cell':p['top'],'settings':p['analysis'],'engine':'builtin'},{'kind':'model_mismatch','model':'unknown'})
    def test_pvt_cartesian(self):
        from icstudio.variation_runs import prepare
        p=example();p['cells'][0]['devices'][0]['source']['type']='dc';m=prepare({'project':p,'cell':p['top'],'settings':p['analysis'],'engine':'builtin'},{'kind':'pvt','target':'V1.value','corners':['nominal'],'voltages':[1,2],'temperatures':[0,27,85]});self.assertEqual(len(m['jobs']),6);self.assertEqual(m['jobs'][4]['settings']['temperature'],27)


class PhysicalTests(unittest.TestCase):
    def test_stable_regeneration_and_electrical_identity(self):
        from icstudio.parametric import install
        from icstudio.analog_constraints import move_device
        p=example();cid=p['top'];d=p['cells'][0]['devices'][1];before=clone(d);r=install(p,cid,d['id'],{'x':0,'y':0,'width':1000});ids=[s['id'] for s in p['cells'][0]['shapes']];pinids=[v['id'] for v in p['cells'][0]['layout_pins']];move_device(p,cid,d['id'],5000,2000);install(p,cid,d['id'],r['spec']);self.assertEqual(ids,[s['id'] for s in p['cells'][0]['shapes']]);self.assertEqual(pinids,[v['id'] for v in p['cells'][0]['layout_pins']]);self.assertEqual(before,d);self.assertEqual(p['cells'][0]['parametric_devices'][0]['spec']['x'],5000);validate(p)
    def test_contact_enclosure(self):
        from icstudio.parametric import install
        from icstudio.live_geometry import check_enclosures
        p=example();c=p['cells'][0];install(p,c['id'],None,{'kind':'contact','rows':2,'columns':2});self.assertFalse(check_enclosures(p,c['id'],c['shapes']));c['shapes']=[s for s in c['shapes'] if s['pcell_role']!='upper'];self.assertTrue(check_enclosures(p,c['id'],c['shapes']))
    def test_live_route_short_blocked(self):
        from icstudio.live_geometry import preview
        from icstudio.layout import rect
        p=example();c=p['cells'][0];c['shapes']=[rect('metal1',0,0,1000,1000,net='a')];candidate={'id':'test','kind':'path','layer':'metal1','points':[[500,500],[500,3000]],'width':300,'net':'b'};self.assertTrue(any(r['code']=='SHORT' for r in preview(p,c['id'],[candidate])))
    def test_matching_symmetry_centroid(self):
        from icstudio.parametric import install
        from icstudio.analog_constraints import arrange,findings
        p=example('empty');c=p['cells'][0];c['devices']=[device('R','R'+str(i+1),value='1k') for i in range(4)]
        for i,d in enumerate(c['devices']):install(p,c['id'],d['id'],{'x':i*20000,'y':0,'width':1000})
        ids=[d['id'] for d in c['devices']];row={'kind':'common_centroid','members':ids,'groups':[ids[:2],ids[2:]],'name':'centroid'};c['analog_constraints']=[row];self.assertTrue(findings(p,c['id']));arrange(p,c['id'],row,20000);self.assertFalse(findings(p,c['id']));c['analog_constraints'].append({'kind':'matching','members':ids,'name':'match'});self.assertFalse(findings(p,c['id']));validate(p)
    def test_matching_checks_hierarchical_parameter_overrides(self):
        from icstudio.analog_constraints import findings
        from icstudio.layout import rect
        from icstudio.model import uid
        p=example('empty');c=p['cells'][0];child={'id':uid(),'name':'unit','ports':['p','n'],'parameters':{'resistance':'1k'},'devices':[],'shapes':[rect('metal1',0,0,1000,1000)]};p['cells'].append(child)
        c['devices']=[device('X','X1',cell=child['id'],nets={'p':'a','n':'0'},parameters={'resistance':'1k'}),device('X','X2',cell=child['id'],nets={'p':'b','n':'0'},parameters={'resistance':'2k'})];c['layout_instances']=[{'id':uid(),'name':d['name'],'cell':child['id'],'device_id':d['id'],'x':i*3000,'y':0} for i,d in enumerate(c['devices'])];c['analog_constraints']=[{'name':'Unit match','kind':'matching','members':[d['id'] for d in c['devices']]}];self.assertTrue(findings(p,c['id']))
    def test_guard_coverage(self):
        from icstudio.parametric import install
        from icstudio.analog_constraints import findings
        p=example('empty');c=p['cells'][0];d=device('R','R1',value='100');c['devices']=[d];install(p,c['id'],d['id'],{'x':3000,'y':3000,'width':1000});r=install(p,c['id'],None,{'kind':'guard_ring','x':0,'y':0,'width':10000,'height':10000,'thickness':600});c['analog_constraints']=[{'kind':'guard_ring','name':'guard','members':[d['id']],'ring':r['id']}];self.assertFalse(findings(p,c['id']))
    def test_rc_network_connectivity_and_same_specs(self):
        from icstudio.distributed_rc import extract,apply,compare_job
        p=rc_design();cid=p['top'];e=extract(p,cid);self.assertGreater(len(e['resistors']),3);self.assertTrue(e['capacitors']);q=apply(p,cid,e);self.assertGreater(len(q['cells'][0]['devices']),len(p['cells'][0]['devices']));self.assertEqual(q['cells'][0]['devices'][1]['id'],p['cells'][0]['devices'][1]['id'])
        with tempfile.TemporaryDirectory() as t:r=compare_job(p,{'project':p,'cell':cid,'settings':{'type':'rc_compare','analysis':p['analysis']},'engine':'builtin'},Path(t));self.assertEqual(len(r['rc_comparison']),1);self.assertEqual(r['design_hash'],design_digest(p));self.assertNotEqual(r['before_waveform']['traces']['vout'],r['after_waveform']['traces']['vout'])
    def test_parallel_coupling_coefficient_and_overlap_gate(self):
        from icstudio.distributed_rc import extract
        p=example('empty');c=p['cells'][0];c['devices']=[device('R','R1',nets={'p':'a','n':'b'}),device('R','R2',nets={'p':'a','n':'b'})];c['shapes']=[{'id':'a_path','kind':'path','layer':'metal1','points':[[0,0],[20000,0]],'width':400,'net':'a'},{'id':'b_path','kind':'path','layer':'metal1','points':[[0,1500],[20000,1500]],'width':400,'net':'b'}];c['layout_pins']=[]
        for i,d in enumerate(c['devices']):
            for pin,y in [('p',0),('n',1500)]:c['layout_pins'].append({'id':d['id']+pin,'device_id':d['id'],'pin':pin,'layer':'metal1','point':[i*20000,y]})
        p['pdk']['parasitics']={'metal1':{'sheet_ohm':2,'coupling_f_per_um':1e-15}};e=extract(p,c['id']);self.assertAlmostEqual(sum(r['value'] for r in e['resistors']),200);self.assertAlmostEqual(sum(v['value'] for v in e['capacitors'] if v['kind']=='coupling')/1e-15,20/1.1)
        c['shapes'].append({**clone(c['shapes'][0]),'id':'duplicate'})
        with self.assertRaises(ValueError):extract(p,c['id'])
    def test_stale_extraction_rejected(self):
        from icstudio.distributed_rc import extract,apply
        p=rc_design();e=extract(p,p['top']);p['revision']+=1
        with self.assertRaises(ValueError):apply(p,p['top'],e)
    def test_unbound_pcell_rule_rejected(self):
        from icstudio.parametric import rules
        p=example();p['pdk']['revision']='other'
        with self.assertRaises(ValueError):rules(p['pdk'])


class ExchangeAnnotationTests(unittest.TestCase):
    def test_exchange_review_changes_and_tamper_gate(self):
        from icstudio.interchange import export_xschem
        from icstudio.exchange_review import review,apply_review
        p=example()
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);export_xschem(p,root);path=root/'top.sch';path.write_text(path.read_text().replace('value="10k"','value="20k"').replace('value=10k','value=20k'));r=review(path);self.assertFalse(r['errors']);self.assertTrue(any(v['change']=='value' for v in r['changes']));apply_review(r);path.write_text(path.read_text()+'\n')
            with self.assertRaises(ValueError):apply_review(r)
    def test_unknown_symbol_is_reviewable_error(self):
        from icstudio.interchange import export_xschem
        from icstudio.exchange_review import review
        p=example()
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);export_xschem(p,root);path=root/'top.sch';path.write_text(path.read_text()+'\nC {unknown.sym} 0 0 0 0 {name=weird}\n');r=review(path);self.assertTrue(r['errors']);self.assertIsNone(r['candidate'])
    def test_operating_point_vectors_no_fabricated_region(self):
        from icstudio.operating_data import extras
        currents,phase,ds=extras(['v(out)','i(v1)','@m1[gm]','@m1[vds]','@m1[vdsat]'],[[1,-.001,.002,.8,.3]],aliases={'m1':'M1','v1':'V1'});self.assertEqual(currents['V1'],[-.001]);self.assertAlmostEqual(ds['M1']['headroom'],.5);self.assertNotIn('region',ds['M1'])
    def test_builtin_annotations_saved_results(self):
        from icstudio.simulation import run
        from icstudio.annotations import readouts
        p=example('inverter');r=run(p,p['top'],{'type':'op'});self.assertTrue(r['device_operating_point']);rows,label=readouts(p,p['top'],r);self.assertTrue(rows);p['revision']+=1;self.assertTrue(readouts(p,p['top'],r)[1].startswith('STALE'))

if __name__=='__main__':unittest.main()
