from pathlib import Path
import tempfile,unittest,json,zipfile,hashlib
from scripts.package_ihp_wsl_research_preparation import package
class Delivery(unittest.TestCase):
 def test_full_bytes_parts_and_small_metadata(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);source=root/'source';(source/'host-proof/receipt').mkdir(parents=True)
   b=bytes(range(256))*300;(source/'host-proof/receipt/large.deb').write_bytes(b)
   (source/'commands.json').write_text('{"status":"synthetic-only"}')
   (source/'filesystem.tar').write_bytes(b'excluded scratch')
   (source/'experimental-payload').mkdir();(source/'experimental-payload/runtime.tar.gz').write_bytes(b'payload')
   (source/'experimental-payload/derivation.json').write_text('{}')
   (source/'experimental-payload/manifest.json').write_text(json.dumps({'archive':'runtime.tar.gz','bytes':7,'sha256':hashlib.sha256(b'payload').hexdigest()}))
   m=package(source,root/'out',part_limit=16384,chunk_limit=4096)
   self.assertGreater(len(m['parts']),1);self.assertTrue(all(x['bytes']<=16384 for x in m['parts'].values()))
   self.assertIn('filesystem.tar',m['excluded_scratch_files']);self.assertNotIn('filesystem.tar',m['files']);self.assertIn('runtime.tar.gz',m['separate_payload'])
   self.assertEqual(m['payload_transport']['max_parts'],16);self.assertTrue((root/'out/metadata/PAYLOAD.json').is_file())
   r=m['files']['host-proof/receipt/large.deb'];data=b''
   for c in r['chunks']:
    with zipfile.ZipFile(root/'out/proof-parts'/c['part']) as z:data+=z.read(c['member'])
   self.assertEqual(data,b);self.assertEqual(r['sha256'],hashlib.sha256(b).hexdigest())
 def test_incomplete_payload_still_retains_failure_metadata_and_proof(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);source=root/'source';source.mkdir();(source/'failure.log').write_text('failed build')
   (source/'experimental-payload').mkdir();(source/'experimental-payload/INCOMPLETE').write_text('partial')
   with self.assertRaisesRegex(ValueError,'proof/metadata retained'):package(source,root/'out')
   m=json.loads((root/'out/metadata/DELIVERY.json').read_text())
   self.assertEqual(m['payload_transport_failure']['status'],'FAILED_NO_NATIVE_ACCEPTANCE')
   self.assertTrue((root/'out/proof-parts/DELIVERY.json').is_file());self.assertIn('failure.log',m['files'])
 def test_fresh_outside_source(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)
   with self.assertRaises(ValueError):package(root,root/'nested')
 def test_empty_failure_receipt_retained(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);source=root/'source';source.mkdir();(source/'failure.log').write_bytes(b'')
   m=package(source,root/'out');self.assertEqual(m['files']['failure.log']['chunks'],[])
 def test_unknown_path_rejects(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);source=root/'source';(source/'unexpected').mkdir(parents=True);(source/'unexpected/extra.bin').write_bytes(b'not silently omitted')
   with self.assertRaisesRegex(ValueError,'Unknown preparation path'):package(source,root/'out')
 def test_unreadable_proof_retains_diagnostics_closes_partial_zip_and_reraises(self):
  from unittest.mock import patch
  from scripts import package_ihp_wsl_research_preparation as module
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);source=root/'source';lock=source/'host-proof/receipt/apt/lists/lock';lock.parent.mkdir(parents=True)
   lock.write_bytes(b'locked');(source/'commands.json').write_text('[{"returncode":1}]')
   (source/'completion.json').write_text('{"failure":"host verifier failed"}')
   original=module.file_sha;failure=PermissionError(13,'synthetic permission denied',str(lock))
   def sha(path):
    if Path(path)==lock:raise failure
    return original(path)
   with patch.object(module,'file_sha',side_effect=sha):
    with self.assertRaises(PermissionError) as caught:package(source,root/'out')
   self.assertIs(caught.exception,failure)
   m=json.loads((root/'out/metadata/DELIVERY.json').read_text())
   self.assertEqual(m['status'],'FAILED_INCOMPLETE_PROOF');self.assertFalse(m['proof_complete']);self.assertFalse(m['qualified'])
   self.assertEqual(m['failed_source_member'],'host-proof/receipt/apt/lists/lock')
   self.assertEqual((root/'out/metadata/failure-receipts/completion.json').read_bytes(),(source/'completion.json').read_bytes())
   parts=list((root/'out/proof-parts').glob('*.zip'));self.assertTrue(parts)
   for part in parts:
    with zipfile.ZipFile(part) as z:self.assertIsNone(z.testzip())
   self.assertFalse((root/'out/proof-parts/DELIVERY.json').exists())
 def test_failure_metadata_bounds_missing_and_no_unknown_copy(self):
  from scripts import package_ihp_wsl_research_preparation as module
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);source=root/'source';source.mkdir();out=root/'out'
   (source/'commands.json').write_bytes(b'x'*(module.FAILURE_FILE_LIMIT+1))
   (source/'collect-signed-host-provenance.stderr.log').write_bytes(b'a'*300000+b'END')
   (source/'unrelated.json').write_text('not in allowlist')
   module.retain_failure(source,out,PermissionError('no raw exception contents'))
   m=json.loads((out/'metadata/DELIVERY.json').read_text())
   self.assertEqual(m['receipts']['commands.json']['status'],'omitted_oversize')
   self.assertEqual(m['receipts']['completion.json']['status'],'missing')
   row=m['receipts']['collect-signed-host-provenance.stderr.log'];self.assertEqual(row['status'],'retained_tail');self.assertEqual(row['bytes'],65536)
   self.assertFalse((out/'metadata/failure-receipts/unrelated.json').exists())
   self.assertNotIn('no raw exception contents',json.dumps(m))
 def test_fallback_failure_never_replaces_original(self):
  from unittest.mock import patch
  from scripts import package_ihp_wsl_research_preparation as module
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);source=root/'source';source.mkdir();failure=PermissionError('original')
   with patch.object(module,'_package',side_effect=failure),patch.object(module,'retain_failure',side_effect=OSError('secondary')):
    with self.assertRaises(PermissionError) as caught:package(source,root/'out')
   self.assertIs(caught.exception,failure)
 def test_fallback_rejects_linked_diagnostics(self):
  from unittest.mock import patch
  from scripts import package_ihp_wsl_research_preparation as module
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);source=root/'source';source.mkdir();(source/'commands.json').write_text('unsafe')
   original=module.unlinked
   def unlinked(path):
    if Path(path)==source/'commands.json':raise ValueError('synthetic linked path')
    return original(path)
   with patch.object(module,'unlinked',side_effect=unlinked):module.retain_failure(source,root/'out',PermissionError())
   m=json.loads((root/'out/metadata/DELIVERY.json').read_text());self.assertEqual(m['receipts']['commands.json']['status'],'unreadable_or_unsafe')
   self.assertFalse((root/'out/metadata/failure-receipts/commands.json').exists())
