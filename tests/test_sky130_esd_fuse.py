"""Empty selectors never excuse nonempty, missing, or mismatched targets."""
from copy import deepcopy
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest

import klayout.db as k
from scripts import sky130_esd_fuse_review as review


class EsdFuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name) / 'inputs'
        p = review.previous
        p.marker.nsm.fixture.unpack(p.marker.nsm.fixture.BUNDLE, cls.folder)
        cls.catalog = json.loads((review.ROOT / p.marker.nsm.geometry.previous.CATALOG).read_bytes())
        cls.inventory = json.loads((review.ROOT / p.marker.nsm.geometry.previous.PERIPHERY).read_bytes())
        cls.proof = review.source_proof(cls.folder / 'sources', cls.inventory, cls.catalog)
        cls.manual = json.loads(p.marker.nsm.scope.OUTPUT.read_bytes())
        cls.geometry = json.loads(p.marker.nsm.geometry.OUTPUT.read_bytes())
        cls.nsm = json.loads(p.marker.nsm.OUTPUT.read_bytes())
        cls.marker = json.loads(p.marker.OUTPUT.read_bytes())

    def inputs(self, name='counter'):
        p = review.previous
        pick = lambda data: next(r for r in data['cases'] if r['case'] == name)
        manual = deepcopy(pick(self.manual))
        baseline = p.preceding(pick(self.geometry), pick(self.nsm), pick(self.marker))
        path = self.folder / name / 'filled.gds'
        baseline = p.reconcile(self.catalog, self.inventory, baseline, manual, p.audit(path))
        return manual, baseline, review.audit(path)

    def reconcile(self, *args):
        return review.reconcile(*args, self.proof)

    def test_sources_bind_exact_targets_and_32_records(self):
        self.assertEqual(self.proof['esd_parent'], review.NCM + '#7')
        self.assertEqual(len(self.proof['bindings']), 32)
        self.assertNotIn('r1261', self.proof['bindings'])
        self.assertEqual(self.proof['bindings']['r1306']['parents'], [review.FUSE + '#15', review.FUSE + '#16'])

    def test_three_references_close_only_the_reviewed_targets(self):
        for name in ('counter', 'uart', 'apb'):
            manual, baseline, measured = self.inputs(name)
            result, errors = self.reconcile(manual, baseline, measured)
            self.assertEqual(result['counts']['execution-review-required'], 15)
            self.assertEqual(result['counts']['definition-required'], 1)
            self.assertEqual(errors['counts'], {'unreviewed': 945, 'executed-reviewed': 356, 'absent-operand': 255})
            changed = [r['id'] for r, old in zip(result['rows'], manual['rows']) if r != old]
            self.assertCountEqual(changed, [self.proof['esd_parent'], self.proof['fuse_parent']])
            changed = [r['id'] for r, old in zip(errors['rows'], baseline['rows']) if r != old]
            self.assertCountEqual(changed, self.proof['bindings'])
            # Enclosing-layer ambiguity and the missing numeric rule survive.
            for rule in ('ncm.3', 'hvtr.3', 'lvtn.4b', 'nsm.3a', 'nsm.3b'):
                self.assertEqual(next(r for r in result['rows'] if r['rule'] == rule)['disposition'], 'execution-review-required')

    def test_nonempty_esd_does_not_pass_merely_because_ncm_is_empty(self):
        manual, baseline, measured = self.inputs()
        measured['counts'][str(review.ESD_PAIR)] = 1
        result, errors = self.reconcile(manual, baseline, measured)
        self.assertEqual(next(r for r in result['rows'] if r['rule'] == 'ncm.4')['disposition'], 'execution-review-required')
        self.assertEqual(errors['counts']['unreviewed'], 945)

    def test_every_fuse_or_target_purpose_reopens_all_fuse_decisions(self):
        manual, baseline, measured = self.inputs()
        for pair in review.FUSE_PAIRS:
            changed = deepcopy(measured)
            changed['counts'][str(pair)] = 1
            result, errors = self.reconcile(manual, baseline, changed)
            self.assertEqual(next(r for r in result['rows'] if r['id'] == self.proof['fuse_parent'])['disposition'], 'execution-review-required')
            self.assertEqual(errors, baseline)

    def test_raw_text_degenerate_paths_and_shapes_in_arrays_are_not_discarded(self):
        for pair in review.PAIRS:
            for kind in ('box', 'polygon', 'text', 'path'):
                layout = k.Layout(); layout.dbu = .001
                top = layout.create_cell('TOP'); child = layout.create_cell('CHILD')
                shapes = child.shapes(layout.layer(*pair))
                if kind == 'box': shapes.insert(k.Box(0, 0, 10, 10))
                elif kind == 'polygon': shapes.insert(k.Polygon([k.Point(0, 0), k.Point(10, 0), k.Point(5, 10)]))
                elif kind == 'text': shapes.insert(k.Text('present', k.Trans(0, 0)))
                else: shapes.insert(k.Path([k.Point(0, 0), k.Point(10, 0)], 0))
                top.insert(k.CellInstArray(child.cell_index(), k.Trans(k.Trans.M90, 100, 200),
                                          k.Vector(40, 0), k.Vector(0, 40), 2, 3))
                self.assertEqual(review.measure(layout)['counts'][str(pair)], 6)

    def test_extra_top_and_wrong_units_are_rejected(self):
        layout = k.Layout(); layout.dbu = .001; layout.create_cell('TOP')
        layout.create_cell('SECOND')
        with self.assertRaises(ValueError): review.measure(layout)
        layout = k.Layout(); layout.dbu = .002; layout.create_cell('TOP')
        with self.assertRaises(ValueError): review.measure(layout)

    def test_incomplete_or_invalid_measurements_cannot_claim_absence(self):
        manual, baseline, measured = self.inputs()
        for pair in review.PAIRS:
            for value in (None, False, 0.0, -1, '0'):
                changed = deepcopy(measured); changed['counts'][str(pair)] = value
                with self.assertRaises(ValueError): self.reconcile(manual, baseline, changed)
            changed = deepcopy(measured); del changed['counts'][str(pair)]
            with self.assertRaises(ValueError): self.reconcile(manual, baseline, changed)

    def test_changed_gds_top_or_checker_identity_is_rejected(self):
        manual, baseline, measured = self.inputs()
        for key in ('gds_sha256', 'top', 'checker_sha256'):
            changed = deepcopy(measured); changed[key] = 'different'
            with self.assertRaises(ValueError): self.reconcile(manual, baseline, changed)

    def test_missing_or_false_fuse_parent_witnesses_fail_closed(self):
        manual, baseline, measured = self.inputs()
        for witnesses in ({}, {'(71, 17)': False, '(76, 44)': 0}, {'(71, 17)': 0, '(76, 44)': 1}):
            changed = deepcopy(manual)
            next(r for r in changed['rows'] if r['id'] == review.FUSE + '#1')['witnesses'] = witnesses
            with self.assertRaises(ValueError): self.reconcile(changed, baseline, measured)

    def test_source_mutation_is_not_accepted(self):
        path = self.folder / 'sources' / review.DEFINITION
        original = path.read_bytes()
        try:
            path.write_bytes(original + b'\n')
            with self.assertRaises(ValueError): review.source_proof(self.folder / 'sources', self.inventory, self.catalog)
        finally:
            path.write_bytes(original)

    def test_catalog_description_change_is_not_accepted(self):
        changed = deepcopy(self.catalog)
        next(r for r in changed['rows'] if r['id'] == 'r1280')['description'] = 'different'
        with self.assertRaises(ValueError): review.source_proof(self.folder / 'sources', self.inventory, changed)

    def test_duplicate_catalog_record_is_not_accepted(self):
        manual, baseline, measured = self.inputs()
        baseline['rows'].append(deepcopy(baseline['rows'][0]))
        with self.assertRaises(ValueError): self.reconcile(manual, baseline, measured)

    def test_omitting_unrelated_requirements_cannot_improve_coverage(self):
        for which in ('manual', 'catalog'):
            manual, baseline, measured = self.inputs()
            selected = manual if which == 'manual' else baseline
            selected['rows'].pop()
            selected['counts'] = dict(Counter(r['disposition'] for r in selected['rows']))
            with self.assertRaises(ValueError): self.reconcile(manual, baseline, measured)


if __name__ == '__main__':
    unittest.main()
