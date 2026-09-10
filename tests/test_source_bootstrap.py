"""Installation-state regressions; subprocess boundaries are simulated, not Windows execution."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

spec=importlib.util.spec_from_file_location('source_bootstrap',Path(__file__).resolve().parents[1]/'scripts/source_bootstrap.py')
bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)


class SourceBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.project=self.root/'Project with spaces';self.project.mkdir()
        (self.project/'requirements.txt').write_text('PySide6-Essentials==6.8.3\nklayout==0.30.5\n')
        self.environment=self.root/'profile/ICStudio/venvs/test';self.calls=[]

    def runner(self,fail=None):
        def run(command,**kwargs):
            self.calls.append(command)
            if '-m' in command and 'venv' in command:
                python=Path(command[-1])/'Scripts/python.exe';python.parent.mkdir(parents=True,exist_ok=True);python.write_text('synthetic interpreter')
            return SimpleNamespace(returncode=1 if fail and fail(command) else 0)
        return run

    def test_deep_project_path_does_not_lengthen_environment(self):
        a=bootstrap.environment_path(self.project,self.root/'profile')
        deep=self.project/('long folder '*10);deep.mkdir();(deep/'requirements.txt').write_text((self.project/'requirements.txt').read_text())
        b=bootstrap.environment_path(deep,self.root/'profile')
        self.assertEqual(len(str(a)),len(str(b)));self.assertNotEqual(a,b)
        self.assertEqual(a,bootstrap.environment_path(self.project,self.root/'profile'))

    def test_failed_install_never_launches_and_retry_repairs_partial_environment(self):
        with self.assertRaisesRegex(RuntimeError,'not started'):
            bootstrap.launch(self.project,self.environment,[],self.runner(lambda cmd:'install' in cmd))
        self.assertTrue((self.environment/'Scripts/python.exe').exists())
        self.assertFalse((self.environment/'icstudio-ready.json').exists())
        self.assertFalse(any(str(self.project/'main.py') in cmd for cmd in self.calls))
        self.calls=[];bootstrap.launch(self.project,self.environment,[],self.runner())
        self.assertTrue(any('--force-reinstall' in cmd for cmd in self.calls))
        self.assertTrue((self.environment/'icstudio-ready.json').exists())
        self.assertEqual(self.calls[-1][1],str(self.project/'main.py'))

    def test_existing_incomplete_install_is_not_trusted_by_executable_or_metadata(self):
        python=self.environment/'Scripts/python.exe';python.parent.mkdir(parents=True);python.write_text('synthetic interpreter')
        metadata=self.environment/'Lib/site-packages/PySide6_Essentials.dist-info';metadata.mkdir(parents=True)
        (metadata/'METADATA').write_text('synthetic partial install')
        bootstrap.prepare(self.project,self.environment,self.runner())
        self.assertTrue(any('--force-reinstall' in cmd for cmd in self.calls))

    def test_successful_launch_reuses_environment_without_running_pip(self):
        bootstrap.prepare(self.project,self.environment,self.runner());self.calls=[]
        arguments=['--project',str(self.root/'example with spaces.icproj')]
        bootstrap.launch(self.project,self.environment,arguments,self.runner())
        self.assertFalse(any('pip' in cmd for cmd in self.calls));self.assertEqual(self.calls[-1][-2:],arguments)

    def test_changed_requirements_invalidates_readiness(self):
        bootstrap.prepare(self.project,self.environment,self.runner());self.calls=[]
        (self.project/'requirements.txt').write_text('klayout==0.30.5\n')
        bootstrap.prepare(self.project,self.environment,self.runner())
        self.assertTrue(any('--force-reinstall' in cmd for cmd in self.calls))
        self.assertEqual(json.loads((self.environment/'icstudio-ready.json').read_text()),bootstrap.fingerprint(self.project))

    def test_simulator_or_models_failure_blocks_gui_and_retries_next_launch(self):
        for script in ('stage_windows_ngspice.py', 'check_simulation_assets.py'):
            self.calls=[]
            with self.subTest(script=script), self.assertRaisesRegex(RuntimeError,'not started'):
                bootstrap.launch(self.project,self.environment,[],self.runner(lambda cmd:any(v.endswith(script) for v in cmd)))
            self.assertFalse(any(str(self.project/'main.py') in cmd for cmd in self.calls))
            self.calls=[]
            bootstrap.launch(self.project,self.environment,[],self.runner())
            self.assertTrue(any(any(v.endswith(script) for v in cmd) for cmd in self.calls))
            self.assertEqual(self.calls[-1][1],str(self.project/'main.py'))

    def test_import_or_dependency_check_failure_never_marks_ready(self):
        for fail in (lambda cmd:cmd[-1]=='check',lambda cmd:'-c' in cmd):
            with self.subTest(fail=fail),self.assertRaises(RuntimeError):bootstrap.prepare(self.project,self.environment,self.runner(fail))
            self.assertFalse((self.environment/'icstudio-ready.json').exists())

    def test_damaged_ready_environment_is_repaired_without_touching_project_venv(self):
        legacy=self.project/'.venv';legacy.mkdir();sentinel=legacy/'keep.txt';sentinel.write_text('do not delete')
        bootstrap.prepare(self.project,self.environment,self.runner());self.calls=[];failed=[False]
        def fail_once(cmd):
            if '-c' in cmd and not failed[0]:failed[0]=True;return True
            return False
        bootstrap.prepare(self.project,self.environment,self.runner(fail_once))
        self.assertTrue(any('--force-reinstall' in cmd for cmd in self.calls));self.assertEqual(sentinel.read_text(),'do not delete')


if __name__=='__main__':unittest.main()
