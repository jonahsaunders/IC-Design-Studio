import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.getting_started import (examples, example_copy, discover_pdks,
                                      default_pdk_roots, readiness, resource_root)
from icstudio.model import file_digest, validate
from icstudio.pdks import PDKRegistry


class GettingStartedTests(unittest.TestCase):
    def test_gallery_is_portable_and_each_copy_has_its_own_history(self):
        entries = examples()
        self.assertGreaterEqual(len(entries), 6)
        self.assertEqual(len({e['id'] for e in entries}), len(entries))
        for entry in entries:
            path = resource_root() / 'examples' / entry['file']
            before = file_digest(path)
            first, second = example_copy(entry), example_copy(entry)
            validate(first)
            self.assertNotEqual(first['id'], second['id'])
            self.assertFalse(first['pdk'].get('package_root'))
            self.assertEqual(file_digest(path), before)
            self.assertTrue(entry['steps'])
        with self.assertRaisesRegex(ValueError, 'inside'):
            example_copy({'file': '../outside.icproj'})

    def test_discovery_finds_multiple_variants_and_wrapped_packages(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, master in [('sky130A', 'sky130.lib.spice'), ('gf180mcuD', 'sm141064.ngspice')]:
                ng = root / name / 'libs.tech/ngspice'; ng.mkdir(parents=True)
                (ng / master).write_text('')
            package = root / 'bundle' / 'teaching'; package.mkdir(parents=True)
            (package / 'package.json').write_text(json.dumps({'schema': 1, 'id': 'teaching', 'revision': 'r1', 'technology': {}, 'files': {}}))
            found, notes = discover_pdks([root, root / 'sky130A'])
            self.assertEqual({p['name'] for p in found}, {'sky130A', 'gf180mcuD', 'teaching'})
            self.assertFalse(notes)
            self.assertEqual(sum(p['kind'] == 'package' for p in found), 1)

    def test_bad_package_does_not_hide_other_candidates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / 'bad').mkdir(); (root / 'bad/package.json').write_text('{')
            ng = root / 'sky130A/libs.tech/ngspice'; ng.mkdir(parents=True); (ng / 'sky130.lib.spice').write_text('')
            found, notes = discover_pdks([root])
            self.assertEqual(len(found), 1); self.assertEqual(len(notes), 1)

    def test_discovery_does_not_crawl_deep_trees(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); ng = root / 'a/b/c/sky130A/libs.tech/ngspice'; ng.mkdir(parents=True)
            (ng / 'sky130.lib.spice').write_text('')
            self.assertEqual(discover_pdks([root]), ([], []))
            self.assertEqual(len(discover_pdks([root / 'a/b/c'])[0]), 1)

    def test_environment_and_ciel_defaults(self):
        paths = default_pdk_roots({'PDK_ROOT': '/pdks', 'PDK': 'gf180mcuD'}, '/user')
        self.assertIn(Path('/pdks/gf180mcuD'), paths)
        self.assertIn(Path('/user/.ciel'), paths)
        self.assertEqual(len(paths), len(set(paths)))

    def test_native_examples_without_labels_still_offer_probes(self):
        from icstudio.spice_program import probes
        p = example_copy(next(e for e in examples() if e['id'] == 'native-divider'))
        for c in p['cells']: c.pop('labels', None)
        self.assertIn('v(out)', probes(p))

    def test_osdi_requirements_and_common_corners_are_explicit(self):
        tech = {'simulation': {'requires_osdi': True, 'includes': [
            {'sections': {'nominal': 'tt', 'slow': 'ss'}}, {'sections': {'nominal': 'typ'}}],
            'catalog': {'good': {}, 'bad': {'unavailable': 'dynamic symbol'}}}}
        status = readiness(tech)
        self.assertEqual(status['corners'], ['nominal'])
        self.assertEqual(status['placeable'], 1)
        self.assertIn('compile and select', status['runtime'])
        self.assertNotIn('ready', status['runtime'].lower())

    def test_managed_install_drops_original_path_and_keeps_license(self):
        import shutil
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); src = root / 'source'
            shutil.copytree(resource_root() / 'examples/pdk-educational', src)
            m = json.loads((src / 'package.json').read_text())
            m['source_root'] = str(root / 'missing-original')
            (src / 'package.json').write_text(json.dumps(m))
            registry = PDKRegistry(root / 'registry'); key = registry.install(src / 'package.json')
            shutil.rmtree(src)
            self.assertNotIn('source_root', registry.verify(key))
            self.assertTrue((registry.root / key / 'LICENSE.txt').is_file())
            self.assertTrue(Path(registry.technology(key)['package_root']).is_dir())
