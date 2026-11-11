"""New post-reset derivation tests; no native tools or models execute."""
import io,json,hashlib,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import prepare_ihp_wsl_research_payload as p
class Payload(unittest.TestCase):
 def archive(self,root,extra=None):
  rows={'usr/lib/lib'+str(i)+'.so':b'library'+bytes([i]) for i in range(8)}
  rows.update({'opt/icstudio/packages.tsv':b'packages','opt/icstudio/simulation/source-lock.json':b'{}'})
  if extra:rows.update(extra)
  locks={n:hashlib.sha256(v).hexdigest() for n,v in rows.items()};rows[p.FILES]=p.encoded(locks);rows[p.RUNTIME]=p.encoded({'files_sha256':hashlib.sha256(rows[p.FILES]).hexdigest()})
  target=root/'base.tar.gz'
  with tarfile.open(target,'w:gz') as z:
   for n,b in rows.items():m=tarfile.TarInfo(n);m.size=len(b);m.mode=0o644;z.addfile(m,io.BytesIO(b))
  return target,rows
 def test_exact_inventory_and_dependencies(self):
  with tempfile.TemporaryDirectory() as td:
   base,rows=self.archive(Path(td));e,l,r=p.inspect_archive(base,p.file_sha(base))
   deps={'/'+n:h for n,h in l.items() if n.startswith('usr/')};p.check_dependencies(e,deps)
   deps['/usr/lib/lib0.so']='0'*64
   with self.assertRaises(ValueError):p.check_dependencies(e,deps)
 def test_member_size_and_total_caps(self):
  with tempfile.TemporaryDirectory() as td:
   base,_=self.archive(Path(td))
   with patch.object(p,'MAX_MEMBER',2):
    with self.assertRaises(ValueError):p.inspect_archive(base,p.file_sha(base))
   with patch.object(p,'MAX_TOTAL',2):
    with self.assertRaises(ValueError):p.inspect_archive(base,p.file_sha(base))
 def test_wrong_lock_membership_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);base,rows=self.archive(root);rows[p.FILES]=p.encoded({});rows[p.RUNTIME]=p.encoded({'files_sha256':hashlib.sha256(rows[p.FILES]).hexdigest()})
   with tarfile.open(base,'w:gz') as z:
    for n,b in rows.items():m=tarfile.TarInfo(n);m.size=len(b);z.addfile(m,io.BytesIO(b))
   with self.assertRaisesRegex(ValueError,'Exact base lock'):p.inspect_archive(base,p.file_sha(base))
 def test_unsafe_names_duplicate_and_link_ancestors(self):
  for mode in ('traversal','duplicate','ancestor','absolute-link'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
    target=Path(td)/'bad.tar'
    with tarfile.open(target,'w') as z:
     if mode=='traversal':m=tarfile.TarInfo('../bad');m.size=1;z.addfile(m,io.BytesIO(b'x'))
     if mode=='duplicate':
      for _ in range(2):z.addfile(tarfile.TarInfo('duplicate'))
     if mode in ('ancestor','absolute-link'):
      m=tarfile.TarInfo('a');m.type=tarfile.SYMTYPE;m.linkname='/outside' if mode=='absolute-link' else 'b';z.addfile(m)
      if mode=='ancestor':m=tarfile.TarInfo('a/child');z.addfile(m)
    with self.assertRaises(ValueError):p.inspect_archive(target,p.file_sha(target))
 def test_complete_synthetic_base_derivation_no_native_execution(self):
  from scripts.materialize_ihp_pmos_measured_v3 import materialize
  repo=Path(__file__).resolve().parents[1]
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);e=root/'evidence';materialize(repo/'docs/qualification/ihp-pmos-measured-reference-v3/evidence-compact.zip',repo/'packaging/ngspice/ngspice-linux47-corrected-v1.zip',e)
   modules=e/'measured-v3/osdi-inputs';va=e/'measured-v3/attempt-1/pdk/libs.tech/verilog-a'
   model_rows=[];extra={'opt/icstudio/bin/ngspice':b'old wrapper'}
   for f in modules.glob('*.osdi'):
    source='psp103/'+f.stem+'.va' if f.stem.startswith('psp103') else f.stem+'/'+f.stem+'.va'
    deps={q.relative_to(va).as_posix():p.file_sha(q) for q in (va/source).parent.iterdir() if q.is_file()}
    model_rows.append({'source':source,'output':f.name,'dependencies':deps,'sha256':p.file_sha(f)});extra['opt/icstudio/osdi/ihp-sg13g2/'+f.name]=f.read_bytes()
   report={'system':'Linux','machine':'x86_64','cpu_target':'generic','models':model_rows};extra['opt/icstudio/osdi/ihp-sg13g2/build.json']=p.encoded(report)
   base,rows=self.archive(root,extra);inner=json.loads(rows[p.RUNTIME]);inner['osdi']={'ihp-sg13g2':report};rows[p.RUNTIME]=p.encoded(inner)
   with tarfile.open(base,'w:gz') as z:
    for n,b in rows.items():m=tarfile.TarInfo(n);m.size=len(b);m.mode=0o644;z.addfile(m,io.BytesIO(b))
   entries,locks,_=p.inspect_archive(base,p.file_sha(base))
   host={'scope':'REVIEWED_NEW_WSL_HOST_BASELINE','new_host_baseline':True,'qualified':False,'approved_six_module_loading':True,'base_archive_sha256':p.file_sha(base),'dependencies':{'/'+n:h for n,h in locks.items() if n.startswith('usr/')},'base_source_provenance':{n:locks[n] for n in ('opt/icstudio/packages.tsv','opt/icstudio/simulation/source-lock.json')}}
   hp=root/'host.json';hp.write_bytes(p.encoded(host));out=root/'derived';p.prepare(base,p.file_sha(base),e,out,hp,p.file_sha(hp))
   manifest=json.loads((out/'manifest.json').read_text());new,_,actual=p.inspect_archive(out/'runtime.tar.gz',manifest['sha256'])
   self.assertFalse((out/'INCOMPLETE').exists());self.assertEqual(new['opt/icstudio/osdi/ihp-sg13g2/psp103.osdi']['sha256'],p.PSP)
   self.assertEqual(new[p.RESEARCH+'measured-v3/attempt-1/engine/runtime/ngspice']['sha256'],p.ENGINE)
   self.assertEqual(actual['experimental_research']['host_contract_sha256'],p.file_sha(hp))
   for n,h in host['dependencies'].items():self.assertEqual(new[n[1:]]['sha256'],h)
   changed={'opt/icstudio/bin/ngspice','opt/icstudio/osdi/ihp-sg13g2/build.json',p.FILES,p.RUNTIME}|{'opt/icstudio/osdi/ihp-sg13g2/'+f.name for f in modules.glob('*.osdi')}
   for n,row in entries.items():
    if n not in changed:self.assertEqual(new[n],row,n)
   self.assertEqual(new['opt/icstudio/bin/ngspice']['mode'],0o755)
   retained={q.relative_to(e).as_posix():p.file_sha(q) for q in e.rglob('*') if q.is_file()}
   self.assertEqual(len(retained),589) #588 immutable payload files plus MANIFEST.json
   for n,h in retained.items():self.assertEqual(new[p.RESEARCH+n]['sha256'],h)
   self.assertEqual(manifest['bytes'],(out/'runtime.tar.gz').stat().st_size)
   self.assertNotIn(p.FILES,json.loads(rows[p.FILES]));self.assertNotIn(p.RUNTIME,json.loads(rows[p.FILES]))
   original_inspect=p.inspect_archive
   def fail_final(path,sha):
    if Path(path).parent.name=='failed':raise ValueError('injected output inspection failure')
    return original_inspect(path,sha)
   with patch.object(p,'inspect_archive',side_effect=fail_final):
    with self.assertRaisesRegex(ValueError,'injected output'):p.prepare(base,p.file_sha(base),e,root/'failed',hp,p.file_sha(hp))
   self.assertTrue((root/'failed/INCOMPLETE').is_file());self.assertFalse((root/'failed/manifest.json').exists())

 def test_reparse_guard(self):
  with tempfile.TemporaryDirectory() as td,patch.object(p,'is_linked',return_value=True):
   with self.assertRaises(ValueError):p.unlinked(Path(td)/'missing')
if __name__=='__main__':unittest.main()
