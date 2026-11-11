"""New reconstruction of private WSL research payload derivation.
Not historical tested bytes. Streams authenticated archives without extraction or
native execution; defaults and original source/evidence remain unchanged.
"""
from pathlib import Path,PurePosixPath
import argparse,copy,hashlib,io,json,posixpath,tarfile,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.read_ihp_pmos_measured_v3 import verify,require,is_linked
ENGINE='67399d2db139e9a8e7bfd118cab8acfa290bb6db003c996333e55ed682a65d25'
PSP='c044065fa80e7d4db69e79b316ed79fba4d1d2f701172e47ec10254d0d73d909'
RESEARCH='opt/icstudio/research/ihp-pmos-v3/'
FILES='opt/icstudio/files.json';RUNTIME='opt/icstudio/runtime.json'
MAX_MEMBER=2*1024**3;MAX_TOTAL=20*1024**3;MAX_ENTRIES=500000

def file_sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  while b:=f.read(1024**2):h.update(b)
 return h.hexdigest()
def encoded(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
def unlinked(path):
 p=Path(path).absolute()
 for q in (p,*p.parents):require(not is_linked(q),'Linked/reparse path')
 return p
def safe(name):
 require(isinstance(name,str) and name and not name.startswith('/') and '\\' not in name and ':' not in name and '\x00' not in name,'Unsafe archive name')
 require(all(x not in ('','.','..') for x in name.split('/')),'Unsafe archive components')
 return name

def inspect_archive(path,expected_sha):
 path=unlinked(path);require(file_sha(path)==expected_sha,'Archive digest')
 entries={};small={};total=0
 with tarfile.open(path,'r|*') as archive:
  for m in archive:
   if m.name=='.' and m.isdir():continue
   n=safe(m.name.rstrip('/') if m.isdir() else m.name)
   require(n not in entries and len(entries)<MAX_ENTRIES,'Duplicate/excess archive entries')
   require(m.isfile() or m.isdir() or m.issym() or m.islnk(),'Unsupported archive member')
   row={'bytes':m.size,'mode':m.mode,'type':'file' if m.isfile() else 'directory' if m.isdir() else 'symlink' if m.issym() else 'hardlink'}
   if m.isfile():
    require(0<=m.size<=MAX_MEMBER,'Archive member cap');total+=m.size;require(total<=MAX_TOTAL,'Archive total cap')
    h=hashlib.sha256();count=0;keep=n in (FILES,RUNTIME);data=bytearray()
    if keep:require(m.size<=32*1024**2,'Identity metadata cap')
    with archive.extractfile(m) as f:
     while b:=f.read(1024**2):
      count+=len(b);require(count<=m.size,'Archive grew');h.update(b)
      if keep:data.extend(b)
    require(count==m.size,'Truncated archive');row['sha256']=h.hexdigest()
    if keep:small[n]=bytes(data)
   elif m.issym() or m.islnk():
    require(m.linkname and not m.linkname.startswith('/') and '\\' not in m.linkname and '\x00' not in m.linkname,'Unsafe link target')
    target=posixpath.normpath(posixpath.join(posixpath.dirname(n),m.linkname)) if m.issym() else posixpath.normpath(m.linkname)
    safe(target);row['target']=target
   entries[n]=row
 for n in entries:
  for parent in PurePosixPath(n).parents:
   if str(parent)=='.':continue
   require(entries.get(str(parent),{}).get('type','directory')=='directory','Linked/non-directory archive ancestor')
 def resolve(n,seen):
  require(n in entries and n not in seen,'Missing/cyclic hardlink');r=entries[n]
  if r['type']=='hardlink':return resolve(r['target'],seen|{n})
  require(r['type']=='file','Hardlink target not file');return r['sha256']
 for n,r in entries.items():
  if r['type']=='hardlink':r['sha256']=resolve(n,set())
 require(set(small)=={FILES,RUNTIME},'Identity metadata absent')
 locks=json.loads(small[FILES]);inner=json.loads(small[RUNTIME])
 require(isinstance(locks,dict) and FILES not in locks and RUNTIME not in locks,'Invalid/self-referential lock')
 expected={n:r['sha256'] for n,r in entries.items() if n.startswith(('usr/','opt/')) and r['type'] in ('file','hardlink') and n not in (FILES,RUNTIME)}
 require(locks==expected,'Exact base lock membership/bytes')
 require(inner['files_sha256']==hashlib.sha256(small[FILES]).hexdigest(),'Inner lock identity')
 require(file_sha(path)==expected_sha,'Archive changed during inspection')
 return entries,locks,inner

def check_dependencies(entries,dependencies):
 require(len(dependencies)==8,'Exact eight dependencies required')
 for n,h in dependencies.items():
  require(n.startswith('/') and n[1:]==safe(n[1:]),'Canonical absolute dependency path')
  r=entries.get(n[1:]);require(r and r['type'] in ('file','hardlink') and r['sha256']==h,'Dependency bytes differ')

def prepare(base,expected_base_sha,evidence,output,host_contract,host_contract_sha):
 root,manifest=verify(evidence);base=unlinked(base);out=unlinked(output);host_contract=unlinked(host_contract)
 require(not out.exists(),'Fresh payload directory');require(file_sha(host_contract)==host_contract_sha,'Reviewed host contract digest')
 host=json.loads(host_contract.read_text());require(host['scope']=='REVIEWED_NEW_WSL_HOST_BASELINE' and host['new_host_baseline'] is True and host['qualified'] is False and host['approved_six_module_loading'] is True,'New research host scope')
 require(host['base_archive_sha256']==expected_base_sha,'Host/base join')
 entries,locks,inner=inspect_archive(base,expected_base_sha);check_dependencies(entries,host['dependencies'])
 require(all(locks.get(n)==h for n,h in host['base_source_provenance'].items()) and set(host['base_source_provenance'])=={'opt/icstudio/packages.tsv','opt/icstudio/simulation/source-lock.json'},'Base source provenance')
 additions={RESEARCH+p.relative_to(root).as_posix():p for p in root.rglob('*') if p.is_file()}
 additions[RESEARCH+'host-contract.json']=host_contract
 model_root=root/'measured-v3/osdi-inputs';models={p.name:p for p in model_root.glob('*.osdi')}
 require(set(models)=={'psp103.osdi','psp103_nqs.osdi','r3_cmc.osdi','mosvar.osdi','cap_cmomi.osdi','cap_cmomf.osdi'},'Six immutable models')
 require(file_sha(models['psp103.osdi'])==PSP and file_sha(root/'measured-v3/attempt-1/engine/runtime/ngspice')==ENGINE,'Experimental engine/module identity')
 report=copy.deepcopy(inner['osdi']['ihp-sg13g2']);require(report['system']=='Linux' and report['machine']=='x86_64' and report['cpu_target']=='generic' and len(report['models'])==6,'Base model ABI')
 require({x['output'] for x in report['models']}==set(models),'Model selection')
 for row in report['models']:
  va=root/'measured-v3/attempt-1/pdk/libs.tech/verilog-a';source=va/safe(row['source'])
  expected_dependencies={q.relative_to(va).as_posix():file_sha(q) for q in source.parent.iterdir() if q.is_file()}
  require(source.is_file() and row['dependencies']==expected_dependencies,'Base model source closure differs')
  n='opt/icstudio/osdi/ihp-sg13g2/'+row['output'];require(entries.get(n,{}).get('type')=='file','Base model not regular')
  additions[n]=models[row['output']];row['sha256']=file_sha(models[row['output']])
  row['compiler_provenance']=RESEARCH+'measured-v3/attempt-1/compiled-provenance' if row['output']=='psp103.osdi' else RESEARCH+'measured-v3/attempt-1/runtime-provenance'
 report.pop('compiler_sha256',None);report['compiler_scope']='Mixed exact retained research modules; per-module provenance, not a common compiler rebuild'
 additions['opt/icstudio/osdi/ihp-sg13g2/build.json']=encoded(report)
 wrapper=b'#!/bin/sh\nset -eu\nunset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH\nexport OMP_NUM_THREADS=1\nexport SPICE_SCRIPTS=/opt/icstudio/research/ihp-pmos-v3/measured-v3/attempt-1/engine/runtime\nexec /opt/icstudio/research/ihp-pmos-v3/measured-v3/attempt-1/engine/runtime/ngspice "$@"\n'
 require(entries.get('opt/icstudio/bin/ngspice',{}).get('type')=='file','Engine wrapper not regular');additions['opt/icstudio/bin/ngspice']=wrapper
 receipt={'scope':'EXPERIMENTAL_PRIVATE_WSL_PROFILE_NOT_QUALIFIED','base_archive_sha256':expected_base_sha,'host_contract_sha256':host_contract_sha,'evidence_manifest_sha256':file_sha(root/'MANIFEST.json'),'engine_sha256':ENGINE,'psp_sha256':PSP,'qualified':False,'source_reconstruction':'New post-reset implementation; historical source approval not inherited'}
 for n,value in additions.items():
  safe(n)
  for parent in PurePosixPath(n).parents:require(entries.get(str(parent),{}).get('type','directory')=='directory','Addition traverses linked ancestor')
  locks[n]=file_sha(value) if isinstance(value,Path) else hashlib.sha256(value).hexdigest()
 additions[FILES]=encoded(locks);inner['files_sha256']=hashlib.sha256(additions[FILES]).hexdigest();inner['osdi']['ihp-sg13g2']=report;inner['experimental_research']=receipt;additions[RUNTIME]=encoded(inner)
 out.mkdir(parents=True);(out/'INCOMPLETE').write_text('Not verified\n');archive_path=out/'runtime.tar.gz'
 with tarfile.open(base,'r|*') as src,tarfile.open(archive_path,'w:gz',compresslevel=1) as dest:
  for m in src:
   if m.name in additions:continue
   stream=src.extractfile(m) if m.isfile() else None
   try:dest.addfile(m,stream)
   finally:
    if stream:stream.close()
  for n,value in sorted(additions.items()):
   m=tarfile.TarInfo(n);m.mode=0o755 if n=='opt/icstudio/bin/ngspice' or n.endswith('/engine/runtime/ngspice') else 0o644;m.mtime=0
   if isinstance(value,Path):
    m.size=value.stat().st_size
    with value.open('rb') as f:dest.addfile(m,f)
   else:m.size=len(value);dest.addfile(m,io.BytesIO(value))
 ah=file_sha(archive_path);new_entries,new_locks,new_inner=inspect_archive(archive_path,ah)
 require(new_locks==locks and new_inner==inner,'Produced payload identity differs');check_dependencies(new_entries,host['dependencies'])
 require(file_sha(base)==expected_base_sha and file_sha(host_contract)==host_contract_sha,'Inputs changed');verify(root)
 outer=dict(inner,archive='runtime.tar.gz',sha256=ah,bytes=archive_path.stat().st_size)
 (out/'manifest.json').write_bytes(encoded(outer));(out/'derivation.json').write_bytes(encoded(receipt));(out/'INCOMPLETE').unlink();return receipt

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('base','evidence','output','host-contract'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--base-sha256',required=True);p.add_argument('--host-contract-sha256',required=True);a=p.parse_args();print(json.dumps(prepare(a.base,a.base_sha256,a.evidence,a.output,a.host_contract,a.host_contract_sha256),indent=2))
if __name__=='__main__':main()
