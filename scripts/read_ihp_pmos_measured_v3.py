"""Portable read-only audit of exact retained research evidence, not a simulator.
Accepts an extracted evidence root; never rewrites historical paths or contracts.
"""
import argparse,hashlib,json,math,re,types,statistics,ast,sys,stat
from fractions import Fraction as F
from pathlib import Path,PurePosixPath
MANIFEST_SHA='8f583f2a0002a17fdb268502e53d269cee73d633fe3aff1a9311f2ead0125a87'
def is_linked(path):
 try:s=Path(path).lstat()
 except FileNotFoundError:return False
 return stat.S_ISLNK(s.st_mode) or bool(getattr(s,'st_file_attributes',0)&0x400)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(ok,message):
 if not ok:raise ValueError(message)
def verify(root):
 root=Path(root).absolute()
 for component in (root,*root.parents):
  require(not is_linked(component),'Linked evidence root')
 require(sha(root/'MANIFEST.json')==MANIFEST_SHA,'Wrong immutable evidence manifest')
 manifest=json.loads((root/'MANIFEST.json').read_text())
 expected=manifest['files'];found=set()
 for p in root.rglob('*'):
  require(not is_linked(p),'Linked evidence')
  if p.is_file():
   n=p.relative_to(root).as_posix()
   if n=='MANIFEST.json':continue
   require(n in expected,'Extra evidence: '+n)
   require(p.stat().st_size==expected[n]['bytes'] and sha(p)==expected[n]['sha256'],'Changed evidence: '+n);found.add(n)
 require(found==set(expected),'Missing evidence')
 return root,manifest
def reviewed_module(path,name):
 # Called only after EVERY byte is authenticated against the fixed manifest.
 # compile/exec avoids generating __pycache__ inside immutable evidence.
 data=path.read_bytes();tree=ast.parse(data)
 allowed={'argparse','bisect','hashlib','json','math','pathlib','re','decimal'}
 for node in ast.walk(tree):
  if isinstance(node,ast.Import):require(all(n.name in allowed for n in node.names),'Unexpected historical import')
  elif isinstance(node,ast.ImportFrom):require(node.level==0 and node.module in allowed,'Unexpected historical import')
 m=types.ModuleType(name);m.__file__=str(path)
 exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__)
 return m
