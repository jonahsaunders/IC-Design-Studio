import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.publish_prerelease import preview_tag, publish
from scripts.release_evidence import preflight_assets


class PreviewPublishingTests(unittest.TestCase):
    def test_source_branch_and_rerun_each_have_distinct_preview_identity(self):
        args = ('0.22.0.dev25', 'main', 'a' * 40, '123', '1')
        tags = {preview_tag(*args)}
        for index, value in ((1, 'experimental'), (2, 'b' * 40), (3, '124'), (4, '2')):
            varied = list(args); varied[index] = value
            tags.add(preview_tag(*varied))
        self.assertEqual(len(tags), 5)
        self.assertNotIn('v0.22.0.dev25', tags)

    def test_invalid_release_identity_is_rejected(self):
        for index, value in ((0, '../notes'), (1, 'feature'), (2, 'a' * 8),
                             (3, '0'), (4, '0'), (4, '-1')):
            args = ['0.22.0.dev25', 'main', 'a' * 40, '123', '1']; args[index] = value
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                preview_tag(*args)

    def fixture(self, root):
        (root / 'docs').mkdir()
        (root / 'docs/UPDATE_0.22_DEV25.md').write_text('Qualified preview')
        assets = root / 'release'; assets.mkdir()
        (assets / 'payload.zip').write_bytes(b'tested asset')
        return assets

    def test_upload_creates_only_a_draft_bound_to_exact_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); assets = self.fixture(root); run = Mock()
            tag = publish(assets, '0.22.0.dev25', 'main', 'a' * 40, '123', '2',
                          'owner/repo', root=root, run=run)
            command = run.call_args.args[0]
            self.assertEqual(command[:4], ['gh', 'release', 'create', tag])
            self.assertEqual(command[command.index('--target') + 1], 'a' * 40)
            self.assertIn('--draft', command); self.assertIn('--prerelease', command)
            self.assertNotIn('--clobber', command)
            self.assertEqual(run.call_args.kwargs, {'check': True})

    def test_missing_notes_or_oversized_payload_never_calls_github(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); assets = self.fixture(root); run = Mock()
            (assets / 'payload.zip').write_bytes(b'x' * 16)
            # Exercise preflight without allocating a multi-GiB file on Windows.
            with patch('scripts.release_evidence.preflight_assets',
                       side_effect=lambda path: preflight_assets(path, limit=16)), self.assertRaises(ValueError):
                publish(assets, '0.22.0.dev25', 'main', 'a' * 40, '123', '1',
                        'owner/repo', root=root, run=run)
            (assets / 'payload.zip').write_bytes(b'small')
            (root / 'docs/UPDATE_0.22_DEV25.md').unlink()
            with self.assertRaises(ValueError):
                publish(assets, '0.22.0.dev25', 'main', 'a' * 40, '123', '1',
                        'owner/repo', root=root, run=run)
            run.assert_not_called()

    def test_upload_failure_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); assets = self.fixture(root)
            run = Mock(side_effect=subprocess.CalledProcessError(1, ['gh']))
            with self.assertRaises(subprocess.CalledProcessError):
                publish(assets, '0.22.0.dev25', 'main', 'a' * 40, '123', '1',
                        'owner/repo', root=root, run=run)


if __name__ == '__main__':
    unittest.main()
