"""Offline exact-input audit and unconditional manufacturer-data residual report."""
import argparse
import json
import re
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ihp_pmos_measured_reference as m
from scripts.audit_sky130_li_linked import raw

CONTRACT_SHA='7891995d390dd80654168aefce77fab329b7d3e57454743a81f6b210deb6bb4a'
CONTRACT='docs/qualification/ihp-pmos-measured-reference-v1/contract.json'
SOURCES=(CONTRACT,'docs/qualification/ihp-pmos-measured-reference-v1/measurement.mdm','docs/qualification/ihp-pmos-measured-reference-v1/UPSTREAM-README.md','docs/qualification/ihp-pmos-measured-reference-v1/LICENSE','scripts/ihp_pmos_measured_reference.py','scripts/run_ihp_pmos_measured_reference.py','scripts/audit_ihp_pmos_measured_reference.py','scripts/audit_sky130_li_linked.py','scripts/stage_linux_ngspice.py','tests/test_ihp_pmos_measured_reference.py')

def clean_log(text):
    m.require(not re.search(r'(?im)^\s*(?:error|fatal|fatal error)\b|unknown (?:parameter|model)|simulation (?:aborted|failed)|no such file|could not load|failed to load',text),'Native diagnostic error')

def selection(): return [(r,i) for r in m.ROUTES for i in range(5)]

def validate_selection(rows):
    actual=[(r['route'],r['gate_index']) for r in rows]
    m.require(actual==selection(),'Missing/duplicate/reordered route')

def inventory(root, files):
    found=set()
    for p in root.rglob('*'):
        m.require(not p.is_symlink() and not (hasattr(p,'is_junction') and p.is_junction()),'Linked evidence')
        if p.is_file() and p not in (root/'run.json',root/'audit.json'):
            name=p.relative_to(root).as_posix();found.add(name)
            m.require(files.get(name)==m.sha(p),'Changed or extra evidence: '+name)
    m.require(found==set(files),'Missing evidence')

