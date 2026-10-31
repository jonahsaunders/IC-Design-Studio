"""Run the isolated pw2dn GUI hook in a caller-selected frozen candidate."""
import argparse,json,math,os,re,shutil,signal,subprocess,sys,time,uuid
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest
from scripts import installed_mim_inputs as identity
from scripts import verify_frozen_pw2dn as reader
from scripts.sky130_pw2dn_source import BASE,CURRENT,predecessor
from scripts.verify_frozen_mim import unlinked

COLLECTION='4472d7255a991ef8a0be1d4580dc8a3e09bb4b02e6f7354954513382462e6592'
def terminate_tree(proc):
    """Stop descendants even when a native engine starts its own session."""
    if os.name=='nt':
        try:
            result=subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,check=False,timeout=10)
            proc.wait(timeout=10)
            return {'method':'taskkill-tree','confirmed':result.returncode==0,'diagnostic':result.stdout[-4000:]}
        except Exception as exc:
            try:proc.kill();proc.wait(timeout=10)
            except Exception:pass
            return {'method':'taskkill-tree','confirmed':False,'error':repr(exc)}
    known={};alive=[]
    def identity_for(pid):
        try:
            fields=(Path('/proc')/str(pid)/'stat').read_text().rsplit(') ',1)[1].split()
            return fields[0],fields[19],int(fields[1])
        except FileNotFoundError:return None
    def owned_signal(pid,start,action):
        current=identity_for(pid)
        if current is not None and current[1]==start and current[0]!='Z':
            try:os.kill(pid,action)
            except ProcessLookupError:pass
    try:
        initial=identity_for(proc.pid)
        if initial is None:return {'method':'proc-descendant-tree','confirmed':False,'error':'Desktop disappeared before descendant discovery.'}
        known[proc.pid]=initial[1];owned_signal(proc.pid,known[proc.pid],signal.SIGSTOP);stable=False
        for _ in range(8):
            lines=subprocess.check_output(['/bin/ps','-eo','pid=,ppid='],text=True,timeout=3).splitlines()
            pairs=[tuple(map(int,line.split())) for line in lines if len(line.split())==2]
            fresh=False;stale=False
            for pid,ppid in pairs:
                if ppid not in known or pid in known:continue
                parent=identity_for(ppid);current=identity_for(pid)
                if parent is None or parent[1]!=known[ppid] or current is None or current[2]!=ppid:
                    stale=True;continue
                known[pid]=current[1];owned_signal(pid,current[1],signal.SIGSTOP);fresh=True
            if not fresh and not stale:stable=True;break
        for pid in sorted(set(known)-{proc.pid},reverse=True):owned_signal(pid,known[pid],signal.SIGKILL)
        owned_signal(proc.pid,known[proc.pid],signal.SIGKILL)
        proc.wait(timeout=10)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            alive=[]
            for pid in set(known)-{proc.pid}:
                current=identity_for(pid)
                if current is not None and current[1]==known[pid] and current[0]!='Z':alive.append(pid)
            if not alive:break
            time.sleep(.05)
        return {'method':'proc-descendant-tree','confirmed':stable and not alive,'children':known,'remaining':alive}
    except Exception as exc:
        for pid,start in known.items():
            try:owned_signal(pid,start,signal.SIGKILL)
            except Exception:pass
        try:proc.kill();proc.wait(timeout=10)
        except Exception:pass
        return {'method':'proc-descendant-tree','confirmed':False,'error':repr(exc)}

