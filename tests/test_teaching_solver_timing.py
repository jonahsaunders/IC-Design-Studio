"""Timing regressions for the included teaching solver.

Sample times are binary floating-point products. These checks compare the
solver's step schedule and ideal sources with exact rational arithmetic, and
tie the source definitions to the SPICE deck exported for the same project.
"""
import math
import unittest
from fractions import Fraction

from icstudio import simulation
from icstudio.interchange import source_spec
from icstudio.model import clone, example, scalar

SUFFIX = {'': Fraction(1), 'm': Fraction(1, 10**3), 'u': Fraction(1, 10**6),
          'n': Fraction(1, 10**9), 'p': Fraction(1, 10**12)}


def exact(text):
    return Fraction(text[:-1]) * SUFFIX[text[-1]] if text[-1] in SUFFIX else Fraction(text)


def voltage_source(kind, **source):
    values = dict(type=kind, low='0', high='1', period='1m', delay='0', duty='0.5', ac='1')
    values.update(source)
    return {'kind': 'V', 'name': 'V1', 'value': '1', 'source': values}


class TransientScheduleTests(unittest.TestCase):
    def test_round_ratios_have_no_zero_length_final_step(self):
        mantissas = ('1', '2', '2.5', '4', '5', '8', '10', '20', '25', '40', '50', '100', '200', '250', '500')
        values = [m + s for m in mantissas for s in ('', 'm', 'u', 'n', 'p')]
        checked = 0
        for stop_text in values:
            for step_text in values:
                ratio = exact(stop_text) / exact(step_text)
                if ratio < 1 or ratio > 20000:
                    continue
                stop, step = scalar(stop_text), scalar(step_text)
                times = simulation.transient_times(stop, step)
                with self.subTest(stop=stop_text, step=step_text):
                    self.assertEqual(times[0], 0)
                    self.assertEqual(times[-1], stop)
                    self.assertTrue(all(b > a for a, b in zip(times, times[1:])))
                    self.assertEqual(len(times), math.ceil(ratio) + 1)
                    if ratio.denominator == 1:
                        self.assertGreater(min(b - a for a, b in zip(times, times[1:])), step * .999)
                checked += 1
        self.assertGreater(checked, 1000)

    def test_partial_final_step_ends_at_stop(self):
        times = simulation.transient_times(1e-3, 3e-4)
        self.assertEqual(len(times), 5)
        self.assertEqual(times[-1], 1e-3)
        self.assertAlmostEqual((times[-1] - times[-2]) / 3e-4, 1 / 3, places=9)

    def test_rc_example_runs_for_stop_and_step_that_used_to_divide_by_zero(self):
        project = example('rc')
        for stop, step, points in (('1m', '10u', 101), ('1m', '1u', 1001), ('2m', '20u', 101), ('5m', '10u', 501)):
            with self.subTest(stop=stop, step=step):
                result = simulation.run(project, project['top'], {'type': 'tran', 'stop': stop, 'step': step})
                xs = result['x']
                self.assertEqual(len(xs), points)
                self.assertEqual(xs[-1], scalar(stop))
                self.assertTrue(all(b > a for a, b in zip(xs, xs[1:])))
                self.assertTrue(all(math.isfinite(v) for v in result['currents']['C1']))

    def test_uniform_schedule_supports_fft(self):
        from icstudio import wavecalc
        project = example('rc')
        result = simulation.run(project, project['top'], {'type': 'tran', 'stop': '5m', 'step': '10u'})
        spectrum = wavecalc.evaluate('fft(V("vout"))', result)
        self.assertEqual(spectrum.domain, 'frequency')


