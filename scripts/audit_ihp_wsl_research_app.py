"""New post-reset structural native receipt audit. No numerical acceptance claim."""
from pathlib import Path,PurePosixPath
import re
from scripts.read_ihp_pmos_measured_v3 import require
from scripts.prepare_ihp_wsl_app_contract import load,sha,regular,SELECTION

def confined(root,name):
 p=PurePosixPath(name)
 require(isinstance(name,str) and not p.is_absolute() and bool(p.parts) and all(x not in ('','..','.') for x in p.parts) and '\\' not in name and ':' not in name,'Unsafe artifact name')
 q=Path(root).joinpath(*p.parts);require(q.resolve().is_relative_to(Path(root).resolve()),'Artifact escape');return regular(q)
def audit_job(root,runtime,modules):
 root=Path(root);meta=load(root/'physical-backend.json');native=load(root/'physical-backend-input.json')
 require(meta['native_input_sha256']==sha(root/'physical-backend-input.json'),'Native input binding')
 require(meta['runtime']==runtime and runtime['kind']=='wsl','Exact WSL identity')
 require(re.fullmatch(r'/var/tmp/icstudio-physical/[0-9a-f]{32}',meta['native_directory']) is not None,'Private native directory')
 require(native['executable']=='/opt/icstudio/bin/ngspice' and native['project']['pdk']['package_root']==meta['native_directory']+'/pdk','Native tool/PDK paths')
 settings=native['settings'];require(settings['tools']=={n:'/opt/icstudio/bin/'+n for n in ('magic','netgen','ngspice','klayout')},'Native tool configuration differs');require(settings['managed_osdi']=='ihp-sg13g2' and settings['timeout']==90 and settings.get('dc_startup',False) is False,'Native production settings')
 expected=[dict(path='/opt/icstudio/osdi/ihp-sg13g2/'+name,sha256=h,system='Linux',machine='x86_64') for name,h in modules]
 require(len(expected)==6 and len({x['path'] for x in expected})==6,'Exact six modules')
 require(native['project']['simulation_runtime']=={'osdi':expected},'Native module identity')
 require(load(root/'runtime-lock.json')=={'osdi':expected},'Staged module lock')
 for i,(_,h) in enumerate(modules):require(sha(regular(root/f'runtime-osdi/model-{i}.osdi'))==h,'Staged module bytes')
 artifacts=load(root/'physical-artifacts.json')
 require(bool(artifacts),'Empty native artifact inventory')
 for name,h in artifacts.items():require(sha(confined(root,name))==h,'Received native bytes differ')
 host=load(root/'physical-host-result.json');require(host['managed_execution']==dict(meta,received_files=artifacts),'Host/backend receipt join')
 status=load(root/'status.json');require(status['status']=='complete' and status['exit_code']==0,'Incomplete native job')
 result=load(root/'result.json');require('reused_from' not in result,'Reused job')
 return {'scope':'STRUCTURAL_RECEIPT_ONLY','artifact_files':len(artifacts),'numerical_acceptance':False}

def audit(path):
 receipt=load(path)
 require(receipt.get('qualified') is False,'No qualification promotion')
 raise ValueError('BLOCKED: full deck/source/independent raw comparison remains unreconstructed; structural receipts alone cannot yield acceptance')

def compare_raw(actual,original,expected_title,reader,atol,rtol):
 """Finite original-grid comparison; caller must first authenticate reader/decks."""
 import math
 require(atol>0 and rtol>0,'Positive inherited tolerances')
 text=regular(actual).read_text()
 require(text.splitlines()[0].casefold()==('Title: '+expected_title).casefold() and 'Command: ngspice-47,' in text,'Raw title/engine')
 values,axis=reader(actual);reference,expected_axis=reader(original)
 require(len(axis)==len(expected_axis)==28 and all(abs(x+j/20)<1e-12 for j,x in enumerate(axis)) and axis==expected_axis,'Exact original grid')
 require(all('i(v'+t+')' in values and 'i(v'+t+')' in reference for t in 'dgsb'),'All terminal currents required')
 errors=[]
 for t in 'dgsb':
  name='i(v'+t+')';require(len(values[name])==len(reference[name])==28,'Complete terminal grid')
  for actual_value,expected in zip(values[name],reference[name]):
   require(math.isfinite(actual_value) and math.isfinite(expected),'Nonfinite terminal current')
   errors.append(abs(actual_value-expected)/(atol+rtol*abs(expected)))
 require(max(errors)<=1,'Inherited current comparison failed')
 return {'points':28,'terminal_comparisons':112,'maximum_normalized_error':max(errors),'scope':'FINITE_RAW_COMPARISON_ONLY_NOT_STANDALONE_ACCEPTANCE'}

