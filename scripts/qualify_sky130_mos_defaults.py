"""Execute fresh-placement SKY130 MOS defaults against literal public models.

Selected DC/corner/temperature and nominal terminal-AC integration only.
No full operating envelope, ESD rating or physical qualification is implied.
"""
import argparse,json,math,sys,traceback
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,device,example,file_digest,save_project
from icstudio.catalog import create_device,parameter_values
from icstudio.engines import run_ngspice,run_deck
from icstudio.pdks import model_lines,stage_model_deck
from scripts.qualify_standard_mos import load_technology,write
from scripts.qualify_mos_variants import manual,voltages,compare

# Literal expected W/L in micrometres, transcribed from the ordinary public
# symbol counterparts; the seven short-symbol legacy defaults are defective.
DEFAULTS = {'nfet3_01v8': [1.0, 0.15],
 'nfet3_01v8_lvt': [1.0, 0.15],
 'nfet3_03v3_nvt': [1.0, 0.5],
 'nfet3_05v0_nvt': [1.0, 0.9],
 'nfet3_g5v0d10v5': [1.0, 0.5],
 'nfet3_g5v0d16v0': [5.0, 0.7],
 'nfet_01v8': [1.0, 0.15],
 'nfet_01v8_lvt': [1.0, 0.15],
 'nfet_01v8_lvt_nf': [1.0, 0.15],
 'nfet_01v8_nf': [1.0, 0.15],
 'nfet_03v3_nvt': [1.0, 0.5],
 'nfet_03v3_nvt_nf': [1.0, 0.5],
 'nfet_05v0_nvt': [1.0, 0.8999999999999999],
 'nfet_05v0_nvt_nf': [1.0, 0.8999999999999999],
 'nfet_g5v0d10v5': [1.0, 0.5],
 'nfet_g5v0d10v5_nf': [1.0, 0.5],
 'nfet_g5v0d16v0': [5.0, 0.7],
 'nfet_g5v0d16v0_nf': [5.0, 0.7],
 'pfet3_01v8': [1.0, 0.15],
 'pfet3_01v8_hvt': [1.0, 0.15],
 'pfet3_01v8_lvt': [1.0, 0.35],
 'pfet3_g5v0d10v5': [1.0, 0.5],
 'pfet3_g5v0d16v0': [5.0, 0.66],
 'pfet_01v8': [1.0, 0.15],
 'pfet_01v8_hvt': [1.0, 0.15],
 'pfet_01v8_hvt_nf': [1.0, 0.15],
 'pfet_01v8_lvt': [1.0, 0.35],
 'pfet_01v8_lvt_nf': [1.0, 0.35],
 'pfet_01v8_nf': [1.0, 0.15],
 'pfet_g5v0d10v5': [1.0, 0.5],
 'pfet_g5v0d10v5_nf': [1.0, 0.5],
 'pfet_g5v0d16v0': [5.0, 0.66],
 'pfet_g5v0d16v0_nf': [5.0, 0.66],
 'nfet_01v8_esd': [20.35, 0.165],
 'nfet_g5v0d10v5_esd': [21.499999999999996, 0.55],
 'nfet3_20v0': [29.41, 2.95],
 'nfet_20v0': [29.41, 2.95],
 'nfet_20v0_iso': [30.0, 1.5],
 'nfet_20v0_nvt': [30.0, 1.5],
 'nfet_20v0_zvt': [30.0, 5.0],
 'pfet3_20v0': [30.0, 0.5],
 'pfet_20v0': [30.0, 0.5]}

def rows():
    for i,(name,(w,l)) in enumerate(DEFAULTS.items()):
        model=name.replace('fet3_','fet_').removesuffix('_nf')
        if name.endswith('_esd'):model='esd_'+name.removesuffix('_esd')
        yield dict(tag=f'q{i}',name=name,key='sky130_fd_pr/'+name+'.sym',model='sky130_fd_pr__'+model,
            w=w,l=l,nf=1,copies=1,pm=name.startswith('pfet'),target='sky130A',
            pins=('d','g','s','b','sub') if name=='nfet_20v0_iso' else ('d','g','s','b'))

