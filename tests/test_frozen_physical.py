"""Exact-candidate physical acceptance must not depend on UI source diagnostics."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from icstudio import build_identity
from icstudio.model import file_digest
from scripts import verify_frozen_physical as gate

COMMIT = 'a' * 40


def report(digest='b' * 64):
    return dict(status='passed', frozen=True, executable_sha256=digest,
                build=dict(commit=COMMIT, dirty=False, frozen=True))


class PhysicalCandidateTests(unittest.TestCase):
    def test_successful_head_survives_unrelated_source_status_timeout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'.git').mkdir()
            module = root/'icstudio/build_identity.py'

            def git(command, **kwargs):
                if command[1] == 'status':
                    raise subprocess.TimeoutExpired(command, 3)
                if command[1:3] == ['rev-parse', '--abbrev-ref']:
                    return 'candidate\n'
                return COMMIT+'\n'

            with patch.object(build_identity, '__file__', str(module)), \
                    patch('subprocess.check_output', side_effect=git) as calls:
                # This was the host comparison used by the failed installed job:
                # a later status failure discards the successfully read HEAD.
                self.assertEqual(build_identity.identity()['commit'], 'unknown')
                calls.reset_mock()
                self.assertEqual(gate.candidate_commit(COMMIT, root), COMMIT)
                self.assertEqual(calls.call_count, 1)
                self.assertEqual(calls.call_args.args[0], ['git', 'rev-parse', 'HEAD'])
                self.assertEqual(calls.call_args.kwargs['timeout'], 3)

    def test_candidate_is_explicit_and_full_before_git_or_gui(self):
        for value in ('', 'unknown', 'a'*39, 'A'*40, COMMIT+'\n', None):
            with self.subTest(value=value), patch.object(gate.subprocess, 'check_output') as git:
                with self.assertRaisesRegex(ValueError, '40-character'):
                    gate.candidate_commit(value)
                git.assert_not_called()

    def test_wrong_head_and_failed_git_never_become_a_pass(self):
        with patch.object(gate.subprocess, 'check_output', return_value='c'*40):
            with self.assertRaisesRegex(ValueError, 'differs from candidate'):
                gate.candidate_commit(COMMIT)
        for failure in (OSError('unavailable'), subprocess.TimeoutExpired('git', 3),
                        subprocess.CalledProcessError(1, 'git')):
            with self.subTest(error=failure), patch.object(gate.subprocess, 'check_output', side_effect=failure):
                with self.assertRaises(type(failure)):
                    gate.candidate_commit(COMMIT)

    def test_ambient_git_configuration_cannot_redirect_the_candidate(self):
        with patch.dict(os.environ, {'GIT_DIR': '/unrelated', 'GIT_WORK_TREE': '/other', 'KEEP_ME': 'yes'}), \
                patch.object(gate.subprocess, 'check_output', return_value=COMMIT) as git:
            gate.candidate_commit(COMMIT)
        env = git.call_args.kwargs['env']
        self.assertFalse(any(k.upper().startswith('GIT_') for k in env))
        self.assertEqual(env['KEEP_ME'], 'yes')

    def test_report_requires_clean_frozen_matching_build_and_executable(self):
        good = report()
        gate.validate_report(good, COMMIT, 'b'*64)
        changes = [('status', 'failed'), ('frozen', False), ('executable_sha256', 'c'*64),
                   ('build.commit', 'c'*40), ('build.commit', 'unknown'),
                   ('build.dirty', True), ('build.dirty', None), ('build.dirty', 0),
                   ('build.frozen', False), ('build.frozen', 1)]
        for field, value in changes:
            bad = copy.deepcopy(good)
            target = bad['build'] if field.startswith('build.') else bad
            target[field.split('.')[-1]] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                gate.validate_report(bad, COMMIT, 'b'*64)
        for key in ('status', 'frozen', 'build', 'executable_sha256'):
            bad = copy.deepcopy(good)
            del bad[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                gate.validate_report(bad, COMMIT, 'b'*64)

    def test_cli_and_required_workflow_name_the_exact_candidate(self):
        with patch.object(gate, 'verify') as verify:
            gate.main(['--executable', 'app', '--pdk', 'pdk', '--out', 'out', '--expected-commit', COMMIT])
        verify.assert_called_once_with(Path('app'), Path('pdk'), Path('out'), COMMIT)
        workflow = (gate.ROOT/'.github/workflows/build-desktop.yml').read_text()
        command = next(line for line in workflow.splitlines() if 'run: python scripts/verify_frozen_physical.py' in line)
        self.assertIn('--expected-commit "${{ github.sha }}"', command)
        windows = (gate.ROOT/'scripts/verify_windows.ps1').read_text()
        command = next(line for line in windows.splitlines() if line.startswith('python scripts/verify_frozen_physical.py'))
        self.assertIn('--expected-commit "$commit"', command)
        from scripts.ci_feedback import UNIT_MODULES
        self.assertEqual(UNIT_MODULES.count('test_frozen_physical'), 1)


class PhysicalInvocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.exe = self.root/'app'
        self.exe.write_bytes(b'fixture executable')
        self.pdk = self.root/'pdk'
        self.pdk.mkdir()
        self.out = self.root/'evidence'

    def launch(self, command, **kwargs):
        self.assertEqual(command, [str(self.exe), '--physical-acceptance', '--managed',
                                  '--pdk', str(self.pdk), '--out', str(self.out/'probe')])
        self.assertEqual(kwargs['timeout'], 1200)
        self.assertIs(kwargs['check'], True)
        self.assertEqual(kwargs['env']['QT_QPA_PLATFORM'], 'offscreen')
        (self.out/'probe').mkdir()
        (self.out/'probe/report.json').write_text(json.dumps(report(file_digest(self.exe))))

    def test_complete_invocation_checks_candidate_before_and_after_and_retains_identity(self):
        with patch.object(gate, 'candidate_commit', return_value=COMMIT) as candidate, \
                patch.object(gate.subprocess, 'run', side_effect=self.launch):
            result = gate.verify(self.exe, self.pdk, self.out, COMMIT)
        self.assertEqual(candidate.call_count, 2)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['expected_commit'], COMMIT)
        self.assertEqual(result['report_sha256'], file_digest(self.out/'probe/report.json'))
        self.assertEqual(json.loads((self.out/'acceptance.json').read_text()), result)

    def test_old_output_cannot_be_reused(self):
        self.out.mkdir()
        with patch.object(gate, 'candidate_commit', return_value=COMMIT), \
                patch.object(gate.subprocess, 'run') as launch:
            with self.assertRaises(FileExistsError):
                gate.verify(self.exe, self.pdk, self.out, COMMIT)
            launch.assert_not_called()

    def test_executable_mutation_fails_even_when_report_names_the_original(self):
        def mutate(command, **kwargs):
            self.launch(command, **kwargs)
            self.exe.write_bytes(b'changed executable')
        with patch.object(gate, 'candidate_commit', return_value=COMMIT), \
                patch.object(gate.subprocess, 'run', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'changed during'):
                gate.verify(self.exe, self.pdk, self.out, COMMIT)
        self.assertEqual(json.loads((self.out/'acceptance.json').read_text())['status'], 'failed')

    def test_checkout_change_after_execution_fails(self):
        with patch.object(gate, 'candidate_commit', side_effect=[COMMIT, ValueError('HEAD changed')]), \
                patch.object(gate.subprocess, 'run', side_effect=self.launch):
            with self.assertRaisesRegex(ValueError, 'HEAD changed'):
                gate.verify(self.exe, self.pdk, self.out, COMMIT)
        saved = json.loads((self.out/'acceptance.json').read_text())
        self.assertEqual(saved['status'], 'failed')
        self.assertIn('HEAD changed', saved['error'])

    def test_failed_missing_or_wrong_child_report_remains_failed(self):
        def wrong_report(command, **kwargs):
            self.launch(command, **kwargs)
            saved = report(file_digest(self.exe))
            saved['build']['commit'] = 'd'*40
            (self.out/'probe/report.json').write_text(json.dumps(saved))
        failures = [subprocess.CalledProcessError(1, 'app'), subprocess.TimeoutExpired('app', 1200),
                    lambda *a, **kw: None, wrong_report]
        for index, failure in enumerate(failures):
            self.out = self.root/str(index)
            with self.subTest(index=index), patch.object(gate, 'candidate_commit', return_value=COMMIT), \
                    patch.object(gate.subprocess, 'run', side_effect=failure):
                with self.assertRaises((subprocess.SubprocessError, OSError, ValueError)):
                    gate.verify(self.exe, self.pdk, self.out, COMMIT)
            saved = json.loads((self.out/'acceptance.json').read_text())
            self.assertEqual(saved['status'], 'failed')
            self.assertIn('error', saved)


if __name__ == '__main__':
    unittest.main()
