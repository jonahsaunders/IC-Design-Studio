"""Admittance qualification must detect phase, missing data and vacuous passes."""
import cmath,math,unittest
from copy import deepcopy
from scripts.qualify_standard_passives import compare,points


class StandardPassiveQualificationTests(unittest.TestCase):
    def response(self):
        x=[100*10**(i/5) for i in range(26)];magnitudes={};phases={}
        for row in points():
            values=[complex(-1e-4,0) if row['kind']=='res' else -2j*math.pi*f*1e-14 for f in x]
            name='v'+row['tag'];magnitudes[name]=[abs(v) for v in values];phases[name]=[math.degrees(cmath.phase(v)) for v in values]
        return dict(x=x,currents=magnitudes,current_phase=phases)

    def test_every_independent_probe_requires_magnitude_and_phase(self):
        ref=self.response();self.assertEqual(compare(ref,ref)['complex_vectors'],12)
        for section in ('currents','current_phase'):
            for key in ref[section]:
                actual=deepcopy(ref);actual[section].pop(key)
                with self.subTest(section=section,probe=key),self.assertRaisesRegex(ValueError,'complex passive current'):compare(actual,ref)

    def test_phase_error_is_detected_even_when_magnitudes_agree(self):
        ref=self.response();actual=deepcopy(ref);actual['current_phase']['vcap0m1']=[0.]*26
        result=compare(actual,ref);self.assertEqual(result['status'],'MISMATCH')
        self.assertGreater(result['channel_errors']['vcap0m1'],1)
        self.assertEqual(result['channel_errors']['vres0m1'],0)

    def test_zero_open_and_wrong_scale_are_per_channel_failures(self):
        ref=self.response()
        for factor in (0.,1.2):
            actual=deepcopy(ref);actual['currents']={k:[v*factor for v in values] for k,values in ref['currents'].items()}
            result=compare(actual,ref);self.assertEqual(result['status'],'MISMATCH')
            self.assertTrue(all(v>1 for v in result['channel_errors'].values()))

    def test_zero_negative_and_constant_references_are_rejected(self):
        for mode in ('zero','negative','constant'):
            ref=self.response()
            if mode=='zero':ref['currents']={k:[0.]*26 for k in ref['currents']}
            if mode=='negative':ref['current_phase']['vres0m1']=[0.]*26
            if mode=='constant':ref['currents']['vcap0m1']=[1e-9]*26
            with self.subTest(mode=mode),self.assertRaises(ValueError):compare(ref,ref)

    def test_nonfinite_values_and_wrong_frequency_ranges_fail(self):
        ref=self.response()
        for mode in ('nan','negative','frequency','missing'):
            actual=deepcopy(ref)
            if mode=='nan':actual['current_phase']['vres0m1'][4]=math.nan
            if mode=='negative':actual['currents']['vres0m1'][4]=-1
            if mode=='frequency':actual['x']=[v*10 for v in actual['x']]
            if mode=='missing':actual['x'].pop()
            with self.subTest(mode=mode),self.assertRaises(ValueError):compare(actual,ref)


if __name__=='__main__':unittest.main()
