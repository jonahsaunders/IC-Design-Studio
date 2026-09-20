import json
from pathlib import Path
import tempfile
import unittest

from icstudio.magic_rc import normalize, finalize


ORIGINAL = '''scale 1000 2 100
port "IN" 1 0 0 0 0 m1
port "VSS" 2 0 1 0 1 m1
node "IN" 0 100 0 0 m1
node "N#" 0 60 10 0 m1
substrate "VSS" 0 0 0 1 m1
cap "IN" "N#" 40
'''
RESISTANCE = '''scale 1000 4 100
killnode "N#"
rnode "N.n0" 0 30000 10 0 0
rnode "N.t0" 0 10000 20 0 0
resist "N.n0" "N.t0" 10
rnode "IN" 0 10000 0 0 0
rnode "IN.t0" 0 30000 1 0 0
resist "IN" "IN.t0" 20
rnode "VSS" 0 0 0 1 0
'''


class MagicRCNormalizationTests(unittest.TestCase):
    def inputs(self, root, original=ORIGINAL, resistance=RESISTANCE):
        (root / 'top.ext').write_text(original)
        (root / 'top.res.ext').write_text(resistance)

    def test_matrix_conservation_with_internal_port_and_different_scales(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.inputs(root)
            result = normalize(root, 'top')
            self.assertEqual((root / 'top.raw.ext').read_text(), ORIGINAL)
            self.assertEqual((root / 'top.raw.res.ext').read_text(), RESISTANCE)
            self.assertEqual(result['generated_mutual_capacitors'], 4)
            self.assertEqual(result['resistor_count'], 2)
            self.assertEqual(result['nets']['N#']['weights'], {'N.n0': .75, 'N.t0': .25})
            self.assertEqual(result['nets']['VSS']['fallback']['anchor'], 'VSS')
            self.assertEqual(result['conservation']['maximum_error_af'], 0)
            values = {(v['a'], v['b']): v['normalized_af'] for v in result['conservation']['entries']}
            self.assertEqual(values[('IN', 'IN')], 280)
            self.assertEqual(values[('N#', 'N#')], 200)
            self.assertEqual(values[('IN', 'N#')], -80)
            self.assertNotIn('\ncap ', (root / 'top.ext').read_text())
            self.assertIn('rnode "N.n0" 0 22.5 ', (root / 'top.res.ext').read_text())
            self.assertIn('cap "IN" "N.n0" 3.75', (root / 'top.res.ext').read_text())
            self.assertEqual(json.loads((root / 'rc-normalization.json').read_text()), result)
            with self.assertRaisesRegex(ValueError, 'untouched'):
                normalize(root, 'top')

    def test_zero_weights_choose_nearest_origin_and_preserve_intrinsic_ground(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resistance = RESISTANCE.replace('30000', '0').replace('10000', '0')
            self.inputs(root, resistance=resistance)
            result = normalize(root, 'top')
            self.assertEqual(result['nets']['N#']['weights'], {'N.n0': 1.0})
            self.assertEqual(result['nets']['IN']['weights'], {'IN': 1.0})
            self.assertEqual(result['generated_mutual_capacitors'], 1)
            self.assertIn('rnode "N.n0" 0 30 ', (root / 'top.res.ext').read_text())

    def test_fail_closed_before_mutation(self):
        cases = [
            (ORIGINAL + 'use child instance 0 0 0 0\n', RESISTANCE, 'Unsupported'),
            (ORIGINAL + 'equiv "IN" "alias"\n', RESISTANCE, 'Unsupported'),
            (ORIGINAL, RESISTANCE.replace('N.t0" 10', 'IN.t0" 10'), 'crosses'),
            (ORIGINAL, RESISTANCE.replace('resist "N.n0" "N.t0" 10\n', ''), 'disconnected'),
            (ORIGINAL, RESISTANCE.replace('30000', 'nan'), 'finite'),
            (ORIGINAL, RESISTANCE.replace('scale 1000 4 100', 'scale 1000 4 200'), 'scales'),
            (ORIGINAL.replace('N#', 'ghost'), RESISTANCE, 'killed'),
            (ORIGINAL.replace('N#', 'IN#'), RESISTANCE.replace('N.', 'IN.').replace('N#', 'IN#'), 'Ambiguous'),
            (ORIGINAL + 'node "in" 0 0 1 0 m1\n', RESISTANCE, 'case-insensitive'),
            (ORIGINAL.replace('N#', 'N space#'), RESISTANCE, 'malformed'),
        ]
        for original, resistance, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.inputs(root, original, resistance)
                with self.assertRaisesRegex(ValueError, message):
                    normalize(root, 'top')
                self.assertEqual((root / 'top.ext').read_text(), original)
                self.assertEqual((root / 'top.res.ext').read_text(), resistance)
                self.assertFalse((root / 'top.raw.ext').exists())

    def test_capacitance_expansion_budget_is_checked_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.inputs(root)
            with self.assertRaisesRegex(ValueError, 'budget'):
                normalize(root, 'top', max_capacitors=3)
            self.assertEqual((root / 'top.ext').read_text(), ORIGINAL)
            self.assertFalse((root / 'rc-normalization.json').exists())

    def test_final_export_preserves_resistors_and_restores_tiny_mutual_capacitance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.inputs(root, original=ORIGINAL.replace('"N#" 40', '"N#" 0.0001'))
            normalize(root, 'top')
            exported = '.subckt top IN VSS\nR0 N.n0 N.t0 10\nR1 IN IN.t0 20\nC0 IN N.n0 0\n.ends\n'
            (root / 'extracted.spice').write_text(exported)
            result = finalize(root, 'top')
            final = (root / 'extracted.spice').read_text()
            self.assertIn('R0 N.n0 N.t0 10\nR1 IN IN.t0 20\n', final)
            self.assertEqual((root / 'raw-export.spice').read_text(), exported)
            self.assertEqual(result['export']['status'], 'passed')
            self.assertLess(result['export']['maximum_error_af'], 1e-12)
            self.assertEqual(result['export']['full_precision_capacitors'], 8)
            self.assertIn('e-23', final)

    def test_finalizer_rejects_exporter_graph_changes_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.inputs(root)
            normalize(root, 'top')
            exported = '.subckt top IN VSS\nR0 N.n0 IN.t0 10\nR1 IN IN.t0 20\n.ends\n'
            (root / 'extracted.spice').write_text(exported)
            with self.assertRaisesRegex(ValueError, 'resistance graph'):
                finalize(root, 'top')
            self.assertEqual((root / 'extracted.spice').read_text(), exported)
            self.assertFalse((root / 'raw-export.spice').exists())

    def test_finalizer_rejects_unmapped_device_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = ORIGINAL + 'device msubckt known 0 0 1 1 l=1 w=1 "VSS" "IN" 1 0 "VSS" 1 0 "N#" 1 0\n'
            self.inputs(root, original=original)
            normalize(root, 'top')
            exported = '.subckt top IN VSS\nR0 N.n0 N.t0 10\nR1 IN IN.t0 20\nX0 N.n0 ghost VSS VSS known w=1 l=1\n.ends\n'
            (root / 'extracted.spice').write_text(exported)
            with self.assertRaisesRegex(ValueError, 'unmapped endpoint'):
                finalize(root, 'top')
            self.assertFalse((root / 'raw-export.spice').exists())


if __name__ == '__main__':
    unittest.main()
