"""Exercise starter repairs, physical connectivity and captured native logic runs."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from icstudio import student_cell_layout as geometry, student_standard_cells as cells
from icstudio.model import atomic_write, clone
from icstudio.student_hub import curriculum, evaluate
from icstudio.student_projects import create, lesson_workspace
from icstudio.worker import main


NGSPICE = os.environ.get('ICSTUDIO_TEST_NGSPICE', '')
SOLUTIONS = {'inv-compact': {'pitch':'4.8'}, 'nand-drive': {'stack':'2'},
             'dff-clock': {'q_n':'2', 'q_p':'3.5'},
             'nor-rise': {'stack':'4'},
             'nand-input': {'b_n':'1.8','b_p':'1'},
             'mux-glitch': {'out_n':'2','out_p':'4'},
             'buffer-fo4': {'first_n':'1','first_p':'2','out_n':'1.5','out_p':'3'},
             'xor-energy': {'logic_n':'.7','logic_p':'1.4','out_n':'1.25','out_p':'2.5'},
             'dff-aperture': {'in_n':'1','in_p':'2'}}


def route(project, cell):
    for net, params in cell['student_cell_layout']['breaks'].items():
        geometry.close_gap(project, cell, net, **params)


class StandardCellLessons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lessons = {lesson['standard_cell']: lesson for lesson in curriculum()['lessons']
                       if lesson.get('standard_cell')}

    def test_all_layout_starters_have_two_measurable_gaps(self):
        self.assertEqual(set(self.lessons), {'inv', 'nand2', 'nor2', 'aoi21', 'mux2', 'dff', 'abutment', *SOLUTIONS})
        for key, lesson in self.lessons.items():
            if key == 'abutment':
                continue
            with self.subTest(key=key):
                project = create(lesson['starter'])
                place, routing = lesson['steps'][1:3]
                cell, fixture = cells.context(project, key)
                self.assertEqual(cell['name'], key.replace('-', '_'))
                self.assertEqual(fixture['name'], cell['name'] + '_characterization')
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

    def test_row_starts_misaligned_and_checks_actual_rail_contact(self):
        lesson = self.lessons['abutment']
        project = create(lesson['starter'])
        step = lesson['steps'][1]
        with self.assertRaisesRegex(ValueError, 'horizontal gap is 1'):
            evaluate(step,lesson,project)
        cells.build_layout(project,'abutment',dict(x='13.8',y='0'))
        evidence = evaluate(step,lesson,project)
        self.assertEqual(evidence['continuous_rails'], ['VPWR','VGND'])
        self.assertEqual(evidence['spacing_issues'], 0)
        _, child = next((i,c) for i in project['cells'][0]['layout_instances']
                        for c in project['cells'] if i['name']=='XNAND' and c['id']==i['cell'])
        child['shapes'] = [s for s in child['shapes'] if s.get('net')!='VPWR']
        with self.assertRaises(ValueError):
            evaluate(step,lesson,project)

    def test_fo4_uses_four_independent_reusable_inverter_loads(self):
        project = create(self.lessons['buffer-fo4']['starter'])
        fixture = cells.check_fixture(project,'buffer-fo4')
        loads = [d for d in fixture['devices'] if d['name'].startswith('XLOAD')]
        self.assertEqual(len(loads),4)
        self.assertEqual({d['nets']['A'] for d in loads},{'out'})
        self.assertEqual(len({d['nets']['Y'] for d in loads}),4)
        self.assertEqual(len({d['cell'] for d in loads}),1)
        inv = next(c for c in project['cells'] if c['id']==loads[0]['cell'])
        inv['devices'][0]['params']['w'] = '3u'
        with self.assertRaisesRegex(ValueError,'load dimensions'):
            cells.check_fixture(project,'buffer-fo4')

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

    def test_inverter_replacement_restores_two_open_gaps_and_reduces_width(self):
        from icstudio.student_cell_specs import measure

        key = 'inv-compact'
        project = create(self.lessons[key]['starter'])
        cells.build_layout(project,key)
        cell, _ = cells.context(project,key)
        route(project,cell)
        baseline = measure({},cell,geometry.check_routing(project,cell),cells.course()[key])
        self.assertEqual(baseline[0]['value'],13.8)
        self.assertFalse(baseline[0]['passed'])
        with self.assertRaisesRegex(ValueError, 'Confirm'):
            cells.build_layout(project,key,SOLUTIONS[key])
        cells.build_layout(project,key,SOLUTIONS[key],replace=True)
        self.assertEqual(geometry.open_nets(project,cell),{'Y','VPWR'})
        route(project,cell)
        tuned = measure({},cell,geometry.check_routing(project,cell),cells.course()[key])
        self.assertEqual(tuned[0]['value'],12.8)
        self.assertTrue(tuned[0]['passed'])

    @unittest.skipUnless(Path(NGSPICE).is_file(), 'Set ICSTUDIO_TEST_NGSPICE for native SKY130 simulation')
    def test_real_truth_tables_capture_hold_and_stale_evidence(self):
        with tempfile.TemporaryDirectory(prefix='sc-') as folder:
            for key, lesson in self.lessons.items():
                if key == 'abutment':
                    continue
                with self.subTest(key=key):
                    project = create(lesson['starter'])
                    cells.build_layout(project, key, SOLUTIONS.get(key))
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
                    if key in SOLUTIONS:
                        self.assertTrue(evidence['targets'])
                        self.assertTrue(all(row['passed'] for row in evidence['targets']))
                        if key in {'nor-rise','nand-input','xor-energy'}:
                            self.assertGreater(evidence['targets'][0]['reference'], evidence['targets'][0]['value'])
                        if key == 'dff-aperture':
                            for kind in ('Setup','Hold'):
                                rows = [r for r in evidence['timing_sweep'] if r['kind']==kind]
                                self.assertTrue(any(r['passed'] for r in rows))
                                self.assertTrue(any(not r['passed'] for r in rows))
                        altered=clone(result)
                        altered['student_cell_layout']['targets'][0]['value'] = 0
                        atomic_write(out,json.dumps(altered))
                        with self.assertRaisesRegex(ValueError,'target readings'):
                            evaluate(step,lesson,project,[row])
                        atomic_write(out,json.dumps(result))
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
