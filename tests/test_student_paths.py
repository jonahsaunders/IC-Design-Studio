"""Cross-world milestones use earned measurements from the previous lesson."""

import unittest

from icstudio.model import example
from icstudio.student_hub import curriculum, evaluate, lesson_stamp
from icstudio.student_paths import ROUTES, handoff, handoff_note, milestones


class StudentPathsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lessons = {lesson['id']:lesson for lesson in curriculum()['lessons']}

    def record(self, state, key, step, values):
        lesson = self.lessons[key]
        record = state.setdefault('lessons',{}).setdefault(key, dict(stamp=lesson_stamp(lesson),steps={}))
        record['steps'][step] = dict(evidence=values)

    def test_sensor_passes_settling_budget_then_register_payload(self):
        route, state = ROUTES['sensor'], {}
        self.assertEqual(milestones(route,state,self.lessons),[None,None,None])
        self.record(state,'tb-tia-step','measure',{'bench_figures':{
            'Settling within 20 mV (µs)': 8.3, 'Undershoot (mV)':4.1}})
        timing = handoff(route,'m-settling',state,self.lessons)
        self.assertIn('8.3 µs',timing['reading'])
        self.assertIn('9 whole periods',timing['task'])
        self.record(state,'m-settling','measure',{'codes':[2], 'edges':[7]})
        payload = handoff(route,'d-spi-register',state,self.lessons)
        self.assertIn('edge 7',payload['reading'])
        self.assertIn('00000010',payload['task'])
        reflection = self.lessons['d-spi-register']['steps'][-1]
        project = example('empty')
        with self.assertRaisesRegex(ValueError,'Record the test conditions'):
            evaluate(reflection,self.lessons['d-spi-register'],project,note=handoff_note(payload))
        note = handoff_note(payload)+'\nI committed the ADC code only after receiving a complete frame.'
        self.assertEqual(evaluate(reflection,self.lessons['d-spi-register'],project,note=note)['note'],note)

    def test_feedback_carries_loaded_loop_and_step_as_one_result(self):
        route, state = ROUTES['feedback'], {}
        self.record(state,'tb-verify-loop-stability','loop-step',{'bench_figures':{'Settling within 2% (µs)':.8}})
        self.assertIsNone(handoff(route,'project-miller',state,self.lessons)['reading'])
        self.record(state,'tb-verify-loop-stability','loop-ac',{'bench_figures':{
            'Phase margin (°)':66.7,'First unity crossing (Hz)':1.46e6}})
        reading = handoff(route,'project-miller',state,self.lessons)['reading']
        self.assertIn('66.7°',reading)
        self.assertIn('0.8 µs',reading)

    def test_physical_report_uses_measured_layout_change(self):
        state = {}
        self.record(state,'sc-mux2','verify',{
            'logic_samples':[{'inputs':{'A':1},'output_V':1.7}],
            'schematic_samples':[{'inputs':{'A':1},'output_V':1.8}],
        })
        handoff_value = handoff(ROUTES['physical'],'p-review',state,self.lessons)
        self.assertIn('100 mV',handoff_value['reading'])
        state['lessons']['sc-mux2']['stamp']='stale'
        self.assertIsNone(handoff(ROUTES['physical'],'p-review',state,self.lessons)['reading'])


if __name__ == '__main__':
    unittest.main()
