"""Exercise starter repairs, physical connectivity and captured native logic runs."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from icstudio import student_standard_cells as cells
from icstudio.model import atomic_write
from icstudio.student_hub import curriculum, evaluate
from icstudio.student_projects import create, lesson_workspace
from icstudio.wiring import set_label
from icstudio.worker import main


NGSPICE = os.environ.get('ICSTUDIO_TEST_NGSPICE', '')


def fix(project, key):
    cell, _ = cells.context(project, key)
    by_name = {part['name']: part for part in cell['devices']}
    connections = {name: cells.terminals(kind, gate, drain, source)
                   for kind, name, gate, drain, source in cells.network(key)}
    for name, pin, _ in cells.course()[key]['faults']:
        set_label(cell, by_name[name]['id'], pin, connections[name][pin], project)


class StandardCellLessons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lessons = {lesson['standard_cell']: lesson for lesson in curriculum()['lessons']
                       if lesson.get('standard_cell')}

    def test_starter_repair_using_native_pin_labels(self):
        self.assertEqual(set(self.lessons), {'inv', 'nand2', 'nor2', 'aoi21', 'mux2', 'dff'})
        for key, lesson in self.lessons.items():
            with self.subTest(key=key):
                project = create(lesson['starter'])
                wire = lesson['steps'][1]
                cell, fixture = cells.context(project, key)
                self.assertEqual(lesson_workspace(project, lesson, 'wire'), (cell['id'], 'schematic'))
                self.assertEqual(lesson_workspace(project, lesson, 'verify'), (fixture['id'], 'schematic'))
                with self.assertRaisesRegex(ValueError, 'Connect '):
                    evaluate(wire, lesson, project)
                fix(project, key)
                evidence = evaluate(wire, lesson, project)
                self.assertEqual(evidence['ports'][-2:], ['VPWR', 'VGND'])

    def test_inverter_physical_ports_and_geometry(self):
        lesson = self.lessons['inv']
        step = next(s for s in lesson['steps'] if s['id'] == 'physical')
        project = create(lesson['starter'])
        fix(project, 'inv')
        cells.build_layout(project)
        evidence = evaluate(step, lesson, project)
        self.assertEqual(evidence['physical_ports'], ['A', 'VGND', 'VPWR', 'Y'])
        cell, _ = cells.context(project, 'inv')
        cell['shapes'].clear()
        with self.assertRaises(ValueError):
            evaluate(step, lesson, project)

    @unittest.skipUnless(Path(NGSPICE).is_file(), 'Set ICSTUDIO_TEST_NGSPICE for native SKY130 simulation')
    def test_real_truth_tables_capture_hold_and_stale_evidence(self):
        with tempfile.TemporaryDirectory(prefix='sc-') as folder:
            for key, lesson in self.lessons.items():
                with self.subTest(key=key):
                    project = create(lesson['starter'])
                    fix(project, key)
                    step = next(s for s in lesson['steps'] if s['id'] == 'verify')
                    root = Path(folder) / key
                    job = cells.prepare(project, lesson, {'ngspice': NGSPICE})
                    inp, out = root/'input.json', root/'result.json'
                    atomic_write(inp, json.dumps(job))
                    log = io.StringIO()
                    with redirect_stdout(log):
                        status = main(inp, out)
                    self.assertEqual(status, 0, log.getvalue())
                    result = json.loads(out.read_text(encoding='utf-8'))
                    row = dict(job=job, result=result, path=root, state='Complete')
                    evidence = evaluate(step, lesson, project, [row])
                    self.assertEqual(len(evidence['logic_samples']), len(cells.samples(key)))
                    cell, _ = cells.context(project, key)
                    cell['devices'][0]['params']['w'] = '3u'
                    with self.assertRaisesRegex(ValueError, 'latest edits'):
                        evaluate(step, lesson, project, [row])


if __name__ == '__main__':
    unittest.main()
