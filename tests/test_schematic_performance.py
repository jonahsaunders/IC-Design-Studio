"""Electrical identity and snapshot regressions for ordinary capture edits."""
import random
import unittest
from collections import defaultdict
from unittest.mock import patch

from icstudio import capture_ops, electrical_identity, wiring
from icstudio.model import History, clone, device, digest, example, flatten, validate


def exhaustive_identity(cell):
    """Independent all-pairs reference for the persisted net identity policy."""
    old = clone(cell['electrical']['nets'])
    groups = defaultdict(lambda: {'terminals': [], 'wires': []})
    for d in cell['devices']:
        for pin, name in d['nets'].items():
            groups[name]['terminals'].append(electrical_identity.terminal_id(d, pin))
    for wire in cell['wires']:
        groups[wire['net']]['wires'].append(wire['id'])
    candidates = []
    for name, members in groups.items():
        for prior in old:
            terminals = len(set(members['terminals']).intersection(prior['terminals']))
            wires = len(set(members['wires']).intersection(prior['wires']))
            if terminals or wires:
                candidates.append((-terminals, -wires, prior['name'] != name, prior['id'], name))
    assigned = {}; used = set()
    for _, _, _, ident, name in sorted(candidates):
        if name not in assigned and ident not in used:
            assigned[name] = ident; used.add(ident)
    result = []
    for name, members in sorted(groups.items()):
        if name not in assigned:
            seed = ['net', cell['id'], sorted(members['terminals']), sorted(members['wires'])]
            ident = 'n_' + digest(seed)[:24]
            while ident in used:
                seed.append(ident); ident = 'n_' + digest(seed)[:24]
            assigned[name] = ident; used.add(ident)
        result.append(dict(id=assigned[name], name=name,
                           terminals=sorted(members['terminals']), wires=sorted(members['wires'])))
    return result


class ElectricalIdentityPerformanceTests(unittest.TestCase):
    def test_index_matches_exhaustive_splits_merges_renames_and_wire_only_nets(self):
        rng = random.Random(4731)
        cell = example('empty')['cells'][0]
        cell['devices'] = [device('R', 'R'+str(i), nets={'p': 'n'+str(i), 'n': '0'}) for i in range(70)]
        cell['wires'] = [{'id': 'wire'+str(i), 'net': 'n'+str(i)} for i in range(90)]
        electrical_identity.synchronize(cell)
        for iteration in range(35):
            for d in cell['devices']:
                if rng.random() < .35:
                    d['nets'][rng.choice(('p', 'n'))] = 'n'+str(rng.randrange(110))
            for wire in cell['wires']:
                if rng.random() < .35: wire['net'] = 'n'+str(rng.randrange(110))
            expected = exhaustive_identity(cell)
            electrical_identity.synchronize(cell)
            self.assertEqual(cell['electrical']['nets'], expected, iteration)
            identities = {row['name']: row['id'] for row in expected}
            for d in cell['devices']:
                self.assertEqual(d['net_ids'], {pin: identities[name] for pin, name in d['nets'].items()})
            for wire in cell['wires']:
                self.assertEqual(wire['net_id'], identities[wire['net']])

    def test_terminal_identity_tracks_interface_identity_not_mutable_pin_name(self):
        d = device('R', 'R1')
        d['symbol'] = {'pin_meta': {'p': {'id': 'stable-pin'}}}
        first = electrical_identity.terminal_id(d, 'p')
        d['symbol']['pin_meta']['renamed'] = d['symbol']['pin_meta'].pop('p')
        self.assertEqual(electrical_identity.terminal_id(d, 'renamed'), first)
        d['symbol']['pin_meta']['renamed']['id'] = 'replacement-pin'
        self.assertNotEqual(electrical_identity.terminal_id(d, 'renamed'), first)
        for identity in ([], {}, 0, False, None):
            d['symbol']['pin_meta']['renamed']['id'] = identity
            self.assertEqual(electrical_identity.terminal_id(d, 'renamed'), 't_'+digest([d['id'], identity])[:24])

    def test_stretch_never_copies_physical_geometry_and_preserves_connections(self):
        class LayoutData(list):
            def __deepcopy__(self, memo):
                raise AssertionError('Schematic editing traversed physical geometry')

        project = example('rc'); cell = project['cells'][0]
        wiring.migrate(cell, project)
        electrical_identity.synchronize(cell)
        cell['shapes'] = LayoutData([{'id': 'untouched-layout'}])
        before = electrical_identity.partition(cell)
        geometry = cell['shapes']
        capture_ops.transform(project, cell['id'], [cell['devices'][1]['id']], 20, 0)
        self.assertEqual(electrical_identity.partition(cell), before)
        self.assertIs(cell['shapes'], geometry)
        self.assertEqual(cell['shapes'], [{'id': 'untouched-layout'}])


