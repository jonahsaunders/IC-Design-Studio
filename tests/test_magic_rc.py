import json
from pathlib import Path
import tempfile
import unittest
import re

from icstudio.magic_rc import normalize, finalize, _node_candidates, _node_stems


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
    def test_indexed_names_preserve_literal_stems_exact_names_and_ambiguity(self):
        originals = dict.fromkeys(['N', 'N#', 'N!', 'N#!', 'N.n2', 'N.n2#',
                                   'a.b[3]', 'a+b?', 'a(b)', '#', '!'])
        candidates = list(originals) + [
            'N.n0', 'N.t123', 'N.n2.n0', 'N.n2#.n0', 'a.b[3].t9',
            'aXb3.t9', 'a+b?.n0', 'a(b).n7', '.n0', 'N.t-1', 'N.nx',
            'N.n1.extra', 'N.n\u0661', 'unknown.n0']
        stems = _node_stems(originals)
        for name in candidates:
            with self.subTest(name=name):
                expected = [n for n in originals if n == name or
                            re.fullmatch(re.escape(n.rstrip('#!')) + r'\.[nt][0-9]+', name)]
                self.assertCountEqual(_node_candidates(name, originals, stems), expected)

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
            (ORIGINAL + 'equiv "IN" "VSS"\n', RESISTANCE, 'alias'),
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
            rewired = 'device msubckt known 0 0 1 1 "VSS" "IN.t0" 1 0 "VSS" 1 0 "N.t0" 1 0\n'
            self.inputs(root, original=original, resistance=RESISTANCE + rewired)
            normalize(root, 'top')
            exported = '.subckt top IN VSS\nR0 N.n0 N.t0 10\nR1 IN IN.t0 20\nX0 N.n0 ghost VSS VSS known w=1 l=1\n.ends\n'
            (root / 'extracted.spice').write_text(exported)
            with self.assertRaisesRegex(ValueError, 'unmapped endpoint'):
                finalize(root, 'top')
            self.assertFalse((root / 'raw-export.spice').exists())

    def test_explicit_aliases_keep_the_port_name_and_rewrite_split_nodes(self):
        original = ORIGINAL.replace('node "IN"', 'node "label"') + 'equiv "label" "IN"\n'
        resistance = RESISTANCE.replace('"IN', '"label')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.inputs(root, original, resistance)
            report = normalize(root, 'top')
            self.assertEqual(report['aliases'], {'label': 'IN'})
            self.assertEqual(report['nets']['IN']['nodes'], ['IN', 'IN.t0'])
            self.assertIn('node "IN"', (root / 'top.ext').read_text())
            self.assertNotIn('equiv', (root / 'top.ext').read_text())
            self.assertEqual((root / 'top.raw.ext').read_text(), original)
            (root / 'extracted.spice').write_text('.subckt top IN VSS\nR0 N.n0 N.t0 10\nR1 IN IN.t0 20\n.ends\n')
            report = finalize(root, 'top')
            self.assertEqual(report['export']['status'], 'passed')

    def test_hierarchical_names_have_independent_resistance_groups(self):
        original = ORIGINAL.replace('N#', 'stage[0]/N#')
        resistance = RESISTANCE.replace('N#', 'stage[0]/N#').replace('"N.', '"stage[0]/N.')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.inputs(root, original, resistance)
            report = normalize(root, 'top')
            self.assertEqual(report['nets']['stage[0]/N#']['nodes'], ['stage[0]/N.n0', 'stage[0]/N.t0'])
            self.assertEqual(report['conservation']['maximum_error_af'], 0)

    def test_aliases_cannot_merge_independent_records_or_short_ports(self):
        for addition in ('equiv "IN" "N#"\n', 'equiv "IN" "VSS"\n',
                         'equiv "unknown" "other"\n'):
            with self.subTest(addition=addition), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.inputs(root, ORIGINAL + addition)
                with self.assertRaisesRegex(ValueError, 'alias'):
                    normalize(root, 'top')
                self.assertFalse((root / 'top.raw.ext').exists())

    def test_extresist_cannot_reconnect_device_to_another_original_net(self):
        original = ORIGINAL + 'device msubckt known 0 0 1 1 l=1 w=1 "VSS" "IN" 1 0 "VSS" 1 0 "N#" 1 0\n'
        rewired = 'device msubckt known 0 0 1 1 "VSS" "IN.t0" 1 0 "VSS" 1 0 "IN" 1 0\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.inputs(root, original, RESISTANCE + rewired)
            with self.assertRaisesRegex(ValueError, 'changed a device terminal net'):
                normalize(root, 'top')
            self.assertFalse((root / 'top.raw.ext').exists())

    def test_model_backed_resistor_preserves_its_substrate_and_terminal_order(self):
        original = ORIGINAL + 'device rsubckt poly 0 0 1 1 l=10 w=1 "VSS" "IN" 0 0 "IN" 1 0 "N#" 1 0\n'
        rewired = 'device rsubckt poly 0 0 1 1 "VSS" "IN" 0 0 "IN.t0" 1 0 "N.t0" 1 0\n'
        base = '.subckt top IN VSS\nR0 N.n0 N.t0 10\nR1 IN IN.t0 20\n'
        for valid in (True, False):
            with self.subTest(valid=valid), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.inputs(root, original, RESISTANCE + rewired)
                normalize(root, 'top')
                device = 'X0 IN.t0 N.t0 VSS poly r_length=10u r_width=1u\n'
                if not valid: device = device.replace('N.t0 VSS', 'VSS N.t0')
                (root / 'extracted.spice').write_text(base + device + '.ends\n')
                if valid:
                    report = finalize(root, 'top')
                    self.assertEqual(report['export']['device_terminals'], {'status': 'passed', 'count': 1})
                    self.assertIn(device, (root / 'extracted.spice').read_text())
                else:
                    with self.assertRaisesRegex(ValueError, 'electrical terminal'):
                        finalize(root, 'top')
                    self.assertFalse((root / 'raw-export.spice').exists())

    def test_resistance_values_and_units_are_checked_per_parallel_edge(self):
        resistance = RESISTANCE.replace('scale 1000', 'scale 2000') + 'resist "IN" "IN.t0" 5\n'
        for values, valid in ((('40', '10'), True), (('39', '11'), False), (('40k', '10'), False)):
            with self.subTest(values=values), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.inputs(root, resistance=resistance); normalize(root, 'top')
                exported = '.subckt top IN VSS\nR0 N.n0 N.t0 20\nR1 IN IN.t0 '+values[0]+'\nR2 IN.t0 IN '+values[1]+'\n.ends\n'
                (root / 'extracted.spice').write_text(exported)
                if valid:
                    self.assertEqual(finalize(root, 'top')['export']['resistor_values']['count'], 3)
                else:
                    with self.assertRaisesRegex(ValueError, 'resistance value'):
                        finalize(root, 'top')
                    self.assertEqual((root / 'extracted.spice').read_text(), exported)

    def test_retained_real_engine_coupon_replays_with_terminal_and_value_checks(self):
        source = Path(__file__).resolve().parents[1] / 'docs/validation/dev25/process-rc-final-evidence/metal1-rc-coupon/100/extraction'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'rc_coupon.ext').write_bytes((source / 'rc_coupon.raw.ext').read_bytes())
            (root / 'rc_coupon.res.ext').write_bytes((source / 'rc_coupon.raw.res.ext').read_bytes())
            (root / 'extracted.spice').write_bytes((source / 'raw-export.spice').read_bytes())
            normalize(root, 'rc_coupon'); report = finalize(root, 'rc_coupon')
            self.assertEqual(report['export']['device_terminals']['count'], 1)
            self.assertEqual(report['export']['resistor_values']['count'], 4)
            self.assertLess(report['export']['maximum_error_af'], 1e-9)

    def test_physical_primitive_rc_devices_survive_parasitic_reconstruction(self):
        cases = [('devres', 'poly', '10 2', 'poly w=2u l=10u', 3),
                 ('devres', 'None', '1234', '1234', 3),
                 ('devcap', 'mim', '10 2', 'mim w=2u l=10u', 2),
                 ('devcap', 'None', '3.25', '3.25f', 2)]
        for kind, model, header, suffix, count in cases:
            with self.subTest(kind=kind, model=model), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                terms = '"IN" 0 0 ' if count == 3 else ''
                original = ORIGINAL + f'device {kind} {model} 0 0 1 1 {header} '+terms+'"IN" 1 0 "N#" 1 0\n'
                # Supported Magic ResPrint omission: no required value or L/W.
                rewired = f'device {kind} {model} 0 0 1 1 "None" '+terms+'"IN.t0" 1 0 "N.t0" 1 0\n'
                self.inputs(root, original, RESISTANCE + rewired)
                report = normalize(root, 'top')
                info = report['primitive_devices'][0]
                self.assertTrue(info['restored_resistance_header'])
                line = info['name']+' IN.t0 N.t0 '+suffix+'\n'
                exported = '.subckt top IN VSS\nR0 N.n0 N.t0 10\nR1 IN IN.t0 20\n'+line+'C0 IN VSS 0\n.ends\n'
                (root / 'extracted.spice').write_text(exported)
                result = finalize(root, 'top')
                self.assertEqual(result['export']['preserved_physical_passives'], [info['name'].lower()])
                self.assertIn(line, (root / 'extracted.spice').read_text())
                self.assertNotIn('C0 IN VSS', (root / 'extracted.spice').read_text())
                self.assertEqual((root / 'top.raw.ext').read_text(), original)
                self.assertEqual((root / 'top.raw.res.ext').read_text(), RESISTANCE + rewired)

    def test_known_engine_milliohm_bias_is_removed_without_hiding_other_errors(self):
        resistance = RESISTANCE.replace('"N.t0" 10', '"N.t0" 0.00142486')
        for value, valid in (('0.00192486', True), ('0.00142486', True), ('0.00292486', False)):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.inputs(root, resistance=resistance); normalize(root, 'top')
                (root / 'extracted.spice').write_text('.subckt top IN VSS\nR0 N.n0 N.t0 '+value+'\nR1 IN IN.t0 20\n.ends\n')
                if valid:
                    result = finalize(root, 'top')
                    line = next(l for l in (root / 'extracted.spice').read_text().splitlines() if l.startswith('R0 '))
                    self.assertEqual(float(line.split()[3]), .00142486)
                    self.assertEqual(result['export']['resistor_values']['recognized_export_bias_ohm'], .0005)
                else:
                    with self.assertRaisesRegex(ValueError, 'resistance value'):
                        finalize(root, 'top')

    def test_pre_resistance_parameters_detect_dimension_changes_and_restore_junctions(self):
        original = ORIGINAL + 'parameters other a1=w\nparameters known a1=as p1=ps\ndevice msubckt known 0 0 1 1 l=1 w=1 "VSS" "IN" 1 0 "VSS" 1 0 "N#" 1 0\n'
        rewired = 'device msubckt known 0 0 1 1 "VSS" "IN.t0" 1 0 "VSS" 1 0 "N.t0" 1 0\n'
        reference = '.subckt top IN VSS\nXref N# IN VSS VSS known w=1 l=1 ad=1 as=2 pd=3 ps=4\n.ends\n'
        for width, area, valid in ((1, 2, True), (1, 0, True), (2, 2, False)):
            with self.subTest(width=width, area=area), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); self.inputs(root, original, RESISTANCE + rewired)
                (root / 'device-reference.spice').write_text(reference)
                normalize(root, 'top', require_device_reference=True)
                export = '.subckt top IN VSS\nR0 N.n0 N.t0 10\nR1 IN IN.t0 20\n'+f'X0 N.t0 IN.t0 VSS VSS known w={width} l=1 ad=1 as={area} pd=3 ps=4\n.ends\n'
                (root / 'extracted.spice').write_text(export)
                if valid:
                    result = finalize(root, 'top')
                    self.assertEqual(result['export']['device_parameters']['status'], 'passed')
                    self.assertEqual(result['export']['device_parameters']['restored_junction_fields'], int(area == 0))
                    self.assertIn('as=2 ', (root / 'extracted.spice').read_text())
                else:
                    with self.assertRaisesRegex(ValueError, 'physical device parameters'):
                        finalize(root, 'top')
                    self.assertFalse((root / 'raw-export.spice').exists())


if __name__ == '__main__':
    unittest.main()
