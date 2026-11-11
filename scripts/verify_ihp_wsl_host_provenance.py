"""Reconstructed readback with bounded decoder; historical original retained separately."""
from pathlib import Path
import json,subprocess,tempfile
from scripts import linux_ngspice_dependencies as d
from scripts.collect_ihp_wsl_host_provenance import binary_index,binary_match,signed_source,prove_tar_members
from scripts.prepare_ihp_wsl_research_payload import inspect_archive,check_dependencies,encoded,unlinked

def verify(proof, report_sha, base, base_sha):
 root=unlinked(proof);d.require(d.sha(root/'report.json')==report_sha,'Report binding')
 r=d.load(root/'report.json');d.require(r['engine_sha256']==d.ENGINE,'Research engine identity');d.require(r['status']=='AUTHENTICATED_NEW_HOST_BASELINE' and r['numerical_execution'] is False and r['base_archive_sha256']==base_sha,'Proof scope/base')
 for n,h in d.load(root/'files.json').items():d.require(d.sha(d.confined(root,n))==h,'Proof inventory differs')
 entries,locks,inner=inspect_archive(base,base_sha);check_dependencies(entries,r['dependencies'])
 proved={};source_names=set()
 def auth(row):
  a=row['authentication'];d.require(set(a)=={'release','index','index_path','keyring'},'Authentication keys')
  return {k:str(d.confined(root,v)) if k!='index_path' else v for k,v in a.items()}
 for row in r['binary_proofs']:
  a=auth(row);text,_=binary_index(a['release'],a['index'],a['index_path'],a['keyring'])
  deb=d.confined(root,row['archive']);signed=binary_match(text,row['package'],row['version'],deb)
  metadata=[x['package'] for x in r['rows'].values() if x['package']['binary_package']==row['package']]
  d.require(metadata and all(signed_source(signed)==(m['source_package'],m['source_version']) for m in metadata),'Signed binary/source relation')
  with tempfile.TemporaryDirectory() as temp:
   tar=Path(temp)/'package.tar'
   def cap():
    import resource
    resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024**3,2*1024**3))
   with tar.open('wb') as f:proc=subprocess.run(['/usr/bin/dpkg-deb','--fsys-tarfile',str(deb)],stdout=f,stderr=subprocess.DEVNULL,timeout=60,env=d.environment(),preexec_fn=cap)
   d.require(proc.returncode==0 and tar.stat().st_size<=2*1024**3,'Binary decode failure/cap')
   prove_tar_members(tar,row['files'])
  # Collector compares package contents; final contract additionally requires
  # those exact library hashes already present in the authenticated base.
  for n,h in row['files'].items():d.require(n not in proved,'Duplicate proved dependency');proved[n]=h
 for row in r['source_proofs']:
  a=auth(row);text,_=d.authenticated_index(a)
  members=d.source_package(d.confined(root,row['dsc']),row['package'],row['version'])
  d.source_metadata(text,row['package'],row['version'],members)
  d.require({str(p.relative_to(root)):d.sha(p) for p in members.values()}==row['members'],'Source member mapping')
  source_names.add((row['package'],row['version']))
 d.require(proved==r['dependencies'] and len(proved)==8,'Complete binary-byte closure')
 expected={(x['package']['source_package'],x['package']['source_version']) for x in r['rows'].values()}
 d.require(source_names==expected,'Full dependency source coverage including system libraries')
 required=['opt/icstudio/packages.tsv','opt/icstudio/simulation/source-lock.json']
 d.require(all(n in locks for n in required),'Base source metadata absent')
 return {'scope':'REVIEWED_NEW_WSL_HOST_BASELINE','base_archive_sha256':base_sha,'approved_six_module_loading':True,
  'dependencies':proved,'base_source_provenance':{n:locks[n] for n in required},
  'collector_report_sha256':report_sha,'collector_inventory_sha256':d.sha(root/'files.json'),
  'image':r['image'],'build_inputs_sha256':r['build_inputs_sha256'],'new_host_baseline':True,'qualified':False}