class SchematicTransactionTests(unittest.TestCase):
    def fixture(self):
        project = example('rc'); cell = project['cells'][0]
        wiring.migrate(cell, project); electrical_identity.synchronize(cell)
        from icstudio.layout import rect
        cell['shapes'] = [rect('metal1', i*1000, 0, 400, 400) for i in range(300)]
        return project, cell

    def test_full_validation_equivalence_sharing_and_exact_undo_redo(self):
        project, cell = self.fixture(); history = History(project)
        for options in ({'dx': 20.0, 'dy': 0.0}, {'mirror': True}, {'dx': 0.0, 'dy': 0.0}):
            before = history.project; prior_digest = digest(before['cells'])
            expected = clone(before)
            capture_ops.transform(expected, cell['id'], [cell['devices'][1]['id']], **options)
            validate(expected)
            self.assertTrue(history.commit_schematic_transform(cell['id'], [cell['devices'][1]['id']], **options))
            self.assertEqual(digest(history.project['cells']), digest(expected['cells']))
            self.assertEqual(digest(before['cells']), prior_digest)
            self.assertIs(history.project['cells'][0]['shapes'], before['cells'][0]['shapes'])
            self.assertIs(history.project['pdk'], before['pdk'])
            self.assertIs(history.project['cells'][0]['devices'][1]['params'], before['cells'][0]['devices'][1]['params'])
            validate(clone(history.project))
            history.undo(); self.assertEqual(digest(history.project['cells']), prior_digest)
            history.redo(); self.assertEqual(digest(history.project['cells']), digest(expected['cells']))

    def test_shared_coordinate_lists_stay_isolated_during_label_transforms(self):
        from icstudio.net_labels import add
        project = example('empty'); cell = project['cells'][0]
        cell.update(devices=[device('R', 'R1', 100, 150), device('C', 'C1', 400, 150)], wires=[])
        wire, _ = wiring.add_wire(cell, [[100, 100], [400, 100]], project)
        label = add(cell, 'input', {'kind': 'wire', 'id': wire, 'point': [250, 100]}, project)
        pin_label = add(cell, 'input', {'kind': 'pin', 'id': cell['devices'][0]['id'], 'pin': 'p'}, project)
        point_label = add(cell, 'separate', {'kind': 'point', 'point': [700, 300]}, project)
        electrical_identity.synchronize(cell)
        for ids in ([label], [pin_label], [point_label], [cell['devices'][0]['id'], pin_label]):
            history = History(clone(project)); original = history.project; unchanged = digest(original)
            expected = clone(original); capture_ops.transform(expected, cell['id'], ids, 20.0, 20.0); validate(expected)
            self.assertTrue(history.commit_schematic_transform(cell['id'], ids, 20.0, 20.0))
            self.assertEqual(digest(original), unchanged)
            self.assertEqual(digest(history.project['cells']), digest(expected['cells']))
            history.undo(); self.assertEqual(digest(history.project['cells']), digest(original['cells']))

    def test_invalid_positions_and_electrical_collision_are_atomic(self):
        project = example('empty'); cell = project['cells'][0]
        cell.update(devices=[device('R', 'R1', 100, 150), device('R', 'R2', 400, 150)], wires=[])
        wiring.rebuild(cell, project); electrical_identity.synchronize(cell)
        history = History(project); ident = cell['devices'][0]['id']
        self.assertTrue(history.commit_schematic_transform(cell['id'], [ident], 20, 0)); history.undo()
        before = digest(history.project); stacks = clone((history.undo_stack, history.redo_stack)); serial = history.serial
        for dx in (float('nan'), float('inf'), 1e308, 1e7, 300):
            with self.assertRaises(ValueError): history.commit_schematic_transform(cell['id'], [ident], dx, 0)
            self.assertEqual(digest(history.project), before)
            self.assertEqual((history.undo_stack, history.redo_stack), stacks)
            self.assertEqual(history.serial, serial)

    def test_transform_does_not_fold_signed_zero_into_unchanged_rows(self):
        project = example('empty'); cell = project['cells'][0]
        cell['devices'] = [device('R', 'R1', x=-0.0, y=100.0)]
        history = History(project); expected = clone(history.project)
        capture_ops.transform(expected, cell['id'], [cell['devices'][0]['id']], dx=0.0)
        validate(expected)
        self.assertTrue(history.commit_schematic_transform(cell['id'], [cell['devices'][0]['id']], dx=0.0))
        self.assertEqual(digest(history.project['cells']), digest(expected['cells']))

    def test_changed_net_names_fall_back_without_publishing(self):
        project = example('empty'); cell = project['cells'][0]
        cell.update(devices=[device('R', 'R1', 100, 150), device('C', 'C1', 400, 150)], wires=[])
        wiring.add_wire(cell, [[100, 100], [400, 100]], project)
        history = History(project); before = digest(history.project)
        self.assertFalse(history.commit_schematic_transform(cell['id'], [cell['devices'][0]['id']], 0, 40, stretch=False))
        self.assertEqual(digest(history.project), before); self.assertFalse(history.undo_stack)
        history.commit(lambda p: capture_ops.transform(p, cell['id'], [cell['devices'][0]['id']], 0, 40, stretch=False))
        changed = history.project['cells'][0]['devices']
        self.assertNotEqual(changed[0]['nets']['p'], changed[1]['nets']['p'])

    def test_new_branch_ids_checked_against_other_views(self):
        project, cell = self.fixture()
        cell.update(devices=[device('R', 'R1', 250, 150), device('C', 'C1', 400, 150)],
                    wires=[{'id': 'branch-main', 'points': [[100, 100], [400, 100]]}], labels=[])
        for d in cell['devices']: d['net_labels'] = {}
        cell.pop('electrical', None); wiring.rebuild(cell, project)
        history = History(project); before = digest(history.project)
        with patch('icstudio.wiring.uid', return_value=cell['shapes'][0]['id']):
            with self.assertRaisesRegex(ValueError, 'duplicate object ID'):
                history.commit_schematic_transform(cell['id'], [cell['devices'][0]['id']], 20, 40)
        self.assertEqual(digest(history.project), before); self.assertFalse(history.undo_stack)

    def test_shared_hierarchy_is_preserved_and_public_flatten_stays_isolated(self):
        project, child = self.fixture(); child['ports'] = ['vin', 'vout']
        parent = {'id': 'parent', 'name': 'parent', 'ports': [], 'shapes': [],
                  'devices': [device('X', 'X1', 100, 100, cell=child['id'], nets={'vin': 'in', 'vout': 'out'})]}
        project['cells'].append(parent); project['top'] = parent['id']
        wiring.migrate(parent, project); history = History(project)
        before = history.project; circuit = [(d['name'], d['nets']) for d in flatten(before)]
        self.assertTrue(history.commit_schematic_transform(child['id'], [child['devices'][1]['id']], 20, 0))
        self.assertIs(history.project['cells'][1], before['cells'][1])
        validate(clone(history.project))
        self.assertEqual([(d['name'], d['nets']) for d in flatten(history.project)], circuit)
        unchanged = digest(history.project); result = flatten(history.project)
        result[0]['nets']['p'] = 'edited-result'
        self.assertEqual(digest(history.project), unchanged)

    def test_validation_reuses_rebuilt_masters_but_public_flatten_rebuilds(self):
        project, cell = self.fixture()
        with patch('icstudio.wiring.rebuild', wraps=wiring.rebuild) as rebuild:
            validate(project)
            self.assertEqual(rebuild.call_count, 1)
            flatten(project)
            self.assertEqual(rebuild.call_count, 2)

    def test_select_drag_matches_full_command_for_attached_and_point_labels(self):
        from icstudio.schematic_ui import SchematicMixin
        from icstudio.net_labels import add

        class Base:
            def __init__(self, project, fast):
                self.history = History(clone(project)); self.cid = project['top']
                if not fast: self.history.commit_schematic_transform = None
            @property
            def project(self): return self.history.project
            @property
            def cell(self): return self.project['cells'][0]
            def commit(self, fn, label='Edit'): self.history.commit(fn, label)
            def guard(self, fn): return fn()
            def flush_inspector(self): return True
            def queue_recovery(self, **options): pass
            def refresh(self): pass

        class Drag(SchematicMixin, Base): pass

        project = example('empty'); cell = project['cells'][0]
        cell.update(devices=[device('R', 'R1', 100, 150), device('C', 'C1', 400, 150)], wires=[])
        for d in cell['devices']: d['net_labels'] = {}
        wire, _ = wiring.add_wire(cell, [[100, 100], [400, 100]], project)
        label = add(cell, 'input', {'kind': 'wire', 'id': wire, 'point': [250, 100]}, project)
        pin_label = add(cell, 'input', {'kind': 'pin', 'id': cell['devices'][0]['id'], 'pin': 'p'}, project)
        point_label = add(cell, 'separate', {'kind': 'point', 'point': [700, 300]}, project)
        for ids in ([wire], [wire, label], [label], [pin_label], [point_label], [cell['devices'][0]['id'], pin_label]):
            baseline = Drag(project, False); accelerated = Drag(project, True)
            baseline.move(ids, 20.0, 20.0, 'schematic'); accelerated.move(ids, 20.0, 20.0, 'schematic')
            from icstudio.history_delta import difference
            self.assertEqual(digest(accelerated.project['cells']), digest(baseline.project['cells']), difference(baseline.project['cells'], accelerated.project['cells']))
        # Legacy source-only cells and wired imports without normalized pin
        # label dictionaries retain the original select-drag transaction.
        for project in (example('rc'), project):
            project['cells'][0]['devices'][0].pop('net_labels', None)
            baseline = Drag(project, False); accelerated = Drag(project, True)
            ids = [project['cells'][0]['devices'][0]['id']]
            baseline.move(ids, 20, 0, 'schematic'); accelerated.move(ids, 20, 0, 'schematic')
            self.assertEqual(digest(accelerated.project['cells']), digest(baseline.project['cells']))


if __name__ == '__main__': unittest.main()
