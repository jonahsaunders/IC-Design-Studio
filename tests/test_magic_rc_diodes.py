"""Native diode polarity and geometry must survive the complete RC path."""
from pathlib import Path
import shlex
import tempfile
import unittest

from icstudio.magic_rc import _device, _spice_devices, normalize, finalize, contract
from icstudio.rc_islands import prune
from tests.test_magic_rc import ORIGINAL, RESISTANCE

N = 'device ndiode diode_n 0 0 1 1 a=8136 p=370 "VSS" "IN" 138 0 "N#" 0 0\n'
P = 'device pdiode diode_p 2 0 3 1 a=8136 p=370 "VSS" "IN" 138 0 "N#" 0 0\n'
NR = 'device ndiode diode_n 0 0 1 1 "VSS" "IN.t0" 472 0 "N.t0" -177 0\n'
PR = 'device pdiode diode_p 2 0 3 1 "VSS" "IN.t0" 472 0 "N.t0" -177 0\n'
REFERENCE = '.subckt top IN VSS\nDn N# IN diode_n area=0.2034p pj=1.85u m=2\nDp IN N# diode_p area=0.2034p pj=1.85u\n.ends\n'
EXPORTED = '.subckt top IN VSS\nR0 N.n0 N.t0 10\nR1 IN IN.t0 20\nDn N.t0 IN.t0 diode_n area=0.2034p pj=1.85u m=2\nDp IN.t0 N.t0 diode_p area=0.2034p pj=1.85u\n.ends\n'


class NativeDiodeRCTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def inputs(self, original=ORIGINAL + N + P, resistance=RESISTANCE + NR + PR, reference=REFERENCE):
        (self.root / 'top.ext').write_text(original, encoding='utf-8', newline='\n')
        (self.root / 'top.res.ext').write_text(resistance, encoding='utf-8', newline='\n')
        if reference is not None:
            (self.root / 'device-reference.spice').write_text(reference, encoding='utf-8', newline='\n')

    def test_polarity_uses_native_terminal_order_and_not_extra_bulk(self):
        self.assertEqual(_device(shlex.split(N))['electrical'], ['N#', 'IN'])
        self.assertEqual(_device(shlex.split(P))['electrical'], ['IN', 'N#'])
        self.assertEqual(_device(shlex.split(P.replace('pdiode', 'diode')))['electrical'], ['IN', 'N#'])
        for source in (N, P):
            self.assertEqual(_device(shlex.split(source))['prefix'], 'd')

    def test_single_terminal_uses_substrate_without_changing_polarity(self):
        for kind, expected in (('ndiode', ['VSS', 'IN']), ('pdiode', ['IN', 'VSS']), ('diode', ['IN', 'VSS'])):
            source = f'device {kind} model 0 0 1 1 a=8136 p=370 "VSS" "IN" 138 0'
            self.assertEqual(_device(shlex.split(source))['electrical'], expected)
            with self.assertRaisesRegex(ValueError, 'two electrical terminals'):
                _device(shlex.split(source.replace('"VSS"', '"None"')))

    def test_normalize_export_contract_and_islands_preserve_native_diodes(self):
        self.inputs()
        normalized = normalize(self.root, 'top', require_device_reference=True)
        self.assertEqual([d['prefix'] for d in normalized['devices']], ['d', 'd'])
        (self.root / 'extracted.spice').write_text(EXPORTED, encoding='utf-8', newline='\n')
        result = finalize(self.root, 'top')
        self.assertEqual(result['export']['device_parameters']['devices'], 2)
        self.assertEqual(result['export']['device_parameters']['restored_junction_fields'], 0)
        final = (self.root / 'extracted.spice').read_text()
        self.assertIn('Dn N.t0 IN.t0 diode_n area=0.2034p pj=1.85u m=2\n', final)
        self.assertIn('Dp IN.t0 N.t0 diode_p area=0.2034p pj=1.85u\n', final)
        self.assertEqual(_spice_devices(contract(final, result)), _spice_devices(REFERENCE))
        islands = prune(self.root / 'extracted.spice', self.root / 'electrical.spice', normalization=result)
        self.assertFalse(islands['removed_resistors'])
        self.assertEqual((self.root / 'electrical.spice').read_text(), final)

    def test_aliases_preserve_ordered_diode_connections(self):
        original = (ORIGINAL + 'equiv "N#" "alias"\n' + N + P).replace('"N#" 0 0', '"alias" 0 0')
        self.inputs(original=original)
        report = normalize(self.root, 'top', require_device_reference=True)
        self.assertEqual(report['aliases'], {'alias': 'N#'})
        (self.root / 'extracted.spice').write_text(EXPORTED)
        self.assertEqual(finalize(self.root, 'top')['export']['device_parameters']['devices'], 2)

    def test_diodes_require_parameter_reference_before_mutating_inputs(self):
        self.inputs(reference=None)
        before = (self.root / 'top.ext').read_bytes()
        with self.assertRaisesRegex(ValueError, 'pre-resistance device reference'):
            normalize(self.root, 'top')
        self.assertEqual((self.root / 'top.ext').read_bytes(), before)
        self.assertFalse((self.root / 'top.raw.ext').exists())

    def test_geometry_multiplicity_polarity_model_and_missing_device_faults_fail(self):
        faults = [EXPORTED.replace('area=0.2034p', 'area=0.3034p', 1),
                  EXPORTED.replace('pj=1.85u', 'pj=2.85u', 1),
                  EXPORTED.replace('m=2', 'm=3'),
                  EXPORTED.replace('Dn N.t0 IN.t0', 'Dn IN.t0 N.t0'),
                  EXPORTED.replace('diode_n area', 'other_model area'),
                  EXPORTED.replace('Dp IN.t0 N.t0 diode_p area=0.2034p pj=1.85u\n', ''),
                  EXPORTED.replace('Dp IN.t0 N.t0', 'Dp ghost N.t0')]
        for index, fault in enumerate(faults):
            with self.subTest(index=index):
                folder = self.root / str(index); folder.mkdir()
                original_root = self.root
                self.root = folder
                self.inputs()
                normalize(folder, 'top', require_device_reference=True)
                (folder / 'extracted.spice').write_text(fault)
                with self.assertRaises(ValueError): finalize(folder, 'top')
                self.assertEqual((folder / 'extracted.spice').read_text(), fault)
                self.assertFalse((folder / 'raw-export.spice').exists())
                self.root = original_root

    def test_diode_dimensions_never_use_mos_junction_restoration(self):
        original = ORIGINAL + 'parameters diode_n a1=area p1=pj\n' + N + P
        self.inputs(original=original)
        normalize(self.root, 'top', require_device_reference=True)
        fault = EXPORTED.replace('area=0.2034p pj=1.85u m=2', 'area=0.1p pj=1u m=2')
        (self.root / 'extracted.spice').write_text(fault)
        with self.assertRaisesRegex(ValueError, 'physical device parameters'):
            finalize(self.root, 'top')
        self.assertEqual((self.root / 'extracted.spice').read_text(), fault)

    def test_rewired_diode_must_remain_on_original_nets(self):
        self.inputs(resistance=RESISTANCE + NR.replace('"N.t0" -177', '"VSS" -177') + PR)
        with self.assertRaisesRegex(ValueError, 'changed a device terminal net'):
            normalize(self.root, 'top', require_device_reference=True)
        self.assertFalse((self.root / 'top.raw.ext').exists())

    def test_diode_contact_keeps_an_otherwise_unobserved_resistor_component(self):
        source = '.subckt top IN VSS\nRkeep internal remote 10\nDonly remote body model area=1p pj=4u\nRdrop unused1 unused2 5\n.ends\n'
        path = self.root / 'source.spice'; path.write_text(source)
        result = prune(path, self.root / 'pruned.spice')
        self.assertEqual(result['removed_resistors'], ['rdrop'])
        self.assertIn('Rkeep internal remote 10\nDonly remote body model area=1p pj=4u', (self.root / 'pruned.spice').read_text())

    def test_malformed_native_diode_cards_are_rejected(self):
        for source in ('D1 a model', 'D1 a b c model', 'D1 a b model 2',
                       'D1 a b model area=1p area=2p', 'D1 a b model area=1p bad'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                _spice_devices(source)

    def test_incomplete_extraction_device_is_rejected_before_mutation(self):
        self.inputs(original=ORIGINAL + 'device\n')
        before = (self.root / 'top.ext').read_bytes()
        with self.assertRaisesRegex(ValueError, 'device class'):
            normalize(self.root, 'top')
        self.assertEqual((self.root / 'top.ext').read_bytes(), before)
        self.assertFalse((self.root / 'top.raw.ext').exists())

    def test_native_continuations_preserve_ports_terminals_parameters_and_resistors(self):
        self.inputs(reference=REFERENCE.replace(' IN VSS\n', ' IN\n+ VSS\n')
                    .replace(' area=', '\n+ area='))
        normalize(self.root, 'top', require_device_reference=True)
        source = (EXPORTED.replace(' IN VSS\n', ' IN\n+ VSS\n')
                  .replace('N.n0 N.t0 10', 'N.n0\n+ N.t0 10.0005')
                  .replace('Dn N.t0 IN.t0', 'Dn N.t0\n+ IN.t0')
                  .replace(' area=', '\n+ area='))
        (self.root / 'extracted.spice').write_text(source, newline='\n')
        report = finalize(self.root, 'top')
        result = (self.root / 'extracted.spice').read_bytes().decode()
        self.assertIn('.subckt top IN\n+ VSS\n', result)
        self.assertIn('R0 N.n0\n+ N.t0 10\n', result)
        self.assertIn('Dn N.t0\n+ IN.t0 diode_n\n+ area=0.2034p pj=1.85u m=2\n', result)
        collapsed = contract(result, report)
        self.assertIn('Dn N#\n+ IN diode_n\n+ area=0.2034p pj=1.85u m=2\n', collapsed)
        self.assertEqual(_spice_devices(collapsed), _spice_devices(REFERENCE))
        retained = prune(self.root / 'extracted.spice', self.root / 'electrical.spice', normalization=report)
        self.assertFalse(retained['removed_resistors'])
        self.assertEqual((self.root / 'electrical.spice').read_bytes().decode(), result)

    def test_wrapped_interface_fault_and_orphaned_continuation_are_rejected(self):
        self.inputs()
        normalize(self.root, 'top', require_device_reference=True)
        fault = EXPORTED.replace('.subckt top IN VSS', '.subckt top IN\n+ wrong')
        (self.root / 'extracted.spice').write_text(fault, newline='\n')
        with self.assertRaisesRegex(ValueError, 'port interface'):
            finalize(self.root, 'top')
        self.assertEqual((self.root / 'extracted.spice').read_text(), fault)
        with self.assertRaisesRegex(ValueError, 'Orphaned'):
            _spice_devices('+ area=0.2034p\n')


if __name__ == '__main__':
    unittest.main()
