import unittest
from scripts import ihp_pmos_measured_reference_v2 as m

class MeasuredReferenceTests(unittest.TestCase):
    def setUp(self): self.data=m.DATA.read_bytes()
    def test_authenticated_grid_and_signs(self):
        rows=m.parse(self.data);self.assertEqual(len(rows),140)
        self.assertEqual(rows[0]['currents']['d'],'7.3648E-10')
        self.assertLess(float(rows[1]['currents']['d']),0)
        self.assertEqual(rows[-1]['vg'],'-1.35')
    def test_tamper_even_whitespace(self):
        with self.assertRaises(ValueError):m.parse(self.data+b'\n')
    def test_temperature_semantics(self):
        with self.assertRaises(ValueError):m.parse(self.data.replace(b'27.0000',b'26.8500'),False)
    def test_missing_block(self):
        with self.assertRaises(ValueError):m.parse(self.data[:self.data.rfind(b'BEGIN_DB')],False)
    def test_duplicate_block(self):
        with self.assertRaises(ValueError):m.parse(self.data+self.data[self.data.rfind(b'BEGIN_DB'):],False)
    def test_duplicate_and_missing_point(self):
        line=next(l for l in self.data.splitlines(True) if b'7.3648e-10' in l)
        for replacement in (b'',line+line):
            with self.subTest(replacement=replacement):
                with self.assertRaises(ValueError):m.parse(self.data.replace(line,replacement),False)
    def test_nonfinite(self):
        for v in (b'NaN',b'Infinity',b'-Infinity'):
            with self.assertRaises(ValueError):m.parse(self.data.replace(b'7.3648e-10',v),False)
    def test_duplicate_metadata(self):
        with self.assertRaises(ValueError):m.parse(self.data.replace(b'  MAIN.M "1"',b'  MAIN.M "1"\n  MAIN.M "1"'),False)
    def test_reordered_columns(self):
        with self.assertRaises(ValueError):m.parse(self.data.replace(b'#vd                    id                    ig',b'#vd                    ig                    id'),False)
    def test_residuals_do_not_decide_acceptance(self):
        rows=m.parse(self.data);s=[{t:float(r['currents'][t])+1 for t in ('d','g','s','b')} for r in rows]
        r=m.residuals(rows,s);self.assertFalse(r['qualified']);self.assertIsNone(r['measurement_residual_acceptance'])
        self.assertAlmostEqual(r['points'][0]['terminals']['d']['signed_residual_a'],1)
    def test_output_rejects_nonfinite_or_missing(self):
        rows=m.parse(self.data);s=[{t:0 for t in ('d','g','s','b')} for r in rows]
        with self.assertRaises(ValueError):m.residuals(rows,s[:-1])
        s[0]['d']=float('nan')
        with self.assertRaises(ValueError):m.residuals(rows,s)
    def test_deck_exact_interface(self):
        d=m.deck('test','nominal','-.446')
        for value in ('.temp 27','w=10u l=10u ng=1 m=1','as=3.4p ad=3.4p ps=20.68u pd=20.68u','XDUT d g s b','mos_tt'):
            self.assertIn(value,d)
        self.assertIn('m=2',m.deck('test','multiplicity-2','-.446'))
        self.assertIn('XDUT s g d b',m.deck('test','drain-source-swapped','-.446'))
        with self.assertRaises(ValueError):m.deck('test','unknown','-.446')

