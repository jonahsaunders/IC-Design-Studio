"""An absent enclosing/NSM operand cannot erase an unrelated required target."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import unittest
import zipfile

from icstudio import digital_sky130_scope as scope
from icstudio.digital_sky130_rules import evaluate
from scripts import sky130_scope_corrections as report
from scripts.sky130_rule_inventory import manual_rows
from tests import test_sky130_application_rules as application

ROOT=Path(__file__).resolve().parents[1]


class Sky130ScopeCorrectionTests(unittest.TestCase):
    def baseline(self):
        return json.loads((ROOT/'docs/validation/sky130-density-scope-2026-10-14.json').read_bytes())['cases'][0]

    def test_corrects_exactly_three_rows_without_changing_any_measurement(self):
        before=self.baseline();saved=deepcopy(before);after=scope.correct(before)
        self.assertEqual(before,saved)
        targets={item['id'] for item in scope.CORRECTIONS}
        for left,right in zip(before['rows'],after['rows']):
            if left['id'] not in targets:self.assertEqual(left,right)
            else:
                self.assertEqual(right['disposition'],'execution-review-required')
                self.assertEqual(left.get('witnesses'),right.get('witnesses'))
                self.assertEqual({k:v for k,v in left.items() if k not in ('reason','disposition')},
                                 {k:v for k,v in right.items() if k not in ('reason','disposition')})
        self.assertEqual(after['counts']['executed-reviewed'],135)
        self.assertEqual(after['counts']['absent-operand'],274)
        self.assertEqual(after['counts']['execution-review-required'],17)
        self.assertEqual(after['error_counts'],before['error_counts'])
        self.assertEqual(scope.correct(after),after)

    def test_exact_published_targets_do_not_depend_on_absent_enclosers(self):
        with zipfile.ZipFile(ROOT/'tests/fixtures/sky130-filled-references-v1.zip') as archive:
            rows={}
            for item in scope.CORRECTIONS:
                rows.update({r['id']:r for r in manual_rows(archive.read('sources/'+item['source']),item['source'])})
            for item in scope.CORRECTIONS:
                row=rows[item['id']]
                for key in ('source','source_sha256','record','rule'):self.assertEqual(row[key],item[key])
            hvtr=next(r for r in rows.values() if r['rule']=='hvtr.3')
            self.assertEqual(hvtr['description'],'Min enclosure of pfet by hvtr')
            nsm_a=next(r for r in rows.values() if r['rule']=='nsm.3a')
            nsm_b=next(r for r in rows.values() if r['rule']=='nsm.3b')
            self.assertIn('by :drc_tag:`areaid.ft`',nsm_a['description'])
            self.assertIn('between :drc_tag:`areaid.dt`',nsm_b['description'])
            self.assertNotIn('nsm',nsm_a['description'].lower())
            self.assertNotIn('nsm',nsm_b['description'].lower())

    def test_changed_missing_duplicate_or_promoted_sources_are_rejected(self):
        base=self.baseline();target=scope.CORRECTIONS[0]['id']
        for fault in ('source','missing','duplicate','executed','advisory','identity','counts'):
            changed=deepcopy(base);row=next(r for r in changed['rows'] if r['id']==target)
            if fault=='source':row['source_sha256']='a'*64
            elif fault=='missing':changed['rows'].remove(row)
            elif fault=='duplicate':changed['rows'].append(deepcopy(row))
            elif fault=='executed':row.update(disposition='executed-reviewed',execution={})
            elif fault=='advisory':row['disposition']='advisory'
            elif fault=='identity':row['rule']='another'
            else:changed['counts']['absent-operand']+=1
            if fault!='counts':changed['counts']=dict(Counter(r['disposition'] for r in changed['rows']))
            with self.subTest(fault=fault),self.assertRaises(ValueError):scope.correct(changed)

    def test_missing_scope_or_restored_absence_cannot_validate(self):
        good=scope.correct(self.baseline())
        for fault in ('missing-review','changed-review','restored-absence','changed-reason'):
            bad=deepcopy(good)
            row=next(r for r in bad['rows'] if r['id']==scope.CORRECTIONS[0]['id'])
            if fault=='missing-review':bad.pop('scope_review')
            elif fault=='changed-review':bad['scope_review']['qualified']=True
            elif fault=='restored-absence':row['disposition']='absent-operand'
            else:row['reason']='unchanged mask means passed'
            bad['counts']=dict(Counter(r['disposition'] for r in bad['rows']))
            with self.subTest(fault=fault),self.assertRaises(ValueError):scope.validate(bad)

    def test_correction_keeps_existing_pending_rows_pending_even_with_present_witnesses(self):
        value=self.baseline()
        for row in value['rows']:
            if row['id'] in {x['id'] for x in scope.CORRECTIONS}:
                row['disposition']='execution-review-required';row['witnesses']={'measured operand':1}
        value['counts']=dict(Counter(r['disposition'] for r in value['rows']))
        corrected=scope.correct(value)
        self.assertEqual(corrected['counts'],value['counts'])
        self.assertTrue(all(r['witnesses']=={'measured operand':1} for r in corrected['rows'] if r['id'] in {x['id'] for x in scope.CORRECTIONS}))

    def test_saved_application_gate_requires_current_scope_review(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            _,_,good=application.fixture(Path(td))
            for fault in ('missing-review','restored-absence'):
                bad=deepcopy(good)
                if fault=='missing-review':bad['ledger'].pop('scope_review')
                else:
                    next(r for r in bad['ledger']['rows'] if r['id']==scope.CORRECTIONS[0]['id'])['disposition']='absent-operand'
                    bad['ledger']['counts']=dict(Counter(r['disposition'] for r in bad['ledger']['rows']))
                    bad['coverage']['counts']=bad['ledger']['counts']
                with self.subTest(fault=fault),self.assertRaises(ValueError):
                    evaluate(bad,good['gds_sha256'],good['checkpoint_sha256'],good['top'],good['platform_fingerprint'],good['policy'])

    def test_full_report_preserves_historical_source_scope_and_counts(self):
        value=report.build()
        self.assertFalse(value['qualified']);self.assertFalse(value['chunk_complete'])
        self.assertEqual(len(value['cases']),3)
        self.assertTrue(all(r['counts']['execution-review-required']==17 for r in value['cases']))


if __name__=='__main__':unittest.main()
