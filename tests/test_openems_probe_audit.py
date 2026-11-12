"""Native coordinate evidence must not silently assume requested probe positions."""
import tempfile
import unittest
from pathlib import Path

from scripts.audit_openems_waves import probe_position


class ProbePositionTests(unittest.TestCase):
    def parse(self, text, kind='it'):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'port'
            path.write_text(text)
            return probe_position(path, kind, {'start_um':[-14.,-24.,14.2303],
                                              'stop_um':[-11.,-21.,336.1303]})

    def test_current_header_preserves_actual_staggered_plane_and_loop(self):
        text = ('% time-domain current probe by openEMS\n'
                '% start-coordinates: (-1.5e-05,-2.5e-05,0.000169479) m -> [3,4,8]\n'
                '% stop-coordinates: (-1e-05,-2e-05,0.000169479) m -> [6,7,8]\n'
                '% t/s current\n0 0\n1e-15 1\n')
        actual = self.parse(text)
        self.assertEqual(actual['requested_bounds_um'], [[-14.,-24.,175.1803],[-11.,-21.,175.1803]])
        for a,b in zip(actual['actual_bounds_um'][0], [-15.,-25.,169.479]):
            self.assertAlmostEqual(a,b)
        for a,b in zip(actual['displacement_um'][0], [-1.,-1.,-5.7013]):
            self.assertAlmostEqual(a,b)

    def test_voltage_path_uses_center_and_full_vertical_span(self):
        actual = self.parse('% start-coordinates: (-1.3e-05,-2.3e-05,1.42303e-05) m\n'
                            '% stop-coordinates: (-1.3e-05,-2.3e-05,0.0003361303) m\n0 0\n', 'ut')
        self.assertEqual(actual['requested_bounds_um'], [[-12.5,-22.5,14.2303],[-12.5,-22.5,336.1303]])
        for delta in actual['displacement_um']:
            self.assertAlmostEqual(delta[0],-.5)
            self.assertAlmostEqual(delta[1],-.5)
            self.assertAlmostEqual(delta[2],0.)

    def test_missing_units_coordinates_and_post_data_headers_are_rejected(self):
        good = '% start-coordinates: (0,0,0) m\n% stop-coordinates: (0,0,1) m\n'
        for text in ('0 0\n', good.replace(') m', ') um'), good.splitlines()[0]+'\n', '0 0\n'+good):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'Missing native probe coordinates'):
                self.parse(text)

    def test_nonfinite_dimension_and_duplicate_coordinates_are_rejected(self):
        good = '% start-coordinates: (0,0,0) m\n% stop-coordinates: (0,0,1) m\n'
        for text in (good.replace('(0,0,0)', '(nan,0,0)'), good.replace('(0,0,0)', '(1e309,0,0)'),
                     good.replace('(0,0,0)', '(0,0)'), good.replace('(0,0,0)', '(bad,0,0)'), good+good):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'Malformed native probe coordinates'):
                self.parse(text)


if __name__ == '__main__':
    unittest.main()
