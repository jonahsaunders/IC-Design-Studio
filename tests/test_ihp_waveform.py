import json
from pathlib import Path
import tempfile
import unittest
from scripts.check_ihp_waveform import audit


class IHPWaveformTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.wave = self.root/'waveform.txt'; self.expected = self.root/'expected.json'
        self.log = self.root/'engine.log'; self.log.write_text('ngspice-42 done\n')
        self.wave.write_text('time v(Q)\n0 0\n1e-9 0\n2e-9 1.2\n3e-9 1.2\n')
        self.expected.write_text(json.dumps(dict(voltage=1.2, channels=[dict(node='Q')],
            samples=[dict(time_ns=.5,bits=['0']),dict(time_ns=2.5,bits=['1'])])))

    def check(self):
        return audit(self.wave, self.expected, 3, self.log)

    def test_complete_two_state_trace(self):
        result = self.check()
        self.assertEqual((result['status'], result['tested_bits']), ('pass', 2))

    def test_decimal_endpoint_roundoff_is_bounded(self):
        value = json.loads(self.expected.read_text()); value['samples'][-1]['time_ns'] = 3
        self.expected.write_text(json.dumps(value))
        self.assertEqual(self.check()['status'], 'pass')

    def test_zero_exit_and_partial_waveform_do_not_establish_success(self):
        self.wave.write_text('time v(Q)\n0 0\n1e-9 0\n')
        with self.assertRaisesRegex(ValueError, 'entire'): self.check()

    def test_aborted_log_rejects_even_with_full_stale_waveform(self):
        self.log.write_text('tran simulation(s) aborted\nngspice-42 done\n')
        with self.assertRaisesRegex(ValueError, 'incomplete'): self.check()

    def test_wrong_output_is_a_functional_failure(self):
        self.wave.write_text('time v(Q)\n0 0\n1e-9 0\n2e-9 0\n3e-9 0\n')
        result = self.check()
        self.assertEqual((result['status'], result['failed_bits']), ('fail', 1))

    def test_channel_swap_cannot_relabel_a_result(self):
        self.wave.write_text(self.wave.read_text().replace('v(Q)', 'v(OTHER)'))
        with self.assertRaisesRegex(ValueError, 'channels'): self.check()

    def test_nonfinite_and_repeated_time_rejected(self):
        for data in ('time v(Q)\n0 0\n3e-9 nan\n',
                     'time v(Q)\n0 0\n0 0\n3e-9 1.2\n'):
            with self.subTest(data=data):
                self.wave.write_text(data)
                with self.assertRaisesRegex(ValueError, 'nonfinite'): self.check()

    def test_future_expected_sample_cannot_be_silently_skipped(self):
        value = json.loads(self.expected.read_text()); value['samples'][-1]['time_ns'] = 4
        self.expected.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'Every expected'): self.check()