class AuditBoundaryTests(unittest.TestCase):
    def test_exact_selection(self):
        from scripts import audit_ihp_pmos_measured_reference_v2 as a
        rows=[{'route':r,'gate_index':i} for r,i in a.selection()]
        a.validate_selection(rows)
        for bad in (rows[:-1],rows+rows[:1],rows[:1]+rows[:-1],list(reversed(rows))):
            with self.assertRaises(ValueError):a.validate_selection(bad)
    def test_timeout_retains_console(self):
        import tempfile, subprocess
        from pathlib import Path
        from unittest.mock import patch
        from scripts import run_ihp_pmos_measured_reference_v2 as r
        def fail(*args,**kwargs):
            kwargs['stdout'].write('native partial output\n')
            raise subprocess.TimeoutExpired(args[0],kwargs['timeout'])
        with tempfile.TemporaryDirectory() as d:
            log=Path(d)/'log'
            with patch.object(r.subprocess,'run',side_effect=fail):
                with self.assertRaises(subprocess.TimeoutExpired):r.execute(['engine'],d,{},log)
            self.assertEqual(log.read_text(),'native partial output\n')
    def test_zero_exit_diagnostic_errors(self):
        from scripts import audit_ihp_pmos_measured_reference_v2 as a
        a.clean_log('Using KLU as Direct Linear Solver\nNo. of Data Rows : 28')
        for text in ('Error on line 3', 'Unknown parameter xyz', 'fatal error loading module', 'could not load module'):
            with self.assertRaises(ValueError):a.clean_log('Using KLU as Direct Linear Solver\n'+text)
    def test_independent_literal_nominal_deck(self):
        expected = """* IHP-PMOS-measured-reference-v1 ABC nominal -.446
.lib "pdk/libs.tech/ngspice/models/cornerMOSlv.lib" mos_tt
.option reltol=1e-8 abstol=1e-16 vntol=1e-13
.option gminsteps=0 srcsteps=0
.option klu
.temp 27
VD d 0 0
VG g 0 -.446
VS s 0 0
VB b 0 0
XDUT d g s b sg13_lv_pmos w=10u l=10u ng=1 m=1 as=3.4p ad=3.4p ps=20.68u pd=20.68u rfmode=0 mm_ok=0
.save i(vd) i(vg) i(vs) i(vb)
.dc VD 0 -1.35 -0.05
.end
"""
        self.assertEqual(m.deck('ABC','nominal','-.446'), expected)
    def test_inventory_changed_missing_extra(self):
        import tempfile
        from pathlib import Path
        from scripts import audit_ihp_pmos_measured_reference_v2 as a
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'data';p.write_bytes(b'x');files={'data':m.sha(p)}
            a.inventory(root,files)
            p.write_bytes(b'y')
            with self.assertRaises(ValueError):a.inventory(root,files)
            p.unlink()
            with self.assertRaises(ValueError):a.inventory(root,files)
            p.write_bytes(b'x');(root/'extra').write_bytes(b'')
            with self.assertRaises(ValueError):a.inventory(root,files)
    def test_inventory_link(self):
        import tempfile
        from pathlib import Path
        from scripts import audit_ihp_pmos_measured_reference_v2 as a
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'data';p.write_bytes(b'x')
            try:(root/'link').symlink_to(p)
            except OSError as exc:
                import os
                if os.name=='nt' and getattr(exc,'winerror',None) in (1,50,1314):
                    self.skipTest('Windows symlink unsupported or privilege unavailable')
                raise
            with self.assertRaises(ValueError):a.inventory(root,{'data':m.sha(p),'link':m.sha(p)})
    def test_unreviewed_runtime_blocks_before_output(self):
        import tempfile
        from pathlib import Path
        from scripts import run_ihp_pmos_measured_reference_v2 as r
        import json
        spec=json.loads((m.ROOT/r.a.CONTRACT).read_text())
        spec['runtime']['osdi']=None
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'fresh'
            with patch.object(r.json,'loads',return_value=spec):
                with self.assertRaisesRegex(ValueError,'authenticated PSP103'):r.run(out,Path(d)/'absent.osdi')
            self.assertFalse(out.exists())


class KluProtocolTests(unittest.TestCase):
    def test_only_selector_changes_all_twenty_decks(self):
        from scripts import ihp_pmos_measured_reference as old
        for route in m.ROUTES:
            for gate in m.GATES:
                text=m.deck('nonce',route,str(gate))
                self.assertEqual(text.count('.option klu\n'),1)
                self.assertEqual(text.replace('.option klu\n',''),old.deck('nonce',route,str(gate)))
    def test_requires_real_backend_readback(self):
        from scripts import audit_ihp_pmos_measured_reference_v2 as a
        marker='Using KLU as Direct Linear Solver'
        for bad in ('', '.option klu', 'Using Sparse as Direct Linear Solver', marker+'\n'+marker, marker+'\nUsing Sparse as Direct Linear Solver'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):a.clean_log(bad)
    def test_contract_preserves_input_accuracy_and_runtime(self):
        import json
        from scripts import audit_ihp_pmos_measured_reference_v2 as a
        new=json.loads((m.ROOT/a.CONTRACT).read_text())
        old=json.loads((m.DATA.parent/'contract.json').read_text())
        self.assertEqual(m.sha(m.ROOT/a.CONTRACT),a.CONTRACT_SHA)
        self.assertEqual(m.sha(m.DATA.parent/'contract.json'),new['predecessor']['sha256'])
        for key in old:
            if key not in ('id','solver_protocol'):self.assertEqual(new[key],old[key])
        for key in old['solver_protocol']:
            if key!='id':self.assertEqual(new['solver_protocol'][key],old['solver_protocol'][key])

if __name__=='__main__':unittest.main()
