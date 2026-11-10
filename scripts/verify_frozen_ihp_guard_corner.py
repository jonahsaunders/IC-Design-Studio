"""Separate exact-candidate installed guard-routing gate; legacy60/165 gate unchanged.

Six Qt cases, eighteen GUI controls and twenty-one fresh managed native jobs
(six positives; fifteen geometry/reference controls). Not full-family signoff.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.verify_frozen_ihp_resistors import *
from scripts import verify_frozen_ihp_resistors as legacy

GUARD_ASSETS='icstudio/assets/qualification/ihp-guard-corner-safe'
CASES=tuple(f'{m}-r{r}' for m in MODELS for r in (0,90))
CORNER_LABEL='Corner-safe Metal2 body (2/7 um only)'
GUARD_FAULTS=('guard-via-open','body-open','terminal-short','reference-width','reference-model')
SCOPE='Separate frozen corner-safe guard routing: six actual Qt layouts,18 GUI controls,6 managed native positives and15 faults. Corrected finite routing, not native-mask equivalence or full-family qualification.'

def candidate(commit):
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,env=git_environment(),text=True).strip()==commit,'Selected candidate differs from checker HEAD.')
    result=legacy.candidate(commit)
    for name in ('scripts/verify_frozen_ihp_guard_corner.py','scripts/verify_windows.ps1',*(GUARD_ASSETS+'/'+n for n in ('templates.json','README.txt','Apache-2.0.txt'))):
        raw=git_blob(commit,name);expected=hashlib.sha256(raw).hexdigest();require(sha(ROOT/name)==expected,'Guard candidate input differs: '+name);result['files'][name]=expected
    require('icstudio/ihp_guard_corner_desktop_probe.py' in result['files'],'Missing guard producer in candidate.')
    return result


def assets_binding(bundle,inputs):
    result=legacy.assets_binding(bundle,inputs)
    for name,expected in inputs['files'].items():
        if name.startswith(GUARD_ASSETS+'/'):require(sha(unlinked(bundle/name))==expected,'Bundled guard asset differs: '+name);result[name]=expected
    return result


def header(report,executable,commit,nonce,inputs,bundle):
    require(report.get('schema')==1 and report.get('status')=='passed' and report.get('mode')=='guard-corner-safe-lifecycle' and report.get('frozen') is True,'Requires a passing frozen guard lifecycle producer.')
    require(report.get('execution_id')==nonce and re.fullmatch('[0-9a-f]{32}',nonce),'Stale guard execution nonce.')
    build=report.get('build',{});require(build.get('commit')==commit and build.get('dirty') is False and build.get('frozen') is True,'Guard build is different, dirty or not frozen.')
    require(Path(report['executable']).resolve()==executable.resolve() and report['executable_sha256']==sha(executable),'Guard executable identity differs.')
    require(Path(report['resource_root']).resolve()==bundle.resolve() and Path(report['template_path']).resolve()==(bundle/GUARD_ASSETS/'templates.json').resolve(),'Guard used external resources.')
    require(all(report.get(k) is False for k in ('qualified','release_ready','full_family','installed_acceptance','native_execution')) and not report.get('errors') and not report.get('error'),'Producer overclaim or error.')
    require(report['package_manifest_sha256']==inputs['package_sha256'] and report['bundle_collection_sha256']==inputs['collection_sha256'] and report['template_sha256']==inputs['files'][GUARD_ASSETS+'/templates.json'],'Guard package/template identity differs.')


def lifecycle(root,report,lock,templates):
    require([r.get('case') for r in report['lifecycle']]==list(CASES),'Missing/duplicate/reordered guard GUI cases.')
    require(Path(report['execution_root']).resolve()==root.resolve(),'Guard execution root differs.')
    rows=[]
    for row in report['lifecycle']:
        model,angle=row['case'].split('-r');angle=int(angle);saved=row['with_ports'];path=confined(root,saved['project'])
        require(sha(path)==saved['project_sha256'],'Changed guard saved project.')
        project=load(path);require(design_hash(project)==saved['design_hash'] and project['pdk']['package_lock']==saved['package_lock'],'Guard reopened design/lock differs.')
        prior=row['saved'];prior_path=confined(root,prior['project']);prior_project=load(prior_path)
        require(sha(prior_path)==prior['project_sha256'] and design_hash(prior_project)==prior['design_hash'] and prior_project['pdk']['package_lock']==prior['package_lock'],'Guard first save/reopen differs.')
        prior_geometry=copy.deepcopy(prior_project);prior_geometry['cells'][0]['layout_ports']=copy.deepcopy(project['cells'][0]['layout_ports'])
        same_stream(project_stream(project),project_stream(prior_geometry))
        require(prior_project['cells'][0]['devices']==project['cells'][0]['devices'] and prior_project['cells'][0]['pdk_layouts']==project['cells'][0]['pdk_layouts'],'Port assignment changed device/generation.')
        cell=project['cells'][0];top=f'guard_{model}_r{angle}_{report["execution_id"][:12]}'
        require(len(project['cells'])==1 and project['top']==cell['id'] and cell['name']==top and cell['ports']==['R1','R2','B'] and len(cell['devices'])==1,'Guard top/interface differs.')
        require((row['model'],row['rotation'],row['width_um'],row['length_um'],row['terminal_access'],row['guard_routing'])==(model,angle,2,7,'Metal1','corner-safe-m2-v1'),'Guard case scope differs.')
        require(all(row[k] is True for k in ('generation_undo_redo','same_option_regeneration','guard_option_stale','dimensions_stale','stale_preview_rejected')) and len(row['switches'])==4,'Incomplete guard lifecycle actions.')
        require(row['switches']==[dict(iteration=i,guard_routing=label,undo_redo=True) for i in range(2) for label in ('Native Metal1 body',CORNER_LABEL)],'Guard repeated option transitions differ.')
        require(row['interruption_controls']==dict(form_cancel=True,review_cancel=True,selection_not_persisted=True),'Guard cancellation controls differ.')
        blocked=row['invalid_regeneration'];bp=confined(root,blocked['project']);bproject=load(bp)
        require(sha(bp)==blocked['project_sha256'] and digest(bproject)==blocked['before_hash']==blocked['after_hash'] and blocked['apply_disabled'] is True and blocked['unchanged'] is True and blocked['requested_guard']==CORNER_LABEL and blocked['requested_terminal_access']=='Metal1','Invalid regeneration changed design or control.')
        bc=next(c for c in bproject['cells'] if c['id']==blocked['cell_id']);bd=bc['devices'][0]
        require(len(bc['devices'])==1 and bd['model_ref']['device']=='sg13g2_pr/'+model+'.sym' and bd.get('physical_guard_routing')=='corner-safe-m2-v1' and all(math.isclose(scalar(bd['model_params'][k]),v,rel_tol=1e-12,abs_tol=1e-18) for k,v in (('w',7e-6),('l',2e-6))) and bc['pdk_layouts']==row['generation'],'Invalid regeneration is not the fixed stale-dimension control.')
        require(all(project['pdk']['package_lock'][k]==lock[k] for k in ('id','revision','files')),'Guard package lock differs.')
        registry=confined(root,project['pdk']['package_root']);require(digest(load(registry/'package.json'))==digest(lock),'Guard registry differs.');file_map(registry,lock['files'])
        device=cell['devices'][0];symbol='sg13g2_pr/'+model+'.sym';require(device['kind']=='PDK' and device['model_ref']==dict(pdk='ihp-sg13g2',revision=lock['revision'],device=symbol) and device['nets']==dict(p='R1',m='R2',body='B'),'Guard model/nets differ.')
        require(device.get('physical_terminal_vias',False) is False and device.get('physical_guard_routing')=='corner-safe-m2-v1','Guard access choice differs.')
        original=lock['technology']['simulation']['catalog'][symbol];binding=project['pdk']['simulation']['catalog'][symbol]
        require(all(binding[k]==original[k] for k in ('model','prefix','pin_order','emit_parameters','parameter_scale','parameters')),'Guard catalog binding changed.')
        expected={key:scalar(v['default']) for key,v in original['parameters'].items()};expected.update(w=2e-6,l=7e-6,m=1)
        if 'b' in expected:expected['b']=0
        require(same_parameters({k:scalar(v) for k,v in device['model_params'].items()},expected),'Guard actual dimensions/parameters differ.')
        require(cell['pdk_layouts']==row['generation'] and cell['layout_pins']==row['layout_pins'] and cell['layout_ports']==row['layout_ports'],'Guard saved lifecycle receipt differs.')
        require(len(cell['pdk_layouts'])==1,'Guard has extra footprint records.');spec=cell['pdk_layouts'][0]['spec']
        require(spec['recipe']=='ihp-resistor-guard-corner-safe-v1' and spec['guard_routing']=='corner-safe-m2-v1' and spec['guard_native_equivalence'] is False and spec['template_sha256']==report['template_sha256'] and spec['guard_contract_sha256']==templates['contract_sha256'] and spec['guard_source_report_sha256']==templates['source_report_sha256'],'Guard corrected spec provenance differs.')
        require(spec['source_hashes']==report['source_hashes'] and all(lock['files']['libs.tech/magic/'+k]==v for k,v in spec['source_hashes'].items()) and spec['package_manifest_semantic_sha256']==digest(lock) and spec['guard_cifout_sha256']==report['guard_cifout_sha256']==lock['files']['libs.tech/magic/ihp-sg13g2-cifout.tech'],'Guard source/package provenance differs.')
        require(spec['model']==model and spec['dimensions_nm']==dict(w=2000,l=7000) and spec['terminal_vias'] is False and spec['nets']==device['nets'] and same_parameters(spec['values'],expected),'Guard spec parameters differ.')
        pins={x['pin']:x for x in cell['layout_pins']};ports={x['name']:x for x in cell['layout_ports']}
        require(len(cell['layout_pins'])==len(cell['layout_ports'])==3 and set(pins)=={'p','m','body'} and set(ports)=={'R1','R2','B'},'Guard missing/duplicate pins.')
        for pin,name in (('p','R1'),('m','R2'),('body','B')):
            layer='Metal2.drawing' if pin=='body' else 'Metal1.drawing'
            require(pins[pin]['device_id']==device['id'] and pins[pin]['layer']==ports[name]['layer']==layer and pins[pin]['point']==ports[name]['point'],'Guard pin layer/anchor differs.')
            text=[t for t in cell.get('layout_texts',[]) if t['text']==name];require(len(text)==1 and text[0]['layer']==layer.replace('.drawing','.pin'),'Guard duplicate/lower terminal label.')
        target=legacy.oracle(templates['templates'][model],dict(rotation=angle),cell['pdk_layouts'])
        # Regeneration rotates geometry/anchors but deliberately emits upright text.
        target=(target[0],[(*v[:4],0) for v in target[1]]);same_stream(project_stream(project),target)
        for ext in ('gds','oas'):same_stream(stream(root/row['case']/('layout.'+ext),top),target,text_presentation=ext=='gds')
        ref=confined(root,saved['reference']);circuit(ref.read_text(),top,model,2,7,schematic=True,expected_params=expected)
        exported=confined(root,saved['schematic']).read_text();primitive=re.findall(r'(?mi)^X\S+.*$',exported);reference_primitive=re.findall(r'(?mi)^X\S+.*$',ref.read_text())
        require(primitive==reference_primitive and len(primitive)==1 and not re.search(r'(?im)^\s*[rcqmdjblv]\S+\s',exported),'Guard schematic export differs from reference.')
        rows.append((dict(case=row['case'],top=top,model=model,width_um=2,length_um=7,rotation=angle,terminal_vias=False,reference=str(ref)),project,target))
    return rows


def producer_controls(root,report,bundle,inputs):
    require(len(report['legacy'])==2 and {Path(x['source']).name for x in report['legacy']}=={'mos.icproj','resistor.icproj'},'Guard legacy coverage missing.')
    for row in report['legacy']:
        name=Path(row['source']).name;source=bundle/LEGACY/name
        require(Path(row['source']).resolve()==source.resolve() and sha(source)==row['source_sha256']==inputs['files'][LEGACY+'/'+name] and sha(confined(root,row['saved']))==row['saved_sha256'],'Guard legacy evidence identity differs.')
        def protected(project):
            cells=[]
            for cell in project['cells']:
                devices=copy.deepcopy(cell['devices'])
                for device in devices:device.pop('net_labels',None)
                cells.append({key:cell.get(key,{} if key=='parameters' else []) for key in ('id','name','ports','parameters','shapes','layout_pins','layout_ports','layout_texts','pdk_layouts')}|dict(devices=devices))
            return dict(id=project['id'],top=project['top'],parameters=project.get('parameters',{}),cells=cells)
        require(protected(load(source))==protected(load(confined(root,row['saved']))),'Guard changed legacy project semantics.')
    expected=[]
    for m in MODELS:expected.extend([f'{m}-invalid-size-{i}' for i in range(4)]+[m+'-corner-metal2',m+'-legacy-metal2'])
    require([r.get('case') for r in report['controls']]==expected,'Guard GUI controls missing/duplicate/reordered.')
    for row in report['controls']:
        model=row['case'].split('-')[0];kind='invalid-size' if '-invalid-size-' in row['case'] else 'unsupported-corner-metal2' if row['case'].endswith('-corner-metal2') else 'legacy-metal2-preserved'
        require(row.get('model')==model and row.get('kind')==kind,'Guard control kind/model does not match fixed case.')
        if row['kind']=='legacy-metal2-preserved':
            saved=row['saved'];require(sha(confined(root,saved['project']))==saved['project_sha256'],'Legacy M2 save changed.');p=load(confined(root,saved['project']));c=p['cells'][0];d=c['devices'][0]
            require(d['model_ref']['device']=='sg13g2_pr/'+model+'.sym' and row['legacy_metal2_access_preserved'] is True and d.get('physical_terminal_vias') is True and 'physical_guard_routing' not in d and c['pdk_layouts'][0]['spec']['recipe']=='ihp-resistor-selected-v1','Legacy M2 behavior changed.')
            continue
        require(row['requested_guard']==CORNER_LABEL and row['apply_disabled'] is True and row['unchanged'] is True,'Guard rejection selection/result differs.')
        path=confined(root,row['project']);require(sha(path)==row['project_sha256'],'Blocked guard project changed.');p=load(path);c=next(x for x in p['cells'] if x['id']==row['cell_id'])
        require(row['before_hash']==row['after_hash'] and digest(p)==row['before_hash'] and not c['shapes'] and not c.get('pdk_layouts') and len(c['devices'])==1,'Blocked guard changed original design.')
        d=c['devices'][0];require(d['model_ref']['device']=='sg13g2_pr/'+row['model']+'.sym','Blocked guard model differs.')
        if row['kind']=='invalid-size':
            require(row['requested_terminal_access']=='Metal1','Invalid-size control access differs.')
            pair=((7,2),(.5,.5),(1,7),(2,7.000001))[int(row['case'].rsplit('-',1)[1])]
            require(all(math.isclose(scalar(d['model_params'][k])*1e6,v,rel_tol=0,abs_tol=1e-10) for k,v in zip(('w','l'),pair)),'Blocked guard dimension differs.')
        else:require(row['kind']=='unsupported-corner-metal2' and row['requested_terminal_access']=='Metal2' and all(math.isclose(scalar(d['model_params'][k]),v,rel_tol=1e-12,abs_tol=1e-18) for k,v in (('w',2e-6),('l',7e-6))),'Wrong terminal-access control.')


def source_audit(root,resources):
    """Explicit read-only development audit; cannot enter installed verify()."""
    root=unlinked(root).resolve();resources=unlinked(resources).resolve();report=load(root/'report.json')
    require(report.get('source_unchanged') is True and report.get('mode')=='guard-corner-safe-lifecycle' and report.get('frozen') is False and report.get('status')=='passed' and report.get('native_execution') is False and all(report.get(k) is False for k in ('qualified','installed_acceptance','release_ready','full_family')),'Source lifecycle report is incomplete or overclaims.')
    require(load(root/'files.json')==inventory(root,('report.json','files.json')) and sha(root/'files.json')==report['files_sha256'],'Source final post-exit inventory differs.')
    lock=package(resources/PDK,sha(resources/PDK/'package.json'));templates=load(resources/GUARD_ASSETS/'templates.json')
    require(report['template_sha256']==sha(resources/GUARD_ASSETS/'templates.json') and report['package_manifest_semantic_sha256']==digest(lock),'Reviewed source assets differ.')
    rows=lifecycle(root,report,lock,templates)
    files={str(path.relative_to(resources)).replace('\\','/'):sha(path) for path in (resources/LEGACY).iterdir() if path.is_file()};producer_controls(root,report,resources,dict(files=files))
    return dict(status='PASS',gate='ihp-guard-corner-source-gui-readback',qualified=False,release_ready=False,full_family=False,installed_acceptance=False,native_execution=False,gui_layouts=len(rows),gui_controls=18,legacy_projects=2,frozen=False,source_unchanged=report['source_unchanged'],report_sha256=sha(root/'report.json'),files_sha256=sha(root/'files.json'))

def guard_via_open(project):
    import klayout.db as db
    q=copy.deepcopy(project);c=q['cells'][0];ports={v['name']:v for v in c['layout_ports']};point=ports['B']['point'];source=project_stream(project)
    selected=[p for p in source[0][10,0].each() if p.inside(db.Point(*point))];require(len(selected)==1,'Guard fault needs one selected M2 component.')
    region=db.Region(selected[0]);layers={l['name']:(l['gds'],l['datatype']) for l in q['pdk']['layers']};removed=[]
    for s in c['shapes']:
        if layers[s['layer']]!=(19,0):continue
        poly=db.Polygon(db.Box(*s['points'][0],*s['points'][1])) if s['kind']=='rect' else db.Polygon([db.Point(*p) for p in s['points']])
        if not (db.Region(poly)&region).is_empty():removed.append(s)
    require(len(removed)==54,'Guard cut-set control must remove all54 actual cuts.');c['shapes']=[s for s in c['shapes'] if s not in removed];return q


def run_jobs(executable,rows,out,env,runtime,inputs,physical,records,nonce,deadline):
    jobs=[]
    for row,project,_ in rows:
        for fault in (None,)+ (GUARD_FAULTS if row['rotation']==0 else ()):
            folder=out/'native'/row['case']/(fault or 'positive');actual=guard_via_open(project) if fault=='guard-via-open' else project
            prepare_fault=None if fault=='guard-via-open' else fault
            job,job_project,ref,command,attempt,tick=legacy.prepare_job(executable,actual,row,folder,runtime,inputs,physical,prepare_fault)
            execute_job(folder,command,attempt,tick,env,deadline=deadline,runtime=runtime)
            result=legacy.audit_job(folder,row,job,job_project,ref,runtime,physical,records,'body-open' if fault=='guard-via-open' else fault)
            result['fault']=fault;jobs.append(result)
    return jobs


def verify(executable,out,commit,timeout=900):
    executable=unlinked(executable).resolve();out=unlinked(out).resolve();require(re.fullmatch('[0-9a-f]{40}',commit) and math.isfinite(timeout) and timeout>0,'Exact candidate and finite deadline required.')
    require(not out.is_relative_to(executable.parent) and not executable.is_relative_to(out),'Evidence output cannot overlap installed deliverable.')
    require(not out.exists(),'Use a fresh parent output directory.');out.mkdir(parents=True);nonce=uuid.uuid4().hex;started=time.monotonic()
    try:
        inputs=candidate(commit);bundle=executable.parent/'_internal';lock=package(bundle/PDK,inputs['package_sha256']);assets_binding(bundle,inputs)
        payload=bundle/'icstudio/assets/runtime/digital';payload_hash=sha(payload/'manifest.json');meta=load(payload/'manifest.json')
        require(meta['schema']==1 and meta['archive']=='runtime.tar.gz' and sha(payload/'runtime.tar.gz')==meta['sha256'],'Frozen payload archive changed.')
        backend=backend_binding(payload/'backend/icstudio',commit);build_metadata(payload/'backend/icstudio',commit,inputs)
        for name in inputs['files']:
            if name.startswith((ASSETS+'/',GUARD_ASSETS+'/')):require(sha(payload/'backend'/name)==inputs['files'][name],'Shipped native backend omitted recipe assets.')
        env=git_environment()
        for key in list(env):
            if key.upper() in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','ICSTUDIO_DIGITAL_PAYLOAD','ICSTUDIO_DIGITAL_NATIVE','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH'):env.pop(key)
        env['QT_QPA_PLATFORM']='offscreen'
        if not env.get('ICSTUDIO_DIGITAL_STATE'):
            base=Path(env['LOCALAPPDATA']) if os.name=='nt' else Path(env.get('XDG_DATA_HOME',str(Path.home()/'.local/share')));env['ICSTUDIO_DIGITAL_STATE']=str(base/'ICDesignStudio/digital')
        exe_hash=sha(executable);command=[str(executable),'--ihp-guard-corner-acceptance','--managed','--execution-id',nonce,'--out',str(out/'probe')]
        write(out/'invocation.json',dict(command=command,expected_commit=commit,execution_id=nonce,executable_sha256=exe_hash,expected_inputs=inputs,payload_manifest_sha256=payload_hash))
        launch=dict(command=command,expected_commit=commit,execution_id=nonce,executable_sha256=exe_hash,expected_inputs=inputs,payload_manifest_sha256=payload_hash,status='RUNNING',started_unix=time.time());write(out/'invocation.json',launch)
        try:
            with (out/'launcher.log').open('wb') as log:completed=subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,check=True)
            launch.update(status='complete',returncode=completed.returncode,seconds=time.monotonic()-started,log_sha256=sha(out/'launcher.log'));write(out/'invocation.json',launch)
        except BaseException as error:
            launch.update(status='failed',returncode=getattr(error,'returncode',None),error=str(error),seconds=time.monotonic()-started,log_sha256=sha(out/'launcher.log'));write(out/'invocation.json',launch);raise
        producer=out/'probe';report=load(producer/'report.json');header(report,executable,commit,nonce,inputs,bundle)
        require(sha(producer/'files.json')==report['files_sha256'] and load(producer/'files.json')==inventory(producer,('report.json','files.json')),'Producer final post-exit inventory differs.')
        producer_inventory=inventory(producer);write(out/'producer-receipt.json',producer_inventory)
        runtime,records=check_runtime(producer,report,bundle,backend,payload_hash)
        before=runtime_files(runtime,records);uid_before=runtime_uid(runtime,env);write(out/'runtime-before.json',dict(files=before,native=uid_before))
        rows=lifecycle(producer,report,lock,load(bundle/GUARD_ASSETS/'templates.json'));producer_controls(producer,report,bundle,inputs);jobs=[]
        physical=dict(root=bundle/PDK,package=lock)
        jobs=run_jobs(executable,rows,out,env,runtime,inputs,physical,records,nonce,started+timeout)
        require(len(jobs)==21 and sum(v['fault'] is None for v in jobs)==6 and len({v['execution']['native_directory'] for v in jobs})==21,'Native job selection incomplete or reused a native directory.')
        after=runtime_files(runtime,records);uid_after=runtime_uid(runtime,env);write(out/'runtime-after.json',dict(files=after,native=uid_after));require(before==after and uid_before==uid_after and inventory(producer)==producer_inventory,'Runtime/UID or immutable GUI evidence changed during native execution.')
        require(candidate(commit)==inputs,'Checker candidate changed during execution.')
        require(sha(payload/'runtime.tar.gz')==meta['sha256'],'Frozen runtime archive changed during execution.')
        require(sha(executable)==exe_hash and sha(payload/'manifest.json')==payload_hash and backend_binding(payload/'backend/icstudio',commit)==backend,'Frozen executable/backend changed.');assets_binding(bundle,inputs);package(bundle/PDK,inputs['package_sha256'])
        result=dict(schema=1,status='PASS',gate='ihp-guard-corner-installed-gui-managed-layout',scope=SCOPE,qualified=False,release_ready=False,full_family=False,installed_acceptance=True,expected_commit=commit,execution_id=nonce,executable_sha256=exe_hash,report_sha256=sha(producer/'report.json'),producer_receipt_sha256=sha(out/'producer-receipt.json'),counts=dict(gui_layouts=6,gui_controls=18,legacy_projects=2,native_layouts=6,native_controls=15,fresh_managed_jobs=21),expected_inputs=inputs,runtime=runtime,native_identity=uid_before,runtime_identity_sha256=digest(before),jobs=jobs,seconds=time.monotonic()-started)
        write(out/'files.json',inventory(out,('verification.json','files.json')));result['files_sha256']=sha(out/'files.json');write(out/'verification.json',result);return result
    except Exception as error:
        failure=dict(schema=1,status='FAIL',scope=SCOPE,qualified=False,release_ready=False,full_family=False,installed_acceptance=False,expected_commit=commit,execution_id=nonce,error=str(error),seconds=time.monotonic()-started)
        try:write(out/'files.json',inventory(out,('verification.json','files.json')));failure['files_sha256']=sha(out/'files.json')
        except Exception as inventory_error:failure['inventory_error']=str(inventory_error)
        write(out/'verification.json',failure);raise

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--executable',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--expected-commit',required=True);ap.add_argument('--timeout',type=float,default=900)
    args=ap.parse_args();print(json.dumps(verify(args.executable,args.out,args.expected_commit,args.timeout),indent=2))

if __name__=='__main__':main()
