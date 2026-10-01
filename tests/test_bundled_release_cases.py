"""Keep the release gate aligned with every shipped process and its runtime."""
import unittest
from unittest.mock import patch

from icstudio.model import clone
from scripts.verify_bundled_simulation import native_case, run_native_case
from tests.test_student_physical import technology


class BundledReleaseCases(unittest.TestCase):
    def test_all_four_variants_use_their_own_core_device_and_voltage(self):
        expected = {
            'sky130A': ('sky130_fd_pr/nfet_01v8.sym', 1.8),
            'gf180mcuC': ('symbols/nfet_03v3.sym', 3.3),
            'gf180mcuD': ('symbols/nfet_03v3.sym', 3.3),
            'ihp-sg13g2': ('sg13g2_pr/sg13_lv_nmos.sym', 1.2),
        }
        def managed(job):
            job['settings'].update(managed_osdi='ihp-sg13g2', physical_runtime={'kind': 'linux'})
        for variant, contract in expected.items():
            with self.subTest(variant=variant), patch('icstudio.physical_backend.prepare_simulation', side_effect=managed) as prepare:
                tech = technology(variant); before = clone(tech)
                job, model, supply = native_case(tech, 'native-ngspice')
                self.assertEqual((model, supply), contract)
                self.assertIn(model, tech['simulation']['catalog'])
                self.assertEqual(tech, before)
                self.assertEqual(prepare.call_count, int(variant == 'ihp-sg13g2'))
                if variant == 'ihp-sg13g2':
                    self.assertNotIn('executable', job)
                    with patch('icstudio.physical_backend.dispatch', return_value={'managed': True}) as dispatch, \
                            patch('icstudio.engines.run_ngspice', side_effect=AssertionError('IHP must use its compiled runtime')):
                        self.assertEqual(run_native_case(job, 'work'), {'managed': True})
                        self.assertEqual(dispatch.call_args.args[:2], (job, 'work'))
                else:
                    self.assertEqual(job['executable'], 'native-ngspice')

    def test_missing_ihp_runtime_stops_qualification_instead_of_skipping(self):
        with patch('icstudio.digital_runtime.manifest', return_value=None):
            with self.assertRaisesRegex(ValueError, 'included physical tools'):
                native_case(technology('ihp-sg13g2'), 'ngspice')

    def test_unknown_or_incomplete_process_cannot_borrow_gf180_models(self):
        tech = technology('gf180mcuD'); tech['package_lock']['id'] = 'future-process'
        with self.assertRaisesRegex(ValueError, 'supported four-terminal'):
            native_case(tech, 'ngspice')


if __name__ == '__main__':
    unittest.main()
