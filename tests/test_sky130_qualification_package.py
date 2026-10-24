"""The historical physical fixture must survive live importer improvements."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from icstudio.model import digest, file_digest
from scripts import prepare_sky130_qualification as recipe


class LockedPhysicalManifestTests(unittest.TestCase):
    def test_retained_manifest_is_the_original_qualification_identity(self):
        manifest, content = recipe.locked_manifest()
        self.assertEqual(hashlib.sha256(content).hexdigest(),
                         '531c0a4263b839b693d171ad223d01f1484130113f0fcb9010bf99b4c2da9417')
        self.assertEqual(manifest['revision'], '9a491f0ebd51a0aa')
        self.assertEqual(len(manifest['files']), 441)
        # A historical unavailable binding stays historical; current packages
        # have a separately versioned fix and must not be relabelled as this one.
        entry = manifest['technology']['simulation']['catalog']['sky130_fd_pr/res_generic_li.sym']
        self.assertTrue(entry['unavailable'])
        current = json.loads((recipe.ROOT/'icstudio/assets/pdks/sky130A/package.json').read_bytes())
        self.assertFalse(current['technology']['simulation']['catalog']['sky130_fd_pr/res_generic_li.sym']['unavailable'])


class QualificationPreparationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.source = self.root/'input/sky130A'
        self.source.mkdir(parents=True)
        self.output = self.root/'output'
        license_path = self.source/'libs.tech/xschem/LICENSE'
        license_path.parent.mkdir(parents=True)
        license_path.write_bytes(b'fixture license\n')
        (self.source/'model.spice').write_bytes(b'.model fixture R (rsh=1)\n')
        upstream = json.loads((recipe.ROOT/'examples/sky130-reference-assets.json').read_bytes())
        upstream['files'] = {k:v for k,v in upstream['files'].items()
                             if k in ('common.tar.zst', 'sky130_fd_pr.tar.zst')}
        (self.source.parent/'upstream-lock.json').write_text(json.dumps(upstream), encoding='utf-8')
        self.manifest = {'id':'sky130A', 'revision':'fixture',
                         'technology':{'revision':'fixture'},
                         'files':{'model.spice':file_digest(self.source/'model.spice')}}
        self.manifest_path = self.root/'package.json'
        self.lock_path = self.root/'lock.json'
        self.save_manifest()
        self.enterContext(patch.object(recipe, 'MANIFEST', self.manifest_path))
        self.enterContext(patch.object(recipe, 'LOCK', self.lock_path))

    def save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding='utf-8')
        self.lock_path.write_text(json.dumps({
            'id':'sky130A', 'revision':'fixture',
            'manifest_sha256':file_digest(self.manifest_path),
            'files_hash':digest(self.manifest['files'])}), encoding='utf-8')

    def test_reproduction_never_depends_on_current_scanner(self):
        with patch('icstudio.pdk_import.scan_local', side_effect=AssertionError('live scanner used')):
            result = recipe.prepare(self.source, self.output)
        self.assertEqual(result['manifest_sha256'], file_digest(self.manifest_path))
        self.assertEqual((self.output/'package.json').read_bytes(), self.manifest_path.read_bytes())
        self.assertEqual((self.output/'model.spice').read_bytes(), (self.source/'model.spice').read_bytes())

    def test_changed_and_missing_assets_fail_before_output_creation(self):
        (self.source/'model.spice').write_bytes(b'changed model')
        with self.assertRaisesRegex(ValueError, 'Source differs'):
            recipe.prepare(self.source, self.output)
        self.assertFalse(self.output.exists())
        (self.source/'model.spice').unlink()
        with self.assertRaisesRegex(ValueError, 'Source differs'):
            recipe.prepare(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_changed_retained_metadata_fails_its_original_lock(self):
        self.manifest_path.write_bytes(self.manifest_path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError, 'retained adapter differs'):
            recipe.prepare(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_inconsistent_identity_is_rejected(self):
        lock = json.loads(self.lock_path.read_bytes())
        for field in ('id','revision','files_hash'):
            with self.subTest(field=field):
                self.lock_path.write_text(json.dumps({**lock,field:'wrong'}), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'identity differs'):
                    recipe.prepare(self.source, self.output)
                self.assertFalse(self.output.exists())

    def test_changed_upstream_provenance_is_rejected(self):
        (self.source.parent/'upstream-lock.json').write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'upstream provenance differs'):
            recipe.prepare(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_outside_asset_is_rejected_even_with_matching_hash(self):
        outside = self.source.parent/'outside.spice'
        outside.write_bytes(b'model')
        self.manifest['files'] = {'../outside.spice':file_digest(outside)}
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'Unsafe qualification asset path'):
            recipe.prepare(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_preexisting_output_is_preserved(self):
        self.output.mkdir()
        (self.output/'keep').write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'new adapter output'):
            recipe.prepare(self.source, self.output)
        self.assertEqual((self.output/'keep').read_bytes(), b'keep')

    def test_source_is_rechecked_after_validation(self):
        original = recipe.manifest_for
        def changed(source):
            result = original(source)
            (source/'model.spice').write_bytes(b'changed after validation')
            return result
        with patch.object(recipe, 'manifest_for', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'Source changed during preparation'):
                recipe.prepare(self.source, self.output)
        self.assertFalse((self.output/'package.json').exists())


if __name__ == '__main__':
    unittest.main()
