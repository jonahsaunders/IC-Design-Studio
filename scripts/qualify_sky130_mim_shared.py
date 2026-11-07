"""Finite shared-bottom MiM import/DRC/LVS evidence; no RC or family claim."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio.catalog import link_technology
from icstudio.interchange import export_layout
from icstudio.layout import polygon,rect
from icstudio.layout_import import read_layout
from icstudio.layout_verification import run,reference
from icstudio.model import file_digest,save_project
from icstudio.sky130_mim2_extract import MODELS
from icstudio.sky130_rf_verification import drc
from scripts.qualify_sky130_mim2 import fixture,independent
from scripts.qualify_standard_mos_layout import technology


def write(path,value):
    path.write_bytes((json.dumps(value,indent=2,allow_nan=False)+'\n').encode())


def shared_project(tech,plate):
    project=fixture(tech,(2,10,2),plate=plate);cell=project['cells'][0]
    pair=MODELS[f'sky130_fd_pr__cap_mim_m3_{plate}']['bottom']
    layer=next(r['name'] for r in tech['layers'] if (r['gds'],r['datatype'])==pair)
    boxes=sorted((polygon(s).bbox() for s in cell['shapes'] if s['layer']==layer),key=lambda b:b.bottom)
    if len(boxes)!=2:raise ValueError('Expected two separately contacted source units.')
    first,second=boxes
    cell['shapes'].append(rect(layer,first.left,first.top,first.width(),second.bottom-first.top,net='N'))
    return project


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sky130',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    from scripts.audit_sky130_mim_shared import inventory,source_files,verify
    from scripts.check_ihp_cmim_enclosures import safe_path
    if sys.platform!='linux':raise ValueError('Run on a verified native Linux source snapshot.')
    out=safe_path(args.output.absolute()).resolve()
    if out.exists() or out.is_relative_to(ROOT):raise ValueError('Choose a fresh directory outside the source snapshot.')
    out.mkdir(parents=True)
    tech,package=technology('sky130A',args.sky130)
    for name in ('package.json','LICENSE-PDK.txt','NOTICE-QUALIFICATION.txt'):
        shutil.copyfile(args.sky130/name,out/('adapter-'+name))
    tools={name:str(Path(shutil.which(name)).resolve(strict=True)) for name in ('magic','netgen','klayout')}
    guarded=source_files()
    report={'schema':1,'status':'RUNNING','scope':__doc__,'qualified':False,'installed_acceptance':False,
            'source_files':guarded,'package':package,'tools':{n:{'path':p,'sha256':file_digest(p)} for n,p in tools.items()},'cases':[]}
    import klayout.db as db
    for plate in (1,2):
        original=out/f'plate{plate}.gds';export_layout(shared_project(tech,plate),original)
        for mode,angle in (('positive',0),('positive',90),('missing-contact-group',0),('wrong-width',0),('wrong-count',0)):
            name=f'p{plate}-{mode}-{angle}';folder=out/name;folder.mkdir()
            layout=db.Layout();layout.read(str(original));cell=layout.top_cell()
            if mode=='missing-contact-group':
                spec=MODELS[f'sky130_fd_pr__cap_mim_m3_{plate}'];caps=db.Region(cell.shapes(layout.layer(*spec['cap']))).merged()
                cuts=cell.shapes(layout.layer(*spec['cut']));kept=db.Region()
                for cut in db.Region(cuts).each():
                    if (db.Region(cut)-caps).is_empty() or cut.bbox().top<10000:kept.insert(cut)
                cuts.clear();cuts.insert(kept)
            cell.transform(db.Trans(angle//90,False,0,0));layout.write(str(folder/'input.gds'))
            project,_=read_layout(folder/'input.gds');link_technology(project,tech);project['cells'][0]['ports']=['P','N']
            save_project(project,folder/'input.icproj')
            size=(3,10,2) if mode=='wrong-width' else (2,10,1) if mode=='wrong-count' else (2,10,2)
            text=independent(size,plate=plate);(folder/'reference.spice').write_bytes(text.encode())
            result=run(project,project['top'],folder/'job',tools,reference(text,'device_coupon'))
            item={'name':name,'plate':plate,'angle':angle,'mode':mode,'status':result['status'],'error':result.get('error'),
                  'stages':{r['name']:r['status'] for r in result['stages']}}
            if mode=='positive':item['public_drc']=drc(tools['klayout'],folder/'job/layout.gds','device_coupon',tech,folder/'public-drc')
            report['cases'].append(item);write(out/'report.json',report);print(json.dumps(item),flush=True)
    if source_files()!=guarded:raise ValueError('Source changed during shared MiM verification.')
    technology('sky130A',args.sky130)
    if any(file_digest(row['path'])!=row['sha256'] for row in report['tools'].values()):raise ValueError('Selected native launcher changed.')
    report.update(status='OBSERVED',files=inventory(out));write(out/'report.json',report)
    receipt=verify(out);write(out/'verification.json',receipt);print(json.dumps(receipt),flush=True)


if __name__=='__main__':main()
