"""Independent network checks for repeated physical cells and shared interfaces."""
import unittest
from icstudio.model import clone, device, uid, validate, design_digest
from icstudio.physical_extraction import calibrated_network
from icstudio.distributed_rc import apply
from icstudio.rc_hierarchy import flatten_for_rc
from test_physical_extraction import resistive_bench


def series_hierarchy():
    p, leaf_id, bench = resistive_bench()
    leaf = p['cells'][0]
    left = device('X', 'XLEFT', cell=leaf_id, nets={'IN': 'IN', 'OUT': 'middle'})
    right = device('X', 'XRIGHT', cell=leaf_id, nets={'IN': 'middle', 'OUT': 'OUT'})
    root = {'id': uid(), 'name': 'series_pair', 'ports': ['IN', 'OUT'], 'devices': [left, right],
            'shapes': [{'id': uid(), 'kind': 'path', 'layer': 'metal1', 'width': 1000,
                        'points': [[0, 3000], [-10000, 3000], [-10000, 10000], [60000, 10000], [60000, 0]], 'net': 'middle'}],
            'layout_instances': [{'id': uid(), 'name': d['name'], 'cell': leaf_id, 'device_id': d['id'],
                                  'x': x, 'y': 0, 'rotation': 0, 'mirror': False} for d, x in [(left, 0), (right, 40000)]],
            'layout_ports': [{'name': 'IN', 'layer': 'metal1', 'point': [20000, 0]},
                             {'name': 'OUT', 'layer': 'metal1', 'point': [40000, 3000]}]}
    p['cells'].append(root)
    p['cells'][1]['devices'][-1]['cell'] = root['id']
    bench['dut_cell'] = root['id']
    return validate(p), root['id'], leaf_id, bench


