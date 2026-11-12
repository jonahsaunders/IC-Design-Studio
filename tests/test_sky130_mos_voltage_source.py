import ast, contextlib, copy, io, json, math, pathlib, shutil, tempfile, unittest
from decimal import Decimal, localcontext
from fractions import Fraction
from unittest import mock
from scripts.qualification_sky130_mos_voltage_core import ROOT, VoltageScreen, main, exact_json

P='sky130_fd_pr__'
class SourceVoltageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.screen=VoltageScreen()
    def point(self,name='nfet_01v8',**changes):
        point=dict(model=P+name,vds=1,vgs=1,vbs=0,temperature_c=27)
        point.update(changes)
        return self.screen.check(point)
    def test_every_documented_axis_at_limits_and_one_ulp_outside(self):
        visits=0
        for model,row in self.screen.rows.items():
            limits=row['model_voltage_limits_v']
            if not limits: continue
            for axis,(lower,upper) in limits.items():
                base={k:(a+b)/2 for k,(a,b) in limits.items()}
                for edge in (lower,upper):
                    with self.subTest(model=model,axis=axis,edge=edge):
                        p=dict(model=model,temperature_c=27,**base);p[axis]=edge
                        self.assertEqual(self.screen.check(p)['three_axis_status'],'WITHIN_DOCUMENTED_LIMITS')
                        p[axis]=math.nextafter(edge,-math.inf if edge==lower else math.inf)
                        self.assertEqual(self.screen.check(p)['three_axis_status'],'OUTSIDE_DOCUMENTED_LIMITS')
                        visits+=1
        self.assertEqual(visits,102)
    def test_conditional_nmos_16v_at_zero_gate_only(self):
        self.assertEqual(self.point('nfet_g5v0d16v0',vds=16,vgs=0)['three_axis_status'],'WITHIN_DOCUMENTED_LIMITS')
        for gate in (math.nextafter(0,1),.001,5.5):
            result=self.point('nfet_g5v0d16v0',vds=16,vgs=gate)
            self.assertEqual(result['three_axis_status'],'OUTSIDE_DOCUMENTED_LIMITS')
            self.assertEqual(result['applied_bounds_v']['vds'],[0,11])
    def test_conditional_pmos_and_wrong_gate_sign(self):
        self.assertEqual(self.point('pfet_g5v0d16v0',vds=-16,vgs=-0.0)['three_axis_status'],'WITHIN_DOCUMENTED_LIMITS')
        for gate in (-1e-300,-.001,-5.5):
            self.assertEqual(self.point('pfet_g5v0d16v0',vds=-11,vgs=gate)['three_axis_status'],'OUTSIDE_DOCUMENTED_LIMITS')
        self.assertEqual(self.point('pfet_g5v0d16v0',vds=-16,vgs=1e-300)['three_axis_status'],'OUTSIDE_DOCUMENTED_LIMITS')
    def test_signed_polarity_and_body_asymmetry(self):
        self.assertEqual(self.point('pfet_01v8',vds=1.95,vgs=1.95)['three_axis_status'],'OUTSIDE_DOCUMENTED_LIMITS')
        self.assertEqual(self.point('nfet_01v8',vbs=.3)['three_axis_status'],'WITHIN_DOCUMENTED_LIMITS')
        self.assertEqual(self.point('pfet_01v8',vds=-1,vgs=-1,vbs=-.3)['three_axis_status'],'OUTSIDE_DOCUMENTED_LIMITS')
        self.assertEqual(self.point('nfet_03v3_nvt',vbs=.3)['three_axis_status'],'OUTSIDE_DOCUMENTED_LIMITS')
    def test_no_sample_or_nominal_temperature_becomes_valid_range(self):
        for temp in (-55,-40,0,27,30,85,125,155):
            r=self.point(temperature_c=temp)
            self.assertEqual(r['temperature_validity_status'],'NOT_ESTABLISHED')
            self.assertEqual(r['rated_operating_bounds_status'],'NOT_ESTABLISHED')
            self.assertEqual(r['full_operating_envelope_status'],'NOT_ESTABLISHED')
            self.assertFalse(r['qualified'])
            self.assertEqual(r['temperature_is_historical_sample_point'],temp in (0,27,85))
    def test_model_label_is_not_model_validity_or_failure_voltage(self):
        self.assertEqual(self.point(vds=1.95,vgs=1.95)['three_axis_status'],'WITHIN_DOCUMENTED_LIMITS')
        self.assertEqual(self.point(vds=1.98)['three_axis_status'],'OUTSIDE_DOCUMENTED_LIMITS')
        self.assertEqual(self.point('nfet_g5v0d10v5',vgs=7.3)['three_axis_status'],'OUTSIDE_DOCUMENTED_LIMITS')
        self.assertEqual(self.point('nfet_20v0',vds=22,vgs=5.5,vbs=-2)['three_axis_status'],'WITHIN_DOCUMENTED_LIMITS')
        self.assertEqual(self.point('nfet_20v0',vds=22)['soa_status'],'SOURCE_REQUIRED_NOT_ESTABLISHED')
    def test_fifth_terminal_range_stays_unknown(self):
        r=self.point('nfet_20v0_iso',vds=22,vgs=5.5,vbs=-2)
        self.assertEqual(r['all_terminal_voltage_status'],'NOT_ESTABLISHED')
        self.assertFalse(r['qualified'])
    def test_ambiguous_esd_and_public_native_alias_fail_closed(self):
        for name in ('esd_nfet_01v8','esd_nfet_g5v0d10v5','esd_nfet_g5v0d10v5_nvt','esd_nfet_05v0_nvt'):
            self.assertEqual(self.point(name)['three_axis_status'],'BLOCKED')
        with self.assertRaises(ValueError):self.point('nfet3_01v8')
    def test_invalid_numbers_missing_and_extra_fields_fail(self):
        for value in (True,False,'1',float('nan'),float('inf'),None):
            for field in ('vds','vgs','vbs','temperature_c'):
                with self.subTest(value=value,field=field):
                    with self.assertRaises(ValueError):self.point(**{field:value})
        with self.assertRaises(ValueError):self.point(sub=0)
        with self.assertRaises(ValueError):self.point(qualified=True)
        with self.assertRaises(ValueError):self.screen.check({'model':P+'nfet_01v8'})
    def test_source_table_lock_and_model_examples_tampering_rejected(self):
        # One changed document, one changed nominal card and two changed policy
        # artifacts, authenticated through the normal loading entry point.
        targets=['sources/device-details.rst','sources/hv.rst','sources/LICENSE','gap-acceptance-table.json','source-lock.json']
        lock=json.loads((ROOT/'source-lock.json').read_bytes())
        targets.append(lock['model_nominal_examples'][0]['file'])
        for target in targets:
            with self.subTest(target=target),tempfile.TemporaryDirectory() as td:
                dest=pathlib.Path(td)/'contract';shutil.copytree(ROOT/'sources',dest/'sources')
                for name in ('gap-acceptance-table.json','source-lock.json'):shutil.copyfile(ROOT/name,dest/name)
                with (dest/target).open('ab') as f:f.write(b'\nchanged\n')
                with self.assertRaises(ValueError):VoltageScreen(dest)
    def test_existing_core_runner_has_identical_three_axis_transcription(self):
        # Read-only AST inspection, not import/execution or re-running sweeps.
        path=pathlib.Path(__file__).resolve().parents[1]/'scripts/qualify_sky130_mos_bias.py'
        tree=ast.parse(path.read_text())
        node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='LIMITS' for t in n.targets))
        old=ast.literal_eval(node.value)
        self.assertEqual(len(old),11)
        for name,(drain,gate,body,_) in old.items():
            self.assertEqual(self.screen.rows[P+name]['model_voltage_limits_v'],dict(vds=list(drain),vgs=list(gate),vbs=list(body)))

class ExactJsonVoltageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.screen=VoltageScreen()

    def run_cli(self, model='nfet_01v8', **coordinates):
        fields=dict(vds='1', vgs='1', vbs='0', temperature_c='27')
        fields.update(coordinates)
        raw='[{"model":'+json.dumps(P+model)+','+','.join(
            json.dumps(k)+':'+v for k,v in fields.items())+'}]'
        with tempfile.TemporaryDirectory() as td:
            path=pathlib.Path(td)/'points.json';path.write_text(raw)
            stream=io.StringIO()
            with mock.patch('sys.argv', ['screen',str(path)]),contextlib.redirect_stdout(stream):
                code=main()
        return code,json.loads(stream.getvalue(),parse_float=Decimal)['results'][0]

    def test_json_nonzero_underflow_cannot_select_either_extended_drain(self):
        for model,drain,gate in [('nfet_g5v0d16v0','16','1e-400'),
                                 ('pfet_g5v0d16v0','-16','-1e-400')]:
            with self.subTest(model=model):
                code,r=self.run_cli(model,vds=drain,vgs=gate)
                self.assertEqual(code,2)
                self.assertEqual(r['drain_predicate'],'ordinary_or_conducting_limit')
                self.assertEqual(r['coordinates_v']['vgs'],Decimal(gate))
                self.assertNotEqual(r['coordinates_v']['vgs'],0)
                for zero in ('0','-0.0','0e-400','-0e-400'):
                    code,r=self.run_cli(model,vds=drain,vgs=zero)
                    self.assertEqual(code,0)
                    self.assertEqual(r['drain_predicate'],'exact_zero_gate_extended_drain_limit')
                    self.assertFalse(r['qualified'])
                    self.assertEqual(r['soa_status'],'SOURCE_REQUIRED_NOT_ESTABLISHED')

    def test_every_source_decimal_boundary_against_independent_rational_oracle(self):
        # Fraction arithmetic is exact and independent of Decimal's current
        # precision. Probe beyond binary resolution on both sides of all axes.
        rows=json.loads((ROOT/'gap-acceptance-table.json').read_bytes(),parse_float=Fraction)['models']
        visits=0
        for row in rows:
            limits=row['model_voltage_limits_v']
            if not limits: continue
            for axis,(lower,upper) in limits.items():
                for edge,direction in ((lower,-1),(upper,1)):
                    with localcontext() as ctx:
                        ctx.prec=100
                        exact=Decimal(edge.numerator)/Decimal(edge.denominator) if isinstance(edge,Fraction) else Decimal(edge)
                        outside=exact+Decimal(direction)*Decimal('1e-70')
                    for value in (exact,outside):
                        kwargs={k:'0' for k in limits}
                        # An ordinary, nonzero gate ensures conditional drain
                        # ranges do not replace the ordinary source bounds.
                        kwargs['vgs']='0.1' if 'nfet' in row['model'] else '-0.1'
                        kwargs[axis]=str(value)
                        with self.subTest(model=row['model'],axis=axis,value=str(value)),localcontext() as ctx:
                            ctx.prec=3
                            code,r=self.run_cli(row['model'].removeprefix(P),**kwargs)
                        expected=lower <= Fraction(value) <= upper
                        violation=any(v['axis']==axis for v in r['violations'])
                        self.assertEqual(violation,not expected)
                        self.assertEqual(r['coordinates_v'][axis],value)
                    visits+=1
        self.assertEqual(visits,102)

    def test_extended_drain_decimal_boundaries_and_exact_cancellation_residue(self):
        for model,edge,sign in [('nfet_g5v0d16v0',16,1),('pfet_g5v0d16v0',-16,-1)]:
            with localcontext() as ctx:
                ctx.prec=100
                outside=Decimal(edge)+Decimal(sign)*Decimal('1e-70')
            code,r=self.run_cli(model,vds=str(outside),vgs='0')
            self.assertEqual(code,2)
            self.assertEqual(r['drain_predicate'],'exact_zero_gate_extended_drain_limit')
            self.assertTrue(any(v['axis']=='vds' for v in r['violations']))
            # Input coordinates are already source-relative, not terminal
            # potentials. Preserve a residual that binary subtraction would lose.
            residual=Fraction(10**70+sign,10**70)-1
            with localcontext() as ctx:
                ctx.prec=100
                gate=Decimal(residual.numerator)/Decimal(residual.denominator)
            code,r=self.run_cli(model,vds=str(edge),vgs=str(gate))
            self.assertEqual(code,2)
            self.assertEqual(Fraction(r['coordinates_v']['vgs']),residual)
            self.assertEqual(r['drain_predicate'],'ordinary_or_conducting_limit')

    def test_signed_decimal_and_integer_extremes_remain_exact(self):
        for literal in ('1e400','-1e400',str(10**400)):
            code,r=self.run_cli(vds=literal)
            self.assertEqual(code,2)
            self.assertEqual(Fraction(r['coordinates_v']['vds']),Fraction(literal))
        for literal in ('1.9500000000000000000000000000000000000001',):
            code,r=self.run_cli(vds=literal)
            self.assertEqual(code,2)
            self.assertEqual(r['coordinates_v']['vds'],Decimal(literal))
        code,r=self.run_cli('pfet_01v8',vds='-1.9500000000000000000000000000000000000001',vgs='-1')
        self.assertEqual(code,2)
        code,r=self.run_cli(vbs='-1e-400',temperature_c='27.000000000000000000000000000000000001')
        self.assertEqual(code,0)
        self.assertFalse(r['temperature_is_historical_sample_point'])
        self.assertEqual(r['temperature_validity_status'],'NOT_ESTABLISHED')

    def test_decimal_nonfinite_and_json_constants_fail_closed(self):
        for value in (Decimal('NaN'),Decimal('sNaN'),Decimal('Infinity'),Decimal('-Infinity')):
            with self.assertRaises(ValueError):
                self.screen.check(dict(model=P+'nfet_01v8',vds=value,vgs=1,vbs=0,temperature_c=27))
            with self.assertRaises(ValueError):exact_json(value)
        for value in ('NaN','Infinity','-Infinity','true','"1"'):
            with self.assertRaises(ValueError):self.run_cli(vds=value)

    def test_decimal_ambiguous_model_and_fifth_terminal_stay_unknown(self):
        code,r=self.run_cli('esd_nfet_01v8',vgs='1e-400')
        self.assertEqual(code,2)
        self.assertEqual(r['three_axis_status'],'BLOCKED')
        self.assertFalse(r['qualified'])
        code,r=self.run_cli('nfet_20v0_iso',vds='22.0',vgs='5.5',vbs='-2.0')
        self.assertEqual(code,0)
        self.assertEqual(r['all_terminal_voltage_status'],'NOT_ESTABLISHED')
        self.assertFalse(r['qualified'])

if __name__=='__main__':unittest.main(verbosity=2)
