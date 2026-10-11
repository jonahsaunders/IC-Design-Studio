import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.ihp_waveform_convergence import compare
from scripts import ihp_waveform_convergence


class IHPWaveformConvergenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.left, self.right = [Path(temp.name)/name for name in ('baseline', 'tighter')]
        for folder, settings, tran in ((self.left, '1e-5 1e-12 1e-8', '100p 30n 0 200p'),
                                      (self.right, '5e-6 5e-13 5e-9', '50p 30n 0 100p')):
            folder.mkdir()
            for name in ('circuit.spice', 'capacitance.spice', '.spiceinit'):
                (folder/name).write_text('* fixed physical input\n')
            r, a, v = settings.split()
            (folder/'bench.spice').write_text(f'fixture\nVDD supply 0 1.2\n.options reltol={r} abstol={a} vntol={v}\n.control\ntran {tran}\n.endc\n.end\n')
            (folder/'engine.log').write_text('simulation completed\n')
            (folder/'expectations.json').write_text(json.dumps(dict(voltage=1.2, channels=[dict(node='Q')],
                samples=[dict(time_ns=5, bits=['0']), dict(time_ns=25, bits=['1'])])))
            self.wave(folder)

    def wave(self, folder, shift=0.):
        (folder/'waveform.txt').write_text(f'time v(Q)\n0 0\n{14e-9+shift:.17g} 0\n{16e-9+shift:.17g} 1.2\n3e-8 1.2\n')

    def check(self):
        return compare(self.left, self.right, 30)

    def test_full_matching_traces_and_sub_ps_shift_pass(self):
        self.wave(self.right, .5e-12)
        result = self.check()
        self.assertEqual(result['status'], 'convergence-pass')
        self.assertEqual(result['matched_edges'], 1)
        self.assertAlmostEqual(result['maximum_edge_change_ps'], .5)
        self.assertFalse(result['qualified'])

    def test_two_ps_fault_fails_even_with_correct_output_bits(self):
        self.wave(self.right, 2e-12)
        result = self.check()
        self.assertEqual(result['status'], 'convergence-failed')
        self.assertTrue(all(row['status'] == 'pass' for row in result['waveform_audits']))

    def test_no_transitions_cannot_establish_convergence(self):
        for folder in (self.left, self.right):
            (folder/'waveform.txt').write_text('time v(Q)\n0 0\n3e-8 0\n')
            expected = json.loads((folder/'expectations.json').read_text())
            expected['samples'][-1]['bits'] = ['0']
            (folder/'expectations.json').write_text(json.dumps(expected))
        self.assertEqual(self.check()['status'], 'convergence-failed')

    def test_extra_glitch_fails_even_if_samples_pass(self):
        (self.right/'waveform.txt').write_text('time v(Q)\n0 0\n11e-9 0\n12e-9 1.2\n13e-9 0\n14e-9 0\n16e-9 1.2\n3e-8 1.2\n')
        self.assertEqual(self.check()['status'], 'convergence-failed')

    def test_changed_physics_or_expectations_rejected(self):
        for name in ('circuit.spice', 'capacitance.spice', '.spiceinit', 'expectations.json'):
            path = self.right/name; before = path.read_text()
            with self.subTest(name=name):
                path.write_text(before+'\n')
                with self.assertRaisesRegex(ValueError, 'inputs differ'): self.check()
                path.write_text(before)

    def test_stimulus_and_method_may_not_change(self):
        path = self.right/'bench.spice'; before = path.read_text()
        for text in (before.replace('supply 0 1.2', 'supply 0 1.08'), before.replace('.options ', '.options method=trap ')):
            path.write_text(text)
            with self.assertRaisesRegex(ValueError, 'stimulus'): self.check()
        path.write_text(before)

    def test_uic_mode_must_match_and_cannot_be_silently_replaced(self):
        for folder in (self.left, self.right):
            path = folder/'bench.spice'
            path.write_text(path.read_text().replace('p\n.endc', 'p uic\n.endc'))
        self.assertEqual(self.check()['status'], 'convergence-pass')
        path = self.right/'bench.spice'
        path.write_text(path.read_text().replace(' uic\n', '\n'))
        with self.assertRaisesRegex(ValueError, 'stimulus'): self.check()

    def test_looser_tolerance_and_step_rejected(self):
        path = self.right/'bench.spice'; before = path.read_text()
        for old, new in (('5e-6','2e-5'), ('5e-13','2e-12'), ('5e-9','2e-8'), ('0 100p','0 300p')):
            path.write_text(before.replace(old, new))
            with self.assertRaisesRegex(ValueError, 'tighten'): self.check()
        path.write_text(before)

    def test_partial_stale_failed_and_wrong_output_captures_rejected(self):
        (self.right/'waveform.txt').write_text('time v(Q)\n0 0\n16e-9 1.2\n')
        with self.assertRaisesRegex(ValueError, 'entire'): self.check()
        self.wave(self.right)
        (self.right/'engine.log').write_text('tran simulation(s) aborted\n')
        with self.assertRaisesRegex(ValueError, 'incomplete'): self.check()
        (self.right/'engine.log').write_text('done\n')
        (self.right/'waveform.txt').write_text('time v(Q)\n0 0\n3e-8 0\n')
        with self.assertRaisesRegex(ValueError, 'functional'): self.check()

    def test_capture_changed_during_comparison_rejected(self):
        original = ihp_waveform_convergence._events
        def mutate(path, voltage):
            result = original(path, voltage)
            if path.parent == self.right:
                self.wave(self.right, 2e-12)
            return result
        with patch.object(ihp_waveform_convergence, '_events', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'changed during'): self.check()
