import base64
import copy
import gzip
import hashlib
import io
import json
import tarfile
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from scripts.inventory_upstream_views import (
    archive_rows, canonical, compare_files, compressed, git_hash, package_index,
    safe_path, verified_closure,
)


def tree_document(entries):
    rows = [dict(path=p, mode=mode, type='commit' if mode == '160000' else 'blob', sha=sha)
            for p, mode, sha in entries]
    body = b''.join(r['mode'].encode() + b' ' + r['path'].encode() + b'\0' + bytes.fromhex(r['sha'])
                    for r in sorted(rows, key=lambda row: row['path'].encode()))
    return dict(sha=git_hash('tree', body), truncated=False, tree=rows)


class SourceClosureTests(unittest.TestCase):
    def fixture(self):
        module = b'[submodule "child"]\npath = child\nurl = https://github.com/example/child.git\n'
        child = tree_document([('device.spice', '100644', git_hash('blob', b'public model'))])
        parent = tree_document([('.gitmodules', '100644', git_hash('blob', module)),
                                ('child', '160000', '2' * 40)])
        bundle = {'root-tree.json': parent, 'child-tree.json': child,
                  'root-commit.json': dict(sha='1' * 40, tree=dict(sha=parent['sha'])),
                  'child-commit.json': dict(sha='2' * 40, tree=dict(sha=child['sha'])),
                  'root-gitmodules.json': dict(encoding='base64', content=base64.b64encode(module).decode())}
        roots = {'ihp-sg13g2': 'example/root@' + '1' * 40}
        repos = {'example/root': ('1' * 40, parent['sha']), 'example/child': ('2' * 40, child['sha'])}
        entries = {repo + '@' + commit: dict(repository=repo, commit=commit, tree=tree,
                                            commit_file=repo.split('/')[1] + '-commit.json',
                                            tree_file=repo.split('/')[1] + '-tree.json')
                   for repo, (commit, tree) in repos.items()}
        bundle['lock.json'] = dict(roots=roots, entries=entries,
                                  edges=[dict(parent=roots['ihp-sg13g2'], path='child',
                                              child='example/child@' + '2' * 40)])
        return bundle, roots, repos

    def test_complete_submodule_closure_includes_child_files(self):
        bundle, roots, repos = self.fixture()
        rows, source = verified_closure(bundle, roots, repos)
        self.assertEqual([r['path'] for r in rows], ['.gitmodules', 'child/device.spice'])
        self.assertEqual(len(source['repositories']), 2)
        self.assertTrue(all(r['git_tree_verified'] for r in source['repositories'].values()))
        self.assertFalse(any(r['commit_signature_verified'] for r in source['repositories'].values()))

    def test_removed_renamed_changed_or_extra_gitlinks_fail(self):
        for fault in ('omit', 'duplicate', 'path', 'child', 'extra'):
            bundle, roots, repos = self.fixture()
            edges = bundle['lock.json']['edges']
            if fault == 'omit':
                edges.clear()
            elif fault == 'duplicate':
                edges.append(copy.deepcopy(edges[0]))
            elif fault == 'path':
                edges[0]['path'] = 'elsewhere'
            elif fault == 'child':
                edges[0]['child'] = roots['ihp-sg13g2']
            else:
                edges.append(dict(edges[0], path='extra'))
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                verified_closure(bundle, roots, repos)

    def test_changed_child_commit_tree_or_blob_fails(self):
        for fault in ('commit', 'tree', 'blob', 'omitted-blob', 'truncated'):
            bundle, roots, repos = self.fixture()
            if fault == 'commit':
                bundle['child-commit.json']['sha'] = '0' * 40
            elif fault == 'tree':
                bundle['child-commit.json']['tree']['sha'] = '0' * 40
            elif fault == 'blob':
                bundle['child-tree.json']['tree'][0]['sha'] = '0' * 40
            elif fault == 'omitted-blob':
                bundle['child-tree.json']['tree'].clear()
            else:
                bundle['child-tree.json']['truncated'] = True
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                verified_closure(bundle, roots, repos)

    def test_changed_gitmodules_or_unpinned_repository_fails(self):
        for fault in ('modules', 'repo', 'missing-repo', 'extra-file'):
            bundle, roots, repos = self.fixture()
            if fault == 'modules':
                bundle['root-gitmodules.json']['content'] = base64.b64encode(b'changed').decode()
            elif fault == 'repo':
                bundle['lock.json']['entries']['example/child@' + '2' * 40]['repository'] = 'other/repo'
            elif fault == 'missing-repo':
                del bundle['lock.json']['entries']['example/child@' + '2' * 40]
            else:
                bundle['extra.json'] = {}
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                verified_closure(bundle, roots, repos)


