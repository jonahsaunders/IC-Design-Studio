"""Adversarial cache acquisition tests; no network or upstream execution."""
import gzip
import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import sys
import unittest
from unittest.mock import patch
import urllib.error
from scripts import recover_source_disposition_cache as recovery

REV = 'a'*40
REPO = 'official/sample@'+REV
PREFIX = 'sample-'+REV


def row(data=b'original\n', mode='100644'):
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                git_blob_sha1=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest(), mode=mode)


def archive(entries):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w:gz') as tar:
        for name, data, kind in entries:
            item = tarfile.TarInfo(name)
            if kind == 'file':
                item.size = len(data); tar.addfile(item, io.BytesIO(data))
            elif kind == 'symlink':
                item.type = tarfile.SYMTYPE; item.linkname = data.decode(); tar.addfile(item)
            elif kind == 'hardlink':
                item.type = tarfile.LNKTYPE; item.linkname = data.decode(); tar.addfile(item)
            elif kind == 'device':
                item.type = tarfile.CHRTYPE; tar.addfile(item)
    return out.getvalue()


class SourceCacheRecoveryTests(unittest.TestCase):
    def recover(self, entries, wanted=None, limit=1024*1024):
        wanted = {'path.txt':row()} if wanted is None else wanted
        with tempfile.TemporaryDirectory() as folder:
            count = recovery.recover_archive(io.BytesIO(archive(entries)), REPO, wanted, folder, limit)
            return count, {p.name:p.read_bytes() for p in Path(folder).iterdir()}

    def test_exact_regular_source_only_is_retained(self):
        count, files = self.recover([(PREFIX+'/path.txt', b'original\n', 'file'),
                                     (PREFIX+'/ignored.txt', b'do not retain', 'file')])
        self.assertEqual(count, 1)
        self.assertEqual(files, {row()['git_blob_sha1']:b'original\n'})

    def test_exact_reviewed_repository_rename_preserves_revision_and_bytes(self):
        repo, name = next(iter(recovery.ARCHIVE_NAMES.items()))
        revision = repo.rsplit('@', 1)[1]
        raw = archive([(name+'-'+revision+'/path.txt', b'original\n', 'file')])
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(recovery.recover_archive(io.BytesIO(raw), repo, {'path.txt':row()}, folder, 1024*1024), 1)
            with self.assertRaisesRegex(ValueError, 'archive root'):
                recovery.recover_archive(io.BytesIO(raw), repo.rsplit('@',1)[0]+'@'+'0'*40,
                                         {'path.txt':row()}, folder, 1024*1024)

    def test_literal_symlink_becomes_regular_blob_data_not_traversal(self):
        target = b'../../outside'
        count, files = self.recover([(PREFIX+'/link', target, 'symlink')], {'link':row(target, '120000')})
        self.assertEqual(count, 1)
        self.assertEqual(files, {row(target)['git_blob_sha1']:target})

    def test_missing_member_rejects_without_partial_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            wanted = {'path.txt':row(), 'absent':row(b'absent')}
            with self.assertRaisesRegex(ValueError, 'missing'):
                recovery.recover_archive(io.BytesIO(archive([(PREFIX+'/path.txt',b'original\n','file')])), REPO,wanted,folder,1024*1024)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_duplicate_wanted_and_unwanted_members_reject(self):
        for name in ('path.txt', 'ignored'):
            entries = [(PREFIX+'/path.txt',b'original\n','file'),(PREFIX+'/'+name,b'original\n','file')]
            if name == 'ignored': entries.append(entries[-1])
            with self.assertRaisesRegex(ValueError, 'duplicate'):self.recover(entries)

    def test_malicious_paths_and_wrong_roots_reject(self):
        for name in ('../escape', '/absolute', PREFIX+'/../escape', PREFIX+'/a//b',
                     PREFIX+'/a\\b', 'other-'+REV+'/path.txt'):
            with self.subTest(name=name), self.assertRaises(ValueError):self.recover([(name,b'x','file')])

    def test_unknown_special_files_and_hardlinks_reject(self):
        for kind in ('hardlink', 'device'):
            with self.assertRaisesRegex(ValueError, 'member type'):
                self.recover([(PREFIX+'/ignored',b'path.txt',kind)])

    def test_regular_symlink_type_substitution_rejects(self):
        for kind, expected in (('symlink','100644'),('file','120000')):
            with self.assertRaisesRegex(ValueError, 'type changed'):
                self.recover([(PREFIX+'/path.txt',b'original\n',kind)], {'path.txt':row(mode=expected)})

    def test_oversized_truncated_mismatched_and_wrong_git_inputs_reject(self):
        for data in (b'original\nextra',b'origin',b'changed!\n'):
            with self.assertRaises(ValueError):self.recover([(PREFIX+'/path.txt',data,'file')])
        wrong = row()|{'git_blob_sha1':'0'*40}
        with self.assertRaisesRegex(ValueError,'Git blob'):
            self.recover([(PREFIX+'/path.txt',b'original\n','file')], {'path.txt':wrong})

    def test_expanded_and_compressed_stream_limits_reject(self):
        with self.assertRaisesRegex(ValueError, 'byte limit'):
            self.recover([(PREFIX+'/path.txt',b'original\n','file')], limit=5)
        with self.assertRaisesRegex(ValueError, 'byte limit'):
            self.recover([(PREFIX+'/ignored',b'0'*100000,'file'),(PREFIX+'/path.txt',b'original\n','file')], limit=2000)

    def test_corrupt_gzip_trailer_rejects(self):
        raw = bytearray(archive([(PREFIX+'/path.txt',b'original\n','file')]))
        raw[-8] ^= 1
        with tempfile.TemporaryDirectory() as folder, self.assertRaises((gzip.BadGzipFile,ValueError)):
            recovery.recover_archive(io.BytesIO(raw),REPO,{'path.txt':row()},folder,1024*1024)

    def test_symlink_cache_destination_rejects(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/row()['git_blob_sha1']
            try:
                target.symlink_to(Path(folder)/'elsewhere')
            except OSError as exc:
                if sys.platform == 'win32':
                    self.skipTest('Host cannot create a symlink: '+str(exc))
                raise
            with self.assertRaisesRegex(ValueError,'symlink'):
                recovery.recover_archive(io.BytesIO(archive([(PREFIX+'/path.txt',b'original\n','file')])),REPO,{'path.txt':row()},folder,1024*1024)

    def test_cached_file_readback_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'blob';p.write_bytes(b'original\n');recovery.verify_file(p,row())
            p.write_bytes(b'changed!\n')
            with self.assertRaises(ValueError):recovery.verify_file(p,row())

    def test_asset_stream_checks_size_and_digest_before_acceptance(self):
        for raw in (b'original\nextra',b'origin',b'changed!\n'):
            with self.assertRaises(ValueError):
                recovery.verify_stream(io.BytesIO(raw),(row()['bytes'],row()['sha256']))

    def test_local_storage_and_integrity_errors_are_not_network_retries(self):
        for error in (OSError('disk full'), gzip.BadGzipFile('corrupt trailer')):
            events=[]
            with patch.object(recovery.time, 'sleep') as sleep:
                with self.assertRaises(type(error)):
                    recovery.bounded_retry(lambda:(_ for _ in ()).throw(error),
                                           lambda **kw:events.append(kw), 'source')
                sleep.assert_not_called()
            self.assertEqual(events, [])

    def test_deadline_and_retry_are_bounded(self):
        reader=recovery.LimitedReader(io.BytesIO(b'x'),1,seconds=-1)
        with self.assertRaisesRegex(ValueError,'deadline'):reader.read(1)
        events=[]
        with patch.object(recovery.time,'sleep') as sleep:
            with self.assertRaises(urllib.error.URLError):
                recovery.bounded_retry(lambda:(_ for _ in ()).throw(urllib.error.URLError('blocked')),
                                       lambda **kw:events.append(kw),'source')
            self.assertEqual(len(events),2);sleep.assert_called_once_with(2)
        events=[]
        with self.assertRaises(ValueError):
            recovery.bounded_retry(lambda:(_ for _ in ()).throw(ValueError('integrity')),
                                   lambda **kw:events.append(kw),'source')
        self.assertEqual(events,[])


if __name__ == '__main__':unittest.main()
