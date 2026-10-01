"""Exercise real process simulation, DRC/LVS faults, repairs and evidence integrity.

Use an empty output directory and a full checksummed process package. No model
or physical-tool substitutes are used. A missing capability makes this fail.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,digest,file_digest,atomic_write,save_project
from icstudio import student_inverter as course
from icstudio.student_hub import curriculum
from icstudio.student_learning import study_guide


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdk-manifest',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    for name in ('ngspice','magic','netgen'):parser.add_argument('--'+name,default='')
    parser.add_argument('--runtime-record',type=Path,help='Existing managed runtime ready record; runtime identity and installed files are reverified by the backend.')
    parser.add_argument('--osdi-directory',type=Path,help='Native IHP model build with build.json and its six compiled libraries.')
    args=parser.parse_args();out=args.out.resolve()
    if out.exists() and any(out.iterdir()):parser.error('Use a fresh empty output directory.')
    out.mkdir(parents=True,exist_ok=True)
    m=json.loads(args.pdk_manifest.read_text(encoding='utf-8'));tech=clone(m['technology'])
    tech.update(package_root=str(Path(m.get('source_root',args.pdk_manifest.parent)).resolve()),
                package_lock=dict(id=m['id'],revision=m['revision'],manifest_hash=digest(m),files=m['files']))
    item=course.profile(tech);data,_=course.expand(curriculum(),study_guide(curriculum()),[item])
    p=course.create(item);tools={n:getattr(args,n) for n in ('ngspice','magic','netgen')}
    if args.osdi_directory:
        from icstudio.osdi import configure,managed_models
        build=json.loads((args.osdi_directory/'build.json').read_text())
        models=managed_models(p['pdk'],{'osdi':{'ihp-sg13g2':build}})
        p['simulation_runtime']={'osdi':configure([args.osdi_directory/model['output'] for model in models])}
        if any(entry['sha256']!=model['sha256'] for entry,model in zip(p['simulation_runtime']['osdi'],models)):
            raise ValueError('Compiled model differs from its build record.')
    runtime=json.loads(args.runtime_record.read_text())['runtime'] if args.runtime_record else None
    records=[]
    def lesson(stage):return next(l for l in data['lessons'] if l.get('inverter_stage')==stage)
    def run(l,name):
        from icstudio.worker import main as worker
        root=out/name;root.mkdir();job=course.prepare(p,l,tools)
        if runtime and job['settings']['type']=='silicon':
            job['settings'].pop('physical_blocked_reason',None);job['settings']['physical_runtime']=runtime
        atomic_write(root/'input.json',json.dumps(job))
        if worker(str(root/'input.json'),str(root/'result.json')):raise ValueError('Worker failed for '+name)
        result=json.loads((root/'result.json').read_text(encoding='utf-8'))
        return dict(state='Complete',path=str(root),job=job,result=result)
    for stage,check in [('dc','dc'),('transient','tran')]:
        l=lesson(stage);row=run(l,stage)
        records.append(dict(stage=stage,evidence=course.check(p,l,dict(check=check),[row])))
    course.build_layout(p);course.check(p,lesson('layout'),dict(check='layout'),[])
    save_project(p,out/'inverter.icproj')
    for kind in ('drc','lvs'):
        l=lesson(kind);course.fault(p,kind);row=run(l,kind+'-fault')
        records.append(dict(stage=kind+'-fault',evidence=course.check(p,l,dict(check=kind+'-failure'),[row])))
        try:course.check(p,l,dict(check=kind),[row])
        except ValueError:pass
        else:raise AssertionError('Fault earned repaired credit')
        course.repair(p);row=run(l,kind+'-repaired')
        records.append(dict(stage=kind+'-repaired',evidence=course.check(p,l,dict(check=kind),[row])))
        if kind=='lvs':records.append(dict(stage='final-both',evidence=course.check(p,l,dict(check='handoff'),[row])))
        evidence=Path(row['result']['evidence_directory'])/'lvs/lvs.log'
        original=evidence.read_bytes();evidence.write_bytes(original+b'\nchanged evidence\n')
        try:
            try:course.check(p,l,dict(check=kind),[row])
            except ValueError as exc:
                if 'changed' not in str(exc):raise
            else:raise AssertionError('Altered verification evidence was accepted')
        finally:evidence.write_bytes(original)
    report=dict(status='passed',pdk=m['id'],revision=m['revision'],checks=records,
                environment=records[0]['evidence']['environment'])
    atomic_write(out/'checks.json',json.dumps(report,indent=2));print('QUALIFICATION PASSED',m['id'])


if __name__=='__main__':main()
