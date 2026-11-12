"""New post-reset build-only reconstruction. No native numerical execution.
Requires separately reviewed new source policy. Historical approvals do not apply.
"""
from pathlib import Path
import argparse,json,os,re,shutil,subprocess,sys,time,uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.build_digital_runtime import stage_context,cache_identity,pack_filesystem,context_identity
from scripts.prepare_ihp_wsl_research_payload import file_sha,unlinked,encoded,prepare
from scripts.read_ihp_pmos_measured_v3 import verify,require
from scripts.verify_ihp_wsl_host_provenance import verify as verify_host
ROOT=Path(__file__).resolve().parents[1]

def collector_user(output):
 """Bind proof ownership to the ordinary Linux caller, never container root."""
 require(sys.platform=='linux','Collector requires an ordinary native Linux host')
 uid,gid=os.getuid(),os.getgid()
 require(type(uid) is int and type(gid) is int and uid>0 and gid>0,'Non-root numeric host UID:GID required')
 require((uid,gid)==(os.geteuid(),os.getegid()),'Real/effective collector identity differs')
 require(Path(output).stat().st_uid==uid,'Build output must belong to the host caller')
 return str(uid)+':'+str(gid)


def cleanup_collector(name,image_id):
 record={'name':name,'expected_image_id':image_id,'status':'pending'}
 try:
  found=subprocess.run(['docker','container','inspect',name],capture_output=True,text=True,timeout=10)
  record.update(inspect_returncode=found.returncode,inspect_stderr=found.stderr)
  if found.returncode:
   require('No such object' in found.stderr or 'No such container' in found.stderr,'Cannot establish collector absence');record['status']='absent';return record
  rows=json.loads(found.stdout);require(len(rows)==1 and rows[0]['Name']=='/'+name and rows[0]['Image']==image_id,'Collector ownership/image mismatch')
  removed=subprocess.run(['docker','rm','--force',name],capture_output=True,text=True,timeout=30)
  record.update(remove_returncode=removed.returncode,remove_stdout=removed.stdout,remove_stderr=removed.stderr)
  require(removed.returncode==0,'Owned collector removal failed');record['status']='removed';return record
 except BaseException as exc:record.update(status='failed',error=repr(exc));return record

def source_guard(policy_path,expected_sha):
 require(file_sha(policy_path)==expected_sha,'Explicit new policy digest')
 policy=json.loads(Path(policy_path).read_text())
 require(policy['review_state']=='APPROVED_FOR_BUILD_ONLY' and policy['scope']=='REVIEWED_SAME_RUN_WSL_RESEARCH_BUILD_NO_PMOS','Build-only reviewed scope')
 require(policy.get('reconstruction_version')==2,'Historical policy cannot authorize reconstructed code')
 require(cache_identity()['sha256']==policy['build_context_sha256'],'Build context differs')
 required={'scripts/build_digital_runtime.py','scripts/build_ihp_wsl_research_base.py','scripts/collect_ihp_wsl_host_provenance.py','scripts/verify_ihp_wsl_host_provenance.py','scripts/prepare_ihp_wsl_research_payload.py','scripts/linux_ngspice_dependencies.py','scripts/read_ihp_pmos_measured_v3.py','scripts/materialize_ihp_pmos_measured_v3.py','scripts/package_ihp_wsl_research_preparation.py','scripts/transport_ihp_wsl_payload.py'}
 require(required<=set(policy['research_source_bindings']),'Incomplete source policy')
 for n,h in policy['research_source_bindings'].items():
  require(not Path(n).is_absolute() and '..' not in Path(n).parts,'Unsafe source binding');require(file_sha(unlinked(ROOT/n))==h,'Research source changed: '+n)
 return policy

