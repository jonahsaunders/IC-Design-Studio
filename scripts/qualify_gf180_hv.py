"""Local selected-point GF180 asymmetric MOS integration and fault controls.

Independent decks use public subcircuit defaults for junction geometry rather
than the application symbol formulas. All four complex terminal currents are
compared. This verifies integration, not silicon accuracy or foundry signoff.
"""
import argparse,cmath,json,math,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,device,example,file_digest,save_project
from icstudio.catalog import create_device
from icstudio.engines import run_ngspice,run_deck
from icstudio.pdks import PDKRegistry,model_lines,stage_model_deck
from scripts.qualify_catalog_interfaces import one

SIZES=((4,.6,1),(4,20,1),(50,.6,1),(50,20,1),(25,.6,1),(25,.6,2),(25,.6,100))


def points():
    return [dict(model=model,w=w,l=l,m=m,tag=f'{model[0]}{i}') for model in ('nfet_10v0_asym','pfet_10v0_asym') for i,(w,l,m) in enumerate(SIZES)]


def write(p,v):p.write_bytes((json.dumps(v,indent=2)+'\n').encode())


def fixture(tech,drain):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0]
    v=device('V','VG',value='2.5',nets={'p':'gate','n':'0'});v['source']['ac']='0';c['devices']=[v]
    for row in points():
        d=create_device(tech,'symbols/'+row['model']+'.sym','D'+row['tag'])
        d['params'].update(w=str(row['w'])+'u',l=str(row['l'])+'u');d['model_params']['m']=row['m']
        d['nets']={n:row['tag']+n for n in ('d','g','s','b')};pm=row['model'].startswith('p')
        # PMOS source is zero and its gate sweeps -5..0 V. Both polarities
        # exercise |VGS|=0..5 independently of their |VDS|=5 or 10 V.
        for pin,value in zip(('d','g','s','b'),(-drain if pm else drain,-5 if pm else 0,0,.2 if pm else -.2)):
            v=device('V','V'+row['tag']+pin,value=str(value),nets={'p':d['nets'][pin],'n':'gate' if pin=='g' else '0'})
            v['source']['ac']=str(dict(d=1,g=.37,s=.11,b=.23)[pin]);c['devices'].append(v)
        c['devices'].append(d)
    return p


def independent(tech,corner,temp,analysis,drain):
    lines=['* Independent public GF180 HV model calls',*model_lines(tech,corner),'VG gate 0 DC 2.5 AC 0']
    for row in points():
        pm=row['model'].startswith('p');nodes=[row['tag']+pin for pin in ('d','g','s','b')]
        for pin,node,value in zip(('d','g','s','b'),nodes,(-drain if pm else drain,-5 if pm else 0,0,.2 if pm else -.2)):
            lines.append(f'V{row["tag"]}{pin} {node} '+('gate' if pin=='g' else '0')+f' {value} AC '+str(dict(d=1,g=.37,s=.11,b=.23)[pin]))
        lines.append(f'X{row["tag"]} '+ ' '.join(nodes)+f' {row["model"]} w={row["w"]}u l={row["l"]}u nf=1 m={row["m"]}')
    return '\n'.join([*lines,f'.temp {temp}', '.dc VG 0 5 .1' if analysis=='dc' else '.ac dec 5 100 10meg','.end',''])


def values(result,analysis):
    if analysis not in ('dc','ac'):raise ValueError('Unsupported high-voltage analysis.')
    x=result.get('x',[]);expected=[i/10 for i in range(51)] if analysis=='dc' else [100*10**(i/5) for i in range(26)]
    if len(x)!=len(expected) or any(not math.isfinite(a) or not math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-14) for a,b in zip(x,expected)):
        raise ValueError('Incomplete high-voltage sweep.')
    currents={k.lower():v for k,v in result.get('currents',{}).items()};phases={k.lower():v for k,v in result.get('current_phase',{}).items()};out={}
    for row in points():
        for pin in ('d','g','s','b'):
            key='v'+row['tag']+pin;v=currents.get(key,[])
            if len(v)!=len(x) or any(not math.isfinite(n) for n in v):raise ValueError('Missing finite high-voltage terminal current: '+key)
            if analysis=='ac':
                phase=phases.get(key,[])
                if len(phase)!=len(x) or any(not math.isfinite(n) for n in phase) or any(n<0 for n in v):raise ValueError('Missing high-voltage current phase or magnitude.')
                v=[cmath.rect(a,math.radians(b)) for a,b in zip(v,phase)]
            out[key]=v
    return x,out


