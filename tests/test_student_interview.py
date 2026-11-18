"""Revision-bound interview evidence, seeded trials, and the layout repair."""

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from icstudio.model import atomic_write, clone
from icstudio.student_hub import curriculum, evaluate
from icstudio.student_interview import BENCHES, prepare
from icstudio.student_projects import create
from icstudio.worker import main


class InterviewLabs(unittest.TestCase):
    def setUp(self):
        self.lessons = {l['id'].removeprefix('interview-'):l for l in curriculum()['lessons']
                        if l.get('analog_project')=='interview'}

    def check_step(self, p, kind, key, out):
        lesson = self.lessons[kind]
        step = next(step for step in lesson['steps'] if step['id']==key)
        rows = []
        for job in prepare(p,key,{}):
            folder = out/job['student_analog']['bench']
            folder.mkdir(parents=True)
            ip,op = folder/'input.json',folder/'result.json'
            atomic_write(ip,json.dumps(job))
            self.assertEqual(main(ip,op),0)
            rows.append(dict(state='Complete',path=folder,job=job,result=json.loads(op.read_text())))
        return evaluate(step,lesson,p,rows),rows,step

    def test_every_lesson_opens_a_circuit_with_a_saved_experiment(self):
        self.assertEqual(len(self.lessons),10)
        for kind,lesson in self.lessons.items():
            p = create(lesson['starter'])
            self.assertEqual(p['student_interview'],kind)
            for step in lesson['steps']:
                if step['kind']=='check':
                    self.assertIn(step['id'],BENCHES)

    def test_mismatch_area_halves_sigma_and_saved_evidence_goes_stale(self):
        p = create('interview-mismatch')
        with TemporaryDirectory() as directory:
            record,rows,step = self.check_step(p,'mismatch','mismatch',Path(directory))
            a,b = (record['interview_measurements'][size] for size in ('small','large'))
            key = 'Sample input-referred sigma (mV)'
            self.assertAlmostEqual(b[key]/a[key],.5,delta=.02)
            self.assertGreater(b['Within ±8 mV (of 64)'],a['Within ±8 mV (of 64)'])
            edited = clone(p)
            next(d for d in edited['cells'][0]['devices'] if d['name']=='RL')['value'] = '15k'
            with self.assertRaisesRegex(ValueError,'latest edits'):
                evaluate(step,self.lessons['mismatch'],edited,rows)

    def test_layout_timing_failure_and_repair_use_same_input_trace(self):
        p = create('interview-post-layout-debug')
        with TemporaryDirectory() as directory:
            out = Path(directory)
            baseline,_,_ = self.check_step(p,'post-layout-debug','route-baseline',out/'baseline')
            next(s for s in p['cells'][0]['shapes'] if s['kind']=='path')['width'] = 400
            repaired,_,_ = self.check_step(p,'post-layout-debug','route-repair',out/'repair')
            first,last = (v['interview_measurements'] for v in (baseline,repaired))
            self.assertEqual(first['before'],last['before'])
            self.assertGreater(first['after']['2% settling (ps)'],50.)
            self.assertLess(last['after']['2% settling (ps)'],50.)
