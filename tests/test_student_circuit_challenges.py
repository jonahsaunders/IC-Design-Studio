"""Exercise failing and passing circuit-design and passive-layout lessons."""

import io
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import tempfile
import unittest

from icstudio import student_signal_labs as signal, student_testbench as benches, testbenches
from icstudio.model import atomic_write
from icstudio.student_hub import curriculum, evaluate
from icstudio.student_layout_passives import place_decap, route_mim
from icstudio.student_projects import create
from icstudio.worker import main

NGSPICE = os.environ.get('ICSTUDIO_TEST_NGSPICE', '')
SOLUTIONS = {
    'floating-voltage': {'BMETER': [('nets','ref','lo')]},
    'open-drain': {'RPULL': [(None,'value','4.7k')]},
    'switch-drive': {'MSW': [('params','w','400u')], 'VGATE': [('source','high','1.8')]},
    'weak-sensor': {'RINPUT': [(None,'value','1g')], 'RISO': [(None,'value','1k')]},
    'window-detector': {'VLOW': [(None,'value','.55')], 'VHIGH': [(None,'value','1.25')]},
    'swcap-gain': {'CS': [(None,'value','2p')]},
    'tunable-gmc': {'CFILT': [(None,'value','318p')]},
}


class EngineeringLessonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lessons = {l['id']:l for l in curriculum()['lessons']}

    def run_job(self, job, folder):
        inp, out = folder/'input.json', folder/'result.json'
        atomic_write(inp,json.dumps(job))
        log = io.StringIO()
        with redirect_stdout(log):
            status = main(inp,out)
        self.assertEqual(status,0,log.getvalue())
        return dict(job=job,result=json.loads(out.read_text(encoding='utf-8')),
                    path=folder,state='Complete')

    def test_layout_routes_drive_the_measured_improvement(self):
        for key, move in [('mim-plate',lambda p:route_mim(p,0)),('decoupling',lambda p:place_decap(p,2000))]:
            lesson = self.lessons['l-'+key]
            project = create(lesson['starter'])
            before, after = lesson['steps'][1:3]
            baseline = evaluate(before,lesson,project)['layout_study']
            with self.assertRaises(ValueError):
                evaluate(after,lesson,project)
            move(project)
            tuned = evaluate(after,lesson,project)['layout_study']
            metric = next(iter(baseline))
            self.assertLess(tuned[metric],baseline[metric]/2)

    @unittest.skipUnless(Path(NGSPICE).is_file(),'Set ICSTUDIO_TEST_NGSPICE for native measurements')
    def test_signal_starters_fail_tuned_targets_and_saved_results_pass(self):
        indexed = {l['signal_lab']:l for l in self.lessons.values() if 'signal_lab' in l}
        with tempfile.TemporaryDirectory(prefix='scn-') as tmp:
            for key, changes in SOLUTIONS.items():
                with self.subTest(key=key):
                    lesson = indexed[key]
                    project = create(lesson['starter'])
                    before, repair = lesson['steps'][1:3]
                    starter = signal.prepare(project,lesson,'baseline',{'ngspice':NGSPICE})
                    evidence = self.run_job(starter,Path(tmp)/key/'starter')
                    self.assertTrue(evaluate(before,lesson,project,[evidence])['signal_measurements'])
                    for name, edits in changes.items():
                        part = next(d for d in project['cells'][0]['devices'] if d['name']==name)
                        for section, field, value in edits:
                            (part[section] if section else part)[field] = value
                    if key=='floating-voltage':
                        cell = project['cells'][0]
                        for name in ('wires','labels','junctions','example_drawing'):
                            cell.pop(name,None)
                        from icstudio.example_schematics import arrange
                        from icstudio.model import validate
                        validate(arrange(project))
                    job = signal.prepare(project,lesson,'repair',{'ngspice':NGSPICE})
                    result = self.run_job(job,Path(tmp)/key/'tuned')
                    self.assertTrue(evaluate(repair,lesson,project,[result])['signal_measurements'])

    @unittest.skipUnless(Path(NGSPICE).is_file(),'Set ICSTUDIO_TEST_NGSPICE for native measurements')
    def test_balanced_stimulus_in_both_workflows(self):
        key = 'tb-balanced-stimulus'
        lesson,unit = self.lessons[key],benches.course()[key]
        project = create(lesson['starter'])
        cid = benches.fixture(project,key)
        c = next(c for c in project['cells'] if c['id']==cid)
        minus = next(d for d in c['devices'] if d['name']=='VMINUS')
        minus['source'].update(low='.95',high='.85')
        bench = testbenches.create(project,cid)
        bench['analysis'].update(unit['analysis'],temperature=27,corner='nominal')
        bench['probes'] = benches.probes(unit)
        bench['measurements'] = [benches.measurement(unit)]
        project['testbenches'].append(bench)
        project['student_bench']['programs'][key] = benches.program(unit)
        with tempfile.TemporaryDirectory(prefix='bald-') as tmp:
            for mode in benches.WORKFLOWS:
                job = benches.prepare(project,lesson,mode,{'ngspice':NGSPICE})
                row = self.run_job(job,Path(tmp)/mode)
                proof = evaluate(lesson['steps'][1],lesson,project,[row])
                self.assertAlmostEqual(proof['bench_reading'],.1,places=4)
                self.assertEqual(proof['bench_workflow'],mode)
            minus['source']['delay'] = '6u'
            for mode in benches.WORKFLOWS:
                job = benches.prepare(project,lesson,mode,{'ngspice':NGSPICE})
                row = self.run_job(job,Path(tmp)/(mode+'-skewed'))
                with self.assertRaisesRegex(ValueError,'Peak common-mode error'):
                    evaluate(lesson['steps'][1],lesson,project,[row])