def regenerated_deck(native,saved,source_pdk,model_files,modules):
 """Rebuild ordinary application deck in disposable storage, never a simulator."""
 import tempfile,shutil
 from icstudio.model import clone
 from icstudio.native_analysis import deck
 from icstudio.pdks import stage_model_deck
 project=clone(native['project']);expected=clone(saved)
 # Only managed runtime injection and the locked PDK relocation are permitted.
 expected['simulation_runtime']=project['simulation_runtime']
 expected['pdk']['package_root']=project['pdk']['package_root']
 require(project==expected,'Native project differs from saved Studio project')
 require(project['pdk']['package_lock']['files']=={n:h for n,h in model_files.items() if n!='package.json'},'PDK model lock differs')
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp);pdk=root/'pdk';output=root/'output';output.mkdir();pdk.mkdir()
  for name,h in model_files.items():
   source=confined(source_pdk,name);require(sha(source)==h,'Authenticated model source differs')
   target=pdk/PurePosixPath(name);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
  project['pdk']['package_root']=str(pdk)
  text,_=deck(project,native['cell'],native['settings'],output)
  text=stage_model_deck(project['pdk'],text,output)
  require('ICSTUDIO_DIODE_GEOMETRY' not in text and not native['settings'].get('diagnostic'),'Unreviewed executable compatibility/diagnostic adaptation')
  lines=text.splitlines();lines[1:1]=['.control']+[f'pre_osdi runtime-osdi/model-{i}.osdi' for i in range(len(modules))]+['.endc']
  text='\n'.join(lines)+'\n'
  files={p.relative_to(output).as_posix():p.read_bytes() for p in output.rglob('*') if p.is_file()}
 return text,files

def science_lines(text):
 """Independent exact device/options/bias check, separate from app regeneration."""
 return [x.strip() for x in text.splitlines() if x.strip().startswith(('.option ','XDUT ','VD ','VG ','VS ','VB ','.temp ','.dc '))]

