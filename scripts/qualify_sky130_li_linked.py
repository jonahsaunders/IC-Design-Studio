"""Selected legal SKY130 LI layouts linked to native and independent simulation.

Fresh development execution only. The selected model/geometry/27 C tests do not
qualify full operating limits, li.2 interpretation, statistics or installation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import cmath
import json
import math
import os
from pathlib import Path
import platform
import re
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio.catalog import create_device
from icstudio.engines import parse_raw,run_deck
from icstudio.interchange import spice
from icstudio.model import clone,device,example,file_digest,save_project
from icstudio.pdks import model_lines,stage_model_deck
from scripts.qualify_standard_mos import load_technology,write
from scripts.qualify_standard_mos_layout import technology
from scripts import qualify_sky130_metal_resistor_layouts as physical

HISTORICAL_CONTRACT='docs/qualification/sky130-li-contract-v1.json'
HISTORICAL_CONTRACT_SHA='be2c12aa3c80f3a189da0c303d53323ce083982820d0ff101c524b8a8d4e10c6'
from scripts import sky130_contract_versions as versions
CURRENT_CONTRACT=versions.selected('li')
CONTRACT,CONTRACT_SHA=CURRENT_CONTRACT['path'],CURRENT_CONTRACT['sha256']
KEY='sky130_fd_pr/res_generic_li.sym'
MODEL='sky130_fd_pr__res_generic_l1'
SECTIONS=('tt','ll','hh','hl','lh')
PARAMETERS={'tt':(12.2,0),'ll':(10.31,.014e-6),'hh':(14.02,-.014e-6),'hl':(14.8,-.020e-6),'lh':(9.5,.020e-6)}
ANALYSES=('dc','ac','tran','noise')
FAULTS=('wrong-width','wrong-length','wrong-metal-model','wrong-multiplicity','disconnected-terminal','wrong-passive-section')


def contract():
    path=ROOT/CONTRACT
    if file_digest(path)!=CONTRACT_SHA:raise ValueError('LI requirement contract changed; review before execution.')
    value=json.loads(path.read_bytes())
    for key in ('model','symbol','package','library','li_rules','generic_specs',*('corner_'+s for s in SECTIONS)):
        row=value['sources'][key]
        if file_digest(ROOT/row['path'])!=row['sha256']:raise ValueError('Contract source changed: '+key)
    return value


def selected(sections,rotations):
    if not sections or len(sections)!=len(set(sections)) or any(s not in SECTIONS for s in sections):
        raise ValueError('Select distinct known passive sections.')
    if not rotations or len(rotations)!=len(set(rotations)) or any(r not in (0,90) for r in rotations):
        raise ValueError('Select distinct 0/90 degree orientations.')
    return [(s,r) for s in sections for r in rotations]


def fixture(tech,analysis,fault=None):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c['name']='li_linked';c['devices']=[]
    v=device('V','VDRIVE',0,0,value='.0005',nets={'p':'input','n':'0'});v['source']['ac']='1'
    if analysis=='tran':v['source'].update(type='pulse',low='.0001',high='.001',period='20n',delay='1n',duty='.5')
    d=create_device(tech,KEY,'LI');d['model_params'].update(w=2,l=5,mult=1);d['nets']={'m':'input','p':'output'}
    if fault=='wrong-width':d['model_params']['w']=2.4
    elif fault=='wrong-length':d['model_params']['l']=6
    elif fault=='wrong-metal-model':d['model_ref']['device']='sky130_fd_pr/res_generic_m1.sym'
    elif fault=='wrong-multiplicity':d['model_params']['mult']=2
    elif fault=='disconnected-terminal':d['nets']['m']='0'
    elif fault not in (None,'wrong-passive-section'):raise ValueError('Unknown LI electrical fault.')
    c['devices']=[v,d,device('R','RL',0,0,value='1k',nets={'p':'output','n':'0'},model_mode='generic'),
                  device('C','CL',0,0,value='1p',nets={'p':'output','n':'0'},model_mode='generic')]
    return p


def settings(analysis,section):
    return dict(type=analysis,corner=section,temperature=27,source='VDRIVE',dc_start='0',dc_stop='.001',dc_step='.000025',
                start='100',end='10meg',points=5,step='50p',stop='60n',output='output',noise_source='VDRIVE')


def read_native(path):
    text=Path(path).read_text(encoding='utf-8')
    interface=re.findall(r'(?im)^\s*\.subckt\s+(\S+)\s+([^\n]+)',text)
    if len(interface)!=1 or interface[0][0]!='coupon' or interface[0][1].split()!=['R1','R2']:
        raise ValueError('Unexpected native LI interface.')
    rows=[line.split() for line in text.splitlines() if line.strip() and not line.lstrip().startswith(('*','.'))]
    if len(rows)!=1 or not re.fullmatch(r'R\S+',rows[0][0],re.I):raise ValueError('Expected one unmodified native resistor.')
    row=rows[0]
    if len(row)!=6 or set(row[1:3])!={'R1','R2'} or row[3]!=MODEL:
        raise ValueError('Unexpected native model/terminals/parameters.')
    params=dict(x.split('=',1) for x in row[4:])
    if set(params)!={'w','l'} or float(params['w'])!=2 or float(params['l'])!=5:
        raise ValueError('Native width/length differ from the selected legal coupon.')
    # Only include the original file; do not reconstruct model/dimensions from
    # schematic metadata. Scale/global/include directives require separate review.
    directives=[line.strip().split()[0].lower() for line in text.splitlines() if line.lstrip().startswith('.')]
    if directives!=['.subckt','.ends']:raise ValueError('Unreviewed native extraction directive.')
    return dict(model=row[3],terminals=row[1:3],width_um=float(params['w']),length_um=float(params['l']),sha256=file_digest(path))


def stage_models(tech,out):
    folder=out/'shared-models';folder.mkdir()
    staged={}
    for section in SECTIONS:
        text=stage_model_deck(tech,'\n'.join(model_lines(tech,section)),folder)
        staged[section]=absolute_model_references(text,folder)
    # The normal staging helper writes paths relative to one run directory.
    # These shared immutable models are read from several run directories, so
    # their nested include paths need the same explicit root as the top level.
    for path in sorted((folder/'pdk-models').glob('*.spice')):
        path.write_bytes(absolute_model_references(path.read_text(encoding='utf-8'),folder).encode())
    files={p.relative_to(folder).as_posix():file_digest(p) for p in sorted(folder.rglob('*')) if p.is_file()}
    write(folder/'source-identity.json',dict(package=tech['revision'],staged=staged,files=files))
    return staged,files


def absolute_model_references(text,folder):
    return re.sub(r'(?im)^(\s*\.(?:lib|include|inc)) +(pdk-models/\S+)',
                  lambda m:m[1]+' '+(folder/m[2]).as_posix(),text)


def add_probes(text):
    if len(re.findall(r'(?im)^\.end\s*$',text))!=1:raise ValueError('Expected one top-level end directive.')
    return re.sub(r'(?im)^\.end\s*$',
        'VPROBE_RL1 parameter_rl1 0 {rl1}\nVPROBE_TOL parameter_tol 0 {tol_li}\n.end',text)


def deck(tech,analysis,section,kind,staged,native,p=None):
    if kind=='application':
        text=spice(p,p['top'],settings(analysis,section),hierarchical=False)
        originals=model_lines(tech,section)
        if any(text.count(line)!=1 for line in originals):raise ValueError('Unexpected application model includes.')
        for line in originals:text=text.replace(line,'')
        text=text.replace('\n','\n'+staged[section]+'\n',1)
    elif kind in ('manual','extracted'):
        lines=['* Independently wired LI loaded network',staged[section]]
        if kind=='extracted':
            read_native(native);lines.extend([f'.include {Path(native).as_posix()}','XEXTRACT input output coupon'])
        else:lines.append('RREF input output '+MODEL+' w=2 l=5 m=1')
        lines.extend(['VDRIVE input 0 '+('PULSE(.0001 .001 1n .2p .2p 10n 20n) AC 1' if analysis=='tran' else 'DC .0005 AC 1'),
                      'RL output 0 1000','CL output 0 1p','.temp 27'])
        directive={'dc':'.dc VDRIVE 0 .001 .000025','ac':'.ac dec 5 100 10meg','tran':'.tran 50p 60n','noise':'.noise V(output) VDRIVE dec 5 100 10meg'}[analysis]
        text='\n'.join([*lines,directive,'.end',''])
    else:raise ValueError('Unknown comparison path.')
    return add_probes(text)


def raw_values(path,analysis,source,require_response=True):
    variables,rows,complex_data=parse_raw(path)
    names=[s.lower() for s in variables]
    if any(len(row)!=len(names) or any(not math.isfinite(complex(v).real) or not math.isfinite(complex(v).imag) for v in row) for row in rows):
        raise ValueError('Nonfinite or incomplete native raw sample.')
    needed=['onoise_spectrum'] if analysis=='noise' else ['v(input)','v(output)']
    if len(set(names))!=len(names) or any(names.count(v)!=1 for v in needed) or len(rows)<2:
        raise ValueError('Missing/duplicate native result channels.')
    x=[float(v[0].real if complex_data else v[0]) for v in rows]
    if not all(math.isfinite(v) for v in x) or any(a>=b for a,b in zip(x,x[1:])):raise ValueError('Invalid result coordinates.')
    if analysis=='dc' and (len(x)!=41 or abs(x[0])>1e-15 or not math.isclose(x[-1],.001,rel_tol=1e-10)):raise ValueError('Incomplete DC sweep.')
    if analysis in ('ac','noise') and (len(x)!=26 or any(not math.isclose(v,100*10**(i/5),rel_tol=1e-9) for i,v in enumerate(x))):raise ValueError('Incomplete frequency sweep.')
    if analysis=='tran' and (x[0]>1e-12 or not math.isclose(x[-1],60e-9,rel_tol=1e-8)):raise ValueError('Incomplete transient.')
    values={name:[v[names.index(name)] for v in rows] for name in needed}
    if any(not math.isfinite(complex(v).real) or not math.isfinite(complex(v).imag) for vals in values.values() for v in vals):raise ValueError('Nonfinite native result.')
    if analysis=='noise' and any(v<=0 for v in values['onoise_spectrum']):raise ValueError('Nonpositive noise response.')
    if require_response and analysis in ('dc','tran') and max(values['v(output)'])-min(values['v(output)'])<1e-5:raise ValueError('Unexercised network output.')
    probes={}
    if analysis in ('dc','tran'):
        for name in ('parameter_rl1','parameter_tol'):
            key='v('+name+')'
            if names.count(key)!=1:raise ValueError('Missing native corner-parameter probe.')
            data=[float(r[names.index(key)]) for r in rows]
            if any(not math.isfinite(v) or not math.isclose(v,data[0],rel_tol=1e-11,abs_tol=1e-18) for v in data):raise ValueError('Nonconstant corner parameter.')
            probes[name]=data[0]
    if analysis in ('dc','ac'):
        source_key='i('+source.lower()+')'
        if names.count(source_key)!=1:raise ValueError('Missing source-current probe: '+source_key)
        currents=[row[names.index(source_key)] for row in rows]
        expected=[-v*(.001+(2j*math.pi*f*1e-12 if analysis=='ac' else 0)) for f,v in zip(x,values['v(output)'])]
        if any(abs(a-b)>1e-12+1e-6*abs(b) for a,b in zip(currents,expected)):raise ValueError('Native loaded-network KCL mismatch.')
        drive=values['v(input)']
        if any(abs(v-(f if analysis=='dc' else 1))>1e-10 for f,v in zip(x,drive)):raise ValueError('Incorrect applied source voltage.')
    return dict(x=x,values=values,corner_parameters=probes,sha256=file_digest(path))


def compare(actual,expected,analysis):
    left=actual['values']['onoise_spectrum' if analysis=='noise' else 'v(output)']
    right=expected['values']['onoise_spectrum' if analysis=='noise' else 'v(output)']
    x,y=actual['x'],expected['x']
    if analysis=='tran':
        import bisect
        values=[]
        for t in x:
            i=max(0,min(len(y)-2,bisect.bisect_right(y,t)-1));f=(t-y[i])/(y[i+1]-y[i]);values.append(right[i]+f*(right[i+1]-right[i]))
        right=values
    elif len(x)!=len(y) or any(not math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-15) for a,b in zip(x,y)):
        raise ValueError('Comparison coordinates differ.')
    rel=2e-4 if analysis=='tran' else 1e-6
    absolute=1e-18 if analysis=='noise' else 1e-8 if analysis=='tran' else 1e-10
    error=max(abs(a-b)/(absolute+rel*abs(b)) for a,b in zip(left,right))
    return dict(status='PASS' if error<=1 else 'MISMATCH',maximum_normalized_error=error,samples=len(left),relative_tolerance=rel,absolute_tolerance=absolute)


def execute_case(tech,section,rotation,native,staged,out,engine):
    folder=out/f'{section}-r{rotation}';folder.mkdir();row=dict(name=folder.name,section=section,rotation=rotation,status='RUNNING',analyses={},faults=[])
    try:
        readback=read_native(native);row['native']=readback
        references={}
        for analysis in ANALYSES:
            measured={};path_records={}
            for kind in ('manual','application','extracted'):
                dest=folder/analysis/kind;dest.mkdir(parents=True)
                p=fixture(tech,analysis);save_project(p,dest/'input.icproj')
                text=deck(tech,analysis,section,kind,staged,native,p)
                path=dest/'input.cir';path.write_bytes(text.encode())
                run_deck(p,p['top'],dict(deck=str(path),analysis=settings(analysis,section)),engine,dest)
                raw=raw_values(dest/'deck.raw',analysis,'VDRIVE')
                if analysis in ('dc','tran'):
                    expect=dict(zip(('parameter_rl1','parameter_tol'),PARAMETERS[section]))
                    if any(not math.isclose(raw['corner_parameters'][k],v,rel_tol=1e-10,abs_tol=1e-18) for k,v in expect.items()):raise ValueError('Wrong effective passive corner.')
                measured[kind]=raw;path_records[kind]=dict(raw_sha256=raw['sha256'],deck_sha256=file_digest(path),corner_parameters=raw['corner_parameters'])
            comparisons={kind:compare(measured[kind],measured['manual'],analysis) for kind in ('application','extracted')}
            if any(v['status']!='PASS' for v in comparisons.values()):raise ValueError('Linked LI response mismatch: '+analysis)
            row['analyses'][analysis]=dict(paths=path_records,comparisons=comparisons)
            references[analysis]=measured['manual']
        for fault in FAULTS:
            dest=folder/fault;dest.mkdir();chosen=('hl' if section!='hl' else 'lh') if fault=='wrong-passive-section' else section
            p=fixture(tech,'dc',fault);save_project(p,dest/'input.icproj')
            path=dest/'input.cir';path.write_bytes(deck(tech,'dc',chosen,'application',staged,native,p).encode())
            run_deck(p,p['top'],dict(deck=str(path),analysis=settings('dc',chosen)),engine,dest)
            # Disconnection intentionally invalidates the positive applied-drive
            # interpretation; preserve raw simulation then compare output only.
            raw=raw_values(dest/'deck.raw','dc','VDRIVE',require_response=False);comparison=compare(raw,references['dc'],'dc')
            if comparison['status']!='MISMATCH':raise ValueError('Electrical fault not detected: '+fault)
            row['faults'].append(dict(name=fault,detected=True,section=chosen,raw_sha256=raw['sha256'],comparison=comparison))
        row['status']='PASS'
    except Exception as exc:row.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('sky130','magic','netgen','ngspice','output'):ap.add_argument('--'+name,required=True,type=Path)
    ap.add_argument('--sections',nargs='+',default=['tt'],choices=SECTIONS)
    ap.add_argument('--rotations',nargs='+',type=int,default=[0,90],choices=(0,90))
    ap.add_argument('--workers',type=int,choices=range(1,5),default=2)
    a=ap.parse_args();cases=selected(a.sections,a.rotations);review=contract()
    out=a.output.resolve()
    if any(c.isspace() for c in str(out)):raise ValueError('Use a native evidence path without whitespace for this selected pilot.')
    out.mkdir(parents=True,exist_ok=False)
    # This development runner never imports a successful case from older runs.
    sources=[*sorted((ROOT/'icstudio').rglob('*.py')),*sorted((ROOT/'scripts').glob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before)
    (out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    tools={k:str(getattr(a,k).resolve(strict=True)) for k in ('magic','netgen','ngspice')}
    report=dict(schema=1,chunk=7,qualified=False,chunk_complete=False,status='RUNNING',scope=__doc__,
        selected_cases=[f'{s}-r{r}' for s,r in cases],full_declared_cases=[f'{s}-r{r}' for s in SECTIONS for r in (0,90)],
        contract_sha256=CONTRACT_SHA,tools={k:dict(path=v,sha256=file_digest(v)) for k,v in tools.items()},
        platform=platform.platform(),python=sys.version,execution_root=str(out),cases=[],development_reuse=False,source_files_sha256=file_digest(out/'source-files.json'),
        remaining=['Complete operating envelope','li.2 applicability and complete manual geometry rules','Statistical/RF/reliability accuracy','Installed acceptance','M1-M4 electrical qualification'])
    write(out/'qualification.json',report)
    try:
        sim,simid=load_technology('sky130A');phys,physid=technology('sky130A',a.sky130)
        report.update(simulation_package=simid,physical_package=physid)
        staged,model_files=stage_models(sim,out);write(out/'model-files.json',model_files)
        physical_out=out/'physical';physical_out.mkdir()
        layout=physical.case(phys,'l1',2,5,physical_out,tools)
        report['physical']=layout
        if layout['status']!='PASS':raise ValueError('The fresh native physical/fault batch failed.')
        with ThreadPoolExecutor(max_workers=a.workers) as pool:
            jobs=[pool.submit(execute_case,sim,s,r,physical_out/'l1-w2-l5'/f'physical-{r}'/'lvs-extraction/extracted.spice',staged,out,tools['ngspice']) for s,r in cases]
            for done in as_completed(jobs):
                row=done.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],row.get('error',''),flush=True)
        report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
        report['model_inputs_unchanged']=model_files=={p.relative_to(out/'shared-models').as_posix():file_digest(p) for p in sorted((out/'shared-models').rglob('*')) if p.is_file() and p.name!='source-identity.json'}
        report['tools_unchanged']=all(file_digest(v)==report['tools'][k]['sha256'] for k,v in tools.items())
        report['status']='PASS' if (report['implementation_unchanged'] and report['model_inputs_unchanged'] and report['tools_unchanged'] and len(report['cases'])==len(cases) and all(c['status']=='PASS' for c in report['cases'])) else 'FAIL'
    except Exception as exc:report.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
    report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report)
    write(out/'manifest.json',{p.relative_to(out).as_posix():file_digest(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest.json'})
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
