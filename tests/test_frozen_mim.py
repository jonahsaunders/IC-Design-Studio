"""Fail-closed boundaries of the independent installed MiM subgate checker."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_frozen_mim as check


class FrozenMimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.exe = self.root/'Installed App With Spaces/ICDesignStudio.exe'
        self.exe.parent.mkdir()
        self.exe.write_bytes(b'fixture application')
        self.commit = 'c'*40
        self.nonce = 'a'*32
        self.header = dict(schema=1, status='passed', mode='physical', frozen=True, native_execution=True,
            build=dict(commit=self.commit, dirty=False, frozen=True), execution_id=self.nonce,
            executable=str(self.exe), executable_sha256=check.sha(self.exe),
            qualified=False, release_ready=False, full_mim_installed=False)

    def write(self, name, data):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding='utf-8')
        return path

    def deck(self, plate=1, parameters='w=2 l=10 m=1 mf=1'):
        return f'* comment\n.subckt coupon P N\nX1 P N sky130_fd_pr__cap_mim_m3_{plate} {parameters}\n.ends coupon\n'

    def test_exact_frozen_candidate_header(self):
        check.header(self.header, self.exe, self.commit, self.nonce)

    def test_source_wrong_candidate_dirty_stale_and_overclaimed_reports_fail(self):
        mutations = [dict(frozen=False), dict(mode='lifecycle'), dict(native_execution=False), dict(status='failed'),
                     dict(execution_id='b'*32), dict(full_mim_installed=True), dict(qualified=True),
                     dict(release_ready=True), dict(errors=['worker failed']),
                     dict(build=dict(commit='d'*40, dirty=False, frozen=True)),
                     dict(build=dict(commit=self.commit, dirty=True, frozen=True)),
                     dict(build=dict(commit=self.commit, dirty=False, frozen=False))]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                check.header({**self.header, **mutation}, self.exe, self.commit, self.nonce)

    def test_executable_mutation_or_path_substitution_fails(self):
        self.exe.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'executable'):
            check.header(self.header, self.exe, self.commit, self.nonce)
        other = self.root/'other.exe'; other.write_bytes(b'fixture application')
        with self.assertRaisesRegex(ValueError, 'executable'):
            check.header(self.header, other, self.commit, self.nonce)

    def test_strict_json_rejects_duplicates_and_nonfinite_values(self):
        path = self.root/'record.json'
        for value in ('{"status":"failed","status":"passed"}', '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}'):
            path.write_text(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                check.load(path)

    def test_paths_reject_traversal_drive_alias_and_outside_absolute(self):
        for value in ('../old/report.json', '/old/report.json', 'C:/old/report.json', 'a\\b', 'a//b', './b', 'a/../b', 'output:stream'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                check.relative(value)
        with self.assertRaises(ValueError):
            check.confined(self.root/'evidence', self.exe)
        self.assertEqual(check.confined(self.root, 'record.json'), self.root/'record.json')

    @unittest.skipIf(os.name == 'nt', 'Windows symlink creation requires privileges on some hosts.')
    def test_symlink_inside_evidence_is_rejected(self):
        target = self.root/'real'; target.mkdir(); (target/'file').write_text('bytes')
        (self.root/'alias').symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            check.confined(self.root, 'alias/file')
        with self.assertRaises(ValueError):
            check.inventory(self.root)

    def test_file_inventory_rejects_missing_corrupt_and_unsafe_entries(self):
        path = self.root/'output.txt'; path.write_text('complete')
        records = {'output.txt': check.sha(path)}
        check.file_map(self.root, records)
        path.write_text('corrupt')
        with self.assertRaises(ValueError): check.file_map(self.root, records)
        path.unlink()
        with self.assertRaises(ValueError): check.file_map(self.root, records)
        with self.assertRaises(ValueError): check.file_map(self.root, {'../x': 'a'*64})
        with self.assertRaises(ValueError): check.file_map(self.root, {})

    def test_current_historical_and_extracted_mim_circuits(self):
        check.circuit(self.deck(), 'coupon', 1)
        check.circuit(self.deck(2, 'w=2 l=10 m=4 vm=4'), 'coupon', 2, 4, historical=True)
        check.circuit(self.deck(2, 'w=2 l=10'), 'coupon', 2, extracted=True)

    def test_rehashed_semantic_circuit_mutations_are_rejected(self):
        mutations = [self.deck().replace('P N sky', 'N P sky'), self.deck(2),
                     self.deck(parameters='w=10 l=2 m=1 mf=1'), self.deck(parameters='w=2 l=10 m=2 mf=1'),
                     self.deck(parameters='w=2 l=10 m=1 vm=1'), self.deck(parameters='w=2 l=10 m=1 mf=1 w=2'),
                     self.deck(parameters='w=NaN l=10 m=1 mf=1'), self.deck().replace('.ends', 'R1 P N 1\n.ends'),
                     self.deck().replace('coupon', 'different')]
        for text in mutations:
            with self.subTest(text=text), self.assertRaises(ValueError):
                check.circuit(text, 'coupon', 1)

    def test_package_lock_binds_manifest_and_every_asset(self):
        self.write('package.json', dict(id='sky130A', files={'model.spice': hashlib.sha256(b'model').hexdigest()}))
        (self.root/'model.spice').write_bytes(b'model'); expected = check.sha(self.root/'package.json')
        check.package(self.root, expected)
        (self.root/'model.spice').write_bytes(b'changed')
        with self.assertRaises(ValueError): check.package(self.root, expected)
        with self.assertRaises(ValueError): check.package(self.root, '0'*64)

    def test_missing_duplicated_or_reordered_lifecycle_never_passes(self):
        for cases in ([], check.CASES[:-1], (*check.CASES, check.CASES[0]), tuple(reversed(check.CASES))):
            with self.subTest(cases=cases), self.assertRaisesRegex(ValueError, 'layout cases'):
                check.lifecycle(self.root, {'lifecycle': [dict(case=c) for c in cases]}, {}, {})

    def test_cross_case_nonce_is_rejected_before_saved_evidence(self):
        rows = [dict(case=c, plate=int(c[1]), rotation=int(c.split('-r')[1]),
                     top='mim_p1_r0_wrong', execution_id=self.nonce) for c in check.CASES]
        with self.assertRaisesRegex(ValueError, 'case identity'):
            check.lifecycle(self.root, dict(lifecycle=rows, execution_id=self.nonce), {}, {})

    def test_native_stage_summary_cannot_hide_missing_or_failed_stage(self):
        for stages in ([dict(name=n, status='passed') for n in check.STAGES[:-1]],
                       [dict(name=n, status='passed') for n in (*check.STAGES, 'lvs')],
                       [dict(name=n, status='failed' if n == 'lvs' else 'passed') for n in check.STAGES]):
            with self.subTest(stages=stages), self.assertRaises(ValueError):
                check.native_output(self.root, dict(stages=stages, status='passed'), 1, 'coupon')

    def native_fixture(self):
        contents = {'drc/console.log': 'STUDIO_DRC_COUNT 0\nSTUDIO_DRC_STYLE drc(full)\nSTUDIO_MAGIC_COMPLETE\n',
                    'drc/findings.tsv': '', 'lvs-extraction/native-extraction.log': 'STUDIO_MAGIC_COMPLETE\n',
                    'lvs-extraction/console.log': 'STUDIO_MAGIC_COMPLETE\n',
                    'lvs-extraction/extracted.spice': self.deck(parameters='w=2 l=10'),
                    'lvs/lvs.log': 'Final result: Circuits match uniquely.\nCell pin lists are equivalent.\n',
                    'layout.gds': 'fixture raw GDS identity', 'input.icproj': '{}',
                    'schematic.spice': self.deck(), 'schematic-lvs.spice': self.deck()}
        for name, text in contents.items():
            path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
        stages = [dict(name=n, status='passed', evidence={}) for n in check.STAGES]
        stages[3]['evidence'] = dict(deck='lvs-extraction/extracted.spice', sha256=check.sha(self.root/'lvs-extraction/extracted.spice'),
            settings=dict(hierarchy=True, blackbox=False, merge='none', scale=False,
                          capacitance_threshold='infinite', resistance_threshold='infinite', distributed_resistance=False))
        stages[4]['evidence'] = dict(unique_match=True, log='lvs/lvs.log')
        stages[5]['evidence'] = dict(verified=True, files={name: check.sha(self.root/name) for name in contents})
        return dict(stages=stages, status='passed', drc_engine='magic', lvs_extractor='magic',
                    magic_drc_style='drc(full)', drc_count=0, magic_drc_count=0)

    def test_native_output_reads_raw_drc_lvs_and_exact_extraction_settings(self):
        native = self.native_fixture()
        check.native_output(self.root, native, 1, 'coupon')

    def test_rehashed_raw_native_corruptions_fail_without_trusting_summary(self):
        controls = ('drc-count', 'drc-style', 'duplicate-complete', 'findings', 'lvs-property',
                    'lvs-pins', 'model', 'blackbox', 'missing-integrity', 'count')
        for fault in controls:
            native = self.native_fixture()
            if fault == 'drc-count': (self.root/'drc/console.log').write_text('STUDIO_DRC_COUNT 1\nSTUDIO_DRC_STYLE drc(full)\nSTUDIO_MAGIC_COMPLETE\n')
            elif fault == 'drc-style': (self.root/'drc/console.log').write_text('STUDIO_DRC_COUNT 0\nSTUDIO_DRC_STYLE fast\nSTUDIO_MAGIC_COMPLETE\n')
            elif fault == 'duplicate-complete': (self.root/'lvs-extraction/console.log').write_text('STUDIO_MAGIC_COMPLETE\nSTUDIO_MAGIC_COMPLETE\n')
            elif fault == 'findings': (self.root/'drc/findings.tsv').write_text('narrow metal\t0,0,1,1\n')
            elif fault == 'lvs-property': (self.root/'lvs/lvs.log').write_text('Final result: Circuits match uniquely.\nCell pin lists are equivalent.\nProperty errors were found.\n')
            elif fault == 'lvs-pins': (self.root/'lvs/lvs.log').write_text('Final result: Circuits match uniquely.\n')
            elif fault == 'model': (self.root/'lvs-extraction/extracted.spice').write_text(self.deck(2, 'w=2 l=10'))
            elif fault == 'blackbox': native['stages'][3]['evidence']['settings']['blackbox'] = True
            elif fault == 'missing-integrity': native['stages'][5]['evidence']['files'].pop('layout.gds')
            else: (self.root/'lvs-extraction/extracted.spice').write_text(self.deck(parameters='w=2 l=10 m=2'))
            native['stages'][3]['evidence']['sha256'] = check.sha(self.root/'lvs-extraction/extracted.spice')
            for name in native['stages'][5]['evidence']['files']:
                native['stages'][5]['evidence']['files'][name] = check.sha(self.root/name)
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                check.native_output(self.root, native, 1, 'coupon')

    def test_git_overrides_are_removed_case_insensitively(self):
        with patch.dict(os.environ, {'GIT_DIR': 'elsewhere', 'git_work_tree': 'other', 'GIT_CONFIG_COUNT': '1', 'ordinary': 'keep'}):
            env = check.git_environment()
        self.assertFalse(any(k.upper().startswith('GIT_') for k in env))
        self.assertEqual(next(v for k, v in env.items() if k.lower() == 'ordinary'), 'keep')

    def test_undo_content_identity_allows_only_revision_and_modified_changes(self):
        old = dict(id='design', revision=1, modified='before', cells=[dict(name='mim', shapes=[])])
        repaired = {**old, 'revision': 3, 'modified': 'after'}
        self.assertNotEqual(check.design_hash(old), check.design_hash(repaired))
        self.assertEqual(check.content_hash(old), check.content_hash(repaired))
        repaired = copy.deepcopy(repaired); repaired['cells'][0]['shapes'].append({'layer': 'extra'})
        self.assertNotEqual(check.content_hash(old), check.content_hash(repaired))

    def test_existing_output_and_invalid_candidate_fail_before_launch(self):
        out = self.root/'already-used'; out.mkdir()
        with patch.object(check.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'new output'):
                check.verify(self.exe, self.root, out, self.commit)
            with self.assertRaises(ValueError):
                check.verify(self.exe, self.root, self.root/'new', 'main')
            with self.assertRaises(ValueError):
                check.verify(self.exe, self.root, self.root/'new', self.commit, float('nan'))
            run.assert_not_called()

    def launcher_fixture(self):
        bundle = self.exe.parent/'_internal'
        payload = bundle/'icstudio/assets/runtime/digital'; payload.mkdir(parents=True)
        (payload/'runtime.tar.gz').write_bytes(b'fixture runtime')
        (payload/'manifest.json').write_text(json.dumps(dict(schema=1, archive='runtime.tar.gz', sha256=check.sha(payload/'runtime.tar.gz'))))
        collection = bundle/'icstudio/assets/pdks/collection.json'; collection.parent.mkdir(parents=True)
        collection.write_text('{}')
        inputs = dict(package_sha256='a'*64, physical_sha256='b'*64, collection_sha256=check.sha(collection))
        return payload, inputs

    def test_launcher_uses_installed_exe_new_nonce_no_source_override_and_preserves_state(self):
        payload, inputs = self.launcher_fixture(); out = self.root/'new-run'
        def run(command, **kwargs):
            self.assertEqual(command[:2], [str(self.exe), '--mim-acceptance'])
            self.assertIn('--managed', command)
            self.assertEqual(command[command.index('--mode')+1], 'physical')
            self.assertRegex(command[command.index('--execution-id')+1], r'^[0-9a-f]{32}$')
            for key in ('PYTHONPATH', 'PYTHONHOME', 'ICSTUDIO_DIGITAL_PAYLOAD', 'ICSTUDIO_DIGITAL_NATIVE', 'LD_LIBRARY_PATH'):
                self.assertNotIn(key, kwargs['env'])
            self.assertEqual(kwargs['env']['ICSTUDIO_DIGITAL_STATE'], 'selected-state')
            self.assertEqual(kwargs['cwd'], out)
            return subprocess.CompletedProcess(command, 0)
        with patch.object(check, 'expected_inputs', return_value=inputs), patch.object(check, 'package'), \
                patch.object(check, 'backend_binding', return_value={'file.py': 'c'*64}), \
                patch.object(check, 'audit', return_value=dict(status='PASS', full_mim_installed=False)), \
                patch.object(check.subprocess, 'run', side_effect=run), patch.dict(os.environ,
                    dict(PYTHONPATH='source', PYTHONHOME='source', ICSTUDIO_DIGITAL_PAYLOAD='external',
                         ICSTUDIO_DIGITAL_NATIVE='1', LD_LIBRARY_PATH='external', ICSTUDIO_DIGITAL_STATE='selected-state')):
            result = check.verify(self.exe, self.root/'pdk', out, self.commit)
        self.assertEqual(result['status'], 'PASS')
        self.assertFalse(result['full_mim_installed'])
        self.assertEqual(check.load(out/'verification.json')['status'], 'PASS')

    def test_launcher_executable_drift_is_failure_even_after_successful_exit(self):
        _, inputs = self.launcher_fixture(); out = self.root/'drift'
        def run(command, **kwargs):
            self.exe.write_bytes(b'replaced after launch')
            return subprocess.CompletedProcess(command, 0)
        with patch.object(check, 'expected_inputs', return_value=inputs), patch.object(check, 'package'), \
                patch.object(check, 'backend_binding', return_value={}), patch.object(check.subprocess, 'run', side_effect=run):
            with self.assertRaisesRegex(ValueError, 'changed during'):
                check.verify(self.exe, self.root/'pdk', out, self.commit)
        self.assertEqual(check.load(out/'verification.json')['status'], 'FAIL')

    def test_timeout_cancels_only_new_probe_owned_native_jobs_and_retains_failure(self):
        _, inputs = self.launcher_fixture(); out = self.root/'timeout'
        unrelated = self.root/'unrelated'; unrelated.mkdir()
        def run(command, **kwargs):
            path = out/'probe/runs with spaces/project/job/input.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(dict(settings=dict(physical_runtime=dict(kind='linux')))))
            raise subprocess.TimeoutExpired(command, 1)
        with patch.object(check, 'expected_inputs', return_value=inputs), patch.object(check, 'package'), \
                patch.object(check, 'backend_binding', return_value={}), patch.object(check.subprocess, 'run', side_effect=run):
            with self.assertRaises(subprocess.TimeoutExpired):
                check.verify(self.exe, self.root/'pdk', out, self.commit, 1)
        self.assertTrue((out/'probe/runs with spaces/project/job/digital-cancel').is_file())
        self.assertFalse((unrelated/'digital-cancel').exists())
        self.assertEqual(check.load(out/'verification.json')['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
