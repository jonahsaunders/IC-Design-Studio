"""Tiny hierarchical exchange regressions: native edits must remain portable."""
import shutil
import re
import tempfile
import unittest
from pathlib import Path

from icstudio import net_labels, wiring
from icstudio.capture_ops import apply_symbol, transform
from icstudio.electrical_identity import partition
from icstudio.model import History, clone, digest, load_project, save_project
from icstudio.native_exchange import export_project, review_project
from icstudio.native_migration import review_path
from icstudio.native_spice import netlist, render
from icstudio.studies import set_target
from icstudio.xschem_project import apply_review
from tests.test_native_migration import divider


class NativeExchangeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'IC Design Studio café'
        result = review_path(divider(self.root / 'source', hierarchical=True, include=True))
        self.assertEqual(result['status'], 'Complete', result['items'])
        self.history = History(result['candidate'])

    @property
    def project(self):
        return self.history.project

    @property
    def child(self):
        return next(c for c in self.project['cells'] if c['id'] != self.project['top'])

    def assert_electrical_equal(self, before, after):
        # Relocated model filenames are regenerated; compare the referenced
        # contents while requiring the electrical/program text to stay exact.
        def emission(d, cells, project):
            return re.sub(r'models/([a-f0-9]{24})\.spice',
                          lambda m: 'models/' + project['spice']['assets'][m[1]]['sha256'] + '.spice',
                          render(d, cells.get(d.get('cell'))))
        self.assertEqual(sorted(a['text'] for a in before['spice']['assets'].values()),
                         sorted(a['text'] for a in after['spice']['assets'].values()))
        self.assertEqual(before['id'], after['id'])
        self.assertEqual(before['top'], after['top'])
        oldcells = {c['id']: c for c in before['cells']}
        newcells = {c['id']: c for c in after['cells']}
        self.assertEqual(set(oldcells), set(newcells))
        for cid, old in oldcells.items():
            new = newcells[cid]
            self.assertEqual(old['ports'], new['ports'])
            self.assertEqual(old.get('spice_parameters', {}), new.get('spice_parameters', {}))
            self.assertEqual(partition(old), partition(new))
            olddevices = {d['id']: d for d in old['devices']}
            newdevices = {d['id']: d for d in new['devices']}
            self.assertEqual(set(olddevices), set(newdevices))
            for did, d in olddevices.items():
                actual = newdevices[did]
                for field in ('name', 'x', 'y', 'rotation', 'mirror', 'nets', 'terminal_ids', 'net_ids'):
                    self.assertEqual(d.get(field), actual.get(field), (d['name'], field))
                self.assertEqual(d['symbol']['pin_order'], actual['symbol']['pin_order'])
                self.assertEqual(d['native_spice'].get('parameters'), actual['native_spice'].get('parameters'))
                self.assertEqual(emission(d, oldcells, before), emission(actual, newcells, after))

    def roundtrip(self, project, index=0):
        before = digest(project)
        out = export_project(project, self.root / ('exchange ' + str(index)))
        self.assertEqual(digest(project), before, 'Export mutated the live project')
        path = Path(out['directory']) / out['top']
        record = review_project(path)
        self.assertEqual(record['errors'], [])
        candidate = apply_review(record)
        self.assert_electrical_equal(project, candidate)
        return candidate, path

    def test_port_export_avoids_moved_device_terminal(self):
        cid, did = self.child['id'], self.child['devices'][0]['id']
        self.history.commit(lambda p: transform(p, cid, [did], dx=-120, dy=-30),
                            'Move child resistor')
        # The n terminal now occupies the old generated p-port coordinate.
        self.assertIn([-120, 0], wiring.pins(self.child, self.project).values())
        self.roundtrip(self.project)

    def test_port_export_avoids_wire_interior(self):
        cid = self.child['id']
        def edit(p):
            c = next(c for c in p['cells'] if c['id'] == cid)
            wiring.add_wire(c, [[0, 30], [-200, 30], [-200, 0], [-80, 0]], p)
        self.history.commit(edit, 'Route child return')
        self.roundtrip(self.project)

    def test_port_export_avoids_detached_label(self):
        cid = self.child['id']
        def edit(p):
            c = next(c for c in p['cells'] if c['id'] == cid)
            net_labels.add(c, 'n', {'kind': 'point', 'point': [-120, 0]}, p)
        self.history.commit(edit, 'Place child return label')
        self.roundtrip(self.project)

    def test_unused_port_is_isolated_and_labels_do_not_accumulate(self):
        cid = self.child['id']
        base = clone(self.child['symbol'])
        symbol = clone(base)
        symbol['pins']['unused'] = [40, 0]
        symbol['pin_order'].append('unused')
        def edit(p):
            apply_symbol(p, cid, symbol, base)
            c = next(c for c in p['cells'] if c['id'] == cid)
            # An occupied fallback column too: clearance must use wire bounds.
            wiring.add_wire(c, [[0, 30], [-300, 30], [-300, 80], [-80, 80]], p)
        self.history.commit(edit, 'Add unused interface terminal')
        project = self.project
        for index in range(3):
            project, _ = self.roundtrip(project, index)
            child = next(c for c in project['cells'] if c['id'] == cid)
            labels = child['labels']
            self.assertEqual(len(labels), 3)
            unused = next(l for l in labels if l['name'] == 'unused')
            self.assertEqual(unused['anchor']['kind'], 'point')
            point = net_labels.point(unused, child, project)
            self.assertNotIn(point, wiring.pins(child, project).values())
            self.assertFalse(any(wiring.on_segment(point, a, b) for w in child['wires']
                                 for a, b in zip(w['points'], w['points'][1:])))

    def test_top_ports_keep_declared_order(self):
        # The top cell has no parent symbol from which the importer can recover
        # ordering. Its port records must not follow the order of net labels.
        self.history.commit(lambda p: p['cells'][0].update(ports=['spare', 'out']), 'Declare top ports')
        self.roundtrip(self.project)

    def test_repeated_native_edits_undo_and_hierarchical_roundtrips(self):
        original = clone(self.project['cells'])
        top = next(c for c in self.project['cells'] if c['id'] == self.project['top'])
        xid = next(d['id'] for d in top['devices'] if d['name'] == 'X1')
        # Closely spaced routes must stay compact through repeated connected moves.
        for dy in (-10, -10, -10, 10, 10, 10) * 3:
            before = clone(self.project['cells'])
            self.history.commit(lambda p: transform(p, p['top'], [xid], dy=dy), 'Move instance')
            moved = clone(self.project['cells'])
            self.assertLessEqual(max(len(w['points']) for w in moved[0]['wires']), 4)
            self.assertEqual(partition(original[0]), partition(moved[0]))
            self.history.undo()
            self.assertEqual(self.project['cells'], before)
            self.history.redo()
            self.assertEqual(self.project['cells'], moved)
        self.assertEqual(self.project['cells'], original)

        cid, did = self.child['id'], self.child['devices'][0]['id']
        base = clone(self.child['symbol'])
        symbol = clone(base)
        symbol['pins']['input'] = symbol['pins'].pop('p')
        symbol['pin_meta']['input'] = symbol['pin_meta'].pop('p')
        symbol['pin_order'] = ['input', 'n']
        self.history.commit(lambda p: apply_symbol(p, cid, symbol, base), 'Rename child port')
        self.history.commit(lambda p: transform(p, cid, [did], dx=-120, dy=-30), 'Move child resistor')
        self.history.commit(lambda p: set_target(p, p['top'], 'X1.native.r', '3k'), 'Set instance resistance')

        shutil.rmtree(self.root / 'source')
        project = self.project
        for index in range(3):
            with self.subTest(cycle=index):
                project, _ = self.roundtrip(project, index)
                save_project(project, self.root / 'saved native.icproj')
                project = load_project(self.root / 'saved native.icproj')
                self.assert_electrical_equal(self.project, project)
                self.assertEqual(len(next(c for c in project['cells'] if c['id'] == cid)['labels']), 2)
                text = netlist(project, self.root / ('native run ' + str(index)))
                self.assertIn('.subckt child input n r=1k', text)
                self.assertIn('child r=3000.0', text)
                self.assertIn('R1 input n {r} m=1', text)
                self.assertIn('models/', text)

    def test_external_parameter_edit_and_stale_child_review(self):
        _, top = self.roundtrip(self.project)
        child = top.parent / 'child.sch'
        text = child.read_text(encoding='utf-8')
        self.assertIn('value="\\{r\\}"', text)
        child.write_text(text.replace('value="\\{r\\}"', 'value="\\{r*2\\}"'), encoding='utf-8')
        record = review_project(top)
        self.assertEqual(record['errors'], [])
        candidate = apply_review(record)
        device = next(c for c in candidate['cells'] if c['id'] == self.child['id'])['devices'][0]
        self.assertEqual(device['id'], self.child['devices'][0]['id'])
        self.assertEqual(device['native_spice']['parameters']['value'], '{r*2}')
        child.write_text(child.read_text(encoding='utf-8') + '\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed after review'):
            apply_review(record)

    def test_invalid_connected_move_keeps_history_and_geometry(self):
        xid = next(d['id'] for d in self.project['cells'][0]['devices'] if d['name'] == 'X1')
        before = digest(self.project)
        with self.assertRaisesRegex(ValueError, 'connections|conflicting labels'):
            self.history.commit(lambda p: transform(p, p['top'], [xid], dx=-100, dy=60))
        self.assertEqual(digest(self.project), before)
        self.assertEqual(self.history.undo_stack, [])
        self.assertEqual(self.history.redo_stack, [])


if __name__ == '__main__':
    unittest.main()
