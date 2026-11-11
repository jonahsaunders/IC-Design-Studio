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
if __name__=='__main__':unittest.main()
