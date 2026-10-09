"""Pinned complete downloads, cache reuse and failure isolation."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from scripts import fetch_gf180_connectivity as fetch


class GF180ConnectivityFetchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.output=self.root/'output';self.cache=self.root/'cache'
        self.payloads={'library/LICENSE':b'shared notice','library/cells/inv/cell.cdl':b'CDL source',
                       'pv/LICENSE':b'shared notice','pv/klayout/lvs/gf180mcu.lvs':b'native rule'}
        self.locks={};self.urls={}
        for directory,attribute in [('library','LIBRARY_LOCK'),('pv','PV_LOCK')]:
            lock=dict(repository='https://github.com/fixture/'+directory,revision='a'*40,files={})
            for path,data in self.payloads.items():
                if not path.startswith(directory+'/'):continue
                name=path[len(directory)+1:];sha=hashlib.sha256(data).hexdigest()
                url='https://raw.githubusercontent.com/fixture/'+directory+'/'+'a'*40+'/'+name
                self.urls[url]=data
                lock['files'][name]=dict(sha256=sha,bytes=len(data),url=url,
                    git_blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()) if directory=='library' else sha
            target=self.root/(directory+'.json');target.write_text(json.dumps(lock),encoding='utf-8')
            self.locks[directory]=(target,lock)
            mock=patch.object(fetch,attribute,target);mock.start();self.addCleanup(mock.stop)

    def save_lock(self,directory):
        path,value=self.locks[directory];path.write_text(json.dumps(value),encoding='utf-8')

    def opener(self,url,timeout):return io.BytesIO(self.urls[url])

    def test_complete_atomic_publish_deduplicates_and_reuses_only_verified_cache(self):
        with patch.object(fetch.urllib.request,'urlopen',side_effect=self.opener) as network:
            self.assertEqual(fetch.fetch(self.output,cache=self.cache),self.output)
            self.assertEqual(network.call_count,3)
        for name,data in self.payloads.items():self.assertEqual((self.output/name).read_bytes(),data)
        with patch.object(fetch.urllib.request,'urlopen',side_effect=AssertionError('offline')):
            fetch.fetch(self.root/'offline-copy',cache=self.cache)
        for directory in ('library','pv'):
            self.assertEqual((self.output/(directory+'-source-lock.json')).read_bytes(),self.locks[directory][0].read_bytes())

    def test_corrupt_cached_source_is_refetched_before_publishing(self):
        with patch.object(fetch.urllib.request,'urlopen',side_effect=self.opener):fetch.fetch(self.output,cache=self.cache)
        sha=hashlib.sha256(b'CDL source').hexdigest();(self.cache/'sha256'/sha).write_bytes(b'corrupt')
        with patch.object(fetch.urllib.request,'urlopen',side_effect=self.opener) as network:
            fetch.fetch(self.root/'again',cache=self.cache);self.assertEqual(network.call_count,1)
        self.assertEqual((self.cache/'sha256'/sha).read_bytes(),b'CDL source')

    def test_bad_download_or_incomplete_transport_cannot_publish_a_partial_tree(self):
        for error in (None,urllib.error.URLError('offline')):
            with self.subTest(error=error),patch.object(fetch.time,'sleep'),patch.object(fetch.urllib.request,'urlopen',
                    side_effect=(lambda *a,**k:io.BytesIO(b'wrong checksum')) if error is None else error):
                with self.assertRaises((ValueError,urllib.error.URLError)):fetch.fetch(self.output,cache=self.cache)
            self.assertFalse(self.output.exists())
            self.assertFalse(list((self.cache/'sha256').glob('.gf180-*')))

    def test_transient_download_is_retried_and_only_verified_bytes_are_published(self):
        destination=self.root/'object';responses=[urllib.error.HTTPError('url',503,'unavailable',{},None),io.BytesIO(b'ok')]
        with patch.object(fetch.time,'sleep'),patch.object(fetch.urllib.request,'urlopen',side_effect=responses) as network:
            fetch.download('https://fixture',destination,hashlib.sha256(b'ok').hexdigest())
        self.assertEqual(network.call_count,2);self.assertEqual(destination.read_bytes(),b'ok')

    def test_url_revision_and_path_changes_are_rejected_before_fetching(self):
        path,original=self.locks['library'];original=json.loads(json.dumps(original))
        for fault in ('revision','url','path'):
            lock=json.loads(json.dumps(original))
            if fault=='revision':lock['revision']='main'
            elif fault=='url':lock['files']['LICENSE']['url']='https://example.com/wrong'
            else:lock['files']['../escape']=lock['files'].pop('LICENSE')
            path.write_text(json.dumps(lock),encoding='utf-8')
            with self.subTest(fault=fault),patch.object(fetch.urllib.request,'urlopen') as network:
                with self.assertRaises(ValueError):fetch.fetch(self.output,cache=self.cache)
                network.assert_not_called();self.assertFalse(self.output.exists())

    def test_size_and_git_blob_are_independently_checked(self):
        path,lock=self.locks['library'];original=json.loads(json.dumps(lock))
        for field,value in [('bytes',999),('git_blob','0'*40)]:
            lock=json.loads(json.dumps(original));lock['files']['LICENSE'][field]=value
            path.write_text(json.dumps(lock),encoding='utf-8')
            with self.subTest(field=field),patch.object(fetch.urllib.request,'urlopen',side_effect=self.opener):
                with self.assertRaisesRegex(ValueError,'complete lock'):fetch.fetch(self.output,cache=self.cache)
                self.assertFalse(self.output.exists())

    def test_existing_destination_and_overlapping_cache_are_preserved(self):
        self.output.mkdir();marker=self.output/'keep';marker.write_bytes(b'important')
        with self.assertRaisesRegex(ValueError,'preserve existing'):fetch.fetch(self.output,cache=self.cache)
        self.assertEqual(marker.read_bytes(),b'important')
        with self.assertRaisesRegex(ValueError,'separate'):fetch.fetch(self.root/'new',cache=self.root/'new/cache')


if __name__=='__main__':unittest.main()
