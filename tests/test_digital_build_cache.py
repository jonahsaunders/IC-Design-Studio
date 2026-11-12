"""A cached runtime must follow all actual build inputs, not a partial glob list."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_digital_runtime as builder


class DigitalBuildCacheTests(unittest.TestCase):
    FILES = ('Dockerfile', 'compile_ihp_osdi.py', 'scripts/prepare_gf180_lvs.py',
             'examples/gf180-lvs-source-lock.json', 'ihp-pdk/libs.tech/verilog-a/model.va',
             'icstudio/assets/verification/sky130/rules.drc')

    def fixture(self, root, reverse=False):
        for name in reversed(self.FILES) if reverse else self.FILES:
            path = Path(root)/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(name.encode())

    def test_each_helper_model_lock_and_rule_change_invalidates_the_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.fixture(root); first = builder.context_identity(root)
            for name in self.FILES:
                with self.subTest(path=name):
                    path = root/name; original = path.read_bytes(); path.write_bytes(original+b' changed')
                    self.assertNotEqual(builder.context_identity(root)['sha256'], first['sha256'])
                    path.write_bytes(original)
            path = root/self.FILES[-1]; renamed = path.with_name('renamed.drc'); path.rename(renamed)
            self.assertNotEqual(builder.context_identity(root)['sha256'], first['sha256'])
            renamed.unlink(); self.assertNotEqual(builder.context_identity(root)['sha256'], first['sha256'])
            (root/'Dockerfile').unlink()
            with self.assertRaisesRegex(ValueError, 'Incomplete'): builder.context_identity(root)

    def test_root_order_and_timestamps_do_not_change_the_source_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); a = root/'one'; b = root/'two'
            self.fixture(a); self.fixture(b, reverse=True)
            for path in b.rglob('*'):
                if path.is_file(): os.utime(path, (1000000000, 1000000000))
            self.assertEqual(builder.context_identity(a), builder.context_identity(b))

    def test_changed_inputs_stop_before_docker_and_matching_inputs_are_recorded(self):
        class Inspected(Exception): pass
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.fixture(root/'reference')
            identity = builder.context_identity(root/'reference')
            with patch.object(builder, 'stage_context', side_effect=self.fixture), patch.object(builder.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'inputs changed'):
                    builder.build(root/'rejected', expected_cache_key='0'*64)
                run.assert_not_called()
            def inspect(command, **kwargs):
                self.assertEqual(command[:2], ['docker', 'build'])
                self.assertEqual(builder.context_identity(command[-1]), identity)
                self.assertEqual(json.loads((root/'accepted/build-inputs.json').read_bytes()), identity)
                raise Inspected()
            with patch.object(builder, 'stage_context', side_effect=self.fixture), patch.object(builder.subprocess, 'run', side_effect=inspect):
                with self.assertRaises(Inspected): builder.build(root/'accepted', expected_cache_key=identity['sha256'])

    def test_real_staged_identity_covers_previously_omitted_input_families(self):
        result = builder.cache_identity(); paths = set(result['files'])
        self.assertIn('compile_ihp_osdi.py', paths)
        self.assertIn('scripts/prepare_gf180_lvs.py', paths)
        self.assertIn('scripts/prepare_ihp_fill.py', paths)
        self.assertIn('examples/gf180-lvs-source-lock.json', paths)
        self.assertIn('examples/ihp-fill-source-lock.json', paths)
        self.assertTrue(any(p.startswith('ihp-pdk/libs.tech/verilog-a/') for p in paths))
        self.assertTrue(any(p.startswith('icstudio/assets/verification/sky130/') for p in paths))
        self.assertTrue(any(p.startswith('docs/qualification/') for p in paths))
        self.assertFalse(any('__pycache__' in Path(p).parts or Path(p).suffix in ('.pyc', '.pyo') for p in paths))

    def test_generated_packaging_bytecode_never_enters_the_build_context(self):
        # Exercise the real copy policy on a disposable packaging source. Stop
        # before staging unrelated inputs; no repository source is modified.
        class Copied(Exception): pass
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/'source/packaging/digital'
            (source/'__pycache__').mkdir(parents=True)
            (source/'__pycache__/bundle_platforms.cpython-312.pyc').write_bytes(b'host-specific bytecode')
            (source/'legacy.pyc').write_bytes(b'old cache')
            (source/'legacy.pyo').write_bytes(b'old optimized cache')
            (source/'Dockerfile').write_bytes(b'FROM scratch\n')
            target = root/'target'; target.mkdir()
            with patch.object(builder, 'ROOT', root/'source'), patch.object(builder.shutil, 'copy2', side_effect=Copied):
                with self.assertRaises(Copied): builder.stage_context(target)
            self.assertEqual({p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}, {'Dockerfile'})


if __name__ == '__main__': unittest.main()
