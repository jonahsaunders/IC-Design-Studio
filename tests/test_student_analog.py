"""The design projects launch from the curriculum and hold learners to fixed limits."""

import unittest

from icstudio import student_analog, student_bias
from icstudio.student_hub import curriculum, evaluate
from icstudio.student_learning import study_guide
from icstudio.student_projects import create
from icstudio.two_stage_opamp import generate_layout


class StudentAnalogProjects(unittest.TestCase):
    def setUp(self):
        self.data = curriculum()
        self.lessons = {lesson['analog_project']: lesson for lesson in self.data['lessons']
                        if lesson.get('analog_project') in ('opamp','tia')}

    def test_projects_teach_the_same_complete_process(self):
        self.assertEqual(set(self.lessons), {'opamp', 'tia'})
        material = study_guide(self.data)
        for kind, lesson in self.lessons.items():
            with self.subTest(kind=kind):
                self.assertIn(lesson['id'], material['lessons'])
                self.assertEqual([s['id'] for s in lesson['steps']],
                                 ['brief', 'fixture', 'sizing', 'bias', 'schematic', 'layout', 'bias-layout', 'post-layout', 'review'])
                project = create(lesson['starter'])
                self.assertEqual(project['pdk']['package_lock']['id'], 'sky130A')
                self.assertEqual({*student_analog.run_names(kind, 'schematic'), student_analog.REFERENCE},
                                 set(student_analog.run_names(kind, 'post-layout')))
                self.assertTrue(all(cell.get('example_drawing') for cell in project['cells']))

    def test_fix_fixtures_before_grading_and_check_generated_layout(self):
        for kind, bench_name, part, value, error in (
            ('tia', 'tia_ac', 'RF', '100k', 'same value'),
            ('opamp', 'opamp_ac', 'CL', '1p', '1 pF'),
        ):
            with self.subTest(kind=kind):
                lesson = self.lessons[kind]
                stage = {step['id']: step for step in lesson['steps']}
                project = create(lesson['starter'])
                with self.assertRaisesRegex(ValueError, error):
                    evaluate(stage['fixture'], lesson, project)
                bench = student_analog._get_bench(project, bench_name)
                fixture = student_analog._cell(project, bench['bench_cell'])
                student_analog._named(fixture, part)['value'] = value
                self.assertEqual(evaluate(stage['fixture'], lesson, project)['bench'], bench_name)
                with self.assertRaisesRegex(ValueError, 'Generate'):
                    evaluate(stage['layout'], lesson, project)
                generate_layout(project, bench['dut_cell'])
                self.assertIn('OUT', evaluate(stage['layout'], lesson, project)['ports'])
                with self.assertRaisesRegex(ValueError, 'bias mirror'):
                    evaluate(stage['bias-layout'], lesson, project)
                from icstudio.analog_bank import generate
                generate(project, student_analog._get_bench(project, student_analog.REFERENCE)['dut_cell'])
                self.assertIn('SET', evaluate(stage['bias-layout'], lesson, project)['ports'])
                with self.assertRaisesRegex(ValueError, 'completed result'):
                    evaluate(stage['post-layout'], lesson, project)

    def test_loosened_limits_and_missing_metrics_do_not_pass(self):
        with self.assertRaisesRegex(ValueError, 'Transimpedance'):
            student_analog._limits('tia_ac', [
                dict(name='Transimpedance at 100 Hz', value=47_000, status='PASS'),
            ], [])
        with self.assertRaisesRegex(ValueError, 'phase_margin'):
            student_analog._limits('opamp_ac', [], [])

    def test_bias_sweep_uses_the_same_edited_reference_and_fixed_clamp(self):
        p = create('bias-cascode')
        for kind in ('simple', 'cascode'):
            point = student_analog._get_bench(p, kind+'_bias')
            sweep = student_analog._get_bench(p, kind+'_compliance')
            self.assertEqual(point['bench_cell'], sweep['bench_cell'])
            self.assertEqual(sweep['analysis']['source'], 'VCLAMP')
            student_bias.verify_fixture(p, point)
            fixture = student_analog._cell(p, point['bench_cell'])
            student_analog._named(fixture, 'VCLAMP')['value'] = '1.2'
            with self.assertRaisesRegex(ValueError, '1.4 V output clamp'):
                student_bias.verify_fixture(p, sweep)
