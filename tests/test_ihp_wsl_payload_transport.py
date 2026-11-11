import copy,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from scripts import transport_ihp_wsl_payload as t
class PayloadTransport(unittest.TestCase):
 def source(self,root):
  p=root/'payload';p.mkdir();(p/'runtime.tar.gz').write_bytes(bytes(range(256))*25)
  (p/'derivation.json').write_text('{"research":true}')
  (p/'manifest.json').write_text(json.dumps({'archive':'runtime.tar.gz','bytes':6400,'sha256':t.file_sha(p/'runtime.tar.gz')}));return p
 def test_lossless_bounded_roundtrip(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);source=self.source(root);parts=root/'parts';m=t.package(source,parts,1024)
   self.assertEqual(len(list(parts.glob('*.bin'))),9)
   self.assertTrue(all(p.stat().st_size<=1024 for p in parts.glob('*.bin')))
   out=root/'restored';t.verify(parts,t.file_sha(parts/'PAYLOAD.json'),out)
   self.assertEqual({p.name:p.read_bytes() for p in out.iterdir()},{p.name:p.read_bytes() for p in source.iterdir()})
   with self.assertRaises(ValueError):t.verify(parts,t.file_sha(parts/'PAYLOAD.json'),out)
 def test_part_mutations_and_manifest_identity(self):
  for mode in ('missing','changed','extra','duplicate','offset','path','size','fullhash','manifest'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
    root=Path(temp);parts=root/'parts';m=t.package(self.source(root),parts,1024);mp=parts/'PAYLOAD.json';h=t.file_sha(mp);r=m['files']['runtime.tar.gz'];ref=r['parts'][0]
    if mode=='missing':(parts/ref['name']).unlink()
    elif mode=='changed':(parts/ref['name']).write_bytes(b'x'*ref['bytes'])
    elif mode=='extra':(parts/'unexpected').write_text('x')
    else:
     if mode=='duplicate':r['parts'].append(copy.deepcopy(ref))
     if mode=='offset':ref['offset']=1
     if mode=='path':ref['name']='../outside'
     if mode=='size':ref['bytes']=t.LIMIT+1
     if mode=='fullhash':r['sha256']='0'*64
     if mode=='manifest':m['scope']='changed'
     mp.write_bytes(t.encoded(m))
     if mode!='manifest':h=t.file_sha(mp)
    with self.assertRaises(ValueError):t.verify(parts,h,root/'restored')
    self.assertFalse((root/'restored').exists() and not (root/'restored/INCOMPLETE').exists())
 def test_source_inventory_inner_hash_and_limits(self):
  for mode in ('extra','inner','cap','count'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
    root=Path(temp);s=self.source(root)
    if mode=='extra':(s/'extra').write_text('x')
    if mode=='inner':(s/'runtime.tar.gz').write_bytes(b'changed')
    with patch.object(t,'MAX_TOTAL',100 if mode=='cap' else t.MAX_TOTAL),patch.object(t,'MAX_PARTS',2 if mode=='count' else t.MAX_PARTS):
     with self.assertRaises(ValueError):t.package(s,root/'parts',1024)
    self.assertFalse((root/'parts').exists())
 def test_actual_outer_artifact_identity_and_roundtrip(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);source=self.source(root);parts=root/'parts';t.package(source,parts,1024);mh=t.file_sha(parts/'PAYLOAD.json');dest=root/'downloaded'
   for p in sorted(parts.glob('*.bin')):
    outer=root/(p.name+'.zip')
    with zipfile.ZipFile(outer,'x',compression=zipfile.ZIP_STORED) as z:z.write(p,p.name);z.write(parts/'PAYLOAD.json','PAYLOAD.json')
    h=t.file_sha(outer);size=outer.stat().st_size
    with self.assertRaises(ValueError):t.ingest_artifact(outer,size+1,h,mh,p.name,dest)
    with self.assertRaises(ValueError):t.ingest_artifact(outer,size,'0'*64,mh,p.name,dest)
    t.ingest_artifact(outer,size,h,mh,p.name,dest)
   t.verify(dest,mh,root/'restored')
   self.assertEqual((root/'restored/runtime.tar.gz').read_bytes(),(source/'runtime.tar.gz').read_bytes())
   self.assertLess(t.LIMIT+1024**2+1024**2,256*1024**2)
   from scripts.package_ihp_wsl_research_preparation import PART_LIMIT
   self.assertLess(PART_LIMIT+8*1024**2+1024**2,256*1024**2)
 def test_linked_part_rejected_without_link_privilege(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);parts=root/'parts';t.package(self.source(root),parts,1024);original=t.unlinked
   def guard(p):
    if Path(p).suffix=='.bin':raise ValueError('Mocked reparse point')
    return original(p)
   with patch.object(t,'unlinked',side_effect=guard):
    with self.assertRaises(ValueError):t.verify(parts,t.file_sha(parts/'PAYLOAD.json'))
if __name__=='__main__':unittest.main()
