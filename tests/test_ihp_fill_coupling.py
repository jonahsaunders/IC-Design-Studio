import copy
import math
import unittest
from scripts.check_ihp_fill_coupling import controls_pass, LAYERS


class IHPCouplingTests(unittest.TestCase):
    def rows(self):
        return [dict(layer=layer,cases={state:dict(signal_to_fill_pf=1e-3 if state=='near' else 0.,
                      signal_ground_pf=2e-3) for state in ('absent','near','far')}) for layer in LAYERS]

    def test_every_layer_needs_a_nearby_response(self):
        self.assertTrue(controls_pass(self.rows()))
        for layer in range(7):
            rows=self.rows();rows[layer]['cases']['near']['signal_to_fill_pf']=0.
            self.assertFalse(controls_pass(rows))

    def test_missing_layer_duplicate_and_missing_far_control_fail(self):
        rows=self.rows();rows.pop();self.assertFalse(controls_pass(rows))
        rows=self.rows();rows[-1]=copy.deepcopy(rows[0]);self.assertFalse(controls_pass(rows))
        rows=self.rows();rows[0]['cases'].pop('far');self.assertFalse(controls_pass(rows))

    def test_changed_baseline_and_nonfinite_capacitance_fail(self):
        for state,key,value in [('far','signal_ground_pf',1.),('far','signal_to_fill_pf',1.),
                                ('near','signal_to_fill_pf',math.nan),('near','signal_ground_pf',-1.)]:
            rows=self.rows();rows[0]['cases'][state][key]=value;self.assertFalse(controls_pass(rows))
