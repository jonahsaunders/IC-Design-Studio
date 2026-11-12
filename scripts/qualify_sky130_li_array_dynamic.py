"""New finite dynamic linkage, using authenticated historical extracted arrays.

Does not execute extraction, change source models, qualify limits or satisfy
installed gates. Every output directory is fresh; failed runs remain retained.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import audit_sky130_li_array_dynamic as audit
from scripts import stage_linux_ngspice as runtime
CONTRACT='docs/qualification/sky130-li-array-dynamic-v1.json'
CONTRACT_SHA='d010749d9278e3dcd99763af17d6f0850b1d5fb82c299c76875c3cf58193c055'


def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2)+'\n')


def jobs():
    for case in audit.CASES:
        for mode in ('tran','noise'):
            for kind in ('application','native','analytic'):yield case,mode,kind,None
    for fault in ('remove-one-unit','one-unit-width-3um','load-capacitance-2nF'):
        for mode in ('tran','noise'):yield 'l1-m3-r0',mode,'native',fault


def circuit_text(original,fault):
    lines=original.splitlines()
    indices=[i for i,s in enumerate(lines) if s.startswith('R')]
    if fault=='remove-one-unit':del lines[indices[-1]]
    elif fault=='one-unit-width-3um':lines[indices[-1]]=lines[indices[-1]].replace('w=2','w=3')
    return '\n'.join(lines)+'\n' if fault in ('remove-one-unit','one-unit-width-3um') else original


def deck(spec,nonce,name,mode,kind,count,circuit):
    coeff=spec['model_equation'];dt=spec['selection']['temperature_c']-coeff['tnom_c']
    r=coeff['rsh_ohm_sq']*5e-6/(2e-6+coeff['width_correction_m'])*(1+coeff['tc1']*dt+coeff['tc2']*dt*dt)/count
    model_lines=json.loads((circuit.parent.parent.parent/'historical'/audit.ELECTRICAL/'selected-model-lines.json').read_text())['tt']
    lines=[f'* LI-array-dynamic-v1 {nonce} {name}',model_lines,'.option reltol=1e-8 abstol=1e-16 vntol=1e-13 method=gear','.temp 27',
           'VDRIVE input 0 PWL(0 0 1n .001 100n .001) AC 1',
           f'RTEST input output {r:.17g}' if kind=='analytic' else f'.include {circuit.as_posix()}']
    if kind!='analytic':lines+=['XTEST input output coupon']
    lines+=['RLOAD output 0 10','CLOAD output 0 '+('2n' if 'load-capacitance-2nF' in name else '1n')]
    if mode=='tran':lines+=['.save v(input) v(output) i(vdrive)','.tran 50p 100n 0 50p']
    else:lines+=['.noise V(output) VDRIVE dec 20 1k 1g']
    return '\n'.join(lines+['.end'])+'\n'


def dependencies(engine):
    p=subprocess.run(['ldd',str(engine)],capture_output=True,text=True,check=True)
    audit.require('not found' not in p.stdout,'Missing engine dependency')
    values={}
    for line in p.stdout.splitlines():
        for token in line.split():
            path=Path(token)
            if token.startswith('/') and path.is_file():values[token]={'resolved':str(path.resolve()),'sha256':audit.sha(path)}
    return values,p.stdout


def run(archive,out):
    out=Path(out).resolve();audit.require(not out.exists() and not any(c.isspace() for c in str(out)),'Use fresh whitespace-free output')
    audit.require(audit.sha(ROOT/CONTRACT)==CONTRACT_SHA,'Dynamic contract changed')
    spec=json.loads((ROOT/CONTRACT).read_text());out.mkdir(parents=True)
    record={'schema':1,'status':'RUNNING','qualified':False,'installed_acceptance':False,'fresh_physical_acceptance':False,'scope':spec['scope'],
            'nonce':uuid.uuid4().hex,'output_root':str(out),'historical_archive':str(Path(archive).resolve()),'historical_archive_sha256':audit.ARCHIVE_SHA,
            'contract_sha256':CONTRACT_SHA,'runs':[]}
    write(out/'run.json',record)
    try:
        recovery,payload=audit.archive_inputs(archive)
        for name,data in payload.items():
            p=out/'historical'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        write(out/'recovery.json',recovery)
        engine=runtime.stage(output=out/'engine')
        dep,listing=dependencies(engine);audit.require(dep==spec['runtime']['actual_host_dependencies'],'Unreviewed actual host dependencies')
        write(out/'dependencies-before.json',dep);(out/'ldd-before.txt').write_text(listing)
        shutil.copyfile(ROOT/CONTRACT,out/'contract.json')
        sources=[CONTRACT,'scripts/qualify_sky130_li_array_dynamic.py','scripts/audit_sky130_li_array_dynamic.py','scripts/stage_linux_ngspice.py','scripts/audit_sky130_li_linked.py','tests/test_sky130_li_array_dynamic.py']
        for name in sources:
            p=out/'source'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
        record['source_files']={n:audit.sha(ROOT/n) for n in sources}
        (out/'home').mkdir();(out/'tmp').mkdir()
        env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TZ':'UTC','HOME':str(out/'home'),'TMPDIR':str(out/'tmp'),
             'SPICE_SCRIPTS':str(engine.parent),'OMP_NUM_THREADS':'1'}
        cwd=out/'historical'/audit.ELECTRICAL
        for case,mode,kind,fault in jobs():
            name=f'{case}-{mode}-{kind}'+('-'+fault if fault else '');folder=out/'runs'/name;folder.mkdir(parents=True)
            count=recovery['cases'][case]['multiplicity'];circuit=folder/'circuit.spice'
            if kind!='analytic':
                source=out/'historical'/recovery['cases'][case]['files'][kind+'_normalized']['member']
                circuit.write_text(circuit_text(source.read_text(),fault))
            else:circuit.write_text('* analytical lumped reference; no physical extraction claimed\n')
            text=deck(spec,record['nonce'],name,mode,kind,count,circuit);(folder/'input.cir').write_text(text)
            cmd=[str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(folder/'result.raw'),str(folder/'input.cir')]
            row={'name':name,'case':case,'analysis':mode,'kind':kind,'count':count,'fault':fault,'command':cmd,'cwd':str(cwd),'environment':env,
                 'raw':f'runs/{name}/result.raw','deck':f'runs/{name}/input.cir','circuit':f'runs/{name}/circuit.spice','log':f'runs/{name}/console.log'}
            record['runs'].append(row);write(out/'run.json',record)
            p=subprocess.run(cmd,cwd=cwd,env=env,capture_output=True,text=True,timeout=90);log=p.stdout+p.stderr;(folder/'console.log').write_text(log);row['returncode']=p.returncode
            audit.require(p.returncode==0 and not re.search(r'error|unknown parameter|aborted',log,re.I),'Native process failed: '+name)
            row['observation']=audit.observe(folder/'result.raw',mode,count)
            audit.require(row['observation']['passed']==(fault is None),'Unexpected dynamic result: '+name)
            write(out/'run.json',record);print(name,row['observation']['maximum_normalized_error'],flush=True)
        after,_=dependencies(engine);audit.require(after==dep,'Host runtime changed');write(out/'dependencies-after.json',after);runtime.verify(engine.parent.parent)
        audit.require(record['source_files']=={n:audit.sha(ROOT/n) for n in sources},'Source changed during execution')
        record['status']='PASS'
    except Exception as exc:
        record.update(status='FAIL',error=str(exc));write(out/'run.json',record);raise
    finally:
        record['files']={p.relative_to(out).as_posix():audit.sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p!=out/'run.json'}
        write(out/'run.json',record)
    result=audit.audit(out);write(out/'audit.json',result);return record

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args();run(args.archive,args.out)
