"""Focused guardrails for the finite, unqualified pw2dn native producer."""
import unittest
from icstudio import pw2dn_native_probe as probe

def deck(fault=None):
    lines=[]
    for i,(_,_,area,perim) in enumerate(probe.POINTS):
        pins=['0','d'+str(i)] if fault=='polarity' else ['d'+str(i),'0']
        a=area*.5 if fault=='area' else area;p=perim*1.5 if fault=='perimeter' else perim
        lines.append(f'X_D{i} {pins[0]} {pins[1]} {probe.MODEL} area={a:g} perim={p:g}')
    return '\n'.join(lines)+'\n'

class NativeProbeTests(unittest.TestCase):
    def test_exact_calls_and_faults_are_distinct(self):
        probe.calls(deck())
        for fault in probe.FAULTS:
            probe.calls(deck(fault),fault)
            with self.assertRaises(ValueError):probe.calls(deck(fault))
        with self.assertRaises(ValueError):probe.calls(deck().replace('X_D2','X_D1'))
        with self.assertRaises(ValueError):probe.calls(deck().replace('area=4','area=4 extra=1'))

    def test_finite_contract_is_explicit(self):
        self.assertEqual(probe.POINTS,((2,2,4,8),(4,2,8,12),(10,10,100,40)))
        self.assertEqual(len(probe.CONDITIONS),9)
        self.assertEqual(probe.FAULTS,('polarity','area','perimeter'))

if __name__=='__main__':unittest.main()
