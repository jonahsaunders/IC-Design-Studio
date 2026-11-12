"""Protect exact filled-input identity and refusal of incomplete acceptance."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_STORED

from scripts import check_sky130_filled_replay as replay


class FilledReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with ZipFile(replay.BUNDLE) as archive:
            cls.content = {name: archive.read(name) for name in archive.namelist()}
        cls.manifest = json.loads(cls.content['manifest.json'])

    def rewritten(self, folder, content, manifest, duplicate=None):
        path = folder / 'changed.zip'
        raw = (json.dumps(manifest, indent=2) + '\n').encode()
        with ZipFile(path, 'w', ZIP_STORED) as archive:
            archive.writestr('manifest.json', raw)
            for name, data in content.items():
                if name != 'manifest.json':
                    archive.writestr(name, data)
            if duplicate:
                with self.assertWarns(UserWarning):
                    archive.writestr(duplicate, content[duplicate])
        return path, replay.digest(path.read_bytes()), replay.digest(raw)

    def test_portable_fixture_matches_all_independent_reference_hashes(self):
        with TemporaryDirectory() as temp:
            destination = Path(temp) / 'inputs'
            manifest = replay.unpack(replay.BUNDLE, destination)
            self.assertEqual(len(manifest['files']), 172)
            self.assertEqual({row['case'] for row in manifest['cases']}, {'counter', 'uart', 'apb'})
            self.assertEqual(len(list(destination.rglob('filled.gds'))), 3)
            for name, identity in manifest['files'].items():
                self.assertEqual(replay.digest((destination / name).read_bytes()), identity['sha256'])

    def test_changed_archive_refused_before_any_input_is_written(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            archive = folder / 'changed.zip'
            archive.write_bytes(replay.BUNDLE.read_bytes() + b'changed')
            with self.assertRaisesRegex(ValueError, 'Changed filled-reference bundle'):
                replay.unpack(archive, folder / 'inputs')
            self.assertFalse((folder / 'inputs').exists())

    def test_existing_output_directory_is_never_overwritten(self):
        with TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'must be new'):
                replay.unpack(replay.BUNDLE, Path(temp))

    def test_duplicate_members_cannot_shadow_authenticated_inputs(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            archive, sha, _ = self.rewritten(folder, self.content, self.manifest, 'counter/filled.gds')
            with patch.object(replay, 'BUNDLE_SHA256', sha), self.assertRaisesRegex(ValueError, 'Duplicate'):
                replay.unpack(archive, folder / 'inputs')
            self.assertFalse((folder / 'inputs').exists())

    def test_changed_bytes_fail_even_if_outer_archive_is_relocked(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            content = dict(self.content)
            content['counter/filled.gds'] = b'x' + content['counter/filled.gds'][1:]
            archive, sha, _ = self.rewritten(folder, content, self.manifest)
            with patch.object(replay, 'BUNDLE_SHA256', sha), self.assertRaisesRegex(ValueError, 'member bytes'):
                replay.unpack(archive, folder / 'inputs')
            self.assertFalse((folder / 'inputs').exists())

    def test_relocked_manifest_cannot_replace_final_reference_or_source(self):
        for name in ('counter/filled.gds', 'sources/docs/rules/periphery/p018-x_dotdash.csv'):
            with self.subTest(name=name), TemporaryDirectory() as temp:
                folder = Path(temp)
                content = dict(self.content)
                content[name] += b'changed'
                manifest = deepcopy(self.manifest)
                manifest['files'][name] = dict(sha256=replay.digest(content[name]), bytes=len(content[name]))
                if name.startswith('counter/'):
                    manifest['cases'][0]['gds_sha256'] = replay.digest(content[name])
                archive, sha, msha = self.rewritten(folder, content, manifest)
                with patch.object(replay, 'BUNDLE_SHA256', sha), patch.object(replay, 'MANIFEST_SHA256', msha):
                    with self.assertRaisesRegex(ValueError, 'independent checkpoint|published source'):
                        replay.unpack(archive, folder / 'inputs')
                self.assertFalse((folder / 'inputs').exists())

    def test_relocked_manifest_cannot_change_die_or_case_inventory(self):
        for mutation in ('die', 'duplicate_case', 'missing_member'):
            with self.subTest(mutation=mutation), TemporaryDirectory() as temp:
                folder = Path(temp)
                manifest = deepcopy(self.manifest)
                content = dict(self.content)
                if mutation == 'die':
                    manifest['cases'][0]['die_nm'][2] += 1000
                elif mutation == 'duplicate_case':
                    manifest['cases'][-1] = deepcopy(manifest['cases'][0])
                else:
                    content.pop('counter/inventory.json')
                    manifest['files'].pop('counter/inventory.json')
                archive, sha, msha = self.rewritten(folder, content, manifest)
                with patch.object(replay, 'BUNDLE_SHA256', sha), patch.object(replay, 'MANIFEST_SHA256', msha):
                    with self.assertRaisesRegex(ValueError, 'die/top|scope or cases|bundle member'):
                        replay.unpack(archive, folder / 'inputs')
                self.assertFalse((folder / 'inputs').exists())

    def test_paths_cannot_escape_or_alias_bundle_members(self):
        for name in ('../outside', '/outside', 'C:/outside', 'a\\b', 'a/../b', './a', 'a//b', ''):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'bundle member'):
                replay.member_name(name)

    def test_fresh_execution_cannot_silently_replace_historical_results(self):
        with patch.object(replay.execution, 'audit', return_value={'case': 'counter'}):
            with self.assertRaisesRegex(ValueError, 'Fresh final-layout execution differs'):
                replay.build()

    def test_clean_geometry_cannot_close_missing_acceptance_definitions(self):
        cases = [dict(case=name, grid={'status': 'PASS'}, density={'status': 'PASS'})
                 for name in ('counter', 'uart', 'apb')]
        result = replay.summarize(cases)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertFalse(result['qualified'])
        self.assertFalse(result['chunk_complete'])
        with self.assertRaisesRegex(ValueError, 'Missing or duplicate'):
            replay.summarize(cases[:-1])

    def test_cli_retains_blocked_exit_code_and_reproduces_saved_report(self):
        result = dict(status='BLOCKED', chunk_complete=False, blockers=['Unresolved source definition'])
        with TemporaryDirectory() as temp:
            path = Path(temp) / 'report.json'
            with patch.object(replay, 'build', return_value=result):
                with patch('sys.argv', ['replay', '--output', str(path)]):
                    self.assertEqual(replay.main(), 2)
                with patch('sys.argv', ['replay', '--output', str(path), '--check']):
                    self.assertEqual(replay.main(), 2)
                path.write_text('{}')
                with patch('sys.argv', ['replay', '--output', str(path), '--check']):
                    with self.assertRaisesRegex(ValueError, 'differs'):
                        replay.main()


if __name__ == '__main__':
    unittest.main()
