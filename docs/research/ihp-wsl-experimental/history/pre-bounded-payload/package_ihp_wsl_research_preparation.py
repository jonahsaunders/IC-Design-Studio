"""Split preparation delivery into small metadata, bounded full proof, and payload.
No omission is silent. Full proof/log bytes are losslessly chunked, not extracted
or executed. The experimental runtime archive is a separate artifact.
"""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,zipfile,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.prepare_ihp_wsl_research_payload import unlinked,encoded,file_sha
from scripts.read_ihp_pmos_measured_v3 import require,is_linked
PART_LIMIT=256*1024**2
CHUNK_LIMIT=16*1024**2
META_LIMIT=16*1024**2

def package(source,output,part_limit=PART_LIMIT,chunk_limit=CHUNK_LIMIT):
 source=unlinked(source);out=unlinked(output);require(not out.exists() and not out.is_relative_to(source),'Fresh separate delivery directory')
 require(1024<=chunk_limit<part_limit<=PART_LIMIT,'Delivery bounds')
 selected={};excluded={}
 def classification(n):
  if n.startswith('experimental-payload/'):return 'payload'
  if n.startswith('context/') or n in ('filesystem.tar','base-runtime.tar.gz'):return 'scratch'
  if n.startswith('host-proof/') or '/' not in n and Path(n).suffix in ('.json','.log'):return 'proof'
  raise ValueError('Unknown preparation path; refusing omission: '+n)
 # Retain entire host proof plus every top-level builder receipt/log. Exclude
 # only separately delivered payload and explicitly named bulky build scratch.
 for p in source.rglob('*'):
  require(not is_linked(p),'Linked preparation evidence')
  if not p.is_file():continue
  n=p.relative_to(source).as_posix()
  kind=classification(n)
  if kind=='proof':selected[n]=p
  elif kind=='scratch':excluded[n]={'bytes':p.stat().st_size,'sha256':file_sha(p),'reason':'Explicit omitted build scratch, not executable replay'}
 require(bool(selected),'No preparation receipts to deliver')
 require(len(selected)<=10000 and sum(p.stat().st_size for p in selected.values())<=3*1024**3,'Full proof delivery cap exceeded; no omission permitted')
 out.mkdir(parents=True);meta=out/'metadata';meta.mkdir();proof=out/'proof-parts';proof.mkdir()
 manifest={'schema':1,'scope':'BUILD_PREPARATION_DELIVERY_NO_NATIVE_ACCEPTANCE','files':{},'parts':{},
  'separate_payload':{},'excluded_build_scratch':['context/','filesystem.tar','base-runtime.tar.gz'],
  'excluded_scratch_files':excluded,'metadata_previews':{}}
 z=None;part=None;part_index=0;budget=0;chunk_index=0
 def finish():
  nonlocal z
  if z is not None:
   z.close();require(part.stat().st_size<=part_limit,'Part size cap')
   manifest['parts'][part.name]={'bytes':part.stat().st_size,'sha256':file_sha(part)};z=None
 try:
  for n,p in sorted(selected.items()):
   record={'bytes':p.stat().st_size,'sha256':file_sha(p),'chunks':[]};manifest['files'][n]=record
   with p.open('rb') as stream:
    offset=0
    while data:=stream.read(chunk_limit):
     # Account conservatively for ZIP headers/central directory; max entries
     # per part is bounded by this nonzero fixed overhead even for tiny files.
     if z is None or budget+len(data)+2048>part_limit:
      finish();part_index+=1;require(part_index<=16,'Proof part count exceeded; retain failure');part=proof/f'host-proof-{part_index:04d}.zip';z=zipfile.ZipFile(part,'x',compression=zipfile.ZIP_STORED);budget=0
     member=f'chunk-{chunk_index:08d}';chunk_index+=1;budget+=len(data)+256
     z.writestr(member,data);record['chunks'].append({'part':part.name,'member':member,'offset':offset,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()});offset+=len(data)
   require(offset==record['bytes'] and file_sha(p)==record['sha256'],'Source changed during packaging')
  finish()
 finally:
  if z is not None:z.close()
 # Small complete metadata where practical; previews are explicitly labelled
 # and every original remains losslessly available in proof parts above.
 metadata_names=[n for n in selected if n.endswith('.json') and ('/lists/' not in n)]
 used=0
 for n in metadata_names:
  p=selected[n];size=p.stat().st_size
  if used+size<=META_LIMIT//2 and size<=2*1024**2:
   target=meta/'receipts'/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes());used+=size
   manifest['metadata_previews'][n]='complete copy'
  else:manifest['metadata_previews'][n]='full bytes in proof parts; metadata copy omitted by16MiB cap'
 payload=source/'experimental-payload'
 if payload.exists():
  for p in payload.rglob('*'):
   require(not is_linked(p),'Linked payload')
   if p.is_file():manifest['separate_payload'][p.relative_to(payload).as_posix()]={'bytes':p.stat().st_size,'sha256':file_sha(p)}
 manifest['parts_count']=part_index
 manifest_bytes=encoded(manifest);require(used+len(manifest_bytes)<=META_LIMIT,'Metadata artifact cap')
 (meta/'DELIVERY.json').write_bytes(manifest_bytes);(proof/'DELIVERY.json').write_bytes(manifest_bytes)
 # Independent readback of every chunk, offset, file SHA/size and archive CRC.
 for part_name,info in manifest['parts'].items():
  p=proof/part_name;require(file_sha(p)==info['sha256'] and p.stat().st_size==info['bytes'],'Part changed')
  with zipfile.ZipFile(p) as archive:require(archive.testzip() is None,'Part CRC failure')
 for n,r in manifest['files'].items():
  h=hashlib.sha256();offset=0
  for ref in r['chunks']:
   with zipfile.ZipFile(proof/ref['part']) as archive:data=archive.read(ref['member'])
   require(ref['offset']==offset and len(data)==ref['bytes'] and hashlib.sha256(data).hexdigest()==ref['sha256'],'Chunk readback differs')
   h.update(data);offset+=len(data)
  require(offset==r['bytes'] and h.hexdigest()==r['sha256'],'Full proof reconstruction differs')
 current={}
 for p in source.rglob('*'):
  require(not is_linked(p),'Preparation gained a linked path')
  if p.is_file():
   n=p.relative_to(source).as_posix()
   if classification(n)=='proof':current[n]=p
 require(set(current)==set(selected),'Preparation inventory changed during delivery')
 require(all(file_sha(p)==manifest['files'][n]['sha256'] and p.stat().st_size==manifest['files'][n]['bytes'] for n,p in current.items()),'Preparation bytes changed during delivery')
 return manifest

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(package(a.source,a.output),indent=2))
if __name__=='__main__':main()
