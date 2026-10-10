"""Both runtime profiles must carry complete, independently verified inputs."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from icstudio import digital_platform
from icstudio.model import clone
from scripts import build_digital_runtime
from tests import test_gf180_connectivity_preparation as fixtures

spec=importlib.util.spec_from_file_location('gf180_bundler',Path(__file__).resolve().parents[1]/'packaging/digital/bundle_platforms.py')
bundler=importlib.util.module_from_spec(spec);spec.loader.exec_module(bundler)


class GF180RuntimeBundleTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.GF180ConnectivityPreparationTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root;self.staging=self.root/'build';self.staging.mkdir()
        self.profiles={name:self.fixture.platform(name) for name in ('gf180','gf180d')}
        for profile in self.profiles.values():profile['directory']='gf180'
        # This fixture replaces only network and raw-deck staging. Actual input
        # authentication and C/D profile attachment are exercised below.
        a=patch.object(bundler,'fetch_gf180',return_value=self.root);a.start();self.addCleanup(a.stop)
        def rules(_,output):shutil.copytree(self.fixture.rules,output)
        b=patch.object(bundler,'prepare_gf180_rules',side_effect=rules);b.start();self.addCleanup(b.stop)

    def test_both_profiles_share_exact_collateral_and_preserve_stack_settings(self):
        before=clone(self.profiles)
        with patch.object(bundler,'prepare_gf180_inputs',wraps=bundler.prepare_gf180_inputs) as prepare:
            result=bundler.gf180_profiles(self.profiles,self.staging)
            self.assertEqual(prepare.call_count,1)
        self.assertEqual(before,self.profiles)
        self.assertEqual(result['gf180']['files'],result['gf180d']['files'])
        self.assertEqual(result['gf180']['fingerprint'],result['gf180d']['fingerprint'])
        for name,profile in result.items():
            digital_platform.verify(profile)
            self.assertEqual(profile['orfs'],before[name]['orfs'])
            self.assertEqual(set(profile['lvs_reference']['masters']),set(profile['gf180_connectivity']['masters']))
            self.assertTrue(any(item['path'].endswith('/library/LICENSE') for item in profile['files']))
            self.assertTrue(any(item['path'].endswith('/rules/LICENSE') for item in profile['files']))

    def test_wrong_second_stack_cannot_return_a_partial_configured_catalog(self):
        self.profiles['gf180d']['orfs']['variables']['KVALUE']='9'
        with self.assertRaisesRegex(ValueError,'matching 9-track'):
            bundler.gf180_profiles(self.profiles,self.staging)
        self.assertTrue(all('gf180_connectivity' not in p for p in self.profiles.values()))

    def test_changed_source_aborts_the_profile_build(self):
        (self.fixture.library/self.fixture.gds).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'differs from its lock'):
            bundler.gf180_profiles(self.profiles,self.staging)
        self.assertFalse((self.fixture.base/'gf180/verification').exists())

    def test_missing_rule_aborts_before_profiles_are_configured(self):
        (self.fixture.rules/'klayout/lvs/gf180mcu.lvs').unlink()
        with self.assertRaises(FileNotFoundError):
            bundler.gf180_profiles(self.profiles,self.staging)
        self.assertTrue(all('gf180_connectivity' not in p for p in self.profiles.values()))
        self.assertFalse((self.fixture.base/'gf180/verification').exists())

    def test_runtime_build_context_has_every_required_script_lock_and_docker_input(self):
        class ContextChecked(Exception):pass
        def inspect(command,**kwargs):
            self.assertEqual(command[:2],['docker','build']);context=Path(command[-1])
            scripts=('fetch_gf180_connectivity.py','prepare_gf180_connectivity.py','prepare_gf180_lvs.py','gf180_cdl_diodes.py')
            locks=('gf180-connectivity-library-lock.json','gf180-lvs-source-lock.json')
            for name in scripts:self.assertTrue((context/'scripts'/name).is_file(),name)
            docker=(context/'Dockerfile').read_text(encoding='utf-8')
            for name in locks:
                self.assertTrue((context/'examples'/name).is_file(),name)
                self.assertIn('examples/'+name,docker)
            self.assertIn('COPY scripts /tmp/studio/scripts',docker)
            raise ContextChecked()
        with tempfile.TemporaryDirectory() as td,patch.object(build_digital_runtime.subprocess,'run',side_effect=inspect):
            with self.assertRaises(ContextChecked):build_digital_runtime.build(td)


if __name__=='__main__':unittest.main()
