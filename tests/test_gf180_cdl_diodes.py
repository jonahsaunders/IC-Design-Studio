"""CDL antenna geometry must survive a real KLayout reader and comparison."""
from pathlib import Path
import tempfile
import unittest

import klayout.db as k

from scripts.gf180_cdl_diodes import enable_geometry, normalize


CELL = '''* Independent antenna reference form.
.SUBCKT antenna I VDD VNW VPW VSS
d0 VPW I diode_nd2ps_06v0 0.2034p 1.85u $m=1
d1 I VNW diode_pd2nw_06v0 0.2034p 1.85u $m=1
.ENDS antenna
'''


class DiodeCDLTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.count = 0

    def read(self, text, geometry=False):
        self.count += 1
        path = self.root / (str(self.count) + '.cdl')
        path.write_text(text, encoding='utf-8', newline='')
        netlist = k.Netlist()
        netlist.read(str(path), k.NetlistSpiceReader())
        if geometry:
            enable_geometry(netlist)
        return netlist

    def test_positional_source_fails_stock_reader(self):
        with self.assertRaisesRegex(RuntimeError, 'two nodes'):
            self.read(CELL)

    def test_actual_reader_preserves_polarity_models_and_geometry(self):
        text, changes = normalize(CELL)
        self.assertEqual(len(changes), 2)
        self.assertEqual(changes[0]['area_si'], '2.034E-13')
        self.assertEqual(changes[0]['perimeter_si'], '0.00000185')
        netlist = self.read(text)
        circuit = netlist.circuit_by_name('ANTENNA')
        devices = list(circuit.each_device())
        self.assertEqual(len(devices), 2)
        expected = [('DIODE_ND2PS_06V0', 'VPW', 'I'), ('DIODE_PD2NW_06V0', 'I', 'VNW')]
        for device, (model, anode, cathode) in zip(devices, expected):
            self.assertEqual(device.device_class().name, model)
            self.assertEqual(device.net_for_terminal('A').name, anode)
            self.assertEqual(device.net_for_terminal('C').name, cathode)
            self.assertAlmostEqual(device.parameter('A'), .2034, places=12)
            self.assertAlmostEqual(device.parameter('P'), 1.85, places=12)

    def test_multiplicity_scales_both_native_parameters(self):
        text, changes = normalize(CELL.replace('$m=1', '$m=3'))
        netlist = self.read(text)
        for device in netlist.circuit_by_name('ANTENNA').each_device():
            self.assertAlmostEqual(device.parameter('A'), .6102, places=12)
            self.assertAlmostEqual(device.parameter('P'), 5.55, places=12)
        self.assertTrue(all(row['multiplicity'] == 3 for row in changes))

    def test_equivalent_scientific_notation_and_case(self):
        source = CELL.replace('0.2034p 1.85u $m=1', '2.034e-13 1.85E-6 $M=1')
        actual = self.read(normalize(source)[0])
        expected = self.read(normalize(CELL)[0])
        self.assertTrue(k.NetlistComparer().compare(actual, expected))

    def test_named_parameters_are_validated_and_idempotent(self):
        text, changes = normalize(CELL)
        self.assertEqual(normalize(text), (text, []))
        self.assertEqual(len(changes), 2)

    def test_preserves_other_elements_and_continuation_bytes(self):
        extra = 'M_keep D G S B nfet_05v0 W=1.32U\r\n+ L=1U\r\n'
        source = CELL.replace('\n', '\r\n').replace('.ENDS antenna', extra + '.ENDS antenna')
        text, _ = normalize(source)
        self.assertIn(extra, text)
        self.assertIn('* Independent antenna reference form.\r\n', text)
        self.assertEqual(text.count('\r\n'), source.count('\r\n'))

    def test_diode_and_subcircuit_continuations(self):
        source = CELL.replace('.SUBCKT antenna I VDD VNW VPW VSS', '.SUBCKT antenna I VDD\n+ VNW VPW VSS')
        source = source.replace('0.2034p 1.85u $m=1', '0.2034p\n+ 1.85u $m=1')
        text, changes = normalize(source)
        self.assertEqual(len(changes), 2)
        self.assertEqual(changes[0]['last_line'], changes[0]['line'] + 1)
        self.assertTrue(k.NetlistComparer().compare(self.read(text), self.read(normalize(CELL)[0])))

    def test_reader_comparison_rejects_real_parameter_and_polarity_faults(self):
        reference = self.read(normalize(CELL)[0], geometry=True)
        faults = [CELL.replace('0.2034p', '0.3034p', 1), CELL.replace('1.85u', '2.85u', 1),
                  CELL.replace('d0 VPW I', 'd0 I VPW'), CELL.replace('$m=1', '$m=2', 1),
                  CELL.replace('d1 I VNW diode_pd2nw_06v0 0.2034p 1.85u $m=1\n', '')]
        for source in faults:
            with self.subTest(source=source):
                self.assertFalse(k.NetlistComparer().compare(self.read(normalize(source)[0], geometry=True), reference))

    def test_default_comparison_misses_geometry_faults(self):
        reference = self.read(normalize(CELL)[0])
        for changed in (CELL.replace('0.2034p', '0.3034p', 1),
                        CELL.replace('1.85u', '2.85u', 1), CELL.replace('$m=1', '$m=2', 1)):
            with self.subTest(source=changed):
                self.assertTrue(k.NetlistComparer().compare(self.read(normalize(changed)[0]), reference))

    def test_geometry_guard_preserves_values_and_other_classes(self):
        source = CELL.replace('.ENDS antenna', 'M1 I VDD VSS VPW nfet_05v0 W=1.32U L=1U\n.ENDS antenna')
        netlist = self.read(normalize(source)[0])
        before = netlist.to_s()
        mos = netlist.device_class_by_name('NFET_05V0')
        parameters = [(p.name, p.is_primary) for p in mos.parameter_definitions()]
        self.assertEqual(enable_geometry(netlist), ['DIODE_ND2PS_06V0', 'DIODE_PD2NW_06V0'])
        self.assertEqual(netlist.to_s(), before)
        self.assertEqual([(p.name, p.is_primary) for p in mos.parameter_definitions()], parameters)
        for name in ('DIODE_ND2PS_06V0', 'DIODE_PD2NW_06V0'):
            self.assertTrue(all(p.is_primary for p in netlist.device_class_by_name(name).parameter_definitions()))
        self.assertTrue(k.NetlistComparer().compare(netlist, self.read(normalize(source)[0], geometry=True)))

    def test_geometry_guard_rejects_wrong_class_and_custom_comparer(self):
        netlist = k.Netlist()
        cls = k.DeviceClassCapacitor()
        cls.name = 'diode_nd2ps_06v0'
        netlist.add(cls)
        with self.assertRaisesRegex(ValueError, 'Expected a diode'):
            enable_geometry(netlist)
        netlist = self.read(normalize(CELL)[0])
        cls = netlist.device_class_by_name('DIODE_ND2PS_06V0')
        cls.equal_parameters = k.EqualDeviceParameters(cls.parameter_id('A'), 1, 0)
        with self.assertRaisesRegex(ValueError, 'custom diode parameter comparer'):
            enable_geometry(netlist)

    def test_bad_geometry_and_multiplicity_fail_closed(self):
        for bad in ('0', '-1p', 'NaN', 'Inf', '1e999', '1e-999', '1e300', '1um', '{area}'):
            with self.subTest(area=bad), self.assertRaises(ValueError):
                normalize(CELL.replace('0.2034p', bad, 1))
        for bad in ('$m=0', '$m=-1', '$m=1.5', '$m={m}', '$m=nan', '$m=1 $m=2'):
            with self.subTest(m=bad), self.assertRaises(ValueError):
                normalize(CELL.replace('$m=1', bad, 1))

    def test_missing_extra_unknown_and_duplicate_fields_fail_closed(self):
        for source in (CELL.replace('diode_nd2ps_06v0', 'unreviewed_model'),
                       CELL.replace(' 1.85u', '', 1), CELL.replace('$m=1', '$m=1 $unknown=2', 1),
                       CELL.replace('0.2034p 1.85u $m=1', 'AREA=0.2034p PJ=1.85u M=1', 1),
                       CELL.replace('0.2034p 1.85u $m=1', 'A=0.2034p A=1.85u M=1', 1),
                       CELL.replace('d1 I VNW', 'D0 I VNW')):
            with self.subTest(source=source), self.assertRaises(ValueError):
                normalize(source)

    def test_invalid_subcircuit_and_continuation_scopes(self):
        for source in (CELL.replace('.ENDS antenna\n', ''), CELL.replace('.ENDS antenna', '.ENDS different'),
                       CELL.replace('.SUBCKT antenna I VDD VNW VPW VSS\n', ''),
                       '+ orphan\n' + CELL, '\n+ orphan\n' + CELL,
                       '* comment\n+ orphan\n' + CELL,
                       CELL.replace('d0 VPW I', '.SUBCKT nested\nd0 VPW I')):
            with self.subTest(source=source), self.assertRaises(ValueError):
                normalize(source)

    def test_no_diodes_no_reformatting(self):
        source = '* comment\r\n.SUBCKT mos D G S B\r\nM1 D G S B nfet_05v0 W=1U L=1U\r\n.ENDS'
        self.assertEqual(normalize(source), (source, []))


if __name__ == '__main__':
    unittest.main()
