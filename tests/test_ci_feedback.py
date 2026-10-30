"""Protect fast feedback, synthetic merge testing and exhaustive release routing."""
from pathlib import Path
import json
import os
import re
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import ci_feedback
from scripts.ci_feedback import ROOT, UNIT_MODULES, PACKAGE_MODULES, RUNTIME_RELEASE_MODULES, check_syntax, source_identity, stages

EXHAUSTIVE = (
    'build-desktop', 'digital-runtime', 'physical-qualification', 'interoperability',
    'digital', 'vga-playground', 'analog-campaign-qualification',
    'ihp-inductor-qualification', 'reference-compatibility',
)


def workflow(name):
    return (ROOT / '.github/workflows' / (name + '.yml')).read_text(encoding='utf-8')


class FeedbackTests(unittest.TestCase):
    def test_failed_stage_and_source_mutation_retain_failed_evidence(self):
        for failure in ('stage', 'package', 'source'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / 'evidence'
                identities = [{'scripts/runner.py': 'a' * 64}, {'scripts/runner.py': 'b' * 64}]
                commands = [] if failure == 'source' else [(
                    'package-contracts' if failure == 'package' else 'controlled-failure', ['unused'])]
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

    def test_nested_qualification_code_and_fixture_are_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            nested = root / 'scripts/qualification/sky130_mim_conditioning/replay.py'
            fixture = root / 'docs/qualification/sky130-mim-conditioning-v1/fixture-bundle.zip'
            nested.parent.mkdir(parents=True)
            fixture.parent.mkdir(parents=True)
            nested.write_text('x = 1\n')
            fixture.write_bytes(b'original fixture')
            before = source_identity(root)
            self.assertEqual(set(before), {nested.relative_to(root).as_posix(),
                                           fixture.relative_to(root).as_posix()})
            self.assertEqual(check_syntax(root), 1)
            fixture.write_bytes(b'changed fixture')
            self.assertNotEqual(source_identity(root), before)
            nested.write_text('def invalid(:\n')
            with self.assertRaises(SyntaxError):
                check_syntax(root)
            nested.unlink()
            self.assertNotIn('scripts/qualification/sky130_mim_conditioning/replay.py',
                             source_identity(root))

    def test_ihp_assets_and_post_exit_inventory_are_bound(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            asset = root / 'icstudio/assets/qualification/ihp-resistor-templates/templates.json'
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b'original')
            before = source_identity(root)
            self.assertIn(asset.relative_to(root).as_posix(), before)
            asset.write_bytes(b'changed')
            self.assertNotEqual(source_identity(root), before)
            output = root / 'probe'
            output.mkdir()
            payload = output / 'project.icproj'
            payload.write_bytes(b'project')
            inventory = output / 'files.json'
            inventory.write_text(json.dumps({'project.icproj': hashlib.sha256(payload.read_bytes()).hexdigest()}))
            report = dict(status='passed', frozen=False, installed_acceptance=False,
                          native_execution=False, qualified=False, release_ready=False, full_family=False,
                          lifecycle=[{'case': f'{model}-g{geometry}-v{via}-r{rotation}'}
                                     for model in ('rsil', 'rppd', 'rhigh') for geometry in range(5)
                                     for via in (0, 1) for rotation in (0, 90)],
                          files_sha256=hashlib.sha256(inventory.read_bytes()).hexdigest())
            (output / 'report.json').write_text(json.dumps(report))
            ci_feedback.check_ihp_gui_output(output)
            original_case = report['lifecycle'][0]['case']
            report['lifecycle'][0]['case'] = report['lifecycle'][1]['case']
            (output / 'report.json').write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                ci_feedback.check_ihp_gui_output(output)
            report['lifecycle'][0]['case'] = original_case
            (output / 'report.json').write_text(json.dumps(report))
            payload.write_bytes(b'changed after child exit')
            with self.assertRaises(ValueError):
                ci_feedback.check_ihp_gui_output(output)
            payload.write_bytes(b'project')
            (output / 'extra.txt').write_bytes(b'extra')
            with self.assertRaises(ValueError):
                ci_feedback.check_ihp_gui_output(output)
            (output / 'extra.txt').unlink()
            report['installed_acceptance'] = True
            (output / 'report.json').write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                ci_feedback.check_ihp_gui_output(output)

    def test_focused_modules_exist_and_release_contracts_remain_fast_checks(self):
        for name in (*UNIT_MODULES, *PACKAGE_MODULES, *RUNTIME_RELEASE_MODULES):
            self.assertTrue((ROOT / 'tests' / (name.split('.')[0] + '.py')).is_file(), name)
        commands = stages()
        self.assertEqual([name for name, _ in commands],
                         ['unit-contracts', 'package-contracts', 'runtime-release-contracts', 'release-contracts', 'menu-smoke', 'project-hub-smoke',
                          'metal-resistor-editor-smoke', 'metal-resistor-parallel-smoke',
                          'ihp-resistor-editor-smoke'])
        self.assertIn('test_pdk_qualification_matrix', UNIT_MODULES)
        self.assertIn('test_release_acceptance', UNIT_MODULES)

    def test_required_package_checks_are_separate_complete_and_nonoverlapping(self):
        self.assertFalse(set(UNIT_MODULES) & set(PACKAGE_MODULES))
        command = dict(stages())['package-contracts']
        self.assertEqual(command[3:-1], ['tests.' + name for name in PACKAGE_MODULES])
        tests = unittest.defaultTestLoader.loadTestsFromNames(command[3:-1])
        self.assertEqual(tests.countTestCases(), 11)
        self.assertEqual(len(command[3:-1]), len(set(command[3:-1])))
        self.assertNotIn('test_default_device_packages', UNIT_MODULES)

    def test_runtime_release_checks_remain_required_separate_and_unique(self):
        expected = {'test_stage_linux_ngspice', 'test_linux_ngspice_dependencies',
                    'test_fetch_linux_ngspice_sources', 'test_release_pw2dn_evidence',
                    'test_release_qualification', 'test_publish_prerelease'}
        self.assertEqual(set(RUNTIME_RELEASE_MODULES), expected)
        self.assertEqual(len(RUNTIME_RELEASE_MODULES), len(expected))
        self.assertFalse(set(RUNTIME_RELEASE_MODULES) & (set(UNIT_MODULES) | set(PACKAGE_MODULES)))
        self.assertEqual(dict(stages())['runtime-release-contracts'][3:-1],
                         ['tests.' + name for name in RUNTIME_RELEASE_MODULES])
        self.assertIn('test_sky130_esd_nvt_audit', UNIT_MODULES)

    def test_desktop_payload_gate_runs_for_both_platforms_and_retains_failure_receipts(self):
        text = workflow('build-desktop')
        for platform, output in (('Windows', 'build/windows-evidence/pw2dn'),
                                 ('Linux', 'build/frozen-pw2dn-evidence')):
            self.assertIn('Assemble and execute ' + platform + ' release archives', text)
            self.assertIn('--source-archive build/desktop-handoff-source/source.zip --pw2dn-evidence ' + output, text)
        for module in ('test_stage_linux_ngspice', 'test_linux_ngspice_dependencies',
                       'test_fetch_linux_ngspice_sources', 'test_release_pw2dn_evidence',
                       'test_release_qualification', 'test_sky130_esd_nvt_audit'):
            self.assertIn('tests.' + module, text)
        for path in ('**/report.json', '**/files.json', '**/ldd.txt', 'source-cache/apt*.log',
                     'source-cache/invocations.json', 'source-cache/fetch-report.json',
                     'source-cache/source-inputs.json'):
            self.assertEqual(text.count('build/ngspice-dependencies-*/' + path), 3)
        self.assertNotIn('build/linux-runtime-dependency-provenance', text)

    def test_runtime_archive_and_selected_models_and_contracts_are_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / 'packaging/ngspice/ngspice-linux47-corrected-v1.zip'
            contract = root / 'docs/qualification/sky130-li-contract-v3.json'
            package = root / 'icstudio/assets/pdks/sky130A/package.json'
            asset = package.parent / 'libs/models/pw2dn.spice'
            for path in (archive, contract, asset): path.parent.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(b'runtime'); contract.write_bytes(b'contract'); asset.write_bytes(b'model')
            package.write_text(json.dumps({'files': {'libs/models/pw2dn.spice': 'a' * 64}}))
            before = source_identity(root)
            for path in (archive, contract, asset, package):
                name = path.relative_to(root).as_posix()
                self.assertIn(name, before)
                original = path.read_bytes(); path.write_bytes(original + b' ')
                self.assertNotEqual(source_identity(root), before, name)
                path.write_bytes(original)
            asset.unlink()
            with self.assertRaisesRegex(ValueError, 'Missing selected SKY130 package member'):
                source_identity(root)
            for name in ('libs/./model', 'libs//model', '../outside', 'C:/outside', 'libs\\model', '/absolute'):
                with self.subTest(name=name):
                    package.write_text(json.dumps({'files': {name: 'a' * 64}}))
                    with self.assertRaisesRegex(ValueError, 'Unsafe selected SKY130 package member'):
                        source_identity(root)

    @unittest.skipIf(os.name == 'nt', 'Directory symlink creation is not assumed on Windows.')
    def test_selected_model_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); package = root / 'icstudio/assets/pdks/sky130A/package.json'
            package.parent.mkdir(parents=True)
            outside = root / 'outside'; outside.mkdir(); (outside / 'model').write_bytes(b'model')
            (package.parent / 'libs').symlink_to(outside, target_is_directory=True)
            package.write_text(json.dumps({'files': {'libs/model': 'a' * 64}}))
            with self.assertRaisesRegex(ValueError, 'Linked selected SKY130 package member'):
                source_identity(root)

    def test_package_timeout_remains_a_required_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'evidence'
            with patch.dict(os.environ, {'GITHUB_SHA': 'a' * 40}, clear=True), \
                 patch('sys.argv', ['ci_feedback.py', '--output', str(output)]), \
                 patch.object(ci_feedback.subprocess, 'check_output', return_value='a' * 40), \
                 patch.object(ci_feedback.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['unused'], 300)) as run, \
                 patch.object(ci_feedback, 'source_identity', return_value={'scripts/runner.py': 'a' * 64}), \
                 patch.object(ci_feedback, 'check_syntax', return_value=1), \
                 patch.object(ci_feedback, 'stages', return_value=[('package-contracts', ['unused'])]), patch('builtins.print'):
                with self.assertRaisesRegex(RuntimeError, 'package-contracts failed with exit code 124'):
                    ci_feedback.main()
            self.assertEqual(run.call_args.kwargs['timeout'], 300)
            report = json.loads((output / 'report.json').read_bytes())
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['stages'][0]['returncode'], 124)
            self.assertFalse(report['release_acceptance'])

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

    def test_exact_native_capability_contract_runs_without_full_analog_suite(self):
        selected = 'test_analog.AnalogTests.test_capabilities_do_not_trust_catalog_or_metadata'
        self.assertIn(selected, UNIT_MODULES)
        command = dict(stages())['unit-contracts']
        self.assertEqual(command.count('tests.' + selected), 1)
        self.assertNotIn('tests.test_analog', command)
        self.assertNotIn('tests.test_analog.AnalogTests', command)

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
