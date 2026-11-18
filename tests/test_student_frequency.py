"""Measured teaching checkpoints and independent pole/zero examples."""

import json
from contextlib import redirect_stdout
import io
import tempfile
import unittest
from pathlib import Path

from icstudio import student_ahuja, student_bandgap, student_filters as filters, student_layout_decisions as layout, student_miller
from icstudio.model import atomic_write, clone
from icstudio.simulation import run
from icstudio.student_hub import curriculum, evaluate, prepare_lesson
from icstudio.student_projects import create
from icstudio.worker import main


class StudentFrequencyTests(unittest.TestCase):
    def setUp(self):
        self.lessons = {lesson['starter']: lesson for lesson in curriculum()['lessons']}

    def replay(self, project, starter, step, directory):
        lesson = self.lessons[starter]
        job = layout.prepare(project, step) if starter == 'layout-decisions' else prepare_lesson(project)
        directory = Path(directory)
        inp, out = directory/'input.json', directory/'result.json'
        atomic_write(inp, json.dumps(job))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(inp, out), 0)
        row = dict(job=job, state='Complete', path=directory, result=json.loads(out.read_text()))
        return row, next(s for s in lesson['steps'] if s['id']==step)

    def test_four_measured_traces_and_a_retuned_filter(self):
        project = create('lc-bode')
        lesson = self.lessons['lc-bode']
        parts = {d['name']: d for d in project['cells'][0]['devices']}
        with tempfile.TemporaryDirectory() as td:
            row, step = self.replay(project, 'lc-bode', 'slopes', Path(td)/'original')
            metrics = evaluate(step, lesson, project, [row])['lesson_measurements']
            self.assertAlmostEqual(metrics['lp']['high_db_per_decade'], -40, delta=.2)
            self.assertAlmostEqual(metrics['hp']['low_db_per_decade'], 40, delta=.2)
            self.assertAlmostEqual(metrics['bp']['center_db'], 0, delta=.02)
            self.assertLess(metrics['bs']['center_db'], -100)
            self.assertIsNone(metrics['bs']['phase_deg'])
            parts['RLP']['value'] = '470'
            with self.assertRaisesRegex(ValueError, 'latest edits'):
                evaluate(step, lesson, project, [row])
            row, step = self.replay(project, 'lc-bode', 'damping', Path(td)/'damped')
            damping = evaluate(step, lesson, project, [row])['lesson_measurements']
            self.assertAlmostEqual(damping['q'], .673, delta=.001)
            self.assertAlmostEqual(damping['center_db'], -3.44, delta=.02)
            parts['CLP']['value'] = '25.33n'
            row, step = self.replay(project, 'lc-bode', 'tune', Path(td)/'retuned')
            tuned = evaluate(step, lesson, project, [row])['lesson_measurements']
            self.assertAlmostEqual(tuned['f0_Hz'], 10_000, delta=1)

    def test_bode_mistapped_output_fails(self):
        project = create('lc-bode')
        result = run(project, project['top'], project['analysis'])
        result['traces']['hp'] = result['traces']['lp']
        result['phase']['hp'] = result['phase']['lp']
        with self.assertRaisesRegex(ValueError, 'High-pass'):
            filters.check(project, result, 'slopes')

    def test_geometry_pass_can_hide_an_open_and_wider_can_miss_spec(self):
        from icstudio.layout import drc

        project = create('layout-decisions')
        lesson = self.lessons['layout-decisions']
        for key in ('via', 'matching'):
            with self.assertRaises(ValueError):
                layout.check_geometry(project, key)
        via, matching = [project['cells'][i]['shapes'] for i in (1, 2)]
        via[-1]['points'] = [[175,175],[325,325]]
        self.assertGreaterEqual(layout.check_geometry(project, 'via')['measurements']['metal2_enclosure_nm'], 75)
        matching[1]['points'], matching[3]['points'] = matching[3]['points'], matching[1]['points']
        match = layout.check_geometry(project, 'matching')['measurements']
        self.assertEqual(match['centroid_a_nm'], match['centroid_b_nm'])
        broken = clone(project)
        broken['cells'][0]['shapes'] = [s for s in broken['cells'][0]['shapes'] if s['kind']!='path']
        self.assertEqual(drc(broken, broken['top']), [])
        with self.assertRaisesRegex(ValueError, 'physical connectivity'):
            layout.check_geometry(broken, 'connectivity')
        route = next(s for s in project['cells'][0]['shapes'] if s['kind']=='path')
        with tempfile.TemporaryDirectory() as td:
            row, step = self.replay(project, 'layout-decisions', 'baseline', Path(td)/'baseline')
            base = evaluate(step, lesson, project, [row])['lesson_measurements']
            self.assertAlmostEqual(base['route_ohm'],226.65)
            route['width'] = 800
            row, step = self.replay(project, 'layout-decisions', 'optimize', Path(td)/'wide')
            with self.assertRaisesRegex(ValueError, '12.5 GHz'):
                evaluate(step, lesson, project, [row])
            self.assertGreater(sum(c['value'] for c in row['result']['extraction']['capacitors']), base['added_F'])
            route['width'] = 400
            row, step = self.replay(project, 'layout-decisions', 'optimize', Path(td)/'middle')
            improved = evaluate(step, lesson, project, [row])['lesson_measurements']
            self.assertGreater(improved['after_Hz'],12.5e9)
            self.assertGreater(improved['added_F'],base['added_F'])
            self.assertLess(improved['route_ohm'],base['route_ohm'])

    def test_ahuja_buffer_and_load_are_real_model_knobs(self):
        _, fast = student_ahuja.study(20, 50)
        _, slow = student_ahuja.study(20, 10)
        _, light = student_ahuja.study(2, 50)
        self.assertAlmostEqual(student_ahuja.MILLER_ZERO_HZ/1e6,79.58,delta=.01)
        self.assertAlmostEqual(fast['Direct Miller']['phase_margin_deg'],37.4,delta=.2)
        self.assertAlmostEqual(fast['Ideal Ahuja']['phase_margin_deg'],81.2,delta=.2)
        self.assertLess(slow['Finite buffer']['phase_margin_deg'],20)
        self.assertAlmostEqual(slow['Ideal Ahuja']['phase_margin_deg'],fast['Ideal Ahuja']['phase_margin_deg'])
        self.assertGreater(light['Direct Miller']['phase_margin_deg'],60)

    def test_miller_resistor_moves_the_zero_without_guaranteeing_margin(self):
        cc = 2e-12
        self.assertEqual(student_miller.equivalent_input_capacitance(2), 202)
        _, nominal = student_miller.study()
        _, higher = student_miller.study(resistor=2000)
        side, zero_hz = nominal['Capacitor only']['zero']
        self.assertEqual(side, 'Right half plane')
        self.assertAlmostEqual(zero_hz/1e6, 79.58, delta=.01)
        self.assertEqual(nominal['Series RC']['zero'], ('At infinity', None))
        self.assertEqual(higher['Series RC']['zero'], ('Left half plane', zero_hz))
        self.assertEqual(student_miller.zero(cc, 500), ('Right half plane', 2*zero_hz))
        self.assertAlmostEqual(nominal['Uncompensated']['phase_margin_deg'], 3.1, delta=.1)
        self.assertAlmostEqual(nominal['Series RC']['phase_margin_deg'], 42.8, delta=.1)
        self.assertGreater(higher['Series RC']['phase_margin_deg'], nominal['Series RC']['phase_margin_deg'])
        _, tuned = student_miller.study(cc_pf=4, resistor=2000)
        self.assertGreater(tuned['Series RC']['phase_margin_deg'], 60)
        self.assertLess(tuned['Series RC']['unity_Hz'], higher['Series RC']['unity_Hz'])
        for load in (1, 100):
            for cap in (.5, 10):
                for resistor in (0, 8000):
                    student_miller.study(load, cap, resistor)

    def test_four_bandgap_models_trim_and_run_the_nominal_summation(self):
        values = {}
        for kind in student_bandgap.NAMES:
            with self.subTest(topology=kind):
                starter = 'bandgap-' + kind
                ratio, weight, extra = student_bandgap.defaults(kind)
                data = student_bandgap.study(kind, ratio, weight, extra)
                self.assertEqual(self.lessons[starter]['bandgap'], kind)
                p = create(starter)
                measured = run(p, p['top'], p['analysis'])['traces']['vref'][0]
                self.assertAlmostEqual(measured, data['nominal'], delta=1e-6)
                trimmed = student_bandgap.study(kind, ratio, data['optimum_ratio'], extra)
                self.assertAlmostEqual(trimmed['slope27'], 0.)
                self.assertLess(trimmed['drift'][-1], -.005)
                values[kind] = data
        self.assertAlmostEqual(values['widlar']['delta_room'], .05956, delta=.00002)
        self.assertAlmostEqual(values['brokaw']['nominal'], values['kuijk']['nominal'])
        self.assertAlmostEqual(values['banba']['nominal'], .5*values['kuijk']['nominal'])
        shifted = student_bandgap.study('kuijk', 8, 10, 2)
        self.assertEqual(shifted['density_ratio'], 16)
        self.assertAlmostEqual(shifted['optimum_ratio'], 7.53, delta=.01)
        lower = student_bandgap.study('banba', 8, 10, .4)
        self.assertAlmostEqual(lower['nominal'], .8*values['banba']['nominal'])
        self.assertEqual(lower['optimum_ratio'], values['banba']['optimum_ratio'])