def build(evidence,output,policy_path,policy_sha):
 out=unlinked(output);require(not out.exists(),'Fresh output');out.mkdir(parents=True)
 commands=[];failure=None;container=None;image_id=None;collector_attempted=False
 tag='icstudio-ihp-wsl-research-'+uuid.uuid4().hex[:12];collector_name=tag+'-collector'
 def run(argv,label,timeout=300,stdout_path=None,capture=False):
  row={'argv':argv,'timeout_seconds':timeout,'label':label};start=time.monotonic();log=stdout_path or out/(label+'.log')
  try:
   with log.open('xb') as f, (out/(label+'.stderr.log')).open('xb') as err:
    result=subprocess.run(argv,stdout=f,stderr=err,timeout=timeout)
   row['returncode']=result.returncode;require(result.returncode==0,'Command failed: '+label)
   if capture:require(log.stat().st_size<=32*1024**2,'Command metadata cap');return log.read_text().strip()
  except subprocess.TimeoutExpired:row['timed_out']=True;raise
  finally:row['seconds']=time.monotonic()-start;commands.append(row);(out/'commands.json').write_bytes(encoded(commands))
 try:
  policy=source_guard(policy_path,policy_sha);evidence,_=verify(evidence)
  user=collector_user(out)
  require(shutil.disk_usage(out).free>=30*1024**3,'Require30GiB free before build');require(policy['official_base']=='ubuntu:24.04','Official base only')
  run(['docker','pull','--platform','linux/amd64','ubuntu:24.04'],'pull-official-base')
  info=json.loads(run(['docker','image','inspect','ubuntu:24.04'],'official-image-inspect',capture=True))
  require(len(info)==1 and info[0]['Os']=='linux' and info[0]['Architecture']=='amd64','Base architecture')
  digests=[x for x in info[0]['RepoDigests'] if re.fullmatch(r'ubuntu@sha256:[0-9a-f]{64}',x)];require(len(digests)==1,'Official exact digest');base_digest=digests[0]
  context=out/'context';stage_context(context);require(context_identity(context)['sha256']==policy['build_context_sha256'],'Actual staged context differs')
  dockerfile=context/'Dockerfile';text=dockerfile.read_text();require(text.count('FROM ubuntu:24.04')==1,'Unexpected default Dockerfile');dockerfile.write_text(text.replace('FROM ubuntu:24.04','FROM '+base_digest))
  (out/'build-inputs.json').write_bytes(encoded({'reviewed_default_context':cache_identity(),'resolved_official_base':base_digest,'derived_Dockerfile_sha256':file_sha(dockerfile),'research_sources':policy['research_source_bindings'],'collector_host_user':user}))
  run(['docker','build','--platform','linux/amd64','--tag',tag,str(context)],'build-private-image',3600)
  derived=json.loads(run(['docker','image','inspect',tag],'private-image-inspect',capture=True));require(len(derived)==1 and derived[0]['Os']=='linux' and derived[0]['Architecture']=='amd64','Private image architecture');image_id=derived[0]['Id']
  image={'base_repo_digest':base_digest,'base_image_id':info[0]['Id'],'derived_image_id':image_id,'official_inspect_sha256':file_sha(out/'official-image-inspect.log'),'derived_inspect_sha256':file_sha(out/'private-image-inspect.log')}
  (out/'image-receipt.json').write_bytes(encoded(image));image_sha=file_sha(out/'image-receipt.json');inputs_sha=file_sha(out/'build-inputs.json')
  container=run(['docker','create','--platform','linux/amd64',image_id],'create-export-container',capture=True).splitlines()[-1]
  exported=json.loads(run(['docker','container','inspect',container],'export-container-inspect',capture=True));require(len(exported)==1 and exported[0]['Image']==image_id,'Export image mismatch')
  run(['docker','export',container],'export-private-image',600,out/'filesystem.tar')
  pack_filesystem(out/'filesystem.tar',out/'base-runtime.tar.gz');base_sha=file_sha(out/'base-runtime.tar.gz')
  proof=out/'host-proof';proof.mkdir();engine=evidence/'measured-v3/attempt-1/engine/runtime'
  args=['docker','run','--user',user,'--name',collector_name,'--platform','linux/amd64','--rm','--env','PYTHONDONTWRITEBYTECODE=1',
   '--mount','type=bind,src='+str(ROOT)+',dst=/research-tools,readonly',
   '--mount','type=bind,src='+str(engine)+',dst=/research-engine,readonly',
   '--mount','type=bind,src='+str(out)+',dst=/research-output',image_id,
   '/usr/bin/python3','/research-tools/scripts/collect_ihp_wsl_host_provenance.py','--engine','/research-engine/ngspice',
   '--output','/research-output/host-proof/receipt','--image','/research-output/image-receipt.json',
   '--base-archive-sha256',base_sha,'--build-inputs-sha256',inputs_sha]
  collector_attempted=True;run(args,'collect-signed-host-provenance',1800)
  report=proof/'receipt/report.json';r=json.loads(report.read_text())
  require(file_sha(out/'image-receipt.json')==image_sha and file_sha(out/'build-inputs.json')==inputs_sha,'Build receipts changed')
  require(r['image']==image and r['build_inputs_sha256']==inputs_sha and r['base_archive_sha256']==base_sha,'Collector/build join differs')
  host=verify_host(proof/'receipt',file_sha(report),out/'base-runtime.tar.gz',base_sha)
  (out/'host-contract.json').write_bytes(encoded(host));prepare(out/'base-runtime.tar.gz',base_sha,evidence,out/'experimental-payload',out/'host-contract.json',file_sha(out/'host-contract.json'))
  source_guard(policy_path,policy_sha);verify(evidence)
  (out/'result.json').write_bytes(encoded({'status':'PREPARED_PENDING_WINDOWS_NATIVE_REVIEW','qualified':False,'pmos_executed':False,'policy_sha256':policy_sha,'image':image,'base_archive_sha256':base_sha,'host_contract_sha256':file_sha(out/'host-contract.json'),'payload_manifest_sha256':file_sha(out/'experimental-payload/manifest.json')}))
 except BaseException as exc:failure=repr(exc);raise
 finally:
  cleanup={'collector':cleanup_collector(collector_name,image_id) if collector_attempted else {'status':'not_started'}}
  if container:
   try:
    removed=subprocess.run(['docker','rm',container],capture_output=True,text=True,timeout=30)
    cleanup['export_container']={'id':container,'returncode':removed.returncode,'stdout':removed.stdout,'stderr':removed.stderr,'status':'removed' if removed.returncode==0 else 'failed'}
   except BaseException as exc:cleanup['export_container']={'id':container,'status':'failed','error':repr(exc)}
  bad=any(x['status']=='failed' for x in cleanup.values())
  (out/'completion.json').write_bytes(encoded({'failure':failure,'cleanup_failed':bad,'cleanup':cleanup,'source_policy_sha256':policy_sha,'pmos_executed':False}))
  if failure is None:require(not bad,'Owned container cleanup failed')

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('evidence','output','policy'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--policy-sha256',required=True);a=p.parse_args();build(a.evidence,a.output,a.policy,a.policy_sha256)
if __name__=='__main__':main()
