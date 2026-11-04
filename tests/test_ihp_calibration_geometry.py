import unittest
from scripts.ihp_calibration_geometry import compare


class IHPCalibrationGeometryTests(unittest.TestCase):
    def setUp(self):
        self.wires=[dict(name='WIRE',layer='Metal1',box=[0,0,160,15840])]
        self.native='scale 1000 1 1\nnode "WIRE" 0 1 0 0 m1 0 0 25344 3200\n'

    def test_exact_native_rectangle(self):
        self.assertTrue(compare(self.native,self.wires)['passed'])

    def test_measurement_pin_extension_is_rejected(self):
        result=compare(self.native.replace('25344 3200','25600 3232'),self.wires)
        self.assertFalse(result['passed']);self.assertEqual(result['failed_nets'],1)

    def test_wrong_layer_or_scale_is_rejected(self):
        for value in (self.native.replace(' m1 ',' m2 '),self.native.replace('1 1\n','1 0.5\n')):
            with self.subTest(value=value):self.assertFalse(compare(value,self.wires)['passed'])

    def test_finer_native_grid_preserves_exact_geometry(self):
        text='scale 1000 1 .1\nnode "WIRE" 0 1 0 0 m1 0 0 2534400 32000\n'
        self.assertTrue(compare(text,self.wires)['passed'])

    def test_missing_duplicate_and_multilayer_nodes_are_rejected(self):
        for text in ('scale 1000 1 1\n',self.native+self.native.splitlines()[1]+'\n',
                     self.native.replace('0 0 25344','1 4 25344')):
            with self.subTest(text=text),self.assertRaises(ValueError):compare(text,self.wires)

    def test_devices_and_nonfinite_scale_are_rejected(self):
        for text in (self.native+'device mosfet unexpected\n',self.native.replace('1 1\n','1 nan\n')):
            with self.subTest(text=text),self.assertRaises(ValueError):compare(text,self.wires)

    def test_only_empty_implicit_substrate_is_allowed(self):
        substrate='substrate "SUB" 0 0 -100 -100 space 0 0\n'
        self.assertTrue(compare(self.native+substrate,self.wires)['passed'])
        for bad in (substrate.replace('0 0 -100','0 1 -100'),substrate.replace('space 0 0','space 1 4'),
                    substrate.replace('space 0 0','space invalid 0'),substrate*2):
            with self.subTest(bad=bad),self.assertRaises(ValueError):compare(self.native+bad,self.wires)
