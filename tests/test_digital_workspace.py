"""Dependency, constraint, trace and representative-block acceptance checks."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from icstudio import digital, digital_constraints as constraints, digital_identity as identity
from icstudio.model import clone
from icstudio.digital_planning import sequence, latest_upstream
from tests.test_digital import tool


class IntentTests(unittest.TestCase):
    def setUp(self):self.config=digital.counter_project()['digital']

    def test_synthesis_budget_tracks_generated_constraints(self):
        intent=constraints.default_intent();config=constraints.apply(self.config,intent)
        self.assertAlmostEqual(constraints.synthesis_settings(config)['delay_ns'],7.9)
        self.assertIn('set_cmd_units -time ns -capacitance pF',config['files'][-1]['text'])
        config['files'][-1]['text']+='set_false_path -from [get_ports reset]\n'
        with self.assertRaisesRegex(ValueError,'SDC was edited'):constraints.synthesis_settings(config)
        config['synthesis']={'delay_ns':3};self.assertEqual(constraints.synthesis_settings(config)['delay_ns'],3)

    def test_multiple_clocks_and_invalid_timing_intent(self):
        value=constraints.default_intent();value['clocks'].append({'name':'slow','port':'slow_clk','period_ns':5})
        self.assertEqual(constraints.synthesis_settings(constraints.apply(self.config,value))['delay_ns'],5)
        value['clocks'][1]['period_ns']=0
        with self.assertRaises(ValueError):constraints.sdc(value)
        value=constraints.default_intent();value['inputs'][0]['min_ns']=9
        with self.assertRaises(ValueError):constraints.sdc(value)

    def test_sdc_generation_cannot_delete_an_rtl_source(self):
        with self.assertRaisesRegex(ValueError,'belongs to another source'):
            constraints.apply(self.config,constraints.default_intent(),'counter.sv')

    def test_semantic_invalidation_separates_simulation_and_mapping(self):
        edited=clone(self.config);edited['files'][1]['text']+='\n// New test scenario';edited['timeout']=300
        self.assertEqual(identity.stage_key(self.config,'mapped'),identity.stage_key(edited,'mapped'))
        self.assertNotEqual(identity.stage_key(self.config,'simulate'),identity.stage_key(edited,'simulate'))
        edited=clone(self.config);edited['files'][2]['text']+='\n# timing edit'
        self.assertEqual(identity.stage_key(self.config,'mapped'),identity.stage_key(edited,'mapped'))
        self.assertNotEqual(identity.stage_key(self.config,'timing'),identity.stage_key(edited,'timing'))
        structured=constraints.apply(self.config,constraints.default_intent());changed=clone(structured)
        changed['constraints']['clocks'][0]['period_ns']=5;changed=constraints.apply(changed,changed['constraints'])
        self.assertNotEqual(identity.stage_key(structured,'mapped'),identity.stage_key(changed,'mapped'))

    def test_execution_threads_and_route_layers_preserve_earlier_stages(self):
        a=clone(self.config);a['physical']={'threads':2};b=clone(a);b['physical']['threads']=8
        self.assertEqual(identity.stage_key(a,'finish'),identity.stage_key(b,'finish'))
        b['physical']['max_routing_layer']='met4'
        self.assertEqual(identity.stage_key(a,'place'),identity.stage_key(b,'place'))
        self.assertNotEqual(identity.stage_key(a,'route'),identity.stage_key(b,'route'))

    def test_library_binding_and_physical_intent_affect_analysis_identity(self):
        a=clone(self.config);a['platform']={'fingerprint':'files','corner':'tt','corners':{'tt':['a.lib']}}
        b=clone(a);b['platform']['corners']['tt']=['b.lib']
        self.assertNotEqual(identity.stage_key(a,'mapped'),identity.stage_key(b,'mapped'))
        b=clone(a);b['physical']={'place_density':.7}
        self.assertNotEqual(identity.stage_key(a,'timing'),identity.stage_key(b,'timing'))

    def test_flow_targets_and_upstream_selection(self):
        p=digital.counter_project();cid=p['top']
        self.assertEqual(sequence('route',p['digital']),['mapped','floorplan','place','cts','route','timing'])
        self.assertEqual(sequence('verify',p['digital']),['lint','simulate','mapped','equivalence','timing'])
        def row(stage,state='Complete'):
            return {'state':state,'job':{'project':clone(p),'cell':cid,'settings':{}},
                    'result':{'digital_result':{'stage':stage,'input_key':identity.stage_key(p['digital'],stage)}}}
        mapped=row('mapped');placed=row('place');failed=row('cts','Failed')
        self.assertIs(latest_upstream([mapped,placed,failed],p,cid,'route'),placed)
        p['digital']['files'][0]['text']+='\n// revision'
        self.assertIsNone(latest_upstream([mapped,placed],p,cid,'route'))

    def test_run_comparisons_reject_different_constraints(self):
        from icstudio.digital_reports import compare_results
        def row(name,area,constraint):
            return {'id':name,'name':name,'state':'Complete','job':{'settings':{'stage':'timing'}},'result':{'digital_result':{
                'stage':'timing','statistics':{'area_um2':area},'fingerprints':{'constraints':constraint},'timing':{'parasitics':'extracted SPEF'}}}}
        rows=compare_results([row('base',10,'a'),row('changed',20,'b'),row('same',15,'a')])
        self.assertEqual(rows[1]['baseline'],'changed');self.assertEqual(rows[2]['area_um2_delta'],5)

    def test_tns_and_electrical_failures_are_not_hidden(self):
        from icstudio.digital_reports import timing_report
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for name,text in {'timing_paths.tsv':'setup\ta\tb\t2\ta|b\n','timing_checks.txt':'','timing_units.txt':'time 1ns',
                              'timing_totals.txt':'tns max -1.25','electrical_checks.txt':'max slew VIOLATED'}.items():(root/name).write_text(text)
            data=timing_report(root);self.assertEqual(data['status'],'FAIL');self.assertEqual(data['summary']['setup_total_negative_slack_ns'],-1.25)


class TraceTests(unittest.TestCase):
    def test_streamed_aliases_unknowns_and_random_access(self):
        from icstudio.digital_trace_store import index_vcd,open_waveform,next_event
        from icstudio.digital_waveform import read_vcd,value_at,format_value
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);vcd=root/'wave.vcd'
            vcd.write_text('$timescale 1ps $end\n$scope module top $end\n$var wire 4 ! bus [3:0] $end\n$var wire 4 ! alias [3:0] $end\n$upscope $end\n$enddefinitions $end\n#0 bx !\n#2 bz !\n'+''.join(f'#{i+3} b{i%16:b} !\n' for i in range(2100)))
            reference=read_vcd(vcd);data=index_vcd(vcd,root/'waveform.sqlite');(root/'waveform.json').write_text(json.dumps(data))
            indexed=open_waveform(root/'waveform.json');events=indexed['changes']['!']
            self.assertEqual(indexed['event_count'],reference['event_count']);self.assertEqual(indexed['signals'],reference['signals'])
            for tick in (0,1,2,4,520,1050,1800,2103):self.assertEqual(value_at(events,tick,4),value_at(reference['changes']['!'],tick,4))
            self.assertEqual(next_event(events,100,'1111'),114);self.assertEqual(next_event(events,100,'zzzz',True),2)
            self.assertEqual(format_value('1111','signed'),'-1');self.assertEqual(format_value('xx01','signed'),'xx01')

    def test_failed_index_is_removed(self):
        from icstudio.digital_trace_store import index_vcd
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'bad.vcd').write_text('$timescale nope $end')
            with self.assertRaises(ValueError):index_vcd(root/'bad.vcd',root/'waveform.sqlite')
            self.assertFalse((root/'waveform.sqlite').exists())

    def test_language_protocol_handles_fragmented_unicode_and_batches(self):
        from icstudio.digital_lsp import frame,Decoder
        data=[{'id':1,'result':'λ input'},{'method':'diagnostic','params':{'text':'é'}}];encoded=b''.join(frame(d) for d in data)
        decoder=Decoder();out=[]
        for i in range(0,len(encoded),7):out+=decoder.feed(encoded[i:i+7])
        self.assertEqual(out,data);self.assertEqual(decoder.buffer,b'')

    def test_logic_cone_does_not_connect_two_load_pins_as_driver_and_sink(self):
        from icstudio.digital_inspection import cone
        index=[{'module':'top','name':name,'kind':'cell','connections':{'P':[2]},'port_directions':{'P':direction}} for name,direction in (('driver','output'),('a','input'),('b','input'))]
        graph=cone(index,'top','a')
        pairs={(e['source'],e['target']) for e in graph['edges']}
        self.assertEqual(pairs,{('driver','a'),('driver','b')})

    def test_hierarchy_ambiguity_is_explicit(self):
        from icstudio.digital_inspection import sources_for_signal
        index=[{'module':m,'name':'count','kind':'net'} for m in ('left','right')]
        self.assertEqual(len(sources_for_signal(index,'bench.dut.count[3:0]')),2)
        self.assertEqual(sources_for_signal(index,'bench.left.count[3:0]'),[index[0]])


@unittest.skipUnless(tool('iverilog') and tool('vvp'),'Install Icarus for peripheral acceptance')
class PeripheralTests(unittest.TestCase):
    def test_apb_protocol_fifo_interrupt_and_deliberate_fault(self):
        from icstudio.digital_apb_example import apb_project
        from icstudio.digital_flow import prepare,run
        p=apb_project();tools={n:tool(n) for n in ('iverilog','vvp')}
        with tempfile.TemporaryDirectory() as td:
            result=run(prepare(p,'simulate',tools=tools),Path(td)/'pass')
            self.assertGreater(result['digital_result']['statistics']['events'],50)
            p['digital']['files'][1]['text']=p['digital']['files'][1]['text'].replace('irq_enable && !empty','irq_enable && empty')
            with self.assertRaisesRegex(RuntimeError,'interrupt mismatch|setup performed'):
                run(prepare(p,'simulate',tools=tools),Path(td)/'fault')


if __name__=='__main__':unittest.main()
