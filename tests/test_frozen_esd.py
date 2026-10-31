"""Small rejection tests for the optional frozen ESD acceptance boundary.

Native accuracy is covered by the retained 98-run acceptance, not these fixtures.
No simulator, GUI session, installed bundle or external evidence is required.
"""
import copy
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from icstudio import esd_desktop_probe as producer
from scripts import qualify_installed_sky130_esd as launcher
from scripts import verify_frozen_esd as reader


def selected_project():
    devices = []
    for index in range(6):
        nodes = {pin: f'q{index}{pin}' for pin in 'dgsb'}
        devices.append(dict(id=f'device-{index}', name=f'Dq{index}', kind='NMOS',
                            nets=nodes, net_labels=dict(nodes),
                            params={'w': '10u', 'l': f'{(.9, 2, 4)[index // 2]}u'},
                            model_params={'mult': str((1, 3)[index % 2])}))
    return dict(id='project', name='selected', revision=12, top='top',
                pdk={'layers': {}}, cells=[dict(id='top', devices=devices, wires=[])])


class FrozenEsdReaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def test_saved_graph_and_numeric_multiplicity_are_preserved(self):
        selected = selected_project()
        actual = producer.stimulus(selected, 'dc')
        actual['name'] = 'test title'
        reader.derived_project(actual, selected, 'dc', 'application', 'test title')
        self.assertEqual(actual['cells'][0]['devices'][:6], selected['cells'][0]['devices'])
        for device in actual['cells'][0]['devices'][:6]:
            device['model_params']['mult'] = str(float(device['model_params']['mult']) * 2)
        reader.derived_project(actual, selected, 'dc', 'wrong-multiplicity', 'test title')
        actual['cells'][0]['devices'][1]['model_params']['mult'] = '33'
        with self.assertRaisesRegex(ValueError, 'saved GUI graph'):
            reader.derived_project(actual, selected, 'dc', 'wrong-multiplicity', 'test title')

    def test_hidden_gate_label_and_length_changes_are_rejected(self):
        selected = selected_project()
        actual = producer.stimulus(selected, 'g')
        actual['name'] = 'test title'
        for field, value in (('net_labels', {'g': 'q0s'}), ('params', {'l': '4u'})):
            changed = copy.deepcopy(actual)
            changed['cells'][0]['devices'][0][field].update(value)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'saved GUI graph'):
                reader.derived_project(changed, selected, 'g', 'application', 'test title')
        changed = copy.deepcopy(actual)
        changed['cells'][0]['devices'][7]['net_labels']['p'] = 'q1d'
        with self.assertRaisesRegex(ValueError, 'declared sources'):
            reader.derived_project(changed, selected, 'g', 'application', 'test title')

    def result_fixture(self, drive):
        project = producer.stimulus(selected_project(), drive)
        ac = drive != 'dc'
        data = {'frequency' if ac else 'v(v-sweep)': [1000+0j, 10000+0j] if ac else [0j, .1+0j],
                'v(q0d)': [3+4j, 4+3j] if ac else [.3+0j, .4+0j],
                'i(vq0d)': [1j, -1j] if ac else [.01+0j, .02+0j]}
        settings = dict(type='ac' if ac else 'dc', corner='nominal', temperature=27,
                        source='VG', dc_start='0', dc_stop='1.2', dc_step='.03',
                        start='1k', end='1g', points=5)
        result = dict(schema=1, engine='ngspice (installed executable)', engine_hash='fixture-engine',
                      project_id=project['id'], revision=project['revision'], cell_id=project['top'],
                      design_hash=reader.digest(project), pdk_hash=reader.digest(project['pdk']),
                      rule_hash=reader.digest(project['pdk']['layers']), settings=settings, log='fixture log\n',
                      traces={'q0d': [5., 5.]} if ac else {'v-sweep': [0., .1], 'q0d': [.3, .4]},
                      phase={'q0d': [53.13010235415598, 36.86989764584402]} if ac else {},
                      currents={'Vq0d': [1., 1.]} if ac else {'Vq0d': [.01, .02]},
                      current_phase={'Vq0d': [90., -90.]} if ac else {},
                      x=[1000., 10000.] if ac else [0., .1],
                      x_label='Frequency (Hz)' if ac else 'Source value',
                      y_label='Voltage magnitude (V)' if ac else 'Voltage (V)',
                      operating_point={}, device_operating_point={}, operating_currents={})
        (self.root/'engine.log').write_text(result['log'], encoding='utf-8')
        return project, data, result

    def check_result(self, drive, project, data, result):
        (self.root/'comparison-result.json').write_text(json.dumps(result), encoding='utf-8')
        reader.application_result(self.root, project, data, 'nominal', 27, drive, 'fixture-engine')

    def test_independent_dc_and_ac_vector_reconstruction(self):
        for drive in ('dc', 'd'):
            with self.subTest(drive=drive):
                project, data, result = self.result_fixture(drive)
                self.check_result(drive, project, data, result)
                changed = copy.deepcopy(result)
                changed['currents']['Vq0d'][0] += .1
                with self.assertRaisesRegex(ValueError, 'currents'):
                    self.check_result(drive, project, data, changed)
                changed = copy.deepcopy(result)
                del changed['traces']['q0d']
                with self.assertRaisesRegex(ValueError, 'traces'):
                    self.check_result(drive, project, data, changed)
                changed = copy.deepcopy(result)
                changed['x'][0] = math.nan
                with self.assertRaises(ValueError):
                    self.check_result(drive, project, data, changed)

    def test_terminal_current_conservation(self):
        data = {f'i(vq{i}{pin})': [0j, 0j] for i in range(6) for pin in 'dgsb'}
        data['i(vq0d)'] = [1e-3+0j, 2e-3j]
        data['i(vq0s)'] = [-1e-3+0j, -2e-3j]
        reader.current_balance(data)
        data['i(vq0b)'][1] = 1e-6j
        with self.assertRaisesRegex(ValueError, 'conservation'):
            reader.current_balance(data)

    def test_sealed_inventory_rejects_added_and_missing_files(self):
        reader.write(self.root/'report.json', {'status': 'fixture'})
        (self.root/'raw.txt').write_text('native bytes', encoding='ascii')
        manifest = dict(schema=1, execution_id='fixture', files=reader.inventory(self.root))
        reader.write(self.root/'producer-manifest.json', manifest)
        expected = dict(execution_id='fixture', report_sha256=reader.sha(self.root/'report.json'),
                        producer_manifest_sha256=reader.sha(self.root/'producer-manifest.json'))
        reader.producer_inventory(self.root, expected)
        (self.root/'extra.txt').write_text('unexpected', encoding='ascii')
        with self.assertRaisesRegex(ValueError, 'changed after capture'):
            reader.producer_inventory(self.root, expected)
        (self.root/'extra.txt').unlink()
        (self.root/'raw.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'changed after capture'):
            reader.producer_inventory(self.root, expected)

    def test_original_windows_and_posix_paths_relocate_without_escape(self):
        for origin, good, escaped, traversal in (
                ('C:/original/probe', 'C:/original/probe/native/raw.txt', 'C:/outside/raw.txt',
                 'C:/original/probe/native/../../outside.txt'),
                ('/original/probe', '/original/probe/native/raw.txt', '/outside/raw.txt',
                 '/original/probe/native/../../outside.txt')):
            with self.subTest(origin=origin):
                self.assertEqual(reader.original_file(self.root, origin, good), self.root/'native/raw.txt')
                for bad in (escaped, traversal):
                    with self.assertRaises(ValueError):
                        reader.original_file(self.root, origin, bad)


class FrozenEsdLauncherTests(unittest.TestCase):
    def test_candidate_inventory_and_bytes_match_real_git_objects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            app = root/'icstudio'
            app.mkdir()
            (root/'scripts').mkdir()
            paths = ['icstudio/__init__.py', 'icstudio/device.py', 'icstudio/build_info.py']
            paths += ['scripts/'+name for name in (
                'qualify_installed_sky130_esd.py', 'verify_frozen_esd.py',
                'audit_sky130_esd_nvt.py', 'prepare_sky130_esd_nvt.py', 'sky130_pw2dn_source.py',
                'installed_mim_inputs.py', 'verify_frozen_mim.py')]
            for name in paths:
                (root/name).write_text('# '+name+'\n', encoding='utf-8', newline='\n')
            # This repository exists only inside the test's fresh temporary root.
            def git(*arguments):
                return subprocess.run(
                    ['git', '-c', 'user.name=ESD test', '-c', 'user.email=fixture@example.invalid',
                     '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath='+str(root/'no-hooks'),
                     *arguments], cwd=root, env=launcher.git_environment(), check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
            git('init', '-q')
            git('add', 'icstudio', 'scripts')
            git('commit', '-q', '-m', 'temporary fixture')
            commit = git('rev-parse', 'HEAD').decode().strip()
            sources = launcher.candidate_files(root, commit)
            self.assertNotIn('icstudio/build_info.py', sources)
            with patch.object(launcher.runtime_inputs, 'ROOT', root):
                launcher.runtime_inputs.candidate_sources(sources, commit)
            original = (app/'device.py').read_bytes()
            (app/'device.py').unlink()
            with self.assertRaisesRegex(ValueError, 'inventory differs'):
                launcher.candidate_files(root, commit)
            (app/'device.py').write_bytes(original)
            (app/'unexpected.py').write_text('# unexpected\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'inventory differs'):
                launcher.candidate_files(root, commit)
            (app/'unexpected.py').unlink()
            (app/'device.py').write_text('# changed candidate bytes\n', encoding='utf-8')
            changed = launcher.candidate_files(root, commit)
            with patch.object(launcher.runtime_inputs, 'ROOT', root), self.assertRaisesRegex(
                    ValueError, 'differs from candidate'):
                launcher.runtime_inputs.candidate_sources(changed, commit)

    def test_output_cannot_modify_selected_deliverable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            executable = root/'studio'
            executable.write_bytes(b'fixture')
            out = root/'evidence'
            with patch.object(launcher, 'candidate_files') as candidates:
                with self.assertRaisesRegex(ValueError, 'outside the selected deliverable'):
                    launcher.verify(executable, out, '1'*40)
            candidates.assert_not_called()
            self.assertFalse(out.exists())

    def test_probe_receipt_binds_completion_and_actual_log(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            def completed(command, **kwargs):
                kwargs['stdout'].write(b'completed fixture output\n')
                return subprocess.CompletedProcess(command, 0)
            with patch.object(launcher.subprocess, 'run', side_effect=completed):
                launcher.run_probe(['fixture'], root, {}, .1, {'command': ['fixture']})
            receipt = reader.load(root/'invocation.json')
            self.assertEqual(receipt['status'], 'PASS')
            self.assertEqual(receipt['returncode'], 0)
            self.assertEqual(receipt['launcher_log_sha256'], reader.sha(root/'launcher.log'))
            self.assertLessEqual(receipt['started_utc'], receipt['ended_utc'])
            self.assertGreaterEqual(receipt['elapsed_seconds'], 0)

    def test_launch_failure_and_timeout_never_create_acceptance(self):
        for error in (subprocess.CalledProcessError(7, ['fixture']),
                      subprocess.TimeoutExpired(['fixture'], .1)):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                executable = root/'bundle'/'studio'
                executable.parent.mkdir()
                executable.write_bytes(b'fixture executable')
                engine = executable.parent/'_internal/icstudio/assets/runtime/ngspice'/(
                    'ngspice.exe' if os.name == 'nt' else 'ngspice')
                engine.parent.mkdir(parents=True)
                engine.write_bytes(b'fixture engine')
                digest = '0'*64
                reader.write(engine.parent/'runtime-manifest.json', {'files': {engine.name: digest}})
                out = root/'evidence'
                with ExitStack() as stack:
                    for target, value in (
                        ('candidate_files', {}), ('expected_inputs', {'package_sha256': reader.BASE,
                                                                    'collection_sha256': digest}),
                        ('prepare', None)):
                        stack.enter_context(patch.object(launcher, target, return_value=value))
                    stack.enter_context(patch.object(launcher.runtime_inputs, 'candidate_sources'))
                    stack.enter_context(patch.object(launcher.runtime_inputs, 'native_environment', return_value={}))
                    stack.enter_context(patch.object(launcher.runtime_inputs, 'runtime', return_value={}))
                    stack.enter_context(patch.object(reader, 'package_at', return_value={}))
                    stack.enter_context(patch.object(reader, 'sha', return_value=digest))
                    stack.enter_context(patch.dict(reader.raw_audit.ENGINES, {digest: '46'}))
                    references = stack.enter_context(patch.object(reader, 'references'))
                    audit = stack.enter_context(patch.object(reader, 'audit'))
                    process = stack.enter_context(patch.object(launcher.subprocess, 'run', side_effect=error))
                    with self.assertRaises(type(error)):
                        launcher.verify(executable, out, '1'*40, timeout=.1)
                self.assertEqual(process.call_count, 1)
                references.assert_not_called()
                audit.assert_not_called()
                self.assertFalse((out/'acceptance.json').exists())
                failure = reader.load(out/'failure.json')
                self.assertEqual(failure['status'], 'FAIL')
                self.assertFalse(failure['qualified'])
                self.assertFalse(failure['default_promoted'])
                invocation = reader.load(out/'invocation.json')
                self.assertEqual(invocation['status'], 'TIMEOUT' if isinstance(
                    error, subprocess.TimeoutExpired) else 'FAIL')
                self.assertEqual(invocation['returncode'], getattr(error, 'returncode', None))
                self.assertIn('launcher_log_sha256', invocation)


if __name__ == '__main__':
    unittest.main()
