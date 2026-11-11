"""Finite linked IHP tap physical/electrical pilot, never family qualification.

Native A/P is projected through the pinned public parallel-conductance formula.
The original extraction remains unchanged. This is an explicit electrical
projection, not a claim that the native R/A/P syntax is directly simulatable.
"""
import argparse
import cmath
import json
import math
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio.model import clone,device,example,file_digest,load_project,save_project,scalar
from icstudio.catalog import create_device
from icstudio.catalog_migration import emit
from icstudio.engines import run_ngspice,run_deck
from icstudio.osdi import configure,preload
from icstudio.pdks import model_lines,stage_model_deck
from icstudio.ihp_taps import SYMBOLS,MODELS
from scripts.qualify_standard_mos import load_technology,write

MODELS_SELECTED=('ntap1','ptap1')
SELECTION=tuple((m,r) for m in MODELS_SELECTED for r in (0,90))
W=L=2e-6
REL=1e-6
ABS=1e-10

def require(value,message):
    if not value:raise ValueError(message)

def native_tap(text,model,well):
    """Strict single-coupon reader; never guess an unknown extractor format."""
    rows=[line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(rows)==3,'Expected one native subcircuit and one tap.')
    start,body,end=[r.split() for r in rows]
    require(len(start)==4 and start[0].lower()=='.subckt' and start[1]=='coupon' and set(start[2:])=={'TIE',well},'Native subcircuit/terminal set changed.')
    require([s.lower() for s in end] in (['.ends','coupon'],['.ends']),'Native subcircuit ending changed.')
    require(len(body)==6 and body[0].upper().startswith('R') and body[1:4]==['TIE',well,model],'Native tap model or terminal roles changed.')
    params={}
    for field in body[4:]:
        pair=field.split('=');require(len(pair)==2 and pair[0].lower() not in params,'Duplicate or unresolved geometry.')
        value=scalar(pair[1]);require(math.isfinite(value) and value>0,'Positive finite native geometry required.');params[pair[0].lower()]=value
    require(set(params)=={'a','p'},'Only native A/P is supported.')
    require(math.isclose(params['a'],W*L,rel_tol=1e-10) and math.isclose(params['p'],2*(W+L),rel_tol=1e-10),'Native geometry differs from selected masks.')
    return {'model':model,'top_port_order':start[2:],'terminals':body[1:3],'area_m2':params['a'],'perimeter_m':params['p'],'resistance_ohm':1/(params['a']/9.8e-10+params['p']/9.8e-4)}

def source_proof(tech):
    root=Path(tech['package_root']);files=tech['package_lock']['files'];proof={}
    for model in MODELS_SELECTED:
        entry=tech['simulation']['catalog']['sg13g2_pr/'+model+'.sym']
        require(entry['model']==model and entry['pin_order']==['p','m'],'Tap model/terminal binding changed.')
        for rel,h in ((entry['source'],SYMBOLS[model]),(entry['model_source'],MODELS[Path(entry['model_source']).name])):
            require(files[rel]==h and file_digest(root/rel)==h,'Pinned tap source changed.');proof[rel]=h
        text=(root/entry['model_source']).read_text()
        block=re.search(r'(?im)^\.subckt '+model+r' 1 2\s*\n(.*?)^\.ends '+model+r'\s*$',text,re.S|re.M)
        require(block is not None and block[1].strip()=='.param R=262.8 w=0.78e-6 l=0.78e-6\nR1 1 2 R=R','Tap model is no longer the reviewed literal resistor.')
    return proof

def physical_binding(root,row):
    """Verify retained native evidence before using extracted geometry."""
    folder=root/row['name'];report=folder/'physical/report.json'
    require(file_digest(report)==row['report_sha256'],'Physical report changed.')
    obj=json.loads(report.read_text());stages={s['name']:s for s in obj['stages']}
    require(obj['status']=='passed' and obj['drc_count']==0 and all(s['status']=='passed' for s in stages.values()),'Required physical stage did not pass.')
    evidence=stages['integrity']['evidence'];require(evidence['verified'],'Physical inventory not verified.')
    for name,h in evidence['files'].items():
        path=(report.parent/name).resolve();require(path.is_relative_to(report.parent.resolve()) and path.is_file() and file_digest(path)==h,'Changed native evidence: '+name)
    for fault in row['faults']:
        require(file_digest(folder/fault['name']/'report.json')==fault['report_sha256'],'Physical fault report changed.')
    native=folder/'physical/lvs-extraction/native.cir'
    require(file_digest(native)==row['native']['sha256'],'Native extraction changed.')
    require(all(x['status']=='passed' for x in row['exchange'].values()),'Stream exchange did not pass.')
    return native

