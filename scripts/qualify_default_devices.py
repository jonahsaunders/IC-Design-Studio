"""Exercise the promoted device packages through ordinary project creation.

This is a nominal installation regression, not complete device qualification.
Independent model calls and deliberate faults reuse the declared family gates.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest,load_project,save_project
from icstudio.osdi import configure
from icstudio.pdks import PDKRegistry
from icstudio.project_hub import inventory,build_project
from scripts.device_qualification_source import PROMOTED,REVISIONS
from scripts.qualify_standard_mos import case_run,write
from scripts import qualify_capacitor_families as caps
from scripts import qualify_four_terminal_capacitors as four
from scripts import qualify_mos_variants as mos


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--ngspice',required=True)
    ap.add_argument('--osdi',type=Path,required=True)
    ap.add_argument('--workers',type=int,choices=range(1,9),default=4)
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    osdi=configure(sorted(a.osdi.glob('*.osdi')))
    sources=[*sorted((ROOT/'icstudio').rglob('*.py')),*sorted((ROOT/'scripts').glob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    write(out/'source-files.json',before)
    report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',cases=[],processes={},
        scope='New-project default installation, selected nominal electrical comparisons and deliberate faults; complete operating envelopes and physical device qualification remain separate.',
        source_files_sha256=file_digest(out/'source-files.json'),engine_sha256=file_digest(a.ngspice),osdi=osdi)
    registry=PDKRegistry(out/'registry');rows,notes=inventory(registry)
    if notes:raise ValueError('Default discovery has diagnostics: '+repr(notes))
    technologies={}
    for target in PROMOTED:
        source=ROOT/'icstudio/assets/pdks'/target/'package.json'
        if file_digest(source)!=PROMOTED[target]:raise ValueError('Unreviewed default package: '+target)
        row=next(r for r in rows if r['id']==target and r['status']=='Available offline')
        if row['revision']!=REVISIONS[target]:raise ValueError('Unexpected default selection: '+target)
        project=build_project(registry,row,'Default regression '+target,'empty')['project']
        saved=out/(target+'.icproj');save_project(project,saved);reopened=load_project(saved)
        tech=reopened['pdk'];installed=Path(tech['package_root'])/'package.json'
        if tech!=project['pdk'] or json.loads(installed.read_bytes())!=json.loads(source.read_bytes()):
            raise ValueError('Installed or reopened default changed: '+target)
        registry.verify(row['key']);technologies[target]=tech
        report['processes'][target]=dict(revision=tech['revision'],bundled_manifest_sha256=PROMOTED[target],
            installed_manifest_sha256=file_digest(installed),project_sha256=file_digest(saved),key=row['key'])
    jobs={}
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for name in ('standard-mos','mos-variants','capacitors','four-terminal'):(out/name).mkdir()
        for target,tech in technologies.items():
            for polarity in ('n','p'):
                j=pool.submit(case_run,tech,target,polarity,'interior','nominal',27,out/'standard-mos',a.ngspice,osdi)
                jobs[j]='standard-mos'
            for drive in range(max(len(r['pins']) for r in caps.probes(target))):
                j=pool.submit(caps.case,tech,target,drive,.5,'nominal',27,out/'capacitors',a.ngspice,osdi,target=='sky130A')
                jobs[j]='capacitors'
        for target in ('sky130A','ihp-sg13g2'):
            for drive in range(4):
                j=pool.submit(four.case,technologies[target],target,drive,.5,'nominal',27,out/'four-terminal',a.ngspice,osdi)
                jobs[j]='four-terminal'
        for group,(target,_) in mos.GROUPS.items():
            for drive in ['dc',*dict.fromkeys(p for r in mos.probes(group) for p in r['pins'])]:
                j=pool.submit(mos.case,technologies[target],group,'nominal',27,drive,out/'mos-variants',a.ngspice,osdi)
                jobs[j]='mos-variants'
        report['expected_cases']=len(jobs);write(out/'qualification.json',report)
        for job in as_completed(jobs):
            row=job.result();row['family']=jobs[job];report['cases'].append(row)
            write(out/'qualification.json',report);print(row['family'],row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['implementation_unchanged'] and len(report['cases'])==report['expected_cases'] and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda r:(r['family'],r['name']));write(out/'qualification.json',report)
    return int(report['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
