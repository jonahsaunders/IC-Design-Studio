import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.publish_prerelease import preview_tag, publish, public_tag, render_release_notes
from scripts.release_evidence import archive_evidence, preflight_assets, checksum, EVIDENCE_KINDS


class ReleaseNotesRenderingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name); (self.root / 'docs').mkdir()
        self.notes = self.root / 'docs/UPDATE_0.23.0.md'; self.commit = 'a' * 40
        for name in ('README.md', 'docs/DOWNLOADS.md', 'docs/Guide with spaces.md', 'docs/image.png'):
            (self.root / name).write_text('Fixture')
        self.base = 'https://github.com/owner/repo/blob/' + self.commit + '/'

    def render(self, text):
        self.notes.write_text(text)
        return render_release_notes(self.notes, 'owner/repo', self.commit, root=self.root)

    def test_local_links_keep_fragments_titles_and_encoding_at_exact_source_revision(self):
        text = ('[Downloads](DOWNLOADS.md#first-run "Install")\n'
                '[Root](../README.md?plain=1#start)\n'
                '[Guide](<Guide with spaces.md>)\n'
                '[Encoded](Guide%20with%20spaces.md)\n'
                '[Repository root](/README.md)\n'
                '[reference]: DOWNLOADS.md#checksums "Checks"\n'
                '![Preview](image.png)\n')
        rendered = self.render(text)
        self.assertIn('[Downloads](' + self.base + 'docs/DOWNLOADS.md#first-run "Install")', rendered)
        self.assertIn('[Root](' + self.base + 'README.md?plain=1#start)', rendered)
        self.assertIn('[Guide](<' + self.base + 'docs/Guide%20with%20spaces.md>)', rendered)
        self.assertIn('[Encoded](' + self.base + 'docs/Guide%20with%20spaces.md)', rendered)
        self.assertIn('[Repository root](' + self.base + 'README.md)', rendered)
        self.assertIn('[reference]: ' + self.base + 'docs/DOWNLOADS.md#checksums "Checks"', rendered)
        self.assertIn('![Preview](https://raw.githubusercontent.com/owner/repo/' + self.commit + '/docs/image.png)', rendered)
        self.assertEqual(self.notes.read_text(), text)

    def test_external_urls_release_anchors_and_code_examples_are_preserved(self):
        text = ('[Site](https://example.com/guide) [Email](mailto:maintainer@example.com)\n'
                '[CDN](//example.com/image.png) [Here](#downloads)\n'
                '`[Example](missing.md)`\n'
                '```md\n[Example](missing.md)\n```\n'
                '~~~markdown\n[Example](missing.md)\n~~~\n')
        self.assertEqual(self.render(text), text)

    def test_missing_or_outside_repository_links_are_rejected(self):
        for target in ('missing.md', '../../outside.md', '../%2E%2E/outside.md'):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'Missing or unsafe'):
                self.render('[Invalid](' + target + ')')

    def test_current_release_notes_resolve_all_documentation_links_on_github(self):
        root = Path(__file__).resolve().parents[1]
        notes = root / 'docs/UPDATE_0.23.0.md'
        original = notes.read_text(encoding='utf-8')
        rendered = render_release_notes(notes, 'owner/repo', self.commit, root=root)
        for path in ('RELEASING.md#large-evidence-archives', 'DOWNLOADS.md',
                     'STUDENT_HUB.md#engines-and-models', 'MIXED_SIGNAL_SAR.md#local-engine-setup',
                     'RELEASE_FOLLOWUPS.md', 'NATIVE_DESKTOP_ACCEPTANCE.md',
                     'RELEASING.md#public-release-preparation'):
            with self.subTest(path=path):
                self.assertIn('](' + self.base + 'docs/' + path + ')', rendered)
                self.assertNotIn('](' + path + ')', rendered)
        self.assertIn('](https://github.com/jonahsaunders/IC-Design-Studio/releases/tag/v0.23.0)', rendered)
        self.assertEqual(notes.read_text(encoding='utf-8'), original)

    def test_historical_dev25_notes_keep_their_evidence_and_external_links(self):
        root = Path(__file__).resolve().parents[1]
        notes = root / 'docs/UPDATE_0.22_DEV25.md'
        original = notes.read_text(encoding='utf-8')
        rendered = render_release_notes(notes, 'owner/repo', self.commit, root=root)
        for destination in re.findall(r'\]\(([^\s)]+)\)', original):
            expected = destination if destination.startswith('https://') else self.base + 'docs/' + destination
            with self.subTest(destination=destination):
                self.assertIn('](' + expected + ')', rendered)
        self.assertEqual(notes.read_text(encoding='utf-8'), original)


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

    def test_upload_reads_rebased_notes_without_changing_source_or_release_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); assets = self.fixture(root)
            notes = root / 'docs/UPDATE_0.22_DEV25.md'
            original = '[Install](DOWNLOADS.md#linux)'; notes.write_text(original)
            (root / 'docs/DOWNLOADS.md').write_text('Install')
            uploaded = {}
            def github(command, **kwargs):
                path = Path(command[command.index('--notes-file') + 1])
                uploaded['path'], uploaded['text'] = path, path.read_text(encoding='utf-8')
                return subprocess.CompletedProcess(command, 0)
            publish(assets, '0.22.0.dev25', 'main', 'a' * 40, '123', '1',
                    'owner/repo', root=root, run=github)
            self.assertEqual(uploaded['text'], '[Install](https://github.com/owner/repo/blob/' + 'a' * 40 + '/docs/DOWNLOADS.md#linux)')
            self.assertFalse(uploaded['path'].exists())
            self.assertEqual(notes.read_text(), original)
            self.assertEqual([path.name for path in assets.iterdir()], ['payload.zip'])


class PublicPublishingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name); (self.root / 'docs').mkdir()
        (self.root / 'docs/UPDATE_0.23.0.md').write_text('Qualified 0.23.0 release')
        self.assets = self.root / 'release'; self.assets.mkdir()
        self.prefix = 'IC-Design-Studio-0.23.0-'; self.commit = 'a' * 40
        probe = {'status': 'passed', 'version': '0.23.0', 'frozen': True,
                 'build': {'commit': self.commit, 'dirty': False}}
        for platform in ('Windows', 'Linux'):
            archive = self.prefix + ('Windows-x64-Portable.zip' if platform == 'Windows' else 'Linux-x86_64.tar.gz')
            names = [archive, self.prefix + f'Source-{platform}.zip', self.prefix + f'Evidence-{platform}.zip']
            if platform == 'Windows': names.append(self.prefix + 'Windows-x64-Setup.exe')
            for name in names: (self.assets / name).write_bytes(('Qualified fixture: ' + name).encode())
            record = {'status': 'passed', 'version': '0.23.0', 'commit': self.commit, 'platform': platform,
                      'assets': {name: checksum(self.assets / name) for name in names},
                      'distribution': {'status': 'passed', 'archive': archive, 'archive_sha256': checksum(self.assets / archive), 'report': probe}}
            if platform == 'Windows':
                setup = names[-1]
                record['installer'] = {'status': 'passed', 'version': '0.23.0', 'commit': self.commit,
                    'installer': setup, 'installer_sha256': checksum(self.assets / setup),
                    'probes': [dict(probe, scale=scale) for scale in ('1', '1.5', '2')]}
            (self.assets / (self.prefix + f'Validation-{platform}.json')).write_text(json.dumps(record))
        for kind in EVIDENCE_KINDS: (self.assets / (self.prefix + kind + '-Evidence.zip')).write_bytes(b'Qualification fixture')
        (self.assets / (self.prefix + 'Statistical-Validation.json')).write_text(json.dumps(
            {'status': 'passed', 'version': '0.23.0', 'commit': self.commit}))
        self.sums = self.assets / 'SHA256SUMS-0.23.0.txt'; self.refresh_checksums()

    def refresh_checksums(self):
        self.sums.write_text(''.join(checksum(path) + '  ' + path.name + '\n'
                                    for path in sorted(self.assets.iterdir()) if path != self.sums))

    def github(self, command, **kwargs):
        if command[:2] == ['gh', 'api']:
            if '--include' in command:
                return subprocess.CompletedProcess(command, 1, 'HTTP/2.0 404 Not Found\r\n', '')
            return subprocess.CompletedProcess(command, 0, '', '')
        return subprocess.CompletedProcess(command, 0, '', '')

    def publish(self, run, **kwargs):
        return publish(self.assets, '0.23.0', 'main', self.commit, '123', '1', 'owner/repo',
                       root=self.root, run=run, public=True, **kwargs)

    def test_public_uploads_both_platforms_before_reserving_and_publishing_canonical_tag(self):
        run = Mock(side_effect=self.github)
        self.assertEqual(self.publish(run), 'v0.23.0')
        commands = [call.args[0] for call in run.call_args_list]
        create = next(command for command in commands if command[:3] == ['gh', 'release', 'create'])
        self.assertIn('--draft', create); self.assertIn('--prerelease', create)
        for suffix in ('Windows-x64-Setup.exe', 'Windows-x64-Portable.zip', 'Linux-x86_64.tar.gz'):
            self.assertIn(str((self.assets / (self.prefix + suffix)).resolve()), create)
        reserve = next(command for command in commands if '--method' in command)
        self.assertIn('ref=refs/tags/v0.23.0', reserve); self.assertIn('sha=' + self.commit, reserve)
        edit = commands[-1]
        self.assertEqual(edit[:4], ['gh', 'release', 'edit', create[3]])
        self.assertIn('--draft=false', edit); self.assertIn('--prerelease=false', edit); self.assertIn('--latest', edit)
        self.assertIn('--verify-tag', edit); self.assertEqual(edit[edit.index('--tag') + 1], 'v0.23.0')
        self.assertEqual(edit[edit.index('--target') + 1], self.commit)
        self.assertLess(commands.index(create), commands.index(reserve)); self.assertLess(commands.index(reserve), commands.index(edit))
        self.assertFalse(any('--clobber' in command or 'delete' in command for command in commands))

    def test_public_identity_requires_stable_main_and_matching_notes(self):
        for version, branch in (('0.23.0.dev1', 'main'), ('0.23.0', 'experimental'), ('00.23.0', 'main')):
            with self.subTest(version=version, branch=branch), self.assertRaises(ValueError): public_tag(version, branch)
        (self.root / 'docs/UPDATE_0.23.0.md').unlink(); run = Mock()
        with self.assertRaisesRegex(ValueError, 'notes'): self.publish(run)
        run.assert_not_called()

    def test_public_release_upload_uses_rebased_notes_before_promotion(self):
        notes = self.root / 'docs/UPDATE_0.23.0.md'
        notes.write_text('[Install](DOWNLOADS.md#first-run)')
        (self.root / 'docs/DOWNLOADS.md').write_text('Install')
        uploaded = []
        def github(command, **kwargs):
            if command[:3] == ['gh', 'release', 'create']:
                uploaded.append(Path(command[command.index('--notes-file') + 1]).read_text(encoding='utf-8'))
            return self.github(command, **kwargs)
        self.assertEqual(self.publish(Mock(side_effect=github)), 'v0.23.0')
        self.assertEqual(uploaded, ['[Install](https://github.com/owner/repo/blob/' + self.commit + '/docs/DOWNLOADS.md#first-run)'])

    def test_missing_windows_or_linux_package_never_calls_github(self):
        for suffix in ('Windows-x64-Setup.exe', 'Windows-x64-Portable.zip', 'Linux-x86_64.tar.gz'):
            path = self.assets / (self.prefix + suffix); original = path.read_bytes(); path.unlink(); run = Mock()
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, 'both qualified'): self.publish(run)
            run.assert_not_called(); path.write_bytes(original)

    def test_mismatched_source_version_or_post_validation_asset_change_never_calls_github(self):
        path = self.assets / (self.prefix + 'Validation-Windows.json'); original = path.read_text()
        for field, value in (('commit', 'b' * 40), ('version', '0.22.0')):
            record = json.loads(original); record[field] = value; path.write_text(json.dumps(record)); self.refresh_checksums(); run = Mock()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'selected version, commit'): self.publish(run)
            run.assert_not_called()
        path.write_text(original); self.refresh_checksums()
        (self.assets / (self.prefix + 'Windows-x64-Portable.zip')).write_bytes(b'Unqualified replacement'); run = Mock()
        with self.assertRaisesRegex(ValueError, 'Changed public release asset'): self.publish(run)
        run.assert_not_called()

    def test_refreshed_checksums_cannot_hide_changed_installer_or_platform_asset(self):
        path = self.assets / (self.prefix + 'Windows-x64-Setup.exe'); path.write_bytes(b'Unexecuted replacement'); self.refresh_checksums(); run = Mock()
        with self.assertRaisesRegex(ValueError, 'qualified platform validation'): self.publish(run)
        run.assert_not_called()

    def test_checksums_must_cover_every_upload_asset_without_duplicates(self):
        original = self.sums.read_text()
        for invalid in ('\n'.join(original.splitlines()[1:]) + '\n', original + original.splitlines()[0] + '\n'):
            self.sums.write_text(invalid); run = Mock()
            with self.assertRaisesRegex(ValueError, 'checksums|checksum entry'): self.publish(run)
            run.assert_not_called()

    def test_upload_failure_never_reserves_tag_or_makes_release_visible(self):
        def failure(command, **kwargs):
            if command[:3] == ['gh', 'release', 'create']: raise subprocess.CalledProcessError(1, command)
            return self.github(command, **kwargs)
        run = Mock(side_effect=failure)
        with self.assertRaises(subprocess.CalledProcessError): self.publish(run)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertFalse(any('--method' in command or command[:3] == ['gh', 'release', 'edit'] for command in commands))

    def test_existing_public_or_draft_release_and_existing_tag_are_refused(self):
        for conflict in ('release', 'tag'):
            def response(command, **kwargs):
                if conflict == 'release' and '--paginate' in command: return subprocess.CompletedProcess(command, 0, '12345\n', '')
                if conflict == 'tag' and '--include' in command: return subprocess.CompletedProcess(command, 0, 'HTTP/1.1 200 OK\r\n', '')
                return self.github(command, **kwargs)
            run = Mock(side_effect=response)
            with self.subTest(conflict=conflict), self.assertRaisesRegex(ValueError, 'existing canonical'): self.publish(run)
            self.assertFalse(any(call.args[0][:2] == ['gh', 'release'] for call in run.call_args_list))
            self.assertIn('--paginate', run.call_args_list[0].args[0])

    def test_remote_errors_are_not_interpreted_as_unused_tag(self):
        for status in ('401', '403', '429', '500', None):
            def response(command, **kwargs):
                if '--include' in command: return subprocess.CompletedProcess(command, 1, 'HTTP/2.0 ' + status + ' Error\r\n' if status else '', 'network error')
                return self.github(command, **kwargs)
            run = Mock(side_effect=response)
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, 'Could not confirm'): self.publish(run)
            self.assertFalse(any(call.args[0][:2] == ['gh', 'release'] for call in run.call_args_list))

    def test_intervening_release_or_atomic_tag_conflict_keeps_uploaded_draft_private(self):
        for conflict in ('release', 'tag'):
            calls = []
            def response(command, **kwargs):
                calls.append(command)
                if conflict == 'release' and '--paginate' in command and any(c[:3] == ['gh', 'release', 'create'] for c in calls):
                    return subprocess.CompletedProcess(command, 0, '12345\n', '')
                if conflict == 'tag' and '--method' in command: raise subprocess.CalledProcessError(1, command)
                return self.github(command, **kwargs)
            run = Mock(side_effect=response)
            with self.subTest(conflict=conflict), self.assertRaises((ValueError, subprocess.CalledProcessError)): self.publish(run)
            self.assertTrue(any(c[:3] == ['gh', 'release', 'create'] for c in calls))
            self.assertFalse(any(c[:3] == ['gh', 'release', 'edit'] for c in calls))

    def split_evidence(self):
        name = self.prefix + 'physical-Evidence.zip'
        (self.assets / name).unlink()
        source = self.root / 'split evidence'; source.mkdir()
        (source / 'proof.bin').write_bytes(bytes(range(256)) * 4)
        paths = archive_evidence(source, self.assets, name, part_bytes=128)
        manifest = next(path for path in paths if path.name.endswith('.parts.json'))
        self.refresh_checksums()
        return manifest, json.loads(manifest.read_text())

    def test_complete_split_evidence_is_uploaded_and_missing_part_cannot_be_hidden_by_checksums(self):
        manifest, record = self.split_evidence(); run = Mock(side_effect=self.github)
        self.assertEqual(self.publish(run), 'v0.23.0')
        create = next(call.args[0] for call in run.call_args_list if call.args[0][:3] == ['gh', 'release', 'create'])
        self.assertIn(str(manifest.resolve()), create)
        for part in record['parts']: self.assertIn(str((self.assets / part['name']).resolve()), create)
        (self.assets / record['parts'][-1]['name']).unlink(); self.refresh_checksums(); run = Mock()
        with self.assertRaisesRegex(ValueError, 'Missing or changed public evidence part'): self.publish(run)
        run.assert_not_called()

    def test_split_archive_order_and_whole_hash_are_verified_before_github(self):
        manifest, record = self.split_evidence()
        for mutation in ('order', 'archive hash', 'part bytes'):
            changed = json.loads(json.dumps(record))
            if mutation == 'order': changed['parts'].reverse()
            elif mutation == 'archive hash': changed['archive']['sha256'] = '0' * 64
            else: changed['parts'][0]['bytes'] += 1
            manifest.write_text(json.dumps(changed)); self.refresh_checksums(); run = Mock()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.publish(run)
            run.assert_not_called()

    def test_release_lookup_errors_fail_closed_and_http1_missing_tag_is_supported(self):
        def denied(command, **kwargs):
            if '--paginate' in command: return subprocess.CompletedProcess(command, 1, '', 'access denied')
            return self.github(command, **kwargs)
        run = Mock(side_effect=denied)
        with self.assertRaisesRegex(ValueError, 'Could not check existing public releases'): self.publish(run)
        self.assertEqual(run.call_count, 1)
        def http1(command, **kwargs):
            if '--include' in command: return subprocess.CompletedProcess(command, 1, 'HTTP/1.1 404 Not Found\r\n', '')
            return self.github(command, **kwargs)
        self.assertEqual(self.publish(Mock(side_effect=http1)), 'v0.23.0')

    def test_promotion_failure_leaves_reserved_tag_for_manual_review_and_rerun_refuses_it(self):
        reserved = False
        def response(command, **kwargs):
            nonlocal reserved
            if '--method' in command: reserved = True
            if command[:3] == ['gh', 'release', 'edit']: raise subprocess.CalledProcessError(1, command)
            if reserved and '--include' in command: return subprocess.CompletedProcess(command, 0, 'HTTP/2.0 200 OK\r\n', '')
            return self.github(command, **kwargs)
        run = Mock(side_effect=response)
        with self.assertRaisesRegex(ValueError, 'Inspect that tag and draft .* before retrying'): self.publish(run)
        self.assertTrue(reserved)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(sum(command[:3] == ['gh', 'release', 'create'] for command in commands), 1)
        self.assertFalse(any('--clobber' in command or 'delete' in command for command in commands))
        run.reset_mock()
        with self.assertRaisesRegex(ValueError, 'existing canonical tag'): self.publish(run)
        self.assertFalse(any(call.args[0][:2] == ['gh', 'release'] for call in run.call_args_list))

    def test_malformed_execution_evidence_is_refused_before_github(self):
        path = self.assets / (self.prefix + 'Validation-Windows.json'); original = json.loads(path.read_text())
        for invalid in ({'distribution': None}, {'installer': None}, {'installer': dict(original['installer'], probes=None)},
                        {'distribution': dict(original['distribution'], report=dict(original['distribution']['report'], build=None))}):
            path.write_text(json.dumps(dict(original, **invalid))); self.refresh_checksums(); run = Mock()
            with self.subTest(invalid=invalid), self.assertRaises(ValueError): self.publish(run)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
