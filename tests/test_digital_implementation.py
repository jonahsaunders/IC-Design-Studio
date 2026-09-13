"""Cell identity, proof outcomes, and actual RTL-to-layout acceptance runs."""
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from icstudio import digital, digital_design as design, digital_flow as flow, digital_platform as platform
from icstudio import digital_reports as reports, job_store
from icstudio.model import clone, validate, History, atomic_write, file_digest
from tests.test_digital import tool


class DigitalWorkspaceModelTests(unittest.TestCase):
    def test_generated_bus_artifact_paths_stay_confined(self):
        self.assertEqual(flow.artifact_path('proof/count[0]/$sat.log'),'proof/count[0]/$sat.log')
        for name in ('../file','proof/../../file','/absolute','proof//file','proof/./file'):
            with self.assertRaises(ValueError):flow.artifact_path(name)

    def test_comparison_uses_same_stage_and_platform_baseline(self):
        def row(name,stage,area,corner='tt'):
            return dict(id=name,name=name,state='Complete',job={'settings':{'stage':stage}},result={'digital_result':{'stage':stage,'platform':{'corner':corner},'statistics':{'area_um2':area}}})
        rows=reports.compare_results([row('sim','simulate',None),row('first','mapped',100),row('second','mapped',125),row('slow','mapped',140,'ss')])
        self.assertEqual(rows[2]['area_um2_delta'],25);self.assertEqual(rows[2]['baseline'],'first')
        self.assertEqual(rows[3]['area_um2_delta'],0)

    def test_cell_views_survive_top_change_and_undo(self):
        p=digital.counter_project();original=p['top'];h=History(p)
        def change(p):
            p['top']=design.new_cell(p,'other',clone(p['digital']))
            design.config(p,p['top'])['defines']={'WIDTH':'8'}
        h.commit(change);validate(h.project)
        self.assertEqual(design.config(h.project,original),p['digital'])
        self.assertEqual(design.config(h.project,h.project['top'])['defines'],{'WIDTH':'8'})
        h.undo();self.assertEqual(h.project['cells'],p['cells'])

    def test_platform_locks_reject_edits_and_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'cells.lib').write_text('library(test) {}')
            manifest={'version':1,'name':'test','revision':'fixture-1','corner':'tt','corners':{'tt':['cells.lib']},'files':['cells.lib']}
            (root/'platform.json').write_text(json.dumps(manifest));value=platform.read_manifest(root/'platform.json')
            platform.stage(value,root/'capture')
            self.assertEqual((root/'capture/cells.lib').read_text(),'library(test) {}')
            bad=clone(value);bad['directory']='../escape'
            with self.assertRaises(ValueError):platform.validate(bad)
            (root/'cells.lib').write_text('changed')
            with self.assertRaisesRegex(ValueError,'changed'):platform.verify(value)

    def test_equivalence_reports_distinguish_unknown_fail_error(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);status=root/'strategies/q/sat/status';status.parent.mkdir(parents=True)
            for value in ('UNKNOWN','FAIL','ERROR'):
                status.write_text(value);self.assertEqual(reports.eqy_report(root)['status'],value)
            status.write_text('PASS');self.assertEqual(reports.eqy_report(root)['status'],'ERROR')
            (root/'PASS').touch();self.assertEqual(reports.eqy_report(root)['status'],'PASS')
            other=status.parent.parent/'other/status';other.parent.mkdir();other.write_text('FAIL')
            self.assertEqual(reports.eqy_report(root)['status'],'FAIL')
            other.unlink();status.write_text('TIMEOUT');self.assertEqual(reports.eqy_report(root)['status'],'UNKNOWN')
            status.unlink();self.assertEqual(reports.eqy_report(root)['status'],'ERROR')

    def test_unconstrained_timing_never_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'timing_paths.tsv').write_text('setup\ta\tb\t3.5\ta|b\n')
            (root/'timing_units.txt').write_text('time 1ns')
            for text,status in [('Warning: missing input_delay','INCOMPLETE'),('','PASS')]:
                (root/'timing_checks.txt').write_text(text);self.assertEqual(reports.timing_report(root)['status'],status)
            (root/'timing_paths.tsv').write_text('setup\ta\tb\t-0.125\ta|b\n');self.assertEqual(reports.timing_report(root)['status'],'FAIL')

    def test_mixed_plan_does_not_multiply_rtl_by_analog_pvt(self):
        from icstudio.model import example
        from icstudio.test_plans import sources,prepare,matrix
        p=example('rc');cid=design.new_cell(p,'counter',digital.counter_project()['digital'])
        p['simulation_setups']=[{'name':'Analog','cell':p['top'],'engine':'builtin','settings':p['analysis']}]
        plan={'id':'mixed','name':'Mixed plan','entries':sources(p),'corners':['nominal'],'temperatures':[0,27,85]}
        jobs=prepare(p,plan,lambda settings,engine,project,cid:dict(settings=settings,engine=engine,project=project,cell=cid))
        self.assertEqual(len(jobs),4);rtl=jobs[-1];self.assertIsNone(rtl['case']['labels']['temperature'])
        with self.assertRaisesRegex(ValueError,'no analog'):design.require_analog_implementations(p,cid)
        result=matrix([dict(id='rtl',job=rtl,state='Complete',result={'result_type':'digital','digital_result':{'stage':'simulate'}})],rtl['case']['group'])
        self.assertEqual(next(iter(result['rows'][0]['values'].values()))['status'],'PASS')

    def test_physical_geometry_units_and_orientation(self):
        from icstudio.digital_physical import preview
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'cell.lef').write_text('MACRO cell\n SIZE 2 BY 4 ;\nEND cell\n')
            (root/'chip.def').write_text('UNITS DISTANCE MICRONS 1000 ;\nDIEAREA ( 0 0 ) ( 10000 20000 ) ;\nCOMPONENTS 1 ;\n- u cell + PLACED ( 1000 2000 ) E ;\nEND COMPONENTS\nNETS 1 ;\n- n ( u A ) ( PIN n ) + ROUTED met1 ( 1000 2000 ) ( * 7000 ) ;\nEND NETS\n')
            data=preview(root/'chip.def',[root/'cell.lef']);self.assertEqual(data['die'],[0,0,10,20])
            self.assertEqual(data['components'][0]['width'],4);self.assertEqual(data['segments'][0]['points'],[[1,2],[1,7]])


