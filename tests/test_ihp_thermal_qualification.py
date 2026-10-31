import copy
import unittest

from scripts.qualify_ihp_thermal import check_stimulus, compare, fixture, independent, probes, vectors
from scripts.qualify_standard_mos import load_technology
from icstudio.interchange import spice
from icstudio.catalog import binding_for


def response(analysis='dc'):
    x = [.45 + i * .01 for i in range(34)] if analysis == 'dc' else [1e5 * 10 ** (i / 5) for i in range(21)]
    result = dict(x=x, traces={}, currents={}, phase={}, current_phase={})
    for row in probes():
        tag = row['tag']
        result['traces'][tag + 't'] = [1.] * len(x)
        result['phase'][tag + 't'] = [0.] * len(x)
        for pin, value in [('c', -1e-4), ('b', -1e-6), ('e', 101e-6), ('s', 0.)]:
            key = 'v' + tag + pin
            result['currents'][key] = [abs(value) if analysis == 'ac' else value] * len(x)
            result['current_phase'][key] = [180. if value < 0 else 0.] * len(x)
    return result


class ThermalQualificationTests(unittest.TestCase):
    def test_real_fixture_has_free_temperature_outputs_and_matching_heating_cycle(self):
        tech, _ = load_technology('ihp-sg13g2')
        p = fixture(tech, 'tran', [])
        devices = [d for d in p['cells'][0]['devices'] if d.get('model_ref')]
        self.assertEqual(len(devices), 10)
        self.assertEqual({binding_for(tech, d)['model'] for d in devices}, {'npn13G2_5t', 'npn13G2l_5t', 'npn13G2v_5t'})
        self.assertTrue(all(d['nets']['t'] != '0' for d in devices))
        emitted = spice(p, p['top'], dict(type='tran', corner='nominal', temperature=27, step='1n', stop='600n'))
        self.assertIn('SIN(0.665 0.115 5000000 1e-08)', emitted)
        self.assertIn('SIN(.665 .115 5meg 10n)', independent(tech, 'tran', 'nominal', 27))

    def test_missing_or_nonfinite_thermal_output_is_rejected(self):
        for fault in ('missing', 'nonfinite'):
            result = response()
            if fault == 'missing': del result['traces']['qn1l0t']
            else: result['traces']['qn1l0t'][7] = float('nan')
            with self.assertRaisesRegex(ValueError, 'thermal/electrical vector'):
                vectors(result, 'dc')

    def test_incomplete_sweep_is_rejected(self):
        result = response(); result['x'] = result['x'][:-1]
        with self.assertRaisesRegex(ValueError, 'Incomplete HBT DC sweep'):
            vectors(result, 'dc')

    def test_balanced_electrical_fault_and_thermal_clamp_are_detected(self):
        expected = response(); actual = copy.deepcopy(expected)
        actual['currents']['vqn1l0c'] = [-2e-4] * 34
        actual['currents']['vqn1l0e'] = [201e-6] * 34
        actual['traces']['qn1l0t'] = [0.] * 34
        check = compare(actual, expected, 'dc')
        self.assertEqual(check['status'], 'MISMATCH')
        self.assertGreater(check['channel_errors']['vqn1l0c'], 1)
        self.assertGreater(check['channel_errors']['qn1l0t'], 1)

    def test_phase_fault_is_detected_with_unchanged_magnitude(self):
        expected = response('ac'); actual = copy.deepcopy(expected)
        actual['phase']['qn1l0t'] = [90.] * 21
        self.assertEqual(compare(expected, expected, 'ac')['status'], 'PASS')
        self.assertGreater(compare(actual, expected, 'ac')['channel_errors']['qn1l0t'], 1)

    def test_missing_current_cannot_hide_behind_temperature(self):
        result = response(); result['currents']['vqn1l0e'] = [0.] * 34
        with self.assertRaisesRegex(ValueError, 'violate KCL'):
            vectors(result, 'dc')

    def test_input_readback_rejects_wrong_amplitude_and_missing_input(self):
        result = dict(x=[0., 10e-9, 60e-9], traces={'drive': [.665, .665, .78]})
        self.assertEqual(check_stimulus(result, 'tran')['samples'], 3)
        result['traces']['drive'][-1] = .75
        with self.assertRaisesRegex(ValueError, 'stimulus differs'):
            check_stimulus(result, 'tran')
        result['traces']['drive'][-1] = float('nan')
        with self.assertRaisesRegex(ValueError, 'nonfinite heating-cycle input'):
            check_stimulus(result, 'tran')
        result['traces'] = {}
        with self.assertRaisesRegex(ValueError, 'Missing or nonfinite heating-cycle input'):
            check_stimulus(result, 'tran')


if __name__ == '__main__':
    unittest.main()
