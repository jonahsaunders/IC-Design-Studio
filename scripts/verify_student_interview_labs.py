"""Replay the Student Hub interview experiments through the normal worker."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from icstudio.model import atomic_write, file_digest
from icstudio.student_analog import _named
from icstudio.student_hub import curriculum, evaluate
from icstudio.student_interview import focus, prepare
from icstudio.student_projects import create
from icstudio.worker import main as worker


def replay(lesson, executable, directory):
    project = create(lesson['starter'])
    kind = project['student_interview']
    report = dict(lesson=lesson['id'], stages={})
    for step in lesson['steps']:
        if step['kind']!='check':
            continue
        key = step['id']
        if key=='route-repair':
            next(s for s in project['cells'][0]['shapes'] if s['kind']=='path')['width'] = 400
        elif key=='sar-repair':
            circuit = next(c for c in project['cells'] if c['id']==focus(project,key,circuit=True))
            _named(circuit,'C3')['value'] = '800f'
        rows = []
        result = {}
        try:
            for job in prepare(project,key,{'ngspice':executable}):
                case = job['student_analog']['bench']
                folder = directory/kind/key/case
                folder.mkdir(parents=True)
                inputs,outputs = folder/'input.json',folder/'result.json'
                atomic_write(inputs,json.dumps(job))
                if worker(inputs,outputs):
                    raise ValueError('Worker failed for '+case)
                wave = json.loads(outputs.read_text(encoding='utf-8'))
                rows.append(dict(state='Complete',path=folder,job=job,result=wave))
            evidence = evaluate(step,lesson,project,rows)
            result.update(status='passed',metrics=evidence['interview_measurements'])
        except (ValueError,KeyError) as error:
            result.update(status='failed',error=str(error))
            from icstudio.student_interview import READOUTS
            try:
                result['metrics'] = READOUTS[key](project,{row['job']['student_analog']['bench']:row['result']
                                                          for row in rows})
            except (ValueError,KeyError):
                pass
        result['worker_results'] = {row['job']['student_analog']['bench']:file_digest(row['path']/'result.json')
                                    for row in rows}
        report['stages'][key] = result
        print('LESSON',lesson['id'],key,json.dumps(result,ensure_ascii=False),flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--ngspice',default=shutil.which('ngspice'))
    parser.add_argument('--lesson',action='append',help='Lesson suffix, such as input-pairs')
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    if any(args.out.iterdir()):
        parser.error('Choose an empty evidence directory.')
    lessons = [lesson for lesson in curriculum()['lessons'] if lesson.get('analog_project')=='interview'
               and (not args.lesson or lesson['id'].removeprefix('interview-') in args.lesson)]
    if not lessons:
        parser.error('Choose an existing interview lesson.')
    with ThreadPoolExecutor(max_workers=min(6,len(lessons))) as pool:
        reports = list(pool.map(lambda lesson:replay(lesson,args.ngspice,args.out.resolve()),lessons))
    atomic_write(args.out/'report.json',json.dumps(reports,ensure_ascii=False,indent=2)+'\n')
    return int(any(stage['status']!='passed' for report in reports for stage in report['stages'].values()))


if __name__=='__main__':
    raise SystemExit(main())
