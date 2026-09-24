import unittest
from unittest.mock import patch

from icstudio.analysis_sources import source_names
from icstudio.model import clone, device, example, flatten, uid


class AnalysisSourcesTests(unittest.TestCase):
    def test_repeated_hierarchy_matches_netlister_order_without_mutation(self):
        p = example('rc')
        child = p['cells'][0]
        child['devices'].append(device('I', 'IBIAS'))
        parent = {'id': uid(), 'name': 'parent', 'ports': [], 'shapes': [],
                  'devices': [device('V', 'VDD')] + [
                      device('X', name, cell=child['id'], nets={})
                      for name in ('XA', 'XB')]}
        p['cells'].append(parent)
        p['top'] = parent['id']
        before = clone(p)
        self.assertEqual(source_names(p), [d['name'] for d in flatten(p)
                                          if d['kind'] in ('V', 'I')])
        self.assertEqual(source_names(p), ['VDD', 'XA/V1', 'XA/IBIAS', 'XB/V1', 'XB/IBIAS'])
        self.assertEqual(source_names(p, child['id']), ['V1', 'IBIAS'])
        self.assertEqual(p, before)

    def test_refresh_observes_rename_removal_and_rebinding(self):
        p = example('rc')
        cell = p['cells'][0]
        self.assertEqual(source_names(p), ['V1'])
        cell['devices'][0]['name'] = 'VIN'
        self.assertEqual(source_names(p), ['VIN'])
        cell['devices'].pop(0)
        self.assertEqual(source_names(p), [])
        cell['devices'].append(device('X', 'BAD', cell='missing', nets={}))
        with self.assertRaisesRegex(ValueError, 'missing'):
            source_names(p)

    def test_cycles_and_expansion_remain_bounded(self):
        p = example('empty')
        c = p['cells'][0]
        c['devices'] = [device('X', 'RECURSE', cell=c['id'], nets={})]
        with self.assertRaisesRegex(ValueError, 'Recursive'):
            source_names(p)
        c['devices'] = [device('R', 'R1'), device('R', 'R2')]
        with patch('icstudio.analysis_sources.MAX_FLAT_DEVICES', 1):
            with self.assertRaisesRegex(ValueError, 'capacity'):
                source_names(p)


if __name__ == '__main__':
    unittest.main()
