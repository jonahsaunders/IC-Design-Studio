"""Numerical interconnect regressions; synthetic coupons are not process evidence."""
import json
import math
import os
import tempfile
import unittest
from pathlib import Path

from icstudio.model import example, clone, device, uid, validate, design_digest, file_digest
from icstudio.layout import rect
from icstudio.physical import connectivity
from icstudio.physical_extraction import normalize_extraction, calibrated_network, measurement_comparison
from icstudio.distributed_rc import extract, apply, compare_job
from icstudio.rc_calibration import calibrate, install
from icstudio.testbenches import create
from test_layout_priorities import coupons


def resistive_bench():
    p=example('empty');c=p['cells'][0];c['name']='resistive_dut';c['ports']=['IN','OUT']
    resistor=device('R','RDUT',value='100',nets={'p':'IN','n':'OUT'});c['devices']=[resistor]
    c['shapes']=[{'id':uid(),'kind':'path','layer':'metal1','points':[[0,0],[20000,0]],
                  'width':1000,'net':'IN'},rect('metal1',-500,2500,1000,1000,net='OUT')]
    c['layout_pins']=[{'id':uid(),'device_id':resistor['id'],'pin':pin,'layer':'metal1','point':pt}
                      for pin,pt in [('p',[0,0]),('n',[0,3000])]]
    c['layout_ports']=[{'name':'IN','layer':'metal1','point':[20000,0]},
                       {'name':'OUT','layer':'metal1','point':[0,3000]}]
    bench={'id':uid(),'name':'fixture','ports':[],'shapes':[],'devices':[
        device('V','VDD',value='1',nets={'p':'input','n':'0'}),
        device('R','RLOAD',value='100',nets={'p':'output','n':'0'}),
        device('X','XDUT',cell=c['id'],nets={'IN':'input','OUT':'output'})]}
    p['cells'].append(bench);p['top']=bench['id'];p['analysis'].update(type='op',temperature=27)
    t=create(p,bench['id']);t['measurements']=[{'name':'output_level','kind':'voltage','node':'output','min':'.45'}]
    t['physical_extraction']={'mode':'calibrated_rc','corner':'nominal','section_nm':6000,'coupling_distance_nm':5000}
    p['testbenches']=[t]
    for corner,sheet in [('nominal',2),('slow_rc',4)]:
        data=coupons();data['corner']=corner
        for row in data['layers']['metal1']['resistance']:row['resistance_ohm']=sheet*row['length_um']/row['width_um']
        install(p['pdk'],calibrate(p['pdk'],data))
    return validate(p),c['id'],t


