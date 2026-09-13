"""Digital input, waveform and real-engine regression tests."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from icstudio import digital, digital_flow, digital_waveform, job_store
from icstudio.model import History, clone, design_digest, load_project, save_project, validate
from icstudio.project_store import save_directory, load_directory

ROOT = Path(__file__).resolve().parents[1]


class DigitalModelTests(unittest.TestCase):
    def test_project_roundtrip_revision_and_undo(self):
        project = digital.counter_project(); before = design_digest(project)
        history = History(project)
        history.commit(lambda p: p['digital']['files'][0].update(text='// edit\n'+p['digital']['files'][0]['text']))
        self.assertNotEqual(before, design_digest(history.project))
        history.undo(); self.assertEqual(history.project['digital'], project['digital'])
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'counter.icproj'; save_project(project,path)
            self.assertEqual(load_project(path)['digital'],project['digital'])
            save_directory(project,Path(td)/'folder')
            self.assertEqual(load_directory(Path(td)/'folder')['digital'],project['digital'])

    def test_invalid_paths_and_conflicting_files(self):
        for path in ('../escape.sv','/absolute.sv','a\\b.sv','a/../b.sv','a//b.sv','a;touch.sv'):
            with self.subTest(path=path), self.assertRaises(ValueError): digital.relative_path(path)
        project = digital.counter_project(); project['digital']['files'].append({'path':'counter.sv/child.sv','role':'rtl','text':''})
        with self.assertRaisesRegex(ValueError,'directory'): validate(project)
        project['digital']['files'][-1]['path']='COUNTER.SV/child.sv'
        with self.assertRaisesRegex(ValueError,'directory'): validate(project)
        for path in ('COUNTER.SV','counter.sv/child.vcd'):
            project=digital.counter_project();project['digital']['waveform']=path
            with self.assertRaisesRegex(ValueError,'overwrite'):validate(project)
        project = digital.counter_project(); project['digital']['files'][1]['path']='COUNTER.SV'
        with self.assertRaisesRegex(ValueError,'unique'): validate(project)

    def test_dependency_closure_and_source_capture(self):
        config = clone(digital.counter_project()['digital'])
        config['files'][0]['text'] = '`include "defs.vh"\n'+config['files'][0]['text']
        with self.assertRaisesRegex(ValueError,'missing include'): digital.check_dependencies(config)
        config['files'].append({'path':'defs.vh','role':'include','text':'`define WIDTH 4\n'})
        digital.check_dependencies(config)
        config['files'][0]['text'] += '\n// `include "missing.vh"\n'
        digital.check_dependencies(config)
        config['files'][0]['text'] += '\n`include `FILE\n'
        with self.assertRaisesRegex(ValueError,'literal'): digital.check_dependencies(config)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root/'dut.sv').write_text('module dut; endmodule')
            (root/'project.json').write_text(json.dumps({'version':1,'top':'dut','files':[{'path':'dut.sv','role':'rtl'}]}))
            captured = digital.read_manifest(root/'project.json'); signature = digital.source_hash(captured)
            (root/'dut.sv').write_text('changed externally')
            self.assertEqual(signature,digital.source_hash(captured))
            self.assertEqual(captured['files'][0]['text'],'module dut; endmodule')

    def test_memory_dependencies(self):
        config = digital.counter_project()['digital']
        config['files'][0]['text'] += '\ninitial $readmemh("rom.hex", mem);\n'
        with self.assertRaisesRegex(ValueError,'initialization'): digital.check_dependencies(config)
        config['files'].append({'path':'rom.hex','role':'data','text':'00\n01\n'})
        digital.check_dependencies(config)

    def test_flow_bundle_is_explicit_unqualified_handoff(self):
        config = digital.counter_project()['digital']
        with tempfile.TemporaryDirectory() as td:
            root = digital_flow.export_flow(config,Path(td)/'flow')
            self.assertEqual((root/'sources/counter.sv').read_text(),config['files'][0]['text'])
            self.assertIn('engine smtbmc bitwuzla',(root/'equivalence.eqy').read_text())
            self.assertIn('PLATFORM = sky130hd',(root/'config.mk').read_text())
            self.assertEqual(json.loads((root/'manifest.json').read_text())['physical_status'],'not_run')
            with self.assertRaisesRegex(ValueError,'empty'): digital_flow.export_flow(config,root)

    def test_analog_result_reader_keeps_original_contract(self):
        from icstudio.simulation import run
        from icstudio.model import example
        project=example(); result=run(project,project['top'],project['analysis'])
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'input.json').write_text(json.dumps({'project':project,'cell':project['top'],'settings':project['analysis']}))
            (root/'result.json').write_text(json.dumps(result)); job_store.state(root,'complete')
            self.assertEqual(job_store.read_result(root/'result.json',project['id'])['traces'],result['traces'])


class DigitalWaveformTests(unittest.TestCase):
    def parse(self, text):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'wave.vcd'; path.write_text(text)
            return digital_waveform.read_vcd(path)

    HEADER = '''$timescale 1 ps $end
$scope module tb $end
$var wire 4 ! count [3:0] $end
$var wire 4 ! alias [3:0] $end
$var wire 1 " clk $end
$upscope $end
$enddefinitions $end
'''

    def test_aliases_x_z_vectors_and_exact_large_ticks(self):
        huge=2**54+3
        data=self.parse(self.HEADER+f'$dumpvars bx ! 0" $end\n#5 b1 ! 1"\n#5 bz !\n#{huge} b1010 !\n')
        self.assertEqual(data['timescale'],'1ps');self.assertEqual(data['end_tick'],huge)
        self.assertEqual(data['signals'][0]['code'],data['signals'][1]['code'])
        changes=data['changes']['!'];self.assertEqual(changes[0],[0,'xxxx']);self.assertEqual(changes[-1],[huge,'1010'])
        self.assertEqual(digital_waveform.value_at(changes,5,4),'zzzz')
        self.assertEqual(digital_waveform.value_at(changes,huge,4),'1010')
        self.assertEqual(digital_waveform.format_value('1010'),'a')
        self.assertEqual(digital_waveform.format_value('10xz'),'10xz')

    def test_rejects_truncation_bad_times_and_oversized_preview(self):
        for suffix in ('#5 b1', '#10 b1 ! #9 b0 !', '#1 b10000 !', '#1 b1 unknown'):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):self.parse(self.HEADER+suffix)
        with self.assertRaises(ValueError):self.parse('$scope module unfinished')
        with patch.object(digital_waveform,'MAX_EVENTS',1), self.assertRaisesRegex(ValueError,'transitions'):
            self.parse(self.HEADER+'#0 b0 ! #1 b1 !')
        with patch.object(digital_waveform,'MAX_VALUE_BYTES',7), self.assertRaisesRegex(ValueError,'Decoded'):
            self.parse(self.HEADER+'#0 bx ! #1 bz !')


def tool(name):
    return os.environ.get('ICSTUDIO_TEST_'+name.upper()) or shutil.which(name)


@unittest.skipUnless(tool('iverilog') and tool('vvp'),'Install Icarus or set ICSTUDIO_TEST_IVERILOG/VVP')
class IcarusIntegrationTests(unittest.TestCase):
    def run_project(self, project, root, stage='simulate', tools=None):
        job=digital_flow.prepare(project,stage,tools=tools or {'iverilog':tool('iverilog'),'vvp':tool('vvp')})
        root.mkdir();(root/'input.json').write_text(json.dumps(job))
        command=[sys.executable,str(ROOT/'main.py'),'--worker',str(root/'input.json'),str(root/'result.json')]
        completed=subprocess.run(command,capture_output=True,text=True,timeout=90)
        job_store.state(root,'complete' if completed.returncode==0 else 'failed')
        return job,completed

    def test_counter_real_worker_results_stale_inputs_and_artifact_integrity(self):
        project=digital.counter_project()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'run with spaces';job,completed=self.run_project(project,root)
            self.assertEqual(completed.returncode,0,completed.stderr+'\n'+completed.stdout[-3000:])
            result=job_store.read_result(root/'result.json',project['id'])
            incomplete=clone(result);incomplete['digital_result']['artifacts'].pop('waveform')
            with self.assertRaisesRegex(ValueError,'required artifacts'):digital_flow.validate_result(incomplete,root)
            self.assertNotIn('traces',result)
            wave=json.loads((root/'waveform.json').read_text()); signal=next(s for s in wave['signals'] if s['name']=='counter_tb.count[3:0]')
            changes=wave['changes'][signal['code']]
            self.assertEqual(digital_waveform.value_at(changes,5000,4),'0000')
            self.assertEqual(digital_waveform.value_at(changes,165000,4),'0000')
            self.assertEqual(changes[-1][1],'0100')
            self.assertIn('checks passed',(root/'engine.log').read_text())
            project['digital']['files'][0]['text']+='\n// changed'
            self.assertNotEqual(design_digest(project),result['design_hash'])
            self.assertEqual(job['project']['digital']['files'][0]['text'],(root/'sources/counter.sv').read_text())
            (root/'waveform.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'changed'):job_store.read_result(root/'result.json',project['id'])

    def test_fault_and_timeout_never_publish_result(self):
        for mode in ('fault','timeout'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
                project=digital.counter_project()
                if mode=='fault':project['digital']['files'][0]['text']=project['digital']['files'][0]['text'].replace("count + 1'b1","count + 2'd2")
                else:
                    project['digital']['timeout']=1
                    project['digital']['files'][1]['text']='module counter_tb; initial forever #1; endmodule'
                root=Path(td)/'run';job,completed=self.run_project(project,root)
                self.assertNotEqual(completed.returncode,0);self.assertFalse((root/'result.json').exists())
                self.assertTrue((root/'engine.log').is_file())

    def test_tool_change_before_execution_is_rejected(self):
        project=digital.counter_project();job=digital_flow.prepare(project,tools={'iverilog':tool('iverilog'),'vvp':tool('vvp')})
        job['environment']['executables']['vvp']='changed'
        with tempfile.TemporaryDirectory() as td,self.assertRaisesRegex(ValueError,'changed'):
            digital_flow.run(job,td)


@unittest.skipUnless(tool('yosys'),'Install Yosys or set ICSTUDIO_TEST_YOSYS')
class YosysIntegrationTests(unittest.TestCase):
    def test_synthesis_and_gate_simulation(self):
        project=digital.counter_project()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'synthesis';root.mkdir()
            job=digital_flow.prepare(project,'synth',tools={'yosys':tool('yosys')})
            result=digital_flow.run(job,root)
            netlist=json.loads((root/'netlist.json').read_text())
            self.assertIn('counter',netlist['modules']);self.assertGreater(len(netlist['modules']['counter']['cells']),0)
            self.assertNotIn('counter_tb',netlist['modules'])
            self.assertEqual(result['digital_result']['stage'],'synth')
            if tool('iverilog') and tool('vvp'):
                project['digital']['files'][0]['text']=(root/'netlist.v').read_text()
                simulation=Path(td)/'gate';simulation.mkdir()
                job=digital_flow.prepare(project,tools={'iverilog':tool('iverilog'),'vvp':tool('vvp')})
                digital_flow.run(job,simulation)
                self.assertIn('checks passed',(simulation/'engine.log').read_text())


@unittest.skipUnless(tool('verilator'),'Install Verilator or set ICSTUDIO_TEST_VERILATOR')
class VerilatorIntegrationTests(unittest.TestCase):
    def test_lint_and_timed_counter_simulation(self):
        project=digital.counter_project()
        with tempfile.TemporaryDirectory() as td:
            for stage in ('lint','simulate'):
                with self.subTest(stage=stage):
                    root=Path(td)/stage;root.mkdir()
                    job=digital_flow.prepare(project,stage,'verilator',{'verilator':tool('verilator')})
                    result=digital_flow.run(job,root)
                    self.assertEqual(result['digital_result']['stage'],stage)
                    if stage=='simulate':
                        self.assertIn('checks passed',(root/'engine.log').read_text())
                        self.assertIn('waveform',result['digital_result']['artifacts'])
            job=digital_flow.prepare(project,'simulate','verilator',{'verilator':tool('verilator')})
            with self.assertRaisesRegex(ValueError,'without spaces'):
                digital_flow.run(job,Path(td)/'run with spaces')


if __name__=='__main__':unittest.main()
