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
            with self.subTest(factor=factor),self.assertRaisesRegex(ValueError,'does not scale'):check(wrong,'sky130A')


if __name__=='__main__':unittest.main()
