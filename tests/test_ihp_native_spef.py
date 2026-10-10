import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from icstudio.digital_fill_spef import parse
from scripts.ihp_native_spef import transfer
from scripts.ihp_fill_spef import export
from tests.test_digital_gf180_fill import SPEF


class NativeSpefTests(unittest.TestCase):
    EXT = ('scale 1000 1 0.5\nnode "A" 0 100 0 0 m1\n'
           'node "F" 0 200 1 0 m2\nsubstrate "SUB" 0 0 0 1 space\n'
           'cap "A" "F" 300\n')
    WEIGHTS = {'A': {'out': .25, 'out:1': .75},
               'F': {'ICSTUDIO_FLOAT_0000:1': .4, 'ICSTUDIO_FLOAT_0000:2': .6}}

    def inputs(self, folder, ext=None):
        source = Path(folder)/'source.spef'; native = Path(folder)/'native.ext'
        source.write_text(SPEF); native.write_text(self.EXT if ext is None else ext)
        return native, source, Path(folder)/'out.spef'

    def test_all_capacitance_is_replaced_and_every_resistor_terminal_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            native, source, target = self.inputs(folder)
            before = parse(source); result = transfer(native, source, target, self.WEIGHTS)
            after = parse(target)
            self.assertFalse(result['qualified'])
            self.assertLess(result['maximum_contracted_capacitance_error_af'], 1e-9)
            for name in before['nets']:
                for key in ('conn', 'res'):
                    self.assertEqual(before['nets'][name][key], after['nets'][name][key])
            self.assertAlmostEqual(float(after['nets']['out']['ground']['out']), 25e-6)
            self.assertEqual(len(after['couplings']), 4)
            expected = {('ICSTUDIO_FLOAT_0000:1', 'out'): 30e-6,
                        ('ICSTUDIO_FLOAT_0000:2', 'out'): 45e-6,
                        ('ICSTUDIO_FLOAT_0000:1', 'out:1'): 90e-6,
                        ('ICSTUDIO_FLOAT_0000:2', 'out:1'): 135e-6}
            for pair, value in expected.items():
                self.assertAlmostEqual(float(after['couplings'][pair]), value)
            self.assertEqual(source.read_text(), SPEF)

    def test_unmapped_internal_cell_node_is_rejected_even_without_capacitance(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.inputs(folder, self.EXT+'node "INTERNAL" 0 0 2 0 m1\n')
            with self.assertRaisesRegex(ValueError, 'nodes and endpoint'):
                transfer(*args, self.WEIGHTS)

    def test_missing_endpoint_is_not_silently_redistributed(self):
        weights = copy.deepcopy(self.WEIGHTS); weights['A'] = {'out': 1.}
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'Every SPEF'):
                transfer(*self.inputs(folder), weights)

    def test_invented_duplicate_or_mixed_net_endpoints_fail(self):
        cases = [dict(A={'missing': 1.}, F=self.WEIGHTS['F']),
                 dict(A=self.WEIGHTS['A'], F=self.WEIGHTS['A']),
                 dict(A={'out': .5, 'ICSTUDIO_FLOAT_0000:1': .5}, F={'out:1': .5, 'ICSTUDIO_FLOAT_0000:2': .5})]
        for weights in cases:
            with self.subTest(weights=weights), tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(ValueError): transfer(*self.inputs(folder), weights)

    def test_bad_weights_fail(self):
        for value in (-1., 0., .2, float('nan'), float('inf'), True):
            weights = copy.deepcopy(self.WEIGHTS); weights['A']['out'] = value
            with self.subTest(value=value), tempfile.TemporaryDirectory() as folder:
                with self.assertRaisesRegex(ValueError, 'normalized'):
                    transfer(*self.inputs(folder), weights)

    def test_hierarchy_scale_and_nonpassive_native_inputs_fail(self):
        for ext in (self.EXT+'use child x 1 0 0 0 1 0\n',
                    self.EXT.replace('scale 1000 1', 'scale 1000 2'),
                    self.EXT.replace('"F" 0 200', '"F" 0 -200')):
            with self.subTest(ext=ext), tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(ValueError): transfer(*self.inputs(folder, ext), self.WEIGHTS)

    def test_corrupted_export_is_rejected_by_independent_contraction(self):
        def corrupt(source, target, data, result):
            changed = copy.deepcopy(result)
            changed['coupling_f'][0]['value_f'] *= .1
            export(source, target, data, changed)
        with tempfile.TemporaryDirectory() as folder, patch('scripts.ihp_native_spef.export', corrupt):
            with self.assertRaisesRegex(ValueError, 'lost native'):
                transfer(*self.inputs(folder), self.WEIGHTS)

    def test_existing_evidence_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.inputs(folder); args[2].write_text('keep')
            with self.assertRaisesRegex(ValueError, 'new native'):
                transfer(*args, self.WEIGHTS)
            self.assertEqual(args[2].read_text(), 'keep')
