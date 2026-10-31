"""Verify the fixed 20 V interface against independently changed model calls.

Selected DC/AC conditions only. The public model has fixed internal geometry;
within-bin W/L invariance controls check this independently of the app guards.
Multiplicity and terminal faults must still be detected by the common runner.
"""
import argparse,json,re,sys,traceback
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,file_digest
from icstudio.engines import run_deck
from icstudio.pdks import stage_model_deck
from scripts.qualify_mos_variants import case,compare,fixture,independent,probes
from scripts.qualify_standard_mos import write


def check(tech,corner,temp,drive,out,engine):
    record=case(tech,'sky-hv',corner,temp,drive,out,engine,[])
    folder=out/record['name']
    if record['status']=='PASS' and drive in ('dc','g'):
        record['ignored_geometry_controls']=[]
        try:
            reference=json.loads((folder/'independent/comparison-result.json').read_bytes())
            # Both controls stay inside the explicit lmin/lmax/wmin/wmax bins
            # of all five public models. Wider changes can fail bin selection.
            for dimension,factor in (('w',.9),('l',.999)):
                text=independent(tech,'sky-hv',drive,corner,temp)
                lines=[]
                for line in text.splitlines():
                    if line.startswith('Xq'):
                        line,n=re.subn(r'\b'+dimension+r'=([0-9.]+)\b',lambda m:dimension+'='+format(float(m[1])*factor,'.12g'),line)
                        if n!=1:raise ValueError('Geometry control failed to change exactly one instance parameter.')
                    lines.append(line)
                dest=folder/('ignored-'+dimension);dest.mkdir();deck=stage_model_deck(tech,'\n'.join(lines)+'\n',dest)
                path=dest/'reference.cir';path.write_bytes(deck.encode())
                p=fixture(tech,'sky-hv',drive,[])
                settings=dict(type='dc' if drive=='dc' else 'ac')
                response=run_deck(p,p['top'],dict(deck=str(path),analysis=settings),engine,dest)
                write(dest/'comparison-result.json',response)
                result=compare(response,reference,list(probes('sky-hv')),drive)
                record['ignored_geometry_controls'].append(dict(dimension=dimension,factor=factor,comparison=result,raw_sha256=file_digest(dest/'deck.raw')))
                if result['status']!='PASS':raise ValueError('Public model responded to the supposedly ignored '+dimension+'.')
        except Exception as e:record.update(status='FAIL',error=repr(e),traceback=traceback.format_exc())
    write(folder/'record.json',record);return record


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--ngspice',required=True);p.add_argument('--workers',type=int,choices=range(1,9),default=4);a=p.parse_args()
    package=json.loads((a.package/'package.json').read_bytes())
    for rel,h in package['files'].items():
        path=(a.package/rel).resolve()
        if not path.is_relative_to(a.package.resolve()) or file_digest(path)!=h:raise ValueError('Changed package asset: '+rel)
    tech=clone(package['technology']);tech.update(package_root=str(a.package.resolve()),package_lock={k:package[k] for k in ('id','revision','files')})
    a.output.mkdir(parents=True,exist_ok=False)
    sources=[*sorted((ROOT/'icstudio').rglob('*.py')),*sorted((ROOT/'scripts').glob('*.py'))]
    before={f.relative_to(ROOT).as_posix():file_digest(f) for f in sources};write(a.output/'source-files.json',before)
    report=dict(schema=1,status='RUNNING',chunk=7,chunk_complete=False,scope=__doc__,cases=[],manifest_sha256=file_digest(a.package/'package.json'),revision=package['revision'],engine_sha256=file_digest(a.ngspice),source_files_sha256=file_digest(a.output/'source-files.json'))
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(check,tech,c,t,d,a.output,a.ngspice) for c in ('nominal','ss','ff') for t in (0,27,85) for d in ('dc','d','g','s','b','sub')]
        for job in as_completed(jobs):
            r=job.result();report['cases'].append(r);write(a.output/'qualification.json',report);print(r['name'],r['status'],r.get('error',''),flush=True)
    report['implementation_unchanged']=before=={f.relative_to(ROOT).as_posix():file_digest(f) for f in sources}
    report['cases'].sort(key=lambda r:r['name']);report['status']='PASS' if report['implementation_unchanged'] and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    write(a.output/'qualification.json',report);return int(report['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
