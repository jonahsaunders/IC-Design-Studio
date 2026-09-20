"""Placement checklist semantics and linear shape traversal at desktop scale."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from icstudio.layout import rect
from icstudio.model import device, digest, example, uid
from icstudio.parametric import install, placement_inventory


class PlacementInventoryTests(unittest.TestCase):
    def test_primitive_and_linked_instance_states_preserve_missing_terminals(self):
        p = example('empty'); c = p['cells'][0]
        placed, partial, absent = [device('R', 'R' + str(i), nets={'p': 'a', 'n': '0'}) for i in range(1, 4)]
        c['devices'] = [placed, partial, absent, device('V', 'V1')]
        install(p, c['id'], placed['id'], {'x': 0, 'y': 0})
        install(p, c['id'], partial['id'], {'x': 20000, 'y': 0})
        c['layout_pins'] = [pin for pin in c['layout_pins']
                            if (pin['device_id'], pin['pin']) != (partial['id'], 'n')]
        child = {'id': uid(), 'name': 'leaf', 'ports': ['A', 'B'], 'devices': [],
                 'shapes': [rect('metal1', 0, 0, 1000, 1000)],
                 'layout_ports': [{'name': name, 'point': point, 'layer': 'metal1'}
                                  for name, point in [('A', [0, 0]), ('B', [1000, 0])]]}
        p['cells'].append(child)
        instance = device('X', 'X1', cell=child['id'], nets={'A': 'a', 'B': '0'})
        c['devices'].append(instance)
        c['layout_instances'] = [{'id': uid(), 'name': 'X1', 'cell': child['id'],
                                  'device_id': instance['id'], 'x': 40000, 'y': 0}]
        original = digest(p)
        rows = placement_inventory(p, c['id'])
        self.assertEqual([(r['name'], r['state'], r['missing']) for r in rows], [
            ('R1', 'Placed', []), ('R2', 'Terminals missing', ['n']),
            ('R3', 'Unplaced', ['n', 'p']), ('X1', 'Placed', [])])
        self.assertEqual(digest(p), original)
        # Deleting geometry is visible on the next refresh; no persistent cache.
        c['shapes'] = [s for s in c['shapes'] if s.get('device_id') != placed['id']]
        self.assertEqual(placement_inventory(p, c['id'])[0]['state'], 'Unplaced')

    def test_native_sources_and_programs_are_excluded_with_one_source_scan(self):
        from icstudio.native_analysis import sources
        from icstudio.native_migration import review_path
        from tests.test_native_migration import divider
        with tempfile.TemporaryDirectory() as directory:
            p = review_path(divider(Path(directory) / 'source'))['candidate']
        with patch('icstudio.native_analysis.sources', wraps=sources) as source_scan:
            rows = placement_inventory(p, p['top'])
        self.assertEqual({r['name'] for r in rows}, {'R1', 'R2'})
        self.assertTrue(all(r['state'] == 'Unplaced' for r in rows))
        self.assertEqual(source_scan.call_count, 1)

    def test_500_device_inventory_visits_10000_shapes_once(self):
        class CountedShapes(list):
            visits = 0
            def __iter__(self):
                for shape in super().__iter__():
                    self.visits += 1
                    yield shape
        p = example('empty'); c = p['cells'][0]
        c['devices'] = [device('R', 'R' + str(i)) for i in range(500)]
        c['shapes'] = CountedShapes(rect('metal1', i * 1000, 0, 400, 400) for i in range(10000))
        rows = placement_inventory(p, c['id'])
        self.assertEqual(len(rows), 500)
        self.assertTrue(all(r['state'] == 'Unplaced' for r in rows))
        self.assertEqual(c['shapes'].visits, 10000)


if __name__ == '__main__': unittest.main()
