import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import qualify_sky130_li_linked as li
from scripts import audit_sky130_li_linked as independent


class LinkedLiTests(unittest.TestCase):
    def test_contract_sources_and_distinct_passive_sections(self):
        record=li.contract()
        self.assertFalse(record['qualified'])
        self.assertEqual(set(li.PARAMETERS),{'tt','ll','hh','hl','lh'})
        self.assertEqual(len(set(li.PARAMETERS.values())),5)
        for section,expected in li.PARAMETERS.items():
            row=record['corner_contract'][section]
            self.assertEqual(row['rl1_ohm_per_square'],expected[0])
            self.assertAlmostEqual(row['tol_li_um']*1e-6,expected[1],places=20)

    def test_selection_rejects_duplicates_unknown_and_empty(self):
        self.assertEqual(li.selected(['tt'],[0,90]),[('tt',0),('tt',90)])
        for sections,rotations in [([], [0]),(['ss'],[0]),(['tt','tt'],[0]),(['tt'],[]),(['tt'],[0,0]),(['tt'],[180])]:
            with self.assertRaises(ValueError):li.selected(sections,rotations)

    def test_application_source_and_model_dimensions_are_literal_reviewed_values(self):
        tech,_=li.load_technology('sky130A');p=li.fixture(tech,'dc')
        text=li.spice(p,p['top'],li.settings('dc','tt'),hierarchical=False)
        self.assertIn('VDRIVE input 0 DC 0.0005 AC 1',text)
        self.assertIn('R_LI input output '+li.MODEL+' l=5 m=1 w=2',text)
        self.assertIn('.dc VDRIVE 0 0.001',text)

    def test_native_identity_is_read_without_reconstruction(self):
        good='.subckt coupon R1 R2\nR0 R2 R1 '+li.MODEL+' w=2 l=5\n.ends\n'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'native.spice';path.write_bytes(good.encode())
            self.assertEqual(li.read_native(path)['terminals'],['R2','R1'])
            for bad in (good.replace('w=2','w=2u'),good.replace('l=5','l=6'),good.replace('R2 R1','R1 R1'),
                        good.replace(li.MODEL,'bad'),good+'R1 x y 1000\n',good+'.option scale=1e-6\n',good.replace('R1 R2\n','R2 R1\n')):
                path.write_bytes(bad.encode())
                with self.assertRaises(ValueError):li.read_native(path)

    def test_raw_data_needs_complete_channels_parameters_kcl_and_drive(self):
        x=[i*.000025 for i in range(41)]
        names=['v-sweep','v(input)','v(output)','i(vdrive)','v(parameter_rl1)','v(parameter_tol)']
        rows=[[v,v,v*.97,-v*.97/1000,12.2,0] for v in x]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'raw';path.write_bytes(b'fixture')
            with patch.object(li,'parse_raw',return_value=(names,rows,False)):
                result=li.raw_values(path,'dc','vdrive')
                self.assertEqual(result['corner_parameters'],dict(parameter_rl1=12.2,parameter_tol=0))
            changes=[]
            changed=[r[:] for r in rows];changed[-1][3]*=2;changes.append((names,changed))
            changed=[r[:] for r in rows];changed[-1][3]=float('nan');changes.append((names,changed))
            changed=[r[:] for r in rows];changed[-1][4]=12.3;changes.append((names,changed))
            changed=[r[:] for r in rows];changed[-1][1]*=.9;changes.append((names,changed))
            changes.extend([(names,rows[:-1]),(names[:-1],[r[:-1] for r in rows])])
            for altered_names,altered_rows in changes:
                with patch.object(li,'parse_raw',return_value=(altered_names,altered_rows,False)):
                    with self.assertRaises(ValueError):li.raw_values(path,'dc','vdrive')

    def test_fault_zero_response_is_permitted_only_for_negative_control(self):
        names=['v-sweep','v(input)','v(output)','i(vdrive)','v(parameter_rl1)','v(parameter_tol)']
        rows=[[v,v,0,0,12.2,0] for v in [i*.000025 for i in range(41)]]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'raw';path.write_bytes(b'fixture')
            with patch.object(li,'parse_raw',return_value=(names,rows,False)):
                with self.assertRaises(ValueError):li.raw_values(path,'dc','vdrive')
                self.assertEqual(len(li.raw_values(path,'dc','vdrive',False)['x']),41)

    def test_numeric_difference_and_phase_are_not_hidden(self):
        a=dict(x=[100,200],values={'v(output)':[.97+.001j,.97+.002j]})
        self.assertEqual(li.compare(a,a,'ac')['status'],'PASS')
        b=dict(x=a['x'],values={'v(output)':[.97-.001j,.97-.002j]})
        self.assertEqual(li.compare(a,b,'ac')['status'],'MISMATCH')
        b['x']=[100,201]
        with self.assertRaises(ValueError):li.compare(a,b,'ac')

    def test_probes_are_explicit_and_end_is_unambiguous(self):
        text=li.add_probes('* test\n.end\n')
        self.assertIn('parameter_rl1 0 {rl1}',text)
        self.assertIn('parameter_tol 0 {tol_li}',text)
        for text in ('* empty','* test\n.end\n.end\n'):
            with self.assertRaises(ValueError):li.add_probes(text)

    def test_shared_model_nested_includes_are_rooted_without_equation_edits(self):
        text='.lib pdk-models/root.spice tt\n.include pdk-models/nested.spice\n.param x=12.2\n'
        root=Path('/models')
        result=li.absolute_model_references(text,root)
        self.assertEqual(result,'.lib /models/pdk-models/root.spice tt\n.include /models/pdk-models/nested.spice\n.param x=12.2\n')
        self.assertEqual(li.absolute_model_references(result,root),result)

    def test_independent_raw_reader_checks_shape_indices_and_finiteness(self):
        text='Title: test\nFlags: real\nNo. Variables: 2\nNo. Points: 2\nVariables:\n0 v(a) voltage\n1 v(b) voltage\nValues:\n0 0\n1\n1 2\n3\n'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'raw';path.write_bytes(text.encode())
            data,x=independent.raw(path)
            self.assertEqual(x,[0,2]);self.assertEqual(data['v(b)'],[1,3])
            frequency=text.replace('0 v(a) voltage','0 frequency frequency grid=3')
            path.write_bytes(frequency.encode());self.assertEqual(independent.raw(path)[1],[0,2])
            path.write_bytes(frequency.replace('grid=3','arbitrary=3').encode())
            with self.assertRaises(ValueError):independent.raw(path)
            spectral=text.replace('Flags: real','Plotname: Noise Spectral Density Curves\nFlags: real')
            integrated='Title: test\nPlotname: Integrated Noise\nFlags: real\nNo. Variables: 2\nNo. Points: 1\nVariables:\n0 v(onoise_total) voltage\n1 v(inoise_total) voltage\nValues:\n0 0.001\n0.002\n'
            path.write_bytes((spectral+integrated).encode());self.assertEqual(independent.raw(path)[1],[0,2])
            for tail in (integrated.replace('Integrated Noise','Other'),integrated.replace('0.002\n','nan\n'),integrated[:-6]):
                path.write_bytes((spectral+tail).encode())
                with self.assertRaises(ValueError):independent.raw(path)
            for bad in (text.replace('1 2\n','2 2\n'),text.replace('3\n','nan\n'),text.rstrip()[:-1],text.replace('1 v(b)','1 v(a)')):
                path.write_bytes(bad.encode())
                with self.assertRaises((ValueError,IndexError)):independent.raw(path)

    def test_independent_comparator_preserves_complex_phase(self):
        good=([100,200],[.9+.001j,.9+.002j])
        self.assertEqual(independent.compare(good,good,'ac'),0)
        self.assertGreater(independent.compare(good,([100,200],[.9-.001j,.9-.002j]),'ac'),1)

    def test_independent_deck_audit_rejects_manual_substitution_and_wrong_section(self):
        from hashlib import sha256
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'input.cir';execution='/original'
            shared={'staged':{'tt':'.lib /original/shared-models/pdk-models/lib.spice tt'}}
            text='\n'.join([shared['staged']['tt'],'.include /original/physical/l1-w2-l5/physical-0/lvs-extraction/extracted.spice',
                'XEXTRACT input output coupon','VDRIVE input 0 DC .0005 AC 1','RL output 0 1000','CL output 0 1p',
                'VPROBE_RL1 parameter_rl1 0 {rl1}','VPROBE_TOL parameter_tol 0 {tol_li}','.temp 27','.end',''])
            def check(value):
                raw=value.encode();path.write_bytes(raw);(root/'deck-snapshot.cir').write_bytes(raw)
                return independent.deck_identity(path,'extracted','tt',0,execution,shared,sha256(raw).hexdigest())
            self.assertTrue(check(text))
            for changed in (text.replace('XEXTRACT input output coupon','RREF input output sky130_fd_pr__res_generic_l1 w=2 l=5 m=1'),
                            text.replace('lib.spice tt','lib.spice hl'),text.replace('physical-0/','physical-90/'),text.replace('input output coupon','output input coupon')):
                with self.assertRaises(ValueError):check(changed)


if __name__=='__main__':unittest.main()