class IdealSourceTests(unittest.TestCase):
    def test_pulse_edges_match_exact_arithmetic(self):
        cases = (('40u', '2u', '0.5', '200n', '100u'), ('1m', '0', '0.5', '10u', '5m'),
                 ('1m', '0', '0.5', '1u', '5m'), ('20n', '0', '0.5', '100p', '200n'),
                 ('10n', '1n', '0.5', '50p', '100n'), ('1u', '0', '0.25', '10n', '10u'),
                 ('100u', '0', '0.5', '1u', '1m'), ('2m', '0', '0.1', '10u', '20m'),
                 ('1m', '250u', '0.75', '10u', '10m'))
        for period, delay, duty, step, stop in cases:
            device = voltage_source('pulse', period=period, delay=delay, duty=duty)
            wrong = []
            for index, time in enumerate(simulation.transient_times(scalar(stop), scalar(step))):
                elapsed = index * exact(step) - exact(delay)
                # The initial condition precedes the first edge; later samples on an edge take the new level.
                high = index > 0 and elapsed >= 0 and elapsed % exact(period) < exact(period) * Fraction(duty)
                if simulation.source(device, time) != (1. if high else 0.):
                    wrong.append(index)
            with self.subTest(period=period, delay=delay, duty=duty, step=step):
                self.assertEqual(wrong, [])

    def test_pulse_widths_are_identical_in_every_period(self):
        device = voltage_source('pulse', period='2m', duty='0.1')
        levels = [simulation.source(device, t) for t in simulation.transient_times(19.5e-3, 10e-6)]
        rising = [i for i in range(1, len(levels)) if levels[i] > levels[i - 1]]
        falling = [i for i in range(1, len(levels)) if levels[i] < levels[i - 1]]
        # The first sample is the initial condition, so the first edge is at the first step.
        self.assertEqual(rising, [1] + list(range(200, 2000, 200)))
        self.assertEqual(falling, list(range(20, 2000, 200)))

    def test_zero_delay_pulse_starts_low_like_the_exported_deck(self):
        device = voltage_source('pulse', low='0.2', high='1.8', period='20u')
        self.assertEqual(simulation.source(device, 0), 0.2)
        self.assertEqual(simulation.source(device, 1e-7), 1.8)
        # PULSE(V1 V2 TD ...): SPICE also takes V1 as the value at t=0.
        self.assertTrue(source_spec(device).startswith('PULSE(0.2 1.8 0 '))

    def test_zero_delay_pulse_charges_an_rc_from_the_low_level(self):
        project = clone(example('rc'))
        cell = next(c for c in project['cells'] if c['id'] == project['top'])
        source = next(d for d in cell['devices'] if d['kind'] == 'V')
        source['source'].update(type='pulse', low='0', high='1', period='1', delay='0', duty='0.5')
        result = simulation.run(project, project['top'], {'type': 'tran', 'stop': '100u', 'step': '100n'})
        tau = scalar('10k') * scalar('1n')
        self.assertEqual(result['traces']['vout'][0], 0)
        for index, value in enumerate(result['traces']['vout']):
            # Backward Euler closed form for a unit step through R into C.
            self.assertAlmostEqual(value, 1 - (1 + 1e-7 / tau) ** -index, places=7)

    def test_sine_holds_its_offset_until_the_delay(self):
        device = voltage_source('sine', low='0.9', high='1.4', period='1u', delay='250n')
        self.assertEqual(simulation.source(device, 0), 0.9)
        self.assertEqual(simulation.source(device, 1e-7), 0.9)
        self.assertAlmostEqual(simulation.source(device, 5e-7), 1.4, places=9)
        self.assertAlmostEqual(simulation.source(device, 1e-6), 0.4, places=9)
        # SIN(VO VA FREQ TD): offset, amplitude and delay are the same contract.
        self.assertTrue(source_spec(device).startswith('SIN(0.9 0.5 1000000 2.5e-07)'))

    def test_delayed_pulse_example_is_unchanged(self):
        project = example('rc')
        result = simulation.run(project, project['top'], project['analysis'])
        self.assertEqual(len(result['x']), 501)
        vin = result['traces']['vin']
        self.assertEqual(vin[9], 0)
        self.assertEqual(vin[10], 1.8)
        self.assertEqual(vin[110], 0)


if __name__ == '__main__':
    unittest.main()
