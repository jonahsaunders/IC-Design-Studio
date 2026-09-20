"""Regressions for stable-ID, revision-checked, all-or-nothing design scripting."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from icstudio import wiring
from icstudio.design_automation import (commit_batch, dispatch, envelope, inspect,
    install_preview, preview, resolve_path)
from icstudio.electrical_identity import partition, synchronize
from icstudio.model import (History, clone, design_digest, device, digest,
    example, flatten, load_project, save_project, uid, validate)
from icstudio.sdk import apply_commands


def hierarchy():
    p = example('empty')
    top = p['cells'][0]
    child = {'id': uid(), 'name': 'resistor_cell', 'ports': ['p', 'n'],
             'parameters': {'resistance': '1k'},
             'devices': [device('R', 'R1', value='{resistance}', nets={'p': 'p', 'n': 'n'})], 'shapes': []}
    alternative = clone(child)
    alternative.update(id=uid(), name='resistor_precision')
    alternative['devices'][0]['id'] = uid()
    alternative['parameters']['resistance'] = '2k'
    p['cells'] += [child, alternative]
    top['devices'] = [device('X', 'X1', cell=child['id'], nets={'p': 'in', 'n': '0'}),
                      device('X', 'X2', cell=child['id'], nets={'p': 'out', 'n': '0'})]
    validate(p)
    return p


def change_value(p, value='22k'):
    c = p['cells'][0]
    return {'type': 'set_parameter', 'cell_id': c['id'], 'device_id': c['devices'][1]['id'],
            'name': 'value', 'value': value}


class AutomationTests(unittest.TestCase):
    def test_failed_late_command_preserves_project_undo_redo_and_last_event(self):
        history = History(example())
        commit_batch(history, envelope(history.project, [change_value(history.project)]))
        history.undo()
        before = clone(history.__dict__)
        request = envelope(history.project, [change_value(history.project),
            {'type': 'rename_device', 'cell_id': history.project['top'], 'device_id': 'missing', 'name': 'Rbad'}])
        with self.assertRaisesRegex(ValueError, 'Command 2.*Unknown device'):
            commit_batch(history, request)
        self.assertEqual(history.__dict__, before)

    def test_preview_install_single_undo_and_no_aliases(self):
        history = History(example())
        before = clone(history.project)
        request = envelope(before, [change_value(before)])
        proposal = preview(before, request)
        self.assertEqual(history.project, before)
        self.assertEqual(len(history.undo_stack), 0)
        history.commit(lambda p: install_preview(p, proposal), 'Reviewed batch')
        self.assertEqual(history.project['cells'][0]['devices'][1]['value'], '22k')
        self.assertEqual(len(history.undo_stack), 1)
        self.assertEqual(history.project['id'], before['id'])
        self.assertTrue(proposal['report']['results_stale'])
        proposal['project']['cells'][0]['devices'][1]['value'] = '99k'
        self.assertEqual(history.project['cells'][0]['devices'][1]['value'], '22k')
        history.undo()
        self.assertEqual(history.project['cells'], before['cells'])
        history.redo()
        self.assertEqual(history.project['cells'][0]['devices'][1]['value'], '22k')

    def test_stale_revision_hash_wrong_project_and_modified_preview_rejected(self):
        history = History(example())
        batch = envelope(history.project, [change_value(history.project)])
        proposal = preview(history.project, batch)
        commit_batch(history, batch)
        with self.assertRaisesRegex(ValueError, 'revision changed'):
            commit_batch(history, batch)
        with self.assertRaisesRegex(ValueError, 'revision changed'):
            history.commit(lambda p: install_preview(p, proposal))
        batch = envelope(history.project, [change_value(history.project)])
        history.project['name'] = 'external same-revision edit'
        with self.assertRaisesRegex(ValueError, 'content changed'):
            commit_batch(history, batch)
        batch = envelope(history.project, [change_value(history.project)])
        batch['project_id'] = 'another-project'
        with self.assertRaisesRegex(ValueError, 'different project'):
            commit_batch(history, batch)
        fresh = envelope(history.project, [change_value(history.project)])
        proposal = preview(history.project, fresh)
        proposal['project']['name'] = 'tampered'
        with self.assertRaisesRegex(ValueError, 'preview content changed'):
            history.commit(lambda p: install_preview(p, proposal))

    def test_invalid_final_design_rolls_back_and_unknown_fields_are_rejected(self):
        history = History(example())
        before = digest(history.project)
        for command in [change_value(history.project, '0'), {**change_value(history.project), 'typo': True}]:
            with self.assertRaises(ValueError):
                commit_batch(history, envelope(history.project, [command]))
            self.assertEqual(digest(history.project), before)
            self.assertFalse(history.undo_stack)

    def test_shared_master_inspection_and_interface_checked_view_switch(self):
        p = hierarchy()
        top, child, alternative = p['cells']
        instance = top['devices'][0]
        info = inspect(p, [instance['id']])
        self.assertEqual(info['cell_id'], child['id'])
        self.assertEqual(len(next(c for c in info['cells'] if c['id'] == child['id'])['parents']), 2)
        history = History(p)
        command = {'type': 'switch_cell_view', 'cell_id': top['id'], 'device_id': instance['id'], 'view_cell_id': alternative['id']}
        commit_batch(history, envelope(history.project, [command]))
        self.assertEqual(history.project['cells'][0]['devices'][0]['id'], instance['id'])
        self.assertEqual([d['value'] for d in flatten(history.project)], ['2000.0', '1000.0'])
        self.assertEqual(resolve_path(history.project, [instance['id']])[0]['id'], alternative['id'])
        history.undo()
        self.assertEqual([d['value'] for d in flatten(history.project)], ['1000.0', '1000.0'])
        history.project['cells'][2]['ports'] = ['n', 'p']
        with self.assertRaisesRegex(ValueError, 'ordered ports'):
            commit_batch(history, envelope(history.project, [command]))

    def test_view_switch_rejects_recursion_and_linked_layout(self):
        history = History(hierarchy())
        top, child, alternate = history.project['cells']
        command = {'type': 'switch_cell_view', 'cell_id': top['id'], 'device_id': top['devices'][0]['id'], 'view_cell_id': alternate['id']}
        top['layout_instances'] = [{'id': uid(), 'name': 'physical', 'cell': child['id'],
                                    'device_id': top['devices'][0]['id'], 'x': 0, 'y': 0}]
        with self.assertRaisesRegex(ValueError, 'linked physical placement'):
            commit_batch(history, envelope(history.project, [command]))
        history = History(hierarchy())
        top, child, _ = history.project['cells']
        # The same-interface alternative points back to the cell being edited.
        recursive = device('X', 'recurse', cell=child['id'], nets={'p': 'p', 'n': 'n'})
        with self.assertRaisesRegex(ValueError, 'Recursive'):
            commit_batch(history, envelope(history.project, [{'type': 'add_device', 'cell_id': child['id'], 'device': recursive}]))

    def test_shape_batch_cannot_short_a_saved_matched_route(self):
        from icstudio.layout import rect
        from icstudio.layout_routing import matched_pair, install
        p = example('empty')
        endpoint = lambda x, y: {'layer': 'metal1', 'point': [x, y]}
        install(p, matched_pair(p, p['top'], [endpoint(0, 0), endpoint(0, 5000)],
            [endpoint(10000, 0), endpoint(10000, 5000)], ['a', 'b'], 400, layers=['metal1']))
        history = History(p)
        before = digest(history.project)
        command = {'type': 'add_shape', 'cell_id': p['top'], 'shape': rect('metal1', 2000, -200, 400, 5400)}
        with self.assertRaisesRegex(ValueError, 'Saved layout constraint'):
            commit_batch(history, envelope(history.project, [command]))
        self.assertEqual(digest(history.project), before)
        self.assertFalse(history.undo_stack)

    def test_wired_move_and_rename_preserve_electrical_identities_and_labels(self):
        p = example('empty')
        c = p['cells'][0]
        c.update(wires=[], junctions=[])
        c['devices'] = [device('R', 'R1', 100, 150, net_labels={}), device('C', 'C1', 400, 150, net_labels={})]
        wiring.rebuild(c, p)
        wiring.add_wire(c, [[100, 100], [100, 40], [400, 40], [400, 100]], p)
        wiring.set_label(c, c['devices'][0]['id'], 'p', 'signal', p)
        synchronize(c)
        history = History(p)
        before = clone(history.project['cells'][0])
        device_id = before['devices'][0]['id']
        commands = [{'type': 'move_device', 'cell_id': c['id'], 'device_id': device_id, 'x': 140, 'rotation': 90},
                    {'type': 'rename_device', 'cell_id': c['id'], 'device_id': device_id, 'name': 'Rrenamed'}]
        commit_batch(history, envelope(history.project, commands))
        after = history.project['cells'][0]
        self.assertEqual(partition(before), partition(after))
        self.assertEqual(before['devices'][0]['terminal_ids'], after['devices'][0]['terminal_ids'])
        self.assertEqual(before['devices'][0]['net_ids'], after['devices'][0]['net_ids'])
        self.assertEqual(after['devices'][0]['nets']['p'], 'signal')
        self.assertEqual(after['wires'][0]['points'][0], [190, 150])
        history.undo()
        self.assertEqual(history.project['cells'][0], before)

    def test_connection_command_relabels_geometric_conductor_and_undo_restores(self):
        p = example()
        wiring.migrate(p['cells'][0], p)
        history = History(p)
        before = clone(history.project['cells'][0])
        resistor = before['devices'][1]
        batch = envelope(history.project, [{'type': 'connect_pin', 'cell_id': p['top'],
            'device_id': resistor['id'], 'pin': 'n', 'net': 'result'}])
        commit_batch(history, batch)
        resistor, capacitor = history.project['cells'][0]['devices'][1:]
        self.assertEqual(resistor['nets']['n'], 'result')
        self.assertEqual(capacitor['nets']['p'], 'result')
        history.undo()
        self.assertEqual(history.project['cells'][0], before)

    def test_native_parameter_namespace_updates_the_emitted_definition(self):
        project = load_project(Path(__file__).resolve().parents[1] / 'examples/native-rc.icproj')
        cell = project['cells'][0]
        native = next(d for d in cell['devices'] if d.get('native_spice', {}).get('parameters'))
        name = next(iter(native['native_spice']['parameters']))
        history = History(project)
        command = {'type': 'set_parameter', 'cell_id': cell['id'], 'device_id': native['id'],
                   'name': name, 'namespace': 'native', 'value': '123'}
        commit_batch(history, envelope(history.project, [command]))
        updated = next(d for d in history.project['cells'][0]['devices'] if d['id'] == native['id'])
        self.assertEqual(updated['native_spice']['parameters'][name], '123')
        from icstudio.native_spice import render
        self.assertIn('123', render(updated))

    def test_cli_preview_never_writes_project_and_apply_matches_rpc(self):
        from icstudio.cli import main
        p = example()
        batch = envelope(p, [change_value(p)])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, request, output = root / 'design.icproj', root / 'batch.json', root / 'output.icproj'
            save_project(p, path)
            request.write_text(json.dumps(batch))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['automation', 'apply', str(path), '--batch', str(request), '--output', str(output), '--preview']), 0)
                self.assertFalse(output.exists())
                self.assertEqual(main(['automation', 'apply', str(path), '--batch', str(request), '--output', str(output)]), 0)
            result = dispatch('automation.apply', {'project': p, 'batch': batch})
            self.assertEqual(load_project(output)['cells'], result['project']['cells'])
            self.assertEqual(load_project(path)['revision'], 0)

    def test_legacy_sdk_commands_remain_atomic_and_detach_inputs(self):
        p = example()
        before = digest(p)
        commands = [change_value(p)]
        result = apply_commands(p, commands)
        self.assertEqual(digest(p), before)
        self.assertEqual(result['cells'][0]['devices'][1]['value'], '22k')
        commands[0]['value'] = '7k'
        self.assertEqual(result['cells'][0]['devices'][1]['value'], '22k')


if __name__ == '__main__':
    unittest.main()