def compare(actual,reference,analysis):
    x,a=values(actual,analysis);y,b=values(reference,analysis);errors={}
    for row in points():
        drain=b['v'+row['tag']+'d']
        if max(abs(v) for v in drain)<1e-7 or analysis=='dc' and max(drain)-min(drain)<1e-7:raise ValueError('Unexercised independent high-voltage device.')
    for key,right in b.items():errors[key]=max(abs(v-w)/(1e-12+1e-6*abs(w)) for v,w in zip(a[key],right))
    return dict(status='PASS' if max(errors.values())<=1 else 'MISMATCH',errors=errors,vectors=len(errors),samples=len(x),relative_tolerance=1e-6,absolute_tolerance=1e-12)


def case(tech,corner,temp,drain,root,engine):
    folder=root/f'{corner}-{temp}-{drain}V';folder.mkdir();record=dict(corner=corner,temperature_c=temp,drain_v=drain,status='RUNNING',analyses={},faults=[])
    s=dict(corner=corner,temperature=temp,source='VG',dc_start='0',dc_stop='5',dc_step='.1',start='100',end='10meg',points=5)
    try:
        for analysis in ('dc','ac'):
            p=fixture(tech,drain);app=folder/analysis/'application';ref=folder/analysis/'independent';app.mkdir(parents=True);ref.mkdir();save_project(p,app/'input.icproj')
            a=run_ngspice(p,p['top'],dict(s,type=analysis),engine,app);write(app/'result.json',a)
            path=ref/'reference.cir';path.write_bytes(stage_model_deck(tech,independent(tech,corner,temp,analysis,drain),ref).encode())
            b=run_deck(p,p['top'],dict(deck=str(path),analysis=dict(s,type=analysis)),engine,ref);write(ref/'result.json',b)
            check=compare(a,b,analysis)
            if check['status']!='PASS':raise ValueError('Independent high-voltage response mismatch: '+analysis)
            record['analyses'][analysis]=dict(comparison=check,raw_sha256={'application':file_digest(app/'result.raw'),'independent':file_digest(ref/'deck.raw')})
            if analysis=='dc':dc=b
        for fault in ('wrong-width','drain-source-swap'):
            p=fixture(tech,drain)
            for d in p['cells'][0]['devices']:
                if not d.get('model_ref'):continue
                if fault=='wrong-width':
                    w=float(d['params']['w'][:-1]);d['params']['w']=str(w*(.8 if w==50 else 1.2))+'u'
                else:d['nets']['d'],d['nets']['s']=d['nets']['s'],d['nets']['d']
            dest=folder/fault;dest.mkdir();save_project(p,dest/'input.icproj');bad=run_ngspice(p,p['top'],dict(s,type='dc'),engine,dest);write(dest/'result.json',bad)
            check=compare(bad,dc,'dc');detected={row['tag']:max(check['errors']['v'+row['tag']+pin] for pin in ('d','g','s','b'))>1 for row in points()}
            if not all(detected.values()):raise ValueError('High-voltage fault escaped detection: '+fault)
            record['faults'].append(dict(name=fault,status='detected',devices=detected,comparison=check,raw_sha256=file_digest(dest/'result.raw')))
        record['status']='PASS'
    except Exception as exc:record.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
    write(folder/'record.json',record);return record


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--package',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--ngspice',required=True);ap.add_argument('--pilot',action='store_true');a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);reg=PDKRegistry(out/'registry');tech=reg.technology(reg.install(a.package/'package.json'))
    sources=[Path(__file__),ROOT/'scripts/qualify_catalog_interfaces.py',*sorted((ROOT/'icstudio').rglob('*.py'))];before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before);(out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',scope=__doc__,geometry_um_and_m=SIZES,manifest_sha256=file_digest(a.package/'package.json'),revision=tech['revision'],engine_sha256=file_digest(a.ngspice),cases=[])
    report['interfaces']=[one(tech,'symbols/'+m+'.sym',out/('interface-'+m)) for m in ('nfet_10v0_asym','pfet_10v0_asym')]
    for corner in ('nominal',) if a.pilot else ('nominal','ss','ff','sf','fs'):
        for temp in (25,) if a.pilot else (-40,25,125,175):
            for drain in (5,10):
                row=case(tech,corner,temp,drain,out,a.ngspice);report['cases'].append(row);write(out/'qualification.json',report);print(corner,temp,drain,row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['implementation_unchanged'] and all(r['status']=='PASS' for r in report['cases']+report['interfaces']) else 'FAIL';write(out/'qualification.json',report)
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
