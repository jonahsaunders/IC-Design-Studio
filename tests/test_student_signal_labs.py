"""Execute the editable signal lesson fixtures through the saved-job grader."""

import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

from icstudio import student_signal_labs as labs
from icstudio.model import atomic_write
from icstudio.student_hub import curriculum, evaluate
from icstudio.student_projects import create
from icstudio.student_signal_circuits import named
from icstudio.worker import main


EXE = os.environ.get('ICSTUDIO_TEST_NGSPICE', '')


class StudentSignalLabsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lessons = {lesson['signal_lab']: lesson for lesson in curriculum()['lessons'] if lesson.get('signal_lab')}

    def execute(self, p, lab, step, root):
        path = root / lab / str(len(list((root / lab).glob('*'))))
        job = labs.prepare(p, self.lessons[lab], step, {'ngspice': EXE})
        inp, out = path / 'input.json', path / 'result.json'
        atomic_write(inp, json.dumps(job))
        log = io.StringIO()
        with redirect_stdout(log):
            status = main(inp, out)
        self.assertEqual(status, 0, log.getvalue())
        result = json.loads(out.read_text(encoding='utf-8'))
        self.assertFalse(result['student_signal']['issue'])
        return dict(job=job, result=result, state='Complete', path=path)

    def measure(self, p, lab, step, *rows):
        lesson = self.lessons[lab]
        checkpoint = next(candidate for candidate in lesson['steps'] if candidate['id'] == step)
        return evaluate(checkpoint, lesson, p, rows)['signal_measurements']

    def open(self, lab):
        return create(self.lessons[lab]['starter'])

    def part(self, p, name):
        return named(next(c for c in p['cells'] if c['id'] == p['top']), name)

    def set_values(self, p, values):
        for name, value in values.items():
            self.part(p, name)['value'] = value

    def test_bias_matched_linearity_and_capture_integrity(self):
        p = self.open('linearity')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = self.execute(p, 'linearity', 'baseline', root)
            original = self.measure(p, 'linearity', 'baseline', base)
            self.set_values(p, {'RS': '4k', 'VBIAS': '.934'})
            with self.assertRaisesRegex(ValueError, 'latest edits'):
                self.measure(p, 'linearity', 'baseline', base)
            repair = self.execute(p, 'linearity', 'repair', root)
            improved = self.measure(p, 'linearity', 'repair', repair)
            self.assertLess(abs(improved['Drain bias (µA)'] - original['Drain bias (µA)']), .5)
            self.assertLess(improved['THD, harmonics 2–5 (%)'], original['THD, harmonics 2–5 (%)'] / 3)
            self.assertLess(improved['Fundamental gain (V/V)'], original['Fundamental gain (V/V)'])
            (repair['path'] / 'transient/wave.json').write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'waveform evidence changed'):
                self.measure(p, 'linearity', 'repair', repair)
            self.set_values(p, {'RD': '1k'})
            with self.assertRaisesRegex(ValueError, 'supplied topology'):
                self.execute(p, 'linearity', 'repair', root)

    def test_rejection_requires_independent_excitations(self):
        p = self.open('rejection')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.measure(p, 'rejection', 'baseline', self.execute(p, 'rejection', 'baseline', root))
            self.set_values(p, {'RTAIL': '100k', 'CDEC': '1u'})
            row = self.execute(p, 'rejection', 'repair', root)
            self.assertEqual([c['name'] for c in row['result']['student_signal']['cases']],
                             ['differential', 'common-mode', 'supply'])
            repair = self.measure(p, 'rejection', 'repair', row)
            self.assertGreater(repair['CMRR at 10 kHz (dB)'], 30)
            self.assertGreater(repair['Input-referred PSRR+ at 10 kHz (dB)'], 33)

    def test_temperature_anchor_fit_and_held_out_conditions(self):
        p = self.open('temperature')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.measure(p, 'temperature', 'baseline', self.execute(p, 'temperature', 'baseline', root))
            self.set_values(p, {'RFIX': '6.8k'})
            measured = self.measure(p, 'temperature', 'anchor', self.execute(p, 'temperature', 'anchor', root))
            low, high = [r['ADC code'] for r in measured.values()]
            self.assertEqual((low, high), (588, 646))
            uncalibrated = self.execute(p, 'temperature', 'validate', root)
            with self.assertRaisesRegex(ValueError, 'Worst held-out error'):
                self.measure(p, 'temperature', 'validate', uncalibrated)
            gain = round(80_000 / (high - low))
            labs.set_calibration(p, gain, -gain * low)
            with self.assertRaisesRegex(ValueError, 'latest edits'):
                self.measure(p, 'temperature', 'validate', uncalibrated)
            final = self.measure(p, 'temperature', 'validate', self.execute(p, 'temperature', 'validate', root))
            trials = [r for r in final.values() if r['Role'] == 'Held-out trial']
            self.assertEqual(len(trials), 15)
            self.assertEqual({r['Supply (V)'] for r in trials}, {1.6, 1.8, 2.0})
            self.assertLess(max(abs(r['Error (°C)']) for r in trials), 2.5)

    @unittest.skipUnless(Path(EXE).is_file(), 'Set ICSTUDIO_TEST_NGSPICE to the native ngspice executable')
    def test_load_and_adc_faults_and_repairs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = self.open('load')
            initial = self.measure(p, 'load', 'baseline', self.execute(p, 'load', 'baseline', root))
            self.assertIsNone(initial['source-follower-500p']['Settling to ±10 mV (µs)'])
            with self.assertRaisesRegex(ValueError, '4 µs settling'):
                self.measure(p, 'load', 'repair', self.execute(p, 'load', 'repair', root))
            self.set_values(p, {'CDOM': '330p'})
            repair = self.measure(p, 'load', 'repair', self.execute(p, 'load', 'repair', root))
            self.assertEqual(len(repair), 4)
            self.assertLess(repair['feedback-buffer-500p']['Settling to ±10 mV (µs)'], 3.2)

            p = self.open('adc-ramp')
            initial = self.measure(p, 'adc-ramp', 'baseline', self.execute(p, 'adc-ramp', 'baseline', root))
            self.assertIn(3, initial['Missing codes'] + initial['Near-missing codes'])
            self.set_values(p, {'R4': '1k'})
            repair = self.measure(p, 'adc-ramp', 'repair', self.execute(p, 'adc-ramp', 'repair', root))
            self.assertEqual(repair['Code counts'], [512] * 8)

    @unittest.skipUnless(Path(EXE).is_file(), 'Set ICSTUDIO_TEST_NGSPICE to the native ngspice executable')
    def test_chopper_oscillator_and_programmable_gain(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = self.open('chopper')
            self.measure(p, 'chopper', 'baseline', self.execute(p, 'chopper', 'baseline', root))
            self.part(p, 'VDEMOD')['source']['delay'] = '0'
            self.set_values(p, {'CLP': '10n'})
            final = self.measure(p, 'chopper', 'repair', self.execute(p, 'chopper', 'repair', root))
            self.assertAlmostEqual(final['chopped']['Recovered gain (V/V)'], 20, places=1)
            self.assertGreater(final['bypassed']['Output offset (mV)'], 75)

            p = self.open('relaxation')
            self.measure(p, 'relaxation', 'baseline', self.execute(p, 'relaxation', 'baseline', root))
            self.part(p, 'RT')['native_spice']['parameters']['r'] = '22k'
            corners = self.measure(p, 'relaxation', 'corners', self.execute(p, 'relaxation', 'corners', root))
            self.assertGreater(corners['cold-low-rail']['Frequency (Hz)'], corners['hot-high-rail']['Frequency (Hz)'])

            p = self.open('pga')
            self.measure(p, 'pga', 'baseline', self.execute(p, 'pga', 'baseline', root))
            with self.assertRaisesRegex(ValueError, 'gain targets'):
                self.measure(p, 'pga', 'repair', self.execute(p, 'pga', 'repair', root))
            self.set_values(p, {'RG1': '20k', 'RG2': '6.665k', 'RG3': '2.856k'})
            final = self.measure(p, 'pga', 'repair', self.execute(p, 'pga', 'repair', root))
            self.assertGreater(min(c['Bandwidth (Hz)'] for c in final.values()), 3e6)
