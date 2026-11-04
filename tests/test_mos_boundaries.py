from copy import deepcopy
import math
import unittest
from scripts.qualify_mos_boundaries import (
    AXES, PROFILES, STEPS, compare, contract, probes, source_identity, sweep, vectors,
)


class MosBoundaryTests(unittest.TestCase):
    def response(self, target, polarity, axis):
        low, high = sweep(target, polarity, axis)
        currents = {}
        for index, row in enumerate(probes(target, polarity, axis)):
            sign = 1 if polarity == 'p' else -1
            drain = [sign*(i+1)*(index+1)*1e-7 for i in range(STEPS+1)]
            tag = 'v'+row['tag']
            currents.update({tag+'d': drain, tag+'s': [-v for v in drain],
                             tag+'g': [0.]*(STEPS+1), tag+'b': [0.]*(STEPS+1)})
        return dict(x=[low+(high-low)*i/STEPS for i in range(STEPS+1)], currents=currents)

    def test_published_polarity_boundaries_and_selected_axes_stay_distinct(self):
        self.assertEqual(sweep('sky130A', 'n', 'body'), (-1.95, .3))
        self.assertEqual(sweep('sky130A', 'p', 'body'), (-.1, 1.95))
        self.assertEqual(sweep('ihp-sg13g2', 'n', 'drain'), (0., 1.5))
        self.assertEqual(sweep('ihp-sg13g2', 'n', 'gate'), (0., 1.2))
        self.assertEqual(contract('gf180mcuC')['temperatures'], [-40, 25, 125])
        self.assertIn('temperature', contract('sky130A')['selected'])
        self.assertEqual(len(contract('gf180mcuD')['sizes']), 16)
        self.assertIn((.15, .13), contract('ihp-sg13g2')['sizes'])
        source_identity()

    def test_all_targets_polarities_and_axes_require_every_terminal(self):
        for target in PROFILES:
            for polarity in ('n', 'p'):
                for axis in AXES:
                    data = self.response(target, polarity, axis)
                    with self.subTest(target=target, polarity=polarity, axis=axis):
                        self.assertEqual(compare(data, deepcopy(data), target, polarity, axis)['status'], 'PASS')
                        for pin in ('d', 'g', 's', 'b'):
                            changed = deepcopy(data); changed['currents'].pop('vq0a0b0'+pin)
                            with self.assertRaisesRegex(ValueError, 'Missing'):
                                compare(changed, data, target, polarity, axis)

    def test_identical_incomplete_or_shifted_grids_do_not_pass(self):
        for fault in ('shift', 'short', 'nan'):
            data = self.response('sky130A', 'p', 'body')
            if fault == 'shift': data['x'] = [v+.01 for v in data['x']]
            if fault == 'short': data['x'].pop()
            if fault == 'nan': data['x'][3] = math.nan
            with self.subTest(fault=fault), self.assertRaisesRegex(ValueError, 'declared coordinates'):
                compare(data, data, 'sky130A', 'p', 'body')

    def test_identical_dead_wrong_sign_and_nonconserving_devices_fail(self):
        for fault in ('flat', 'sign', 'charge'):
            data = self.response('ihp-sg13g2', 'n', 'gate')
            if fault == 'flat': data['currents'] = {k: [v[0]]*len(v) for k, v in data['currents'].items()}
            if fault == 'sign': data['currents'] = {k: [-x for x in v] for k, v in data['currents'].items()}
            if fault == 'charge': data['currents']['vq0a0b0b'][5] = 1e-3
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                compare(data, data, 'ihp-sg13g2', 'n', 'gate')

    def test_fault_acceptance_is_per_device_not_one_global_mismatch(self):
        reference = self.response('gf180mcuC', 'n', 'drain')
        changed = deepcopy(reference)
        changed['currents']['vq0a0b0d'][10] *= 1.01
        result = compare(changed, reference, 'gf180mcuC', 'n', 'drain')
        self.assertEqual(result['status'], 'DIFFERENT')
        self.assertGreater(result['device_errors']['q0a0b0'], 1)
        self.assertFalse(all(v > 1 for v in result['device_errors'].values()))
        changed['currents']['vq0a0b0d'][10] = math.inf
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            vectors(changed, 'gf180mcuC', 'n', 'drain', require_response=False)


if __name__ == '__main__':
    unittest.main()
