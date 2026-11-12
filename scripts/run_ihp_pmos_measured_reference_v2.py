"""Fresh local diagnostic; refuses unreviewed engine/model-runtime identities."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ihp_pmos_measured_reference_v2 as m
from scripts import audit_ihp_pmos_measured_reference_v2 as a
from scripts import stage_linux_ngspice as stage

def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')

def dependencies(engine):
    p=subprocess.run(['ldd',str(engine)],capture_output=True,text=True,check=True)
    m.require('not found' not in p.stdout,'Missing dependency')
    return {str(Path(s).resolve()):m.sha(s) for line in p.stdout.splitlines() for s in line.split() if s.startswith('/') and Path(s).is_file()}

def execute(cmd,cwd,env,log_path,timeout=90):
    """Stream output directly so killed/timed-out native processes remain auditable."""
    with Path(log_path).open('w') as log:
        return subprocess.run(cmd,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,text=True,timeout=timeout)

def run(out,osdi):
    m.require(m.sha(ROOT/a.CONTRACT)==a.CONTRACT_SHA,'Contract identity changed')
    spec=json.loads((ROOT/a.CONTRACT).read_text())
    m.require(spec['runtime']['osdi'] is not None,'BLOCKED: authenticated PSP103 runtime not reviewed')
    m.require(m.sha(osdi)==spec['runtime']['osdi']['sha256'],'Wrong PSP103 runtime')
    nqs=Path(osdi).parent/'psp103_nqs.osdi'
    m.require(m.sha(nqs)==spec['runtime']['nqs_osdi']['sha256'],'Wrong PSP NQS runtime')
    m.require(sys.platform=='linux','Profile is native Linux only')
    out=Path(out).resolve();m.require(not out.exists() and not any(c.isspace() for c in str(out)),'Fresh whitespace-free output required');out.mkdir(parents=True)
    r={'root':str(out),'nonce':uuid.uuid4().hex,'status':'RUNNING','qualified':False,'runs':[],'sources':{n:m.sha(ROOT/n) for n in a.SOURCES}}
    write(out/'run.json',r)
    try:
        shutil.copyfile(ROOT/a.CONTRACT,out/'contract.json');shutil.copyfile(m.DATA,out/'measurement.mdm')
        provenance=m.DATA.parent/'runtime-provenance'
        for name,h in spec['runtime']['provenance_files'].items():
            m.require(m.sha(provenance/name)==h,'Runtime provenance changed')
            target=out/'runtime-provenance'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(provenance/name,target)
        for name,h in spec['solver_protocol']['reference_files'].items():
            source=m.DATA.parent/'solver-reference'/name;m.require(m.sha(source)==h,'Solver reference changed')
            target=out/'solver-reference'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        for n in a.SOURCES:
            p=out/'sources'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
        pdk=ROOT/'icstudio/assets/pdks/ihp-sg13g2'
        for n,h in spec['model_files'].items():
            m.require(m.sha(pdk/n)==h,'Model changed');p=out/'pdk'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(pdk/n,p)
        (out/'runtime').mkdir();shutil.copyfile(osdi,out/'runtime/psp103.osdi');shutil.copyfile(nqs,out/'runtime/psp103_nqs.osdi')
        engine=stage.stage(output=out/'engine');r['dependencies_before']=dependencies(engine)
        m.require(r['dependencies_before']==spec['runtime']['dependencies'],'Unreviewed actual dependencies')
        r['osdi_dependencies_before']={n:dependencies(out/'runtime'/n) for n in ('psp103.osdi','psp103_nqs.osdi')}
        m.require(r['osdi_dependencies_before']==spec['runtime']['osdi_dependencies'],'Unreviewed OSDI dependencies')
        for route,i in a.selection():
            folder=out/'runs'/f'{route}-{i}';folder.mkdir(parents=True)
            text=m.deck(r['nonce'],route,str(m.GATES[i])).replace('\n.lib','\n.control\npre_osdi runtime/psp103.osdi\npre_osdi runtime/psp103_nqs.osdi\n.endc\n.lib',1)
            (folder/'input.cir').write_text(text)
            cmd=[str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(folder/'result.raw'),str(folder/'input.cir')]
            env={'PATH':'/usr/bin:/bin','HOME':str(out),'LANG':'C','LC_ALL':'C','TZ':'UTC','SPICE_SCRIPTS':str(engine.parent),'OMP_NUM_THREADS':'1'}
            row={'route':route,'gate_index':i,'returncode':None,'command':cmd,'cwd':str(out),'environment':env}
            r['runs'].append(row);write(out/'run.json',r)
            try:
                p=execute(cmd,out,env,folder/'console.log')
            except subprocess.TimeoutExpired:
                row['timed_out']=True;write(out/'run.json',r);raise
            row['returncode']=p.returncode;write(out/'run.json',r)
            m.require(p.returncode==0,'Native failure: '+route)
            a.clean_log((folder/'console.log').read_text())
        r['dependencies_after']=dependencies(engine)
        r['osdi_dependencies_after']={n:dependencies(out/'runtime'/n) for n in ('psp103.osdi','psp103_nqs.osdi')}
        r['status']='EXECUTED_PENDING_AUDIT'
    except Exception as exc:r.update(status='FAILED',error=str(exc));raise
    finally:
        r['files']={p.relative_to(out).as_posix():m.sha(p) for p in out.rglob('*') if p.is_file() and p not in (out/'run.json',out/'audit.json')};write(out/'run.json',r)
    result=a.audit(out);write(out/'audit.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--osdi',type=Path,required=True);x=p.parse_args();run(x.out,x.osdi)
