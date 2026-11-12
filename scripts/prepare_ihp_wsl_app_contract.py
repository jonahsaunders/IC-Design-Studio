"""New post-reset source-only admission contract. Never grants native permission."""
from pathlib import Path
import argparse, hashlib, json, os
from scripts.read_ihp_pmos_measured_v3 import require, is_linked, verify

ROUTES=('nominal','width-5um','multiplicity-2','drain-source-swapped')
SELECTION=tuple((r,i) for r in ROUTES for i in range(5))
PAYLOAD=('manifest.json','runtime.tar.gz','derivation.json')
def sha(p):
 with Path(p).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def regular(p):
 p=Path(p).absolute()
 require(not any(is_linked(q) for q in (p,*p.parents)), 'Linked input')
 require(p.is_file(),'Missing regular input')
 return p
def load(p): return json.loads(regular(p).read_bytes())
def source_identity(root):
 root=Path(root).absolute(); result={}
 for folder in ('icstudio','scripts'):
  for p in sorted((root/folder).rglob('*')):
   if '__pycache__' in p.parts: continue
   require(not is_linked(p),'Linked source')
   if p.is_file() and (folder=='icstudio' or p.suffix=='.py'):
    result[p.relative_to(root).as_posix()]=sha(regular(p))
 require(bool(result),'Empty source identity')
 return result
def payload_identity(root):
 root=Path(root).absolute()
 require(not any(is_linked(q) for q in (root,*root.parents)), 'Linked payload root')
 require(root.is_dir() and {p.name for p in root.iterdir()}==set(PAYLOAD),'Exact three-file payload required; no backend override')
 hashes={n:sha(regular(root/n)) for n in PAYLOAD};m=load(root/'manifest.json')
 require(m['archive']=='runtime.tar.gz' and type(m['bytes']) is int and m['bytes']>0,'Archive declaration')
 require((root/'runtime.tar.gz').stat().st_size==m['bytes'] and hashes['runtime.tar.gz']==m['sha256'],'Archive identity')
 require(load(root/'derivation.json')==m['experimental_research'],'Payload derivation differs')
 return hashes

def prepare(source,prepared,evidence,projects):
 # Imported lazily: the independently reconstructed build-only gate must exist.
 from scripts.check_ihp_wsl_prepared import check
 before=source_identity(source);checked=check(prepared)
 require(checked['status']=='CLEAN_BUILD_PREPARATION_ONLY' and checked['native_authorized'] is False,'Prepared scope')
 evidence,_=verify(evidence);prepared=Path(prepared)
 payload=payload_identity(prepared/'experimental-payload');host=load(prepared/'host-contract.json')
 require(host['scope']=='REVIEWED_NEW_WSL_HOST_BASELINE' and host['qualified'] is False,'Host scope')
 run=load(evidence/'measured-v3/attempt-1/run.json')
 require(len(run['runs'])==20 and {(r['route'],r['gate_index']) for r in run['runs']}==set(SELECTION),'Exact historical selection')
 require(all(r['deadline_seconds']==90 for r in run['runs']),'Original deadline')
 projects=Path(projects);project_record=load(projects/'projects.json')
 require(project_record['qualified'] is False and project_record['deadline_seconds']==90 and project_record['pre_native_review_required'] is True,'Source project scope')
 require(len(project_record['cases'])==20 and {x['case'] for x in project_record['cases']}=={f'{r}-{i}' for r,i in SELECTION},'Source project selection')
 project_hashes={}
 for row in project_record['cases']:
  require(row['project']==row['case']+'.icproj','Project filename')
  require(sha(regular(projects/row['project']))==row['sha256'],'Source project bytes')
  project_hashes[row['case']]=row['sha256']
 decks={f'{r}-{i}':sha(regular(evidence/f'measured-v3/attempt-1/runs/{r}-{i}/input.cir')) for r,i in SELECTION}
 require(before==source_identity(source),'Source changed during preparation')
 return dict(schema=1,scope='SOURCE_ONLY_RECONSTRUCTED_WINDOWS_WSL_APP_DRAFT',review_state='PENDING_INDEPENDENT_WINDOWS_ADAPTER_REVIEW',native_authorized=False,host_acceptance_pending=True,approved_managed_six_module_loading=False,qualified=False,installed_acceptance=False,source_reconstruction='New implementation; not exact historical restoration or historical approval',source_files_sha256=before,prepared_bindings=checked['bindings'],payload_files_sha256=payload,payload_archive_sha256=payload['runtime.tar.gz'],payload_root=str((prepared/'experimental-payload').absolute()),private_state_root=None,runtime_identity=None,host_dependencies=host['dependencies'],runtime_full_identity=None,managed_modules=[[x['output'],x['sha256']] for x in load(prepared/'experimental-payload/manifest.json')['osdi']['ihp-sg13g2']['models']],project_files_sha256=project_hashes,projects_manifest_sha256=sha(projects/'projects.json'),host_contract_sha256=sha(prepared/'host-contract.json'),evidence_manifest_sha256=sha(evidence/'MANIFEST.json'),selection=[list(x) for x in SELECTION],historical_decks_sha256=decks,job_timeout_seconds=90,max_jobs=20,retries=0,refinement=False,solver='default Sparse',native_adapter_ready=False)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('source','prepared','evidence','projects','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();result=prepare(a.source,a.prepared,a.evidence,a.projects)
 with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
if __name__=='__main__':main()
