"""Execute the two SKY130 primitive diode bindings against independent D calls."""
import argparse,math,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,device,example,file_digest,save_project
from icstudio.catalog import create_device
from icstudio.engines import run_ngspice,run_deck
from icstudio.pdks import model_lines,stage_model_deck
from scripts.qualify_standard_mos import load_technology,write

PROBES=[dict(tag=f'd{i}a{a}',symbol=symbol,area=a*1e12) for i,symbol in enumerate(('diode','lvsdiode')) for a in (1,2)]


def fixture(tech):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c['devices']=[device('V','VG',0,0,value='0',nets={'p':'drive','n':'0'})]
    for row in PROBES:
        tag=row['tag'];d=create_device(tech,'sky130_fd_pr/'+row['symbol']+'.sym','D'+tag);d['nets']={'d0':tag,'d1':'0'};d['model_params']['area']=row['area']
        c['devices'] += [device('V','V'+tag,0,0,value='0',nets={'p':tag,'n':'drive'}),d]
    return p


def vectors(data,physical=False):
    if len(data['x'])!=41 or any(not math.isfinite(v) or not math.isclose(v,-.2+i*.025,abs_tol=1e-9) for i,v in enumerate(data['x'])):raise ValueError('Incomplete diode voltage sweep.')
    current={k.lower():v for k,v in data['currents'].items()};out={}
    for row in PROBES:
        key='v'+row['tag'];v=current.get(key,[])
        if len(v)!=41 or any(not math.isfinite(x) for x in v):raise ValueError('Invalid diode current: '+key)
        if physical and (v[-1]>=-1e-7 or abs(v[-1])<=100*max(abs(v[0]),1e-15)):raise ValueError('Diode lacks forward conduction and rectification: '+key)
        out[key]=v
    return out


def compare(actual,expected):
    a=vectors(actual);b=vectors(expected,True)
    errors={k:max(abs(x-y)/(1e-14+1e-6*abs(y)) for x,y in zip(a[k],v)) for k,v in b.items()}
    return dict(status='PASS' if all(e<=1 for e in errors.values()) else 'MISMATCH',channel_errors=errors,maximum_normalized_error=max(errors.values()),vectors=4,samples=41)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--ngspice',required=True);a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    tech,identity=load_technology('sky130A');sources=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))];before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before)
    report=dict(schema=1,chunk=7,status='RUNNING',qualified=False,chunk_complete=False,process=identity,cases=[],probes=PROBES,engine_sha256=file_digest(a.ngspice),source_files_sha256=file_digest(out/'source-files.json'),scope='Two default SKY130 primitive diode bindings, two area inputs, three process and temperature points, independent DC calls and polarity/area faults. No complete diode inventory, geometry, operating envelope or measured-silicon qualification.')
    for corner in ('nominal','ss','ff'):
        for temp in (0,27,85):
            name=f'{corner}-{temp}';folder=out/name;folder.mkdir();row=dict(name=name,corner=corner,temperature_c=temp,status='RUNNING',faults=[])
            try:
                p=fixture(tech);save_project(p,folder/'input.icproj');settings=dict(type='dc',corner=corner,temperature=temp,source='VG',dc_start='-.2',dc_stop='.8',dc_step='.025')
                for side in ('application','independent'):(folder/side).mkdir()
                actual=run_ngspice(p,p['top'],settings,a.ngspice,folder/'application');write(folder/'application/response.json',actual)
                lines=['* Independent primitive diode calls',*model_lines(tech,corner),'VG drive 0 0']
                for r in PROBES:lines += [f'V{r["tag"]} {r["tag"]} drive 0',f'D{r["tag"]} {r["tag"]} 0 sky130_fd_pr__diode_pw2nd_05v5 area={r["area"]:.12g}']
                lines += [f'.temp {temp}','.dc VG -.2 .8 .025','.end',''];ref=folder/'independent';(ref/'reference.cir').write_bytes(stage_model_deck(tech,'\n'.join(lines),ref).encode())
                expected=run_deck(p,p['top'],dict(deck=str(ref/'reference.cir'),analysis=settings),a.ngspice,ref);write(ref/'response.json',expected);row['comparison']=compare(actual,expected)
                if row['comparison']['status']!='PASS':raise ValueError('Primitive diode currents differ.')
                for fault in ('reverse-pins','wrong-area'):
                    q=clone(p)
                    for d in q['cells'][0]['devices']:
                        if not d.get('model_ref'):continue
                        if fault=='reverse-pins':d['nets']['d0'],d['nets']['d1']=d['nets']['d1'],d['nets']['d0']
                        else:d['model_params']['area']*=1.2
                    dest=folder/fault;dest.mkdir();save_project(q,dest/'input.icproj');bad=run_ngspice(q,q['top'],settings,a.ngspice,dest);write(dest/'response.json',bad);control=compare(bad,expected)
                    if not all(e>1 for e in control['channel_errors'].values()):raise ValueError('Diode fault not detected on every channel: '+fault)
                    row['faults'].append(dict(name=fault,detected=True,comparison=control))
                row['status']='PASS'
            except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
            report['cases'].append(row);write(folder/'record.json',row);write(out/'qualification.json',report);print(name,row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};report['status']='PASS' if report['implementation_unchanged'] and all(r['status']=='PASS' for r in report['cases']) else 'FAIL';write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
