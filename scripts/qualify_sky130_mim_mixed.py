"""Two independent SKY130 MiM families in one native extraction workspace."""
import argparse,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.catalog import create_device,link_technology
from icstudio.model import clone,example,file_digest,save_project
from icstudio.sky130_devices import install
from icstudio.physical_cells import assign_port
from icstudio.interchange import export_layout
from icstudio.layout_import import read_layout
from icstudio.layout_verification import run,reference
from scripts.qualify_standard_mos_layout import technology
from scripts.qualify_sky130_threshold_layouts import rejected
from icstudio.sky130_rf_verification import drc


def fixture(tech):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0]
    c.update(name='mixed_mim',ports=['P1','N1','P2','N2'])
    for plate,(w,l) in enumerate(((3.005,5.005),(2,10)),1):
        d=create_device(tech,f'sky130_fd_pr/cap_mim_m3_{plate}.sym',f'C{plate}')
        d['model_params'].update(w=w,l=l,mf=1);d['nets']={'c0':f'P{plate}','c1':f'N{plate}'}
        c['devices'].append(d);install(p,c['id'],d['id'])
        if plate==2:
            # Orient the second device perpendicular to the first, then separate
            # them. The imported stream carries no generator metadata.
            for s in c['shapes']:
                if s.get('generated_device')==d['id']:s['points']=[[40000-y,x] for x,y in s['points']]
            for pin in c['layout_pins']:
                if pin['device_id']==d['id']:
                    x,y=pin['point'];pin['point']=[40000-y,x]
        for pin in c['layout_pins']:
            if pin['device_id']==d['id']:assign_port(p,c['id'],d['nets'][pin['pin']],pin['layer'],pin['point'])
    return p


def circuit(fault=None):
    sizes=[(3.005,5.005),(2,10)]
    if fault:sizes[fault-1]=tuple(reversed(sizes[fault-1]))
    return '.subckt mixed_mim P1 N1 P2 N2\n'+'\n'.join(
        f'X{i} P{i} N{i} sky130_fd_pr__cap_mim_m3_{i} w={w} l={l}'
        for i,(w,l) in enumerate(sizes,1))+'\n.ends mixed_mim\n'


def main():
    import klayout.db as db
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('sky130','output','magic','netgen','klayout'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    tech,identity=technology('sky130A',a.sky130);p=fixture(tech);save_project(p,out/'input.icproj')
    export_layout(p,out/'input.gds');tools={n:str(getattr(a,n).resolve(strict=True)) for n in ('magic','netgen','klayout')}
    record=dict(status='RUNNING',scope=__doc__,package=identity,layouts=[],faults=[],qualified=False,chunk_complete=False)
    for mirror in (False,True):
        for angle in range(4):
            name=f'{mirror}-{angle}';ly=db.Layout();ly.read(str(out/'input.gds'))
            ly.top_cell().transform(db.Trans(angle,mirror,-123000,456000));stream=out/(name+'.gds');ly.write(str(stream))
            q,_=read_layout(stream);link_technology(q,tech);q['cells'][0]['ports']=['P1','N1','P2','N2']
            dest=out/name;report=run(q,q['top'],dest,tools,reference(circuit(),'mixed_mim'))
            if report['status']!='passed':raise ValueError(report.get('error'))
            check=drc(tools['klayout'],dest/'layout.gds','mixed_mim',tech,dest/'public-drc')
            if check['violations']:raise ValueError('Mixed-family public DRC failed.')
            text=re.sub(r'\n\s*\+\s*',' ',(dest/'lvs-extraction/extracted.spice').read_text())
            devices=[s.split() for s in text.splitlines() if s.startswith('X')]
            if len(devices)!=2:raise ValueError('Mixed extraction did not preserve two devices.')
            for plate,size in ((1,(3.005,5.005)),(2,(2,10))):
                rows=[s for s in devices if s[3]==f'sky130_fd_pr__cap_mim_m3_{plate}']
                if len(rows)!=1 or rows[0][1:3]!=[f'P{plate}',f'N{plate}']:raise ValueError('Mixed model/terminal mismatch.')
                params=dict(v.split('=',1) for v in rows[0][4:])
                if set(params)-{'w','l'} or tuple(float(params[k]) for k in ('w','l'))!=size:raise ValueError('Mixed model geometry mismatch.')
            record['layouts'].append(dict(name=name,status='PASS',report_sha256=file_digest(dest/'report.json'),public_drc=check))
            if angle==1:
                for fault in (1,2):
                    target=out/f'{name}-swapped-{fault}'
                    bad=run(q,q['top'],target,tools,reference(circuit(fault),'mixed_mim'))
                    if not rejected(bad,target):raise ValueError('Swapped mixed-model geometry was not detected.')
                    record['faults'].append(dict(name=target.name,status='detected',report_sha256=file_digest(target/'report.json')))
            print(name,'PASS',flush=True)
    record['status']='PASS';record['source_sha256']=file_digest(__file__)
    (out/'record.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())


if __name__=='__main__':main()
