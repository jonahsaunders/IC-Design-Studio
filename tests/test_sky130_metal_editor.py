"""Native resistor editor, regeneration and real geometric contact boundaries."""
import tempfile
import unittest
from pathlib import Path

from icstudio.catalog import create_device
from icstudio.layout import polygon, rect
from icstudio.layout_eco import regenerate, inventory
from icstudio.model import clone, example, load_project, save_project
from icstudio.physical import connectivity
from icstudio.sky130_devices import install, supported
from icstudio.sky130_metal_resistors import geometry, specification, layers, LAYERS
from tests.test_sky130_devices import technology


def fixture(key, w=2, l=5):
    p = example('empty'); p['pdk'] = technology(); c = p['cells'][0]
    name = 'li' if key == 'l1' else key
    d = create_device(p['pdk'], 'sky130_fd_pr/res_generic_'+name+'.sym', 'R1')
    d['model_params'].update(w=w, l=l, mult=1); d['nets'] = {'m': 'A', 'p': 'B'}
    c['devices'] = [d]
    install(p, c['id'], d['id'])
    return p, c, d


class MetalEditorTests(unittest.TestCase):
    def test_all_five_models_use_normal_placement_and_exact_mask_dimensions(self):
        for key in LAYERS:
            with self.subTest(key=key):
                p, c, d = fixture(key)
                self.assertTrue(supported(p['pdk'], d))
                self.assertFalse(connectivity(p, c['id'])['issues'])
                self.assertEqual(inventory(p, c['id'])['devices'][0]['status'], 'current')
                marker = next(s for s in c['shapes'] if s['generator_role'].endswith(':marker'))
                b = polygon(marker).bbox()
                self.assertEqual((b.width(), b.height()), (2000, 5000))
                self.assertEqual(next(v for v in p['pdk']['layers'] if v['name'] == marker['layer'])['datatype'], 13)

    def test_removed_moved_and_narrowed_markers_expose_a_short(self):
        for key in LAYERS:
            for change in ('remove', 'move', 'narrow'):
                p, c, d = fixture(key)
                marker = next(s for s in c['shapes'] if s['generator_role'].endswith(':marker'))
                if change == 'remove': c['shapes'].remove(marker)
                elif change == 'move': marker['points'] = [[x+20000, y] for x, y in marker['points']]
                else: marker['points'][1][0] -= 5
                with self.subTest(key=key, change=change):
                    self.assertIn('LVS.SHORT', {i['code'] for i in connectivity(p, c['id'])['issues']})

    def test_bypass_is_not_hidden_and_pin_inside_body_is_not_a_terminal(self):
        for key in LAYERS:
            p, c, d = fixture(key); layer = layers(p['pdk'], key)['conductor']
            # The bridge deliberately passes outside the resistive marker.
            c['shapes'] += [rect(layer, -1000, -300, 2100, 100),
                            rect(layer, -1000, -300, 100, 5700),
                            rect(layer, -1000, 5200, 2100, 100)]
            self.assertIn('LVS.SHORT', {i['code'] for i in connectivity(p, c['id'])['issues']})
            p, c, d = fixture(key)
            c['layout_pins'][0]['point'] = [1000, 2500]
            self.assertTrue(connectivity(p, c['id'])['issues'])

    def test_regeneration_reopen_and_stream_export_keep_original_polygons(self):
        from icstudio.interchange import export_layout
        from icstudio.layout_import import read_layout
        from scripts.qualification_geometry import regions
        for key in LAYERS:
            p, c, d = fixture(key)
            oldpins = {v['pin']: v['id'] for v in c['layout_pins']}
            oldshapes = {v['generator_role']: v['id'] for v in c['shapes']}
            d['model_params'].update(w=.505, l=2.005)
            self.assertEqual(inventory(p, c['id'])['devices'][0]['status'], 'changed')
            regenerate(p, c['id'], d['id'])
            self.assertEqual(oldpins, {v['pin']: v['id'] for v in c['layout_pins']})
            self.assertEqual(oldshapes, {v['generator_role']: v['id'] for v in c['shapes']})
            self.assertFalse(connectivity(p, c['id'])['issues'])
            before = clone(c['shapes']); connectivity(p, c['id'])
            self.assertEqual(before, c['shapes'])
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); save_project(p, root/'project.icproj')
                q = load_project(root/'project.icproj')
                self.assertFalse(connectivity(q, q['top'])['issues'])
                export_layout(q, root/'layout.gds')
                imported, _ = read_layout(root/'layout.gds')
                self.assertEqual(set(regions(q)), set(regions(imported)))
                for mask, value in regions(q).items():
                    self.assertTrue((value ^ regions(imported)[mask]).is_empty())

    def test_recipe_bounds_and_binding_reject_before_mutation(self):
        for key in LAYERS:
            p, c, d = fixture(key); original = clone(p)
            for values in ({'w': .495}, {'l': 10.005}, {'w': .501}, {'w': '2u'}, {'mult': 2}, {'mult': .5}):
                changed = clone(d); changed['model_params'].update(values)
                with self.subTest(key=key, values=values), self.assertRaises(ValueError):
                    geometry(p['pdk'], changed)
            self.assertEqual(p, original)
            for w, l in ((.5, .5), (10, 10), (.505, 2.005)):
                changed = clone(d); changed['model_params'].update(w=w, l=l)
                self.assertEqual(specification(p['pdk'], changed)['dimensions_nm'], {'w': round(w*1000), 'l': round(l*1000)})
            for field, value in (('prefix', 'X'), ('pin_order', ['p', 'm']), ('parameter_scale', {'w': 1, 'l': 1})):
                tech = clone(p['pdk']); tech['simulation']['catalog'][d['model_ref']['device']][field] = value
                with self.assertRaises(ValueError): specification(tech, d)

    def test_incremental_graph_tracks_marker_edits_and_restoration(self):
        from icstudio.layout_graph import GeometryGraph
        p, c, d = fixture('m1'); graph = GeometryGraph()
        graph.sync(c['shapes'], p['pdk']); initial = len(set(graph.groups.values()))
        marker = next(s for s in c['shapes'] if s['generator_role'].endswith(':marker'))
        c['shapes'].remove(marker); graph.sync(c['shapes'], p['pdk'])
        self.assertLess(len(set(graph.groups.values())), initial)
        c['shapes'].append(marker); graph.sync(c['shapes'], p['pdk'])
        self.assertEqual(len(set(graph.groups.values())), initial)

    def test_connected_move_preserves_attached_terminal_routes(self):
        from icstudio.layout_topology import move
        for key in LAYERS:
            p, c, d = fixture(key); layer = layers(p['pdk'], key)['conductor']
            c['shapes'].append(dict(id='terminal-route', kind='path', layer=layer,
                points=[[1000, -250], [-2000, -250]], width=200, net='A', device_id=''))
            move(p, c['id'], [s['id'] for s in c['shapes'] if s.get('generated_device')], 5000, 5000)
            self.assertFalse(connectivity(p, c['id'])['issues'])
            moved = p['cells'][0]
            route = next(s for s in moved['shapes'] if s['id'] == 'terminal-route')
            self.assertIn([6000, 4750], route['points'])

    def test_invalid_resistive_mask_cannot_hide_normal_conductors(self):
        from icstudio.contact_rules import conductive_shapes
        p, c, d = fixture('m1'); tech = p['pdk']; ls = layers(tech, 'm1')
        for rule in ({'conductor': ls['conductor'], 'mask': ls['conductor']},
                     {'conductor': 'missing', 'mask': ls['marker']},
                     {'conductor': ls['conductor'], 'mask': 'missing'},
                     {'conductor': ls['conductor'], 'mask': ls['marker'], 'ignore': True}):
            changed = clone(tech); changed['connectivity']['resistive_masks'] = [rule]
            with self.assertRaises(ValueError): conductive_shapes(c['shapes'], changed)

    def test_connected_move_checks_spacing_of_split_terminal_geometry(self):
        from icstudio.layout_topology import move
        from icstudio.layout_transaction import propose
        for operation in (move, propose):
            p, c, d = fixture('m1'); layer = layers(p['pdk'], 'm1')['conductor']
            next(v for v in p['pdk']['layers'] if v['name'] == layer)['space'] = 140
            c['shapes'].append(rect(layer, 7100, 4500, 1000, 300, net='OTHER'))
            before = clone(p)
            with self.assertRaisesRegex(ValueError, 'spacing'):
                operation(p, c['id'], [s['id'] for s in c['shapes'] if s.get('generated_device')], 5000, 5000)
            self.assertEqual(p, before)

    def test_hierarchical_connected_move_keeps_split_terminal_clearance_checks(self):
        from icstudio.layout_topology import move
        from icstudio.model import uid
        p, c, d = fixture('m1'); layer = layers(p['pdk'], 'm1')['conductor']
        next(v for v in p['pdk']['layers'] if v['name'] == layer)['space'] = 140
        child = example('empty')['cells'][0]; child['name'] = 'empty_child'; p['cells'].append(child)
        c['layout_instances'] = [dict(id=uid(), cell=child['id'], name='child', x=20000, y=20000,
            rotation=0, mirror=False, nx=1, ny=1)]
        c['shapes'].append(rect(layer, 7100, 4500, 1000, 300, net='OTHER'))
        before = clone(p)
        with self.assertRaisesRegex(ValueError, 'spacing'):
            move(p, c['id'], [s['id'] for s in c['shapes'] if s.get('generated_device')], 5000, 5000)
        self.assertEqual(p, before)


if __name__ == '__main__':
    unittest.main()