def audit(evidence_root):
 root,manifest=verify(evidence_root);v=root/'measured-v3';run=v/'attempt-1';side=root/'source-aware-scaling-v1'
 r=json.loads((run/'run.json').read_text());spec=json.loads((run/'contract.json').read_text());c=json.loads((side/'contract.json').read_text())
 require(sha(run/'contract.json')==c['original_contract_sha256'] and sha(run/'run.json')==c['original_run_sha256'],'Original identities')
 require(sha(v/'readback-failure.json')==c['original_failure_sha256'],'Original rejection changed')
 require(r['status']=='EXECUTED_PENDING_AUDIT' and r['qualified'] is False,'Original status')
 require(all(spec[k] is False for k in ['qualified','independent_calibration','installed_acceptance']),'Qualification claim')
 m=reviewed_module(v/'scripts/ihp_pmos_measured_reference_v3.py','retained_measurement')
 raw=reviewed_module(v/'scripts/audit_sky130_li_linked.py','retained_raw').raw
 expected_selection=[(route,i) for route in m.ROUTES for i in range(5)]
 require([(x['route'],x['gate_index']) for x in r['runs']]==expected_selection,'Selection changed')
 # Historical absolute paths are evidence, not paths opened on this computer.
 historic=PurePosixPath(r['root'])
 require(str(historic)==c['original_root'] and historic.is_absolute(),'Historical root binding')
 require(r['dependencies_before']==r['dependencies_after']==spec['runtime']['dependencies'],'Engine dependency identity')
 require(r['osdi_dependencies_before']==r['osdi_dependencies_after']==spec['runtime']['osdi_dependencies'],'Module dependency identity')
 require(sha(run/'engine/runtime/ngspice')==spec['runtime']['engine_sha256'],'Engine identity')
 require(sha(run/'runtime/psp103.osdi')==spec['runtime']['osdi']['sha256'],'Module identity')
 require(sha(run/'runtime/psp103_nqs.osdi')==spec['runtime']['nqs_osdi']['sha256'],'NQS identity')
 for n,h in r['files'].items():require(sha(run/n)==h,'Historical file inventory: '+n)
 for n,h in r['sources'].items():require(sha(v/n)==h==sha(run/'sources'/n),'Historical source: '+n)
 for n,h in spec['model_files'].items():require(sha(run/'pdk'/n)==h,'Model source')
 for n,h in c['sources'].items():require(sha(side/n)==h,'Source-law proof')
 output={route:[] for route in m.ROUTES};axes={route:[] for route in m.ROUTES}
 for row in r['runs']:
  route,i=row['route'],row['gate_index'];folder=run/'runs'/f'{route}-{i}'
  expected=m.deck(r['nonce'],route,str(m.GATES[i])).replace('\n.lib','\n.control\npre_osdi runtime/psp103.osdi\npre_osdi runtime/psp103_nqs.osdi\n.endc\n.lib',1)
  require((folder/'input.cir').read_text()==expected,'Deck/source settings changed')
  historical_folder=historic/'runs'/f'{route}-{i}';engine=historic/'engine/runtime/ngspice'
  command=[str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(historical_folder/'result.raw'),str(historical_folder/'input.cir')]
  env={'PATH':'/usr/bin:/bin','HOME':str(historic),'LANG':'C','LC_ALL':'C','TZ':'UTC','SPICE_SCRIPTS':str(engine.parent),'OMP_NUM_THREADS':'1'}
  require(row['command']==command and row['cwd']==str(historic) and row['environment']==env,'Native invocation identity')
  require(row['returncode']==0 and not row.get('timed_out') and row['deadline_seconds']==90,'Incomplete execution')
  log=(folder/'console.log').read_text()
  require(not re.search(r'(?im)^\s*(?:error|fatal)\b|unknown (?:parameter|model)|simulation (?:aborted|failed)|no such file|could not load|failed to load|using KLU|singular matrix|timestep too small',log),'Native diagnostic failure')
  text=(folder/'result.raw').read_text()
  require(text.splitlines()[0].lower()==('Title: '+expected.splitlines()[0]).lower() and 'Command: ngspice-47,' in text,'Raw title/engine')
  values,axis=raw(folder/'result.raw')
  require(len(axis)==28 and all(abs(x+j/20)<1e-12 for j,x in enumerate(axis)),'Raw grid')
  require(set(values)=={'v(v-sweep)','i(vd)','i(vg)','i(vs)','i(vb)'},'Terminal set')
  points=[{t:-float(values['i(v'+t+')'][j]) for t in 'dgsb'} for j in range(28)]
  require(all(math.isfinite(x) for p in points for x in p.values()),'Nonfinite currents')
  output[route]+=points;axes[route]+=axis
 atol=spec['numerical_consistency']['absolute_current_tolerance_a'];rtol=spec['numerical_consistency']['relative_tolerance']
 naive=max(abs(output['multiplicity-2'][i][t]-2*output['nominal'][i][t])/(atol+rtol*abs(2*output['nominal'][i][t])) for i in range(140) for t in 'dgsb')
 kcl=max(abs(sum(p.values()))/(atol+rtol*sum(abs(x) for x in p.values())) for ps in output.values() for p in ps)
 prior,prior_axis=raw(run/'solver-reference/result.raw')
 require(len(prior_axis)==28 and all(abs(x+i/20)<1e-12 for i,x in enumerate(prior_axis)),'Prior grid')
 overlap=max(abs(output['nominal'][i][t]+prior['i(v'+t+')'][i])/(atol+rtol*abs(prior['i(v'+t+')'][i])) for i in range(28) for t in 'dgsb')
 require(naive>1 and kcl<=1 and overlap<=1,'Historical rejection classification changed')
 # Source-law identity is manifest-bound, not inferred/fitted from these currents.
 require(c['internal_voltage_mapping']=={'DI':'D','SI':'S','BP':'BI=B'} and c['gmin_siemens_hex']==float(1e-12).hex(),'Unsupported source-law context')
 g=F(float.fromhex(c['gmin_siemens_hex']));errors=[]
 for i in range(140):
  require(axes['nominal'][i]==axes['multiplicity-2'][i],'Control bias mismatch')
  d=g*F(axes['nominal'][i]);offset={'d':d,'g':F(0),'s':F(0),'b':-d}
  for t in 'dgsb':
   nominal=F(output['nominal'][i][t]);actual=F(output['multiplicity-2'][i][t])
   errors.append(float(abs(actual-(2*nominal-offset[t]))/(F(atol)+F(rtol)*abs(2*nominal))))
 source_scale=max(errors)
 require(source_scale<=1,'Source-aware consistency failed')
 residuals=m.residuals(m.parse((run/'measurement.mdm').read_bytes()),output['nominal'])
 original=json.loads((v/'readback-failure.json').read_text())
 require(residuals==original['residuals'],'Unconditional measured residuals changed')
 perturb={}
 for route in ('width-5um','drain-source-swapped'):
  norm=max(abs(output[route][i][t]-output['nominal'][i][t])/(atol+rtol*abs(output['nominal'][i][t])) for i in range(140) for t in 'dgsb')
  perturb[route]={'maximum_normalized_difference':norm,'observed_distinguishable_from_nominal':norm>1,'universal_detection_asserted':False}
 summary={}
 for t in 'dgsb':
  vals=[p['terminals'][t] for p in residuals['points']]
  absolute=[x['absolute_residual_a'] for x in vals];relative=[abs(x['signed_relative_residual']) for x in vals if x['signed_relative_residual'] is not None]
  summary[t]=dict(points=140,max_absolute_residual_a=max(absolute),median_absolute_residual_a=statistics.median(absolute),nonzero_measured_count=len(relative),zero_measured_count=140-len(relative),max_absolute_relative_residual=max(relative) if relative else None,median_absolute_relative_residual=statistics.median(relative) if relative else None,zero_measured_max_absolute_residual_a=max([x['absolute_residual_a'] for x in vals if x['measured_a']==0],default=None))
 require(summary==json.loads((v/'measured-comparison-summary.json').read_text())['terminals'],'Measured summary changed')
 return dict(status='RETAINED_RESEARCH_READBACK_COMPLETE',native_jobs=20,native_points=560,new_native_runs=0,qualified=False,independent_calibration=False,installed_acceptance=False,original_numerical_audit='REJECTED_MULTIPLICITY_SCALING',original_scaling_max_normalized=naive,source_aware_consistency='PASS' if source_scale<=1 else 'FAIL',source_aware_scaling_max_normalized=source_scale,kcl_max_normalized=kcl,prior_overlap_max_normalized=overlap,perturbations=perturb,residuals=residuals,measured_comparison_summary=summary,evidence_manifest_sha256=MANIFEST_SHA,python_readback_runtime=sys.version,python_dependencies='Host Python standard library; historical readers limited to argparse,bisect,hashlib,json,math,pathlib,re,decimal',scope='Exact retained research only; no current-machine executable replay or managed/default runtime replacement.')
def write_output(evidence_root,output):
 output=Path(output).absolute()
 for component in (output,*output.parents):
  require(not is_linked(component),'Linked output path')
 require(not output.exists(),'Fresh output required')
 require(not output.is_relative_to(Path(evidence_root).absolute()),'Output must be outside immutable evidence')
 result=audit(evidence_root)
 with output.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
 return result
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('evidence_root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 write_output(a.evidence_root,a.output)
if __name__=='__main__':main()
