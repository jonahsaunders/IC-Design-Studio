from copy import deepcopy
import unittest
from scripts.ihp_magic_rc_points import point, prepare


class ResistancePointTests(unittest.TestCase):
    def fixture(self):
        pins = [dict(layer='Metal1', box_nm=[97800, 168070, 98115, 168330])]
        labels = dict(checkpoint_sha256='a' * 64, nets=[
            dict(net=name, alias=f'NET{i:06d}', pins=deepcopy(pins))
            for i, name in enumerate(('VDD', 'VSS', 'clk', 'internal'))])
        boundary = dict(checkpoint_sha256='a' * 64,
                        ports={'clk': dict(net='clk', boxes=[
                            dict(layer='Metal2', box_nm=[100, 100, 300, 300])])})
        return labels, boundary

    def test_exact_label_pattern_excludes_nearby_fill(self):
        result = prepare(*self.fixture())
        self.assertIn('select area labels NET000003', result['commands'])
        self.assertNotIn('select area labels\n', result['commands'])
        self.assertNotIn('FILL', result['commands'])

    def test_external_endpoint_uses_boundary_and_internal_uses_cell_pin(self):
        rows = prepare(*self.fixture())['points']
        self.assertEqual(rows[0]['point_nm'], [200, 200])
        self.assertEqual(rows[0]['layer'], 'Metal2')
        self.assertEqual(rows[1]['point_nm'], [97955, 168200])
        self.assertTrue(rows[0]['boundary'])
        self.assertFalse(rows[1]['boundary'])

    def test_supplies_are_not_resistance_ports(self):
        commands = prepare(*self.fixture())['commands']
        self.assertIn('port NET000000 remove', commands)
        self.assertIn('port NET000001 remove', commands)
        self.assertNotIn('findlabel NET000000', commands)

    def test_mismatched_checkpoint_fails(self):
        labels, boundary = self.fixture()
        boundary['checkpoint_sha256'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'checkpoints differ'):
            prepare(labels, boundary)

    def test_unknown_or_repeated_boundary_net_fails(self):
        for net in ('unknown', 'clk'):
            labels, boundary = self.fixture()
            boundary['ports']['bad'] = dict(net=net, boxes=boundary['ports']['clk']['boxes'])
            with self.assertRaises(ValueError):
                prepare(labels, boundary)

    def test_unsafe_or_duplicate_alias_fails(self):
        for alias in ('NET000002;quit', 'NET000000'):
            labels, boundary = self.fixture()
            labels['nets'][2]['alias'] = alias
            with self.assertRaises(ValueError):
                prepare(labels, boundary)

    def test_degenerate_or_unsupported_pin_fails(self):
        for pin in (dict(layer='Metal1', box_nm=[0, 0, 1, 1]),
                    dict(layer='Poly', box_nm=[0, 0, 100, 100]),
                    dict(layer='Metal1', box_nm=[0., 0, 100, 100])):
            with self.assertRaises(ValueError):
                point(pin)

    def test_missing_boundary_pin_fails(self):
        labels, boundary = self.fixture()
        labels['nets'][2]['pins'] = []
        with self.assertRaisesRegex(ValueError, 'verified metal pin'):
            prepare(labels, boundary)


if __name__ == '__main__':
    unittest.main()
