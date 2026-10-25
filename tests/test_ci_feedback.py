"""Protect fast feedback, synthetic merge testing and exhaustive release routing."""
from pathlib import Path
import json
import os
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import ci_feedback
from scripts.ci_feedback import ROOT, UNIT_MODULES, check_syntax, source_identity, stages

EXHAUSTIVE = (
    'build-desktop', 'digital-runtime', 'physical-qualification', 'interoperability',
    'digital', 'vga-playground', 'analog-campaign-qualification',
    'ihp-inductor-qualification', 'reference-compatibility',
)


def workflow(name):
    return (ROOT / '.github/workflows' / (name + '.yml')).read_text(encoding='utf-8')


class FeedbackTests(unittest.TestCase):
    def test_failed_stage_and_source_mutation_retain_failed_evidence(self):
        for failure in ('stage', 'source'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / 'evidence'
                identities = [{'scripts/runner.py': 'a' * 64}, {'scripts/runner.py': 'b' * 64}]
                commands = [('controlled-failure', ['unused'])] if failure == 'stage' else []
                with patch.dict(os.environ, {'GITHUB_SHA': 'a' * 40}, clear=True), \
                     patch('sys.argv', ['ci_feedback.py', '--output', str(output)]), \
                     patch.object(ci_feedback.subprocess, 'check_output', return_value='a' * 40), \
                     patch.object(ci_feedback.subprocess, 'run', return_value=SimpleNamespace(returncode=1)), \
                     patch.object(ci_feedback, 'source_identity', side_effect=identities), \
                     patch.object(ci_feedback, 'check_syntax', return_value=1), \
                     patch.object(ci_feedback, 'stages', return_value=commands), patch('builtins.print'):
                    with self.assertRaises(RuntimeError):
                        ci_feedback.main()
                report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
                self.assertEqual(report['status'], 'failed')
                self.assertFalse(report['release_acceptance'])
                self.assertIn('first_failure_seconds', report)
                self.assertEqual(report['source_files_sha256'], identities[0])

    def test_new_runner_and_test_syntax_is_checked_before_long_suites(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('icstudio', 'scripts', 'tests'):
                (root / name).mkdir()
                (root / name / 'valid.py').write_text('x = 1\n')
            self.assertEqual(check_syntax(root), 3)
            before = source_identity(root)
            (root / 'scripts/broken.py').write_text('def broken(:\n')
            self.assertNotEqual(source_identity(root), before)
            with self.assertRaises(SyntaxError):
                check_syntax(root)

    def test_focused_modules_exist_and_release_contracts_remain_fast_checks(self):
        for name in UNIT_MODULES:
            self.assertTrue((ROOT / 'tests' / (name + '.py')).is_file(), name)
        commands = stages()
        self.assertEqual([name for name, _ in commands],
                         ['unit-contracts', 'release-contracts', 'menu-smoke', 'project-hub-smoke',
                          'metal-resistor-editor-smoke'])
        self.assertIn('test_pdk_qualification_matrix', UNIT_MODULES)
        self.assertIn('test_release_acceptance', UNIT_MODULES)

    def test_pr_and_merge_queue_use_default_synthetic_merge_checkout(self):
        text = workflow('pr-feedback')
        header = text.split('permissions:', 1)[0]
        self.assertIn('  pull_request:\n', header)
        self.assertIn('  merge_group:\n', header)
        self.assertNotIn('paths:', header)
        self.assertNotIn('pull_request.head.sha', text)
        self.assertIn('name: PR feedback', text)
        self.assertIn('needs: feedback', text)
        self.assertIn('if: always()', text)
        self.assertIn('FEEDBACK_RESULT', text)
        self.assertLess(text.index('Check application, runner and test syntax'),
                        text.index('Install pinned Python dependencies'))

    def test_exhaustive_triggers_require_selected_candidates_and_keep_version_tags(self):
        for name in EXHAUSTIVE:
            with self.subTest(workflow=name):
                text = workflow(name)
                header = text.split('jobs:', 1)[0]
                self.assertIn('  workflow_call:', header)
                self.assertIn('  workflow_dispatch:', header)
                self.assertIn('      candidate_sha:', header)
                self.assertNotIn('  pull_request:', header)
                self.assertNotIn('branches:', header)
                if name != 'digital-runtime':
                    self.assertIn("tags: ['v*']", header)
                self.assertIn('cancel-in-progress: false', header)
                self.assertIn('run: python scripts/ci_candidate.py', text)
                jobs = re.findall(r'^  ([a-z][a-z0-9-]*):\n((?:(?!^  [a-z]).|\n)*)', text.split('jobs:\n', 1)[1], re.M)
                for job, block in jobs:
                    if job != 'candidate':
                        self.assertRegex(block, r'(?m)^    needs:', job)

    def test_release_preparation_preserves_all_independent_gates_and_fresh_identity(self):
        text = workflow('release-preview')
        self.assertNotIn('  push:', text.split('permissions:', 1)[0])
        self.assertIn('      candidate_sha:', text)
        gates = 'mode, desktop, interoperability, physical, digital, vga, statistics, reference-compatibility'
        self.assertIn('needs: [' + gates + ']', text)
        for name in ('build-desktop', 'interoperability', 'physical-qualification', 'digital',
                     'vga-playground', 'analog-campaign-qualification', 'reference-compatibility'):
            self.assertIn('uses: ./.github/workflows/' + name + '.yml', text)
        self.assertLess(text.index('scripts/ci_candidate.py'), text.index('scripts/release_intent.py'))
        self.assertIn('RELEASE_COMMIT: ${{ github.sha }}', text)
        self.assertIn('scripts/release_evidence.py package', text)

    def test_independent_reference_corners_start_early_without_skipping_physical_gate(self):
        text = workflow('reference-compatibility')
        jobs = dict(re.findall(r'^  ([a-z][a-z0-9-]*):\n((?:(?!^  [a-z]).|\n)*)',
                               text.split('jobs:\n', 1)[1], re.M))
        self.assertEqual(set(jobs), {'candidate', 'rc-toolchain', 'modern-schematic',
                                    'bandgap-rc', 'bandgap-schematic', 'bandgap-physical'})
        self.assertRegex(jobs['rc-toolchain'], r'(?m)^    needs: candidate$')
        self.assertRegex(jobs['bandgap-physical'], r'(?m)^    needs: candidate$')
        self.assertRegex(jobs['bandgap-rc'], r'(?m)^    needs: rc-toolchain$')
        self.assertIn('fail-fast: false', jobs['bandgap-rc'])
        self.assertIn('corner: [nominal, ff, ss, fs, sf]', jobs['bandgap-rc'])
        self.assertIn('needs.rc-toolchain.outputs.artifact_name', jobs['bandgap-rc'])
        self.assertIn('needs.rc-toolchain.outputs.sha256', jobs['bandgap-rc'])
        self.assertIn('scripts/qualify_gf180_rc.py', jobs['bandgap-rc'])
        self.assertNotIn('--extraction-only', jobs['bandgap-rc'])
        self.assertIn('scripts/qualify_gf180_exchange.py', jobs['bandgap-physical'])
        self.assertIn('name: reference-bandgap-physical', jobs['bandgap-physical'])
        for name in jobs:
            self.assertNotRegex(jobs[name], r'(?m)^    (if|continue-on-error):')
        self.assertNotIn('continue-on-error:', text)
        release = workflow('release-preview')
        self.assertIn('uses: ./.github/workflows/reference-compatibility.yml', release)
        self.assertIn('statistics, reference-compatibility]', release)


if __name__ == '__main__':
    unittest.main()
