import tempfile,unittest,json
from pathlib import Path
from icstudio.sky130_flow import subcircuit,logic_metrics,run,TOP

class Sky130FlowTests(unittest.TestCase):
    def test_missing_assets_fail_closed_and_write_each_stage(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);r=run(root/'absent',root/'run',ngspice='not-an-installed-tool',magic='not-an-installed-tool',netgen='not-an-installed-tool')
            self.assertEqual(r['status'],'blocked');self.assertEqual(r['stages'][0]['status'],'failed');self.assertTrue(all(s['status']=='not_run' for s in r['stages'][1:]));self.assertEqual(json.loads((root/'run/report.json').read_text()),r)
    def test_reference_parser_handles_continuations_without_guessing(self):
        text='.subckt '+TOP+' A VGND\n+ VNB VPB VPWR Y\nX0 VGND A Y VNB nfet w=0.65 l=0.15\n.ends\n'
        ports,body,source=subcircuit(text,TOP);self.assertEqual(ports,['A','VGND','VNB','VPB','VPWR','Y']);self.assertIn('nfet',body)
        with self.assertRaises(ValueError):subcircuit(text,'wrong')
    def test_logic_gate_rejects_flat_or_nonfinite_output(self):
        xs=[i*1e-10 for i in range(621)];vin=[1.8 if t>2e-9 and (t-2e-9)%20e-9<10e-9 else 0 for t in xs]
        for out in ([0]*len(xs),[float('nan')]*len(xs)):
            with self.assertRaises(ValueError):logic_metrics({'x':xs,'traces':{'vin':vin,'vout':out}})
