"""A shared RC toolchain rejects wrong candidates, inputs and damaged payloads."""
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reference_toolchain as toolchain

REAL_ENVIRONMENT = toolchain.environment


class ReferenceAptSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.apt = self.root / 'etc-apt'
        (self.apt / 'sources.list.d').mkdir(parents=True)
        self.output = self.root / 'selected'

    def test_current_runner_mirror_is_replaced_without_changing_trust_or_suites(self):
        name = 'sources.list.d/ubuntu.sources'
        source = self.apt / name
        original = (b'Types: deb\nURIs: mirror+file:/etc/apt/apt-mirrors.txt\n'
                    b'Suites: noble noble-updates noble-backports noble-security\n'
                    b'Components: main restricted universe multiverse\n'
                    b'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n')
        source.write_bytes(original)
        receipt = toolchain.apt_sources(self.apt, self.output)
        expected = original.replace(b'mirror+file:/etc/apt/apt-mirrors.txt',
                                    b'https://archive.ubuntu.com/ubuntu/')
        self.assertEqual((self.output / name).read_bytes(), expected)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual((self.output / 'sources.list').read_bytes(), b'')
        self.assertEqual(receipt['files'][name], {
            'original_sha256': toolchain.digest(original),
            'selected_sha256': toolchain.digest(expected), 'changed': True})
        self.assertEqual(json.loads((self.output / 'receipt.json').read_bytes()), receipt)

    def test_legacy_sources_preserve_options_comments_and_other_repositories(self):
        original = (b'deb [arch=amd64 signed-by=/key.gpg] http://azure.archive.ubuntu.com/ubuntu noble main\n'
                    b'deb https://azure.archive.ubuntu.com/ubuntu/ noble-security main # http://azure.archive.ubuntu.com/ubuntu\n'
                    b'# mirror+file:/etc/apt/apt-mirrors.txt\n'
                    b'deb https://packages.microsoft.com/ubuntu/24.04/prod noble main\n')
        (self.apt / 'sources.list').write_bytes(original)
        toolchain.apt_sources(self.apt, self.output)
        expected = (b'deb [arch=amd64 signed-by=/key.gpg] https://archive.ubuntu.com/ubuntu/ noble main\n'
                    b'deb https://archive.ubuntu.com/ubuntu/ noble-security main # http://azure.archive.ubuntu.com/ubuntu\n'
                    b'# mirror+file:/etc/apt/apt-mirrors.txt\n'
                    b'deb https://packages.microsoft.com/ubuntu/24.04/prod noble main\n')
        self.assertEqual((self.output / 'sources.list').read_bytes(), expected)

    def test_unrecognized_hosts_paths_and_mirror_lists_are_not_rewritten(self):
        original = (b'URIs: https://azure.archive.ubuntu.com.evil/ubuntu/\n'
                    b' https://azure.archive.ubuntu.com/ubuntu-other\n'
                    b' mirror+file:/etc/apt/apt-mirrors.txt.other\n'
                    b' https://security.ubuntu.com/ubuntu/\n')
        (self.apt / 'sources.list.d/ubuntu.sources').write_bytes(original)
        receipt = toolchain.apt_sources(self.apt, self.output)
        self.assertEqual((self.output / 'sources.list.d/ubuntu.sources').read_bytes(), original)
        self.assertFalse(receipt['files']['sources.list.d/ubuntu.sources']['changed'])

    def test_missing_sources_and_existing_output_fail_without_overwriting(self):
        with self.assertRaisesRegex(ValueError, 'No APT source'):
            toolchain.apt_sources(self.apt, self.output)
        self.assertFalse(self.output.exists())
        (self.apt / 'sources.list').write_bytes(b'deb https://archive.ubuntu.com/ubuntu noble main\n')
        toolchain.apt_sources(self.apt, self.output)
        sentinel = self.output / 'sentinel'
        sentinel.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'new APT source directory'):
            toolchain.apt_sources(self.apt, self.output)
        self.assertEqual(sentinel.read_bytes(), b'keep')

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink construction')
    def test_linked_source_definitions_are_rejected_before_writing(self):
        (self.apt / 'sources.list').symlink_to(self.root / 'missing')
        with self.assertRaisesRegex(ValueError, 'Linked APT source definition'):
            toolchain.apt_sources(self.apt, self.output)
        self.assertFalse(self.output.exists())


class ReferenceToolchainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.sha = 'a' * 40
        self.platform = patch.object(toolchain, 'environment', return_value={
            'system': 'Linux', 'machine': 'x86_64', 'image_os': 'ubuntu24',
            'image_version': 'fixture'})
        self.platform.start()
        self.addCleanup(self.platform.stop)
        self.git = patch.object(toolchain.subprocess, 'check_output', return_value=self.sha + '\n')
        self.git.start()
        self.addCleanup(self.git.stop)
        for name in ('scripts/reference_toolchain.py', 'scripts/build_physical_engines.py',
                     '.github/workflows/reference-compatibility.yml', 'requirements.txt'):
            self.write(name, name.encode())
        self.write('packaging/physical/test.patch', b'patch bytes')
        locks = {
            'examples/gf180-rc-engine-lock.json': {'magic': {
                'version': '8.3.684', 'patch': 'packaging/physical/test.patch',
                'patch_sha256': toolchain.digest(b'patch bytes')}},
            'examples/modern-schematic-engine-lock.json': {
                'ngspice': {'version': 'ngspice-46', 'require_klu': True},
                'xschem': {'version': '3.4.8'}},
        }
        for name, lock in locks.items():
            self.write(name, json.dumps(lock).encode())
        for folder, lock in toolchain.expected_locks(self.root).items():
            self.write(folder + '/source-lock.json', json.dumps(lock).encode())
            for engine in lock:
                binary = self.write(folder + '/installed/bin/' + engine, b'engine bytes')
                binary.chmod(0o755)
                self.write(folder + '/licenses/' + engine + '/LICENSE', b'upstream license')
                for suffix in ('-build.log', '-version.log'):
                    self.write(folder + '/' + engine + suffix, b'retained log')
        self.archive = self.root / 'artifact/toolchain.tar.gz'

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def pack(self):
        sha = toolchain.pack(self.root, self.archive, self.sha)
        for folder in toolchain.BUNDLES:
            shutil.rmtree(self.root / folder)
        return sha

    def restore(self, sha):
        return toolchain.restore(self.root, self.archive, sha, self.sha)

    def mutate_archive(self, transform):
        with tarfile.open(self.archive, 'r:gz') as original:
            contents = [(m, original.extractfile(m).read() if m.isfile() else None)
                        for m in original.getmembers()]
        with tarfile.open(self.archive, 'w:gz') as changed:
            for member, data in transform(contents):
                if data is not None:
                    member.size = len(data)
                changed.addfile(member, io.BytesIO(data) if data is not None else None)
        return toolchain.digest(self.archive.read_bytes())

    def test_round_trip_retains_bytes_licenses_logs_and_selected_locks(self):
        expected = {p.relative_to(self.root).as_posix(): toolchain.file_record(self.root, p)
                    for p in toolchain.selected(self.root)}
        result = self.restore(self.pack())
        self.assertEqual(result['files'], expected)
        self.assertEqual(result['candidate'], self.sha)
        self.assertNotIn('xschem', toolchain.expected_locks(self.root)['build/modern-engines'])
        self.assertTrue((self.root / 'build' / toolchain.MANIFEST).is_file())

    def test_archive_checksum_must_match_producer(self):
        self.pack()
        with self.assertRaisesRegex(ValueError, 'checksum differs'):
            self.restore('b' * 64)
        self.assertFalse((self.root / 'build/gf180-engines').exists())

    def test_different_candidate_or_checkout_is_rejected_before_extracting(self):
        sha = self.pack()
        with patch.object(toolchain.subprocess, 'check_output', return_value='b' * 40 + '\n'):
            with self.assertRaisesRegex(ValueError, 'Checkout differs'):
                self.restore(sha)
            with self.assertRaisesRegex(ValueError, 'candidate, prefix'):
                toolchain.restore(self.root, self.archive, sha, 'b' * 40)
        with self.assertRaisesRegex(ValueError, 'full immutable'):
            toolchain.restore(self.root, self.archive, sha, 'experimental')
        self.assertFalse((self.root / 'build/gf180-engines').exists())

    def test_changed_builder_patch_or_environment_is_rejected(self):
        sha = self.pack()
        original = (self.root / 'scripts/build_physical_engines.py').read_bytes()
        self.write('scripts/build_physical_engines.py', b'changed builder')
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            self.restore(sha)
        self.write('scripts/build_physical_engines.py', original)
        with patch.object(toolchain, 'environment', return_value={'image_version': 'different'}):
            with self.assertRaisesRegex(ValueError, 'environment or inputs changed'):
                self.restore(sha)
        self.write('packaging/physical/test.patch', b'changed patch')
        with self.assertRaisesRegex(ValueError, 'Pinned engine patch changed'):
            self.restore(sha)

    def test_runtime_damage_rejected_even_if_outer_checksum_is_updated(self):
        self.pack()
        def change(contents):
            for member, data in contents:
                yield member, b'damaged engine' if member.name.endswith('/bin/magic') else data
        sha = self.mutate_archive(change)
        with self.assertRaisesRegex(ValueError, 'bytes, modes or links changed'):
            self.restore(sha)

    def test_duplicate_and_parent_traversal_members_rejected_before_writing(self):
        self.pack()
        original = self.archive.read_bytes()
        for name in ('../escape', toolchain.MANIFEST):
            with self.subTest(name=name):
                self.archive.write_bytes(original)
                def add(contents):
                    return contents + [(tarfile.TarInfo(name), b'injected')]
                sha = self.mutate_archive(add)
                with self.assertRaises(ValueError):
                    self.restore(sha)
                self.assertFalse((self.root / 'build/gf180-engines').exists())

    def test_unexpected_file_is_rejected_before_writing(self):
        self.pack()
        sha = self.mutate_archive(lambda contents: contents + [
            (tarfile.TarInfo('build/gf180-engines/installed/bin/unlisted'), b'extra')])
        with self.assertRaisesRegex(ValueError, 'file inventory differs'):
            self.restore(sha)
        self.assertFalse((self.root / 'build/gf180-engines').exists())

    def test_missing_license_cannot_be_silently_used(self):
        (self.root / 'build/gf180-engines/licenses/magic/LICENSE').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing upstream license'):
            toolchain.pack(self.root, self.archive, self.sha)

    def test_existing_installation_is_never_overwritten(self):
        sha = toolchain.pack(self.root, self.archive, self.sha)
        with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'):
            self.restore(sha)

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink and executable mode preservation')
    def test_internal_symlink_and_executable_mode_survive(self):
        link = self.root / 'build/gf180-engines/installed/bin/magic-link'
        link.symlink_to('magic')
        self.restore(self.pack())
        self.assertEqual(os.readlink(link), 'magic')
        self.assertEqual(link.resolve().stat().st_mode & 0o777, 0o755)

    @unittest.skipIf(os.name == 'nt', 'POSIX ordinary permission mode preservation')
    def test_group_writable_file_and_nondefault_directory_modes_survive(self):
        log = self.root / 'build/gf180-engines/magic-build.log'
        directory = self.root / 'build/gf180-engines/licenses'
        log.chmod(0o664)
        directory.chmod(0o750)
        result = self.restore(self.pack())
        self.assertEqual(log.stat().st_mode & 0o777, 0o664)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o750)
        self.assertEqual(result['files'][log.relative_to(self.root).as_posix()]['mode'], 0o664)

    @unittest.skipIf(os.name == 'nt', 'POSIX special permission bits')
    def test_special_permission_bits_are_rejected_at_producer(self):
        binary = self.root / 'build/gf180-engines/installed/bin/magic'
        binary.chmod(0o4755)
        with self.assertRaisesRegex(ValueError, 'Special runtime permission bits'):
            toolchain.pack(self.root, self.archive, self.sha)

    def test_changed_archive_permissions_are_rejected_before_writing(self):
        self.pack()
        def change(contents):
            for member, data in contents:
                if member.name.endswith('/bin/magic'):
                    member.mode = 0o4755
                yield member, data
        sha = self.mutate_archive(change)
        with self.assertRaisesRegex(ValueError, 'permissions/type'):
            self.restore(sha)
        self.assertFalse((self.root / 'build/gf180-engines').exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink construction')
    def test_members_beneath_symlinks_are_rejected_before_writing(self):
        folder = 'build/gf180-engines/installed/lib'
        self.write(folder + '/real/data', b'original')
        (self.root / folder / 'alias').symlink_to('real', target_is_directory=True)
        self.pack()
        name = folder + '/alias/extra'
        data = b'injected through link'
        def inject(contents):
            for member, raw in contents:
                if member.name == toolchain.MANIFEST:
                    record = json.loads(raw)
                    record['files'][name] = {'kind': 'file', 'mode': 0o644,
                                             'sha256': toolchain.digest(data), 'size': len(data)}
                    raw = json.dumps(record).encode()
                yield member, raw
            extra = tarfile.TarInfo(name)
            extra.mode = 0o644
            yield extra, data
        sha = self.mutate_archive(inject)
        with self.assertRaisesRegex(ValueError, 'would follow a symlink'):
            self.restore(sha)
        self.assertFalse((self.root / 'build/gf180-engines').exists())

    def test_hosted_runner_identity_cannot_be_empty(self):
        with patch.object(toolchain.platform, 'system', return_value='Linux'):
            for values in ({}, {'ImageOS': 'ubuntu24'}, {'ImageOS': ' ', 'ImageVersion': 'test'}):
                with self.subTest(values=values), patch.dict(os.environ, values, clear=True):
                    with self.assertRaisesRegex(ValueError, 'ImageOS and ImageVersion'):
                        REAL_ENVIRONMENT()
            with patch.dict(os.environ, {'ImageOS': 'ubuntu24', 'ImageVersion': 'test'}, clear=True):
                self.assertEqual(REAL_ENVIRONMENT()['image_version'], 'test')

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink construction')
    def test_external_symlink_is_rejected_when_packing(self):
        link = self.root / 'build/gf180-engines/installed/bin/escape'
        link.symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'Symlink escapes'):
            toolchain.pack(self.root, self.archive, self.sha)

    def test_engine_version_and_klu_are_probed_after_restore(self):
        self.restore(self.pack())
        with patch.object(toolchain.subprocess, 'check_output', side_effect=['8.3.684', 'ngspice-46 KLU']):
            self.assertEqual(set(toolchain.probe(self.root)), {'magic', 'ngspice'})
        with patch.object(toolchain.subprocess, 'check_output', side_effect=['8.3.684', 'ngspice-46']):
            with self.assertRaisesRegex(ValueError, 'KLU support differs'):
                toolchain.probe(self.root)


if __name__ == '__main__':
    unittest.main()
