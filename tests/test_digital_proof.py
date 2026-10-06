"""Conservative proof-portfolio results and captured solver identity."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from icstudio import digital, digital_flow, digital_implementation, digital_reports
from icstudio.digital_platform import read_manifest
from icstudio.digital_qualification import faulty_mapping


class DigitalProofTests(unittest.TestCase):
    def test_structural_signed_declarations_keep_widths_and_connections(self):
        source='''module signed_name(clk, y);
  input clk;
  output signed [7:0] y;
  wire signed [31:0] ticks;
  wire unsigned_name;
  signed_cell instance0 (.D(ticks[3]), .Q(y[0]));
  // wire signed [2:0] comment;
endmodule
'''
        expected=source.replace('output signed [7:0]','output [7:0]').replace('wire signed [31:0]','wire [31:0]')
        self.assertEqual(digital_implementation.structural_verilog(source),expected)

    def test_fault_targets_a_register_not_a_combinational_d_pin(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);mapped=root/'mapped';mapped.mkdir()
            netlist="""module test(input clk, a, output busy);
  or4 gate0 (
    .A(a), .B(a), .C(a), .D(a), .X(d)
  );
  dff state0 (
    .CLK(clk), .D(d), .Q(busy)
  );
endmodule
"""
            (mapped/'netlist.v').write_text(netlist)
            (mapped/'netlist.json').write_text(json.dumps({'modules':{'test':{'cells':{
                'gate0':{'type':'or4','port_directions':{'A':'input','D':'input','X':'output'}},
                'state0':{'type':'dff','port_directions':{'CLK':'input','D':'input','Q':'output'}}}}}}))
            (mapped/'result.json').write_text(json.dumps({'digital_result':{'artifacts':{}}}))
            folder=faulty_mapping(mapped,root/'fault',output='busy')
            self.assertEqual((folder/'netlist.v').read_text(),netlist.replace('.D(d)',".D(1'b0)"))
            self.assertEqual((mapped/'netlist.v').read_text(),netlist)
            self.assertEqual(json.loads((folder/'qualification_fault.json').read_text())['instance'],'state0')
            with self.assertRaisesRegex(ValueError,'No mapped D-input register'):
                faulty_mapping(mapped,root/'missing',output='unknown')
            self.assertFalse((root/'missing').exists())

    def test_incomplete_induction_can_be_completed_only_by_an_actual_proof(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);first=root/'strategies/frame/smtbmc/status';first.parent.mkdir(parents=True)
            first.write_text('UNKNOWN')
            second=root/'strategies/frame/pdr/status';second.parent.mkdir();second.write_text('PASS')
            self.assertEqual(digital_reports.eqy_report(root)['status'],'ERROR')
            (root/'PASS').touch()
            report=digital_reports.eqy_report(root)
            self.assertEqual(report['status'],'PASS')
            self.assertEqual(report['partitions'][0]['strategies'],[
                {'strategy':'pdr','status':'PASS'},{'strategy':'smtbmc','status':'UNKNOWN'}])
            # A contradictory failure is never hidden by a second PASS marker.
            first.write_text('FAIL');self.assertEqual(digital_reports.eqy_report(root)['status'],'FAIL')
            first.write_text('UNKNOWN');second.write_text('TIMEOUT')
            self.assertEqual(digital_reports.eqy_report(root)['status'],'UNKNOWN')

    def test_external_pdr_solver_is_part_of_captured_job_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);bindir=root/'bin';bindir.mkdir()
            tools={}
            for name in digital_flow.tool_names('equivalence','icarus'):
                path=bindir/name;path.write_text('captured '+name);tools[name]=str(path)
            (root/'cells.lib').write_text('library(test) {}')
            path=root/'platform.json';path.write_text(json.dumps({'version':1,'name':'test','revision':'fixture',
                'corner':'tt','corners':{'tt':['cells.lib']},'files':['cells.lib']}))
            project=digital.counter_project();project['digital']['platform']=read_manifest(path)
            job=digital_flow.prepare(project,'equivalence',tools=tools,toolchain='custom')
            self.assertIn('yosys-abc',job['environment']['executables'])
            (bindir/'yosys-abc').write_text('different solver')
            self.assertNotEqual(digital_flow.environment(job),job['environment'])

    def test_proof_uses_captured_abc_and_bounded_strategies_with_x_propagation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);config=digital.counter_project()['digital'];config['timeout']=60
            names=digital_flow.tool_names('equivalence','icarus')
            runner=SimpleNamespace(config=config,root=root,tools={n:str(root/n) for n in names},
                libraries=lambda:[root/'cells.lib'],env={'ABC':'unrelated-solver'},
                command=lambda *args,**kwargs:None,save_json=lambda *args:None,add_artifact=lambda *args:None)
            with patch.object(digital_implementation,'mapped',return_value={}), \
                 patch.object(digital_reports,'eqy_report',return_value={'status':'UNKNOWN','counterexamples':[]}):
                result=digital_implementation.equivalence(runner)
            self.assertEqual(result['verdict'],'UNKNOWN')
            self.assertEqual(runner.env['ABC'],str(root/'yosys-abc'))
            text=(root/'equivalence.eqy').read_text()
            self.assertIn('engine abc pdr',text);self.assertIn('engine smtbmc bitwuzla',text)
            self.assertEqual(text.count('xprop on'),2);self.assertEqual(text.count('timeout 30'),2)
            self.assertNotIn('assume',text)


if __name__=='__main__':unittest.main()
