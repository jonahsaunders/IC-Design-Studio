"""Protect fast feedback, synthetic merge testing and exhaustive release routing."""
from pathlib import Path
import json
import os
import re
import subprocess
import sys
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
    def test_project_data_safety_is_required_and_source_bound(self):
        self.assertEqual(UNIT_MODULES.count('test_project_data_safety'), 1)
        self.assertIn('test_project_data_safety', ci_feedback.UNIT_STAGE_MODULES)
        bound = source_identity()
        for name in ('tests/test_project_data_safety.py', 'tests/gui_project_data_safety.py'):
            self.assertIn(name, bound)

    def test_reconstructed_build_policies_are_bound_without_native_selection(self):
        for name in ('test_ihp_wsl_app_dispatch', 'test_ihp_wsl_app_reconstruction', 'test_ihp_wsl_elf_symbols'):
            self.assertIn(name, RUNTIME_RELEASE_MODULES)
        self.assertNotIn('test_ihp_wsl_app_auditor', RUNTIME_RELEASE_MODULES)
        self.assertNotIn('test_ihp_wsl_app_contract', RUNTIME_RELEASE_MODULES)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('ihp-wsl-experimental', 'ihp-wsl-reconstruction-v2'):
                p = root / 'docs/research' / name / 'policy.json'
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('{}')
                before = source_identity(root)
                p.write_text('{"changed":true}')
                self.assertNotEqual(before, source_identity(root))

    def test_bounded_windows_failure_summary_is_checked_in_both_source_lanes(self):
        self.assertEqual(RUNTIME_RELEASE_MODULES.count('test_windows_failure_summary'), 1)
        self.assertEqual(workflow('build-desktop').count('tests.test_windows_failure_summary -v'), 1)

    def test_klayout_wrapper_sources_and_license_are_bound(self):
        self.assertEqual(UNIT_MODULES.count('test_klayout_wrappers'), 1)
        self.assertEqual(UNIT_MODULES.count('test_sky130_li_array_dynamic'), 1)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            names = ('source-lock.json', 'Apache-2.0.txt', 'README.md',
                     'sources/example/rule_decks/devices_connections.lvs')
            paths = [root/'docs/qualification/klayout-wrapper-sources-v1'/name for name in names]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'original exact source')
            before = source_identity(root)
            self.assertEqual(set(before), {p.relative_to(root).as_posix() for p in paths})
            for path in paths:
                path.write_bytes(b'changed source')
                self.assertNotEqual(source_identity(root), before)
                path.unlink()
                self.assertNotEqual(source_identity(root), before)
                path.write_bytes(b'original exact source')
                self.assertEqual(source_identity(root), before)

    def test_xschem_config_fact_fixtures_are_bound(self):
        self.assertEqual(UNIT_MODULES.count('test_xschem_configs'), 1)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = [root/'docs/qualification/xschem-config-facts-v1'/name
                     for name in ('source-lock.json', 'README.md', '1.json', '2.json', '3.json')]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'original source facts')
            before = source_identity(root)
            self.assertEqual(set(before), {p.relative_to(root).as_posix() for p in paths})
            for path in paths:
                path.write_bytes(b'changed facts')
                self.assertNotEqual(source_identity(root), before)
                path.unlink()
                self.assertNotEqual(source_identity(root), before)
                path.write_bytes(b'original source facts')
                self.assertEqual(source_identity(root), before)

    def test_source_manifest_sources_and_license_are_bound(self):
        self.assertEqual(UNIT_MODULES.count('test_source_manifests'), 1)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = [root/'docs/qualification/source-manifest-wrappers-v1'/name
                     for name in ('source-lock.json', 'README.md', 'tools.txt', 'sky130.lylvs', 'Apache-2.0.txt')]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'original exact source')
            before = source_identity(root)
            self.assertEqual(set(before), {p.relative_to(root).as_posix() for p in paths})
            for path in paths:
                path.write_bytes(b'changed source')
                self.assertNotEqual(source_identity(root), before)
                path.unlink()
                self.assertNotEqual(source_identity(root), before)
                path.write_bytes(b'original exact source')
                self.assertEqual(source_identity(root), before)

    def test_follow_on_contracts_and_runtime_provenance_are_bound(self):
        for module in ('test_ihp_guard_vias', 'test_ihp_guard_corner_safe', 'test_ihp_pmos_measured_reference',
                       'test_ihp_pmos_measured_reference_v2', 'test_ihp_pmos_measured_v3_readback', 'test_ihp_tap_linked',
                       'test_source_disposition_reconstruction_v3'):
            self.assertEqual(UNIT_MODULES.count(module), 1)
        names = ('ihp-resistor-guard-vias-v1.json',
                 'ihp-resistor-guard-corner-safe-v2.json',
                 'source-dispositions-2026-11-10-v3.delta.json.gz',
                 'ihp-pmos-measured-reference-v1/contract.json',
                 'ihp-pmos-measured-reference-v2/contract.json',
                 'ihp-pmos-measured-reference-v1/measurement.mdm',
                 'ihp-pmos-measured-reference-v1/LICENSE',
                 'ihp-pmos-measured-reference-v1/provenance/profile.json',
                 'ihp-pmos-measured-reference-v1/provenance/licenses/compiler/LICENSE')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = [root/'docs/qualification'/name for name in names]
            paths.append(root/'tests/fixtures/ihp-guard-raw-all100-v1.json')
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'original retained input')
            before = source_identity(root)
            self.assertEqual(set(before), {p.relative_to(root).as_posix() for p in paths})
            for path in paths:
                path.write_bytes(b'changed input')
                self.assertNotEqual(source_identity(root), before)
                path.unlink()
                self.assertNotEqual(source_identity(root), before)
                path.write_bytes(b'original retained input')
                self.assertEqual(source_identity(root), before)

    def test_checked_in_semantic_inputs_authenticate_before_feedback(self):
        import gzip
        from scripts.inventory_sky130_release import verified_metadata
        from scripts.inventory_upstream_semantics import load_sources
        inputs = ROOT / 'docs/qualification'
        verified_metadata(json.loads((inputs / 'sky130-release-inputs-2026-11-07.json').read_bytes()))
        # Reconstruct the actual committed Git graphs, not only synthetic
        # fixtures. Missing or altered metadata must fail before a CI snapshot.
        files, closure = load_sources(inputs / 'upstream-view-inputs-2026-10-20.json.gz',
                                      inputs / 'upstream-semantics-gf-inputs-2026-11-07.json.gz')
        self.assertTrue(files)
        self.assertTrue(closure['gf_parent_graph']['repositories'])
        historical = json.loads(gzip.decompress((inputs / 'upstream-views-2026-10-20.json.gz').read_bytes()))
        self.assertTrue(historical['files'])
        from scripts.audit_source_dispositions import COMPANION_ROOTS, COMPANION_PINS, REPORTS, checked_report
        from scripts.inventory_upstream_views import verified_closure
        companion_files, _ = verified_closure(json.loads(gzip.decompress(
            (inputs / 'source-dispositions-companion-inputs-2026-11-07.json.gz').read_bytes())),
            roots=COMPANION_ROOTS, repositories=COMPANION_PINS)
        self.assertTrue(companion_files)
        for relative, digest in REPORTS.values():
            checked_report(ROOT / relative, digest)

    def test_semantic_source_graphs_and_release_inputs_are_bound(self):
        self.assertEqual(UNIT_MODULES.count('test_source_disposition_cache'), 1)
        self.assertEqual(UNIT_MODULES.count('test_source_disposition_reconstruction'), 1)
        self.assertEqual(UNIT_MODULES.count('test_source_disposition_reconstruction_v2'), 1)
        names = ('upstream-view-inputs-2026-10-20.json.gz',
                 'upstream-views-2026-10-20.json.gz',
                 'sky130-release-inputs-2026-11-07.json',
                 'upstream-semantics-gf-inputs-2026-11-07.json.gz',
                 'source-dispositions-companion-inputs-2026-11-07.json.gz',
                 'upstream-semantics-inventory-2026-11-07-v2.json.gz',
                 'sky130-release-inventory-2026-11-07.json.gz',
                 'source-dispositions-2026-11-08-v1.json.gz',
                 'source-dispositions-2026-11-10-v1.delta.json.gz',
                 'source-dispositions-2026-11-10-v2.delta.json.gz')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'docs/qualification'
            source.mkdir(parents=True)
            for name in names:
                (source / name).write_bytes(b'original authenticated input')
            before = source_identity(root)
            self.assertEqual(set(before), {'docs/qualification/' + name for name in names})
            for name in names:
                with self.subTest(name=name):
                    path = source / name
                    path.write_bytes(b'changed source metadata')
                    self.assertNotEqual(source_identity(root), before)
                    path.unlink()
                    self.assertNotEqual(source_identity(root), before)
                    path.write_bytes(b'original authenticated input')
                    self.assertEqual(source_identity(root), before)

    def test_standalone_runner_can_bind_retained_inputs_without_pythonpath(self):
        command = [sys.executable, '-I', '-c',
                   "import runpy; from pathlib import Path; "
                   "runner=runpy.run_path(" + repr(str(ROOT / 'scripts/ci_feedback.py')) + "); "
                   "assert any(name.endswith('/digital_platform.py.txt') "
                   "for name in runner['source_identity']())"]
        result = subprocess.run(command, cwd=ROOT.parent, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_failed_stage_and_source_mutation_retain_failed_evidence(self):
        for failure in ('stage', 'package', 'device', 'source'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / 'evidence'
                identities = [{'scripts/runner.py': 'a' * 64}, {'scripts/runner.py': 'b' * 64}]
                commands = [] if failure == 'source' else [(
                    failure+'-contracts' if failure in ('package', 'device') else 'controlled-failure', ['unused'])]
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
            cmim = [root / 'tests/fixtures' / kind / name
                    for kind in ('ihp-cmim-capacitance-v1', 'ihp-cmim-parallel-v1')
                    for name in ('SOURCE.json', 'LICENSE', 'coupon.ext', 'hierarchical.spice', 'flat.spice')]
            nested.parent.mkdir(parents=True)
            fixture.parent.mkdir(parents=True)
            nested.write_text('x = 1\n')
            for path in [fixture, *cmim]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'original fixture')
            before = source_identity(root)
            self.assertEqual(set(before), {path.relative_to(root).as_posix()
                                           for path in [nested, fixture, *cmim]})
            self.assertEqual(check_syntax(root), 1)
            for path in [fixture, *cmim]:
                with self.subTest(fixture=path.relative_to(root).as_posix()):
                    path.write_bytes(b'changed fixture')
                    self.assertNotEqual(source_identity(root), before)
                    path.unlink()
                    self.assertNotEqual(source_identity(root), before)
                    path.write_bytes(b'original fixture')
                    self.assertEqual(source_identity(root), before)
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

    def test_guard_source_stage_assets_and_launched_nonce_are_bound(self):
        from scripts import verify_frozen_ihp_guard_corner as guard_gate
        for module in ('test_ihp_guard_app', 'test_ihp_guard_backend_assets',
                       'test_frozen_ihp_guard_corner'):
            self.assertEqual(UNIT_MODULES.count(module), 1)
        command = dict(stages())['ihp-guard-corner-smoke']
        self.assertEqual(command[:2], [sys.executable, 'tests/gui_ihp_guard_corner.py'])
        self.assertRegex(command[command.index('--execution-id') + 1], r'^[0-9a-f]{32}$')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            assets = [root/'icstudio/assets/qualification/ihp-guard-corner-safe'/name
                      for name in ('templates.json', 'README.txt', 'Apache-2.0.txt')]
            for path in assets:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'original')
            before = source_identity(root)
            self.assertEqual(set(before), {p.relative_to(root).as_posix() for p in assets})
            for path in assets:
                path.write_bytes(b'changed')
                self.assertNotEqual(source_identity(root), before)
                path.write_bytes(b'original')
                self.assertEqual(source_identity(root), before)
            probe = root/'probe'; probe.mkdir()
            nonce = 'a' * 32
            report = {'execution_id': nonce, 'execution_root': str(probe)}
            (probe/'report.json').write_text(json.dumps(report))
            with patch.object(guard_gate, 'source_audit', return_value={'status': 'PASS'}) as audit:
                self.assertEqual(ci_feedback.check_ihp_guard_gui_output(probe, nonce, root), {'status': 'PASS'})
                audit.assert_called_once_with(probe, root)
            for key, value in (('execution_id', 'b' * 32), ('execution_root', str(root/'other'))):
                changed = dict(report); changed[key] = value
                (probe/'report.json').write_text(json.dumps(changed))
                with patch.object(guard_gate, 'source_audit') as audit:
                    with self.assertRaisesRegex(ValueError, 'Stale or relocated'):
                        ci_feedback.check_ihp_guard_gui_output(probe, nonce, root)
                    audit.assert_not_called()
            (probe/'report.json').write_text(json.dumps(report))
            with patch.object(guard_gate, 'source_audit', side_effect=ValueError('changed payload')):
                with self.assertRaisesRegex(ValueError, 'changed payload'):
                    ci_feedback.check_ihp_guard_gui_output(probe, nonce, root)

    def test_focused_modules_exist_and_release_contracts_remain_fast_checks(self):
        for name in (*UNIT_MODULES, *PACKAGE_MODULES, *RUNTIME_RELEASE_MODULES):
            self.assertTrue((ROOT / 'tests' / (name.split('.')[0] + '.py')).is_file(), name)
        commands = stages()
        self.assertEqual([name for name, _ in commands],
                         ['unit-contracts', 'ihp-contracts', 'physical-contracts', 'device-contracts', 'package-contracts', 'runtime-release-contracts', 'release-contracts', 'menu-smoke', 'project-hub-smoke',
                          'metal-resistor-editor-smoke', 'metal-resistor-parallel-smoke',
                          'ihp-resistor-editor-smoke', 'ihp-guard-corner-smoke', 'ihp-capacitor-corner-smoke'])
        self.assertIn('test_ihp_capacitor_corners', UNIT_MODULES)
        self.assertIn('test_pdk_qualification_matrix', UNIT_MODULES)
        self.assertIn('test_sky130_retained_catalog', UNIT_MODULES)
        self.assertIn('test_digital_platforms', UNIT_MODULES)
        self.assertIn('test_release_acceptance', UNIT_MODULES)

    def test_retired_recovery_workflow_is_bound_not_active(self):
        from scripts.ci_feedback import source_identity, UNIT_MODULES
        self.assertIn('test_recover_pw2dn_diagnostics', UNIT_MODULES)
        self.assertIn('tests/fixtures/pw2dn-recovery-2026-11-11/recover-pw2dn-once.yml', source_identity())
        self.assertNotIn('.github/workflows/recover-pw2dn-once.yml', source_identity())

    def test_unit_split_preserves_each_expanded_test_exactly_once(self):
        commands=dict(stages())
        before=['tests.'+name for name in UNIT_MODULES]
        groups=[commands[name][3:-1] for name in ('unit-contracts','ihp-contracts','physical-contracts','device-contracts')]
        self.assertTrue(all(groups))
        self.assertEqual(sum(groups,[]),before)
        def ids(suite):
            for item in suite:
                if isinstance(item,unittest.TestSuite):yield from ids(item)
                else:yield item.id()
        original=list(ids(unittest.defaultTestLoader.loadTestsFromNames(before)))
        expanded=[list(ids(unittest.defaultTestLoader.loadTestsFromNames(group))) for group in groups]
        self.assertEqual(sum(expanded,[]),original)
        self.assertEqual(len(original),len(set(original)))
        self.assertFalse(any('_FailedTest' in name for name in original),
                         '\n'.join(unittest.defaultTestLoader.errors))

    def test_required_package_checks_are_separate_complete_and_nonoverlapping(self):
        self.assertFalse(set(UNIT_MODULES) & set(PACKAGE_MODULES))
        command = dict(stages())['package-contracts']
        self.assertEqual(command[3:-1], ['tests.' + name for name in PACKAGE_MODULES])
        tests = unittest.defaultTestLoader.loadTestsFromNames(command[3:-1])
        self.assertEqual(tests.countTestCases(), 11)
        self.assertEqual(len(command[3:-1]), len(set(command[3:-1])))
        self.assertNotIn('test_default_device_packages', UNIT_MODULES)

    def test_runtime_release_checks_remain_required_separate_and_unique(self):
        expected = {'test_openems_runtime', 'test_stage_linux_ngspice', 'test_linux_ngspice_dependencies',
                    'test_fetch_linux_ngspice_sources', 'test_release_pw2dn_evidence',
                    'test_release_qualification', 'test_publish_prerelease', 'test_windows_failure_summary',
                    'test_ihp_wsl_host_provenance',
                    'test_ihp_wsl_research_payload',
                    'test_ihp_wsl_research_projects',
                    'test_ihp_wsl_builder_cleanup',
                    'test_ihp_wsl_preparation_request',
                    'test_ihp_wsl_research_delivery',
                    'test_ihp_wsl_prepared',
                    'test_ihp_wsl_payload_transport',
    'test_ihp_wsl_app_dispatch',
    'test_ihp_wsl_app_reconstruction',
    'test_ihp_wsl_elf_symbols',
                    }
        self.assertEqual(set(RUNTIME_RELEASE_MODULES), expected)
        self.assertEqual(len(RUNTIME_RELEASE_MODULES), len(expected))
        self.assertFalse(set(RUNTIME_RELEASE_MODULES) & (set(UNIT_MODULES) | set(PACKAGE_MODULES)))
        self.assertEqual(dict(stages())['runtime-release-contracts'][3:-1],
                         ['tests.' + name for name in RUNTIME_RELEASE_MODULES])
        self.assertIn('test_sky130_esd_nvt_audit', UNIT_MODULES)
        self.assertIn('test_esd_installed_header_regression', UNIT_MODULES)

    def test_desktop_payload_gate_runs_for_both_platforms_and_retains_failure_receipts(self):
        text = workflow('build-desktop')
        for platform, output in (('Windows', 'build/windows-evidence/pw2dn'),
                                 ('Linux', 'build/frozen-pw2dn-evidence')):
            self.assertIn('Assemble and execute ' + platform + ' release archives', text)
            self.assertIn('--source-archive build/desktop-handoff-source/source.zip --pw2dn-evidence ' + output, text)
        for module in ('test_stage_linux_ngspice', 'test_linux_ngspice_dependencies',
                       'test_fetch_linux_ngspice_sources', 'test_release_pw2dn_evidence',
                       'test_release_qualification', 'test_sky130_esd_nvt_audit',
                       'test_esd_installed_header_regression'):
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
            dynamic_contract = root / 'docs/qualification/sky130-li-array-dynamic-v1.json'
            package = root / 'icstudio/assets/pdks/sky130A/package.json'
            asset = package.parent / 'libs/models/pw2dn.spice'
            for path in (archive, contract, dynamic_contract, asset): path.parent.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(b'runtime'); contract.write_bytes(b'contract'); asset.write_bytes(b'model')
            dynamic_contract.write_bytes(b'dynamic contract')
            package.write_text(json.dumps({'files': {'libs/models/pw2dn.spice': 'a' * 64}}))
            before = source_identity(root)
            for path in (archive, contract, dynamic_contract, asset, package):
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

    def test_ihp_capacitor_choice_inputs_remain_bound_after_child_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);package=root/'icstudio/assets/pdks/ihp-sg13g2/package.json'
            asset=package.parent/'libs.tech/ngspice/models/cornerCAP.lib'
            asset.parent.mkdir(parents=True);asset.write_bytes(b'original source')
            package.write_text(json.dumps({'files':{'libs.tech/ngspice/models/cornerCAP.lib':'a'*64}}))
            before=source_identity(root)
            self.assertIn(package.relative_to(root).as_posix(),before)
            self.assertIn(asset.relative_to(root).as_posix(),before)
            asset.write_bytes(b'changed after GUI verification')
            self.assertNotEqual(source_identity(root),before)
            asset.unlink()
            with self.assertRaisesRegex(ValueError,'Missing selected IHP package member'):
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

    def test_device_timeout_remains_a_required_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'evidence'
            with patch.dict(os.environ,{'GITHUB_SHA':'a'*40},clear=True), \
                 patch('sys.argv',['ci_feedback.py','--output',str(output)]), \
                 patch.object(ci_feedback.subprocess,'check_output',return_value='a'*40), \
                 patch.object(ci_feedback.subprocess,'run',side_effect=subprocess.TimeoutExpired(['unused'],300)) as run, \
                 patch.object(ci_feedback,'source_identity',return_value={'scripts/runner.py':'a'*64}), \
                 patch.object(ci_feedback,'check_syntax',return_value=1), \
                 patch.object(ci_feedback,'stages',return_value=[('device-contracts',['unused'])]),patch('builtins.print'):
                with self.assertRaisesRegex(RuntimeError,'device-contracts failed with exit code 124'):
                    ci_feedback.main()
            self.assertEqual(run.call_args.kwargs['timeout'],300)
            report=json.loads((output/'report.json').read_bytes())
            self.assertEqual(report['status'],'failed')
            self.assertEqual(report['stages'][0]['returncode'],124)
            self.assertFalse(report['release_acceptance'])

    def test_hosted_groups_partition_all_ordered_stages_without_changing_commands(self):
        commands = stages()
        contracts = ci_feedback.select_stages(commands, 'contracts')
        gui = ci_feedback.select_stages(commands, 'gui')
        self.assertIs(ci_feedback.select_stages(commands), commands)
        self.assertEqual(contracts + gui, commands)
        self.assertEqual((len(contracts), len(gui), len(commands)), (7, 7, 14))
        self.assertFalse(set(n for n, _ in contracts) & set(n for n, _ in gui))
        for invalid in (commands[:-1], commands + [commands[-1]], list(reversed(commands))):
            for group in ('contracts', 'gui'):
                with self.assertRaisesRegex(ValueError, 'partition'):
                    ci_feedback.select_stages(invalid, group)
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            ci_feedback.select_stages(commands, 'missing')

    def test_group_reports_are_explicit_and_keep_identity_and_deadlines(self):
        for group in ('all', 'contracts', 'gui'):
            with self.subTest(group=group), tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / 'evidence'
                commands = [(name, ['unused']) for name, _ in stages(output)]
                argv = ['ci_feedback.py', '--output', str(output)]
                if group != 'all': argv += ['--group', group]
                with patch.dict(os.environ, {'GITHUB_SHA': 'a' * 40}, clear=True), \
                     patch('sys.argv', argv), \
                     patch.object(ci_feedback.subprocess, 'check_output', return_value='a' * 40), \
                     patch.object(ci_feedback.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run, \
                     patch.object(ci_feedback, 'source_identity', return_value={'bound': 'a' * 64}) as identity, \
                     patch.object(ci_feedback, 'check_syntax', return_value=1), \
                     patch.object(ci_feedback, 'stages', return_value=commands), \
                     patch.object(ci_feedback, 'check_ihp_gui_output'), \
                     patch.object(ci_feedback, 'check_ihp_guard_gui_output', return_value={}), \
                     patch('builtins.print'):
                    # Preserve the guard stage's independently checked nonce argument.
                    commands = [(n, ['unused', '--execution-id', 'a' * 32]) for n, _ in commands]
                    with patch.object(ci_feedback, 'stages', return_value=commands):
                        ci_feedback.main()
                selected = ci_feedback.select_stages(commands, group)
                report = json.loads((output / 'report.json').read_bytes())
                self.assertEqual(report['stage_group'], group)
                self.assertEqual(report['full_stage_selection'], group == 'all')
                self.assertEqual(report['expected_stages'], [n for n, _ in selected])
                self.assertEqual([r['name'] for r in report['stages']], report['expected_stages'])
                self.assertEqual(report['all_expected_stages'], [n for n, _ in commands])
                self.assertEqual(report['status'], 'passed')
                self.assertFalse(report['release_acceptance'])
                self.assertEqual(identity.call_count, 2)
                self.assertEqual(run.call_count, len(selected))
                self.assertTrue(all(call.kwargs['timeout'] == 300 for call in run.call_args_list))

    def test_hosted_matrix_requires_all_platform_group_pairs_and_distinct_artifacts(self):
        text = workflow('pr-feedback')
        self.assertIn('os: [ubuntu-24.04, windows-2022]', text)
        self.assertIn('group: [contracts, gui]', text)
        self.assertNotIn('exclude:', text)
        self.assertNotIn('continue-on-error', text)
        self.assertIn('fail-fast: false', text)
        self.assertIn('timeout-minutes: 15', text)
        self.assertIn('python scripts/ci_feedback.py --group ${{ matrix.group }}', text)
        self.assertIn('name: source-feedback-${{ runner.os }}-${{ matrix.group }}-${{ github.sha }}', text)
        self.assertIn('needs: feedback', text)
        self.assertIn('FEEDBACK_RESULT: ${{ needs.feedback.result }}', text)
        self.assertIn('run: test "$FEEDBACK_RESULT" = success', text)
        self.assertIn('permissions:\n  contents: read\n', text)

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
