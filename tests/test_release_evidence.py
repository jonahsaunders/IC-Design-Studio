"""Bounded release assets must preserve complete evidence and fail on corruption."""
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from icstudio import __version__
from scripts.release_evidence import (
    EVIDENCE_KINDS, GITHUB_ASSET_LIMIT, archive_evidence, checksum,
    complete_evidence, preflight_assets, reassemble,
)


class ReleaseEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source evidence'
        self.source.mkdir()
        self.payload = random.Random(123).randbytes(8192)
        (self.source / 'engine-output.bin').write_bytes(self.payload)
        (self.source / 'nested').mkdir()
        (self.source / 'nested' / 'qualification.json').write_text('{"status": "fixture"}\n')
        self.release = self.root / 'release'

    def split(self):
        assets = archive_evidence(self.source, self.release, 'physical-Evidence.zip', part_bytes=1024)
        manifest = next(path for path in assets if path.name.endswith('.parts.json'))
        return manifest, json.loads(manifest.read_text())

    def test_over_limit_archive_becomes_bounded_parts_and_reassembles_every_file(self):
        manifest, record = self.split()
        # A 4 KiB simulated upload limit would reject this archive unsplit.
        self.assertGreater(record['archive']['bytes'], 4096)
        self.assertTrue(all(part['bytes'] <= 1024 for part in record['parts']))
        self.assertEqual(len(preflight_assets(self.release, limit=4096)), len(record['parts']) + 1)
        self.assertFalse((self.release / record['archive']['name']).exists())
        restored = reassemble(manifest, self.root / 'restored')
        self.assertEqual(restored.stat().st_size, record['archive']['bytes'])
        self.assertEqual(checksum(restored), record['archive']['sha256'])
        with zipfile.ZipFile(restored) as archive:
            self.assertEqual(archive.testzip(), None)
            self.assertEqual(archive.read('engine-output.bin'), self.payload)
            self.assertEqual(archive.read('nested/qualification.json'), b'{"status": "fixture"}\n')
            self.assertEqual(set(archive.namelist()), {'engine-output.bin', 'nested/', 'nested/qualification.json'})
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            reassemble(manifest, restored.parent)

    def test_small_evidence_remains_an_ordinary_zip(self):
        assets = archive_evidence(self.source, self.release, 'evidence.zip', part_bytes=16384)
        self.assertEqual([path.name for path in assets], ['evidence.zip'])
        with zipfile.ZipFile(assets[0]) as archive:
            self.assertEqual(archive.read('engine-output.bin'), self.payload)

    def test_exact_part_boundary_has_no_empty_trailing_part(self):
        assets = archive_evidence(self.source, self.release, 'ordinary.zip', part_bytes=16384)
        size = assets[0].stat().st_size
        assets = archive_evidence(self.source, self.release, 'boundary.zip', part_bytes=size)
        self.assertEqual([path.name for path in assets], ['boundary.zip'])
        self.assertEqual(assets[0].stat().st_size, size)

    def test_streamed_zip64_headers_and_descriptors_survive_small_parts(self):
        # Exercise ZIP64 without generating a multi-GiB fixture.
        with patch('zipfile.ZIP64_LIMIT', 2048):
            manifest, record = self.split()
        restored = reassemble(manifest, self.root / 'restored')
        self.assertEqual(checksum(restored), record['archive']['sha256'])
        with zipfile.ZipFile(restored) as archive:
            self.assertEqual(archive.read('engine-output.bin'), self.payload)
            self.assertIsNone(archive.testzip())

    def test_missing_and_same_sized_corrupt_parts_leave_no_restored_archive(self):
        manifest, record = self.split()
        part = self.release / record['parts'][1]['name']
        original = part.read_bytes()
        for mutation in ('missing', 'corrupt'):
            with self.subTest(mutation=mutation):
                if mutation == 'missing':
                    part.unlink()
                else:
                    part.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                output = self.root / mutation
                with self.assertRaisesRegex(ValueError, 'evidence part|Evidence part'):
                    reassemble(manifest, output)
                self.assertEqual(list(output.iterdir()), [])
                part.write_bytes(original)

    def test_whole_archive_hash_is_checked_even_if_part_hash_is_refreshed(self):
        manifest, record = self.split()
        part = self.release / record['parts'][0]['name']
        data = part.read_bytes()
        part.write_bytes(bytes([data[0] ^ 1]) + data[1:])
        record['parts'][0]['sha256'] = checksum(part)
        manifest.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'archive checksum mismatch'):
            reassemble(manifest, self.root / 'restored')
        self.assertEqual(list((self.root / 'restored').iterdir()), [])

    def test_reordered_duplicate_and_path_traversal_parts_are_rejected(self):
        manifest, original = self.split()
        for mutation in ('reordered', 'duplicate', 'traversal', 'archive-traversal'):
            record = json.loads(json.dumps(original))
            if mutation == 'reordered':
                record['parts'].reverse()
            elif mutation == 'duplicate':
                record['parts'][1] = record['parts'][0]
            elif mutation == 'traversal':
                record['parts'][0]['name'] = '../secret'
            else:
                record['archive']['name'] = '../archive.zip'
            manifest.write_text(json.dumps(record))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                reassemble(manifest, self.root / 'restored')
        self.assertFalse((self.root / 'restored').exists())

    def test_preflight_enforces_strict_size_boundary_for_every_asset(self):
        self.release.mkdir()
        with self.assertRaisesRegex(ValueError, 'No release assets'):
            preflight_assets(self.release)
        asset = self.release / 'application.exe'
        asset.write_bytes(b'x' * 1023)
        self.assertEqual(preflight_assets(self.release, limit=1024), [asset])
        asset.write_bytes(b'x' * 1024)
        with self.assertRaisesRegex(ValueError, 'application.exe.*less than 1024'):
            preflight_assets(self.release, limit=1024)
        self.assertEqual(GITHUB_ASSET_LIMIT, 2147483648)

    def test_unsafe_part_sizes_and_missing_evidence_are_rejected(self):
        for size in (0, -1, GITHUB_ASSET_LIMIT, True):
            with self.subTest(size=size), self.assertRaises(ValueError):
                archive_evidence(self.source, self.release, 'evidence.zip', part_bytes=size)
        with self.assertRaisesRegex(ValueError, 'Missing or empty'):
            archive_evidence(self.root / 'missing', self.release, 'evidence.zip')

    def qualification_inputs(self):
        build = self.root / 'build'
        for kind in EVIDENCE_KINDS:
            shutil.copytree(self.source, build / f'{kind}-release-evidence')
        directory = build / 'statistics-release-evidence'
        (directory / 'campaign-gate.json').write_text(json.dumps({'commit': 'a' * 40, 'run_id': '123'}))
        proof = directory / 'statistical-campaign-qualification' / 'qualification.json'
        proof.parent.mkdir()
        proof.write_text(json.dumps({
            'qualification_status': 'passed', 'trials': 128, 'cases': 1152,
            'completed_cases': 1152, 'retried_cases': 4,
            'fault': {'exit_code': -9, 'immutable_input_preserved': True,
                      'stale_publication_rejected': True},
            'statistics': {'joint': {'trials': 128, 'passed': 99, 'failed': 29, 'unresolved': 0}},
        }))
        self.release.mkdir()
        (self.release / 'qualified-desktop.zip').write_bytes(b'unchanged desktop fixture')
        return build

    def test_completion_preserves_gate_payloads_and_covers_every_final_asset(self):
        build = self.qualification_inputs()
        files = complete_evidence(build, self.release, 'a' * 40, '123', part_bytes=1024)
        self.assertEqual((self.release / 'qualified-desktop.zip').read_bytes(), b'unchanged desktop fixture')
        sums_name = f'SHA256SUMS-{__version__}.txt'
        sums = (self.release / sums_name).read_text().splitlines()
        self.assertEqual({line.split('  ')[1] for line in sums}, {path.name for path in files} - {sums_name})
        for line in sums:
            digest, name = line.split('  ')
            self.assertEqual(checksum(self.release / name), digest)
        manifests = list(self.release.glob('*.zip.parts.json'))
        self.assertEqual(len(manifests), len(EVIDENCE_KINDS))
        self.assertTrue((self.release / 'EVIDENCE-REASSEMBLY.md').is_file())
        # The distributed helper must work with no repository imports or cwd.
        result = subprocess.run([sys.executable, '-I', str(self.release / 'reassemble_evidence.py'),
                                 'reassemble', str(manifests[0]), '--output', str(self.root / 'portable')],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(checksum(Path(result.stdout.strip())), json.loads(manifests[0].read_text())['archive']['sha256'])

    def test_statistical_provenance_failure_prevents_evidence_packaging(self):
        build = self.qualification_inputs()
        for commit, run in [('b' * 40, '123'), ('a' * 40, '124')]:
            with self.subTest(commit=commit, run=run), self.assertRaisesRegex(ValueError, 'commit and workflow run'):
                complete_evidence(build, self.release, commit, run, part_bytes=1024)
        self.assertEqual([path.name for path in self.release.iterdir()], ['qualified-desktop.zip'])


if __name__ == '__main__':
    unittest.main()
