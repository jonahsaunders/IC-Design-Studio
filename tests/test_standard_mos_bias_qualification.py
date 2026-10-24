"""Terminal-current acceptance must reject missing probes and false zero passes."""
from copy import deepcopy
import math
import unittest
from scripts.qualify_standard_mos_bias import compare,current_vectors,points


class StandardMosBiasTests(unittest.TestCase):
    def response(self):
        currents={}
        for row in points('sky130A'):
            sign=-1 if row['polarity']=='n' else 1
            drain=[sign*i*1e-5 for i in range(41)];tag='v'+row['tag']
            currents.update({tag+'d':drain,tag+'s':[-v for v in drain],tag+'g':[0.]*41,tag+'b':[0.]*41})
        return dict(x=[i*1.8/40 for i in range(41)],currents=currents)

    def test_all_four_terminal_vectors_of_every_biased_device_are_required(self):
        data=self.response();self.assertEqual(compare(data,deepcopy(data),'sky130A')['terminal_vectors'],72)
        for key in data['currents']:
            changed=deepcopy(data);changed['currents'].pop(key)
            with self.subTest(vector=key),self.assertRaisesRegex(ValueError,'Missing'):
                compare(changed,data,'sky130A')

    def test_constant_or_wrong_sign_reference_does_not_count(self):
        for mode in ('zero','constant','sign'):
            data=self.response()
            if mode=='zero':data['currents']={k:[0.]*41 for k in data['currents']}
            if mode=='constant':data['currents']={k:[v[-1]]*41 for k,v in data['currents'].items()}
            if mode=='sign':data['currents']={k:[-x for x in v] for k,v in data['currents'].items()}
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,'signed current response'):
                compare(data,data,'sky130A')

    def test_conservation_is_independent_of_agreement_between_runs(self):
        data=self.response();data['currents']['vn11b'][20]=1e-5
        with self.assertRaisesRegex(ValueError,'conservation failed'):compare(data,data,'sky130A')

    def test_nonfinite_scale_and_sweep_changes_are_rejected(self):
        reference=self.response()
        for mode in ('nonfinite','scale','sweep','short'):
            data=deepcopy(reference)
            if mode=='nonfinite':data['currents']['vn11d'][20]=math.nan
            if mode=='scale':data['currents']['vn11d'][20]*=1.01
            if mode=='sweep':data['x'][20]+=.001
            if mode=='short':data['currents']['vn11d'].pop()
            with self.subTest(mode=mode),self.assertRaises(ValueError):compare(data,reference,'sky130A')


if __name__=='__main__':unittest.main()
