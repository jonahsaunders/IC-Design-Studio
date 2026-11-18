"""Repeat the actual bandgap lesson workers and their grading checkpoints."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from icstudio.model import atomic_write, save_project, load_project
from icstudio.student_bandgap import NAMES
from icstudio.student_bandgap_lab import check, prepare
from icstudio.student_bandgap_layout import generate
from icstudio.student_projects import create
from icstudio.worker import main as worker


def qualify(kind, stages, tools, folder):
    p = create('bandgap-lab-'+kind)
    folder.mkdir()
    source = folder/'lesson.icproj'
    report = {'topology':kind,'stages':{}}
    for stage in stages:
        if stage=='post-layout':
            if kind!='banba':
                generate(p)
            report['layout'] = check(p,'layout',[])
        save_project(p,source)
        p = load_project(source)
        job, = prepare(p,stage,tools)
        directory = folder/stage
        directory.mkdir()
        inputs,outputs = directory/'input.json',directory/'result.json'
        atomic_write(inputs,json.dumps(job))
        if worker(inputs,outputs):
            report['stages'][stage] = {'error':'Lesson worker failed'}
            continue
        result = json.loads(outputs.read_text(encoding='utf-8'))
        captured = {'state':'Complete','job':job,'path':directory,'result':result}
        rows = result['bandgap_rows']
        summary = dict(passed=sum(row['status']=='passed' for row in rows), runs=len(rows),
                       failures=[{k:r[k] for k in ('bench','corner','temperature','supply_V','errors')}
                                 for r in rows if r['status']!='passed'])
        for suffix in ('schematic_temperature_span_V','extracted_temperature_span_V','extraction'):
            if suffix in result:
                summary[suffix] = result[suffix]
        summary['maximum_peak_V'] = max((v['values'].get('peak_V',0) for r in rows
                                         for s in ('schematic','extracted') if (v:=r.get(s))),default=0)
        summary['max_final_shift_V'] = max((abs(r.get('delta_V',0)) for r in rows),default=0)
        try:
            check(p,stage,[captured])
            summary['status'] = 'passed'
        except (ValueError, KeyError) as error:
            summary.update(status='failed',error=str(error))
        report['stages'][stage] = summary
        print(kind,stage,json.dumps(summary),flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--ngspice',default=shutil.which('ngspice'))
    parser.add_argument('--magic',default=shutil.which('magic'))
    parser.add_argument('--topology',choices=list(NAMES),action='append')
    parser.add_argument('--stage',choices=['accuracy','startup','post-layout'],action='append')
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    if any(args.out.iterdir()):
        parser.error('Choose an empty evidence directory.')
    kinds = args.topology or list(NAMES)
    stages = args.stage or ['accuracy','startup','post-layout']
    tools = dict(ngspice=args.ngspice,magic=args.magic)
    with ThreadPoolExecutor(max_workers=min(4,len(kinds))) as pool:
        reports = list(pool.map(lambda kind:qualify(kind,stages,tools,args.out.resolve()/kind), kinds))
    atomic_write(args.out/'report.json',json.dumps(reports,indent=2,allow_nan=False)+'\n')
    return int(any(stage.get('status')!='passed' for report in reports for stage in report['stages'].values()))


if __name__=='__main__':
    raise SystemExit(main())
