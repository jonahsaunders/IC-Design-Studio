import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from scripts import qualify_sky130_mim_passive_corners as runner
from scripts import audit_sky130_mim_passive_corners as audit

CONTRACT = json.loads((runner.ROOT / runner.CONTRACT).read_bytes())


def write_raw(path, plate=1, section='tt', fault=None):
    coefficients = CONTRACT['passive_sections'][section]['coefficients']
    names = ['frequency']
    names += ['i(vp_' + k.replace('-', '_') + ')' for k in audit.PATHS]
    names += ['v(p_' + k.replace('-', '_') + ')' for k in audit.PATHS]
    names += ['v(par_' + k + ')' for k in (*audit.PARAMETERS, 'mc_mm_switch', 'mc_pr_switch')]
    header = 'Title: Synthetic independent RC control\nPlotname: AC Analysis\nFlags: complex\n'
    header += f'No. Variables: {len(names)}\nNo. Points: 8\nVariables:\n'
    header += ''.join(f'\t{i}\t{name}\t' + ('frequency grid=3' if i == 0 else 'voltage') + '\n' for i, name in enumerate(names))
    payload = []
    for i in range(8):
        frequency = 1e3 * 10 ** i; values = {'frequency': complex(frequency, 0)}
        for name in audit.PATHS:
            r, c = audit.expected(plate, coefficients, name)
            values['i(vp_' + name.replace('-', '_') + ')'] = -1 / complex(r, -1 / (2 * math.pi * frequency * c))
            values['v(p_' + name.replace('-', '_') + ')'] = complex(1)
        values.update({'v(par_' + k + ')': complex(coefficients.get(k, 0)) for k in (*audit.PARAMETERS, 'mc_mm_switch', 'mc_pr_switch')})
        if fault == 'nonfinite': values['i(vp_schematic)'] = complex(float('nan'), 1)
        if fault == 'voltage': values['v(p_schematic)'] = complex(.5)
        if fault == 'coefficient': values['v(par_camimc)'] *= 1.01
        for j, name in enumerate(names):
            payload.append((str(i) + '\t' if j == 0 else '\t') + f'{values[name].real:.17g},{values[name].imag:.17g}\n')
    path.write_bytes((header + 'Values:\n' + ''.join(payload)).encode())


class MiMPassiveCorners(unittest.TestCase):
    def test_selection_is_explicit_unique_and_nonempty(self):
        self.assertEqual(len(runner.selected([1, 2], list(runner.SECTIONS), [0, 90])), 20)
        for values in (([], ['tt'], [0]), ([1, 1], ['tt'], [0]), ([1], ['nominal'], [0]), ([1], ['tt'], [45])):
            with self.assertRaises(ValueError): runner.selected(*values)

    def test_each_section_matches_independent_equations_and_detects_faults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'probe.raw'
            for plate in (1, 2):
                for section in runner.SECTIONS:
                    with self.subTest(plate=plate, section=section):
                        write_raw(path, plate, section)
                        result = runner.measure(path, plate, CONTRACT['passive_sections'][section]['coefficients'])
                        self.assertEqual(result['status'], 'PASS')
                        self.assertEqual(audit.check_raw(path, plate, CONTRACT['passive_sections'][section]['coefficients'], result), 8)

    def test_wrong_section_is_valid_native_data_but_wrong_selected_condition(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'probe.raw'; write_raw(path, section='hh')
            target = CONTRACT['passive_sections']['tt']['coefficients']
            result = runner.measure(path, 1, target, require_match=False)
            self.assertEqual(result['status'], 'MISMATCH')
            self.assertEqual(audit.check_raw(path, 1, CONTRACT['passive_sections']['hh']['coefficients'], result, target), 8)

    def test_native_failures_are_not_accepted_as_detected_faults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'probe.raw'
            for fault in ('nonfinite', 'voltage', 'coefficient'):
                write_raw(path, fault=fault)
                expected = {'nonfinite': 'Nonfinite', 'voltage': 'Incorrect native applied', 'coefficient': 'Expected response'}[fault]
                with self.assertRaisesRegex(ValueError, expected): runner.measure(path, 1, CONTRACT['passive_sections']['tt']['coefficients'])

    def test_independent_audit_recomputes_saved_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'probe.raw'; write_raw(path)
            coefficients = CONTRACT['passive_sections']['tt']['coefficients']
            result = runner.measure(path, 1, coefficients)
            for key in ('maximum_coefficient_normalized_error', 'maximum_relative_errors'):
                bad = copy.deepcopy(result)
                if key == 'maximum_relative_errors': bad[key]['wrong-count'] = 99
                else: bad[key] = 99
                with self.assertRaises(ValueError): audit.check_raw(path, 1, coefficients, bad)

    def test_native_circuit_rejects_duplicate_dimension_or_substitution(self):
        text = '.subckt device_coupon P N\nX1 P N sky130_fd_pr__cap_mim_m3_1 w=2 l=10\n.ends\n'
        self.assertEqual(audit.circuit_rows(text), 'sky130_fd_pr__cap_mim_m3_1')
        for changed in (text.replace('w=2', 'w=2 w=2'), text.replace('w=2', 'w=nan'), text.replace('P N sky', 'N P sky'), text.replace('X1', 'R1')):
            with self.assertRaises(ValueError): audit.circuit_rows(changed)

    def test_explicit_schematic_mf_does_not_weaken_native_contract(self):
        text = '.subckt device_coupon P N\nX1 P N sky130_fd_pr__cap_mim_m3_1 l=10 m=1 mf=1 w=2\n.ends\n'
        self.assertEqual(audit.circuit_rows(text, schematic=True), 'sky130_fd_pr__cap_mim_m3_1')
        with self.assertRaises(ValueError): audit.circuit_rows(text)
        with self.assertRaises(ValueError): audit.circuit_rows(text.replace('mf=1', 'mf=2'), schematic=True)

    def test_actual_export_deck_and_substitution_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); native = folder / 'native.spice'
            native.write_text(runner.independent((2, 10, 1)), encoding='utf-8')
            tech, _ = runner.load_technology('sky130A')
            staged = {'tt': '.lib /fixed/models.spice tt'}
            _, text = runner.circuit(tech, 2, native, staged['tt'])
            path = folder / 'probe.cir'; path.write_text(text, encoding='utf-8')
            audit.check_deck(path, 'tt', staged, native.as_posix(), 2)
            for changed in (text.replace('X_extracted p_extracted 0 device_coupon', 'X_extracted p_extracted 0 independent'), text.replace('.lib /fixed/models.spice tt', '.lib /fixed/models.spice hh'), text.replace('.end\n', '.include /unbound/other.spice\n.end\n'), text.replace('w=2.4 l=10 m=1', 'w=2.5 l=10 m=1')):
                path.write_text(changed, encoding='utf-8')
                with self.assertRaises(ValueError): audit.check_deck(path, 'tt', staged, native.as_posix(), 2)


if __name__ == '__main__': unittest.main()
