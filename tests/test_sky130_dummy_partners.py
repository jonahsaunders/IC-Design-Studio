import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import klayout.db as k
from icstudio import digital_sky130_dummy_partners as checks


def controls():
    for name in ('empty', 'unknown_dummy_present', *checks.LAYERS,
                 'seal_text', 'fuse_text', 'diecut_text', 'nested_array', 'complex_transform',
                 'odd_path', 'one_nm_sliver', 'all_partners', 'named_exemption', 'wrong_purpose'):
        layout = k.Layout(); layout.dbu = .001; top = layout.create_cell('control')
        if name in checks.LAYERS:
            top.shapes(layout.layer(*checks.LAYERS[name])).insert(k.Box(0, 0, 1000, 1000))
        elif name.endswith('_text'):
            pair = {'seal_text': (81, 1), 'fuse_text': (71, 17), 'diecut_text': (81, 11)}[name]
            top.shapes(layout.layer(*pair)).insert(k.Text('annotation', k.Trans()))
        elif name == 'unknown_dummy_present':
            for pair in ((22, 23), (23, 28), (23, 0), (22, 20), (22, 21), (22, 22)):
                top.shapes(layout.layer(*pair)).insert(k.Box(0, 0, 10000, 10000))
        elif name in ('nested_array', 'complex_transform', 'named_exemption'):
            child = layout.create_cell('testchip_buildspace' if name == 'named_exemption' else 'child')
            child.shapes(layout.layer(81, 1)).insert(k.Box(0, 0, 1000, 1000))
            if name == 'nested_array':
                mid = layout.create_cell('middle')
                mid.insert(k.CellInstArray(child.cell_index(), k.Trans(k.Trans.M90), k.Vector(2000, 0), k.Vector(0, 2000), 2, 3))
                top.insert(k.CellInstArray(mid.cell_index(), k.Trans(), k.Vector(10000, 0), k.Vector(0, 10000), 2, 2))
            else:
                top.insert(k.CellInstArray(child.cell_index(), k.ICplxTrans(2, 45, True, 10, 20)))
        elif name == 'odd_path':
            top.shapes(layout.layer(81, 11)).insert(k.Path([k.Point(0, 0), k.Point(1000, 999)], 301))
        elif name == 'one_nm_sliver':
            top.shapes(layout.layer(71, 17)).insert(k.Box(0, 0, 1, 10000))
        elif name == 'all_partners':
            for pair in checks.LAYERS.values():
                top.shapes(layout.layer(*pair)).insert(k.Box(0, 0, 1000, 1000))
        elif name == 'wrong_purpose':
            for pair in ((81, 7), (81, 10), (71, 20), (76, 20)):
                top.shapes(layout.layer(*pair)).insert(k.Text('SEALID fuse dieCut', k.Trans()))
        yield name, layout


class DummyPartnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'layout.gds'

    def report(self, name):
        layout = dict(controls())[name]
        options = k.SaveLayoutOptions(); options.gds2_write_timestamps = False
        layout.write(str(self.path), options)
        return checks.audit(self.path)

    def test_empty_partners_resolve_exactly_five_binary_relations(self):
        r = self.report('empty')
        self.assertEqual({row['id'] for row in r['rows']}, {'r1259', 'r1260', 'r1261', 'r1262', 'r1272'})
        self.assertTrue(all(row['disposition'] == 'absent-operand' for row in r['rows']))
        self.assertEqual(r['unreviewed'], 0); self.assertFalse(r['qualified']); self.assertFalse(r['chunk_complete'])
        checks.validate_saved(r, self.path)

    def test_each_known_partner_blocks_only_its_own_relations(self):
        for name in checks.LAYERS:
            r = self.report(name)
            expected = {'r1259', 'r1260'} if name == 'seal' else {'r1272'} if name == 'diecut' else {'r1261', 'r1262'}
            self.assertEqual({row['id'] for row in r['rows'] if row['disposition'] == 'unreviewed'}, expected, name)

    def test_unknown_dummy_geometry_cannot_change_an_empty_partner_proof(self):
        self.assertEqual(self.report('unknown_dummy_present')['rows'], self.report('empty')['rows'])

    def test_absent_drawn_dummy_does_not_accept_present_partners(self):
        r = self.report('all_partners')
        self.assertEqual(r['unreviewed'], 5)
        self.assertTrue(all(row['disposition'] == 'unreviewed' for row in r['rows']))

    def test_text_paths_and_tiny_shapes_do_not_disappear(self):
        for name, pending in [('seal_text', 2), ('fuse_text', 2), ('diecut_text', 1), ('odd_path', 1), ('one_nm_sliver', 2)]:
            r = self.report(name); self.assertEqual(r['unreviewed'], pending, name)
            if name.endswith('_text'):
                self.assertEqual(sum(v['texts'] for v in r['measurements'].values()), 1)

    def test_nested_reflected_arrays_preserve_every_instance(self):
        r = self.report('nested_array')
        self.assertEqual(r['measurements']['seal'], dict(raw_shapes=24, texts=0))
        self.assertEqual(r['unreviewed'], 2)

    def test_complex_transforms_and_exemption_names_do_not_hide_presence(self):
        for name in ('complex_transform', 'named_exemption'):
            self.assertEqual(self.report(name)['unreviewed'], 2, name)

    def test_unrelated_purposes_are_not_new_partner_aliases(self):
        self.assertEqual(self.report('wrong_purpose')['unreviewed'], 0)

    def test_enclosure_and_unknown_remaining_rules_never_enter_this_checker(self):
        self.assertFalse({'r1256', 'r1257', 'r1258', 'r1267', 'r1269', 'r1271'} & checks.CHECKS.keys())
        self.assertEqual({c['operation'] for c in checks.CHECKS.values()}, {'spacing', 'overlap'})

    def test_missing_duplicate_promoted_or_malformed_evidence_is_rejected(self):
        r = self.report('empty')
        for change in (lambda v: v['rows'].pop(), lambda v: v['rows'].append(v['rows'][0]),
                       lambda v: v.update(qualified=True), lambda v: v['measurements'].pop('fuse_m2_guard'),
                       lambda v: v['measurements']['seal'].update(raw_shapes=False),
                       lambda v: v['measurements']['seal'].update(texts=1)):
            altered = copy.deepcopy(r); change(altered)
            with self.assertRaises(ValueError): checks.evaluate(altered, r['gds_sha256'], r['top'])
        with self.assertRaises(ValueError): checks.evaluate(None, r['gds_sha256'], r['top'])

    def test_forged_rehashed_empty_census_is_recomputed_from_gds(self):
        before = self.report('empty'); after = self.report('seal')
        before['gds_sha256'] = after['gds_sha256']
        with self.assertRaises(ValueError): checks.validate_saved(before, self.path)

    def test_multiple_top_cells_are_rejected(self):
        layout = k.Layout(); layout.create_cell('one'); layout.create_cell('two')
        with self.assertRaises(ValueError): checks.measure(layout)

    def test_source_binding_rejects_an_enclosure_disguised_as_spacing(self):
        from scripts import sky130_dummy_partner_review as review
        folder = Path(self.temp.name)/'fixture'; review.delivery.fixture.unpack(review.delivery.fixture.BUNDLE, folder)
        catalog = json.loads((review.ROOT/review.delivery.queue.CATALOG).read_bytes())
        proof = review.source_proof(folder/'sources', catalog)
        self.assertEqual(set(proof['bindings']), set(checks.CHECKS))
        next(r for r in catalog['rows'] if r['id'] == 'r1272')['description'] = 'fomDummyDRC must be enclosed by dieCut'
        with self.assertRaises(ValueError): review.source_proof(folder/'sources', catalog)


if __name__ == '__main__':
    unittest.main()
