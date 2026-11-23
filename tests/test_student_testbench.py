"""Exercise a native run from each editor through the Student Hub grader."""

import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

from icstudio import student_testbench as benches, testbenches
from icstudio.model import atomic_write
from icstudio.student_hub import curriculum, evaluate
from icstudio.student_learning import study_guide
from icstudio.student_projects import create, lesson_workspace
from icstudio.worker import main


NGSPICE = os.environ.get('ICSTUDIO_TEST_NGSPICE', '')


class TestbenchLessonsTests(unittest.TestCase):
    def test_projects_share_three_distinct_fixtures_and_include_two_walkthroughs(self):
        data = curriculum()
        material = study_guide(data)
        projects = {}
        fixtures = set()
        for lesson in [item for item in data['lessons'] if item['path']=='testbenches']:
            with self.subTest(lesson=lesson['id']):
                kind = lesson['bench_project']
                if kind not in projects:
                    projects[kind] = create(lesson['starter'])
                project = projects[kind]
                cid, view = lesson_workspace(project, lesson, 'measure')
                self.assertNotIn(cid, fixtures)
                fixtures.add(cid)
                self.assertEqual(view, 'schematic')
                practice = material['practice'][lesson['id']]['bench_workflows']['measure']
                self.assertTrue(practice['graphical'])
                self.assertTrue(practice['spice'])
                self.assertIn('lesson_value', practice['program'])
                self.assertEqual(len(material['hints'][lesson['id']]['predict']), 4)
        self.assertEqual(len(projects), 3)
        self.assertEqual(len(fixtures), 9)

    @unittest.skipUnless(Path(NGSPICE).is_file(), 'Set ICSTUDIO_TEST_NGSPICE to run the native engines')
    def test_same_divider_reading_and_evidence_from_either_workflow(self):
        lesson = next(item for item in curriculum()['lessons'] if item['id']=='tb-divider-bias')
        key, step = lesson['id'], lesson['steps'][1]
        unit = benches.course()[key]
        project = create(lesson['starter'])
        cid = benches.fixture(project, key)
        divider = next(c for c in project['cells'] if c['name']=='resistor_divider')
        part = next(d for d in divider['devices'] if d['name']=='R2')
        part['value'] = '1k'
        bench = testbenches.create(project, cid)
        bench['analysis'].update(unit['analysis'], temperature=27)
        bench['measurements'] = [benches.measurement(unit)]
        project['testbenches'].append(bench)
        program = benches.program(unit)
        project['student_bench']['programs'][key] = program
        with tempfile.TemporaryDirectory(prefix='stb-') as tmp:
            rows = []
            for workflow in benches.WORKFLOWS:
                folder = Path(tmp)/workflow
                job = benches.prepare(project, lesson, workflow, {'ngspice': NGSPICE})
                inp, out = folder/'input.json', folder/'result.json'
                atomic_write(inp, json.dumps(job))
                log = io.StringIO()
                with redirect_stdout(log):
                    status = main(inp, out)
                self.assertEqual(status, 0, log.getvalue())
                result = json.loads(out.read_text(encoding='utf-8'))
                rows.append(dict(job=job, result=result, state='Complete', path=folder))
                evidence = evaluate(step, lesson, project, rows)
                self.assertEqual(evidence['bench_workflow'], workflow)
                self.assertAlmostEqual(evidence['bench_reading'], .5, places=8)
            part['value'] = '2k'
            with self.assertRaisesRegex(ValueError, 'latest edits'):
                evaluate(step, lesson, project, rows)
            part['value'] = '1k'
            (rows[-1]['path']/'engine.log').write_text('changed', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'artifact has changed'):
                evaluate(step, lesson, project, rows)
        with self.assertRaisesRegex(ValueError, 'lesson_value'):
            benches.validate_program('op', unit)


if __name__ == '__main__':
    unittest.main()
