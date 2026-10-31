import unittest
from copy import deepcopy
from scripts.qualify_diode_families import compare,probes,sweep


class DiodeCurrentAcceptanceTests(unittest.TestCase):
    def response(self):
        start,stop,step=sweep('junction');x=[start+i*step for i in range(round((stop-start)/step)+1)];currents={}
        for row in probes('gf180mcuC','junction'):
            currents['v'+row['tag']+'p0']=[-1e-6*(v-start) for v in x]
            currents['v'+row['tag']+'p1']=[1e-6*(v-start) for v in x]
        return dict(x=x,currents=currents)

    def test_one_wrong_device_cannot_pass_among_correct_devices(self):
        reference=self.response();actual=deepcopy(reference)
        actual['currents']['vd0s0p0']=[v*1.1 for v in actual['currents']['vd0s0p0']]
        result=compare(actual,reference,'gf180mcuC','junction')
        self.assertEqual(result['status'],'MISMATCH');self.assertGreater(result['device_errors']['d0s0'],1)
        self.assertEqual(result['device_errors']['d1s0'],0)

    def test_zero_reference_missing_terminal_and_truncated_domain_are_rejected(self):
        good=self.response()
        for fault in ('zero','missing','truncated','nonfinite','kcl'):
            bad=deepcopy(good)
            if fault=='zero':bad['currents']={k:[0]*len(v) for k,v in bad['currents'].items()}
            elif fault=='missing':del bad['currents']['vd0s0p0']
            elif fault=='truncated':bad['x'].pop()
            elif fault=='nonfinite':bad['currents']['vd0s0p0'][0]=float('nan')
            else:bad['currents']['vd0s0p0'][-1]=.1
            with self.subTest(fault=fault),self.assertRaises(ValueError):compare(good,bad,'gf180mcuC','junction')


if __name__=='__main__':unittest.main()