def sources(commit):
    env={k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')}
    names=subprocess.check_output(['git','ls-tree','-rz','--name-only',commit,'--','icstudio','scripts'],cwd=ROOT,env=env)
    selected=[]
    extra={'scripts/qualify_installed_sky130_pw2dn.py','scripts/verify_frozen_pw2dn.py','scripts/audit_installed_sky130_pw2dn_native.py',
           'scripts/sky130_pw2dn_source.py','scripts/verify_frozen_mim.py','scripts/installed_mim_inputs.py'}
    for raw in names.split(b'\0'):
        if not raw:continue
        name=raw.decode()
        if ((name.startswith('icstudio/') and name.count('/')==1 and name.endswith('.py') and name!='icstudio/build_info.py')
            or name in extra or name in ('icstudio/assets/pdks/collection.json','icstudio/assets/pdks/sky130A/package.json',
            'icstudio/assets/qualification/sky130-pw2dn-predecessor-v1/package.json')):selected.append(name)
    reader.require(extra.issubset(selected) and {'icstudio/pw2dn_desktop_probe.py','icstudio/pw2dn_native_probe.py'}.issubset(selected),'Candidate source inventory incomplete.')
    result={name:file_digest(unlinked(ROOT/name)) for name in selected};identity.candidate_sources(result,commit)
    return result

def run(executable,engine,out,commit,timeout,executable_sha256,engine_sha256):
    reader.require(re.fullmatch('[0-9a-f]{40}',commit or '') and math.isfinite(timeout) and timeout>0,'Expected commit and finite positive timeout required.')
    reader.require(re.fullmatch('[0-9a-f]{64}',executable_sha256 or '') and re.fullmatch('[0-9a-f]{64}',engine_sha256 or ''),'Expected binary SHA-256 values required.')
    executable=unlinked(executable).resolve();engine=unlinked(engine).resolve();out=unlinked(out).resolve()
    reader.require(file_digest(executable)==executable_sha256 and file_digest(engine)==engine_sha256,'Selected binaries differ from caller identities.')
    reader.require(not out.exists() and not out.is_relative_to(executable.parent),'Use a new output outside the installation.')
    resource=executable.parent/'_internal';bundled=resource/'icstudio/assets/pdks/sky130A'
    reader.require(engine.parent==resource/'icstudio/assets/runtime/ngspice','Engine must be inside selected installation.')
    source_files=sources(commit);pack=reader.package(bundled,CURRENT)
    collection=unlinked(bundled.parent/'collection.json');reader.require(file_digest(collection)==COLLECTION,'Shipped collection differs.')
    runtime_manifest=unlinked(engine.parent/'runtime-manifest.json');runtime=json.loads(runtime_manifest.read_bytes())
    reader.require(engine.name in runtime['files'],'Engine absent from shipped runtime manifest.')
    for name,sha in runtime['files'].items():
        path=unlinked(engine.parent/name).resolve()
        reader.require(path.is_relative_to(engine.parent) and file_digest(path)==sha,'Changed engine runtime: '+name)
    out.mkdir(parents=True);execution_id=uuid.uuid4().hex
    old_manifest=unlinked(resource/'icstudio/assets/qualification/sky130-pw2dn-predecessor-v1/package.json')
    with predecessor(bundled,old_manifest) as old:shutil.copytree(old,out/'predecessor')
    prior=reader.package(out/'predecessor',BASE)
    preparation=out/'environment-preparation';preparation.mkdir()
    native_binding={'mode':'installed','resource_root':str(resource)}
    native_env=identity.native_environment(native_binding,engine,preparation)
    native_env={k:v.replace(str(preparation),str(out/'native/native-environment')) for k,v in native_env.items()}
    native_runtime=identity.runtime(native_binding,engine,native_env)
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(('GIT_','PYTHON','SPICE_','ICSTUDIO_NGSPICE','ICSTUDIO_BUNDLED_NGSPICE')) and k.upper() not in ('LD_LIBRARY_PATH','LD_PRELOAD','ICSTUDIO_DIGITAL_PAYLOAD','ICSTUDIO_DIGITAL_NATIVE')}
    env['QT_QPA_PLATFORM']='offscreen';env['PYTHONDONTWRITEBYTECODE']='1'
    command=[str(executable),'--pw2dn-acceptance','--out',str(out/'gui'),'--predecessor',str(out/'predecessor'),'--execution-id',execution_id,'--engine',str(engine),'--native-out',str(out/'native')]
    expected={'schema':'pw2dn-frozen-gui-input-v1','scope':'frozen-gui-lifecycle-only','execution_id':execution_id,'commit':commit,'timeout_seconds':timeout,'captured_utc':datetime.now(timezone.utc).isoformat(),'executable':str(executable),'executable_sha256':file_digest(executable),
              'engine':str(engine),'engine_sha256':file_digest(engine),'runtime_manifest_sha256':file_digest(runtime_manifest),'runtime_files':runtime['files'],'native_environment':native_env,'runtime':native_runtime,
              'candidate_manifest_sha256':CURRENT,'candidate_files':pack['files'],'candidate_technology':pack['technology'],'collection_sha256':COLLECTION,
              'predecessor_files':prior['files'],'predecessor_technology':prior['technology'],
              'bundled_package':str(bundled.resolve()),'candidate_sources':source_files,'command':command}
    (out/'expected.json').write_text(json.dumps(expected,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    invocation={'status':'RUNNING','command':command,'execution_id':execution_id,'started_utc':datetime.now(timezone.utc).isoformat()}
    started=time.monotonic()
    try:
        with (out/'launcher.log').open('wb') as log:
            proc=subprocess.Popen(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=os.name!='nt',creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
            try:code=proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                invocation['cleanup']=terminate_tree(proc)
                raise
        invocation['returncode']=code
        reader.require(type(code) is int and code==0,'Frozen GUI child failed.')
        expected['prelaunch_sha256']=file_digest(out/'gui/prelaunch.json')
        expected['producer_inventory']=reader.inventory(out/'gui')
        (out/'readback-input.json').write_text(json.dumps(expected,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        result=reader.verify(out/'gui',expected)
        reader.require(reader.inventory(out/'gui')==expected['producer_inventory'],'Producer output changed during independent readback.')
        result['readback_input_sha256']=file_digest(out/'readback-input.json')
        (out/'gui-verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        native=json.loads(unlinked(out/'native/report.json').read_bytes())
        reader.require(native['status']=='PASS_NATIVE_PRODUCTION_ONLY' and native['frozen'] is True and native['execution_id']==execution_id,'Frozen native production incomplete.')
        reader.require(Path(native['selected_project']).resolve()==out/'gui/new/project.icproj' and native['selected_project_sha256']==result['project_sha256'],'Native input is not the audited GUI specimen.')
        reader.require(Path(native['engine']).resolve()==engine and native['engine_sha256']==engine_sha256 and native['runtime_before']==native['runtime_after'],'Native engine/runtime identity differs.')
        reader.require(native['native_environment']==native_env and native['runtime_before']==native_runtime,'Native runtime differs from trusted prelaunch capture.')
        reader.require(native['build']['frozen'] is True and native['build']['dirty'] is False and native['build']['commit']==commit and Path(native['resource_root']).resolve()==resource,'Native frozen build provenance differs.')
        native_expected={**expected,'gui_verification_sha256':file_digest(out/'gui-verification.json'),
            'mode':'installed','pilot':False,'candidate_root':str(bundled),'package_manifest_sha256':CURRENT,
            'gui_report_sha256':file_digest(out/'gui/report.json'),'selected_project_sha256':result['project_sha256'],'selected_export_sha256':result['spice_sha256'],
            'source_root':str(ROOT),'resource_root':str(resource),'selected_project':str(out/'gui/new/project.icproj'),
            'gui_verification_path':str(out/'gui-verification.json'),'native_origin':str(out/'native'),
            'source_files':source_files,'reader_files':{str(ROOT/name):sha for name,sha in source_files.items() if name.startswith('scripts/')},
            'native_report_sha256':file_digest(out/'native/report.json'),'native_inventory':reader.inventory(out/'native')}
        (out/'native-inputs.json').write_text(json.dumps(native_expected,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        # The external reader independently builds literal references and audits
        # raw currents, guards, faults and provenance. Bound its entire process
        # tree as well as the frozen desktop; a missing reader is a hard failure.
        reference_out=out/'native-references'
        reference_command=[sys.executable,'-B',str(ROOT/'scripts/audit_installed_sky130_pw2dn_native.py'),
            '--native-root',str(out/'native'),'--gui-root',str(out/'gui'),'--engine',str(engine),
            '--expected',str(out/'native-inputs.json'),'--reference-out',str(reference_out),'--source',str(ROOT)]
        ref_invocation={'status':'RUNNING','command':reference_command,'execution_id':execution_id,'started_utc':datetime.now(timezone.utc).isoformat()}
        try:
            with (out/'reference-launcher.log').open('wb') as log:
                refproc=subprocess.Popen(reference_command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=os.name!='nt',creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
                try:refcode=refproc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    ref_invocation['cleanup']=terminate_tree(refproc);raise
            ref_invocation['returncode']=refcode
            reader.require(type(refcode) is int and refcode==0,'Independent native reference child failed.')
            native_result=json.loads(unlinked(reference_out/'verification.json').read_bytes())
            ref_invocation['status']='PASS'
        except BaseException as exc:
            ref_invocation.update(status='FAIL',error=repr(exc));raise
        finally:
            ref_invocation['ended_utc']=datetime.now(timezone.utc).isoformat()
            if (out/'reference-launcher.log').exists():ref_invocation['log_sha256']=file_digest(out/'reference-launcher.log')
            (out/'reference-invocation.json').write_text(json.dumps(ref_invocation,indent=2)+'\n',encoding='utf-8')
        reader.require(native_result.get('status')=='PASS_FROZEN_NATIVE_ELECTRICAL','Independent native audit failed.')
        reader.require(reader.inventory(out/'native')==native_expected['native_inventory'],'Native output changed during independent readback.')
        (out/'native-verification.json').write_text(json.dumps(native_result,indent=2)+'\n',encoding='utf-8')
        reader.require(file_digest(executable)==expected['executable_sha256'] and file_digest(engine)==expected['engine_sha256'],'Executable or engine changed during run.')
        reader.require(file_digest(runtime_manifest)==expected['runtime_manifest_sha256'] and sources(commit)==source_files,'Runtime or candidate source changed during run.')
        for name,sha in runtime['files'].items():reader.require(file_digest(unlinked(engine.parent/name))==sha,'Runtime asset changed during GUI run: '+name)
        reader.package(bundled,CURRENT)
        invocation['status']='PASS';combined={'status':'PASS_FROZEN_GUI_AND_NATIVE','gui_verification_sha256':file_digest(out/'gui-verification.json'),'native_verification_sha256':file_digest(out/'native-verification.json'),'execution_id':execution_id,'commit':commit}
        (out/'verification.json').write_text(json.dumps(combined,indent=2)+'\n',encoding='utf-8')
    except Exception as exc:
        invocation.update(status='FAIL',error=repr(exc));raise
    finally:
        invocation.update(ended_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-started)
        if (out/'launcher.log').exists():invocation['launcher_log_sha256']=file_digest(out/'launcher.log')
        (out/'invocation.json').write_text(json.dumps(invocation,indent=2)+'\n',encoding='utf-8')
    return combined

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--executable',type=Path,required=True);p.add_argument('--executable-sha256',required=True);p.add_argument('--engine',type=Path,required=True);p.add_argument('--engine-sha256',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--commit',required=True);p.add_argument('--timeout',type=float,default=900)
    a=p.parse_args();print(json.dumps(run(a.executable,a.engine,a.out,a.commit,a.timeout,a.executable_sha256,a.engine_sha256),indent=2))