class OriginalBaseDelivery(unittest.TestCase):
 def test_exact_original_base_gzip_bytes_retained_in_proof(self):
  import gzip,random
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);source=root/'source';source.mkdir()
   original=gzip.compress(random.Random(19).randbytes(12000),mtime=1700000000)
   (source/'base-runtime.tar.gz').write_bytes(original);(source/'filesystem.tar').write_bytes(b'omitted export scratch')
   m=package(source,root/'out',part_limit=4096,chunk_limit=1024)
   self.assertNotIn('base-runtime.tar.gz',m['excluded_build_scratch']);self.assertNotIn('base-runtime.tar.gz',m['excluded_scratch_files'])
   self.assertEqual(m['excluded_build_scratch'],['context/','filesystem.tar'])
   r=m['files']['base-runtime.tar.gz'];reconstructed=bytearray()
   for c in r['chunks']:
    self.assertEqual(c['offset'],len(reconstructed))
    with zipfile.ZipFile(root/'out/proof-parts'/c['part']) as z:reconstructed.extend(z.read(c['member']))
   self.assertEqual(bytes(reconstructed),original);self.assertEqual(r['sha256'],hashlib.sha256(original).hexdigest());self.assertEqual(r['bytes'],len(original))
   self.assertTrue(all(x['bytes']<=4096 for x in m['parts'].values()));self.assertEqual((source/'base-runtime.tar.gz').read_bytes(),original)
 def test_aggregate_cap_not_relaxed_for_original_base(self):
  import os
  from unittest.mock import patch
  from scripts import package_ihp_wsl_research_preparation as module
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);source=root/'source';source.mkdir();base=source/'base-runtime.tar.gz';base.write_bytes(b'fixture')
   original=Path.stat
   def fake(path,*args,**kwargs):
    value=original(path,*args,**kwargs)
    if path==base:
     values=list(value);values[6]=3*1024**3+1;return os.stat_result(values)
    return value
   with patch.object(Path,'stat',autospec=True,side_effect=fake),self.assertRaisesRegex(ValueError,'cap exceeded'):package(source,root/'out')
   self.assertFalse(json.loads((root/'out/metadata/DELIVERY.json').read_text())['proof_complete'])
 def test_sixteen_part_cap_unchanged(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);source=root/'source';source.mkdir();(source/'base-runtime.tar.gz').write_bytes(b'x'*(17*1024))
   with self.assertRaisesRegex(ValueError,'part count exceeded'):package(source,root/'out',part_limit=2048,chunk_limit=1024)
   self.assertLessEqual(len(list((root/'out/proof-parts').glob('*.zip'))),16)
 def test_default_caps_unchanged(self):
  from scripts import package_ihp_wsl_research_preparation as m
  self.assertEqual(m.PART_LIMIT,240*1024**2);self.assertEqual(m.CHUNK_LIMIT,16*1024**2);self.assertEqual(m.META_LIMIT,16*1024**2)

if __name__=='__main__':unittest.main()
