"""Geometry corrections preserve source locks and cannot reuse old checkpoints."""
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from icstudio import digital, digital_identity, digital_platform, digital_recipes
from icstudio.model import atomic_write, clone, digest, file_digest

FIXTURES = Path(__file__).parent / 'fixtures/gf180-recipes'


class GeometryRecipeTests(unittest.TestCase):
    def fixture(self, root):
        folder = root / 'source/gf180'; folder.mkdir(parents=True)
        (folder / 'cells.lib').write_text('library (fixture) {}\n')
        for recipe, name in zip(digital_recipes.PATCHES, ('pdn.cfg', 'tapcell.tcl')):
            target = folder / recipe['path']; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(FIXTURES / name, target)
            self.assertEqual(file_digest(target), recipe['source_sha256'])
        records = digital_platform.inventory(folder.parent,
            [p.relative_to(folder.parent).as_posix() for p in folder.rglob('*') if p.is_file()])
        platform = {'version': 1, 'name': 'gf180', 'directory': 'gf180', 'root': str(folder.parent),
            'revision': 'Pinned recipe fixture', 'corner': 'typical', 'corners': {'typical': ['gf180/cells.lib']},
            'files': records, 'fingerprint': digest(records),
            'orfs': {'variables': clone(digital_recipes.GF180_VARIABLES), 'geometry_recipe': digital_recipes.GF180_C}}
        digital_platform.stage(platform, root / 'run/platform')
        artifacts = {}
        runner = SimpleNamespace(root=root / 'run', platform=platform)
        runner.add_artifact = lambda key, path: artifacts.update({key: Path(path)})
        def save(key, data, name):
            path = runner.root / name; atomic_write(path, json.dumps(data)); runner.add_artifact(key, path)
        runner.save_json = save
        return runner, artifacts

    def test_generated_files_are_exact_corrections_and_sources_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            runner, artifacts = self.fixture(Path(td)); original = clone(runner.platform)
            commands = digital_recipes.generate(runner, {})
            self.assertEqual([c.split('=')[0] for c in commands], ['PDN_TCL', 'TAPCELL_TCL'])
            for recipe in digital_recipes.PATCHES:
                source = runner.root / 'platform/gf180' / recipe['path']
                generated = artifacts['platform_recipe_' + recipe['name']]
                self.assertEqual(file_digest(source), recipe['source_sha256'])
                self.assertEqual(file_digest(generated), recipe['result_sha256'])
                self.assertEqual(generated.read_text(), source.read_text().replace(recipe['before'], recipe['after']))
            self.assertEqual(runner.platform, original)
            digital_platform.verify(original)
            record = json.loads(artifacts['platform_geometry_recipe'].read_text())
            self.assertEqual([c['status'] for c in record['changes']], ['generated', 'generated'])

    def test_custom_pdn_is_preserved_and_tap_correction_is_retained(self):
        with tempfile.TemporaryDirectory() as td:
            runner, artifacts = self.fixture(Path(td))
            commands = digital_recipes.generate(runner, {'pdn_tcl': 'custom power network'})
            self.assertEqual([c.split('=')[0] for c in commands], ['TAPCELL_TCL'])
            self.assertNotIn('platform_recipe_pdn', artifacts)
            self.assertEqual(json.loads(artifacts['platform_geometry_recipe'].read_text())['changes'][0]['status'], 'user_override')

    def test_already_corrected_locked_sources_are_not_patched_twice(self):
        with tempfile.TemporaryDirectory() as td:
            runner, artifacts = self.fixture(Path(td))
            source_root = Path(runner.platform['root'])
            for recipe in digital_recipes.PATCHES:
                path = source_root / 'gf180' / recipe['path']
                atomic_write(path, path.read_text().replace(recipe['before'], recipe['after']))
            runner.platform['files'] = digital_platform.inventory(source_root,
                [r['path'] for r in runner.platform['files']])
            runner.platform['fingerprint'] = digest(runner.platform['files'])
            digital_platform.stage(runner.platform, runner.root / 'platform')
            digital_recipes.generate(runner, {})
            for recipe in digital_recipes.PATCHES:
                self.assertEqual(file_digest(artifacts['platform_recipe_' + recipe['name']]), recipe['result_sha256'])
            digital_platform.verify(runner.platform)

    def test_missing_stale_or_wrong_stack_recipe_cannot_run(self):
        with tempfile.TemporaryDirectory() as td:
            runner, _ = self.fixture(Path(td))
            for change in ('unknown', 'stack', 'variant', 'source'):
                platform = clone(runner.platform)
                if change == 'unknown': platform['orfs']['geometry_recipe'] = 'unknown'
                elif change == 'stack': platform['orfs']['variables']['KVALUE'] = '11'
                elif change == 'variant': platform['name'] = 'another'
                else: platform['files'] = [r for r in platform['files'] if not r['path'].endswith('tapcell.tcl')]
                with self.subTest(change=change), self.assertRaises(ValueError):
                    digital_recipes.validate(platform)
            source = runner.root / 'platform/gf180' / digital_recipes.PATCHES[0]['path']
            source.write_text('changed power-grid source')
            with self.assertRaisesRegex(ValueError, 'source changed'):
                digital_recipes.generate(runner, {})

    def test_recipe_selection_invalidates_physical_checkpoints(self):
        with tempfile.TemporaryDirectory() as td:
            runner, _ = self.fixture(Path(td)); config = digital.counter_project()['digital']
            config['platform'] = runner.platform
            legacy = clone(config); legacy['platform']['orfs'].pop('geometry_recipe')
            for stage in digital_identity.PHYSICAL:
                self.assertNotEqual(digital_identity.stage_key(config, stage), digital_identity.stage_key(legacy, stage))
            self.assertEqual(digital_identity.stage_key(config, 'simulate'), digital_identity.stage_key(legacy, 'simulate'))
            runner.platform = legacy['platform']
            self.assertEqual(digital_recipes.generate(runner, {}), [])

    def test_imported_default_uses_the_recipe_without_modifying_checkout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); runner, _ = self.fixture(root)
            checkout = root / 'orfs'; folder = checkout / 'flow/platforms/gf180'
            shutil.copytree(Path(runner.platform['root']) / 'gf180', folder)
            profile = clone(digital_platform.ORFS_PROFILES['gf180'])
            profile['corners'] = {'typical': ['cells.lib']}
            profile['orfs'].pop('rc_file'); profile['orfs'].pop('rc_vias')
            profile['orfs']['corners'] = {'typical': {'CORNER': 'TC'}}
            before = {p.relative_to(folder).as_posix(): file_digest(p) for p in folder.rglob('*') if p.is_file()}
            with patch.dict(digital_platform.ORFS_PROFILES, {'gf180': profile}), \
                    patch('subprocess.run', side_effect=[SimpleNamespace(stdout='e'*40), SimpleNamespace(stdout='')]):
                imported = digital_platform.from_orfs(checkout, 'gf180')
            self.assertEqual(imported['orfs']['geometry_recipe'], digital_recipes.GF180_C)
            self.assertEqual(before, {p.relative_to(folder).as_posix(): file_digest(p) for p in folder.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
