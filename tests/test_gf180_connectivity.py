"""Written-GDS controls for complete placed-cell supply coverage."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import klayout.db as k

from icstudio import gf180_connectivity as check
from icstudio.model import file_digest


class GF180ConnectivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.master = check.PREFIX + 'test_1'
        lib = k.Layout(); lib.dbu = .001
        cell = lib.create_cell(self.master)
        for box in ((0, 0, 10000, 1000), (0, 9000, 10000, 10000)):
            cell.shapes(lib.layer(34, 0)).insert(k.Box(*box))
        cell.shapes(lib.layer(33, 0)).insert(k.Box(1900, 300, 2100, 700))
        for name, y in (('VDD', 500), ('VSS', 9500)):
            cell.shapes(lib.layer(34, 10)).insert(k.Text(name, k.Trans(5000, y)))
        path = self.root/'library.gds'; lib.write(str(path))
        self.library = {self.master: dict(path=path, sha256=file_digest(path))}
        self.layout = k.Layout(); self.layout.read(str(path))
        self.top = self.layout.create_cell('design')
        self.top.insert(k.CellInstArray(self.layout.cell(self.master).cell_index(), k.Trans(20000, 20000)))
        self.box(36, 0, (24800, 9800, 25200, 20800))
        self.box(36, 0, (24800, 29200, 25200, 40200))
        self.box(35, 0, (24800, 20300, 25200, 20700))
        self.box(35, 0, (24800, 29300, 25200, 29700))
        for name, layer, x, y in (('VDD', 36, 25000, 10000), ('VSS', 36, 25000, 40000),
                                  ('A', 42, 5000, 20000), ('B', 42, 5000, 30000)):
            self.box(layer, 0, (x-200, y-200, x+200, y+200))
            self.top.shapes(self.layout.layer(layer, 10)).insert(k.Text(name, k.Trans(x, y)))
        self.database = dict(version=1, dbu_per_micron=2000, instances=[dict(
            name='u0', master=self.master, orientation='R0', bbox=[40000, 40000, 60000, 60000],
            pins=[dict(name=n, net=n, direction='INOUT') for n in ('VDD', 'VSS')])])
        self.preview = dict(pins=[dict(name=n, layer=l, point=p) for n,l,p in
            [('VDD', 'Metal2', [25, 15]), ('VSS', 'Metal2', [25, 35]),
             ('A', 'Metal3', [5, 20]), ('B', 'Metal3', [5, 30])]])
        self.gds = self.root/'reference.gds'
        self.db = self.root/'database.json'
        self.view = self.root/'preview.json'
        self.save_sources()

    def box(self, layer, datatype, bounds):
        self.top.shapes(self.layout.layer(layer, datatype)).insert(k.Box(*bounds))

    def save_sources(self):
        self.layout.write(str(self.gds))
        self.db.write_text(json.dumps(self.database))
        self.view.write_text(json.dumps(self.preview))

    def capture(self, variant='C'):
        return check.capture(self.gds, self.db, self.view, self.library, top_name='design', variant=variant)

    def candidate(self, terminals):
        path = self.root/'candidate.gds'; self.layout.write(str(path))
        return check.inspect(path, terminals)

    def test_all_supplies_and_distinct_ports_connected_on_both_stacks(self):
        for variant in ('C', 'D'):
            report = self.candidate(self.capture(variant))
            self.assertTrue(report['passed'])
            self.assertFalse(report['qualified'])
            self.assertEqual((report['placed_cells'], report['power_terminals'], report['port_anchors']), (1,2,4))
            self.assertEqual(report['failure_counts'], {})
            self.assertEqual(len(set(report['port_nets'].values())), 4)

    def test_supply_open_and_missing_via_are_detected(self):
        terminals = self.capture()
        self.top.shapes(self.layout.layer(35, 0)).clear()
        report = self.candidate(terminals)
        self.assertEqual(report['failure_counts'], {'power-terminal-disconnected': 2})
        self.assertEqual({f['pin']['instance'] for f in report['failures']}, {'u0'})

    def test_dummy_metal_is_conductive_and_detects_a_short(self):
        terminals = self.capture()
        self.box(34, 4, (24900, 20500, 25100, 29500))
        report = self.candidate(terminals)
        self.assertEqual(report['failure_counts']['shorted-top-ports'], 1)

    def test_signal_short_is_detected(self):
        terminals = self.capture()
        self.box(42, 0, (4900, 20000, 5100, 30000))
        self.assertEqual(self.candidate(terminals)['failure_counts'], {'shorted-top-ports': 1})

    def test_missing_port_is_not_misreported_as_a_short(self):
        terminals = self.capture()
        self.top.shapes(self.layout.layer(42, 0)).clear()
        report = self.candidate(terminals)
        self.assertEqual(report['failure_counts'], {'missing-port-metal': 1, 'port-anchor-disconnected': 2})

    def test_removed_substrate_contact_requires_separate_native_lvs(self):
        terminals = self.capture()
        self.layout.cell(self.master).shapes(self.layout.layer(33, 0)).clear()
        report = self.candidate(terminals)
        self.assertTrue(report['passed'])
        self.assertFalse(report['qualified'])
        self.assertIn('substrate LVS', report['scope'])

    def test_child_label_cannot_join_disconnected_metal(self):
        terminals = self.capture()
        self.top.shapes(self.layout.layer(35, 0)).clear()
        self.assertFalse(self.candidate(terminals)['passed'])

    def test_candidate_cannot_change_top_port_labels(self):
        terminals = self.capture()
        self.top.shapes(self.layout.layer(42, 10)).clear()
        self.assertEqual(self.candidate(terminals)['failure_counts'], {'changed-top-port-labels': 1})

    def test_source_identity_is_rechecked(self):
        terminals = self.capture()
        self.db.write_text(self.db.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'Captured source changed'):
            self.candidate(terminals)

    def test_library_hash_and_mask_mismatch_are_rejected(self):
        original = self.library[self.master]['sha256']
        self.library[self.master]['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.capture()
        self.library[self.master]['sha256'] = original
        self.layout.cell(self.master).shapes(self.layout.layer(33, 0)).clear()
        self.save_sources()
        with self.assertRaisesRegex(ValueError, 'cell masks differ'):
            self.capture()

    def test_missing_extra_or_moved_placement_is_rejected(self):
        original = copy.deepcopy(self.database)
        for change in ('missing', 'extra', 'moved'):
            self.database = copy.deepcopy(original)
            if change == 'missing': self.database['instances'] = []
            if change == 'extra':
                extra = copy.deepcopy(self.database['instances'][0]); extra['name'] = 'u1'
                self.database['instances'].append(extra)
            if change == 'moved': self.database['instances'][0]['bbox'][0] += 2
            self.save_sources()
            with self.subTest(change=change), self.assertRaises(ValueError): self.capture()

    def test_duplicate_names_and_wrong_supply_assignment_are_rejected(self):
        original = copy.deepcopy(self.database)
        self.database['instances'].append(copy.deepcopy(self.database['instances'][0]))
        self.save_sources()
        with self.assertRaisesRegex(ValueError, 'unique'): self.capture()
        self.database = original
        self.database['instances'][0]['pins'][0]['net'] = 'VSS'
        self.save_sources()
        with self.assertRaisesRegex(ValueError, 'supply assignments'): self.capture()

    def test_fractional_grid_and_unsupported_orientation_are_rejected(self):
        original = copy.deepcopy(self.database)
        for key, value in (('bbox', [40001,40000,60000,60000]), ('orientation','R90')):
            self.database = copy.deepcopy(original)
            self.database['instances'][0][key] = value
            self.save_sources()
            with self.subTest(key=key), self.assertRaises(ValueError): self.capture()

    def test_capture_uses_independent_library_terminals_under_all_row_orientations(self):
        expected = {'R0': [(25000,20500),(25000,29500)],
                    'MX': [(25000,29500),(25000,20500)],
                    'MY': [(25000,20500),(25000,29500)],
                    'R180': [(25000,29500),(25000,20500)]}
        for orient, tr in [('R0', k.Trans(0,False,20000,20000)), ('MX', k.Trans(0,True,20000,30000)),
                           ('MY', k.Trans(2,True,30000,20000)), ('R180', k.Trans(2,False,30000,30000))]:
            list(self.top.each_inst())[0].trans = tr
            self.database['instances'][0]['orientation'] = orient
            self.save_sources()
            with self.subTest(orient=orient):
                points = self.capture().power
                self.assertEqual([(p.x,p.y) for p in points], expected[orient])

    def test_omitted_terminal_coverage_is_rejected(self):
        terminals = self.capture()
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            self.candidate(replace(terminals, power=terminals.power[:1]))

    def test_wrong_port_set_anchor_and_stream_mapping_are_rejected(self):
        original = copy.deepcopy(self.preview)
        for key, value in (('name','unknown'), ('point',[5.0001,20]), ('point',[6,20]),
                           ('gds_layer',[46,0]), ('layer','Metal6')):
            self.preview = copy.deepcopy(original)
            self.preview['pins'][2][key] = value
            self.save_sources()
            with self.subTest(key=key,value=value), self.assertRaises(ValueError): self.capture()

    def test_unsupported_stack_and_extra_top_rejected(self):
        with self.assertRaisesRegex(ValueError, 'C/D'): self.capture('B')
        extra = self.layout.create_cell('other')
        extra.shapes(self.layout.layer(34,0)).insert(k.Box(0,0,100,100))
        self.save_sources()
        with self.assertRaisesRegex(ValueError, 'exactly'): self.capture()

    def test_uncaptured_device_hierarchy_is_rejected(self):
        extra = self.layout.create_cell('hidden')
        extra.shapes(self.layout.layer(22,0)).insert(k.Box(0,0,100,100))
        self.top.insert(k.CellInstArray(extra.cell_index(), k.Trans()))
        self.save_sources()
        with self.assertRaisesRegex(ValueError, 'Uncaptured'): self.capture()

    def test_metal_via_stream_hierarchy_is_allowed(self):
        extra = self.layout.create_cell('stream_via')
        extra.shapes(self.layout.layer(35,0)).insert(k.Box(100,100,200,200))
        self.top.insert(k.CellInstArray(extra.cell_index(), k.Trans()))
        self.save_sources()
        self.assertTrue(self.candidate(self.capture())['passed'])

    def command_args(self):
        result = self.root/'result.json'
        result.write_text(json.dumps(dict(digital_result=dict(stage='finish', artifacts={
            'database': dict(sha256=file_digest(self.db)), 'layout_preview': dict(sha256=file_digest(self.view))}))))
        lock = self.root/'source-lock.json'
        lock.write_text(json.dumps(dict(revision='fixture-only', views={self.master: {'.gds': 'library.gds'}},
            files={'library.gds': dict(sha256=self.library[self.master]['sha256'])})))
        return dict(gds=self.gds, reference_gds=self.gds, database=self.db, preview=self.view,
                    result=result, library_root=self.root, library_lock=lock,
                    top='design', variant='C', output=self.root/'report.json')

    def test_command_binds_job_and_library_and_preserves_reports(self):
        from scripts.check_gf180_connectivity import run
        args = self.command_args()
        report = run(**args)
        self.assertTrue(report['passed'])
        self.assertFalse(report['qualified'])
        self.assertEqual(report['input_bindings']['database']['sha256'], file_digest(self.db))
        before = args['output'].read_bytes()
        with self.assertRaisesRegex(ValueError, 'existing evidence'): run(**args)
        self.assertEqual(args['output'].read_bytes(), before)

    def test_command_rejects_stale_job_and_changed_library(self):
        from scripts.check_gf180_connectivity import run
        args = self.command_args()
        self.db.write_text(self.db.read_text()+'\n')
        with self.assertRaisesRegex(ValueError, 'saved job'): run(**args)
        args = self.command_args()
        self.library[self.master]['path'].write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'): run(**args)
        self.assertFalse(args['output'].exists())

    def test_command_rejects_escaping_library_path(self):
        from scripts.check_gf180_connectivity import run
        args = self.command_args()
        lock = json.loads(args['library_lock'].read_text())
        lock['views'][self.master]['.gds'] = '../library.gds'
        args['library_lock'].write_text(json.dumps(lock))
        with self.assertRaisesRegex(ValueError, 'Invalid library'): run(**args)


if __name__ == '__main__':
    unittest.main()
