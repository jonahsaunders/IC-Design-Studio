"""Applicability controls use written hierarchy, exact layers and rule limits."""
from pathlib import Path
import tempfile
import unittest

import klayout.db as k
from scripts import check_gf180_fill as fill
from scripts import gf180_fill_applicability as applicability


class ApplicabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.layout = k.Layout(); self.layout.dbu = .001
        self.top = self.layout.create_cell('top'); self.child = self.layout.create_cell('child')
        self.top.insert(k.CellInstArray(self.child.cell_index(), k.Trans(10000, 20000)))

    def add(self, layer, datatype, box):
        self.child.shapes(self.layout.layer(layer, datatype)).insert(k.Box(*box))

    def inspect(self):
        path = Path(self.temp.name)/'fixture.gds'; self.layout.write(str(path))
        read = k.Layout(); read.read(str(path)); top = read.top_cell()
        markers = {name: fill.region(read, top, *pair) for name, pair in fill.MARKERS.items()}
        dummy = {name: fill.region(read, top, number, 4) for name, number in fill.LAYERS.items()}
        memory = {name: fill.region(read, top, *pair) for name, pair in fill.UNSUPPORTED_MEMORY.items()}
        channel = fill.region(read, top, 22, 0) & fill.region(read, top, 30, 0)
        return {r['rule']: r for r in applicability.inspect(markers, dummy, memory, channel)['rules']}

    def channel(self):
        self.add(22, 0, (150000, 0, 155000, 5000)); self.add(30, 0, (151000, 0, 152000, 5000))

    def test_absence_is_explicit_not_a_general_qualification(self):
        self.channel()
        self.assertTrue(all(r['status'] == 'not_applicable_absent_operand' for r in self.inspect().values()))

    def test_rows_require_both_dimensions_strictly_over_80um(self):
        self.channel()
        for name, layer, rule in (('RES_MK', 110, 'DCF.8b'), ('NDMY', 111, 'DCF.11b'),
                                  ('IND_MK', 151, 'DCF.13-row')):
            for width, height, required in ((80000, 90000, False), (90000, 80000, False),
                                           (80005, 80005, True), (79995, 90000, False)):
                with self.subTest(marker=name, width=width, height=height):
                    index = self.layout.layer(layer, 5); self.layout.clear_layer(index)
                    self.add(layer, 5, (0, 0, width, height))
                    row = self.inspect()[rule]
                    self.assertEqual(row['status'] == 'requires_exclusion_edge_row_check', required)
                    self.assertEqual(row['polygons'], 1)
            self.layout.clear_layer(self.layout.layer(layer, 5))

    def test_merged_markers_cannot_evade_threshold(self):
        self.channel()
        self.add(110, 5, (0, 0, 50000, 100000)); self.add(110, 5, (40000, 0, 100000, 100000))
        self.assertEqual(self.inspect()['DCF.8b']['status'], 'requires_exclusion_edge_row_check')

    def test_nonrectangular_marker_is_not_waived_from_its_box(self):
        self.channel()
        self.add(111, 5, (0, 0, 100000, 1000)); self.add(111, 5, (0, 0, 1000, 100000))
        self.assertEqual(self.inspect()['DCF.11b']['status'], 'unqualified_nonrectangular_marker')

    def test_channel_absence_is_separate_and_no_arbitrary_metal_is_a_channel(self):
        self.add(110, 5, (0, 0, 90000, 90000)); self.add(34, 0, (0, 0, 5000, 5000))
        self.assertEqual(self.inspect()['DCF.8b']['status'], 'not_applicable_no_channel_intersection')
        self.channel()
        self.assertEqual(self.inspect()['DCF.8b']['status'], 'requires_exclusion_edge_row_check')

    def test_nested_exact_operands_activate_memory_boundary_pad_and_de1(self):
        for layer in (11, 86): self.add(layer, 0, (0, 0, 5000, 5000))
        self.assertEqual(self.inspect()['vendor-memory-fill']['status'], 'not_applicable_absent_operand')
        self.add(86, 17, (0, 0, 5000, 5000)); self.add(22, 4, (10000, 0, 15000, 5000))
        self.add(30, 4, (9700, -300, 15300, 5300)); self.add(37, 0, (20000, 0, 30000, 10000))
        self.add(152, 5, (0, 10000, 5000, 15000))
        rows = self.inspect()
        self.assertEqual(rows['vendor-memory-fill']['status'], 'unsupported_operand_present')
        self.assertEqual(rows['DCF.7a/7b/7c/7d']['status'], 'requires_declared_boundary_check')
        self.assertEqual(rows['DPF.1-prime-die/7']['status'], 'requires_declared_boundary_check')
        self.assertEqual(rows['DCF.9']['status'], 'requires_rf_guideline_review')
        self.assertEqual(rows['DE.1']['status'], 'requires_design_justification')


if __name__ == '__main__': unittest.main()
