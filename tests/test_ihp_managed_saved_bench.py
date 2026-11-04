"""Keep automatic IHP models on the normal managed physical worker route."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from icstudio import physical_backend
from icstudio.model import example
from scripts.qualify_standard_mos import load_technology


MODELS = ('psp103', 'psp103_nqs', 'r3_cmc', 'mosvar', 'cap_cmomi', 'cap_cmomf')
DEPENDENCY = 'psp103/psp103.va'
RUNTIME = {'kind': 'wsl', 'sha256': 'a' * 64}


class IhpManagedSavedBenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tech = load_technology('ihp-sg13g2')[0]
        cls.manifest = {'osdi': {'ihp-sg13g2': {
            'system': 'Linux', 'machine': 'x86_64', 'cpu_target': 'generic',
            'models': [{'output': name + '.osdi', 'sha256': str(i) * 64,
                        'dependencies': {DEPENDENCY: cls.tech['package_lock']['files'][
                            'libs.tech/verilog-a/' + DEPENDENCY]}}
                       for i, name in enumerate(MODELS, 1)],
        }}}

    def job(self, **settings):
        project = example('empty')
        project['pdk'] = deepcopy(self.tech)
        return {'project': project, 'cell': project['top'], 'engine': 'builtin',
                'settings': {'type': 'silicon', 'testbench': 'saved',
                             'physical_toolchain': 'included', **settings}}

    def prepare(self, job, manifest):
        with (patch.object(physical_backend, 'available', return_value=RUNTIME),
              patch('icstudio.digital_runtime.manifest', return_value=manifest)):
            return physical_backend.prepare(job)

    def test_exact_models_attach_only_to_native_project_and_keep_silicon_route(self):
        job = self.job()
        job['project']['simulation_runtime'] = {'metadata': 'preserved'}
        original = deepcopy(job['project'])
        self.assertIs(self.prepare(job, self.manifest), job)
        self.assertEqual(job['settings']['physical_runtime'], RUNTIME)
        self.assertEqual(job['project'], original)
        self.assertNotIn('managed_osdi', job['settings'])
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            with patch('icstudio.digital_runtime.manifest', return_value=self.manifest):
                staged = physical_backend.stage(job, work, '/var/tmp/test', '/')
            models = staged['project']['simulation_runtime']['osdi']
            self.assertEqual(models, [
                {'path': '/opt/icstudio/osdi/ihp-sg13g2/' + name + '.osdi',
                 'sha256': str(i) * 64, 'system': 'Linux', 'machine': 'x86_64'}
                for i, name in enumerate(MODELS, 1)
            ])
            self.assertEqual(staged['project']['simulation_runtime']['metadata'], 'preserved')
            self.assertEqual(job['project'], original)
            self.assertNotIn('managed_osdi', staged['settings'])
            self.assertNotIn('executable', staged)
            (work / 'native-input.json').write_text(json.dumps(staged))
            with patch('icstudio.silicon_flow.job', return_value={'schema': 1}) as silicon:
                physical_backend.native_run(work)
            silicon.assert_called_once()
            self.assertEqual(silicon.call_args.args[:3],
                             (staged['project'], staged['cell'], staged['settings']))

    def test_missing_and_changed_model_manifests_block_before_handoff(self):
        altered = deepcopy(self.manifest)
        altered['osdi']['ihp-sg13g2']['models'][0]['dependencies'][DEPENDENCY] = 'e' * 64
        for manifest, message in (({}, 'current included physical tools'),
                                  (altered, 'do not match this PDK revision')):
            with self.subTest(message=message):
                job = self.job()
                self.prepare(job, manifest)
                self.assertNotIn('physical_runtime', job['settings'])
                self.assertIn(message, job['settings']['physical_blocked_reason'])
        job = self.prepare(self.job(), self.manifest)
        with (tempfile.TemporaryDirectory() as temporary,
              patch('icstudio.digital_runtime.manifest', return_value=altered),
              self.assertRaisesRegex(ValueError, 'do not match this PDK revision')):
            physical_backend.stage(job, Path(temporary), '/var/tmp/test', '/')

    def test_drc_lvs_only_and_explicit_models_do_not_read_bundled_model_manifest(self):
        explicit = {'osdi': [{'path': '/explicit/broken.osdi', 'system': 'Windows'}]}
        job = self.job()
        job['project']['simulation_runtime'] = explicit
        for request in (self.job(verification_mode='drc_lvs'), job):
            with (patch.object(physical_backend, 'available', return_value=RUNTIME),
                  patch('icstudio.digital_runtime.manifest', side_effect=AssertionError),
                  tempfile.TemporaryDirectory() as temporary):
                physical_backend.prepare(request)
                staged = physical_backend.stage(request, Path(temporary), '/var/tmp/test', '/')
            self.assertEqual(staged['project'].get('simulation_runtime'),
                             request['project'].get('simulation_runtime'))
            self.assertNotIn('managed_osdi', staged['settings'])

    def test_custom_and_non_ihp_selection_keep_existing_policy(self):
        custom = self.job(physical_toolchain='custom')
        other = self.job()
        other['project']['pdk']['package_lock']['id'] = 'third-party-process'
        with (patch.object(physical_backend, 'available', return_value=RUNTIME),
              patch('icstudio.digital_runtime.manifest', side_effect=AssertionError)):
            physical_backend.prepare(custom)
            physical_backend.prepare(other)
        self.assertNotIn('physical_runtime', custom['settings'])
        self.assertEqual(other['settings']['physical_runtime'], RUNTIME)
        self.assertNotIn('simulation_runtime', other['project'])
