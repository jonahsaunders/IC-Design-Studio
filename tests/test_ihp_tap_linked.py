import math
from pathlib import Path
import unittest
from scripts import qualify_ihp_tap_linked as tap

class LinkedTapTests(unittest.TestCase):
    def native(self,model='ntap1',well='well'):
        return f'* public native\n.SUBCKT coupon {well} TIE\nR$1 TIE {well} {model} A=4p P=8u\n.ENDS coupon\n'
    def test_native_geometry_and_identity(self):
        for model,well in (('ntap1','well'),('ptap1','sub!')):
            r=tap.native_tap(self.native(model,well),model,well)
            self.assertEqual(r['model'],model);self.assertEqual(r['terminals'],['TIE',well]);self.assertEqual(r['top_port_order'],[well,'TIE'])
            self.assertAlmostEqual(r['resistance_ohm'],1/(4e-12/9.8e-10+8e-6/9.8e-4))
    def test_port_order_is_explicit_not_assumed(self):
        a=self.native();b=a.replace('.SUBCKT coupon well TIE','.SUBCKT coupon TIE well')
        self.assertEqual(tap.native_tap(a,'ntap1','well')['resistance_ohm'],tap.native_tap(b,'ntap1','well')['resistance_ohm'])
    def test_reject_native_ambiguity(self):
        s=self.native()
        for bad in (s.replace('A=4p P=8u','A=4p A=4p'),s.replace('A=4p','A=nan'),s.replace('A=4p','A=-4p'),s.replace('A=4p','A=5p'),s.replace('P=8u','P=9u'),s.replace(' ntap1 ',' ptap1 '),s.replace('R$1 TIE well','R$1 well TIE'),s+'R$2 TIE well ntap1 A=4p P=8u\n',s.replace('coupon well TIE','coupon well well'),s.replace('A=4p','A={4p}')):
            with self.subTest(bad=bad),self.assertRaises(ValueError):tap.native_tap(bad,'ntap1','well')
    def test_source_proof_is_literal_and_pinned(self):
        tech,_=tap.load_technology('ihp-sg13g2');self.assertEqual(len(tap.source_proof(tech)),3)
    def test_application_keeps_computed_resistance_after_reopen(self):
        import tempfile
        tech,_=tap.load_technology('ihp-sg13g2')
        with tempfile.TemporaryDirectory() as tmp:
            p=tap.project(tech,'ptap1',[]);path=Path(tmp)/'test.icproj';tap.save_project(p,path);q=tap.load_project(path)
            d=next(d for d in q['cells'][0]['devices'] if d['name']=='DUT');line=tap.emit(d,q['pdk']);self.assertIn('ptap1',line);self.assertIn('r=',line.lower())
    def test_feedback_binds_the_complete_additive_source(self):
        from scripts.ci_feedback import UNIT_MODULES,IHP_STAGE_MODULES,source_identity
        self.assertEqual(UNIT_MODULES.count('test_ihp_tap_linked'),1)
        self.assertIn('test_ihp_tap_linked',IHP_STAGE_MODULES)
        files=source_identity()
        for name in ('scripts/qualify_ihp_tap_linked.py','scripts/audit_ihp_tap_linked.py','tests/test_ihp_tap_linked.py'):
            self.assertIn(name,files)
    def test_original_tolerances_unchanged(self):
        self.assertEqual((tap.REL,tap.ABS),(1e-6,1e-10));self.assertEqual(tap.settings('dc')['timeout'],90)
    def test_analytical_dc_and_ac(self):
        r=1/(4e-12/9.8e-10+8e-6/9.8e-4)
        x=[-.01+i*.001 for i in range(21)];v=[f*1000/(r+1000) for f in x]
        self.assertEqual(tap.analytical({'x':x,'traces':{'output':v}},'dc',r),0)
        freq=[100*10**(i/5) for i in range(26)];values=[1000/(r+1000)/(1+2j*math.pi*f/(1/r+1/1000)*1e-12) for f in freq]
        self.assertLess(tap.analytical({'x':freq,'traces':{'output':[abs(v) for v in values]},'phase':{'output':[math.degrees(__import__('cmath').phase(v)) for v in values]}},'ac',r),1)
    def test_nonfinite_or_incomplete_not_a_fault_pass(self):
        good={'x':[-.01+i*.001 for i in range(21)],'traces':{'output':[.001]*21}}
        for bad in ({**good,'x':good['x'][:-1]},{**good,'traces':{'output':[float('nan')]*21}},{**good,'traces':{'output':[0.]*21}}):
            with self.assertRaises(ValueError):tap.response(bad,'dc')
    def test_unknown_fault_rejected(self):
        tech,_=tap.load_technology('ihp-sg13g2')
        with self.assertRaises(ValueError):tap.reference_deck(tech,'ntap1',1,'dc','extracted','ignore')
    def test_all_deck_stimuli_and_loads_independently_checked(self):
        from scripts.audit_ihp_tap_linked import deck_controls
        from icstudio.interchange import spice
        tech,_=tap.load_technology('ihp-sg13g2');p=tap.project(tech,'ntap1',[])
        for a in ('dc','ac'):
            for text in (spice(p,p['top'],tap.settings(a)),tap.reference_deck(tech,'ntap1',81.6666666666667,a,'extracted'),tap.reference_deck(tech,'ntap1',81.6666666666667,a,'independent')):
                deck_controls(text,a)
                for bad in (text.replace('RL output 0 1000','RL output 0 2000'),text.replace('AC 1','AC 2'),text.replace('.temp 27','.temp 85'),text.replace('.end','RX output 0 1\n.end',1)):
                    with self.assertRaises(ValueError):deck_controls(bad,a)
    def test_projection_not_raw_native_execution_claim(self):
        tech,_=tap.load_technology('ihp-sg13g2');s=tap.reference_deck(tech,'ntap1',80,'dc','extracted')
        self.assertIn('XTAP input output ntap1 r=80',s);self.assertIn('explicit electrical',tap.__doc__)


