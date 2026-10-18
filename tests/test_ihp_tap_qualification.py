import copy
import math
import unittest
from scripts.qualify_ihp_taps import analytical,compare,points,resistance,values


def response():
    x=[-.01+i*.001 for i in range(21)]
    return {'x':x,'traces':{r['tag']:[v*1000/(1000+resistance(r['w']*1e-6,r['l']*1e-6)) for v in x] for r in points()}}


class TapComparisonTests(unittest.TestCase):
    def test_complete_independent_response_and_analytic_oracle(self):
        data=response();self.assertEqual(compare(data,copy.deepcopy(data),'dc')['status'],'PASS')
        self.assertEqual(analytical(data,'dc',27)['status'],'PASS')

    def test_missing_nonfinite_incomplete_and_unexercised_vectors_fail(self):
        for fault in ('missing','nan','incomplete','flat'):
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                data=response()
                if fault=='missing':del data['traces']['outn0']
                elif fault=='nan':data['traces']['outn0'][1]=math.nan
                elif fault=='incomplete':data['x'].pop()
                else:data['traces']['outn0']=[0.]*21
                compare(data,data,'dc')

    def test_wrong_gain_and_open_are_detected_for_every_device(self):
        expected=response()
        for scale in (0,.8):
            data=response();data['traces']={k:[v*scale for v in row] for k,row in data['traces'].items()}
            result=compare(data,expected,'dc')
            self.assertEqual(result['status'],'MISMATCH')
            self.assertTrue(all(v>1 for v in result['channel_errors'].values()))
            with self.assertRaises(ValueError):analytical(data,'dc',27)

    def test_ac_phase_is_compared(self):
        data={'x':[100*10**(i/5) for i in range(26)],
              'traces':{r['tag']:[1.]*26 for r in points()},
              'phase':{r['tag']:[0.]*26 for r in points()}}
        expected=copy.deepcopy(data);data['phase']['outp0'][0]=90
        self.assertEqual(compare(data,expected,'ac')['status'],'MISMATCH')

    def test_noise_requires_positive_finite_complete_output(self):
        data={'x':[100*10**(i/5) for i in range(26)],'traces':{'outn0':[1e-9]*26}}
        self.assertEqual(len(values(data,'noise')[0]),26)
        for value in (0.,-1e-9,math.nan):
            data['traces']['outn0']=[value]*26
            with self.assertRaises(ValueError):values(data,'noise')


if __name__=='__main__':unittest.main()