def project(tech,model,osdi):
    p=example('empty');p['pdk']=clone(tech);p['simulation_runtime']={'osdi':clone(osdi)}
    c=p['cells'][0];c['name']='tap_linked';v=device('V','VDRIVE',0,0,value='.0005',nets={'p':'input','n':'0'});v['source']['ac']='1'
    d=create_device(tech,'sg13g2_pr/'+model+'.sym','DUT');d['model_params'].update(w=W,l=L);d['nets']={'p':'input','m':'output'}
    c['devices']=[v,d,device('R','RL',0,0,value='1k',nets={'p':'output','n':'0'},model_mode='generic'),device('C','CL',0,0,value='1p',nets={'p':'output','n':'0'},model_mode='generic')]
    require(emit(d,tech).split()[1:4]==['input','output',model],'Application model/port identity changed.')
    return p

def settings(analysis):
    return dict(type=analysis,corner='nominal',temperature=27,source='VDRIVE',dc_start='-.01',dc_stop='.01',dc_step='.001',start='100',end='10meg',points=5,timeout=90)

def reference_deck(tech,model,resistance,analysis,route,fault=None):
    require(route in ('extracted','independent'),'Unknown route.')
    if fault=='area':resistance=1/(W*L*1.2/9.8e-10+2*(W+L)/9.8e-4)
    elif fault=='perimeter':resistance=1/(W*L/9.8e-10+2*(W+L)*1.2/9.8e-4)
    elif fault not in (None,'disconnected'):raise ValueError('Unknown fault.')
    top='0' if fault=='disconnected' else 'input'
    # The extracted projection retains the actual extracted model identity.
    # Independent ideal R is justified by the checksum-pinned entire subcircuit.
    element=f'XTAP {top} output {model} r={resistance:.17g}' if route=='extracted' else f'RREF {top} output {resistance:.17g}'
    lines=[f'* IHP tap linked v1 {route} {model} {fault}',*model_lines(tech,'nominal'),'VDRIVE input 0 DC .0005 AC 1',element,'RL output 0 1000','CL output 0 1p','.temp 27','.dc VDRIVE -.01 .01 .001' if analysis=='dc' else '.ac dec 5 100 10meg','.end','']
    return '\n'.join(lines)

def response(result,analysis):
    x=result['x'];v=result['traces'].get('output',[])
    require(len(x)==len(v)==(21 if analysis=='dc' else 26),'Incomplete linked sweep.')
    grid=[-.01+i*.001 for i in range(21)] if analysis=='dc' else [100*10**(i/5) for i in range(26)]
    require(all(math.isfinite(a) and math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-12) for a,b in zip(x,grid)),'Changed linked sweep grid.')
    require(all(math.isfinite(a) for a in v),'Nonfinite response.')
    if analysis=='ac':
        phase=result['phase'].get('output',[]);require(len(phase)==len(v) and all(math.isfinite(a) for a in phase),'Missing complex phase.')
        v=[cmath.rect(a,math.radians(b)) for a,b in zip(v,phase)]
    require(max(map(abs,v))>1e-5,'Unexercised response.')
    return x,v

def analytical(result,analysis,resistance):
    x,v=response(result,analysis);parallel=1/(1/resistance+1/1000)
    expected=[f*1000/(resistance+1000) for f in x] if analysis=='dc' else [(1000/(resistance+1000))/(1+2j*math.pi*f*parallel*1e-12) for f in x]
    return max(abs(a-b)/(ABS+REL*abs(b)) for a,b in zip(v,expected))