class PhysicalExtractionTests(unittest.TestCase):
    def test_saved_configuration_rejects_incompatible_or_unsafe_choices(self):
        p,cid,t=resistive_bench()
        self.assertEqual(normalize_extraction(),{'mode':'capacitance'})
        for choice in ({'mode':'rc','section_nm':5000},{'mode':'calibrated_rc','section_nm':50},
                       {'mode':'calibrated_rc','coupling_distance_nm':-1},{'mode':'calibrated_rc','corner':''},
                       {'mode':'invented'}):
            t['physical_extraction']=choice
            with self.subTest(choice=choice),self.assertRaises(ValueError):validate(p)

    def test_path_port_resistance_changes_exact_dc_transfer(self):
        from icstudio.simulation import run
        p,cid,t=resistive_bench();self.assertFalse(connectivity(p,cid)['issues'])
        network,q=calibrated_network(p,cid,t['physical_extraction'])
        self.assertAlmostEqual(sum(r['value'] for r in network['resistors']),40)
        mapping=next(m for m in network['terminal_mapping'] if m['pin']=='p')
        self.assertNotEqual(mapping['node'],'IN')
        before=run(p,p['top'],p['analysis']);after=run(q,q['top'],q['analysis'])
        self.assertAlmostEqual(before['traces']['output'][0],.5,places=8)
        self.assertAlmostEqual(after['traces']['output'][0],100/240,places=8)
        # An interior external port must split the section and see only its 10 µm route.
        p['cells'][0]['layout_ports'][0]['point']=[10000,0]
        _,q=calibrated_network(p,cid,t['physical_extraction'])
        after=run(q,q['top'],q['analysis'])
        self.assertAlmostEqual(after['traces']['output'][0],100/220,places=8)

    def test_calibrated_choice_rejects_missing_changed_corner_and_geometry_faults(self):
        p,cid,t=resistive_bench()
        missing=clone(p);missing['pdk'].pop('parasitic_corners')
        with self.assertRaisesRegex(ValueError,'coupon calibration'):calibrated_network(missing,cid,t['physical_extraction'])
        with self.assertRaisesRegex(ValueError,'corner'):calibrated_network(p,cid,{**t['physical_extraction'],'corner':'absent'})
        altered=clone(p);altered['pdk']['parasitic_corners']['nominal']['coefficients']['metal1']['sheet_ohm']=3
        with self.assertRaisesRegex(ValueError,'changed'):calibrated_network(altered,cid,t['physical_extraction'])
        opened=clone(p);opened['cells'][0]['shapes'][0]['points'][0]=[5000,0]
        with self.assertRaisesRegex(ValueError,'connectivity'):calibrated_network(opened,cid,t['physical_extraction'])
        shorted=clone(p);shorted['cells'][0]['shapes'].append(rect('metal1',-500,0,1000,3500))
        with self.assertRaisesRegex(ValueError,'connectivity'):calibrated_network(shorted,cid,t['physical_extraction'])

    def test_calibrated_parallel_coupling_matches_ac_crosstalk_transfer(self):
        from icstudio.simulation import run
        p=example('empty');c=p['cells'][0]
        c['devices']=[device('V','V1',value='0',nets={'p':'a','n':'0'}),
                      device('R','R1',value='1k',nets={'p':'b','n':'0'})]
        c['shapes']=[{'id':uid(),'kind':'path','layer':'metal1','points':[[0,y],[20000,y]],
                      'width':400,'net':net} for y,net in [(0,'a'),(1500,'b')]]
        c['shapes'].append(rect('metal1',-500,3500,1000,1000,net='0'))
        c['layout_pins']=[{'id':uid(),'device_id':d['id'],'pin':'p','layer':'metal1','point':[0,y]}
                          for d,y in zip(c['devices'],[0,1500])]
        c['layout_pins'].append({'id':uid(),'device_id':c['devices'][1]['id'],'pin':'n','layer':'metal1','point':[0,4000]})
        data=coupons()
        for row in data['layers']['metal1']['resistance']:row['resistance_ohm']=1e-6*row['length_um']/row['width_um']
        for row in data['layers']['metal1']['coupling']:row['capacitance_f']=1e-15*row['overlap_um']/row['gap_um']
        install(p['pdk'],calibrate(p['pdk'],data));p['analysis'].update(type='ac',start='1meg',end='1g',points=3)
        network,q=calibrated_network(p,c['id'],{'mode':'calibrated_rc'})
        before=run(p,p['top'],p['analysis']);after=run(q,q['top'],q['analysis'])
        self.assertEqual(before['traces']['b'],[0.,0.,0.])
        coupling=1e-15*20/1.1;ground=20*.4*2e-17+2*20*1e-17
        for frequency,actual in zip(after['x'],after['traces']['b']):
            # Near-ideal route resistance gives the independent lumped transfer.
            omega=2*math.pi*frequency
            expected=omega*1000*coupling/math.sqrt(1+(omega*1000*(coupling+ground))**2)
            self.assertAlmostEqual(actual,expected,delta=expected*2e-6)
        self.assertAlmostEqual(sum(v['value'] for v in network['capacitors'] if v['kind']=='coupling'),coupling)

    def test_network_rejects_changed_values_cell_and_revision(self):
        p,cid,t=resistive_bench();network,_=calibrated_network(p,cid,t['physical_extraction'])
        changed=clone(network);changed['resistors'][0]['value']*=2
        with self.assertRaisesRegex(ValueError,'network or provenance changed'):apply(p,cid,changed)
        with self.assertRaisesRegex(ValueError,'another circuit'):apply(p,p['top'],network)
        p['revision']+=1
        with self.assertRaisesRegex(ValueError,'stale'):apply(p,cid,network)

    def test_calibrated_network_does_not_bypass_process_verification_gates(self):
        from icstudio.hierarchical_flow import run
        p,cid,t=resistive_bench()
        with tempfile.TemporaryDirectory() as tmp:
            report=run(p,t['id'],Path(tmp)/'physical',{})
        self.assertEqual(report['status'],'blocked')
        self.assertEqual(report['physical_extraction']['mode'],'calibrated_rc')
        stages={s['name']:s['status'] for s in report['stages']}
        self.assertEqual(stages['preflight'],'failed')
        self.assertEqual(stages['lvs'],'not_run')
        self.assertEqual(stages['post_layout_simulation'],'not_run')
        self.assertEqual(stages['integrity'],'not_run')

    def test_mutation_after_simulation_fails_explicit_integrity_stage(self):
        from icstudio.hierarchical_flow import record_stage,verify_integrity
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);deck=directory/'extracted.spice';deck.write_text('Rwire in out 40\n')
            files={'extracted.spice':file_digest(deck)}
            self.assertTrue(verify_integrity(directory,files,{},{} )['verified'])
            report={'stages':[{'name':'post_layout_simulation','status':'passed','evidence':{'measurements':[]}}]}
            # Simulate an external edit after the last numerical result is recorded.
            deck.write_text('Rwire in out 0\n')
            with self.assertRaisesRegex(ValueError,'evidence changed'):
                record_stage(report,'integrity',lambda:verify_integrity(directory,files,{},{}),lambda:None,lambda *_:None)
            self.assertEqual(report['stages'][-2]['status'],'passed')
            self.assertEqual(report['stages'][-1]['name'],'integrity')
            self.assertEqual(report['stages'][-1]['status'],'failed')
            self.assertIn('evidence changed',report['stages'][-1]['error'])

    def test_comparison_retains_failed_missing_and_zero_baseline_values(self):
        rows=measurement_comparison([{'name':'voltage','value':0.,'unit':'V','status':'passed'},
                                     {'name':'missing','value':1.,'unit':'A','status':'passed'}],
                                    [{'name':'voltage','value':-.2,'unit':'V','status':'failed','error':'Below minimum'}])
        self.assertEqual(rows[0]['delta'],-.2);self.assertIsNone(rows[0]['relative_delta']);self.assertTrue(rows[0]['regressed'])
        self.assertEqual(rows[1]['after_status'],'not_run');self.assertIsNone(rows[1]['delta'])

    def test_real_saved_bench_comparison_across_conditions(self):
        from icstudio.spice_program import find_ngspice
        executable=find_ngspice(os.environ.get('ICSTUDIO_TEST_NGSPICE',''))
        if not executable:self.skipTest('ngspice is required for actual saved-bench comparison')
        p,cid,t=resistive_bench();original=clone(p)
        with tempfile.TemporaryDirectory() as tmp:
            index=0
            for supply in (1.,1.2):
                for temperature,corner,sheet in ((27,'nominal',2),(85,'slow_rc',4)):
                    index+=1;sample=clone(p);bench=sample['testbenches'][0]
                    sample['cells'][1]['devices'][0]['value']=str(supply)
                    bench['analysis']['temperature']=temperature
                    bench['physical_extraction']['corner']=corner
                    job={'project':sample,'cell':bench['bench_cell'],'engine':'ngspice','executable':executable,
                         'settings':{'type':'rc_compare','testbench':bench['id']}}
                    directory=Path(tmp)/str(index);result=compare_job(sample,job,directory)
                    row=result['measurement_comparison'][0]
                    self.assertAlmostEqual(row['before'],supply/2,places=7)
                    self.assertAlmostEqual(row['after'],supply*100/(200+sheet*20),places=7)
                    self.assertAlmostEqual(row['delta'],row['after']-row['before'],places=12)
                    self.assertEqual(result['conditions'],{'model_corner':'nominal','rc_corner':corner,'temperature':temperature})
                    self.assertEqual(result['provenance']['design_hash'],design_digest(sample))
                    self.assertEqual(result['provenance']['extraction_sha256'],file_digest(directory/'extraction.json'))
                    self.assertEqual(json.loads((directory/'after/result.json').read_text())['design_hash'],design_digest(sample))
                    self.assertEqual(row['regressed'],row['after']<.45)
                    self.assertEqual(result['status'],'failed' if row['after']<.45 else 'passed')
        self.assertEqual(p,original)


if __name__=='__main__':unittest.main()
