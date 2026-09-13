"""Included-runtime discovery and isolation from the application's environment."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from icstudio import openems_runtime as runtime


class RuntimeTests(unittest.TestCase):
    def test_missing_saved_path_falls_back_to_relocated_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'App with spaces'/'openems'
            python = runtime.python_path(root); python.parent.mkdir(parents=True); python.touch()
            (root/'runtime.json').write_text(json.dumps({'openems_version': 'test'}))
            with patch.object(runtime, 'bundled_root', return_value=root), patch.dict(os.environ, {}, clear=True):
                found, name = runtime.discover(str(root/'old-installation'))
                self.assertEqual(found, str(python)); self.assertEqual(name, 'Included openEMS')
                self.assertEqual(runtime.runtime_for(found), root)
                self.assertIn('Included openEMS test', runtime.describe(found))
                with patch.dict(os.environ, ICSTUDIO_OPENEMS_PYTHON='explicit-custom-python'):
                    self.assertEqual(runtime.discover()[0], 'explicit-custom-python')

    def test_frozen_runtime_isolates_python_and_native_libraries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root/'runtime.json').write_text('{}')
            python = runtime.python_path(root)
            contaminated = dict(PYTHONHOME='app-python', PYTHONPATH='app-modules',
                                QT_PLUGIN_PATH='app-qt', LD_LIBRARY_PATH='app-libs',
                                LD_LIBRARY_PATH_ORIG='original-libs', PATH='system-bin')
            with patch('sys.frozen', True, create=True):
                env = runtime.environment(python, contaminated)
            self.assertNotIn('PYTHONHOME', env); self.assertNotIn('PYTHONPATH', env)
            self.assertNotIn('QT_PLUGIN_PATH', env); self.assertEqual(env['PYTHONNOUSERSITE'], '1')
            self.assertEqual(env['OPENEMS_INSTALL_PATH'], str(root/'native'))
            self.assertTrue(env['PATH'].startswith(str(root/'native')))
            if os.name != 'nt': self.assertEqual(env['LD_LIBRARY_PATH'], str(root/'native/lib')+os.pathsep+str(root/'python/lib'))
            self.assertEqual(contaminated['PYTHONHOME'], 'app-python')

    def test_custom_interpreter_keeps_its_native_environment(self):
        with patch('sys.frozen', True, create=True):
            env = runtime.environment('/custom/python', dict(LD_LIBRARY_PATH='app', LD_LIBRARY_PATH_ORIG='custom', OPENEMS_INSTALL_PATH='custom-solver'))
        self.assertEqual(env['LD_LIBRARY_PATH'], 'custom')
        self.assertEqual(env['OPENEMS_INSTALL_PATH'], 'custom-solver')


if __name__ == '__main__': unittest.main()
