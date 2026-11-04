from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from icstudio import digital_sky130_pad_scope as pad
from icstudio import digital_sky130_rules as rules
from icstudio.digital_macro import export
from tests import test_sky130_application_rules as app

ROOT=Path(__file__).resolve().parents[1]


class PadScopeTests(unittest.TestCase):
    def baseline(self):
        return json.loads((ROOT/'docs/validation/sky130-scope-corrections-2026-10-14.json').read_bytes())['cases'][0]

    def test_reopens_only_mask_target_and_retains_every_measurement(self):
        before=self.baseline();saved=deepcopy(before);after=pad.correct(before)
        self.assertEqual(before,saved);self.assertEqual(pad.correct(after),after)
        for left,right in zip(before['rows'],after['rows']):
            if left['id']!=pad.ROW['id']:self.assertEqual(left,right)
            else:
                self.assertEqual(right['disposition'],'execution-review-required')
                self.assertEqual(left['witnesses'],right['witnesses'])
                self.assertEqual({k:v for k,v in left.items() if k not in ('disposition','reason')},
                                 {k:v for k,v in right.items() if k not in ('disposition','reason')})
        self.assertEqual(after['counts']['absent-operand'],before['counts']['absent-operand']-1)
        self.assertEqual(after['counts']['execution-review-required'],before['counts']['execution-review-required']+1)

    def test_changed_missing_duplicate_or_promoted_target_rejected(self):
        for fault in ('missing','duplicate','source','executed','advisory','counts'):
            bad=self.baseline();row=next(r for r in bad['rows'] if r['id']==pad.ROW['id'])
            if fault=='missing':bad['rows'].remove(row)
            elif fault=='duplicate':bad['rows'].append(deepcopy(row))
            elif fault=='source':row['source_sha256']='0'*64
            elif fault=='executed':row.update(disposition='executed-reviewed',execution={})
            elif fault=='advisory':row['disposition']='advisory'
            bad['counts']=dict(Counter(r['disposition'] for r in bad['rows']))
            if fault=='counts':bad['counts']['absent-operand']+=1
            with self.subTest(fault=fault),self.assertRaises(ValueError):pad.correct(bad)

    def test_reverted_absence_or_removed_review_rejected(self):
        good=pad.correct(self.baseline())
        for fault in ('missing','changed-definition','absence','reason'):
            bad=deepcopy(good);row=next(r for r in bad['rows'] if r['id']==pad.ROW['id'])
            if fault=='missing':bad.pop('pad_scope_review')
            elif fault=='changed-definition':bad['pad_scope_review']['definition']='pad.dg'
            elif fault=='absence':row['disposition']='absent-operand'
            else:row['reason']='no drawn pads'
            bad['counts']=dict(Counter(r['disposition'] for r in bad['rows']))
            with self.subTest(fault=fault),self.assertRaises(ValueError):pad.validate(bad)

    def test_application_and_export_require_the_reopened_mask_obligation(self):
        with TemporaryDirectory() as td:
            root=Path(td);_,result,report=app.fixture(root)
            rules.evaluate(report,report['gds_sha256'],report['checkpoint_sha256'],report['top'],report['platform_fingerprint'],report['policy'])
            export(result,root,root/'reviewed.zip')
            for fault in ('missing','absence'):
                bad=deepcopy(report)
                if fault=='missing':bad['ledger'].pop('pad_scope_review')
                else:
                    next(r for r in bad['ledger']['rows'] if r['id']==pad.ROW['id'])['disposition']='absent-operand'
                    bad['ledger']['counts']=dict(Counter(r['disposition'] for r in bad['ledger']['rows']))
                    bad['coverage']['counts']=bad['ledger']['counts']
                damaged=deepcopy(result);app.save_report(root,damaged,bad)
                target=root/(fault+'.zip')
                with self.subTest(fault=fault),self.assertRaisesRegex(ValueError,'hugePad'):
                    export(damaged,root,target)
                self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
