"""Require real simulators; retain positive cases and deliberately faulty designs."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

from icstudio.model import atomic_write,design_digest,file_digest,save_project
from icstudio.mixed_signal import prepare,run
from icstudio.student_capstone import project,case_project,report,CASES


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=ROOT/'build/student-capstone')
    for name in ('ngspice','iverilog','vvp'):parser.add_argument('--'+name)
    args=parser.parse_args();out=args.out.resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Choose a new evidence directory; existing captures are preserved.')
    out.mkdir(parents=True,exist_ok=True);tools={n:getattr(args,n) for n in ('ngspice','iverilog','vvp')}
    base=project();save_project(base,out/'sensor-reference.icproj');results=[]
    for name in [*CASES,'fault-filter','fault-decision','fault-average','fault-alarm']:
        p=case_project(base,name) if name in CASES else project()
        files=p['cells'][1]['digital']['files']
        if name=='fault-filter':next(d for d in p['cells'][0]['devices'] if d['name']=='Cfilter')['value']='1n'
        elif name=='fault-decision':files[0]['text']=files[0]['text'].replace('if (!cmp)','if (cmp)')
        elif name=='fault-average':files[1]['text']=files[1]['text'].replace('>> 2','>> 1')
        elif name=='fault-alarm':files[1]['text']=files[1]['text'].replace('>= 10','>= 15')
        root=out/name;root.mkdir();job=prepare(p,tools);atomic_write(root/'input.json',json.dumps(job))
        result=run(job,root);atomic_write(root/'result.json',json.dumps(result));atomic_write(root/'status.json',json.dumps({'status':'complete'}))
        checked=report(result,name if name in CASES else 'nominal');expected='PASS' if name in CASES else 'FAIL'
        record=dict(name=name,expected=expected,passed=checked['status']==expected,report=checked,
            design_hash=design_digest(p),input_sha256=file_digest(root/'input.json'),result_sha256=file_digest(root/'result.json'),environment=job['environment'])
        results.append(record);print(name+': '+checked['status']+' (expected '+expected+')',flush=True)
    summary=dict(status='PASS' if all(r['passed'] for r in results) else 'FAIL',
                 checker_sha256=file_digest(ROOT/'icstudio/student_capstone.py'),cases=results)
    atomic_write(out/'report.json',json.dumps(summary,indent=2)+'\n')
    return 0 if summary['status']=='PASS' else 1


if __name__=='__main__':sys.exit(main())
