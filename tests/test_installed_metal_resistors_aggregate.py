"""Receipt substitution controls; fixtures are not native acceptance evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_installed_metal_resistors as check


class AggregateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.gr, self.er = self.root/'gui', self.root/'electrical'
        (self.gr/'probe').mkdir(parents=True); self.er.mkdir()
        self.commit, self.nonce = 'a'*40, 'b'*32
        self.gv = dict(schema=1, status='PASS', gate='metal-resistor-installed-gui-queued-layout',
            counts=copy.deepcopy(check.GUI_COUNTS), expected_commit=self.commit, execution_id=self.nonce,
            qualified=False, release_ready=False, full_family=False)
        self.invocation = dict(expected_commit=self.commit, execution_id=self.nonce)
        self.binding = dict(mode='installed', expected_commit=self.commit, execution_id=self.nonce,
                            gui_root=str(self.gr/'probe'), supplied_root=str(self.gr))
        self.eq = dict(schema=1, status='PASS', mode='installed', expected_commit=self.commit, pilot=False)
        self.ea = dict(schema=1, status='PASS', mode='installed', expected_commit=self.commit,
            gui_execution_id=self.nonce, installed_electrical_acceptance=True, counts=copy.deepcopy(check.COUNTS),
            **{k:False for k in check.SCOPE_FIELDS})
        self.write(self.gr/'probe/report.json', {'fixture':True})
        self.write(self.gr/'probe/files.json', {'fixture':True})
        self.write(self.er/'manifest.json', {'fixture':True})
        self.seal()
        for target, name, effect in (
            (check.common, 'git_blob', lambda commit,name:(check.ROOT/name).read_bytes()),
            (check, 'reaudit', lambda root:copy.deepcopy(self.ea)),
        ):
            mocked = patch.object(target, name, side_effect=effect)
            mocked.start(); self.addCleanup(mocked.stop)

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')

    def seal(self):
        self.gv.update(report_sha256=check.sha(self.gr/'probe/report.json'),
                       files_sha256=check.sha(self.gr/'probe/files.json'))
        self.write(self.gr/'verification.json', self.gv)
        self.write(self.gr/'invocation.json', self.invocation)
        for field, name in (('report_sha256','probe/report.json'), ('files_sha256','probe/files.json'),
                            ('verification_sha256','verification.json'), ('invocation_sha256','invocation.json')):
            self.binding[field] = check.sha(self.gr/name)
        self.write(self.er/'inputs.json', self.binding)
        self.write(self.er/'qualification.json', self.eq)
        self.ea.update(qualification_sha256=check.sha(self.er/'qualification.json'),
                       inputs_sha256=check.sha(self.er/'inputs.json'), manifest_sha256=check.sha(self.er/'manifest.json'))
        self.write(self.er/'audit.json', self.ea)

    def verify(self):
        return check.verify(self.gr, self.er, self.commit)

    def test_matching_receipts_preserve_finite_scope(self):
        result = self.verify()
        self.assertTrue(result['installed_selected_workflow_acceptance'])
        self.assertTrue(all(result[k] is False for k in check.SCOPE_FIELDS))
        self.assertEqual(result['electrical_counts'], check.COUNTS)

    def test_rehashed_semantic_substitutions_reject(self):
        for obj, key, value in (
            (self.gv, 'expected_commit', 'c'*40), (self.invocation, 'execution_id', 'd'*32),
            (self.gv['counts'], 'queued_jobs', 42), (self.gv, 'full_family', True),
            (self.binding, 'mode', 'source-pilot'), (self.binding, 'gui_root', str(self.er)),
            (self.binding, 'supplied_root', str(self.er)), (self.eq, 'pilot', True),
            (self.eq, 'status', 'FAIL'), (self.eq, 'expected_commit', 'e'*40),
            (self.ea, 'mode', 'source-pilot'), (self.ea, 'installed_electrical_acceptance', False),
            (self.ea, 'gui_execution_id', 'f'*32), (self.ea['counts'], 'contexts', 4),
            (self.ea['counts'], 'fresh_gui_native_inputs', 23), (self.ea, 'signoff', True),
        ):
            with self.subTest(key=key, value=value):
                old = obj[key]; obj[key] = value; self.seal()
                with self.assertRaises(ValueError): self.verify()
                obj[key] = old; self.seal()

    def test_stored_audit_cannot_replace_fresh_readback(self):
        changed = copy.deepcopy(self.ea); changed['extra'] = 'forged'
        self.write(self.er/'audit.json', changed)
        with self.assertRaisesRegex(ValueError, 'substituted'): self.verify()

    def test_fresh_raw_readback_failure_propagates(self):
        with patch.object(check, 'reaudit', side_effect=ValueError('Raw KCL differs')):
            with self.assertRaisesRegex(ValueError, 'Raw KCL'): self.verify()

    def test_changed_gui_receipt_rejects(self):
        self.write(self.gr/'probe/report.json', {'fixture':'changed'})
        with self.assertRaisesRegex(ValueError, 'receipt changed'): self.verify()

    def test_missing_audit_rejects(self):
        (self.er/'audit.json').unlink()
        with self.assertRaises(FileNotFoundError): self.verify()

    def test_unselected_checker_rejects(self):
        with patch.object(check.common, 'git_blob', return_value=b'wrong candidate'):
            with self.assertRaisesRegex(ValueError, 'selected candidate'): self.verify()

    def test_same_or_nested_roots_reject(self):
        for path in (self.gr, self.gr/'probe'):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'disjoint'):
                check.verify(self.gr, path, self.commit)


class ReleaseRoutingTests(unittest.TestCase):
    def test_both_hosts_run_selected_acceptance_before_release_completion(self):
        workflow = (check.ROOT/'.github/workflows/build-desktop.yml').read_text()
        windows = (check.ROOT/'scripts/verify_windows.ps1').read_text()
        for text, completion in ((workflow, '      - name: Assemble and execute release archives'),
                                 (windows, "Wait-Checked (Join-Path $install 'unins000.exe')")):
            ordered = [text.index('scripts/'+name) for name in (
                'verify_frozen_mim.py', 'verify_installed_mim.py',
                'verify_frozen_metal_resistors.py', 'qualify_installed_sky130_metal_resistors.py',
                'verify_installed_metal_resistors.py')]
            self.assertEqual(ordered, sorted(ordered))
            self.assertLess(ordered[-1], text.index(completion))
            self.assertNotIn('continue-on-error:', text)
        self.assertIn('metal_resistors=(Get-Content', windows)
        for path in ('build/frozen-metal-resistor-evidence', 'build/frozen-metal-resistor-electrical-evidence',
                     'build/frozen-metal-resistor-workflow-evidence/acceptance.json',
                     'build/windows-evidence/metal-resistors-acceptance.json'):
            self.assertIn(path, workflow)

    def test_daily_feedback_uses_cheap_probe_boundaries_full_discovery_stays(self):
        from scripts.ci_feedback import UNIT_MODULES
        self.assertIn('test_metal_resistor_desktop_probe.ProbeBoundaries', UNIT_MODULES)
        self.assertNotIn('test_metal_resistor_desktop_probe', UNIT_MODULES)
        workflow = (check.ROOT/'.github/workflows/build-desktop.yml').read_text()
        self.assertIn('python -m unittest discover -s tests -v', workflow)


if __name__ == '__main__':
    unittest.main()
