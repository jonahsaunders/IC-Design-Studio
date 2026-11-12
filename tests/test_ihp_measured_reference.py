import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import audit_ihp_measured_reference as reference


class MeasuredCoilReferenceTests(unittest.TestCase):
    def test_measured_and_two_independent_solver_references_match_published_values(self):
        result = reference.audit()
        self.assertEqual(result['status'], 'PASS')
        self.assertFalse(result['qualified'])
        self.assertEqual(len(result['references']), 4)

    def test_changed_measurement_and_changed_inventory_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'sources'; shutil.copytree(reference.FIXTURE, root)
            path = root/'measured.s2p'; path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError, 'public source'): reference.verify_sources(root)
            (root/'SOURCE.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'source inventory'): reference.verify_sources(root)

    def test_public_geometry_roundtrip_retains_ports_ground_and_every_via(self):
        import klayout.db as k
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); result = reference.geometry_exchange(root/'exchange')
            self.assertEqual(result['status'], 'PASS')
            layout = k.Layout(); layout.read(str(root/'exchange/coil.gds'))
            next(layout.top_cell().shapes(layout.find_layer(133, 0)).each()).delete()
            layout.write(str(root/'missing-via.gds'))
            with self.assertRaisesRegex(ValueError, 'physical mask changed'):
                reference.compare_geometry(reference.FIXTURE/'coil.gds', root/'missing-via.gds')
            layout = k.Layout(); layout.read(str(root/'exchange/coil.oas'))
            shape = next(s for s in layout.top_cell().shapes(layout.find_layer(63, 0)).each() if s.is_text())
            text = shape.text; text.x += 5; shape.text = text
            layout.write(str(root/'moved-label.oas'))
            with self.assertRaisesRegex(ValueError, 'text appearance anchor'):
                reference.compare_geometry(reference.FIXTURE/'coil.gds', root/'moved-label.oas')

    def test_phase_only_fault_cannot_hide_behind_identical_magnitudes(self):
        np = reference.np
        good = reference.network((reference.FIXTURE/'openems-2um.s2p').read_text())
        fault = dict(good, scattering=good['scattering']*np.exp(.1j))
        np.testing.assert_allclose(abs(fault['scattering']), abs(good['scattering']))
        self.assertGreater(reference.compare(fault, good)['maximum_absolute_s_error'], .05)
        self.assertEqual(reference.compare(good, good)['maximum_absolute_s_error'], 0)

    def test_resistance_error_is_visible_despite_small_reactive_error(self):
        good = reference.network((reference.FIXTURE/'openems-2um.s2p').read_text())
        fault = dict(good, differential=2*good['differential'].real+1j*good['differential'].imag)
        report = reference.compare(fault, good)
        self.assertAlmostEqual(report['maximum_relative_r_error'], 1)

    def test_missing_band_and_wrong_reference_cannot_be_extrapolated(self):
        good = reference.network((reference.FIXTURE/'openems-2um.s2p').read_text())
        for bad, message in [(dict(good, frequency=good['frequency'][10:]), 'entire declared'),
                             (dict(good, reference=75), 'Reference impedances')]:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                reference.compare(bad, good)

    def test_malformed_nonfinite_and_duplicate_frequency_are_rejected(self):
        text = (reference.FIXTURE/'openems-2um.s2p').read_text()
        lines = [line for line in text.splitlines() if line.strip() and not line.startswith('!')]
        data = next(i for i, line in enumerate(lines) if not line.startswith('#'))
        for changed in [lines[:data]+[lines[data]]+lines[data:],
                        lines[:data]+['nan '+lines[data].split(maxsplit=1)[1]]+lines[data+1:],
                        lines[:data]+['1 2 3']+lines[data+1:]]:
            with self.subTest(row=changed[data]), self.assertRaises(ValueError):
                reference.network('\n'.join(changed))


if __name__ == '__main__': unittest.main()
