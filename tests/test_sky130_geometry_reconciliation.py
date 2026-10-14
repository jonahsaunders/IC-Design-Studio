"""Semantic and tamper controls for the expanded error-record bindings."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as k

from scripts import sky130_geometry_reconciliation as review


class GeometryReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((review.ROOT / review.previous.CATALOG).read_text())
        cls.periphery = json.loads((review.ROOT / review.previous.PERIPHERY).read_text())
        checkpoint = json.loads((review.ROOT / review.previous.CHECKPOINT).read_text())
        cls.cases = json.loads((review.ROOT / checkpoint['data']['path']).read_text())
        cls.bindings = review.geometry_bindings() | review.mask_bindings(cls.catalog)
        cls.controls = review.notch_controls()

    def run_review(self, case=None, bindings=None, controls=None, catalog=None):
        return review.reconcile(catalog if catalog is not None else self.catalog, self.periphery,
                                case if case is not None else self.cases[0],
                                bindings if bindings is not None else self.bindings,
                                controls if controls is not None else self.controls)

    def test_all_original_filled_cases_gain_exact_reviewed_coverage(self):
        for case in self.cases:
            before = deepcopy(case)
            result = self.run_review(case)
            self.assertEqual(result['counts'], {'unreviewed': 1161, 'executed-reviewed': 356, 'absent-operand': 39})
            self.assertEqual(result['periphery_counts']['executed-reviewed'], 135)
            self.assertEqual(result['periphery_counts']['execution-review-required'], 22)
            self.assertEqual(result['periphery_counts']['definition-required'], 1)
            self.assertEqual(result['gds_sha256'], case['gds_sha256'])
            self.assertEqual(case, before)
            self.assertFalse(result['qualified'])
            self.assertFalse(result['chunk_complete'])

    def test_all_catalog_records_remain_present_and_chip_rows_stay_open(self):
        result = self.run_review()
        self.assertEqual(Counter(row['id'] for row in result['rows']), Counter(row['id'] for row in self.catalog['rows']))
        by_id = {row['id']: row for row in result['rows']}
        for row in self.catalog['rows']:
            if row['id'].startswith('s'):
                self.assertEqual(by_id[row['id']]['disposition'], 'unreviewed')
        # Undocumented metop aliases, ambiguous FOM wording and RF/device
        # predicates cannot inherit the broad geometry or mask passes.
        for number in (150, 151, 152, 153, 154, 155, 156, 157, 258, 543, 544, 705, 759):
            self.assertEqual(by_id['r' + str(number)]['disposition'], 'unreviewed')

    def test_every_new_binding_rejects_a_failed_actual_check(self):
        for error_id, binding in self.bindings.items():
            with self.subTest(error_id=error_id):
                case = deepcopy(self.cases[0])
                profile = case[binding['profile']]
                row = next(row for row in profile['checks'] if row['rule'] == binding['checks'][0])
                row['violations'] = 1
                with self.assertRaisesRegex(ValueError, 'companion profile'):
                    self.run_review(case)

    def test_every_new_binding_rejects_a_missing_or_wrong_parent(self):
        # Each distinct parent matters, even when multiple error records share
        # a checker. A stale parent must not be concealed by aggregate zeroes.
        parents = sorted({name for binding in self.bindings.values() for name in binding['parents']})
        for parent_id in parents:
            with self.subTest(parent=parent_id):
                case = deepcopy(self.cases[0])
                row = next(row for row in case['rows'] if row['id'] == parent_id)
                row['execution']['checks'] = []
                with self.assertRaises(ValueError):
                    self.run_review(case)

    def test_boolean_float_missing_duplicate_or_stale_check_cannot_pass(self):
        for bad in (True, False, 0.0, -1):
            case = deepcopy(self.cases[0])
            case[review.METAL]['checks'][0]['violations'] = bad
            with self.assertRaises(ValueError):
                self.run_review(case)
        for mutation in ('missing', 'duplicate', 'stale', 'wrong_top', 'source'):
            case = deepcopy(self.cases[0])
            profile = case[review.METAL]
            if mutation == 'missing':
                profile['checks'].pop()
            elif mutation == 'duplicate':
                profile['checks'][-1] = deepcopy(profile['checks'][0])
            elif mutation == 'stale':
                profile['gds_sha256'] = '0' * 64
            elif mutation == 'wrong_top':
                profile['top'] = 'different'
            else:
                profile['checker_sha256'] = '0' * 64
            with self.assertRaises(ValueError):
                self.run_review(case)

    def test_wrong_parent_check_and_chip_binding_are_refused(self):
        bindings = deepcopy(self.bindings)
        bindings['r398']['parents'] = [review.parent('p021-nwell_dotdash', 2)]
        with self.assertRaisesRegex(ValueError, 'Parent check'):
            self.run_review(bindings=bindings)
        bindings = deepcopy(self.bindings)
        bindings['s1'] = deepcopy(bindings['r398'])
        with self.assertRaisesRegex(ValueError, 'chip coverage'):
            self.run_review(bindings=bindings)

    def test_changed_catalog_threshold_is_rejected(self):
        catalog = deepcopy(self.catalog)
        row = next(row for row in catalog['rows'] if row['id'] == 'r398')
        row['description'] = '0.80 min. width of nwell'
        with self.assertRaisesRegex(ValueError, 'catalog content'):
            self.run_review(catalog=catalog)

    def test_every_mask_alias_rejects_one_nm_slope_errors(self):
        good = k.Region(k.Polygon([k.Point(0, 0), k.Point(100, 0), k.Point(0, 100)]))
        bad = k.Region(k.Polygon([k.Point(0, 0), k.Point(100, 0), k.Point(0, 101)]))
        for _, _, _, pair, _, _ in (*review.MASK_OPERANDS, *review.EDIT_OPERANDS):
            with self.subTest(pair=pair):
                counts = lambda region: {row['rule']: row['violations'] for row in review.global_geometry.check({pair: region})['checks']}
                self.assertEqual(counts(good)['x.3a'], 0)
                self.assertGreater(counts(bad)['x.3a'], 0)
                # A containing shape cannot hide an illegal input edge.
                hidden = k.Region(k.Box(-100, -100, 1000, 1000))
                hidden.insert(bad)
                self.assertGreater(counts(hidden)['x.3a'], 0)

    def test_all_restricted_masks_need_actual_allowed_coverage(self):
        shape = k.Region(k.Box(0, 0, 100, 100))
        for _, _, _, pair, _, _ in review.MASK_OPERANDS:
            for allowed in ((81, 10), (81, 1), (81, 12)):
                counts = lambda masks: {row['rule']: row['violations'] for row in review.global_geometry.check(masks)['checks']}
                self.assertGreater(counts({pair: shape})['x.15a'], 0)
                self.assertEqual(counts({pair: shape, allowed: shape})['x.15a'], 0)
                self.assertGreater(counts({pair: shape, allowed: k.Region(k.Box(1, 0, 100, 100))})['x.15a'], 0)

    def test_all_mask_edits_need_core_not_frame_or_dummy_fill(self):
        shape = k.Region(k.Box(0, 0, 100, 100))
        for _, _, _, pair, _, containment in review.EDIT_OPERANDS:
            if containment is None:
                continue
            counts = lambda masks: {row['rule']: row['violations'] for row in review.global_geometry.check(masks)['checks']}
            self.assertEqual(counts({pair: shape, (81, 2): shape})['x.9'], 0)
            self.assertGreater(counts({pair: shape, (81, 10): shape})['x.9'], 0)
            self.assertGreater(counts({pair: shape, (23, 28): shape})['x.9'], 0)
            self.assertGreater(counts({pair: shape, (81, 2): k.Region(k.Box(1, 0, 100, 100))})['x.9'], 0)

    def test_wrong_purpose_alias_and_changed_mask_description_fail(self):
        changed = list(review.MASK_OPERANDS)
        row = list(changed[0])
        row[2] = 'mask'
        changed[0] = tuple(row)
        with patch.object(review, 'MASK_OPERANDS', changed), self.assertRaisesRegex(ValueError, 'mapping'):
            review.mask_bindings(self.catalog)
        catalog = deepcopy(self.catalog)
        next(row for row in catalog['rows'] if row['id'] == 'r176')['description'] = 'non-octagonal wrong edge'
        with self.assertRaisesRegex(ValueError, 'mask catalog'):
            review.mask_bindings(catalog)

    def test_all_ring_bindings_are_absence_under_exact_square_guards(self):
        absent = {key for key, value in self.bindings.items() if value['disposition'] == 'absent-operand'}
        self.assertEqual(len(absent), 18)
        for error_id, profile, check, pair, size in (
            ('r713', review.LOW, 'licon.1', (66, 44), 170),
            ('r781', review.METAL, 'ct.size', (67, 44), 170),
            ('r805', review.METAL, 'via.size', (68, 44), 150),
            ('r852', review.METAL, 'via2.size', (69, 44), 200),
            ('r872', review.METAL, 'via3.size', (70, 44), 200),
            ('r889', review.METAL, 'via4.size', (71, 44), 800)):
            self.assertIn(error_id, absent)
            good = k.Region(k.Box(0, 0, size, size))
            ring = k.Region(k.Box(0, 0, size * 4, size * 4)) - k.Region(k.Box(size, size, size * 3, size * 3))
            module = review.previous.PROFILES[profile]
            result = lambda region: next(row['violations'] for row in module.check({pair: region})['checks'] if row['rule'] == check)
            self.assertEqual(result(good), 0)
            self.assertGreater(result(ring), 0)

    def test_notch_controls_cover_all_operands_boundaries_and_orientations(self):
        review.validate_notch_controls(self.controls)
        self.assertEqual(self.controls['controls'], 408)
        self.assertEqual(sum(row['violations'] > 0 for row in self.controls['rows']), 136)
        self.assertEqual({row['rotation'] for row in self.controls['rows']}, {0, 90, 180, 270})
        self.assertEqual({row['delta_nm'] for row in self.controls['rows']}, {-1, 0, 1})

    def test_disabled_spacing_operation_is_detected_by_notch_execution(self):
        module = review.previous.PROFILES[review.WIDE]
        original = module.check
        def disabled(regions):
            result = original(regions)
            for row in result['checks']:
                if row['rule'] == 'm1.wide_spacing':
                    row['violations'] = 0
            return result
        with patch.object(module, 'check', disabled), self.assertRaisesRegex(ValueError, 'Notch boundary'):
            review.notch_controls()

    def test_incomplete_false_or_duplicate_notch_evidence_blocks_reconciliation(self):
        for mutation in ('missing', 'duplicate', 'false_pass', 'boolean', 'wrong_limit', 'wrong_status'):
            controls = deepcopy(self.controls)
            if mutation == 'missing':
                controls['rows'].pop()
            elif mutation == 'duplicate':
                controls['rows'][-1] = deepcopy(controls['rows'][0])
            elif mutation == 'false_pass':
                controls['rows'][0]['violations'] = 0
            elif mutation == 'boolean':
                controls['rows'][0]['violations'] = True
            elif mutation == 'wrong_limit':
                controls['rows'][0]['minimum_nm'] -= 1
            else:
                controls['status'] = 'FAIL'
            with self.assertRaisesRegex(ValueError, 'notch controls'):
                self.run_review(controls=controls)

    def test_saved_record_is_exactly_reproducible_and_tampering_fails(self):
        with TemporaryDirectory() as temp:
            output = Path(temp) / 'report.json'
            with patch('sys.argv', ['reconcile', '--output', str(output)]):
                review.main()
            with patch('sys.argv', ['reconcile', '--output', str(output), '--check']):
                review.main()
            data = json.loads(output.read_text())
            data['chunk_complete'] = True
            output.write_text(json.dumps(data))
            with patch('sys.argv', ['reconcile', '--output', str(output), '--check']), self.assertRaisesRegex(ValueError, 'differs'):
                review.main()


if __name__ == '__main__':
    unittest.main()
