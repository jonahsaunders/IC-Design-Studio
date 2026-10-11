from copy import deepcopy
import unittest
from scripts.sky130_rule_execution import bind


def reports():
    # The independent fixture enumerates every published n/psd and HVTP row,
    # including the manual-merge requirement and an unrelated open rule.
    rules=['n/ psd.'+s for s in ('1','2','3','5a','5b','6','7','8','9','10a','10b','11')]+['hvtp.'+str(i) for i in range(1,7)]
    checks=['n/psd.'+s+'.'+t for s in ('1','2','5a','5b','6','7','8','9','11') for t in ('n','p')]
    checks+=['n/psd.10a','n/psd.10b']+['hvtp.'+str(i) for i in range(1,7)]
    checks+=['profile.'+str(pair) for pair in ((64,18),(19,44),(124,20),(124,21),(18,20),(11,44),
             (75,20),(80,20),(125,44),(125,20),(86,20),(79,20),(81,2))]
    checks+=['profile.active_overlap','profile.active_well_straddle']
    review=dict(gds_sha256='a'*64,checker_sha256='b'*64,rows=[dict(rule=r,disposition='execution-review-required') for r in rules+['poly.1a']])
    raw=dict(gds_sha256='a'*64,checker_sha256='c'*64,status='PASS',violations=0,checks=[dict(rule=r,violations=0) for r in checks])
    return review,raw


class RuleExecutionTests(unittest.TestCase):
    def test_only_reviewed_requirements_are_bound(self):
        review,raw=reports();original=deepcopy(review);result=bind(review,raw)
        self.assertEqual(review,original)
        self.assertEqual(result['counts'],{'executed-reviewed':18,'execution-review-required':1})
        self.assertFalse(result['qualified']);self.assertFalse(result['chunk_complete'])

    def test_failed_profile_and_hidden_marker_are_rejected(self):
        for rule in ('n/psd.5a.n','n/psd.6.p','hvtp.3','profile.active_overlap'):
            review,raw=reports();next(r for r in raw['checks'] if r['rule']==rule)['violations']=1
            with self.subTest(rule=rule),self.assertRaisesRegex(ValueError,'profile'):bind(review,raw)

    def test_omitted_or_duplicated_checks_are_rejected(self):
        for duplicate in (False,True):
            review,raw=reports()
            if duplicate:raw['checks'].append(deepcopy(raw['checks'][0]))
            else:raw['checks'].pop(0)
            with self.subTest(duplicate=duplicate),self.assertRaises(ValueError):bind(review,raw)

    def test_layout_change_cannot_reuse_pass(self):
        review,raw=reports();raw['gds_sha256']='d'*64
        with self.assertRaisesRegex(ValueError,'different submitted'):bind(review,raw)

    def test_omitted_profile_guard_cannot_reuse_pass(self):
        review,raw=reports();raw['checks']=[r for r in raw['checks'] if r['rule']!='profile.(75, 20)']
        with self.assertRaisesRegex(ValueError,'profile guard'):bind(review,raw)

    def test_changed_manual_inventory_requires_review(self):
        for change in ('remove','duplicate','disposition'):
            review,raw=reports()
            if change=='remove':review['rows'].pop(0)
            elif change=='duplicate':review['rows'].append(deepcopy(review['rows'][0]))
            else:review['rows'][0]['disposition']='advisory'
            with self.subTest(change=change),self.assertRaises(ValueError):bind(review,raw)


if __name__=='__main__':unittest.main()
