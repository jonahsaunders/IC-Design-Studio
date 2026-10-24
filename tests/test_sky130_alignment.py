import copy
import hashlib
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as k
from icstudio import digital_sky130_alignment as checks

ROOT = Path(__file__).resolve().parents[1]
ORACLES = ROOT/'tests/fixtures/sky130-public-seal-oracles-v1'


def read(name='seal-100x120'):
    layout = k.Layout(); layout.read(str(ORACLES/(name+'.gds')))
    return layout


def write(layout, path):
    options = k.SaveLayoutOptions(); options.gds2_write_timestamps = False
    layout.write(str(path), options)


def controls():
    # Faults are made from independent Magic-exported geometry, not checker
    # constructors. Only the lower-left mask is changed in each mutant.
    golden = read('cross'); cell = golden.top_cell()
    plus = k.Region(cell.begin_shapes_rec(golden.layer(23, 0))).merged().moved(1000, 1000)
    minus = k.Region(cell.begin_shapes_rec(golden.layer(48, 0))).merged().moved(1000, 1000)
    domain = plus + minus
    for name in ('seal-100x120', 'seal-400x300', 'seal-100.005x150.005', 'cross'):
        yield name, read(name)
    for name, (layer, negative, _) in checks.MASKS.items():
        for fault in ('missing', 'reversed', 'one_nm_damage', 'wrong_purpose'):
            layout = read(); top = layout.top_cell(); top.flatten(True)
            index = layout.layer(layer, 0); original = k.Region(top.shapes(index)).merged()
            actual = original - domain
            if fault == 'reversed': actual += plus if negative else minus
            elif fault == 'one_nm_damage':
                actual = original + k.Region(k.Box(2999, 2999, 3000, 3000)) if negative else original - k.Region(k.Box(2999, 2999, 3000, 3000))
            elif fault == 'wrong_purpose': top.shapes(layout.layer(layer, 1)).insert(original & domain)
            top.shapes(index).clear(); top.shapes(index).insert(actual)
            yield name+'_'+fault, layout
    for name in ('renamed', 'translated_reflected', 'rotated', 'nested_array',
                 'duplicate_geometry', 'flattened', 'one_nm_seal_gap', 'unrelated_geometry',
                 'seal_text', 'mask_text', 'mask_path', 'magnified', 'nonorthogonal',
                 'drawn_layer_only', 'fake_nikon_name', 'five_nm_dbu', 'unsupported_dbu', 'empty'):
        layout = read(); top = layout.top_cell()
        if name == 'renamed':
            for cell in layout.each_cell(): cell.name = 'anonymous_'+str(cell.cell_index())
        elif name in ('translated_reflected', 'rotated', 'magnified', 'nonorthogonal', 'nested_array'):
            wrapper = layout.create_cell('outer')
            transform = {'translated_reflected': k.ICplxTrans(1, 0, True, -25000, 80000),
                         'rotated': k.ICplxTrans(1, 90, False, 10000, -20000),
                         'magnified': k.ICplxTrans(2, 0, False, 0, 0),
                         'nonorthogonal': k.ICplxTrans(1, 45, False, 0, 0)}
            if name == 'nested_array':
                wrapper.insert(k.CellInstArray(top.cell_index(), k.Trans(), k.Vector(200000, 0), k.Vector(0, 0), 2, 1))
            else: wrapper.insert(k.CellInstArray(top.cell_index(), transform[name]))
        elif name == 'flattened': top.flatten(True)
        elif name == 'duplicate_geometry':
            for index in layout.layer_indices(): top.shapes(index).insert(k.Region(top.begin_shapes_rec(index)))
        elif name == 'one_nm_seal_gap':
            top.flatten(True); index = layout.layer(81, 1)
            region = k.Region(top.shapes(index)) - k.Region(k.Box(56000, 0, 56001, 6000))
            top.shapes(index).clear(); top.shapes(index).insert(region)
        elif name == 'unrelated_geometry': top.shapes(layout.layer(100, 99)).insert(k.Box(-100000, -100000, 500000, 500000))
        elif name in ('seal_text', 'mask_text'):
            top.shapes(layout.layer(*( (81, 1) if name == 'seal_text' else (23, 0) ))).insert(k.Text('nikon', k.Trans(3000, 3000)))
        elif name == 'mask_path': top.shapes(layout.layer(23, 0)).insert(k.Path([k.Point(0,0), k.Point(10,0)], 1))
        elif name == 'drawn_layer_only':
            for layer, _, _ in checks.MASKS.values(): layout.clear_layer(layout.layer(layer, 0))
            top.shapes(layout.layer(68, 20)).insert(plus)
        elif name == 'fake_nikon_name':
            layout = k.Layout(); layout.dbu = .001; top = layout.create_cell('nikon_sealring_shape')
            top.shapes(layout.layer(23, 0)).insert(plus)
        elif name == 'five_nm_dbu':
            # Physical sizes unchanged; all source vertices are multiples of 5 nm.
            layout.transform(k.ICplxTrans(.2, 0, False, 0, 0)); layout.dbu = .005
        elif name == 'unsupported_dbu': layout.dbu = .003
        elif name == 'empty': layout = k.Layout(); layout.create_cell('empty')
        yield name, layout


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'layout.gds'

    def report(self, layout):
        write(layout, self.path); return checks.audit(self.path)

    def test_independent_magic_cross_matches_every_transcribed_mask(self):
        layout = read('cross'); domain, plus = checks.template(layout)
        self.assertEqual(domain.area(), 13262200); self.assertEqual(plus.area(), 2150000)
        for name, (layer, negative, _) in checks.MASKS.items():
            region = k.Region(layout.top_cell().begin_shapes_rec(layout.layer(layer, 0)))
            self.assertTrue((region ^ (domain - plus if negative else plus)).is_empty(), name)

    def test_two_independent_complete_generated_seals_match_all_four_marks(self):
        for name in ('seal-100x120', 'seal-400x300'):
            report = self.report(read(name))
            self.assertEqual(report['status'], 'public-template-match')
            self.assertEqual(report['matched_mask_windows'], 124)
            self.assertEqual(report['mismatched_mask_windows'], 0)
            checks.validate_saved(report, self.path)

    def test_each_mask_missing_reversed_damaged_and_wrong_purpose_is_detected(self):
        for name, layout in controls():
            if name.rsplit('_', 1)[0] in checks.MASKS or name.endswith(('_one_nm_damage', '_wrong_purpose')):
                with self.subTest(name=name):
                    report = self.report(layout)
                    mask, fault = next((mask, name[len(mask)+1:]) for mask in checks.MASKS if name.startswith(mask+'_'))
                    expected = {'missing':'missing','reversed':'reversed','one_nm_damage':'damaged','wrong_purpose':'missing'}[fault]
                    self.assertEqual(report['measurements']['marks'][0]['masks'][mask]['state'], expected)
                    self.assertEqual(report['matched_mask_windows'], 123)
                    self.assertEqual(report['mismatched_mask_windows'], 1)

    def test_names_hierarchy_reflection_rotation_duplicates_and_unrelated_shapes_do_not_change_results(self):
        selected = {'renamed', 'translated_reflected', 'rotated', 'duplicate_geometry', 'flattened', 'unrelated_geometry', 'five_nm_dbu'}
        for name, layout in controls():
            if name in selected:
                self.assertEqual(self.report(layout)['matched_mask_windows'], 124, name)

    def test_source_generator_five_nm_gap_and_tiny_seal_damage_do_not_define_valid_windows(self):
        for name, layout in controls():
            if name in ('seal-100.005x150.005', 'one_nm_seal_gap', 'nested_array'):
                report = self.report(layout)
                self.assertEqual(report['measurements']['context'], 'unrecognized-seal', name)
                self.assertEqual(report['matched_mask_windows'], 0)

    def test_text_paths_magnification_and_nonorthogonal_transforms_are_explicitly_unsupported(self):
        for name, layout in controls():
            if name in ('seal_text', 'mask_text', 'mask_path', 'magnified', 'nonorthogonal'):
                self.assertEqual(self.report(layout)['measurements']['context'], 'unsupported-mask-data', name)

    def test_missing_boundary_cannot_pass_even_if_a_cross_or_magic_name_is_present(self):
        for name, layout in controls():
            if name in ('cross', 'fake_nikon_name', 'empty'):
                report = self.report(layout)
                self.assertEqual(report['measurements']['context'], 'missing-seal-context', name)
                self.assertEqual(report['matched_mask_windows'], 0)

    def test_drawn_layers_cannot_substitute_for_mask_layers(self):
        layout = next(l for name,l in controls() if name == 'drawn_layer_only')
        report = self.report(layout)
        self.assertEqual(report['mismatched_mask_windows'], 124)

    def test_nonrepresentable_grid_is_not_rounded(self):
        layout = next(l for name,l in controls() if name == 'unsupported_dbu')
        self.assertEqual(self.report(layout)['measurements']['context'], 'unsupported-template-grid-or-size')

    def test_template_success_never_promotes_catalog_or_full_signoff(self):
        report = self.report(read())
        self.assertEqual({row['id'] for row in report['rows']}, {'r'+str(n) for n in range(1076,1132)})
        self.assertTrue(all(row['disposition']=='unreviewed' for row in report['rows']))
        self.assertEqual(report['unreviewed'], 56)
        self.assertFalse(report['qualified']); self.assertFalse(report['chunk_complete'])

    def test_modified_or_incomplete_report_is_rejected(self):
        report = self.report(read())
        for change in (lambda r: r.update(qualified=True), lambda r: r['rows'].pop(),
                       lambda r: r['measurements']['marks'].pop(), lambda r: r['measurements']['census'].pop('cfom'),
                       lambda r: r['measurements']['census']['cfom'].update(raw_shapes=True),
                       lambda r: r['measurements']['marks'][0]['masks'].pop('cfom')):
            bad = copy.deepcopy(report); change(bad)
            with self.assertRaises(ValueError): checks.evaluate(bad,report['gds_sha256'],report['top'])

    def test_rehashed_forged_measurements_are_recomputed_from_actual_layout(self):
        before = self.report(read())
        changed = next(l for name,l in controls() if name == 'cfom_missing')
        after = self.report(changed); before['gds_sha256'] = after['gds_sha256']
        with self.assertRaises(ValueError): checks.validate_saved(before,self.path)

    def test_multiple_roots_are_rejected(self):
        layout = read(); layout.create_cell('extra')
        with self.assertRaises(ValueError): checks.measure(layout)

    def test_magic_oracles_are_hash_authenticated(self):
        from scripts.check_sky130_alignment import ORACLE_MANIFEST_SHA256
        self.assertEqual(hashlib.sha256((ORACLES/'manifest.json').read_bytes()).hexdigest(), ORACLE_MANIFEST_SHA256)
        manifest = json.loads((ORACLES/'manifest.json').read_text(encoding='utf-8'))
        for name, expected in manifest['files'].items():
            data = (ORACLES/name).read_bytes()
            self.assertEqual(len(data), expected['size'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected['sha256'])

    def test_source_bindings_authenticate_all_files_and_canonical_mask_purposes(self):
        from scripts.check_sky130_alignment import source_proof
        proof = source_proof()
        self.assertEqual(len(proof['bindings']), 56)
        self.assertEqual(proof['bindings']['r1076']['gds_map']['GDS layer:datatype'], '23:0')
        self.assertEqual(proof['bindings']['r1106']['gds_map']['Layer name'], 'ctm1')
        changed = Path(self.temp.name)/'source'
        shutil.copytree(ROOT/'tests/fixtures/sky130-public-seal-v1', changed)
        (changed/'nikon_sealring_shape.mag').write_text('changed')
        with self.assertRaises(ValueError): source_proof(changed)

    def test_cli_preserves_unqualified_exit_status_and_never_overwrites_layout(self):
        from scripts.check_sky130_alignment import main
        write(read(),self.path); report_path=Path(self.temp.name)/'report.json'
        self.assertEqual(main([str(self.path),'--output',str(report_path)]), 2)
        self.assertEqual(json.loads(report_path.read_text())['status'], 'public-template-match')
        before = self.path.read_bytes()
        with self.assertRaises(ValueError): main([str(self.path),'--output',str(self.path)])
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
