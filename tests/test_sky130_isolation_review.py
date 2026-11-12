import copy
import unittest

from scripts import sky130_isolation_review as r
from tests import test_sky130_isolation_policy as fixtures


class IsolationReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory=r.previous.read(r.INVENTORY)
        cls.rows,cls.voltage=r.preceding('counter',cls.inventory)

    def result(self, enabled=False):
        layout,_=fixtures.IsolationPolicyTests().fixture()
        return r.policy.check(layout,{'nfet_in_dnwell':enabled})

    def test_reconstructs_all_three_preceding_ledgers(self):
        for case in ('counter','uart','apb'):
            rows,previous=r.preceding(case,self.inventory)
            self.assertEqual(len(rows),601)
            self.assertEqual(previous['periphery_counts']['execution-review-required'],10)
            self.assertEqual(sum(row['disposition']=='execution-review-required' for row in rows),10)

    def test_explicit_bulk_choice_changes_only_x29(self):
        result=self.result();updated=r.reconcile(self.rows,self.inventory,result)
        changes=[row for old,row in zip(self.rows,updated) if old!=row]
        self.assertEqual(len(changes),1);self.assertEqual(changes[0]['id'],r.policy.RULE_ID)
        self.assertEqual(changes[0]['disposition'],'declared-option-not-required')
        self.assertEqual(changes[0]['isolation_check']['status'],'NOT_REQUESTED')

    def test_enabled_failed_measurement_is_never_covered(self):
        updated=r.reconcile(self.rows,self.inventory,self.result(True))
        row=next(row for row in updated if row['id']==r.policy.RULE_ID)
        self.assertEqual(row['disposition'],'execution-failed')

    def test_missing_duplicate_or_changed_unrelated_row_rejected(self):
        for fault in ('missing','duplicate','changed','reordered'):
            rows=copy.deepcopy(self.rows)
            if fault=='missing':rows.pop(0)
            elif fault=='duplicate':rows[0]=rows[1]
            elif fault=='changed':rows[0]['description']='changed'
            else:rows[0],rows[1]=rows[1],rows[0]
            with self.assertRaises(ValueError):r.reconcile(rows,self.inventory,self.result())

    def test_decision_cannot_be_promoted_or_switch_changed(self):
        for field,value in (('status','PASS'),('disposition','executed-reviewed'),('enforced',True),
                            ('options',{'nfet_in_dnwell':True}),('measured_noncontained_gates',0)):
            result=self.result();result[field]=value
            with self.assertRaises(ValueError):r.reconcile(self.rows,self.inventory,result)

    def test_second_reconciliation_is_rejected(self):
        rows=r.reconcile(self.rows,self.inventory,self.result())
        with self.assertRaises(ValueError):r.reconcile(rows,self.inventory,self.result())


if __name__=='__main__':unittest.main()
