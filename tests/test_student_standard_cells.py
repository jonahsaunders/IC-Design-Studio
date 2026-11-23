"""Exercise starter repairs, physical connectivity and captured native logic runs."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from icstudio import student_cell_layout as geometry, student_standard_cells as cells
from icstudio.model import atomic_write
from icstudio.student_hub import curriculum, evaluate
from icstudio.student_projects import create, lesson_workspace
from icstudio.worker import main


NGSPICE = os.environ.get('ICSTUDIO_TEST_NGSPICE', '')


def route(project, cell):
    for net, params in cell['student_cell_layout']['breaks'].items():
        geometry.close_gap(project, cell, net, **params)


class StandardCellLessons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lessons = {lesson['standard_cell']: lesson for lesson in curriculum()['lessons']
                       if lesson.get('standard_cell')}

    def test_all_layout_starters_have_two_measurable_gaps(self):
        self.assertEqual(set(self.lessons), {'inv', 'nand2', 'nor2', 'aoi21', 'mux2', 'dff'})
        for key, lesson in self.lessons.items():
            with self.subTest(key=key):
                project = create(lesson['starter'])
                place, routing = lesson['steps'][1:3]
                cell, _ = cells.context(project, key)
                self.assertEqual(lesson_workspace(project, lesson, 'place'), (cell['id'], 'layout'))
                self.assertEqual(lesson_workspace(project, lesson, 'verify'), (cell['id'], 'layout'))
                with self.assertRaisesRegex(ValueError, 'Place cell rows'):
                    evaluate(place, lesson, project)
                cells.build_layout(project, key)
                evidence = evaluate(place, lesson, project)
                self.assertEqual(evidence['physical_ports'][-2:], ['VPWR', 'VGND'])
                self.assertEqual(geometry.open_nets(project, cell), {'VPWR', cells.output_pin(key)})
                with self.assertRaisesRegex(ValueError, 'disconnected'):
                    evaluate(routing, lesson, project)
                route(project, cell)
                evidence = evaluate(routing, lesson, project)
                self.assertEqual(evidence['height_um'], 24.5)
                self.assertIn(cells.output_pin(key), evidence['connected_nets'])

    def test_inverter_physical_ports_and_geometry(self):
        lesson = self.lessons['inv']
        step = next(s for s in lesson['steps'] if s['id'] == 'route')
        project = create(lesson['starter'])
        cells.build_layout(project, 'inv')
        cell, _ = cells.context(project, 'inv')
        route(project, cell)
        evidence = evaluate(step, lesson, project)
        self.assertEqual(evidence['physical_ports'], ['A', 'Y', 'VPWR', 'VGND'])
        cell['shapes'][-1]['width'] = 320
        with self.assertRaisesRegex(ValueError, 'minimum width'):
            evaluate(step, lesson, project)

    @unittest.skipUnless(Path(NGSPICE).is_file(), 'Set ICSTUDIO_TEST_NGSPICE for native SKY130 simulation')
    def test_real_truth_tables_capture_hold_and_stale_evidence(self):
        with tempfile.TemporaryDirectory(prefix='sc-') as folder:
            for key, lesson in self.lessons.items():
                with self.subTest(key=key):
                    project = create(lesson['starter'])
                    cells.build_layout(project, key)
                    cell, _ = cells.context(project, key)
                    route(project, cell)
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
                    self.assertEqual(len(evidence['schematic_samples']), len(cells.samples(key)))
                    self.assertTrue(evidence['capacitance_estimate'])
                    shape = cell['shapes'][-1]
                    width = shape['width']
                    shape['width'] += 10
                    with self.assertRaisesRegex(ValueError, 'latest edits'):
                        evaluate(step, lesson, project, [row])
                    shape['width'] = width
                    (root/'layout/engine.log').write_text('Changed log', encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, 'artifact has changed'):
                        evaluate(step, lesson, project, [row])


if __name__ == '__main__':
    unittest.main()
