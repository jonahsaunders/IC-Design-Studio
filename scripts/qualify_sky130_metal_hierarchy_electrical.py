"""Finite imported-hierarchy whole-network resistor integration, source only."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid
import zipfile

if '--source' in sys.argv:
    sys.path.insert(0,str(Path(sys.argv[sys.argv.index('--source')+1]).resolve()))
import icstudio
ROOT=Path(icstudio.__file__).resolve().parents[1]
CANDIDATE=Path(__file__).resolve().parents[1]
from icstudio.catalog import create_device, binding_for
from icstudio.engines import parse_raw
from icstudio.interchange import spice
from icstudio.model import example,clone,device,save_project,load_project
from icstudio.testbenches import native_subcircuit
from scripts import installed_mim_inputs as identity
from scripts.qualify_sky130_mim_passive_corners import stage_models

MODELS=('l1','m1','m2','m3','m4')
SECTIONS=('tt','ll','hh','hl','lh')
PORTS=('a1','b1','a2','b2')
PATHS=('app','reference','native','numeric','cross','missing','width')
FAULTS=('cross','missing','width')
SPEC='docs/qualification/sky130-metal-hierarchy-electrical-v1.json'
ARCHIVE_SHA='f160341c8a956a4ee2f6e0a60beaed9b9822fdf6202ce0b4ba7c66ffd7e65fe9'
ARCHIVE_MANIFEST='df0e39c580c9a4a7995804b6d9e827e6cd334840baf60bac9d134553dfb058d9'
SOURCE_MANIFEST='de53c5b24601242e64448a151eb6acf4ed2e57cf2c71d524b207f64f9b74e11b'

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_bytes())
def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
def inventory(root,exclude=()):
    return {p.relative_to(root).as_posix():sha(p) for p in sorted(Path(root).rglob('*')) if p.is_file() and p.relative_to(root).as_posix() not in exclude}
def cases(pilot=False):
    return [dict(name=f'{m}-r{r}-{s}',model=m,rotation=r,section=s) for m in MODELS for r in ((0,) if pilot else (0,90)) for s in (('tt',) if pilot else SECTIONS)]
def contract():
    spec=load(CANDIDATE/SPEC)
    require(spec['models']==list(MODELS) and spec['sections']==list(SECTIONS) and spec['ports']==list(PORTS),'Changed finite contract.')
    for name,digest in spec['source_contracts'].items():require(sha(ROOT/name)==digest,'Base contract changed: '+name)
    return spec
def check_source(manifest):
    require(sha(manifest)==SOURCE_MANIFEST,'Unreviewed base source manifest.')
    files=load(manifest)['files'];require(len(files)==6631,'Source inventory coverage differs.')
    for name,digest in files.items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts,'Unsafe source name.')
        require(sha(ROOT/name)==digest,'Base source identity differs: '+name)
    return files
def restore(archive,dest):
    require(sha(archive)==ARCHIVE_SHA,'Wrong physical archive.')
    with zipfile.ZipFile(archive) as z:
        raw=z.read('manifest.json');require(hashlib.sha256(raw).hexdigest()==ARCHIVE_MANIFEST,'Wrong archive manifest.')
        files={k.removeprefix('native/full-v1/'):v for k,v in json.loads(raw)['files'].items() if k.startswith('native/full-v1/')}
        require(len(files)==1743,'Incomplete physical dependency.')
        if not dest.exists():
            dest.mkdir(parents=True)
            for name,row in files.items():
                require(not Path(name).is_absolute() and '..' not in Path(name).parts,'Unsafe archive name.')
                data=z.read('objects/'+row['sha256'])
                require(len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],'Bad archive object.')
                p=dest/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        require(inventory(dest)=={n:v['sha256'] for n,v in files.items()},'Historical physical bytes differ.')
    return files
def native_graph(text,model,fault=None):
    rows=[x.split() for x in text.splitlines() if x.strip() and not x.lstrip().startswith('*')]
    require(rows[0]==['.subckt','res_pair','A1','B1','A2','B2'] and rows[-1] in (['.ends'],['.ends','res_pair']),'Wrong native ordered interface.')
    resistors=rows[1:-1];require(len(resistors)==(1 if fault=='missing' else 2),'Wrong native occurrence count.')
    require(len({r[0].lower() for r in resistors})==len(resistors),'Duplicate native occurrence.')
    found=[]
    for row in resistors:
        require(row[0].lower().startswith('r') and row[3]=='sky130_fd_pr__res_generic_'+model,'Wrong native model.')
        fields=[x.split('=') for x in row[4:]]
        require(all(len(x)==2 for x in fields) and len({x[0].lower() for x in fields})==len(fields),'Bad native parameters.')
        params={k.lower():float(v) for k,v in fields}
        require(set(params) in ({'w','l'},{'w','l','m'}) and params['l']==5 and params.get('m',1)==1,'Wrong native length/multiplicity.')
        found.append((frozenset(row[1:3]),params['w']))
    expected=[(frozenset(('A1','B1')),2)]
    if fault!='missing':expected.append((frozenset(('A1' if fault=='cross' else 'A2','B2')),3 if fault=='width' else 2))
    require(set(found)==set(expected),'Wrong native nets/width.')
def mutate(data,model,fault):
    text=data.decode();native_graph(text,model);rows=text.splitlines(keepends=True)
    indices=[i for i,x in enumerate(rows) if x.startswith('R') and frozenset(x.split()[1:3])==frozenset(('A2','B2'))]
    require(len(indices)==1 and fault in FAULTS,'Ambiguous mutation.')
    i=indices[0]
    if fault=='missing':rows.pop(i)
    elif fault=='cross':rows[i],n=re.subn(r'\bA2\b','A1',rows[i]);require(n==1,'Ambiguous terminal mutation.')
    else:
        rows[i],n=re.subn(r'(?i)(\bw=)2(?=\s|$)',r'\g<1>3',rows[i]);require(n==1,'Ambiguous width mutation.')
    result=''.join(rows);native_graph(result,model,fault);return result.encode()
def application(tech,model,out):
    p=example('empty');p['pdk']=clone(tech);leaf=p['cells'][0];leaf.update(name='resistor_leaf',ports=['A','B'])
    key='sky130_fd_pr/res_generic_'+('li' if model=='l1' else model)+'.sym'
    d=create_device(tech,key,'RLEAF');binding=binding_for(tech,d)
    require(binding['kind']=='PDK' and binding['prefix']=='R' and binding['pin_order']==['m','p'] and binding['model']=='sky130_fd_pr__res_generic_'+model,'Application resistor ABI differs.')
    d['nets']=dict(m='A',p='B');d['model_params'].update(w=2,l=5,mult=1);leaf['devices']=[d]
    top=dict(id=uuid.uuid4().hex[:16],name='res_pair',ports=[p.upper() for p in PORTS],shapes=[],devices=[device('X',f'X{i}',cell=leaf['id'],nets=dict(A=f'A{i}',B=f'B{i}')) for i in (1,2)])
    p['cells'].append(top);p['top']=top['id'];out.mkdir(parents=True)
    save_project(p,out/'schematic.icproj');saved=load_project(out/'schematic.icproj');require(saved==p,'Application save/reopen changed.')
    (out/'hierarchical.spice').write_text(spice(saved),encoding='utf-8',newline='\n')
    (out/'application.spice').write_text(native_subcircuit(saved,saved['top']),encoding='utf-8',newline='\n')
    return binding
def resistance(spec,model,section,width=2):
    c=spec['coefficients'][model][section];dt=spec['temperature_c']-30
    return c['rsh']*5e-6/(width*1e-6+c['tol']+c['dw'])*(1+c['tc1']*dt+c['tc2']*dt*dt)
def expected(tag,v,r,r3):
    first=(v[0]-v[1])/r
    if tag=='missing':return (first,-first,0j,0j)
    second=(v[0 if tag=='cross' else 2]-v[3])/(r3 if tag=='width' else r)
    return (first+second,-first,0j,-second) if tag=='cross' else (first,-first,second,-second)
def title(origin,nonce,case,analysis,basis):
    return '* metal-hierarchy-electrical '+hashlib.sha256(json.dumps([origin,nonce,case,analysis,basis],separators=(',',':')).encode()).hexdigest()
def probes(model):
    suffix='li' if model=='l1' else model
    return dict(rsh='r'+model,tol='tol_'+suffix,dw=suffix+'_dw',tc1='tc1r'+model,tc2='tc2r'+model,mc_mm_switch='mc_mm_switch',mc_pr_switch='mc_pr_switch')
def deck(spec,case,analysis,basis,networks,staged,origin,nonce):
    lines=[title(origin,nonce,case['name'],analysis,basis),staged,'.param mc_mm_switch=0 mc_pr_switch=0','.temp 27']
    saves=[]
    for tag in PATHS:
        lines.append(f'.subckt whole_{tag} A1 B1 A2 B2')
        if tag=='numeric':
            r=resistance(spec,case['model'],case['section']);lines += [f'RREF1 A1 B1 {r:.17g}',f'RREF2 A2 B2 {r:.17g}']
        else:lines += [f'.include "{networks[tag].as_posix()}"','Xwhole A1 B1 A2 B2 res_pair']
        lines.append(f'.ends whole_{tag}')
        for i,port in enumerate(PORTS):
            amplitude=.001 if i==basis else 0
            dc=amplitude if analysis=='dc' else 0
            lines.append(f'V_{tag}_{port} {tag}_{port} 0 DC {dc:.17g} AC {amplitude:.17g}')
            saves += [f'v({tag}_{port})',f'i(v_{tag}_{port})']
        lines.append('X_'+tag+' '+' '.join(tag+'_'+p for p in PORTS)+' whole_'+tag)
    for name,parameter in probes(case['model']).items():
        lines.append(f'VPAR_{name} par_{name} 0 DC {{{parameter}}} AC {{{parameter}}}')
        saves.append(f'v(par_{name})')
    # One common source sweep drives every active terminal through unity VCVSs.
    if analysis=='dc':
        for tag in PATHS:
            key=f'V_{tag}_{PORTS[basis]} ';i=next(i for i,s in enumerate(lines) if s.startswith(key))
            lines[i]=f'E_{tag}_{PORTS[basis]} {tag}_{PORTS[basis]} 0 drive 0 1'
            saves[saves.index(f'i(v_{tag}_{PORTS[basis]})')]=f'i(e_{tag}_{PORTS[basis]})'
        lines += ['VDRIVE drive 0 0','.dc VDRIVE -0.001 0.001 0.001']
    else:lines += ['.ac dec 1 1k 10G']
    lines += ['.save '+' '.join(saves),'.end',''];return '\n'.join(lines)
def observe(path,spec,case,analysis,basis,expected_title,actual_section=None):
    raw=Path(path).read_bytes();require(re.findall(rb'(?mi)^Title: *([^\r\n]*)',raw)==[expected_title.encode()],'Wrong raw execution identity.')
    names,rows,iscomplex=parse_raw(path);names=[x.lower() for x in names];require(iscomplex is (analysis=='ac'),'Wrong raw plot type.')
    require(len(rows)==(8 if analysis=='ac' else 3),'Missing sweep points.')
    section=actual_section or case['section'];r=resistance(spec,case['model'],section);r3=resistance(spec,case['model'],section,3)
    tolerance=spec['tolerances'];maximum=0.;detections={f:False for f in FAULTS};observations=[];zeros=kcl=0
    for index,row in enumerate(rows):
        data=dict(zip(names,map(complex,row)));coordinate=data['frequency' if analysis=='ac' else 'v(v-sweep)']
        x=10**(index+3) if analysis=='ac' else (index-1)*.001
        require(abs(coordinate-x)<=max(abs(x)*1e-10,1e-15),'Wrong sweep coordinate.')
        amplitude=.001 if analysis=='ac' else x;sample={}
        coefficients={**spec['coefficients'][case['model']][section], 'mc_mm_switch':0,'mc_pr_switch':0}
        for name,value in coefficients.items():
            require(abs(data[f'v(par_{name})']-value)<=1e-24+1e-10*abs(value),'Actual passive coefficient differs: '+name)
        for tag in PATHS:
            voltage=[data[f'v({tag}_{p})'] for p in PORTS]
            current=[-data[f'i({"e" if analysis=="dc" and i==basis else "v"}_{tag}_{p})'] for i,p in enumerate(PORTS)]
            require(all(abs(v-(amplitude if i==basis else 0))<=tolerance['voltage_absolute'] for i,v in enumerate(voltage)),'Terminal clamp differs.')
            exp=expected(tag,voltage,resistance(spec,case['model'],case['section']) if tag=='numeric' else r,r3)
            for actual,target in zip(current,exp):
                error=abs(actual-target)/(tolerance['current_absolute']+tolerance['current_relative']*abs(target));maximum=max(maximum,error)
                require(math.isfinite(error) and error<=1,'Terminal current differs from independent numeric reference.')
                zeros+=target==0
            require(abs(sum(current))<=4*tolerance['current_absolute']+tolerance['current_relative']*sum(map(abs,current)),'Network KCL failed.');kcl+=1
            if tag in FAULTS:
                positive=expected('native',voltage,r,r3)
                relative=max(abs(a-b) for a,b in zip(current,positive))/max(.001/r,max(map(abs,positive)))
                detections[tag] |= relative>tolerance['fault_min_relative_difference']
            sample[tag]=dict(voltages=[[x.real,x.imag] for x in voltage],currents=[[x.real,x.imag] for x in current])
        observations.append(dict(coordinate=[coordinate.real,coordinate.imag],paths=sample))
    return dict(samples=len(rows),maximum_normalized_current_error=maximum,detections=detections,zero_current_samples=zeros,kcl_samples=kcl,observations=observations)
def run(args):
    require(sys.dont_write_bytecode and sys.pycache_prefix,'Use isolated no-bytecode Python.')
    out=args.out.resolve();require(not out.exists(),'Use fresh output.');out.mkdir(parents=True)
    started=time.monotonic();spec=contract();nonce=uuid.uuid4().hex;origin=out.as_posix()
    report=dict(schema=1,gate=spec['id'],status='RUNNING',execution_root=origin,nonce=nonce,mode='source-integration',pilot=args.pilot,qualified=False,installed=False,full_family=False,chunk_complete=False,release_ready=False,signoff=False,cases=[],scope=spec['scope'])
    try:
        sourcefiles=check_source(args.source_manifest);shutil.copyfile(args.source_manifest,out/'source-manifest.json')
        sourcepaths=[p for folder in ('icstudio','scripts') for p in (ROOT/folder).glob('*.py')]
        sourcepaths += [ROOT/p for p in spec['source_contracts']]
        captured={p.relative_to(ROOT).as_posix():sha(p) for p in sourcepaths};write(out/'source-files.json',captured)
        for name,digest in captured.items():
            p=out/'source'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p);require(sha(p)==digest,'Source capture changed.')
        candidatefiles={folder+'/'+n:h for folder in ('scripts','tests','docs') for n,h in inventory(CANDIDATE/folder).items()}
        write(out/'candidate-files.json',candidatefiles)
        for name,digest in candidatefiles.items():
            p=out/'candidate'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(CANDIDATE/name,p)
        shutil.copyfile(CANDIDATE/SPEC,out/'contract.json')
        members=restore(args.archive,args.physical)
        from scripts import audit_sky130_metal_resistor_hierarchy as physical_reader
        proof=physical_reader.audit(args.physical);require(proof['counts']['clean_layouts']==10 and proof['full_selected_models'],'Incomplete historical physical class.');write(out/'physical-readback.json',proof)
        report['physical_dependency']=dict(archive_sha256=ARCHIVE_SHA,manifest_sha256=ARCHIVE_MANIFEST,physical_root=str(args.physical),files=1743,qualification_sha256=sha(args.physical/'qualification.json'),readback_sha256=sha(out/'physical-readback.json'))
        package_root=ROOT/'icstudio/assets/pdks/sky130A';package=load(package_root/'package.json')
        require(sha(package_root/'package.json')==spec['simulation_package']['manifest_sha256'],'Wrong simulation package.')
        packagefiles={'package.json':sha(package_root/'package.json'),**package['files']}
        for name,digest in packagefiles.items():require(sha(package_root/name)==digest,'Wrong package asset: '+name)
        shutil.copyfile(package_root/'package.json',out/'package.json');write(out/'package-files.json',packagefiles)
        (out/'contract-sources').mkdir();shutil.copyfile(package_root/'package.json',out/'contract-sources/package');report['simulation_package']=spec['simulation_package']
        tech=clone(package['technology']);tech.update(package_root=str(package_root),package_lock={k:package[k] for k in ('id','revision','files')})
        staged,modelfiles=stage_models(tech,out);write(out/'model-files.json',modelfiles)
        report['applications']={m:application(tech,m,out/'applications'/m) for m in MODELS}
        bindings={}
        for model in MODELS:
            for rotation in (0,90):
                key=f'{model}-r{rotation}';folder=out/'networks'/key;folder.mkdir(parents=True)
                old=args.physical/model/f'r{rotation}'/'physical'
                networks=dict(app=out/'applications'/model/'application.spice')
                for tag,name in (('native','lvs-extraction/extracted.spice'),('reference','schematic.spice')):
                    networks[tag]=folder/(tag+'.spice');shutil.copyfile(old/name,networks[tag])
                native_graph(networks['native'].read_text(),model)
                for fault in FAULTS:
                    networks[fault]=folder/(fault+'.spice');networks[fault].write_bytes(mutate(networks['native'].read_bytes(),model,fault))
                bindings[key]={tag:dict(path=str(p),sha256=sha(p)) for tag,p in networks.items()}
        report['network_bindings']=bindings
        engine=args.ngspice.resolve();env=identity.native_environment(dict(mode='source-pilot'),engine,out)
        before=identity.runtime(dict(mode='source-pilot'),engine,env);write(out/'runtime-before.json',before)
        assets={**before['files'],**{v['resolved']:v['sha256'] for v in before['elf_dependencies'].values()}}
        for name,digest in assets.items():
            p=out/'runtime-assets'/digest;p.parent.mkdir(exist_ok=True)
            if not p.exists():shutil.copyfile(name,p)
        write(out/'runtime-assets.json',assets)
        report.update(contract_sha256=sha(out/'contract.json'),source_files_sha256=sha(out/'source-files.json'),candidate_files_sha256=sha(out/'candidate-files.json'),source_manifest_sha256=SOURCE_MANIFEST,runtime_before_sha256=sha(out/'runtime-before.json'),selected_cases=[c['name'] for c in cases(args.pilot)],full_declared_cases=[c['name'] for c in cases()],python=dict(executable=sys.executable,version=sys.version,dont_write_bytecode=sys.dont_write_bytecode,pycache_prefix=sys.pycache_prefix))
        def one(case):
            row={**case,'status':'RUNNING','runs':{}};folder=out/case['name'];folder.mkdir()
            try:
                networks={k:Path(v['path']) for k,v in bindings[f'{case["model"]}-r{case["rotation"]}'].items()}
                detected=dict.fromkeys(FAULTS,False)
                for analysis in ('dc','ac'):
                    for basis in range(4):
                        tag=f'{analysis}-e{basis}';dest=folder/tag;dest.mkdir()
                        text=deck(spec,case,analysis,basis,networks,staged[case['section']],origin,nonce)
                        (dest/'input.cir').write_text(text,encoding='utf-8',newline='\n')
                        command=[str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(dest/'result.raw'),str(dest/'input.cir')]
                        result=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,timeout=90)
                        log=result.stdout+result.stderr;(dest/'console.log').write_text(log,encoding='utf-8')
                        write(dest/'invocation.json',dict(command=command,cwd=str(out),environment=env,returncode=result.returncode))
                        require(result.returncode==0 and not re.search(r'error|unknown parameter',log,re.I),'Native simulation failed.')
                        observed=observe(dest/'result.raw',spec,case,analysis,basis,title(origin,nonce,case['name'],analysis,basis))
                        row['runs'][tag]=dict(observed=observed,files=inventory(dest))
                        for fault in FAULTS:detected[fault] |= observed['detections'][fault]
                alternate='hh' if case['section']!='hh' else 'll';dest=folder/'wrong-section';dest.mkdir()
                text=deck(spec,case,'ac',0,networks,staged[alternate],origin,nonce)
                (dest/'input.cir').write_text(text,encoding='utf-8',newline='\n')
                command=[str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(dest/'result.raw'),str(dest/'input.cir')]
                result=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,timeout=90)
                log=result.stdout+result.stderr;(dest/'console.log').write_text(log,encoding='utf-8')
                write(dest/'invocation.json',dict(command=command,cwd=str(out),environment=env,returncode=result.returncode))
                require(result.returncode==0 and not re.search(r'error|unknown parameter',log,re.I),'Wrong-section simulation failed.')
                observed=observe(dest/'result.raw',spec,case,'ac',0,title(origin,nonce,case['name'],'ac',0),actual_section=alternate)
                try:observe(dest/'result.raw',spec,case,'ac',0,title(origin,nonce,case['name'],'ac',0))
                except ValueError as error:
                    require(str(error).startswith('Actual passive coefficient differs:'),'Wrong section rejected for unrelated reason.');rejection=str(error)
                else:raise ValueError('Wrong section was accepted.')
                row['wrong_section']=dict(actual_section=alternate,requested_section=case['section'],rejected=True,error=rejection,observed=observed,files=inventory(dest))
                require(all(detected.values()),'A real wrong-network control was not detected.');row.update(status='PASS',detected=detected)
            except Exception:row.update(status='FAIL',error=traceback.format_exc())
            write(folder/'record.json',row);print(case['name'],row['status'],flush=True);return row
        with ThreadPoolExecutor(max_workers=args.workers) as pool:report['cases']=list(pool.map(one,cases(args.pilot)))
        require(all(r['status']=='PASS' for r in report['cases']),'Electrical case failed.')
        after=identity.runtime(dict(mode='source-pilot'),engine,env);write(out/'runtime-after.json',after);require(before==after,'Runtime changed.')
        check_source(args.source_manifest)
        require(all(sha(CANDIDATE/n)==h for n,h in candidatefiles.items()),'Candidate changed during run.')
        require(all(sha(package_root/n)==h for n,h in packagefiles.items()),'Package changed during run.')
        require(all(sha(out/'shared-models'/n)==h for n,h in modelfiles.items()),'Staged models changed.')
        require(all(sha(v['path'])==v['sha256'] for b in bindings.values() for v in b.values()),'Networks changed.')
        restore(args.archive,args.physical)
        report.update(status='PASS',runtime_after_sha256=sha(out/'runtime-after.json'),guards=dict(source=True,candidate=True,package=True,models=True,runtime=True,physical=True,networks=True),source_integration_acceptance=not args.pilot)
    except Exception:report.update(status='FAIL',error=traceback.format_exc())
    report['seconds']=time.monotonic()-started;write(out/'qualification.json',report);write(out/'manifest.json',inventory(out,('manifest.json',)))
    return report
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','source-manifest','out','physical','archive','ngspice'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--pilot',action='store_true');p.add_argument('--workers',type=int,default=2)
    a=p.parse_args();require(a.workers in (1,2,3,4),'Invalid worker count.');result=run(a);print(json.dumps({k:v for k,v in result.items() if k in ('status','error','seconds')}));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':sys.exit(main())
