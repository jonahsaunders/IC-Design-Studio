from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import klayout.db as k

from scripts.sky130_error_reconciliation import (
    ROOT, CATALOG, PERIPHERY, OUTPUT, PROFILES, GLOBAL_SOURCE,
    build, reconcile, reviewed_bindings, _read_bound,
)
from scripts.sky130_global_geometry import check as global_check
from scripts.sky130_floating_connectivity import check as connection_check


class ErrorReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT/CATALOG).read_text())
        cls.periphery = json.loads((ROOT/PERIPHERY).read_text())
        cls.reviews = json.loads((ROOT/'docs/validation/sky130-floating-review-2026-10-11/data.json').read_text())

    def run_review(self, review=None, catalog=None):
        return reconcile(catalog if catalog is not None else self.catalog, self.periphery,
                         review if review is not None else self.reviews[0])

    def test_all_three_original_references_retain_every_catalog_record(self):
        before = deepcopy(self.reviews)
        for review in self.reviews:
            result = self.run_review(review)
            self.assertEqual(result['counts'], {'unreviewed': 1474, 'executed-reviewed': 61, 'absent-operand': 21})
            self.assertEqual([(r['id'], r['record'], r['rule']) for r in result['rows']],
                             [(r['id'], r['record'], r['rule']) for r in self.catalog['rows']])
            self.assertEqual(result['gds_sha256'], review['gds_sha256'])
            self.assertFalse(result['qualified'])
            self.assertFalse(result['chunk_complete'])
        self.assertEqual(self.reviews, before)

    def test_chip_rules_and_unreviewed_same_name_operands_never_inherit_a_pass(self):
        rows = {row['id']: row for row in self.run_review()['rows']}
        for error_id in ('s11', 's12', 's21', 's41', 'r150', 'r158', 'r241', 'r331', 'r1258'):
            self.assertEqual(rows[error_id]['disposition'], 'unreviewed', error_id)
            self.assertNotIn('evidence', rows[error_id])
        self.assertEqual(rows['r1181']['disposition'], 'executed-reviewed')
        self.assertEqual(rows['r1179']['disposition'], 'absent-operand')
        self.assertEqual(rows['r1179']['evidence']['checks'], ['profile.exception_labels'])

    def test_stricter_orthogonal_checks_are_bound_for_octagonal_subset_records(self):
        bindings = reviewed_bindings()
        self.assertEqual(bindings['r125']['checks'], ['x.2.diff'])
        self.assertEqual(bindings['r125']['source_records'], [4, 10])
        self.assertEqual(bindings['r226']['checks'], ['x.2.active_interconnect'])
        self.assertEqual(bindings['r232']['checks'], ['x.2.upper_via'])

    def test_every_angle_binding_detects_a_real_one_nm_slope_fault(self):
        for error_id, binding in reviewed_bindings().items():
            if binding['rule'] not in ('x.2', 'x.3a'):
                continue
            pair = tuple(binding['pair'])
            good = global_check({pair: k.Region(k.Box(0, 0, 100, 100))})
            bad = global_check({pair: k.Region(k.Polygon([
                k.Point(0, 0), k.Point(100, 0), k.Point(0, 101)]))})
            with self.subTest(error_id=error_id):
                self.assertEqual(good['status'], 'PASS')
                checks = {row['rule']: row['violations'] for row in bad['checks']}
                self.assertGreater(checks[binding['checks'][0]], 0)
                review = deepcopy(self.reviews[0])
                review['global_geometry'].update(bad)
                with self.assertRaisesRegex(ValueError, 'companion'):
                    self.run_review(review)

    def test_every_pin_binding_rejects_uncovered_and_wrong_layer_pins(self):
        for error_id, binding in reviewed_bindings().items():
            if binding['rule'] != 'x.5':
                continue
            pair, drawing = tuple(binding['pair']), tuple(binding['drawing'])
            box = k.Region(k.Box(0, 0, 100, 100))
            self.assertEqual(global_check({pair: box, drawing: box})['status'], 'PASS')
            for conductors in ({}, {(72, 20) if drawing != (72, 20) else (71, 20): box},
                               {drawing: k.Region(k.Box(1, 0, 100, 100))}):
                bad = global_check({pair: box, **conductors})
                with self.subTest(error_id=error_id, conductors=list(conductors)):
                    self.assertGreater(next(row['violations'] for row in bad['checks'] if row['rule'] == 'x.5'), 0)
                    review = deepcopy(self.reviews[0])
                    review['global_geometry'].update(bad)
                    with self.assertRaisesRegex(ValueError, 'companion'):
                        self.run_review(review)

    def test_real_floating_stack_and_each_exception_label_refuse_reconciliation(self):
        box = k.Region(k.Box(0, 0, 100, 100))
        reports = [connection_check({(68, 20): box, (68, 44): box, (69, 20): box})]
        reports += [connection_check({}, labels=[prefix+'_'+suffix])
                    for prefix in ('poly', 'li1', 'm1', 'm2', 'm3', 'm4', 'm5')
                    for suffix in ('float', 'tie')]
        for bad in reports:
            self.assertEqual(bad['status'], 'FAIL')
            review = deepcopy(self.reviews[0])
            review['floating_connectivity'].update(bad)
            with self.assertRaisesRegex(ValueError, 'companion'):
                self.run_review(review)

    def test_every_companion_requires_complete_matching_zero_integer_checks(self):
        for key in PROFILES:
            for mode in ('failure', 'boolean', 'float', 'missing', 'duplicate', 'layout', 'top', 'checker', 'total'):
                review = deepcopy(self.reviews[0])
                report = review[key]
                if mode in ('failure', 'boolean', 'float'):
                    report['checks'][-1]['violations'] = {'failure': 1, 'boolean': False, 'float': 0.0}[mode]
                elif mode == 'missing':
                    report['checks'].pop()
                elif mode == 'duplicate':
                    report['checks'].append(deepcopy(report['checks'][0]))
                elif mode == 'layout':
                    report['gds_sha256'] = '0'*64
                elif mode == 'top':
                    report['top'] = 'other'
                elif mode == 'checker':
                    report['checker_sha256'] = '0'*64
                else:
                    report['violations'] = False
                with self.subTest(profile=key, mode=mode), self.assertRaisesRegex(ValueError, 'companion'):
                    self.run_review(review)

    def test_inconsistent_extracted_area_and_floating_details_are_rejected(self):
        for mode in ('area', 'omit', 'both_omit', 'boolean', 'floating', 'nets', 'anchored'):
            review = deepcopy(self.reviews[0])
            report = review['floating_connectivity']
            if mode == 'area':
                report['covered_area_nm2']['poly'] += 1
            elif mode == 'omit':
                report['covered_area_nm2'].pop('poly')
            elif mode == 'both_omit':
                report['covered_area_nm2'].pop('poly')
                report['layer_area_nm2'].pop('poly')
            elif mode == 'boolean':
                report['layer_area_nm2']['li1_pin_root'] = False
                report['covered_area_nm2']['li1_pin_root'] = False
            elif mode == 'floating':
                report['floating'] = [{'layers': ['m1']}]
            elif mode == 'nets':
                report['nets'] = -1
            else:
                report['anchored_nets'] = report['nets'] + 1
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'extraction'):
                self.run_review(review)

    def test_changed_parent_source_and_execution_are_rejected(self):
        for mode in ('omit', 'duplicate', 'source', 'record', 'rule', 'disposition', 'checks', 'checker'):
            review = deepcopy(self.reviews[0])
            row = next(row for row in review['rows'] if row['id'] == GLOBAL_SOURCE+'#4')
            if mode == 'omit':
                review['rows'].remove(row)
            elif mode == 'duplicate':
                review['rows'].append(deepcopy(row))
            elif mode in ('source', 'rule'):
                row[mode] = 'changed'
            elif mode == 'record':
                row['record'] = 3
            elif mode == 'disposition':
                row['disposition'] = 'upstream-na'
                review['counts'] = dict(Counter(row['disposition'] for row in review['rows']))
            elif mode == 'checks':
                row['execution']['checks'] = ['x.3a']
            else:
                row['execution']['checker_sha256'] = '0'*64
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.run_review(review)

    def test_catalog_mutations_and_unbound_summaries_do_not_become_evidence(self):
        for mode in ('description', 'id', 'omit', 'order'):
            catalog = deepcopy(self.catalog)
            if mode == 'description':
                catalog['rows'][113]['description'] = 'different operand'
            elif mode == 'id':
                catalog['rows'][113]['id'] = 's11'
            elif mode == 'omit':
                catalog['rows'].pop()
            else:
                catalog['rows'].reverse()
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.run_review(catalog=catalog)
        for field, value in (('counts', {}), ('qualified', True), ('chunk_complete', True),
                             ('source_revision', 'changed'), ('checker_sha256', '0'*64),
                             ('applicability_checker_sha256', '0'*64)):
            review = deepcopy(self.reviews[0])
            review[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.run_review(review)

    def test_changed_layer_map_identity_is_rejected(self):
        review = deepcopy(self.reviews[0])
        review['global_geometry']['layer_map_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'layer-purpose'):
            self.run_review(review)

    def test_hash_bound_reader_rejects_changed_content_and_outside_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'data.json').write_text('{}')
            for path in ('data.json', '../outside.json'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    _read_bound(root, dict(path=path, sha256='0'*64))

    def test_saved_report_reproduces_from_exact_retained_evidence(self):
        report = build()
        self.assertEqual(report, json.loads((ROOT/OUTPUT).read_text()))
        self.assertEqual(report['execution_mode'], 'retained-evidence-reconciliation')


if __name__ == '__main__':
    unittest.main()
