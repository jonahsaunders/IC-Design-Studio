"""One research batch only after exact Windows/private-WSL review and authorization."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.prepare_ihp_wsl_app_contract import load,sha,regular,source_identity,payload_identity,SELECTION
from scripts.read_ihp_pmos_measured_v3 import require

def preflight(contract,authorization,source,prepared):
 c=load(contract);a=load(authorization)
 require(sys.platform=='win32','Actual Windows Studio required')
 require(c['review_state']=='REVIEWED_FOR_EXPLICIT_NATIVE_AUTHORIZATION' and c['host_acceptance_pending'] is False and c['approved_managed_six_module_loading'] is True,'Host and managed-six-module review required')
 require(c['qualified'] is False and c['installed_acceptance'] is False,'Research-only scope')
 require(a=={'status':'AUTHORIZED_REVIEWED_WINDOWS_WSL_RESEARCH','contract_sha256':sha(contract),'runner_sha256':sha(__file__)},'Separate exact native authorization required')
 require(c['max_jobs']==20 and c['job_timeout_seconds']==90 and c['retries']==0 and c['refinement'] is False and c['solver']=='default Sparse','Original production limits')
 require(c['selection']==[list(x) for x in SELECTION],'Complete fixed selection')
 require(source_identity(source)==c['source_files_sha256'],'Source identity differs')
 from scripts.check_ihp_wsl_prepared import check
 checked=check(prepared)
 require(checked['bindings']==c['prepared_bindings'],'Prepared input changed')
 require(payload_identity(Path(prepared)/'experimental-payload')==c['payload_files_sha256'],'Payload changed')
 require(sha(Path(prepared)/'host-contract.json')==c['host_contract_sha256'],'Host changed')
 return c

def run(contract_path,authorization,source,prepared,projects_root,output,evidence_root):
 """One explicitly authorized batch, then separate read-only audit; never retry."""
 import json
 from scripts.audit_ihp_wsl_research_app import audit_native,confined
 out=Path(output);receipt=out.with_name(out.name+'.launch.json');audit_path=out.with_name(out.name+'.audit.json')
 require(not out.exists() and not receipt.exists() and not audit_path.exists() and not out.with_name(out.name+'.dispatch-failure.json').exists(),'Fresh attempt, receipt and audit output required')
 require(out.parent.is_dir(),'Existing attempt parent required')
 state=dict(status='PREFLIGHT_PENDING',launch_requested=False,qualified=False,installed_acceptance=False)
 try:
  contract=preflight(contract_path,authorization,source,prepared)
  require(contract.get('native_adapter_ready') is True,'Independent adapter review required')
  projects_root=Path(projects_root);manifest=load(projects_root/'projects.json')
  require(sha(projects_root/'projects.json')==contract['projects_manifest_sha256'],'Reviewed project manifest differs')
  rows=manifest['cases'];require(len(rows)==20 and {r['case'] for r in rows}=={f'{route}-{i}' for route,i in SELECTION},'Fixed twenty project cases')
  projects={r['case']:{'path':str(confined(projects_root,r['project'])),'sha256':r['sha256']} for r in rows}
  studio_adapter(contract_path,authorization,source,prepared,projects,out,state)
  require(state.get('status')=='EXECUTED_PENDING_INDEPENDENT_NATIVE_AUDIT','Native attempt not complete; no audit promotion')
  result=audit_native(receipt,contract_path,evidence_root,projects_root)
  with audit_path.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
  return result
 except BaseException as exc:
  # The adapter owns its existing final receipt. Never overwrite an uncertain
  # native outcome with a later dispatcher/auditor failure.
  if not receipt.exists():
   state.update(error=repr(exc),status='NATIVE_OUTCOME_UNKNOWN' if state.get('launch_requested') else 'PREFLIGHT_OR_APP_PREPARATION_FAILED_NO_NATIVE_LAUNCH_RECORDED')
   with receipt.open('x') as f:json.dump(state,f,indent=2);f.write('\n')
  failure=out.with_name(out.name+'.dispatch-failure.json')
  with failure.open('x') as f:json.dump({'error':repr(exc),'launch_requested':state.get('launch_requested',False),'qualified':False,'installed_acceptance':False},f,indent=2);f.write('\n')
  raise

# Adapter is reachable only through exact independent-review and native
# authorization checks. Source preparation grants neither.
def studio_adapter(contract_path, authorization, source, prepared, projects, output, state):
 contract=preflight(contract_path,authorization,source,prepared)
 require(contract.get("native_adapter_ready") is True,"Independent adapter review required")
 state.update(contract_sha256=sha(contract_path),runner_sha256=sha(__file__),authorization=load(authorization))
 import time
 from unittest.mock import patch
 from PySide6.QtCore import QSettings,QStandardPaths,QTimer
 from PySide6.QtWidgets import QApplication,QMessageBox
 from PySide6.QtTest import QTest
 from icstudio.gui import Studio
 from icstudio.model import load_project,example,clone,digest
 from icstudio.osdi import needs_managed_runtime
 from icstudio.mim_desktop_probe import selected_file
 from icstudio import digital_runtime
 require(sys.platform=='win32','Actual Windows Studio required')
 require(QApplication.instance() is None,'Fresh dedicated application process required')
 out=Path(output);require(not out.exists(),'Fresh output required');out.mkdir(parents=True)
 require(set(projects)=={f'{r}-{i}' for r,i in SELECTION},'Exact twenty projects')
 require({k:v['sha256'] for k,v in projects.items()}==contract['project_files_sha256'],'Reviewed project bindings')
 require(str(digital_runtime.payload_root())==contract['payload_root'] and str(digital_runtime.state_root())==contract['private_state_root'],'Dedicated prepared payload/state required')
 QStandardPaths.setTestModeEnabled(True);QSettings.setDefaultFormat(QSettings.IniFormat)
 QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
 app=QApplication([]);app.setApplicationName('ICStudio-WSL-Research-'+out.name)
 w=None;owned=None;state.update(launch_requested=False,runs=[],cleanup='pending',source_before=source_identity(source))
 def write():
  import json
  (out/'progress.json').write_text(json.dumps(state,indent=2)+'\n')
 def modal_guard():
  dialog=app.activeModalWidget()
  if dialog is not None:
   state['unexpected_modal']=type(dialog).__name__;dialog.reject()
 timer=QTimer();timer.setInterval(30000);timer.timeout.connect(modal_guard);timer.start()
 try:
  w=Studio(recover=False);w.jobs_dir=out/'jobs';w.run_manager.limit=1
  w.settings.setValue('engine/osdi','');w.settings.setValue('engine/ngspice','')
  runtime=digital_runtime.status();require(runtime.get('state')=='ready','Private managed WSL already prepared required')
  runtime=runtime['runtime'];require(runtime['kind']=='wsl' and runtime['sha256']==contract['payload_archive_sha256'],'Exact managed WSL payload')
  require(runtime==contract['runtime_identity'],'Exact private WSL identity')
  state['runtime_identity']=runtime
  state['runtime_full_before']=digital_runtime.identity(runtime,full=True)
  require(state['runtime_full_before']==contract['runtime_full_identity'],'Reviewed runtime lock identity')
  host=load(Path(prepared)/'host-contract.json')
  dependencies=host['dependencies']
  require(len(dependencies)==8 and all(n.startswith('/') for n in dependencies),'Exact absolute dependency set')
  from scripts.audit_ihp_wsl_research_app import confined
  state['dependencies_before']={n:sha(confined(Path(runtime['root']),n[1:])) for n in dependencies}
  require(state['dependencies_before']==dependencies,'Actual host dependencies changed')
  state['actual_dependency_closure_before']=actual_dependency_closure(runtime,dependencies)
  for route,index in SELECTION:
   key=f'{route}-{index}';entry=projects[key];path=Path(entry['path'])
   require(sha(path)==entry['sha256'],'Project input changed')
   project=load_project(path);require(needs_managed_runtime(project),'Managed IHP project required')
   require(not project.get('simulation_runtime',{}).get('osdi'),'Custom OSDI must be absent')
   saved=out/(key+'.icproj');save_reopen_project(w,project,saved)
   settings=w.project['analysis'];prepared_job=w.prepare_simulation(settings,'ngspice');s=prepared_job['settings']
   require(s['timeout']==90 and s['managed_osdi']=='ihp-sg13g2' and s['physical_runtime']==runtime and s.get('dc_startup',False) is False,'Production settings differ')
   require('unexpected_modal' not in state,'Unexpected modal before launch')
   state['launch_requested']=True;state['current_case']=key;write()
   owned=w.start_job(settings,'ngspice');start=time.monotonic()
   while owned['state'] in ('Queued','Running','Stopping'):
    require(time.monotonic()-start<900,'Outer transfer deadline; no retry')
    require('unexpected_modal' not in state,'Unexpected modal')
    QTest.qWait(20)
   require(owned['state']=='Complete' and 'reused_from' not in owned.get('result',{}),'Fresh completed managed job required')
   state['runs'].append({'route':route,'gate_index':index,'job_directory':str(owned['path']),'saved_project':str(saved),'saved_project_sha256':sha(saved),'state':owned['state']})
   owned=None;write()
  state['status']='EXECUTED_PENDING_INDEPENDENT_NATIVE_AUDIT'
 finally:
  state['cleanup_errors']=[]
  try:
   if w is not None and owned is not None and owned['state'] in ('Queued','Running','Stopping'):
    w.run_manager.cancel([owned]);deadline=time.monotonic()+10
    while owned.get('process') is not None and time.monotonic()<deadline:QTest.qWait(20)
    state['cleanup']='owned_process_still_present' if owned.get('process') is not None else 'owned_process_stopped'
    if owned.get('process') is not None:state['cleanup_errors'].append('Owned native process not confirmed stopped')
   else:state['cleanup']='no_owned_active_row'
  except BaseException as exc:state['cleanup_errors'].append('cancel: '+repr(exc))
  try:
   timer.stop()
   if w is not None:
    with patch.object(w,'maybe_save',return_value=True):w.close()
  except BaseException as exc:state['cleanup_errors'].append('close: '+repr(exc))
  try:app.quit()
  except BaseException as exc:state['cleanup_errors'].append('quit: '+repr(exc))
  try:
   state['source_after']=source_identity(source);state['source_unchanged']=state['source_before']==state['source_after']
   preflight(contract_path,authorization,source,prepared)
   if 'runtime_identity' in state:
    state['runtime_full_after']=digital_runtime.identity(state['runtime_identity'],full=True)
    require(state['runtime_full_after']==state['runtime_full_before'],'Runtime changed during execution')
    state['dependencies_after']={n:sha(confined(Path(state['runtime_identity']['root']),n[1:])) for n in dependencies}
    require(state['dependencies_after']==state['dependencies_before'],'Dependencies changed during execution')
    state['actual_dependency_closure_after']=actual_dependency_closure(state['runtime_identity'],dependencies)
    require({n:r['libraries'] for n,r in state['actual_dependency_closure_after']['rows'].items()}=={n:r['libraries'] for n,r in state['actual_dependency_closure_before']['rows'].items()},'Actual loaded closure changed')
  except BaseException as exc:state['cleanup_errors'].append('postcheck: '+repr(exc))
  if state.get('launch_requested') and (state.get('status')!='EXECUTED_PENDING_INDEPENDENT_NATIVE_AUDIT' or state['cleanup_errors'] or not state.get('source_unchanged')):state['status']='NATIVE_OUTCOME_UNKNOWN'
  write()
 return state

_studio_adapter_implementation=studio_adapter
def studio_adapter(contract_path,authorization,source,prepared,projects,output,state):
 """Retain preflight/cleanup failures even before Qt or native job creation."""
 import json
 output=Path(output);receipt=output.with_name(output.name+'.launch.json')
 require(not output.exists() and not receipt.exists(),'Fresh attempt and receipt required')
 require(output.parent.is_dir(),'Existing attempt parent required')
 state.update(status='PREFLIGHT_PENDING',launch_requested=False,qualified=False,installed_acceptance=False)
 with receipt.open('x') as f:json.dump(state,f,indent=2)
 try:
  return _studio_adapter_implementation(contract_path,authorization,source,prepared,projects,output,state)
 except BaseException as exc:
  state['error']=repr(exc)
  state['status']='NATIVE_OUTCOME_UNKNOWN' if state.get('launch_requested') else 'PREFLIGHT_OR_APP_PREPARATION_FAILED_NO_NATIVE_LAUNCH_RECORDED'
  raise
 finally:
  try:
   if output.is_dir():
    state['files']={str(p.relative_to(output)).replace('\\','/'):sha(regular(p)) for p in output.rglob('*') if p.is_file()}
  except BaseException as exc:state['inventory_error']=repr(exc)
  receipt.write_text(json.dumps(state,indent=2)+'\n')

def actual_dependency_closure(runtime,expected):
 """Actual engine loader closure plus static module-to-engine symbol joins."""
 import json,inspect
 from icstudio import digital_runtime
 from scripts.ihp_wsl_elf_symbols import elf_symbols,resolve_symbols
 code='import struct\nfrom pathlib import Path\n'+inspect.getsource(elf_symbols)+'\n'+inspect.getsource(resolve_symbols)+r'''
import os,re,json,subprocess,hashlib,pathlib
engine='/opt/icstudio/research/ihp-pmos-v3/measured-v3/attempt-1/engine/runtime/ngspice'
models=['/opt/icstudio/osdi/ihp-sg13g2/'+n for n in ('psp103.osdi','psp103_nqs.osdi','r3_cmc.osdi','mosvar.osdi','cap_cmomi.osdi','cap_cmomf.osdi')]
p=subprocess.run(['/usr/bin/ldd',engine],capture_output=True,text=True,timeout=30,env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','HOME':'/tmp'})
assert p.returncode==0 and 'not found' not in p.stdout+p.stderr
closure={}
for line in p.stdout.splitlines():
 words=line.split()
 if not words or words[0].startswith('linux-vdso.so'):continue
 candidates=[x for x in words if x.startswith('/')];assert len(candidates)==1,repr(line)
 path=pathlib.Path(candidates[0]).resolve(strict=True)
 with path.open('rb') as stream:closure[str(path)]=hashlib.file_digest(stream,'sha256').hexdigest()
assert len(closure)==8
scope=elf_symbols(engine)['exports'].copy()
for path in closure:
 for name,kind in elf_symbols(path)['exports'].items():scope.setdefault(name,kind)
rows={engine:{'libraries':closure,'resolution':'ENGINE_LOADER_REPORTED','stdout':p.stdout,'stderr':p.stderr}}
for name in models:
 symbols=elf_symbols(name)
 assert symbols['needed']==[], 'Unreviewed new module DT_NEEDED dependency'
 resolution=resolve_symbols(symbols,scope)
 rows[name]={'libraries':closure,'resolution':'NO_DT_NEEDED_USES_AUTHENTICATED_ENGINE_SCOPE','symbol_resolution':resolution}
print(json.dumps({'rows':rows,'dependencies':closure},sort_keys=True))
'''
 result=json.loads(digital_runtime.wsl(['--distribution',runtime['distro'],'--exec','/opt/icstudio/bin/python3','-I','-c',code],timeout=300))
 require(result['dependencies']==expected,'Actual canonical loaded dependency closure differs')
 return result


def save_reopen_project(w,project,saved):
 from unittest.mock import patch
 from PySide6.QtWidgets import QMessageBox
 from icstudio.model import load_project,example,clone,digest
 from icstudio.mim_desktop_probe import selected_file
 w.set_project(project)
 with selected_file('getSaveFileName',saved):require(w.save(as_new=True) is True,'Save failed')
 w.close_project()
 empty=clone(w.project)
 def normalize(value):
  value=clone(value)
  for name in ('id','top','created','modified'):value.pop(name,None)
  for cell in value['cells']:
   cell.pop('id',None);cell.setdefault('wires',[]);cell.setdefault('junctions',[])
  return value
 require(w.path is None and normalize(empty)==normalize(example('empty')),'Only exact empty untitled project may be discarded')
 def discard_empty(parent,title,text,buttons,default):
  require(parent is w and title=='Save project?' and text=='Save changes to Untitled circuit?' and digest(w.project)==digest(empty) and buttons==(QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel) and default==QMessageBox.Save,'Unexpected discard dialog')
  return QMessageBox.Discard
 with selected_file('getOpenFileName',saved),patch.object(QMessageBox,'question',side_effect=discard_empty):w.open_project()
 require(load_project(saved)==w.project,'Actual save/reopen differs')
 return load_project(saved)


def main():
 import argparse,json
 p=argparse.ArgumentParser(description='One reviewed Windows/private-WSL research batch; draft contracts cannot run.')
 for name in ('contract','authorization','source','prepared','projects','output','evidence'):p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();result=run(a.contract,a.authorization,a.source,a.prepared,a.projects,a.output,a.evidence);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
