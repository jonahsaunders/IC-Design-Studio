import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import qualify_sky130_rf_transient as rf


class RFTransientTests(unittest.TestCase):
    def test_reverse_pulse_returns_to_original_voltage_with_explicit_events(self):
        self.assertEqual([rf.waveform(t,2) for t in (0,4,6,8,28,30,32,52)], [1,1,1.25,1.5,1.5,1.25,1,1])

    def test_independent_solution_converges_and_preserves_charge_direction(self):
        for model in rf.COEFFICIENTS:
            c=rf.COEFFICIENTS[model]
            for temperature in (-40,125):
                a=rf.oracle(model,4,8,c['aj'],c['pj'],temperature,.05)
                b=rf.oracle(model,4,8,c['aj'],c['pj'],temperature,.025)
                self.assertLess(rf.normalized(a['current'],b['current']),.01)
                self.assertLess(b['current'][112],0)
                self.assertGreater(b['current'][496],0)
                self.assertLess(abs(b['current'][-1]),abs(b['current'][496])/100)
                self.assertTrue(all(math.isfinite(v) for v in b['current']))

    def test_bad_output_cannot_count_as_a_detected_fault(self):
        reference=dict(time=[i for i in range(rf.POINTS)],tau=32,current=[0.]*rf.POINTS)
        rows=[[t,rf.waveform(t,32),0.] for t in reference['time']]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'raw';path.write_text('retained')
            with patch.object(rf,'parse_raw',return_value=(['time','v(d)','i(vdrive)'],rows,False)):
                self.assertTrue(rf.inspect(path,reference)['accepted'])
            for index,value in ((0,1),(1,2),(2,float('nan'))):
                bad=[r.copy() for r in rows];bad[10][index]=value
                with patch.object(rf,'parse_raw',return_value=(['time','v(d)','i(vdrive)'],bad,False)),self.assertRaises(ValueError):rf.inspect(path,reference)
            for names,data,complex_data in ((['time','v(d)','v(d)'],rows,False),(['time','v(d)','i(vdrive)'],rows[:-1],False),(['time','v(d)','i(vdrive)'],rows,True)):
                with patch.object(rf,'parse_raw',return_value=(names,data,complex_data)),self.assertRaises(ValueError):rf.inspect(path,reference)

    def test_faults_have_specific_independent_physical_effects(self):
        _,sources=rf.public_sources()
        for model in rf.COEFFICIENTS:
            nominal=rf.fault_model(model,sources,'none')
            cap=rf.fault_model(model,sources,'wrong-capacitance')
            self.assertEqual(cap.replace("= '2*","= '"),nominal)
            self.assertEqual(cap.count("= '2*"),2)
            res=rf.fault_model(model,sources,'wrong-series-resistance')
            self.assertEqual(res.replace('2*rp1_diode/perim','rp1_diode/perim'),nominal)
            self.assertNotEqual(res,nominal)
            with self.assertRaises(ValueError):rf.fault_model(model,sources,'unknown')

    def test_unverified_integration_and_nonfinite_comparisons_are_rejected(self):
        c=rf.COEFFICIENTS['ps2nw']
        for ratio in (0,.1,-1):
            with self.assertRaises(ValueError):rf.oracle('ps2nw',4,8,c['aj'],c['pj'],27,ratio)
        for actual,expected in (([],[]),([0],[0,0]),([float('inf')],[0]),([0],[float('nan')])):
            with self.assertRaises(ValueError):rf.normalized(actual,expected)


if __name__=='__main__':unittest.main()
