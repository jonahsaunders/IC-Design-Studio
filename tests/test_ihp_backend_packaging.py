import ast
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from icstudio import ihp_klayout_drc as drc, ihp_klayout_lvs as lvs
from icstudio.model import file_digest
from scripts import stage_ihp_backend_assets as packaging

ROOT = Path(__file__).resolve().parents[1]


class IhpBackendPackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_real_release_stage_contains_exact_tracked_bundles_and_notices(self):
        target = self.root / 'backend'
        source = self.root / 'source'
        source.mkdir()
        (source / 'digital_backend.py').write_text('# test source\n')
        packaging.stage(source, target)
        for name, module in (('ihp_klayout_lvs', lvs), ('ihp_klayout_drc', drc)):
            prefix = 'icstudio/assets/physical/' + name + '/'
            expected = set(module.assets()) | ({'README.md'} if module is lvs else set())
            staged = target / 'assets/physical' / name
            actual = set()
            for folder, dirs, files in os.walk(staged, topdown=True, followlinks=False):
                self.assertNotIn('tmpuxoell2b', dirs)
                self.assertNotIn('tmpuxoell2b', files)
                for filename in files:
                    actual.add((Path(folder) / filename).relative_to(staged).as_posix())
            self.assertEqual(actual, expected)
            for member in expected:
                self.assertNotIn('tmpuxoell2b', Path(member).parts)
                self.assertEqual(file_digest(ROOT / prefix / member), file_digest(staged / member))
            self.assertTrue((target / 'assets/physical' / name / 'LICENSE').is_file())
        self.assertTrue((target / 'digital_backend.py').is_file())

    def test_package_entry_calls_the_tested_release_stage(self):
        tree = ast.parse((ROOT / 'scripts/package.py').read_text(encoding='utf-8'))
        imports = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == 'stage_ihp_backend_assets']
        self.assertEqual(len(imports), 1)
        self.assertEqual([(a.name, a.asname) for a in imports[0].names], [('stage', 'stage_release_backend')])
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == 'stage_release_backend']
        self.assertEqual(len(calls), 1)
        self.assertEqual([ast.unparse(a) for a in calls[0].args],
                         ["root / 'icstudio'", "digital_target / 'backend/icstudio'"])

    def test_missing_lvs_license_and_changed_readme_are_rejected(self):
        for name in ('LICENSE', 'README.md'):
            with self.subTest(name=name), tempfile.TemporaryDirectory(dir=self.root) as folder:
                # Build separate source fixtures from the locked original files.
                bundle = Path(folder) / 'lvs'
                for item, source in lvs.assets().items():
                    if name == 'LICENSE' and item == 'LICENSE': continue
                    dest = bundle / item; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, dest)
                shutil.copyfile(lvs.SOURCE / 'README.md', bundle / 'README.md')
                if name == 'README.md': (bundle / name).write_text('changed')
                with mock.patch.object(lvs, 'SOURCE', bundle):
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        packaging.stage(ROOT / 'icstudio', Path(folder) / 'backend')

    def test_changed_drc_deck_and_notice_are_rejected(self):
        for name in ('ihp-sg13g2.drc', 'LICENSE'):
            with self.subTest(name=name), tempfile.TemporaryDirectory(dir=self.root) as folder:
                bundle = Path(folder) / 'drc'
                for item, source in drc.assets().items():
                    dest = bundle / item; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, dest)
                (bundle / name).write_text('changed')
                with mock.patch.object(drc, 'SOURCE', bundle):
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        packaging.stage(ROOT / 'icstudio', Path(folder) / 'backend')

    def test_source_readme_changed_during_staging_cannot_match_its_copy(self):
        bundle = self.root / 'lvs'
        for name, source in lvs.assets().items():
            dest = bundle / name; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, dest)
        shutil.copyfile(lvs.SOURCE / 'README.md', bundle / 'README.md')
        def mutate(_source, destination):
            Path(destination).mkdir()
            (bundle / 'README.md').write_text('changed during staging')
        with mock.patch.object(lvs, 'SOURCE', bundle), mock.patch.object(packaging, 'stage_backend', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'IHP package dependency changed: README.md'):
                packaging.stage(ROOT / 'icstudio', self.root / 'backend')

    def test_unexpected_output_entry_is_rejected(self):
        output = self.root / 'output'
        output.mkdir()
        (output / 'unexpected').mkdir()
        with self.assertRaisesRegex(ValueError, 'Unexpected IHP package dependency name'):
            packaging._inventory(output, {'LICENSE'})


if __name__ == '__main__':
    unittest.main()
