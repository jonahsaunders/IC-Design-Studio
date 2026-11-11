"""Lossless bounded transport of an experimental payload; no runtime execution."""
from pathlib import Path
import argparse,hashlib,json,sys,zipfile,stat
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.prepare_ihp_wsl_research_payload import unlinked,encoded,file_sha
from scripts.read_ihp_pmos_measured_v3 import require
LIMIT=240*1024**2
MAX_PARTS=16
MAX_TOTAL=4*1024**3
NAMES={'manifest.json','runtime.tar.gz','derivation.json'}

def inventory(root):
 root=unlinked(root)
 for p in root.rglob('*'):unlinked(p)
 return {p.name:p for p in root.iterdir() if p.is_file()}

def verify(parts,manifest_sha,output=None):
 parts=unlinked(parts);m=unlinked(parts/'PAYLOAD.json')
 require(m.stat().st_size<=1024**2 and file_sha(m)==manifest_sha,'Payload transport manifest identity')
 d=json.loads(m.read_text());require(d['schema']==1 and set(d['files'])==NAMES,'Payload file membership')
 refs=[ref for row in d['files'].values() for ref in row['parts']]
 names=[x['name'] for x in refs]
 require(1<=len(names)<=MAX_PARTS and len(set(names))==len(names),'Payload part uniqueness/count')
 require(set(names)=={f'payload-{i:04d}.bin' for i in range(1,len(names)+1)},'Payload part names')
 require({p.name for p in parts.iterdir()}==set(names)|{'PAYLOAD.json'},'Exact payload transport inventory')
 require(0<sum(r['bytes'] for r in d['files'].values())<=MAX_TOTAL,'Payload aggregate limit')
 out=None
 if output is not None:
  out=unlinked(output);require(not out.exists() and not out.is_relative_to(parts),'Fresh separate reconstruction output');out.mkdir(parents=True);(out/'INCOMPLETE').write_text('Not verified\n')
 for name,row in d['files'].items():
  h=hashlib.sha256();offset=0;target=(out/name).open('xb') if out else None
  try:
   for ref in row['parts']:
    require(type(ref['bytes']) is int and 0<ref['bytes']<=LIMIT and ref['offset']==offset,'Payload part bounds/offset')
    p=unlinked(parts/ref['name']);require(p.is_file() and p.stat().st_size==ref['bytes'],'Payload part size')
    ph=hashlib.sha256();count=0
    with p.open('rb') as f:
     while block:=f.read(1024**2):
      count+=len(block);require(count<=ref['bytes'],'Payload part grew');ph.update(block);h.update(block)
      if target:target.write(block)
    require(count==ref['bytes'] and ph.hexdigest()==ref['sha256'],'Payload part digest')
    offset+=count
   require(offset==row['bytes'] and h.hexdigest()==row['sha256'],'Full payload reconstruction digest')
  finally:
   if target:target.close()
 require(file_sha(m)==manifest_sha and {p.name for p in parts.iterdir()}==set(names)|{'PAYLOAD.json'},'Transport manifest/inventory changed')
 if out:
  manifest=json.loads((out/'manifest.json').read_text())
  require(manifest['archive']=='runtime.tar.gz' and manifest['bytes']==(out/'runtime.tar.gz').stat().st_size and manifest['sha256']==file_sha(out/'runtime.tar.gz'),'Inner runtime archive identity')
  (out/'INCOMPLETE').unlink()
 return d

