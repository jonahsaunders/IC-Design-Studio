"""Rule staging rejects stale inputs and preserves attributed, auditable changes."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import prepare_gf180_lvs as prepare


class GF180LVSPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'upstream'
        self.output = self.root / 'staged'
        self.files = {
            'LICENSE': b'Synthetic license fixture; not foundry evidence.\n',
            'AUTHORS': b'Synthetic author fixture.\n',
            prepare.ENTRY: b'# Original header\nsource($input)\ncompare\n# Original footer\n',
            prepare.CONNECTIONS: b'# Original header\nconnect(sub, ptap)\nconnect_global(sub, substrate_name)\nconnect_implicit(\'*\')\n',
            'klayout/lvs/rule_decks/mos_extraction.lvs': b'# Unchanged physical device extraction.\n',
        }
        for name, data in self.files.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.lock_path = self.root / 'lock.json'
        self.lock = dict(repository='synthetic-test-fixture', revision='a' * 40,
                         files={name: hashlib.sha256(data).hexdigest() for name, data in self.files.items()})
        self.write_lock()
        self.addCleanup(patch.stopall)
        patch.object(prepare, 'LOCK', self.lock_path).start()

    def write_lock(self):
        self.lock_path.write_text(json.dumps(self.lock), encoding='utf-8')

    def test_source_preserved_and_only_reviewed_rules_change(self):
        result = prepare.prepare(self.source, self.output)
        self.assertEqual(result['status'], 'prepared_not_qualified')
        self.assertFalse(result['qualified'])
        changed = {name for name, item in result['files'].items() if item['changed']}
        self.assertEqual(changed, {prepare.ENTRY, prepare.CONNECTIONS})
        for name, original in self.files.items():
            self.assertEqual((self.source / name).read_bytes(), original)
            target = (self.output / name).read_bytes()
            self.assertEqual(hashlib.sha256(target).hexdigest(), result['files'][name]['staged_sha256'])
            if name not in changed:
                self.assertEqual(target, original)
        connections = (self.output / prepare.CONNECTIONS).read_text()
        self.assertIn('connect(sub, ptap)', connections)
        self.assertIn('soft_connect_global(ptap, substrate_name)', connections)
        self.assertIn('top_level(true)', connections)
        self.assertNotIn("connect_implicit('*')", connections)
        main = (self.output / prepare.ENTRY).read_text()
        self.assertLess(main.index('icstudio_gf180_diode_geometry(nl).join'), main.index('\ncompare\n'))
        self.assertEqual(json.loads((self.output / 'recipe.json').read_text()), result)

    def test_unmodified_dependency_tampering_is_rejected_before_output(self):
        path = self.source / 'klayout/lvs/rule_decks/mos_extraction.lvs'
        path.write_bytes(path.read_bytes() + b'# Unreviewed change\n')
        with self.assertRaisesRegex(ValueError, 'pinned revision'):
            prepare.prepare(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_directory_and_results_are_preserved(self):
        self.output.mkdir()
        marker = self.output / 'prior-report.json'
        marker.write_bytes(b'important prior evidence')
        with self.assertRaisesRegex(ValueError, 'existing results'):
            prepare.prepare(self.source, self.output)
        self.assertEqual(marker.read_bytes(), b'important prior evidence')

    def test_source_subdirectory_cannot_be_staging_destination(self):
        with self.assertRaisesRegex(ValueError, 'separately'):
            prepare.prepare(self.source, self.source / 'new-rules')
        self.assertFalse((self.source / 'new-rules').exists())

    def test_missing_source_preserves_no_incomplete_output(self):
        (self.source / 'AUTHORS').unlink()
        with self.assertRaises(FileNotFoundError):
            prepare.prepare(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_license_is_required_in_the_lock(self):
        del self.lock['files']['LICENSE']
        self.write_lock()
        with self.assertRaisesRegex(ValueError, 'attribution'):
            prepare.prepare(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_escaping_lock_path_is_rejected(self):
        self.lock['files']['../outside'] = 'a' * 64
        self.write_lock()
        with self.assertRaisesRegex(ValueError, 'source-lock path'):
            prepare.prepare(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_changed_or_repeated_connection_policy_is_not_guessed(self):
        original = self.files[prepare.CONNECTIONS].decode()
        for modified in (original.replace("connect_implicit('*')", "connect_implicit('VSS')"),
                         original + "connect_implicit('*')\n", original + 'top_level(false)\n',
                         original + 'soft_connect_global(ptap, substrate_name)\n'):
            with self.subTest(modified=modified), self.assertRaises(ValueError):
                prepare.patch_connections(modified)

    def test_changed_comparison_section_is_rejected(self):
        original = self.files[prepare.ENTRY].decode()
        for modified in (original.replace('\ncompare\n', '\ncompare(false)\n'),
                         original + '\ncompare\n', prepare.patch_comparison(original)):
            with self.subTest(modified=modified), self.assertRaises(ValueError):
                prepare.patch_comparison(modified)


if __name__ == '__main__':
    unittest.main()
