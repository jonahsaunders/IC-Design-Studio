"""Exploratory ESD corrected-symbol integration, not physical or ESD ratings."""
import argparse,json,math,os,sys,time,traceback,uuid
from datetime import datetime,timezone
from pathlib import Path
W=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--package',type=Path,required=True);ap.add_argument('--ngspice',required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--pilot',action='store_true')
a=ap.parse_args();a.ngspice=str(Path(a.ngspice).resolve());R=a.repo.resolve();sys.path.insert(0,str(R))
from icstudio.model import clone,device,example,file_digest,save_project,load_project
from icstudio.catalog import create_device,parameter_values
from icstudio.engines import run_ngspice,run_deck
from icstudio.pdks import model_lines,stage_model_deck
from icstudio.interchange import export_xschem
from icstudio.xschem_io import import_package
from scripts.qualify_mos_variants import manual,compare,voltages
from scripts.qualify_standard_mos import write

import icstudio.engines as engines
EXECUTION_ID=uuid.uuid4().hex
CURRENT_CASE='';CURRENT_ROLE=''
original_execute=engines.execute
def utc():return datetime.now(timezone.utc).isoformat()
def title(role):return f'icstudio-esd-nvt-v2 {EXECUTION_ID} {CURRENT_CASE} {role}'
def captured_execute(args,cwd,timeout=180,input_text=None,on_line=None,env=None):
    if '-r' not in args:return original_execute(args,cwd,timeout,input_text,on_line,env)
    directory=Path(cwd).resolve();arguments=list(map(str,args))
    raw=Path(arguments[arguments.index('-r')+1]);deck=Path(arguments[-1])
    assert raw.parent==directory and deck.parent==directory
    assert directory.name==CURRENT_ROLE
    assert not (directory/'execution-receipt.json').exists()
    record=dict(schema=1,execution_id=EXECUTION_ID,case=CURRENT_CASE,role=CURRENT_ROLE,cwd=str(directory),
        command=arguments,engine_sha256=file_digest(arguments[0]),deck_filename=deck.name,
        deck_sha256=file_digest(deck),raw_filename=raw.name,started_utc=utc(),timeout_seconds=timeout,status='RUNNING')
    write(directory/'execution-receipt.json',record);started=time.monotonic()
    try:
        result=original_execute(args,cwd,timeout,input_text,on_line,env)
        (directory/'engine.log').write_bytes(result.encode('utf-8'))
        assert file_digest(deck)==record['deck_sha256']
        record.update(status='PASS',raw_sha256=file_digest(raw),log_sha256=file_digest(directory/'engine.log'))
        return result
    except Exception as exc:
        record.update(status='FAIL',error=repr(exc));raise
    finally:
        record.update(ended_utc=utc(),elapsed_seconds=time.monotonic()-started)
        write(directory/'execution-receipt.json',record)
engines.execute=captured_execute

KEY='sky130_fd_pr/nfet_g5v0d10v5_nvt_esd.sym';MODEL='sky130_fd_pr__esd_nfet_05v0_nvt'
def rows():
    return [dict(tag=f'q{i}',key=KEY,name='nfet_g5v0d10v5_nvt_esd',model=MODEL,pins=('d','g','s','b'),w=10,l=l,nf=1,copies=m,pm=False,target='sky130A') for i,(l,m) in enumerate((l,m) for l in (.9,2,4) for m in (1,3))]