def audit_native(receipt_path,contract_path,evidence_root,projects_root):
 import math
 from fractions import Fraction as F
 from scripts import read_ihp_pmos_measured_v3 as retained
 from icstudio.model import load_project
 receipt=load(receipt_path);contract=load(contract_path)
 require(contract['review_state']=='REVIEWED_FOR_EXPLICIT_NATIVE_AUTHORIZATION' and contract['host_acceptance_pending'] is False and contract['approved_managed_six_module_loading'] is True and contract['native_adapter_ready'] is True,'Native contract not independently reviewed')
 require(receipt['contract_sha256']==sha(contract_path),'Actual contract digest')
 require(receipt['authorization']=={'status':'AUTHORIZED_REVIEWED_WINDOWS_WSL_RESEARCH','contract_sha256':sha(contract_path),'runner_sha256':receipt['runner_sha256']},'Native authorization receipt differs')
 require(receipt['runner_sha256']==contract['source_files_sha256']['scripts/probe_ihp_wsl_research_app.py'],'Authorized runner differs from bound source')
 require(receipt['qualified'] is False and receipt['installed_acceptance'] is False,'Research-only native scope')
 require(receipt['status']=='EXECUTED_PENDING_INDEPENDENT_NATIVE_AUDIT' and receipt['cleanup'] in ('owned_process_stopped','no_owned_active_row') and not receipt['cleanup_errors'],'Unclean or incomplete native execution')
 require(receipt['source_before']==receipt['source_after']==contract['source_files_sha256'] and receipt['source_unchanged'] is True,'Actual source identity changed')
 require(receipt['runtime_full_before']==receipt['runtime_full_after']==contract['runtime_full_identity'],'Actual runtime lock changed')
 require(receipt['dependencies_before']==receipt['dependencies_after']==contract['host_dependencies'],'Actual host dependency bytes differ')
 require(receipt['actual_dependency_closure_before']['dependencies']==receipt['actual_dependency_closure_after']['dependencies']==contract['host_dependencies'],'Actual loaded closure differs')
 require({n:r['libraries'] for n,r in receipt['actual_dependency_closure_before']['rows'].items()}=={n:r['libraries'] for n,r in receipt['actual_dependency_closure_after']['rows'].items()},'Per-module loaded closure changed')
 require(receipt['runtime_identity']==contract['runtime_identity'] and receipt['runtime_identity']['sha256']==contract['payload_archive_sha256'],'Runtime/payload join')
 root,manifest=retained.verify(evidence_root);historical=retained.audit(root)
 v=root/'measured-v3';original=v/'attempt-1';spec=load(original/'contract.json');scale=load(root/'source-aware-scaling-v1/contract.json')
 m=retained.reviewed_module(v/'scripts/ihp_pmos_measured_reference_v3.py','measurement_readback')
 reader=retained.reviewed_module(v/'scripts/audit_sky130_li_linked.py','raw_readback').raw
 atol=spec['numerical_consistency']['absolute_current_tolerance_a'];rtol=spec['numerical_consistency']['relative_tolerance']
 require(contract['evidence_manifest_sha256']==retained.MANIFEST_SHA,'Immutable source evidence differs')
 require([(x['route'],x['gate_index']) for x in receipt['runs']]==list(SELECTION),'Complete ordered twenty-job selection')
 project_record=load(Path(projects_root)/'projects.json');require(sha(Path(projects_root)/'projects.json')==contract['projects_manifest_sha256'],'Project manifest differs')
 projects={x['case']:x for x in project_record['cases']}
 modules=[tuple(x) for x in contract['managed_modules']]
 executables={'/opt/icstudio/research/ihp-pmos-v3/measured-v3/attempt-1/engine/runtime/ngspice'}|{'/opt/icstudio/osdi/ihp-sg13g2/'+n for n,h in modules}
 for field in ('actual_dependency_closure_before','actual_dependency_closure_after'):
  require(set(receipt[field]['rows'])==executables,'All seven loader closures required')
  joined={}
  for row in receipt[field]['rows'].values():
   require(bool(row['libraries']),'Empty loader closure')
   for n,h in row['libraries'].items():
    require(contract['host_dependencies'].get(n)==h,'Unreviewed loaded dependency');joined[n]=h
  require(joined==contract['host_dependencies'],'Incomplete loaded closure')
 require(len(modules)==6 and {n for n,h in modules}=={'psp103.osdi','psp103_nqs.osdi','r3_cmc.osdi','mosvar.osdi','cap_cmomi.osdi','cap_cmomf.osdi'},'Six module set')
 for name,h in modules:
  require(sha(v/'osdi-inputs'/name)==h,'Immutable managed module differs')
  from scripts.ihp_wsl_elf_symbols import elf_symbols
  symbols=elf_symbols(v/'osdi-inputs'/name);require(symbols['needed']==[],'Unreviewed module dependencies')
  for field in ('actual_dependency_closure_before','actual_dependency_closure_after'):
   row=receipt[field]['rows']['/opt/icstudio/osdi/ihp-sg13g2/'+name]
   require(row['resolution']=='NO_DT_NEEDED_USES_AUTHENTICATED_ENGINE_SCOPE','Incorrect module loader classification')
   require(row['symbol_resolution']=={'strong_undefined_count':len(symbols['undefined']),'weak_undefined':symbols['weak_undefined'],'needed':[],'scope':'STATIC_ENGINE_AND_AUTHENTICATED_DEPENDENCY_EXPORT_JOIN_NOT_SELF_CONTAINED'},'Module symbol proof differs')
 currents={route:[] for route in m.ROUTES};axes={route:[] for route in m.ROUTES};comparisons=[]
 evidence_directory=Path(receipt_path).with_name(Path(receipt_path).name.removesuffix('.launch.json'))
 def inventory():
  return {p.relative_to(evidence_directory).as_posix():sha(regular(p)) for p in evidence_directory.rglob('*') if p.is_file()}
 require(inventory()==receipt['files'],'Full native attempt inventory differs')
 for row in receipt['runs']:
  key=f"{row['route']}-{row['gate_index']}";job=Path(row['job_directory']);savedpath=Path(row['saved_project'])
  require(job.resolve().is_relative_to(evidence_directory.resolve()) and savedpath.resolve().is_relative_to(evidence_directory.resolve()),'Case path escapes retained attempt')
  require(row['state']=='Complete' and sha(savedpath)==row['saved_project_sha256'],'Saved Studio case differs')
  prepared_project=Path(projects_root)/projects[key]['project'];require(sha(prepared_project)==contract['project_files_sha256'][key]==projects[key]['sha256'],'Reviewed project differs')
  saved=load_project(savedpath);require(saved==load_project(prepared_project),'Saved and reopened project changed')
  audit_job(job,receipt['runtime_identity'],modules);native=load(job/'physical-backend-input.json')
  require(native['cell']==saved['top'],'Selected top/cell differs')
  settings=dict(native['settings']);settings.pop('tools',None);settings.pop('managed_osdi',None)
  require(settings==saved['analysis'],'Native analysis differs')
  expected,staged=regenerated_deck(native,saved,original/'pdk',spec['model_files'],modules)
  require((job/'input.cir').read_text()==expected,'Regenerated full native deck differs')
  require({p.relative_to(job).as_posix() for p in (job/'pdk-models').glob('*') if p.is_file()}=={n for n in staged if n.startswith('pdk-models/')},'Staged model set differs')
  for name,data in staged.items():require(confined(job,name).read_bytes()==data,'Translated model/source bytes differ')
  original_deck=(original/'runs'/key/'input.cir').read_text()
  original_lines=science_lines(original_deck)
  converted=[]
  for line in original_lines:
   if line.startswith(('VD ','VG ','VS ','VB ')):
    words=line.split();require(len(words)==4,'Original independent source syntax');line=' '.join(words[:3])+' DC '+words[3]+' AC 0'
   converted.append(line)
  require(sorted(science_lines(expected))==sorted(converted),'Independent original device/body/options/bias differs')
  import hashlib
  corner='libs.tech/ngspice/models/cornerMOSlv.lib'
  staged_corner='pdk-models/'+hashlib.sha256((corner+'\0'+spec['model_files'][corner]).encode()).hexdigest()[:24]+'.spice'
  permitted=converted+['.lib '+staged_corner+' mos_tt','.control','.endc','.end']+[f'pre_osdi runtime-osdi/model-{i}.osdi' for i in range(6)]
  active=[x.strip() for x in expected.splitlines()[1:] if x.strip() and not x.lstrip().startswith('*')]
  require(sorted(active)==sorted(permitted),'Extra native statement or changed original corner')
  log=(job/'engine.log').read_text()
  require(not re.search(r'(?im)^\s*(?:error|fatal)\b|unknown (?:parameter|model)|simulation (?:aborted|failed)|no such file|could not load|failed to load|using KLU|singular matrix|timestep too small',log),'Native diagnostic failure')
  warnings=[x.strip() for x in log.splitlines() if re.search(r'(?i)warning',x)]
  require(warnings==['Warning: m=xx on .subckt line will override multiplier m hierarchy!'],'Unexpected native warning')
  require(log.splitlines().count('Using SPARSE 1.3 as Direct Linear Solver')==1,'Original Sparse solver required')
  comparisons.append(compare_raw(job/'result.raw',original/'runs'/key/'result.raw',expected.splitlines()[0],reader,atol,rtol))
  values,axis=reader(job/'result.raw');require(set(values)<=set(['v(v-sweep)','i(vd)','i(vg)','i(vs)','i(vb)','v(d)','v(g)','v(s)','v(b)']),'Unexpected raw terminal/body aliases')
  currents[row['route']]+=[{t:-float(values['i(v'+t+')'][j]) for t in 'dgsb'} for j in range(28)];axes[row['route']]+=axis
 kcl=max(abs(sum(p.values()))/(atol+rtol*sum(abs(x) for x in p.values())) for rows in currents.values() for p in rows);require(kcl<=1,'KCL failed')
 require(scale['internal_voltage_mapping']=={'DI':'D','SI':'S','BP':'BI=B'} and scale['gmin_siemens_hex']==float(1e-12).hex(),'Immutable source-law identity')
 g=F(float.fromhex(scale['gmin_siemens_hex']));errors=[]
 for i in range(140):
  require(axes['nominal'][i]==axes['multiplicity-2'][i],'Multiplicity grid differs')
  d=g*F(axes['nominal'][i]);offset={'d':d,'g':F(0),'s':F(0),'b':-d}
  for t in 'dgsb':
   nominal=F(currents['nominal'][i][t]);actual=F(currents['multiplicity-2'][i][t]);errors.append(float(abs(actual-(2*nominal-offset[t]))/(F(atol)+F(rtol)*abs(2*nominal))))
 require(max(errors)<=1,'Source-aware multiplicity failed')
 residuals=m.residuals(m.parse((original/'measurement.mdm').read_bytes()),currents['nominal'])
 require(len(residuals['points'])==140,'Complete measured residual set')
 require(inventory()==receipt['files'],'Native outputs changed during readback');retained.verify(root)
 return dict(status='FINITE_WINDOWS_WSL_RESEARCH_READBACK',qualified=False,installed_acceptance=False,independent_calibration=False,jobs=20,points=560,terminal_comparisons=2240,max_normalized_comparison=max(x['maximum_normalized_error'] for x in comparisons),kcl_max_normalized=kcl,source_aware_max_normalized=max(errors),measured_residuals=residuals,historical_research_status=historical['status'])