def fixture(tech,drive):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0]
    gate=device('V','VG',0,0,value='.8',nets={'p':'sweep','n':'0'});gate['source']['ac']='0';c['devices']=[gate]
    for row in rows():
        d=create_device(tech,row['key'],'D'+row['tag'])
        # These checks inspect constructor output; the fixture never sets W/L.
        actual=parameter_values(tech['simulation']['catalog'][row['key']],d)
        assert all(math.isclose(actual[k],row[k],rel_tol=1e-12) for k in ('w','l')),(row['name'],actual)
        assert actual.get('nf',1)==1 and actual.get('mult',actual.get('m',1))==1
        d['nets']={pin:row['tag']+pin for pin in row['pins']};c['devices'].append(d)
        for pin,value in voltages(row).items():
            v=device('V','V'+row['tag']+pin,0,0,value=str(value),nets={'p':d['nets'][pin],'n':'sweep' if pin=='g' else '0'})
            v['source']['ac']=str(int(pin==drive));c['devices'].append(v)
    for i,d in enumerate(c['devices']):d.update(x=(i%12)*250,y=(i//12)*250)
    return p

def independent(tech,drive,corner,temp):
    lines=['* Literal public-model defaults; no application emitter',*model_lines(tech,corner),'VG sweep 0 .8 AC 0']
    for row in rows():
        for pin,value in voltages(row).items():
            lines.append(f'V{row["tag"]}{pin} {row["tag"]}{pin} '+('sweep' if pin=='g' else '0')+f' DC {value:g} AC {int(pin==drive)}')
        lines.append('X'+row['tag']+' '+' '.join(row['tag']+pin for pin in row['pins'])+' '+row['model']+' '+manual(row))
    return '\n'.join([*lines,f'.temp {temp}', '.dc VG 0 1.2 .03' if drive=='dc' else '.ac dec 5 1k 1g','.end',''])

def case(tech,corner,temp,drive,output,engine):
    folder=Path(output)/f'{corner}-{temp}-{drive}';folder.mkdir();record=dict(corner=corner,temperature=temp,drive=drive,status='RUNNING')
    expected=list(rows())
    try:
        p=fixture(tech,drive);save_project(p,folder/'input.icproj')
        settings=dict(type='dc' if drive=='dc' else 'ac',corner=corner,temperature=temp,source='VG',dc_start='0',dc_stop='1.2',dc_step='.03',start='1k',end='1g',points=5)
        app,ref=folder/'application',folder/'independent';app.mkdir();ref.mkdir()
        a=run_ngspice(p,p['top'],settings,engine,app);write(app/'comparison-result.json',a)
        text=stage_model_deck(tech,independent(tech,drive,corner,temp),ref);path=ref/'reference.cir';path.write_bytes(text.encode())
        b=run_deck(p,p['top'],dict(deck=str(path),analysis=settings),engine,ref);write(ref/'comparison-result.json',b)
        result=compare(a,b,expected,drive);assert result['status']=='PASS',result
        record.update(comparison=result,raw_sha256=dict(application=file_digest(app/'result.raw'),independent=file_digest(ref/'deck.raw')),faults=[])
        if drive=='dc':
            for fault in ('wrong-multiplicity','wrong-terminal'):
                q=clone(p)
                for row in expected:
                    d=next(d for d in q['cells'][0]['devices'] if d['name']=='D'+row['tag'])
                    if fault=='wrong-multiplicity':d['model_params']['mult']=2
                    else:d['nets']['g']=d['nets']['s']
                dest=folder/fault;dest.mkdir();save_project(q,dest/'input.icproj')
                changed=run_ngspice(q,q['top'],settings,engine,dest);write(dest/'comparison-result.json',changed)
                check=compare(changed,b,expected,drive);assert all(v>1 for v in check['device_errors'].values()),check
                record['faults'].append(dict(name=fault,comparison=check,raw_sha256=file_digest(dest/'result.raw')))
        record['status']='PASS'
    except Exception as e:record.update(status='FAIL',error=str(e),traceback=traceback.format_exc())
    write(folder/'record.json',record);return record

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--ngspice',required=True);ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,default=2)
    a=ap.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);tech,identity=load_technology('sky130A')
    files=[Path(__file__),ROOT/'scripts/qualify_mos_variants.py',ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').glob('*.py'))]
    hashes={p.relative_to(ROOT).as_posix():file_digest(p) for p in files};write(out/'source-files.json',hashes)
    record=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',scope=__doc__,package=identity,rows=list(rows()),engine_sha256=file_digest(a.ngspice),cases=[])
    conditions=[('nominal',27,'dc')] if a.pilot else [(c,t,'dc') for c in ('nominal','ss','ff') for t in (0,27,85)]+[('nominal',27,d) for d in ('d','g','s','b','sub')]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for job in as_completed([pool.submit(case,tech,c,t,d,out,a.ngspice) for c,t,d in conditions]):
            row=job.result();record['cases'].append(row);print(row['corner'],row['temperature'],row['drive'],row['status'],row.get('error',''),flush=True);write(out/'record.json',record)
    record['source_unchanged']=hashes=={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    record['status']='PASS' if record['source_unchanged'] and all(c['status']=='PASS' for c in record['cases']) else 'FAIL';write(out/'record.json',record)
    return 0 if record['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