class IndependentRawTapTests(unittest.TestCase):
    def raw(self,folder,analysis='dc',resistance=81.66666666666667,wrong_grid=False):
        import cmath
        from scripts.audit_ihp_tap_linked import raw
        grid=[-.01+i*.001 for i in range(21)] if analysis=='dc' else [100*10**(i/5) for i in range(26)]
        head=['Title: tap','Flags: '+('real' if analysis=='dc' else 'complex'),'No. Variables: 4',f'No. Points: {len(grid)}','Variables:','0 sweep voltage','1 v(input) voltage','2 v(output) voltage','3 i(vdrive) current','Values:'];rows=[]
        for i,x in enumerate(grid):
            value=x if analysis=='dc' else 1;load=.001+(2j*math.pi*x*1e-12 if analysis=='ac' else 0);output=value/(1+resistance*load);current=-output*load
            for k,v in enumerate((x+.01 if wrong_grid else x,value,output,current)):
                text=f'{complex(v).real:.17g},{complex(v).imag:.17g}' if analysis=='ac' else f'{float(v):.17g}'
                rows.append((str(i)+'\t' if k==0 else '\t')+text)
        p=Path(folder)/'test.raw';p.write_text('\n'.join(head+rows)+'\n');return p
    def test_independent_raw_both_analyses(self):
        import tempfile
        from scripts.audit_ihp_tap_linked import compare_raw
        with tempfile.TemporaryDirectory() as d:
            for a in ('dc','ac'):self.assertLess(compare_raw(self.raw(d,a),a,81.66666666666667)['maximum_normalized_response'],1)
    def test_native_padding_and_frequency_grid_metadata(self):
        import tempfile
        from scripts.audit_ihp_tap_linked import raw,compare_raw
        with tempfile.TemporaryDirectory() as d:
            p=self.raw(d,'ac');text=p.read_text().replace('No. Points: 26','No. Points: 26      ').replace('0 sweep voltage','0 frequency frequency grid=3');p.write_text(text)
            self.assertLess(compare_raw(p,'ac',81.66666666666667)['maximum_normalized_response'],1)
            for bad in (text.replace('grid=3','grid=4'),text.replace('1 v(input) voltage','1 v(input) voltage grid=3'),text.replace('0 frequency frequency grid=3','0 frequency voltage grid=3'),text.replace('0 frequency frequency grid=3','1 frequency frequency grid=3'),text.replace('Flags: complex','Flags: real'),text.replace('Flags: complex','Flags: complex extra')):
                p.write_text(bad)
                with self.assertRaises(ValueError):raw(p)
    def test_independent_fault_requires_valid_grid_and_finite_data(self):
        import tempfile
        from scripts.audit_ihp_tap_linked import compare_raw
        with tempfile.TemporaryDirectory() as d:
            p=self.raw(d,resistance=60);self.assertGreater(compare_raw(p,'dc',81.66666666666667,True)['maximum_normalized_response'],1)
            p=self.raw(d,resistance=60,wrong_grid=True)
            with self.assertRaises(ValueError):compare_raw(p,'dc',81.66666666666667,True)
            p=self.raw(d,resistance=60);p.write_text(p.read_text().replace('0.01','nan',1))
            with self.assertRaises(ValueError):compare_raw(p,'dc',81.66666666666667,True)
    def test_incomplete_or_duplicate_raw_rejected(self):
        import tempfile
        from scripts.audit_ihp_tap_linked import raw
        with tempfile.TemporaryDirectory() as d:
            p=self.raw(d);s=p.read_text();p.write_text(s.rsplit('\n',2)[0]+'\n')
            with self.assertRaises(ValueError):raw(p)
            p.write_text(s.replace('3 i(vdrive) current','3 v(output) voltage'))
            with self.assertRaises(ValueError):raw(p)

if __name__=='__main__':unittest.main()
