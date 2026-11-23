"""Exercise the geometry, numerical checkpoints and independent stream capture."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from icstudio import student_layout_labs as course
from icstudio import student_layout_signoff as lab
from icstudio.design_ops import flatten_layout
from icstudio.model import atomic_write, clone
from icstudio.student_hub import curriculum, evaluate
from icstudio.student_projects import create
from icstudio.worker import main


class StudentLayoutSignoffTests(unittest.TestCase):
    def setUp(self):
        self.lessons = {l['layout_lab']: l for l in curriculum()['lessons'] if l.get('layout_lab') in lab.LABS}

    def open(self, key):
        return create(self.lessons[key]['starter'])

    def check(self, p, key, step, rows=()):
        lesson = self.lessons[key]
        checkpoint = next(entry for entry in lesson['steps'] if entry['id'] == step)
        return evaluate(checkpoint, lesson, p, rows)['layout_study']

    def capture(self, p, step, root):
        folder = Path(root) / step
        job = course.prepare(p, self.lessons['handoff'], step, {})
        inputs, outputs = folder / 'input.json', folder / 'result.json'
        atomic_write(inputs, json.dumps(job))
        status = io.StringIO()
        with redirect_stdout(status):
            code = main(inputs, outputs)
        self.assertEqual(code, 0, status.getvalue())
        return dict(job=job, state='Complete', path=folder, result=json.loads(outputs.read_text(encoding='utf-8')))

    def test_native_floorplan_pin_access_and_gds_handoff(self):
        self.assertEqual(len(self.lessons), 9)
        self.assertEqual(len({self.lessons[key]['workspace'] for key in lab.SHARED}), 1)
        p = self.open('floorplan')
        self.assertEqual(p['pdk']['package_lock']['id'], 'gf180mcuC')
        self.assertGreater(self.check(p, 'floorplan', 'loose')['Footprint (µm²)'], 700)
        with self.assertRaisesRegex(ValueError, '345 µm²'):
            self.check(p, 'floorplan', 'compact')
        lab.place_macro(p, 16000, 0)
        self.assertLess(self.check(p, 'floorplan', 'compact')['Footprint (µm²)'], 345)
        self.assertGreater(self.check(p, 'access', 'access')['Metal-1-only detour (µm)'], 14)
        detour = clone(p)
        lab.plan_macro(detour, False)
        with self.assertRaisesRegex(ValueError, 'Meet 14 µm'):
            self.check(detour, 'access', 'route')
        lab.plan_macro(p, True)
        self.assertEqual(self.check(p, 'access', 'route')['Route vias'], 2)
        original = flatten_layout(p, p['top'])
        with tempfile.TemporaryDirectory() as td:
            bad = self.capture(p, 'fault', td)
            self.assertEqual(self.check(p, 'handoff', 'fault', [bad])['Missing labels'], ['OUT'])
            lab.add_stream_label(p, 'OUT')
            with self.assertRaisesRegex(ValueError, 'latest edits'):
                self.check(p, 'handoff', 'fault', [bad])
            self.assertEqual(flatten_layout(p, p['top']), original)
            good = self.capture(p, 'verify', td)
            stream = good['path'] / 'pass_macro.gds'
            # Independent verification does not restore the editor sidecar.
            Path(str(stream) + '.icstudio.json').unlink()
            evidence = self.check(p, 'handoff', 'verify', [good])
            self.assertEqual((evidence['Top cell'], evidence['Placed child instances']), ('pass_macro', 2))
            self.assertEqual(evidence['Missing labels'], [])
            changed = clone(p)
            top = next(c for c in changed['cells'] if c['id'] == changed['top'])
            text = next(t for t in top['layout_texts'] if t['text'] == 'OUT')
            text['layer'] = top['layout_ports'][0]['layer']
            with tempfile.TemporaryDirectory() as wrong_layer_dir:
                wrong_layer = self.capture(changed, 'verify', wrong_layer_dir)
                with self.assertRaisesRegex(ValueError, 'actual stream pin labels'):
                    self.check(changed, 'handoff', 'verify', [wrong_layer])
            stream.write_bytes(b'altered')
            with self.assertRaisesRegex(ValueError, 'captured stream is missing or changed'):
                self.check(p, 'handoff', 'verify', [good])

    def test_pad_map_detects_unassigned_or_swapped_connections(self):
        p = self.open('pad-ring')
        initial = self.check(p, 'pad-ring', 'trace')
        self.assertEqual(set(initial['Unassigned supply pads']), {'PWR', 'GND'})
        self.assertEqual(set(initial['Incorrect signal pads']), {'INA', 'INB'})
        for name in ('PWR', 'GND'):
            lab.assign_ring_port(p, name, name)
        with self.assertRaisesRegex(ValueError, 'Incorrect'):
            self.check(p, 'pad-ring', 'repair')
        for name in ('INA', 'INB'):
            lab.assign_ring_port(p, name, name)
        self.assertEqual(self.check(p, 'pad-ring', 'repair')['Verified pad-to-block connections'], 5)

    def test_density_and_two_antenna_repair_options(self):
        p = self.open('density')
        self.assertLess(self.check(p, 'density', 'scan')['Right density (%)'], 22)
        lab.add_fill(p, 500)
        near = self.check(p, 'density', 'close-fill')
        with self.assertRaisesRegex(ValueError, '1.4 fF'):
            self.check(p, 'density', 'repair')
        lab.add_fill(p, 2500)
        far = self.check(p, 'density', 'repair')
        self.assertLess(far['Estimated fill loading (fF)'], near['Estimated fill loading (fF)'])
        self.assertGreater(far['Right density (%)'], 22)

        p = self.open('antenna')
        baseline = self.check(p, 'antenna', 'fault')
        self.assertGreater(baseline['Area ratio'], baseline['Teaching limit'])
        for case in ('jumper', 'diode'):
            with self.subTest(case=case):
                cid = course.focus(p, 'antenna', case)
                with self.assertRaises(ValueError):
                    self.check(p, 'antenna', case)
                lab.repair_antenna(p, cid, case)
                fixed = self.check(p, 'antenna', case)
                self.assertLess(fixed['Area ratio'], fixed['Teaching limit'])

    def test_via_current_and_quiet_guard(self):
        p = self.open('via-current')
        first = self.check(p, 'via-current', 'diagnose')
        self.assertLess(first['Estimated voltage drop (mV)'], 10)
        lab.set_via_array(p, 1, 2)
        with self.assertRaisesRegex(ValueError, 'cut limit'):
            self.check(p, 'via-current', 'repair')
        lab.set_via_array(p, 2, 2)
        self.assertEqual(self.check(p, 'via-current', 'repair')['Equal-share current per cut (mA)'], .3)

        p = self.open('isolation')
        with self.assertRaisesRegex(ValueError, 'Close the ring'):
            self.check(p, 'isolation', 'ring')
        lab.add_guard_side(p, 'top')
        self.assertEqual(self.check(p, 'isolation', 'ring')['Verified ring net'], 'quiet')
        with self.assertRaisesRegex(ValueError, 'largest contact gap'):
            self.check(p, 'isolation', 'taps')
        lab.set_taps(p, 4)
        self.assertEqual(self.check(p, 'isolation', 'taps')['Maximum perimeter gap (µm)'], 11.4)

    def test_spiral_comparison_uses_current_geometry(self):
        p = self.open('spiral')
        reference = self.check(p, 'spiral', 'reference')
        with self.assertRaisesRegex(ValueError, 'Improve Q'):
            self.check(p, 'spiral', 'candidate')
        lab.tune_spiral(p, course.focus(p, 'spiral', 'candidate'), 'turns', 4)
        candidate = self.check(p, 'spiral', 'candidate')
        self.assertGreater(candidate['Q at 1 GHz'], reference['Q at 1 GHz'] * 1.05)
        self.assertGreater(candidate['Inductance (nH)'], 1.8)
        self.assertLess(candidate['Estimated self-resonance (GHz)'], reference['Estimated self-resonance (GHz)'])
