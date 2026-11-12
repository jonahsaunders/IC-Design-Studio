import json
import os
from pathlib import Path
import hashlib
import tempfile
import unittest
from scripts import windows_failure_summary as summary

class WindowsFailureSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def get(self):return json.loads(summary.collect(self.root,'a'*40))
    def write(self,name,value):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value));return p
    def test_missing_reports_are_explicit_not_success(self):
        d=self.get();self.assertFalse(d['installed_acceptance']);self.assertTrue(d['diagnostic_only']);self.assertFalse(d['reports']);self.assertGreater(len(d['omissions']),1)
    def test_exact_candidate_required(self):
        for sha in ('main','a'*39,'z'*40):
            with self.assertRaises(ValueError):summary.collect(self.root,sha)
    def test_projection_excludes_projects_and_unknown_build_fields(self):
        self.write('wrapper-error.json',{'message':'known error','project':{'secret':'omit'},'build':{'commit':'a'*40,'token':'omit'}})
        p=self.get()['reports'][0]['projection'];self.assertNotIn('project',p);self.assertEqual(p['build'],{'commit':'a'*40})
    def test_oversize_json_omitted_without_parsing(self):
        (self.root/'wrapper-error.json').write_bytes(b'x'*(summary.MAX_INPUT+1));d=self.get();self.assertFalse(d['reports']);self.assertIn('oversize',d['omissions'][0]['reason'])
    def test_tail_bounded_and_not_claimed_full_hash(self):
        p=self.root/'verify-windows-transcript.txt';p.write_bytes(b'x'*(summary.MAX_INPUT+7));r=self.get()['reports'][0]
        self.assertTrue(r['truncated']);self.assertFalse(r['full_source_hash']);self.assertEqual(r['retained_offset'],7);self.assertEqual(len(r['tail']),summary.MAX_INPUT)
    def test_standard_credentials_and_url_query_redacted(self):
        self.write('wrapper-error.json',{'message':'token=abcdef https://example.test/a?sig=foo ghp_abcdef'})
        text=json.dumps(self.get());self.assertNotIn('abcdef',text);self.assertNotIn('sig=foo',text)
    def test_nested_allowlisted_fields_are_omitted_not_serialized(self):
        self.write('wrapper-error.json', {
            'message': {'token': 'nested-message'},
            'errors': [{'secret': 'nested-error'}],
            'status': ['nested-status'],
            'build': {'commit': {'private': 'nested-build'}, 'dirty': False},
        })
        row=self.get()['reports'][0]
        self.assertEqual(row['projection'], {'build': {'dirty': False}})
        self.assertEqual(set(row['omitted_nonscalar_fields']), {'message','errors','status','build.commit'})
        self.assertNotIn('nested-',json.dumps(row))
    def test_quoted_credential_keys_and_multispace_values_redacted(self):
        self.write('wrapper-error.json', {'message': '''{"token": "multi word private", 'password': 'another private', "api-key": "last private"}'''})
        text=json.dumps(self.get())
        self.assertNotIn('private',text);self.assertEqual(text.count('[REDACTED]'),3)
    def test_build_strings_redacted_and_nonfinite_scalar_omitted(self):
        self.write('wrapper-error.json', {'status': float('nan'), 'build': {'version': 'secret=hidden'}})
        row=self.get()['reports'][0]
        self.assertNotIn('hidden',json.dumps(row));self.assertEqual(row['omitted_nonscalar_fields'],['status'])
    def test_pw2dn_child_failure_retained_without_command_or_environment(self):
        self.write('pw2dn/reference-invocation.json', {'status':'FAIL','returncode':1,'command':['secret command'],'environment':{'secret':'omit'}})
        self.write('pw2dn/native-references/failure.json', {'status':'FAIL','error':'ValueError: exact failure','seconds':4.0})
        (self.root/'pw2dn/reference-launcher.log').write_text('Traceback\nValueError: exact failure\n')
        rows={r['path']:r for r in self.get()['reports']}
        self.assertEqual(rows['pw2dn/reference-invocation.json']['projection'],{'status':'FAIL','returncode':1})
        self.assertEqual(rows['pw2dn/native-references/failure.json']['projection']['error'],'ValueError: exact failure')
        self.assertIn('Traceback',rows['pw2dn/reference-launcher.log']['tail'])
    def test_invalid_utf8_transcript_retained_bounded(self):
        (self.root/'verify-windows-transcript.txt').write_bytes(b'\xff\x00oops');self.assertTrue(self.get()['reports'])
    def test_no_recursive_read(self):
        self.write('Installed App With Spaces/private.json',{'token':'never-read'});self.assertFalse(self.get()['reports'])
    def test_symlink_rejected(self):
        target=self.write('external.json',{'message':'must-not-read'})
        try:(self.root/'wrapper-error.json').symlink_to(target)
        except OSError as exc:
            if os.name=='nt' and getattr(exc,'winerror',None) in (5,50,1314):self.skipTest('Windows symlink permission unavailable')
            raise
        self.assertFalse(self.get()['reports']);self.assertIn('linked',self.get()['omissions'][0]['reason'])
    def test_maximum_size_unicode_still_below_budget(self):
        for name in summary.REPORTS:self.write(name,{'message':'é'*30000})
        (self.root/'verify-windows-transcript.txt').write_bytes(b'\xff'*summary.MAX_INPUT)
        self.assertLess(len(summary.collect(self.root,'a'*40)),summary.MAX_OUTPUT)
    def test_workflow_keeps_verifier_and_preserves_original_failure(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(hashlib.sha256((root/'scripts/verify_windows.ps1').read_bytes()).hexdigest(),'b20c29f13cb1f2fdb14fb387e0b0acf3e25411093f348d2cd2ada7af6ad73ff8')
        flow=(root/'.github/workflows/build-desktop.yml').read_text()
        self.assertIn('throw $original',flow);self.assertIn('finally {',flow)
        self.assertIn("try {\n              New-Item -ItemType Directory -Force (Split-Path $transcript) -ErrorAction Stop",flow)
        self.assertEqual(flow.count('./scripts/verify_windows.ps1'),1)
        self.assertLess(flow.index('name: desktop-failure-summary-Windows'),flow.index('name: desktop-installed-checkpoint-'))
        self.assertIn("if: always() && runner.os == 'Windows'",flow)
        self.assertNotIn('continue-on-error:',flow)

if __name__=='__main__':unittest.main()
