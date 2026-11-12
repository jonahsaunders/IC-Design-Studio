"""Finite three-port semantics and provenance controls; no generic device claim."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('ct_audit', ROOT/'scripts/audit_ihp_ct_reference.py')
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
reader = audit.reader


def encode(scattering, mode='RI', frequencies=(1e6,)):
    lines = ['# HZ S '+mode+' R 50']
    for f in frequencies:
        pairs = []
        for value in np.asarray(scattering).reshape(-1):
            if mode == 'RI':
                a, b = value.real, value.imag
            else:
                a = abs(value) if mode == 'MA' else 20*np.log10(abs(value))
                b = np.angle(value, deg=True)
            pairs.extend((format(a, '.17g'), format(b, '.17g')))
        # Wrap every three complex entries; use comments on continuation lines.
        lines.extend([format(f, '.17g')+' '+' '.join(pairs[:6]),
                      ' '.join(pairs[6:12])+' ! row 2', ' '.join(pairs[12:])])
    return '\n'.join(lines)+'\n'


class ThreePortSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.s = np.asarray([[.11+.01j, .12+.02j, .13+.03j],
                             [.21+.04j, .22+.05j, .23+.06j],
                             [.31+.07j, .32+.08j, .33+.09j]])

    def test_all_nine_row_major_entries_and_wrapped_formats(self):
        for mode in ('RI', 'MA', 'DB'):
            with self.subTest(mode=mode):
                network = reader.touchstone3(encode(self.s, mode, (1e6, 2e6)))
                np.testing.assert_allclose(network['scattering'], [self.s, self.s], rtol=1e-14, atol=1e-15)
                self.assertEqual(network['frequency_hz'], [1e6, 2e6])
                self.assertNotEqual(network['scattering'][0][0][1], network['scattering'][0][1][0])

    def test_nonsymmetric_full_y_and_z(self):
        network = reader.touchstone3(encode(self.s))
        eye = np.eye(3)
        y = np.linalg.solve((eye+self.s).T, (eye-self.s).T).T/50
        z = np.linalg.solve((eye-self.s).T, (eye+self.s).T).T*50
        np.testing.assert_allclose(reader.matrices(network, 'y')[0], y, rtol=1e-13, atol=1e-15)
        np.testing.assert_allclose(reader.matrices(network, 'z')[0], z, rtol=1e-13, atol=1e-13)

    def test_reference_scaling_and_units(self):
        text = encode(self.s).replace('# HZ S RI R 50', '# KHZ S RI R 75')
        network = reader.touchstone3(text)
        self.assertEqual(network['frequency_hz'], [1e9])
        self.assertEqual(network['reference_ohm'], 75)
        np.testing.assert_allclose(reader.matrices(network, 'y')[0], audit.s_to_y([self.s], 75)[0])

    def test_distinct_center_tap_experiments_and_roles(self):
        # Independent resistor-network nodal matrix. Hand-derived rational answers.
        y = np.asarray([[2., -1., -.5], [-1., 3., -.25], [-.5, -.25, 1.]])
        s = audit.y_to_s([y], 50)[0]
        network = reader.touchstone3(encode(s))
        result = reader.center_tap_impedances(network, coil_ports=(0, 1), center_tap=2)
        expected = dict(differential_current_ct_open=39/62, differential_current_ct_grounded=3/5,
                        differential_voltage_ct_grounded=4/7, center_tap_ends_grounded=1,
                        first_end_others_grounded=.5, second_end_others_grounded=1/3)
        for key, value in expected.items():
            self.assertAlmostEqual(result[key][0].real, value, places=12)
            self.assertAlmostEqual(result[key][0].imag, 0, places=12)
        permutation = [2, 0, 1]
        permuted = reader.touchstone3(encode(s[np.ix_(permutation, permutation)]))
        moved = reader.center_tap_impedances(permuted, coil_ports=(1, 2), center_tap=0)
        for key in expected:
            np.testing.assert_allclose(result[key], moved[key], rtol=1e-12, atol=1e-13)

    def test_terminal_roles_are_required_and_unique(self):
        network = reader.touchstone3(encode(self.s))
        for coils, ct in (((0, 1), 1), ((0, 0), 2), ((True, 0), 2), ((1,), 2), ((0, 1), 3)):
            with self.subTest(coils=coils, ct=ct), self.assertRaises(ValueError):
                reader.center_tap_impedances(network, coil_ports=coils, center_tap=ct)

    def test_incomplete_options_and_unsupported_v2_reject(self):
        text = encode(self.s)
        cases = [text.split('\n', 1)[1], text+'# HZ S RI R 50\n', text.replace('S RI', 'Y RI'),
                 text.replace('R 50', 'R 0'), text.replace('R 50', 'R inf'),
                 text+'[End]\n', text.rsplit(' ', 1)[0], text+'extra\n']
        for case in cases:
            with self.subTest(case=case[:50]), self.assertRaises(ValueError):
                reader.touchstone3(case)

    def test_nonfinite_magnitude_and_frequency_reject(self):
        valid = encode(self.s)
        cases = [valid.replace('1000000', '0', 1), valid.replace('1000000', '-1', 1),
                 valid.replace('1000000', 'nan', 1), valid.replace('1000000', 'inf', 1),
                 encode(self.s, frequencies=(1e6, 1e6)), encode(self.s, frequencies=(2e6, 1e6)),
                 '# HZ S MA R 50\n1 '+' '.join(['-1 0']*9),
                 '# HZ S DB R 50\n1 '+' '.join(['100000 0']*9)]
        for case in cases:
            with self.subTest(case=case[:60]), self.assertRaises(ValueError):
                reader.touchstone3(case)

    def test_public_conversion_rejects_truncated_or_malformed_network(self):
        network = reader.touchstone3(encode(self.s))
        mutations = [lambda n: n['frequency_hz'].append(2e6), lambda n: n['scattering'].clear(),
                     lambda n: n['scattering'][0].pop(), lambda n: n['scattering'][0][1].append(0),
                     lambda n: n['scattering'][0][2].__setitem__(1, float('nan')),
                     lambda n: n.__setitem__('reference_ohm', 0), lambda n: n.__setitem__('reference_ohm', True),
                     lambda n: n.__setitem__('reference_ohm', float('inf')),
                     lambda n: n.__setitem__('ports', 3.), lambda n: n.__setitem__('frequency_hz', [0])]
        for mutate in mutations:
            broken = copy.deepcopy(network)
            mutate(broken)
            for operation in (lambda: reader.matrices(broken, 'y'),
                              lambda: reader.center_tap_impedances(broken, coil_ports=(0, 1), center_tap=2)):
                with self.assertRaises(ValueError):
                    operation()

    def test_singular_conversion_rejects(self):
        for sign, kind in ((1, 'z'), (-1, 'y')):
            with self.assertRaises(ValueError):
                reader.matrices(reader.touchstone3(encode(np.eye(3)*sign)), kind)

    def test_reference_scaling_overflow_rejects_without_invented_impedance_limit(self):
        for reference, s, kind in ((1e-320, np.zeros((3, 3)), 'y'), (1e308, np.eye(3)*.9, 'z')):
            text = encode(s).replace('R 50', 'R '+str(reference))
            with self.assertRaises(ValueError):
                reader.matrices(reader.touchstone3(text), kind)
        # Finite conversions remain valid even for unusually small or large reference values.
        for reference in (1e-200, 1e200):
            text = encode(np.zeros((3, 3))).replace('R 50', 'R '+str(reference))
            self.assertTrue(np.isfinite(reader.matrices(reader.touchstone3(text), 'y')).all())


class RetainedReferenceTests(unittest.TestCase):
    def test_real_source_full_matrix_and_finite_scope(self):
        result = audit.audit()
        self.assertEqual(result['samples'], 82)
        self.assertEqual(result['band_hz'], [1e7, 6e10])
        self.assertEqual(result['port_order'], ['p1', 'p2', 'ct'])
        self.assertEqual(result['common_reference'], '0')
        for flag in ('fresh_spice_execution', 'measurement', 'original_em_reproduced',
                     'catalog_binding_resolved', 'qualified', 'chunk_complete'):
            self.assertIs(result[flag], False)

    def test_original_license_bytes_and_inventory_are_bound(self):
        for filename in ('LICENSE', 'NOTICES.txt', 'SOURCE.json', 'fitted.sp', 'reference.s3p'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                copied = Path(tmp)/'fixture'
                shutil.copytree(audit.FIXTURE, copied)
                with (copied/filename).open('ab') as stream:
                    stream.write(b'\nchanged\n')
                with self.assertRaises(ValueError):
                    audit.verify_sources(copied)

    def test_rebinding_changed_source_does_not_bypass_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp)/'fixture'
            shutil.copytree(audit.FIXTURE, copied)
            (copied/'fitted.sp').write_bytes((copied/'fitted.sp').read_bytes().replace(b'0.360306', b'0.760306'))
            source = json.loads((copied/'SOURCE.json').read_bytes())
            next(r for r in source['files'] if r['file'] == 'fitted.sp')['sha256'] = audit.sha(copied/'fitted.sp')
            (copied/'SOURCE.json').write_text(json.dumps(source))
            with self.assertRaises(ValueError):
                audit.verify_sources(copied)

    def test_passive_circuit_nodes_and_coupling_are_explicit(self):
        parsed = audit.parse_circuit((audit.FIXTURE/'fitted.sp').read_text())
        self.assertEqual(parsed['nodes'][:3], ['p1', 'p2', 'ct'])
        self.assertEqual(parsed['ground'], '0')
        self.assertNotIn('b', parsed['nodes'])
        self.assertEqual(len(parsed['elements']), 41)
        self.assertEqual(len(parsed['coupling']), 4)

    def test_unsupported_directives_and_terminal_rewrites_reject(self):
        original = (audit.FIXTURE/'fitted.sp').read_text()
        cases = [original.replace('p1 p2 ct', 'p1 ct p2'), original.replace('p1 p2 ct', 'p1 p2 ct b'),
                 original.replace(' 0 ', ' body '), original.replace('.ENDS', '.include external.sp\n.ENDS'),
                 original.replace('.ENDS', 'Bfake p1 0 1\n.ENDS'), original.replace('.ENDS', '.param x=1\n.ENDS'),
                 original.replace('0.360306', '-0.360306'), original.replace('0.360306', 'nan'),
                 original.replace('.ENDS', 'Rs_h1_1 p1 p2 1\n.ENDS'), original.replace('.ENDS', '')]
        for case in cases:
            with self.subTest(case=case[-60:]), self.assertRaises(ValueError):
                audit.parse_circuit(case)

    def test_mutual_coupling_contract_and_passivity_reject(self):
        original = (audit.FIXTURE/'fitted.sp').read_text()
        cases = [original.replace('0.207148', '1.0'), original.replace('0.207148', '.999'),
                 original.replace('K_h1_1_h2_1 Ls_h1_1', 'K_h1_1_h2_1 Missing'),
                 original.replace('.ENDS', 'Kduplicate Ls_h1_1 Ls_h2_1 .2\n.ENDS')]
        for case in cases:
            with self.assertRaises(ValueError):
                audit.parse_circuit(case)

    def test_mutual_dot_orientation_changes_actual_response(self):
        original = (audit.FIXTURE/'fitted.sp').read_text()
        normal = audit.circuit_admittance(audit.parse_circuit(original), [1e9])
        reversed_dot = audit.circuit_admittance(audit.parse_circuit(original.replace('0.207148', '-0.207148')), [1e9])
        self.assertGreater(float(np.max(abs(normal-reversed_dot))), .01)

    def test_each_native_excitation_has_distinct_port_and_common_return(self):
        for i, port in enumerate(audit.PORTS):
            text = audit.deck([1e7], i)
            self.assertIn(f'V{port} {port} 0 DC 0 AC 1\n', text)
            self.assertEqual(text.count(' DC 0 AC 1'), 1)
            self.assertEqual(text.count(' DC 0 AC 0'), 2)
            self.assertIn('Xref p1 p2 ct ct_inductor_model', text)


if __name__ == '__main__':
    unittest.main()
