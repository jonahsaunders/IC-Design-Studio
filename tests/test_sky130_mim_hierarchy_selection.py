"""Development selection guards; no native qualification is implied."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from scripts import qualify_sky130_mim_hierarchy_electrical as runner
from scripts import audit_sky130_mim_hierarchy_electrical as auditor
class Selection(unittest.TestCase):
    def test_all_twenty_development_cases_still_cannot_claim_acceptance(self):
        names=[c['name'] for c in runner.selected()]
        report=dict(pilot=False,development=True,full_declared_cases=names,
                    selected_cases=names,cases=[dict(name=n) for n in names])
        self.assertEqual(auditor.selection_scope(report),dict(full_declared_selection=True,
                         development=True,source_integration_acceptance=False))
        report['development']=False
        self.assertTrue(auditor.selection_scope(report)['source_integration_acceptance'])
    def test_default_pilot_and_single_dispatch(self):
        full=runner.selected();self.assertEqual(len(full),20)
        self.assertEqual(runner.resolve_selection(),full)
        self.assertEqual(len(runner.resolve_selection(pilot=True)),2)
        chosen=runner.resolve_selection(development=True,names=[full[-1]['name']]);seen=[]
        with ThreadPoolExecutor(max_workers=1) as pool:
            futures=runner.submit_cases(pool,lambda c:seen.append(c['name']),chosen)
            for future in futures: future.result()
        self.assertEqual(seen,[full[-1]['name']])
    def test_reject_selection_errors(self):
        good=runner.selected()[0]['name']
        for kw in (dict(names=[good]),dict(development=True),dict(development=True,names=[]),dict(development=True,names=[good,good]),dict(development=True,names=['unknown']),dict(pilot=True,development=True,names=[good])):
            with self.subTest(kw=kw),self.assertRaises(ValueError):runner.resolve_selection(**kw)
    def test_auditor_rejects_incomplete_and_mislabeled(self):
        full=runner.selected(); names=[c['name'] for c in full];one=names[0]
        report=dict(pilot=False,development=True,full_declared_cases=names,selected_cases=[one],cases=[dict(name=one)])
        self.assertEqual(len(auditor.case_inventory(report)[1]),1)
        for patch in (dict(development=False),dict(cases=[]),dict(cases=[dict(name=one),dict(name=one)]),dict(selected_cases=[one,one]),dict(selected_cases=['unknown']),dict(full_declared_cases=names[:-1]),dict(pilot=True)):
            with self.subTest(patch=patch),self.assertRaises((ValueError,KeyError)):
                auditor.case_inventory(dict(report,**patch))
        complete=dict(report,development=False,selected_cases=names,cases=[dict(name=n) for n in names])
        self.assertEqual(len(auditor.case_inventory(complete)[1]),20)
if __name__=='__main__':unittest.main()