def fixture(tech,drive):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c['devices']=[]
    vg=device('V','VG',0,0,value='.8',nets={'p':'sweep','n':'0'});vg['source']['ac']='0';c['devices'].append(vg)
    for r in rows():
        d=create_device(tech,KEY,'D'+r['tag']);d['params']['l']=str(r['l'])+'u';d['model_params']['mult']=r['copies']
        d['nets']={pin:r['tag']+pin for pin in r['pins']};c['devices'].append(d)
        for pin,value in voltages(r).items():
            v=device('V','V'+r['tag']+pin,0,0,value=str(value),nets={'p':d['nets'][pin],'n':'sweep' if pin=='g' else '0'});v['source']['ac']=str(int(pin==drive));c['devices'].append(v)
    for i,d in enumerate(c['devices']):d.update(x=(i%10)*300,y=(i//10)*300)
    return p
def independent(tech,drive,corner,temp):
    lines=['* '+title('independent'),*model_lines(tech,corner),'VG sweep 0 .8 AC 0']
    for r in rows():
        for pin,value in voltages(r).items():lines.append(f'V{r["tag"]}{pin} {r["tag"]}{pin} '+('sweep' if pin=='g' else '0')+f' DC {value:g} AC {int(pin==drive)}')
        lines.append('X'+r['tag']+' '+' '.join(r['tag']+pin for pin in r['pins'])+' '+MODEL+' '+manual(r))
    return '\n'.join([*lines,f'.temp {temp}', '.dc VG 0 1.2 .03' if drive=='dc' else '.ac dec 5 1k 1g','.end',''])
def case(tech,corner,temp,drive,out):
    global CURRENT_CASE,CURRENT_ROLE
    CURRENT_CASE=f'{corner}-{temp}-{drive}'
    dest=out/CURRENT_CASE;dest.mkdir();r=dict(corner=corner,temperature_c=temp,drive=drive,status='RUNNING')
    try:
        p=fixture(tech,drive);p['name']=title('application');save_project(p,dest/'input.icproj');p=load_project(dest/'input.icproj')
        setting=dict(type='dc' if drive=='dc' else 'ac',corner=corner,temperature=temp,source='VG',dc_start='0',dc_stop='1.2',dc_step='.03',start='1k',end='1g',points=5)
        app,ref=dest/'application',dest/'independent';app.mkdir();ref.mkdir()
        CURRENT_ROLE='application'
        actual=run_ngspice(p,p['top'],setting,a.ngspice,app);write(app/'comparison-result.json',actual)
        path=ref/'reference.cir';path.write_text(stage_model_deck(tech,independent(tech,drive,corner,temp),ref),encoding='utf-8')
        CURRENT_ROLE='independent'
        expected=run_deck(p,p['top'],dict(deck=str(path),analysis=setting),a.ngspice,ref);write(ref/'comparison-result.json',expected)
        result=compare(actual,expected,rows(),drive);assert result['status']=='PASS',result
        r.update(comparison=result,faults=[])
        if drive=='dc':
            for fault in ('wrong-multiplicity','wrong-gate','wrong-body','wrong-length'):
                CURRENT_ROLE=fault
                q=clone(p);q['name']=title(fault)
                for row in rows():
                    d=next(d for d in q['cells'][0]['devices'] if d['name']=='D'+row['tag'])
                    if fault=='wrong-multiplicity':d['model_params']['mult']*=2
                    elif fault=='wrong-gate':d['nets']['g']=d['nets']['s']
                    elif fault=='wrong-body':d['nets']['b']=d['nets']['s']
                    else:d['params']['l']='4u' if row['l']!=4 else '2u'
                folder=dest/fault;folder.mkdir();save_project(q,folder/'input.icproj')
                faulty=run_ngspice(q,q['top'],setting,a.ngspice,folder);write(folder/'comparison-result.json',faulty)
                check=compare(faulty,expected,rows(),drive)
                assert all(v>1 for v in check['device_errors'].values()),(fault,check)
                r['faults'].append(dict(name=fault,comparison=check))
        for folder in (app,ref,*[dest/f for f in ('wrong-multiplicity','wrong-gate','wrong-body','wrong-length') if drive=='dc']):
            receipt=json.loads((folder/'execution-receipt.json').read_bytes())
            assert receipt['status']=='PASS'
            assert file_digest(folder/receipt['deck_filename'])==receipt['deck_sha256']
            assert file_digest(folder/receipt['raw_filename'])==receipt['raw_sha256']
            assert file_digest(folder/'engine.log')==receipt['log_sha256']
        r['status']='PASS'
    except Exception as exc:r.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
    write(dest/'record.json',r);return r
out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);start=time.monotonic()
package=json.loads((a.package/'package.json').read_bytes())
assert file_digest(a.package/'package.json')=='5315d2d6ad7618047eeeb48a15f81f221e6f42864647208acfb65124ee5c9c7a'
for rel,h in package['files'].items():assert file_digest(a.package/rel)==h
tech=clone(package['technology']);tech.update(package_root=str(a.package.resolve()),package_lock={k:package[k] for k in ('id','revision','files')})
sources={p.relative_to(R).as_posix():file_digest(p) for base in ('icstudio','scripts') for p in (R/base).glob('*.py')}
report=dict(schema=2,execution_id=EXECUTION_ID,execution_root=str(out),engine=a.ngspice,status='RUNNING',scope=__doc__,qualified=False,default_promoted=False,chunk_complete=False,package_sha256=file_digest(a.package/'package.json'),engine_sha256=file_digest(a.ngspice),source_files=sources,runner_sha256=file_digest(__file__),rows=rows(),cases=[])
write(out/'report.json',report)
conditions=[('nominal',27,'dc')] if a.pilot else [(c,t,'dc') for c in ('nominal','ss','ff','sf','fs') for t in (0,27,85)]+[('nominal',27,p) for p in ('d','g','s','b')]
report['conditions']=conditions;write(out/'report.json',report)
for c,t,d in conditions:
    value=case(tech,c,t,d,out);report['cases'].append(value);write(out/'report.json',report);print(c,t,d,value['status'],value.get('error',''),flush=True)
    if value['status']!='PASS':break
report.update(status='PASS' if len(report['cases'])==len(conditions) and all(r['status']=='PASS' for r in report['cases']) else 'FAIL',elapsed_seconds=time.monotonic()-start)
assert sources=={p.relative_to(R).as_posix():file_digest(p) for base in ('icstudio','scripts') for p in (R/base).glob('*.py')}
write(out/'report.json',report)
manifest={p.relative_to(out).as_posix():file_digest(p) for p in sorted(out.rglob('*')) if p.is_file()}
write(out/'evidence-manifest.json',dict(schema=1,execution_id=EXECUTION_ID,files=manifest))
print('MANIFEST',file_digest(out/'evidence-manifest.json'),flush=True)
raise SystemExit(0 if report['status']=='PASS' else 1)
