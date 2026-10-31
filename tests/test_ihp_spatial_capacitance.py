import copy
from pathlib import Path
import tempfile
import unittest

from scripts.ihp_spatial_capacitance import audit_ground_delta, audit_trace


class IHPSpatialCapacitanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ext = self.root/'circuit.ext'; self.trace = self.root/'trace.tsv'
        self.ext.write_text('scale 1000 1 0.5\n'
                            'substrate "NET000001" 0 0 0 0 pwell\n'
                            'node "NET000002" 0 1000 0 0 metal1\n'
                            'node "NET000003" 0 1000 5 0 metal1\n'
                            'cap "NET000002" "NET000003" 12.3457\n')
        self.rows = [self.row('overlap', 'NET000002', 'NET000003', '12.3456789'),
                     self.row('overlap', 'NET000002', 'NET000001', '3'),
                     self.row('ground-overlap', 'NET000002', '@substrate', '-2')]
        self.write()

    @staticmethod
    def row(kind, a, b, value):
        return '\t'.join(['ICSTUDIO_SPATIAL', kind, a, b, value, '10', '11',
                          '0', '0', '10', '10', '5', '0', '15', '10'])+'\n'

    def write(self):
        self.trace.write_text(''.join(self.rows))

    def test_native_rounding_and_substrate_relocation_are_accounted(self):
        result = audit_trace(self.trace, self.ext)
        self.assertEqual(result['signal_mutual_pairs'], 1)
        self.assertEqual(result['relocated_to_substrate_af'], {'NET000002': 3.})
        self.assertEqual(result['ground_shielding_af'], {'NET000002': -2.})
        self.assertFalse(result['qualified'])

    def test_endpoint_order_does_not_create_a_false_change(self):
        self.rows[0] = self.row('overlap', 'NET000003', 'NET000002', '12.3456789'); self.write()
        self.assertEqual(audit_trace(self.trace, self.ext)['status'], 'trace-mutual-conserved')

    def test_missing_duplicated_and_changed_contributions_fail(self):
        for rows in (self.rows[1:], self.rows+[self.rows[0]],
                     [self.rows[0].replace('12.3456789', '12.3466789')]+self.rows[1:]):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, 'conserve'):
                self.trace.write_text(''.join(rows)); audit_trace(self.trace, self.ext)

    def test_unknown_nodes_invalid_values_and_interleaved_logs_fail(self):
        for line in (self.rows[0].replace('NET000003', 'unknown'),
                     self.rows[0].replace('12.3456789', 'nan'),
                     self.rows[0].replace('12.3456789', 'inf'),
                     self.rows[0].replace('overlap', 'invented'),
                     self.rows[0].rstrip()+' native warning\n', 'ordinary log\n'):
            with self.subTest(line=line), self.assertRaises(ValueError):
                self.trace.write_text(line+''.join(self.rows[1:])); audit_trace(self.trace, self.ext)

    def test_inverted_rectangles_and_wrong_ground_polarity_fail(self):
        fields = self.rows[0].strip().split('\t'); fields[7] = '20'
        for rows in (['\t'.join(fields)+'\n']+self.rows[1:],
                     self.rows[:2]+[self.rows[2].replace('-2', '2')],
                     self.rows[:2]+[self.rows[2].replace('@substrate', 'NET000001')]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.trace.write_text(''.join(rows)); audit_trace(self.trace, self.ext)

    def test_signed_corrections_remain_in_the_sum(self):
        self.rows[0] = self.row('overlap', 'NET000002', 'NET000003', '13.3456789')
        self.rows.append(self.row('corner', 'NET000002', 'NET000003', '-1')); self.write()
        self.assertEqual(audit_trace(self.trace, self.ext)['signal_mutual_pairs'], 1)

    def test_ground_delta_detects_missing_shielding_or_relocated_capacitance(self):
        before = audit_trace(self.trace, self.ext); after = copy.deepcopy(before)
        after['signal_ground_af']['NET000002'] -= .2
        with self.assertRaisesRegex(ValueError, 'ground-C'):
            audit_ground_delta(before, after)
        after['ground_shielding_af']['NET000002'] -= .2
        result = audit_ground_delta(before, after)
        self.assertEqual(result['status'], 'trace-ground-delta-accounted')
        self.assertFalse(result['qualified'])
        after['relocated_to_substrate_af']['NET000002'] += .2
        with self.assertRaisesRegex(ValueError, 'ground-C'):
            audit_ground_delta(before, after)

    def test_ground_delta_allows_only_printed_uncertainty(self):
        before = audit_trace(self.trace, self.ext); after = copy.deepcopy(before)
        after['ground_shielding_af']['NET000002'] -= .009
        self.assertEqual(audit_ground_delta(before, after)['status'], 'trace-ground-delta-accounted')
        after['ground_shielding_af']['NET000002'] -= .002
        with self.assertRaisesRegex(ValueError, 'ground-C'):
            audit_ground_delta(before, after)

    def test_native_graph_corruption_and_empty_traces_fail(self):
        self.trace.write_text('')
        with self.assertRaisesRegex(ValueError, 'Empty'):
            audit_trace(self.trace, self.ext)
        self.write(); self.ext.write_text(self.ext.read_text()+'cap "NET000002" "NET000003" 1\n')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            audit_trace(self.trace, self.ext)

    def test_shielding_subtraction_residue_is_retained_and_bounded(self):
        self.rows.append(self.row('ground-side-halo', 'NET000002', '@substrate', '5e-11')); self.write()
        result = audit_trace(self.trace, self.ext)
        self.assertEqual(result['positive_shielding_residue_count'], 1)
        self.assertEqual(result['positive_shielding_residue_total_af'], 5e-11)
        self.assertGreater(result['ground_shielding_af']['NET000002'], -2.)
        self.rows.extend([self.rows[-1]]*2000); self.write()
        with self.assertRaisesRegex(ValueError, 'residues exceed'):
            audit_trace(self.trace, self.ext)
