"""Independent-receipt and release-routing controls, not native evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_installed_metal_parallel as check


class AggregateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.gr=self.root/'gui';self.er=self.root/'electrical'
        (self.gr/'probe').mkdir(parents=True);self.er.mkdir()
        self.commit='a'*40;self.nonce='b'*32
        self.gv=dict(schema=1,status='PASS',gate='metal-parallel-installed-gui-queued-layout',
            counts=copy.deepcopy(check.GUI_COUNTS),expected_commit=self.commit,execution_id=self.nonce,
            qualified=False,release_ready=False,full_family=False)
        self.invocation=dict(expected_commit=self.commit,execution_id=self.nonce)
        self.binding=dict(mode='installed',expected_commit=self.commit,execution_id=self.nonce,
            gui_root=str(self.gr/'probe'),supplied_root=str(self.gr))
        self.eq=dict(schema=1,status='PASS',mode='installed',expected_commit=self.commit,pilot=False)
        self.ea=dict(schema=1,status='PASS',mode='installed',expected_commit=self.commit,gui_execution_id=self.nonce,
            installed_electrical_acceptance=True,counts=copy.deepcopy(check.COUNTS),**{k:False for k in check.SCOPE_FIELDS})
        for p in (self.gr/'probe/report.json',self.gr/'probe/files.json',self.er/'manifest.json'):self.write(p,{'fixture':True})
        self.seal()
        for target,name,fn in ((check.common,'git_blob',lambda commit,name:(check.ROOT/name).read_bytes()),
                               (check,'reaudit',lambda root:copy.deepcopy(self.ea))):
            patched=patch.object(target,name,side_effect=fn);patched.start();self.addCleanup(patched.stop)

    @staticmethod
    def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

    def seal(self):
        self.gv.update(report_sha256=check.sha(self.gr/'probe/report.json'),files_sha256=check.sha(self.gr/'probe/files.json'))
        self.write(self.gr/'verification.json',self.gv);self.write(self.gr/'invocation.json',self.invocation)
        for field,name in (('report_sha256','probe/report.json'),('files_sha256','probe/files.json'),
                ('verification_sha256','verification.json'),('invocation_sha256','invocation.json')):
            self.binding[field]=check.sha(self.gr/name)
        self.write(self.er/'inputs.json',self.binding);self.write(self.er/'qualification.json',self.eq)
        self.ea.update(qualification_sha256=check.sha(self.er/'qualification.json'),inputs_sha256=check.sha(self.er/'inputs.json'),
            manifest_sha256=check.sha(self.er/'manifest.json'))
        self.write(self.er/'audit.json',self.ea)

    def verify(self):return check.verify(self.gr,self.er,self.commit)

    def test_matching_selected_receipts_keep_finite_scope(self):
        value=self.verify();self.assertTrue(value['installed_selected_workflow_acceptance'])
        self.assertTrue(all(value[k] is False for k in check.SCOPE_FIELDS))
        self.assertEqual(value['electrical_counts']['electrical_analyses'],60)

    def test_rehashed_semantic_substitutions_reject(self):
        for obj,key,value in ((self.gv,'expected_commit','c'*40),(self.invocation,'execution_id','d'*32),
            (self.gv['counts'],'queued_jobs',42),(self.gv['counts'],'eco_transitions',19),
            (self.gv['counts'],'late_lock_rejections',4),(self.gv,'full_family',True),
            (self.binding,'mode','source-pilot'),(self.binding,'gui_root',str(self.er)),
            (self.binding,'supplied_root',str(self.er)),(self.eq,'pilot',True),(self.eq,'status','FAIL'),
            (self.eq,'expected_commit','e'*40),(self.ea,'mode','source-pilot'),
            (self.ea,'installed_electrical_acceptance',False),(self.ea,'gui_execution_id','f'*32),
            (self.ea['counts'],'electrical_contexts',29),(self.ea['counts'],'electrical_analyses',59),
            (self.ea['counts'],'electrical_path_samples',3869),(self.ea,'signoff',True)):
            with self.subTest(key=key,value=value):
                old=obj[key];obj[key]=value;self.seal()
                with self.assertRaises(ValueError):self.verify()
                obj[key]=old;self.seal()

    def test_saved_receipt_never_replaces_independent_raw_readback(self):
        with patch.object(check,'reaudit',side_effect=ValueError('Raw current differs')):
            with self.assertRaisesRegex(ValueError,'Raw current'):self.verify()
        self.write(self.er/'audit.json',{**self.ea,'substituted':True})
        with self.assertRaisesRegex(ValueError,'substituted'):self.verify()

    def test_changed_gui_input_or_missing_audit_reject(self):
        self.write(self.gr/'probe/report.json',{'changed':True})
        with self.assertRaisesRegex(ValueError,'receipt changed'):self.verify()
        self.seal();(self.er/'audit.json').unlink()
        with self.assertRaises(FileNotFoundError):self.verify()

    def test_wrong_candidate_or_overlapping_roots_reject(self):
        with patch.object(check.common,'git_blob',return_value=b'other candidate'):
            with self.assertRaisesRegex(ValueError,'selected candidate'):self.verify()
        for root in (self.gr,self.gr/'probe',self.gr.parent):
            with self.assertRaisesRegex(ValueError,'disjoint'):check.verify(self.gr,root,self.commit)
        with self.assertRaisesRegex(ValueError,'exact candidate'):check.verify(self.gr,self.er,'experimental')


class ReleaseRoutingTests(unittest.TestCase):
    def test_existing_gates_and_arrays_precede_release_completion_on_both_hosts(self):
        workflow=(check.ROOT/'.github/workflows/build-desktop.yml').read_text()
        windows=(check.ROOT/'scripts/verify_windows.ps1').read_text()
        for text,end in ((workflow,'      - name: Assemble and execute release archives'),
                (windows,"Wait-Checked (Join-Path $install 'unins000.exe')")):
            ordered=[text.index('scripts/'+name) for name in ('verify_frozen_mim.py','verify_installed_mim.py',
                'verify_frozen_metal_resistors.py','verify_installed_metal_resistors.py',
                'verify_frozen_metal_parallel.py','qualify_installed_metal_parallel.py','verify_installed_metal_parallel.py')]
            self.assertEqual(ordered,sorted(ordered));self.assertLess(ordered[-1],text.index(end))
            self.assertNotIn('continue-on-error:',text)
        self.assertIn('metal_parallel=(Get-Content',windows)
        for name in ('build/frozen-metal-parallel-evidence','build/frozen-metal-parallel-electrical-evidence',
                'build/frozen-metal-parallel-workflow-evidence/acceptance.json','build/windows-evidence/metal-parallel-acceptance.json'):
            self.assertIn(name,workflow)

    def test_source_feedback_is_bounded_and_full_discovery_remains(self):
        from scripts.ci_feedback import UNIT_MODULES
        self.assertIn('test_metal_resistor_parallel_desktop_probe.ProbeBoundaries',UNIT_MODULES)
        self.assertNotIn('test_metal_resistor_parallel_desktop_probe',UNIT_MODULES)
        self.assertIn('python -m unittest discover -s tests -v',(check.ROOT/'.github/workflows/build-desktop.yml').read_text())


if __name__=='__main__':unittest.main()
