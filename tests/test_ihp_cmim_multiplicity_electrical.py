"""Reject mistaken physical counts and geometry before electrical comparison."""
from pathlib import Path
import json
import tempfile
import unittest

from scripts.check_ihp_cmim_multiplicity_electrical import device_lines, expected_devices, constants, linked_inputs, relative_error, sha
from scripts.qualify_ihp_cmim_multiplicity_electrical import render


class MultiplicityElectricalTests(unittest.TestCase):
    def test_portable_error_uses_exact_components(self):
        self.assertEqual(relative_error(1+2j, 1+1j), 0.7071067811865476)
        self.assertEqual(relative_error(1+1j, 1+1j), 0.0)
        for actual, expected in ((1j, 0j), (complex(float('nan'), 1), 1j), (1j, complex(float('inf'), 1))):
            with self.assertRaises(ValueError):
                relative_error(actual, expected)

    def test_unfiltered_physical_units_preserve_perimeter_and_order(self):
        text = '.SUBCKT coupon C2 C1\nC$1 C1 C2 cap_cmim w=7u l=7u A=49p P=28u m=1\n' \
               'C$2 C1 C2 cap_cmim w=7u l=7u A=49p P=28u m=1\n.ENDS coupon\n'
        rows = device_lines(text, physical=True)
        self.assertEqual(len(rows), 2)
        for altered in (text.replace('A=49p', 'A=98p'), text.replace('P=28u', 'P=42u'),
                        text.replace('C$2 C1 C2', 'C$2 C2 C1'), text.replace('m=1', 'm=2'),
                        text.replace('C$2', 'C$1'), text.replace('.ENDS', '.param injected=1\n.ENDS'),
                        text.replace('w=7u', 'w=7.0000000000000000000000000000000001u')):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                device_lines(altered, physical=True)

    def test_unexpected_reference_statements_and_parameters_reject(self):
        text = '.subckt coupon C1 C2\nX1 C1 C2 cap_cmim w=7u l=7u m=2 mm_ok=1\n.ends coupon'
        self.assertEqual(device_lines(text)[0]['values']['m'], '2')
        for altered in (text.replace('m=2', 'm=NaN'), text.replace('m=2', 'm=2 m=3'),
                        text.replace('mm_ok=1', 'mm_ok=0'), text.replace('C1 C2 cap_cmim', 'C1 junk cap_cmim'),
                        text.replace('.ends', '.include evil.lib\n.ends')):
            with self.subTest(altered=altered), self.assertRaises((ValueError, ArithmeticError)):
                device_lines(altered)

    def test_literal_pair_retains_two_series_resistors_and_perimeters(self):
        cap, resistance = constants('cap_typ')
        self.assertAlmostEqual(cap / 1e-15, 74.62, places=10)
        self.assertEqual(resistance, 0.055)
        self.assertEqual(len(expected_devices('literal', {}, 'cap_typ')), 2)
        self.assertIn('w=7u l=14u m=1', expected_devices('areaonly', {}, 'cap_typ')[0])

    def test_producer_uses_source_corners_without_scaling_perimeter(self):
        root = Path(__file__).resolve().parents[1]
        models = root/'icstudio/assets/pdks/ihp-sg13g2/libs.tech/ngspice/models'
        m2 = device_lines('.subckt coupon C1 C2\nX1 C1 C2 cap_cmim w=7u l=7u m=2 mm_ok=1\n.ends coupon')
        pair = device_lines('.subckt coupon C1 C2\nX1 C1 C2 cap_cmim w=7u l=7u m=1 mm_ok=1\n'
                            'X2 C1 C2 cap_cmim w=7u l=7u m=1 mm_ok=1\n.ends coupon')
        native = device_lines('.subckt coupon C1 C2\nC1 C1 C2 cap_cmim w=7u l=7u A=49p P=28u m=1\n'
                              'C2 C1 C2 cap_cmim w=7u l=7u A=49p P=28u m=1\n.ends coupon', physical=True)
        inputs = {name: {'records': rows} for name, rows in (('m2', m2), ('pair', pair), ('native', native))}
        for section, expected_ff in (('cap_typ', 74.62), ('cap_bcs', 67.27), ('cap_wcs', 81.97)):
            text = render(inputs, section, (models/'capacitors_mod.lib').read_text(), (models/'cornerCAP.lib').read_text())
            literal = text.split('.subckt literal C1 C2\n')[1].split('.ends literal')[0].splitlines()
            self.assertEqual(len(literal), 4)
            self.assertAlmostEqual(float(literal[1].split()[-1])/1e-15, expected_ff, places=9)
            self.assertEqual(float(literal[0].split()[-1]), .055)

    def test_copied_input_requires_exact_full_physical_report_hash_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'inputs').mkdir()
            names = ['m2-0', 'pair-0', 'm2-90', 'pair-90', 'm1-0', 'm3-0', 'wrong-wire-0',
                     'missing-contact-0', 'wrong-width-0', 'physical-width-0']
            cases = [dict(name=name, raw_units=2, strict_lvs='passed' if name in names[:4] else 'failed') for name in names]
            by_name = {row['name']: row for row in cases}
            inputs, originals = {}, {}
            for rotation in (0, 90):
                inputs[str(rotation)] = {}
                for kind in ('m2', 'pair', 'native'):
                    count = 1 if kind == 'm2' else 2
                    lines = [f'{"C" if kind == "native" else "X"}{i} C1 C2 cap_cmim w=7u l=7u ' +
                             ('A=49p P=28u m=1' if kind == 'native' else f'm={2 if kind == "m2" else 1} mm_ok=1')
                             for i in range(count)]
                    text = '.subckt coupon C1 C2\n' + '\n'.join(lines) + '\n.ends coupon\n'
                    path = root/f'inputs/{kind}-{rotation}.spice'
                    path.write_text(text)
                    inputs[str(rotation)][kind] = dict(sha256=sha(path), records=device_lines(text, physical=kind == 'native'))
                    case = f'{"m2" if kind == "native" else kind}-{rotation}'
                    relative = f'{case}/job/physical-flow/' + ('lvs-extraction/native.cir' if kind == 'native' else 'schematic.spice')
                    originals[relative] = sha(path)
                    by_name[case]['native_sha256' if kind == 'native' else 'schematic_sha256'] = sha(path)
            report = dict(status='PASS_FINITE_MULTIPLICITY_READBACK', cases=cases, qualified=False, installed_acceptance=False)
            report_path = root/'physical-reader-report.json'
            receipt_path = root/'physical-inputs.json'
            def save():
                report_path.write_text(json.dumps(report))
                receipt_path.write_text(json.dumps(dict(scope='audited full physical multiplicity output', inputs=inputs,
                    original_input_hashes=originals, physical_reader_report_sha256=sha(report_path))))
            save()
            self.assertEqual(linked_inputs(root), inputs)
            by_name['m2-0']['schematic_sha256'] = '0' * 64
            save()
            with self.assertRaisesRegex(ValueError, 'independently accepted physical record'):
                linked_inputs(root)


if __name__ == '__main__':
    unittest.main()
