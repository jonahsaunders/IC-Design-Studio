"""Execute actual capture-function bodies with deterministic coarse/precise clocks."""
import ast,hashlib,json,math,os,re,tempfile,types,unittest
from pathlib import Path
from unittest.mock import Mock
from scripts import audit_installed_sky130_pw2dn_native as auditor
ROOT=Path(__file__).resolve().parents[1]
CASES=(('icstudio/pw2dn_native_probe.py','captured','original_execute'),('scripts/audit_installed_sky130_pw2dn_native.py','capture','original'))

def capture_function(path,name,clock,execute):
    # No duplicated producer implementation: compile the actual nested function body.
    tree=ast.parse((ROOT/path).read_text());matches=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name]
    assert len(matches)==1
    module=ast.fix_missing_locations(ast.Module(body=[matches[0]],type_ignores=[]))
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    def require(ok,message):
        if not ok:raise ValueError(message)
    def write(p,value):Path(p).write_text(json.dumps(value,allow_nan=False))
    scope=dict(Path=Path,time=clock,os=os,re=re,math=math,file_digest=sha,sha=sha,require=require,write=write,invocations=[],original_execute=execute,original=execute)
    exec(compile(module,str(ROOT/path),'exec'),scope)
    return scope[name]

class ElapsedClockTests(unittest.TestCase):
    def run_capture(self,path,name,delta,error=False):
        clock=types.SimpleNamespace(monotonic=Mock(return_value=100.0),perf_counter_ns=Mock(side_effect=[10**18,10**18+delta]))
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=root/'result.raw';deck=root/'input.cir';raw.write_text('fixture raw');deck.write_text('fixture\n.op\n.end\n')
            native=Mock(side_effect=RuntimeError('native failure') if error else None,return_value='fixture log')
            f=capture_function(path,name,clock,native);command=['ngspice','-r',str(raw),str(deck)]
            if error:
                with self.assertRaisesRegex(RuntimeError,'native failure'):f(command,root,timeout=180,env={'FIXTURE':'1'})
            else:self.assertEqual(f(command,root,timeout=180,env={'FIXTURE':'1'}),'fixture log')
            rec=json.loads((root/'native-invocation.json').read_text())
            self.assertEqual(rec['seconds'],delta/1_000_000_000);self.assertEqual(rec['timeout'],180)
            self.assertEqual(rec['status'],'FAIL' if error else 'PASS');self.assertEqual(rec['command'],command);self.assertEqual(rec['environment'],{'FIXTURE':'1'})
            clock.monotonic.assert_not_called();self.assertEqual(clock.perf_counter_ns.call_count,2);native.assert_called_once()
            if not error:
                self.assertEqual(rec['analysis'],'op')
                if delta<=0:
                    with self.assertRaisesRegex(ValueError,'Changed native timing/analysis contract'):
                        auditor.completed(root,'op',Path('ngspice'),{'FIXTURE':'1'},root,'input.cir','result.raw')
            return rec
    def test_sub_tick_duration_both_captures(self):
        for path,name,_ in CASES:
            with self.subTest(path=path):self.assertGreater(self.run_capture(path,name,100)['seconds'],0)
    def test_failure_receipts_use_same_precise_clock(self):
        for path,name,_ in CASES:
            with self.subTest(path=path):self.run_capture(path,name,1_234_567,error=True)
    def test_zero_and_negative_not_clamped_or_accepted(self):
        for path,name,_ in CASES:
            for delta in (0,-1):
                with self.subTest(path=path,delta=delta):self.run_capture(path,name,delta)
    def test_integer_difference_before_conversion(self):
        for path,name,_ in CASES:
            with self.subTest(path=path):self.assertEqual(self.run_capture(path,name,1)['seconds'],1e-9)
if __name__=='__main__':unittest.main()