class ArchiveTests(unittest.TestCase):
    def archive(self, path, members):
        with tarfile.open(path, 'w') as tar:
            for name, kind in members:
                item = tarfile.TarInfo(name)
                item.type = kind
                item.linkname = 'sky130A/elsewhere'
                item.size = 6 if kind == tarfile.REGTYPE else 0
                tar.addfile(item, io.BytesIO(b'source') if item.size else None)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def run_archive(self, members, wrong_hash=False):
        # The real compressed releases are exercised by the inventory runner.
        # This isolates tar validation without adding zstandard to app runtimes.
        decoder = types.SimpleNamespace(stream_reader=lambda stream: io.BytesIO(stream.read()))
        fake = types.SimpleNamespace(ZstdDecompressor=lambda: decoder)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict('sys.modules', zstandard=fake):
            path = Path(tmp) / 'common.tar.zst'
            digest = self.archive(path, members)
            return archive_rows(path, '0' * 64 if wrong_hash else digest)

    def test_members_preserve_non_target_process_and_content_identity(self):
        rows = self.run_archive([('sky130A/libs.tech/tool/source', tarfile.REGTYPE),
                                 ('sky130B/libs.tech/tool/source', tarfile.REGTYPE)])
        self.assertEqual([r['family'] for r in rows], ['sky130A', 'sky130B'])
        self.assertTrue(all(r['git_blob_sha1'] == git_hash('blob', b'source') for r in rows))

    def test_changed_archive_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Changed SKY130'):
            self.run_archive([('sky130A/source', tarfile.REGTYPE)], wrong_hash=True)

    def test_duplicates_links_unsafe_or_unknown_process_members_rejected(self):
        name = 'sky130A/source'
        for members in ([(name, tarfile.REGTYPE)] * 2, [(name, tarfile.SYMTYPE)],
                        [('../source', tarfile.REGTYPE)], [('sky130A/../source', tarfile.REGTYPE)],
                        [('sky130C/source', tarfile.REGTYPE)], [('sky130A/dir', tarfile.DIRTYPE)]):
            with self.subTest(members=members), self.assertRaises(ValueError):
                self.run_archive(members)


class BundledComparisonTests(unittest.TestCase):
    def packages(self, tmp):
        root = Path(tmp)
        (root / 'relocated.spice').write_bytes(b'original')
        (root / 'same-name.spice').write_bytes(b'local derivative')
        package = dict(revision='test', files={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                             for p in root.iterdir()})
        (root / 'package.json').write_bytes(canonical(package))
        return package_index(root)

    def test_matches_content_and_keeps_derivatives_unmatched(self):
        with tempfile.TemporaryDirectory() as tmp:
            metadata, index = self.packages(tmp)
            source = [dict(family='ihp-sg13g2', path='libs.tech/ngspice/same-name.spice',
                           git_blob_sha1=git_hash('blob', b'original'), mode='100644'),
                      dict(family='ihp-sg13g2', path='libs.tech/ngspice/missing.spice',
                           git_blob_sha1=git_hash('blob', b'not bundled'), mode='100644')]
            rows, views, unmatched = compare_files(source, {'ihp-sg13g2': index})
            by_path = {r['path']: r for r in rows}
            match = by_path[source[0]['path']]['comparisons']['ihp-sg13g2']
            self.assertEqual(match['paths'], ['relocated.spice'])
            self.assertEqual(unmatched['ihp-sg13g2'], ['same-name.spice'])
            self.assertEqual(views[0]['counts']['no_identical_bundled_file'], 1)
            self.assertEqual(metadata['files'], 2)

    def test_tampered_or_unsafe_package_assets_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.packages(tmp)
            (Path(tmp) / 'relocated.spice').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Changed bundled'):
                package_index(tmp)
            (Path(tmp) / 'package.json').write_bytes(canonical(dict(files={'../escape': '0' * 64})))
            with self.assertRaisesRegex(ValueError, 'Unsafe source'):
                package_index(tmp)

    def test_duplicate_effective_paths_and_symlink_false_matches_rejected(self):
        source = dict(family='ihp-sg13g2', path='link', git_blob_sha1='1' * 40, mode='120000')
        packages = {'ihp-sg13g2': {'1' * 40: ['regular-file']}}
        rows, _, _ = compare_files([source], packages)
        self.assertEqual(rows[0]['comparisons']['ihp-sg13g2']['status'], 'no_identical_bundled_file')
        with self.assertRaisesRegex(ValueError, 'Duplicate effective'):
            compare_files([source, source], packages)

    def test_portable_deterministic_compression_and_paths(self):
        a = compressed(dict(b=2, a=1))
        self.assertEqual(a, compressed(dict(a=1, b=2)))
        self.assertEqual(a[4:8], b'\0' * 4)
        self.assertEqual(a[9], 255)
        self.assertEqual(json.loads(gzip.decompress(a)), dict(a=1, b=2))
        for path in ('', '.', '../file', '/abs/file', 'C:/file', 'a\\b', 'a//b'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_path(path)


if __name__ == '__main__':
    unittest.main()