def package(source,output,part_limit=LIMIT):
 source=unlinked(source);out=unlinked(output);require(not out.exists() and not out.is_relative_to(source),'Fresh separate transport output')
 require(type(part_limit) is int and 1024<=part_limit<=LIMIT,'Part limit')
 require({p.name for p in source.iterdir()}==NAMES,'Exact payload source membership')
 paths=inventory(source);require(set(paths)==NAMES,'Payload files only')
 before={n:{'bytes':p.stat().st_size,'sha256':file_sha(p)} for n,p in paths.items()}
 require(0<sum(r['bytes'] for r in before.values())<=MAX_TOTAL,'Payload aggregate limit')
 require(sum((r['bytes']+part_limit-1)//part_limit for r in before.values())<=MAX_PARTS,'Payload exceeds16 bounded parts')
 inner=json.loads(paths['manifest.json'].read_text())
 require(inner['archive']=='runtime.tar.gz' and inner['bytes']==before['runtime.tar.gz']['bytes'] and inner['sha256']==before['runtime.tar.gz']['sha256'],'Inner runtime archive identity')
 out.mkdir(parents=True);(out/'INCOMPLETE').write_text('Transport preparation incomplete\n');d={'schema':1,'scope':'LOSSLESS_PAYLOAD_TRANSPORT_NOT_NATIVE_ACCEPTANCE','max_part_bytes':LIMIT,'max_parts':MAX_PARTS,'files':{}};index=0
 for name,p in sorted(paths.items()):
  row=dict(before[name],parts=[]);d['files'][name]=row;offset=0
  with p.open('rb') as f:
   while offset<row['bytes']:
    index+=1;part=out/f'payload-{index:04d}.bin';size=min(part_limit,row['bytes']-offset);h=hashlib.sha256();count=0
    with part.open('xb') as target:
     while count<size:
      block=f.read(min(1024**2,size-count));require(bool(block),'Payload source truncated');target.write(block);h.update(block);count+=len(block)
    row['parts'].append({'name':part.name,'offset':offset,'bytes':size,'sha256':h.hexdigest()});offset+=size
   require(not f.read(1),'Payload source grew')
 (out/'PAYLOAD.json').write_bytes(encoded(d));(out/'INCOMPLETE').unlink()
 try:
  verify(out,file_sha(out/'PAYLOAD.json'))
  current=inventory(source)
  require({p.name for p in source.iterdir()}==NAMES and set(current)==NAMES and all(p.stat().st_size==before[n]['bytes'] and file_sha(p)==before[n]['sha256'] for n,p in current.items()),'Payload source changed during transport')
 except BaseException:
  (out/'INCOMPLETE').write_text('Transport readback/source verification failed\n');raise
 return d

def ingest_artifact(archive,expected_bytes,expected_sha,manifest_sha,part_name,output):
 """Validate actual outer Actions ZIP against its separately retained metadata.
 No general extraction: only one named binary part and identical PAYLOAD.json.
 """
 archive=unlinked(archive);out=unlinked(output)
 require(type(expected_bytes) is int and 0<expected_bytes<=256*1024**2,'Outer artifact size cap')
 require(archive.stat().st_size==expected_bytes and file_sha(archive)==expected_sha,'Outer artifact identity')
 require(part_name in {f'payload-{i:04d}.bin' for i in range(1,MAX_PARTS+1)},'Requested part name')
 with zipfile.ZipFile(archive) as z:
  infos=z.infolist();require(len(infos)==2 and {i.filename for i in infos}=={part_name,'PAYLOAD.json'},'Outer artifact inventory')
  for i in infos:
   require(i.orig_filename==i.filename and not i.is_dir() and not i.flag_bits&1 and stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFREG),'Outer artifact member type/name')
  mi=z.getinfo('PAYLOAD.json');require(mi.file_size<=1024**2,'Outer manifest cap');mb=z.read(mi)
  require(hashlib.sha256(mb).hexdigest()==manifest_sha,'Outer payload manifest identity')
  d=json.loads(mb);refs=[ref for row in d['files'].values() for ref in row['parts'] if ref['name']==part_name]
  require(len(refs)==1,'Part manifest ambiguity');ref=refs[0];pi=z.getinfo(part_name)
  require(type(ref['bytes']) is int and 0<ref['bytes']<=LIMIT and pi.file_size==ref['bytes'],'Outer part size')
  out.mkdir(parents=True,exist_ok=True);target=unlinked(out/part_name);partial=unlinked(out/(part_name+'.partial'));mp=unlinked(out/'PAYLOAD.json')
  require(not target.exists() and not partial.exists(),'Fresh part target')
  if mp.exists():require(mp.read_bytes()==mb,'Conflicting payload manifests')
  h=hashlib.sha256();count=0
  with z.open(pi) as source,partial.open('xb') as dest:
   while block:=source.read(1024**2):
    count+=len(block);require(count<=ref['bytes'],'Outer decompressed cap');dest.write(block);h.update(block)
  require(count==ref['bytes'] and h.hexdigest()==ref['sha256'],'Outer part digest')
  require(file_sha(archive)==expected_sha,'Outer artifact changed')
  if not mp.exists():
   with mp.open('xb') as f:f.write(mb)
  partial.rename(target)
 return {'outer_bytes':expected_bytes,'outer_sha256':expected_sha,'part':part_name,'part_sha256':h.hexdigest(),'payload_manifest_sha256':manifest_sha}

def main():
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
 a=sub.add_parser('package');a.add_argument('--source',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
 a=sub.add_parser('reconstruct');a.add_argument('--parts',type=Path,required=True);a.add_argument('--manifest-sha256',required=True);a.add_argument('--output',type=Path,required=True)
 a=sub.add_parser('ingest-artifact');a.add_argument('--archive',type=Path,required=True);a.add_argument('--expected-bytes',type=int,required=True);a.add_argument('--expected-sha256',required=True);a.add_argument('--manifest-sha256',required=True);a.add_argument('--part-name',required=True);a.add_argument('--output',type=Path,required=True)
 a=p.parse_args()
 if a.command=='ingest-artifact':
  print(json.dumps(ingest_artifact(a.archive,a.expected_bytes,a.expected_sha256,a.manifest_sha256,a.part_name,a.output),indent=2));return
 result=package(a.source,a.output) if a.command=='package' else verify(a.parts,a.manifest_sha256,a.output);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