def run(physical,out,engine,osdi_dir):
    physical=Path(physical).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    tech,identity=load_technology('ihp-sg13g2');proof=source_proof(tech);osdi=configure(sorted(Path(osdi_dir).glob('*.osdi')))
    report=json.loads((physical/'qualification.json').read_text())
    require(report['status']=='PASS' and report['implementation_unchanged'],'Complete original physical gate required.')
    require(report['process']==identity,'Physical and electrical process identities differ.')
    require(file_digest(physical/'source-files.json')==report['source_files_sha256'],'Physical source inventory changed.')
    physical_sources=json.loads((physical/'source-files.json').read_text())
    require(all((ROOT/n).is_file() and file_digest(ROOT/n)==h for n,h in physical_sources.items()),'Physical source differs from current linked source.')
    require({(r['model'],r['rotation']) for r in report['cases']}==set(SELECTION) and len(report['cases'])==4,'Complete four-case physical pilot required.')
    sources={p.relative_to(ROOT).as_posix():file_digest(p) for p in [Path(__file__),ROOT/'scripts/qualify_ihp_tap_layouts.py',ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))]}
    write(out/'source-files.json',sources);before_engine=file_digest(engine)
    result=dict(schema=1,status='RUNNING',qualified=False,chunk_complete=False,installed_acceptance=False,scope=__doc__,process=identity,source_proof=proof,engine_sha256=before_engine,osdi=osdi,physical_report_sha256=file_digest(physical/'qualification.json'),physical_root=str(physical),cases=[],tolerances={'relative':REL,'absolute_v':ABS})
    write(out/'qualification.json',result)
    try:
        for model,rotation in SELECTION:
            name=f'{model}-2000-2000-{rotation}';row=next(r for r in report['cases'] if r['name']==name)
            require(row['status']=='PASS' and all(f['detected'] for f in row['faults']),'Physical faults missing.')
            native=physical_binding(physical,row);well='well' if model=='ntap1' else 'sub!';binding=native_tap(native.read_text(),model,well)
            folder=out/name;folder.mkdir();(folder/'native.cir').write_bytes(native.read_bytes());write(folder/'projection.json',binding)
            p=project(tech,model,osdi);save_project(p,folder/'application.icproj');p=load_project(folder/'application.icproj')
            entry={'name':name,'model':model,'rotation':rotation,'native_sha256':file_digest(native),'binding':binding,'analyses':{},'faults':[]};result['cases'].append(entry)
            for analysis in ('dc','ac'):
                checks={}
                for route in ('application','extracted','independent'):
                    dest=folder/analysis/route;dest.mkdir(parents=True)
                    if route=='application':actual=run_ngspice(p,p['top'],settings(analysis),engine,dest)
                    else:
                        resistance=binding['resistance_ohm'] if route=='extracted' else 1/(W*L/9.8e-10+2*(W+L)/9.8e-4)
                        deck=dest/'input.cir';deck.write_text(preload(p,stage_model_deck(tech,reference_deck(tech,model,resistance,analysis,route),dest),dest))
                        actual=run_deck(p,p['top'],{'deck':str(deck),'analysis':settings(analysis),'timeout':90},engine,dest)
                    write(dest/'result.json',actual);error=analytical(actual,analysis,binding['resistance_ohm']);require(error<=1,'Linked analytical mismatch: '+route);checks[route]=error
                entry['analyses'][analysis]=checks
            for fault in ('area','perimeter','disconnected'):
                dest=folder/fault;dest.mkdir();deck=dest/'input.cir';deck.write_text(preload(p,stage_model_deck(tech,reference_deck(tech,model,binding['resistance_ohm'],'dc','extracted',fault),dest),dest))
                actual=run_deck(p,p['top'],{'deck':str(deck),'analysis':settings('dc'),'timeout':90},engine,dest);write(dest/'result.json',actual)
                # Disconnection has zero output, so validate its complete finite
                # raw selection without misclassifying an unexercised response.
                if fault=='disconnected':
                    require(len(actual['x'])==len(actual['traces']['output'])==21 and all(math.isfinite(x) for x in actual['x']+actual['traces']['output']),'Invalid disconnected control.')
                    require(max(abs(x) for x in actual['traces']['output'])<ABS,'Disconnected output not near zero.');error=max(abs(x*1000/(binding['resistance_ohm']+1000))/(ABS+REL*abs(x*1000/(binding['resistance_ohm']+1000))) for x in actual['x'])
                else:error=analytical(actual,'dc',binding['resistance_ohm'])
                require(error>1,'Meaningful electrical fault was not detected.');entry['faults'].append({'name':fault,'normalized_error':error,'detected':True})
            entry['status']='PASS';write(out/'qualification.json',result);print(name,'PASS',flush=True)
        require(all(file_digest(ROOT/n)==h for n,h in sources.items()),'Implementation changed during execution.')
        require(file_digest(engine)==before_engine,'Engine changed during execution.')
        require(configure(sorted(Path(osdi_dir).glob('*.osdi')))==osdi,'OSDI inputs changed during execution.')
        require(file_digest(physical/'qualification.json')==result['physical_report_sha256'],'Physical report changed during execution.')
        for row in report['cases']:physical_binding(physical,row)
        result['status']='PASS'
    except Exception as exc:result.update(status='FAIL',error=repr(exc));raise
    finally:
        result['files']={p.relative_to(out).as_posix():file_digest(p) for p in out.rglob('*') if p.is_file() and p!=out/'qualification.json'};write(out/'qualification.json',result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('physical','output','ngspice','osdi'):p.add_argument('--'+n,required=True)
    a=p.parse_args();run(a.physical,a.output,a.ngspice,a.osdi)
