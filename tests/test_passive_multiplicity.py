from copy import deepcopy
import unittest
from tests import test_standard_passive_qualification as fixtures
from scripts.check_passive_multiplicity import check


class PassiveMultiplicityTests(unittest.TestCase):
    def response(self):
        data=fixtures.StandardPassiveQualificationTests().response()
        for key in data['currents']:
            if key.endswith('m3'):data['currents'][key]=[v*3 for v in data['currents'][key]]
        return data

    def test_parallel_admittance_invariant(self):
        data=self.response();self.assertEqual(check(data,'sky130A')['parallel_pairs'],6)

    def test_identical_wrong_application_and_reference_multiplicity_is_rejected(self):
        data=self.response()
        for factor in (0,1/3,3):
            wrong=deepcopy(data)
            for key in wrong['currents']:
                if key.endswith('m3'):wrong['currents'][key]=[v*factor for v in wrong['currents'][key]]
            with self.subTest(factor=factor),self.assertRaises(ValueError):check(wrong,'sky130A')

    def test_all_zero_and_wrong_physics_cannot_pass_parallel_scaling(self):
        for mode in ('zero','negative-conductance','constant-capacitor'):
            wrong=deepcopy(self.response())
            if mode=='zero':wrong['currents']={k:[0.]*26 for k in wrong['currents']}
            elif mode=='negative-conductance':
                for key in wrong['current_phase']:
                    if key.startswith('vres'):wrong['current_phase'][key]=[0.]*26
            else:
                for key in wrong['currents']:
                    if key.startswith('vcap'):wrong['currents'][key]=[1e-9*(3 if key.endswith('m3') else 1)]*26
            with self.subTest(mode=mode),self.assertRaises(ValueError):check(wrong,'sky130A')


if __name__=='__main__':unittest.main()
