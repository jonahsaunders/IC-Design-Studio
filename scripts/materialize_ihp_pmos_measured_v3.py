"""Lossless portable materialization; no upstream code/model execution."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,zipfile,stat
COMPACT_SHA='1f49b494236845576c7e195a68fa7a36f468e47231d383a86d44ea8ad7010003'
BASE_SHA='e74736fd70b2fa6972bb0e0ab77cf87fff38f5926a7cb19d03431c2663e2b714'
MANIFEST_SHA='8f583f2a0002a17fdb268502e53d269cee73d633fe3aff1a9311f2ead0125a87'
def is_linked(path):
 try:s=Path(path).lstat()
 except FileNotFoundError:return False
 return stat.S_ISLNK(s.st_mode) or bool(getattr(s,'st_file_attributes',0)&0x400)
def digest(data):return hashlib.sha256(data).hexdigest()
def require(ok,msg):
 if not ok:raise ValueError(msg)
def unlinked(path):
 p=Path(path).absolute()
 for q in (p,*p.parents):require(not is_linked(q),'Linked path')
 return p
def materialize(compact,engine_archive,output):
 compact=unlinked(compact);engine_archive=unlinked(engine_archive);output=unlinked(output)
 require(not output.exists(),'Fresh output required')
 cb=compact.read_bytes();bb=engine_archive.read_bytes()
 require(digest(cb)==COMPACT_SHA and digest(bb)==BASE_SHA,'Transport/base identity changed')
 with zipfile.ZipFile(compact) as z,zipfile.ZipFile(engine_archive) as base:
  require(len(z.namelist())==len(set(z.namelist())) and len(base.namelist())==len(set(base.namelist())),'Duplicate archive entry')
  mb=z.read('MANIFEST.json');require(digest(mb)==MANIFEST_SHA,'Manifest identity changed')
  manifest=json.loads(mb);t=json.loads(z.read('TRANSPORT.json'))
  require(t['manifest_sha256']==MANIFEST_SHA and t['base_archive_sha256']==BASE_SHA,'Transport binding')
  require(set(t['references'])==set(manifest['files']),'Reference coverage')
  require(len({n.casefold() for n in manifest['files']})==len(manifest['files']),'Case collision')
  # Prevalidate every object before creating destination; bounded by exact pinned sizes.
  for n,r in manifest['files'].items():
   p=PurePosixPath(n);require(not p.is_absolute() and all(x not in ('','..','.') for x in p.parts) and '\\' not in n and ':' not in n,'Unsafe member')
   ref=t['references'][n];kind=ref['kind']
   if kind=='base_archive':data=bb
   elif kind=='base_member':
    require(base.getinfo(ref['member']).file_size==r['bytes'],'Base member size');data=base.read(ref['member'])
   elif kind=='blob':
    require(z.getinfo(ref['member']).file_size==r['bytes'],'Blob size');data=z.read(ref['member'])
   else:raise ValueError('Unknown reference')
   require(len(data)==r['bytes'] and digest(data)==r['sha256'],'Payload identity')
  output.mkdir(parents=True)
  for n,r in manifest['files'].items():
   ref=t['references'][n]
   data=bb if ref['kind']=='base_archive' else base.read(ref['member']) if ref['kind']=='base_member' else z.read(ref['member'])
   require(digest(data)==r['sha256'],'Payload changed')
   p=output/n;p.parent.mkdir(parents=True,exist_ok=True)
   with p.open('xb') as f:f.write(data)
  with (output/'MANIFEST.json').open('xb') as f:f.write(mb)
 return {'files':len(manifest['files']),'manifest_sha256':MANIFEST_SHA,'executed_upstream_code':False}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('compact',type=Path);p.add_argument('engine_archive',type=Path);p.add_argument('output',type=Path);a=p.parse_args();print(json.dumps(materialize(a.compact,a.engine_archive,a.output)))
if __name__=='__main__':main()