def audit(root):
    root=Path(root).resolve();r=json.loads((root/'run.json').read_text())
    m.require(r['root']==str(root),'Different execution root')
    inventory(root,r['files']);validate_selection(r['runs'])
    m.require(m.sha(root/'contract.json')==CONTRACT_SHA==m.sha(ROOT/CONTRACT),'Contract identity changed')
    spec=json.loads((root/'contract.json').read_text())
    m.require(spec['qualified'] is False and spec['independent_calibration'] is False and spec['installed_acceptance'] is False,'Qualification claim changed')
    m.require(r['status']=='EXECUTED_PENDING_AUDIT' and r['qualified'] is False,'Run status/qualification changed')
    m.require(spec==json.loads((ROOT/CONTRACT).read_text()),'Contract mismatch')
    m.require(spec['runtime']['osdi'] is not None,'Unreviewed OSDI runtime')
    for name,h in spec['runtime']['provenance_files'].items():
        m.require(m.sha(root/'runtime-provenance'/name)==h,'Runtime provenance changed')
    profile=json.loads((root/'runtime-provenance/profile.json').read_text())
    m.require(m.sha(root/'runtime-provenance/profile.json')==spec['runtime']['provenance_profile_sha256'],'Wrong runtime profile')
    for name,h in profile['psp103']['source_files'].items():
        m.require(spec['model_files']['libs.tech/verilog-a/'+name]==h,'PSP compiled source mismatch')
    for n in SOURCES:m.require(r['sources'][n]==m.sha(ROOT/n)==m.sha(root/'sources'/n),'Source changed')
    for n,h in spec['model_files'].items():m.require(m.sha(root/'pdk'/n)==h,'Model changed')
    from scripts import stage_linux_ngspice
    stage_linux_ngspice.verify(root/'engine')
    m.require(m.sha(root/'engine/runtime/ngspice')==spec['runtime']['engine_sha256'],'Engine changed')
    m.require(m.sha(root/'runtime/psp103.osdi')==spec['runtime']['osdi']['sha256'],'OSDI changed')
    m.require(m.sha(root/'runtime/psp103_nqs.osdi')==spec['runtime']['nqs_osdi']['sha256'],'NQS module changed')
    build=json.loads((root/'runtime-provenance/osdi/build.json').read_text())
    nqs=next(v for v in build['models'] if v['output']=='psp103_nqs.osdi')
    m.require(nqs['sha256']==spec['runtime']['nqs_osdi']['sha256'],'NQS build mismatch')
    for name,h in nqs['dependencies'].items():m.require(spec['model_files']['libs.tech/verilog-a/'+name]==h,'NQS source mismatch')
    m.require(r['dependencies_before']==r['dependencies_after']==spec['runtime']['dependencies'],'Runtime dependencies changed')
    m.require(r['osdi_dependencies_before']==r['osdi_dependencies_after']==spec['runtime']['osdi_dependencies'],'OSDI dependencies changed')
    measured=m.parse((root/'measurement.mdm').read_bytes())
    output={route:[] for route in m.ROUTES}
    for row in r['runs']:
        route,i=row['route'],row['gate_index'];folder=root/'runs'/f'{route}-{i}'
        expected=m.deck(r['nonce'],route,str(m.GATES[i]))
        expected=expected.replace('\n.lib','\n.control\npre_osdi runtime/psp103.osdi\npre_osdi runtime/psp103_nqs.osdi\n.endc\n.lib',1)
        m.require((folder/'input.cir').read_text()==expected,'Deck changed')
        engine=root/'engine/runtime/ngspice'
        command=[str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(folder/'result.raw'),str(folder/'input.cir')]
        m.require(row['command']==command and row['cwd']==str(root),'Changed native invocation')
        expected_env={'PATH':'/usr/bin:/bin','HOME':str(root),'LANG':'C','LC_ALL':'C','TZ':'UTC','SPICE_SCRIPTS':str(engine.parent),'OMP_NUM_THREADS':'1'}
        m.require(row['environment']==expected_env,'Changed native environment')
        m.require(row['returncode']==0,'Native failure')
        clean_log((folder/'console.log').read_text())
        text=(folder/'result.raw').read_text()
        m.require(text.splitlines()[0].lower()==('Title: '+expected.splitlines()[0]).lower(),'Wrong raw nonce/route')
        m.require('Command: ngspice-47,' in text,'Wrong raw engine')
        data,axis=raw(folder/'result.raw')
        m.require(len(axis)==28 and all(abs(v+j/20)<1e-12 for j,v in enumerate(axis)),'Raw bias grid')
        m.require(set(data)=={'v(v-sweep)','i(vd)','i(vg)','i(vs)','i(vb)'},'Raw terminal channels')
        output[route]+=[{t:-float(data['i(v'+t+')'][j]) for t in ('d','g','s','b')} for j in range(28)]
    for name,h in spec['solver_protocol']['reference_files'].items():m.require(m.sha(root/'solver-reference'/name)==h,'Solver reference changed')
    prior_data,prior_axis=raw(root/'solver-reference/result.raw')
    m.require(len(prior_axis)==28 and all(abs(v+j/20)<1e-12 for j,v in enumerate(prior_axis)),'Prior solver grid')
    controls=spec['numerical_consistency'];atol=controls['absolute_current_tolerance_a'];rtol=controls['relative_tolerance']
    scale=max(abs(output['multiplicity-2'][i][t]-2*output['nominal'][i][t])/(atol+rtol*abs(2*output['nominal'][i][t])) for i in range(140) for t in ('d','g','s','b'))
    kcl=max(abs(sum(row.values()))/(atol+rtol*sum(abs(v) for v in row.values())) for rows in output.values() for row in rows)
    overlap=max(abs(output['nominal'][i][t]+prior_data['i(v'+t+')'][i])/(atol+rtol*abs(prior_data['i(v'+t+')'][i])) for i in range(28) for t in ('d','g','s','b'))
    m.require(scale<=1 and kcl<=1 and overlap<=1,'Numerical interface consistency failed')
    perturbations={}
    for route in ('width-5um','drain-source-swapped'):
        absolute=max(abs(output[route][i][t]-output['nominal'][i][t]) for i in range(140) for t in ('d','g','s','b'))
        normalized=max(abs(output[route][i][t]-output['nominal'][i][t])/(atol+rtol*abs(output['nominal'][i][t])) for i in range(140) for t in ('d','g','s','b'))
        perturbations[route]={'maximum_absolute_current_difference_a':absolute,'maximum_normalized_difference':normalized,'observed_distinguishable_from_nominal':normalized>1,'universal_detection_asserted':False}
    return {'status':'MEASURED_REFERENCE_DIAGNOSTIC_COMPLETE','qualified':False,'independent_calibration':False,'installed_acceptance':False,'numerical_interface_checks':{'same_gate_protocol_overlap_max_normalized_error':overlap,'scaling_max_normalized_error':scale,'kcl_max_normalized_error':kcl},'interface_perturbation_observations':perturbations,'residuals':m.residuals(measured,output['nominal'])}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();print(json.dumps(audit(a.root),indent=2))