@unittest.skipUnless(tool('iverilog') and tool('vvp') and tool('verilator') and tool('verilator_coverage'),'Install Icarus and Verilator with coverage')
class DigitalRegressionTests(unittest.TestCase):
    def test_uart_cases_coverage_and_failed_assertion(self):
        from icstudio.digital_examples import uart_project
        p=uart_project();p['digital']['timeout']=180
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job=flow.prepare(p,'regression');result=flow.run(job,root/'pass')
            cases=result['digital_result']['regression']['cases']
            self.assertEqual([c['status'] for c in cases],['PASS','PASS'])
            self.assertGreater(cases[1]['coverage']['total'],0)
            self.assertIn('uart_tx.sv',[f['path'] for f in cases[1]['coverage']['files']])
            p['digital']['tests']=p['digital']['tests'][:1]
            p['digital']['files'][0]['text']=p['digital']['files'][0]['text'].replace("frame <= {1'b1, data, 1'b0}","frame <= {1'b1, ~data, 1'b0}")
            failed=flow.run(flow.prepare(p,'regression'),root/'fail')
            self.assertEqual(failed['digital_result']['verdict'],'FAIL')
            self.assertIn('mismatch',failed['digital_result']['regression']['cases'][0]['error'])


ORFS=os.environ.get('ICSTUDIO_TEST_ORFS')


