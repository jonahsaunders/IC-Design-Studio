import tempfile
import unittest
from pathlib import Path

from scripts.check_release import require_release_notes


class ReleaseNotesTests(unittest.TestCase):
    def test_stable_version_requires_its_own_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'docs').mkdir()
            (root / 'docs/UPDATE_0.22_DEV25.md').write_text('Historical preview')
            with self.assertRaisesRegex(ValueError, 'UPDATE_0.23.0.md'):
                require_release_notes('0.23.0', root)
            notes = root / 'docs/UPDATE_0.23.0.md'; notes.write_text('Windows and Linux release')
            self.assertEqual(require_release_notes('0.23.0', root), notes)

    def test_development_notes_keep_the_existing_naming(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'docs').mkdir()
            with self.assertRaisesRegex(ValueError, 'UPDATE_0.22_DEV25.md'):
                require_release_notes('0.22.0.dev25', root)
            notes = root / 'docs/UPDATE_0.22_DEV25.md'; notes.write_text('Preview')
            self.assertEqual(require_release_notes('0.22.0.dev25', root), notes)

    def test_patch_release_cannot_reuse_previous_release_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'docs').mkdir()
            (root / 'docs/UPDATE_0.23.0.md').write_text('Previous release')
            with self.assertRaisesRegex(ValueError, 'UPDATE_0.23.1.md'):
                require_release_notes('0.23.1', root)


if __name__ == '__main__':
    unittest.main()
