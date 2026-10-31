import json
import math
from pathlib import Path
import tempfile
import unittest

from scripts import qualify_sky130_metal_resistors_linked as suite


class LinkedMetalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=suite.contract()
        package=json.loads((suite.ROOT/cls.spec['package']['path']/'package.json').read_bytes())
        cls.tech=package['technology']
        cls.tech.update(package_root=str(suite.ROOT/cls.spec['package']['path']),
                        package_lock={k:package[k] for k in ('id','revision','files')})

    def test_complete_predefined_matrix_and_noise_selection(self):
        rows=suite.logical_rows(self.spec)
        self.assertEqual(len(rows),48)
        self.assertEqual(len({r['tag'] for r in rows}),48)
        self.assertEqual(len(suite.selection(self.spec)),90)
        self.assertEqual(len(suite.selection(self.spec,True)),6)
        self.assertEqual(len(suite.branches(self.spec,rows,'dc')),264)
        self.assertEqual(len(suite.branches(self.spec,rows,'noise')),24)
        self.assertFalse(self.spec['qualified'])

    def test_width_temperature_and_parallel_multiplier_have_independent_effects(self):
        row=dict(model='m1',width_um=2,length_um=5,multiplicity=1,fault=None)
        nominal=suite.resistance(self.spec,row,'tt',30)
        self.assertAlmostEqual(nominal,.125*5/(2-.039),places=14)
        self.assertAlmostEqual(suite.resistance(self.spec,{**row,'multiplicity':3},'tt',30),nominal/3,places=14)
        self.assertGreater(suite.resistance(self.spec,row,'tt',125),nominal)
        self.assertLess(suite.resistance(self.spec,row,'tt',-40),nominal)
        for fault in self.spec['experiment']['faults'][:-1]:
            self.assertNotEqual(suite.resistance(self.spec,{**row,'fault':fault},'tt',30,altered=True),nominal)

    def test_source_export_uses_each_model_and_literal_geometry(self):
        rows=suite.branches(self.spec,suite.logical_rows(self.spec),'ac')
        project=suite.fixture(self.tech,rows,'ac')
        text=suite.spice(project,project['top'],hierarchical=False)
        for m in ('m1','m2','m3','m4'):
            self.assertIn(f'R_D_a_{m}_g1_r0_m3 in_a_{m}_g1_r0_m3 out_a_{m}_g1_r0_m3 sky130_fd_pr__res_generic_{m} l=5 m=3 w=2',text)
        self.assertIn('VDRIVE input 0 DC 0.0005 AC 1',text)
        self.assertIn('VS_a_m1_g0_r0_m1 input in_a_m1_g0_r0_m1 DC 0 AC 0',text)

    def test_actual_native_interface_and_units_cannot_be_reconstructed(self):
        row=dict(model='m4',width_um=2,length_um=5)
        good='.subckt coupon R1 R2\nR0 R2 R1 sky130_fd_pr__res_generic_m4 w=2 l=5\n.ends\n'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'native.spice';path.write_text(good)
            self.assertEqual(suite.read_native(path,row)['terminals'],['R2','R1'])
            for value in (good.replace('m4','m3'),good.replace('w=2','w=2u'),good.replace('l=5','l=2'),
                          good.replace('R2 R1','R1 R1'),good+'.option scale=1u\n',good+'R1 x y 1\n'):
                path.write_text(value)
                with self.assertRaises(ValueError): suite.read_native(path,row)

    def test_exact_transient_solution_dc_limit_and_pulse_edges(self):
        spec=self.spec;r=.3;gain=1/(1+r);e=spec['experiment']
        times=[0,e['pulse_delay_s'],2e-9,5e-9,9e-9,15e-9,20e-9]
        result=suite.transient(spec,r,times)
        self.assertAlmostEqual(result[0],e['pulse_low_v']*gain,places=15)
        self.assertAlmostEqual(result[1],e['pulse_low_v']*gain,places=15)
        self.assertGreater(result[2],result[0])
        self.assertAlmostEqual(result[3],e['pulse_high_v']*gain,places=9)
        self.assertLess(result[4],result[2])
        self.assertTrue(all(math.isfinite(v) for v in result))

    def test_context_title_changes_for_run_case_analysis_and_control(self):
        execution=dict(root='/evidence',nonce='a'*32)
        values=[suite.title(execution,'tt-t27-'+suffix) for suffix in ('dc-positive','ac-positive','dc-wrong-section')]
        values.append(suite.title({**execution,'nonce':'b'*32},'tt-t27-dc-positive'))
        self.assertEqual(len(set(values)),4)

    def test_raw_current_finiteness_and_exact_branch_names_are_required(self):
        text='Title: * fixture\nPlotname: DC transfer characteristic\nFlags: real\nNo. Variables: 2\nNo. Points: 2\nVariables:\n0 v(v-sweep) voltage\n1 i(vs_a) current\nValues:\n0 0\n0\n1 .001\n.0001\n'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'result.raw';path.write_text(text)
            self.assertEqual(suite.read_raw(path,'* fixture','DC transfer characteristic',['v(v-sweep)','i(vs_a)'])[0],[0,.001])
            for bad in (text.replace('.0001\n','nan\n'),text.replace('i(vs_a)','i(vs_b)'),text.replace('Title: * fixture','Title: other')):
                path.write_text(bad)
                with self.assertRaises(ValueError):suite.read_raw(path,'* fixture','DC transfer characteristic',['v(v-sweep)','i(vs_a)'])

    def test_noise_vector_and_native_parallel_calls_are_unique(self):
        logical=suite.logical_rows(self.spec,True)
        rows=suite.branches(self.spec,logical,'noise')
        project=suite.fixture(self.tech,rows,'noise')
        app=suite.spice(project,project['top'],hierarchical=False)
        case=dict(section='tt',temperature_c=27,analysis='noise',control='positive',name='tt-t27-noise-positive')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'native.spice'
            path.write_text('.subckt coupon R1 R2\nR0 R2 R1 sky130_fd_pr__res_generic_m1 w=2 l=5\n.ends\n')
            text,section,temp=suite.deck(self.spec,case,rows,app,{'tt':'.lib pdk-models/lib.spice tt'},
                {'m1-w2-l5-r0':path},dict(root='/evidence',nonce='a'*32))
        self.assertEqual((section,temp),('tt',27))
        self.assertIn('setplot noise11',text)
        self.assertEqual(text.count('XN_n_m1_g1_r0_m3_'),3)
        self.assertIn('let noise_n_m1_g1_r0_m3 = onoise_spectrum',text)
        self.assertEqual(text.count('.include '),1)
        self.assertNotIn('chgtol=',text)
        transient_case={**case,'analysis':'tran','name':'tt-t27-tran-positive'}
        transient_rows=[r for r in rows if r['kind']!='native']
        transient_project=suite.fixture(self.tech,transient_rows,'tran')
        transient_export=suite.spice(transient_project,transient_project['top'],hierarchical=False)
        transient_text,_,_=suite.deck(self.spec,transient_case,transient_rows,transient_export,
            {'tt':'.lib pdk-models/lib.spice tt'},{},dict(root='/evidence',nonce='a'*32))
        self.assertIn('method=gear chgtol=1e-24 trtol=1',transient_text)
        self.assertIn('.tran 20p 21n',transient_text)


if __name__=='__main__':unittest.main()