class HierarchicalRcTests(unittest.TestCase):
    def test_mim_mask_keeps_distinct_plates_in_the_rc_network(self):
        from test_sky130_devices import passive
        from test_layout_priorities import coupons
        from icstudio.sky130_devices import layers
        from icstudio.rc_calibration import calibrate, install
        p, c, d = passive(); original_device = clone(d)
        metal = layers(p['pdk'])['m4']; c['ports'] = ['P', 'N']
        routes = [('P', [1000, 1000], [1000, 10000]), ('N', [3500, 1000], [10000, 1000])]
        for net, start, end in routes:
            c['shapes'].append({'id': uid(), 'kind': 'path', 'layer': metal, 'net': net,
                                'points': [start, end], 'width': 400})
        c['layout_ports'] = [{'name': net, 'layer': metal, 'point': end} for net, _, end in routes]
        data = coupons(); data['layers'] = {metal: data['layers']['metal1']}
        install(p['pdk'], calibrate(p['pdk'], data))
        network, q = calibrated_network(p, c['id'], {'mode': 'calibrated_rc'})
        mapped = {r['pin']: r['node'] for r in network['terminal_mapping']}
        self.assertNotEqual(mapped['c0'], mapped['c1'])
        updated = next(v for v in q['cells'][0]['devices'] if v['id'] == d['id'])
        self.assertEqual(updated['model_params'], original_device['model_params'])
        self.assertEqual(updated['model_ref'], original_device['model_ref'])
        self.assertEqual(updated['nets'], mapped)
        # Interconnect R must connect each terminal to its own port only.
        links = {}
        for row in network['resistors']:
            links.setdefault(row['p'], set()).add(row['n']); links.setdefault(row['n'], set()).add(row['p'])
        reached, queue = {'P'}, ['P']
        while queue:
            for node in links.get(queue.pop(), set()) - reached: reached.add(node); queue.append(node)
        self.assertIn(mapped['c0'], reached); self.assertNotIn(mapped['c1'], reached); self.assertNotIn('N', reached)
        instance = device('X', 'XCAP', cell=c['id'], nets={'P': 'P', 'N': 'N'})
        wrapper = {'id': uid(), 'name': 'mim_wrapper', 'ports': ['P', 'N'], 'devices': [instance], 'shapes': [],
                   'layout_instances': [{'id': uid(), 'name': 'XCAP', 'device_id': instance['id'],
                                         'cell': c['id'], 'x': 0, 'y': 0}], 'layout_ports': clone(c['layout_ports'])}
        p['cells'].append(wrapper); p['top'] = wrapper['id']
        hierarchical, extracted = calibrated_network(p, wrapper['id'], {'mode': 'calibrated_rc'})
        self.assertEqual(len(hierarchical['hierarchy']['devices']), 1)
        terminal_nodes = {row['node'] for row in hierarchical['terminal_mapping']}
        self.assertEqual(len(terminal_nodes), 2)
        cap = next(v for cell in extracted['cells'] if cell['id'] == wrapper['id'] for v in cell['devices'] if v['kind'] == 'PDK')
        self.assertEqual(cap['model_params'], original_device['model_params'])
        from icstudio.testbenches import native_subcircuit
        self.assertIn('sky130_fd_pr__cap_mim_m3_1', native_subcircuit(extracted, wrapper['id']))

    def test_repeated_master_keeps_paths_and_independent_series_resistance(self):
        from icstudio.simulation import run
        p, cid, leaf_id, bench = series_hierarchy(); original = clone(p)
        network, extracted = calibrated_network(p, cid, bench['physical_extraction'])
        self.assertEqual(network['schema'], 3)
        self.assertEqual(len(network['hierarchy']['occurrences']), 2)
        self.assertEqual(len(network['hierarchy']['devices']), 2)
        self.assertEqual(len({r['device_id'] for r in network['hierarchy']['devices']}), 2)
        self.assertEqual({r['source_device_id'] for r in network['hierarchy']['devices']}, {p['cells'][0]['devices'][0]['id']})
        # Each leaf is 20 squares; parent interconnect is 97 squares. Sheet = 2 ohm/square.
        self.assertAlmostEqual(sum(r['value'] for r in network['resistors']), 2 * (20 + 20 + 97))
        before = run(p, p['top'], p['analysis']); after = run(extracted, extracted['top'], extracted['analysis'])
        self.assertAlmostEqual(before['traces']['output'][0], 100 / 300, places=8)
        self.assertAlmostEqual(after['traces']['output'][0], 100 / (300 + 274), places=8)
        self.assertEqual(p, original)
        self.assertEqual(next(c for c in extracted['cells'] if c['id'] == leaf_id), p['cells'][0])
        again, provenance = flatten_for_rc(p, cid)
        self.assertEqual(provenance, network['hierarchy'])
        self.assertEqual(design_digest(again), provenance['flattened_design_hash'])

    def test_cross_instance_parallel_coupling_is_retained(self):
        p, cid, leaf_id, bench = series_hierarchy()
        root = next(c for c in p['cells'] if c['id'] == cid)
        p['testbenches'] = []; p['cells'].pop(1); p['top'] = cid
        root['ports'] = ['AIN', 'AOUT', 'BIN', 'BOUT']; root['shapes'] = []
        root['layout_ports'] = []
        for d, inst, prefix, y in zip(root['devices'], root['layout_instances'], ['A', 'B'], [0, 1500]):
            d['nets'] = {'IN': prefix + 'IN', 'OUT': prefix + 'OUT'}
            inst.update(x=0, y=y)
            root['layout_ports'] += [{'name': prefix + 'IN', 'layer': 'metal1', 'point': [20000, y]},
                                    {'name': prefix + 'OUT', 'layer': 'metal1', 'point': [0, y + 3000]}]
        validate(p)
        network, _ = calibrated_network(p, cid, bench['physical_extraction'])
        coeff = p['pdk']['parasitic_corners']['nominal']['coefficients']['metal1']['coupling_f_per_um']
        # 20 um parallel length; 1.5 um center spacing minus 1 um width = 0.5 um edge gap.
        self.assertAlmostEqual(sum(c['value'] for c in network['capacitors'] if c['kind'] == 'coupling'), coeff * 20 / .5, delta=1e-28)

    def test_rotation_mirror_and_source_mapping_are_deterministic(self):
        p, cid, _, _ = series_hierarchy()
        root = next(c for c in p['cells'] if c['id'] == cid)
        root['layout_instances'][1].update(rotation=90, mirror=True)
        flat, provenance = flatten_for_rc(p, cid)
        occurrence = provenance['occurrences'][1]
        self.assertEqual(occurrence['rotation'], 90); self.assertTrue(occurrence['mirror'])
        source = p['cells'][0]['shapes'][0]
        item = next(r for r in provenance['shapes'] if r['source_shape_id'] == source['id'] and r['instance_path'] == occurrence['instance_path'])
        actual = next(s for s in next(c for c in flat['cells'] if c['id'] == cid)['shapes'] if s['id'] == item['shape_id'])
        self.assertEqual(actual['kind'], 'path'); self.assertEqual(actual['width'], source['width'])
        self.assertEqual(actual['points'], [[40000, 0], [40000, 20000]])
        self.assertEqual(flatten_for_rc(p, cid), (flat, provenance))

    def test_unreconciled_instances_arrays_and_parameter_overrides_rejected(self):
        p, cid, leaf_id, _ = series_hierarchy()
        for fault in ('missing', 'duplicate', 'unlinked', 'array', 'parameters'):
            q = clone(p); root = next(c for c in q['cells'] if c['id'] == cid)
            if fault == 'missing': root['layout_instances'].pop()
            if fault == 'duplicate': root['layout_instances'].append({**clone(root['layout_instances'][0]), 'id': uid(), 'name': 'duplicate'})
            if fault == 'unlinked': root['layout_instances'][0].pop('device_id')
            if fault == 'array': root['layout_instances'][0]['nx'] = 2
            if fault == 'parameters':
                next(c for c in q['cells'] if c['id'] == leaf_id)['parameters'] = {'resistance': '100'}
                root['devices'][0]['parameters'] = {'resistance': '200'}
            with self.subTest(fault=fault), self.assertRaises(ValueError): flatten_for_rc(q, cid)

    def test_nested_instances_and_tampered_mapping_fail_closed(self):
        p, cid, _, bench = series_hierarchy()
        network, _ = calibrated_network(p, cid, bench['physical_extraction'])
        bad = clone(network); bad['hierarchy']['devices'][0]['source_device_id'] = 'different'
        with self.assertRaisesRegex(ValueError, 'provenance changed'): apply(p, cid, bad)
        moved = clone(p); next(c for c in moved['cells'] if c['id'] == cid)['layout_instances'][0]['x'] += 1000
        with self.assertRaisesRegex(ValueError, 'stale'): apply(moved, cid, network)
        opened = clone(p); next(c for c in opened['cells'] if c['id'] == cid)['shapes'][0]['points'][0] = [0, 5000]
        with self.assertRaisesRegex(ValueError, 'connectivity'): calibrated_network(opened, cid, bench['physical_extraction'])

    def test_two_levels_keep_the_same_saved_bench_and_real_transfer(self):
        import os, tempfile
        from pathlib import Path
        from icstudio.spice_program import find_ngspice
        from icstudio.distributed_rc import compare_job
        executable = find_ngspice(os.environ.get('ICSTUDIO_TEST_NGSPICE', ''))
        if not executable: self.skipTest('Actual ngspice is required for hierarchical saved-bench comparison')
        p, cid, _, bench = series_hierarchy()
        inner = next(c for c in p['cells'] if c['id'] == cid)
        child = device('X', 'XPAIR', cell=cid, nets={'IN': 'IN', 'OUT': 'OUT'})
        outer = {'id': uid(), 'name': 'nested_pair', 'ports': ['IN', 'OUT'], 'devices': [child], 'shapes': [],
                 'layout_instances': [{'id': uid(), 'name': child['name'], 'cell': cid, 'device_id': child['id'], 'x': 0, 'y': 0}],
                 'layout_ports': clone(inner['layout_ports'])}
        p['cells'].append(outer); p['cells'][1]['devices'][-1]['cell'] = outer['id']; bench['dut_cell'] = outer['id']; validate(p)
        job = {'project': p, 'cell': bench['bench_cell'], 'engine': 'ngspice', 'executable': executable,
               'settings': {'type': 'rc_compare', 'testbench': bench['id']}}
        with tempfile.TemporaryDirectory() as tmp:
            result = compare_job(p, job, Path(tmp))
        hierarchy = result['extraction']['hierarchy']
        self.assertEqual(len(hierarchy['occurrences']), 3)
        self.assertTrue(all(len(row['instance_path']) == 2 for row in hierarchy['devices']))
        self.assertAlmostEqual(result['measurement_comparison'][0]['before'], 100 / 300, places=7)
        self.assertAlmostEqual(result['measurement_comparison'][0]['after'], 100 / 574, places=7)


if __name__ == '__main__': unittest.main()