@unittest.skipUnless(ORFS and tool('yosys'),'Set ICSTUDIO_TEST_ORFS and install Yosys for real implementation tests')
class DigitalImplementationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        evidence=os.environ.get('ICSTUDIO_TEST_EVIDENCE')
        cls.temporary=None if evidence else tempfile.TemporaryDirectory()
        cls.root=Path(evidence).resolve() if evidence else Path(cls.temporary.name)
        cls.project=digital.counter_project();cls.project['digital']['platform']=platform.from_orfs(ORFS)
        cls.project['digital']['timeout']=300
        cls.mapped=cls.root/'mapped';cls.result=cls.run_stage(cls.project,'mapped',cls.mapped)

    @classmethod
    def tearDownClass(cls):
        if cls.temporary:cls.temporary.cleanup()

    @classmethod
    def run_stage(cls,p,stage,root,upstream=None):
        job=flow.prepare(p,stage,tools={n:tool(n) for n in ('yosys','sta','openroad','eqy','make','klayout') if tool(n)},upstream=upstream,orfs=ORFS)
        root.mkdir(parents=True);atomic_write(root/'input.json',json.dumps(job))
        result=flow.run(job,root);atomic_write(root/'result.json',json.dumps(result));job_store.state(root,'complete')
        return job_store.read_result(root/'result.json',p['id'])

    def test_mapped_cells_published_symbol_and_stale_rejection(self):
        result=self.result;self.assertGreater(result['digital_result']['statistics']['area_um2'],0)
        data=json.loads((self.mapped/'netlist.json').read_text());cells=data['modules']['counter']['cells']
        self.assertTrue(all(c['type'].startswith('sky130_fd_sc_hd__') for c in cells.values()))
        p=clone(self.project);ports=design.publish_interface(p,p['top'],result,self.mapped);validate(p)
        self.assertEqual(set(ports),{'clk','reset','count[0]','count[1]','count[2]','count[3]'})
        p['digital']['files'][0]['text']+='\n// edit'
        self.assertEqual(design.views(p,p['top'])[-1]['state'],'Stale')
        with self.assertRaisesRegex(ValueError,'changed'):design.publish_interface(p,p['top'],result,self.mapped)
        from icstudio.digital_implementation import capture_upstream
        with self.assertRaisesRegex(ValueError,'changed'):capture_upstream(p,p['top'],self.mapped)

    @unittest.skipUnless(tool('sta'),'Install OpenSTA')
    def test_timing_real_paths_clock_failure_and_unconstrained(self):
        passing=self.run_stage(self.project,'timing',self.root/'timing',self.mapped)['digital_result']
        self.assertEqual(passing['verdict'],'PASS');self.assertGreater(passing['timing']['summary']['setup_worst_slack_ns'],1)
        self.assertGreater(passing['power']['total_w'],0)
        p=clone(self.project);sdc=next(f for f in p['digital']['files'] if f['role']=='constraint')
        sdc['text']=sdc['text'].replace('-period 10','-period 0.01')
        failing=self.run_stage(p,'timing',self.root/'timing-fail',self.mapped)['digital_result']
        self.assertEqual(failing['verdict'],'FAIL')
        sdc['text']='\n';incomplete=self.run_stage(p,'timing',self.root/'timing-unconstrained',self.mapped)['digital_result']
        self.assertEqual(incomplete['verdict'],'INCOMPLETE')

    @unittest.skipUnless(tool('eqy'),'Install EQY with its Yosys plugins')
    def test_equivalence_actual_mapped_netlist_and_fault(self):
        good=self.run_stage(self.project,'equivalence',self.root/'equivalent',self.mapped)
        self.assertEqual(good['digital_result']['verdict'],'PASS')
        # Inject a gate-level fault into a separate captured fixture, retaining the RTL reference.
        faulty=self.root/'faulty-gate';shutil.copytree(self.mapped,faulty)
        netlist=faulty/'netlist.v';text=netlist.read_text()
        broken,count=re.subn(r'\.D\([^)]*\)',".D(1'b0)",text,count=1)
        self.assertEqual(count,1,'Counter mapping must contain a state register')
        netlist.write_text(broken)
        result=json.loads((faulty/'result.json').read_text());result['digital_result']['artifacts']['netlist']=flow.artifact(faulty,netlist)
        atomic_write(faulty/'result.json',json.dumps(result))
        bad=self.run_stage(self.project,'equivalence',self.root/'inequivalent',faulty)
        self.assertEqual((self.root/'inequivalent/netlist.v').read_text(),broken,'The proof must consume the injected gate-level fault')
        self.assertEqual(bad['digital_result']['verdict'],'FAIL',(self.root/'inequivalent/engine.log').read_text()[-5000:])

    @unittest.skipUnless(tool('openroad') and tool('klayout') and os.environ.get('ICSTUDIO_TEST_PHYSICAL'),'Set ICSTUDIO_TEST_PHYSICAL=1 for all ORFS stages')
    def test_physical_checkpoints_resume_gds_and_extracted_timing(self):
        previous=self.mapped;p=clone(self.project)
        # A macro gets its logical interface from the actual compiled ports.
        design.publish_interface(p,p['top'],self.result,self.mapped)
        for stage in ('floorplan','place','cts','route','finish'):
            root=self.root/stage;result=self.run_stage(p,stage,root,previous)
            self.assertEqual(result['digital_result']['physical']['resumed'],stage!='floorplan')
            self.assertGreater(len(json.loads((root/'layout_preview.json').read_text())['components']),0)
            previous=root
        self.assertGreater((previous/'physical/results/sky130hd/counter/base/6_final.gds').stat().st_size,1000)
        from icstudio.digital_layout import attach
        attach(p,p['top'],result,previous);validate(p)
        c=design.cell(p,p['top']);self.assertTrue(c['layout_instances']);self.assertEqual({v['name'] for v in c['layout_ports']},set(c['ports']))
        timed=self.run_stage(p,'timing',self.root/'extracted-timing',previous)
        self.assertEqual(timed['digital_result']['timing']['parasitics'],'extracted SPEF')
        self.assertIn('layout_preview',timed['digital_result']['artifacts'])
        self.assertTrue(timed['digital_result']['timing']['paths'])


if __name__=='__main__':unittest.main()
