"""Regression checks for Layout world starters, repairs and captured measurements."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from icstudio import student_layout_labs as labs
from icstudio.gf180_layout import layers
from icstudio.layout import drc
from icstudio.layout_eco import apply, propose
from icstudio.model import atomic_write
from icstudio.physical import connectivity
from icstudio.student_hub import curriculum, evaluate
from icstudio.student_projects import create
from icstudio.worker import main


class StudentLayoutLabTests(unittest.TestCase):
    def setUp(self):
        self.lessons = {l['layout_lab']: l for l in curriculum()['lessons'] if l.get('layout_lab')}

    def open(self, key):
        return create(self.lessons[key]['starter'])

    def cell(self, p, key, step):
        cid = labs.focus(p, key, step)
        return next(c for c in p['cells'] if c['id'] == cid)

    def evaluate(self, p, key, step, rows=()):
        lesson = self.lessons[key]
        checkpoint = next(s for s in lesson['steps'] if s['id'] == step)
        return evaluate(checkpoint, lesson, p, rows)['layout_study']

    def run_case(self, p, key, step, root):
        path = Path(root) / (key + '-' + step)
        job = labs.prepare(p, self.lessons[key], step, {})
        inp, out = path / 'input.json', path / 'result.json'
        atomic_write(inp, json.dumps(job))
        trace = io.StringIO()
        with redirect_stdout(trace):
            status = main(inp, out)
        self.assertEqual(status, 0, trace.getvalue())
        return dict(job=job, result=json.loads(out.read_text(encoding='utf-8')), path=path, state='Complete')

    def test_native_device_starters_and_folded_configuration(self):
        p = self.open('fold')
        one = self.cell(p, 'fold', 'single')
        folded = self.cell(p, 'fold', 'folded')
        self.assertEqual(one['pdk_layouts'][0]['spec']['values']['nf'], 1)
        with self.assertRaisesRegex(ValueError, 'nf parameter'):
            labs.build_fold(p, folded['id'], 4)
        folded['devices'][0]['model_params']['nf'] = '4'
        labs.build_fold(p, folded['id'], 4)
        self.assertEqual(folded['pdk_layouts'][0]['spec']['dimensions_nm']['w'], 2000)
        self.assertEqual(folded['pdk_layouts'][0]['spec']['values']['nf'], 4)
        job = labs.prepare(p, self.lessons['fold'], 'folded', {})
        self.assertEqual(job['settings']['verification_mode'], 'drc_lvs')
        self.assertEqual(job['settings']['reference']['ports'], ['OUT', 'GATE', 'SOURCE', 'BODY'])
        with self.assertRaises(ValueError):
            self.evaluate(p, 'fold', 'folded')

        p = self.open('body')
        cell = self.cell(p, 'body', 'tie')
        self.assertIn('LVS.OPEN', {i['code'] for i in connectivity(p, cell['id'])['issues']})
        labs._path(cell, 'SOURCE', ((-2500, 1000), (-500, 1000)), layer=layers(p['pdk'])['m1'])
        self.assertEqual(connectivity(p, cell['id'])['issues'], [])
        self.assertEqual(drc(p, cell['id']), [])
        self.assertEqual(labs.prepare(p, self.lessons['body'], 'tie', {})['cell'], cell['id'])

    def test_amplifier_stages_share_a_workspace_and_real_repairs(self):
        self.assertEqual(len({self.lessons[k]['workspace'] for k in ('match', 'lvs', 'settle')}), 1)
        p = self.open('match')
        amp = self.cell(p, 'match', 'balance')
        with self.assertRaisesRegex(ValueError, 'centroids'):
            self.evaluate(p, 'match', 'balance')
        a, b = (labs._shape(amp, key) for key in ('pair_a2', 'pair_b2'))
        a['points'], b['points'] = b['points'], a['points']
        with self.assertRaisesRegex(ValueError, 'routes differ'):
            self.evaluate(p, 'match', 'balance')
        labs._shape(amp, 'inp_route')['width'] = 400
        self.assertEqual(self.evaluate(p, 'match', 'balance')['Input resistance (Ω)'], [60, 60])

        for step, error in [('open', 'disconnected conductor'), ('short', 'short schematic'), ('swap', 'lands on inn')]:
            with self.subTest(step=step):
                cell = self.cell(p, 'lvs', step)
                self.assertEqual(drc(p, cell['id']), [])
                with self.assertRaisesRegex(ValueError, error):
                    self.evaluate(p, 'lvs', step)
                if step == 'open':
                    next(s for s in cell['shapes'] if s.get('net') == 'inp')['points'][-1][0] = 12000
                elif step == 'short':
                    cell['shapes'] = [s for s in cell['shapes'] if s['kind'] != 'path' or s.get('net')]
                else:
                    labs.set_input_ports(p, cell['id'], True)
                self.assertEqual(self.evaluate(p, 'lvs', step)['Port and terminal connectivity'], 'Match')

        with tempfile.TemporaryDirectory() as td:
            baseline = self.run_case(p, 'settle', 'baseline', td)
            initial = self.evaluate(p, 'settle', 'baseline', [baseline])
            self.assertGreater(initial['Extracted settling error (mV)'], 12)
            amp['shapes'] = [s for s in amp['shapes'] if not s['id'].endswith('_stub')]
            with self.assertRaisesRegex(ValueError, 'latest edits'):
                self.evaluate(p, 'settle', 'baseline', [baseline])
            row = self.run_case(p, 'settle', 'repair', td)
            repaired = self.evaluate(p, 'settle', 'repair', [row])
            self.assertLess(repaired['Extracted settling error (mV)'], 2)
            (row['path'] / 'before' / 'result.json').write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Waveform evidence'):
                self.evaluate(p, 'settle', 'repair', [row])

    def test_dac_placement_and_coupling_change_code_levels(self):
        p = self.open('dac')
        cell = self.cell(p, 'dac', 'array')
        with self.assertRaisesRegex(ValueError, 'Place C23'):
            self.evaluate(p, 'dac', 'array')
        tile = max((s for s in cell['shapes'] if s['layer'] == 'unit_capacitor'), key=lambda s: s['points'][0][0])
        for point in tile['points']:
            point[0] -= 11000
        self.assertEqual(self.evaluate(p, 'dac', 'array')['Unit groups'], '1 / 2 / 4')
        self.assertGreater(self.evaluate(p, 'dac', 'baseline')['Peak endpoint INL (LSB)'], .23)
        with self.assertRaisesRegex(ValueError, '0.16 LSB'):
            self.evaluate(p, 'dac', 'repair')
        cell['shapes'] = [s for s in cell['shapes'] if s['id'] != 'bit2_stub']
        self.assertEqual(self.evaluate(p, 'dac', 'repair')['Effective weights (fF)'], [10, 20, 40])

    def test_shared_device_eco_preserves_parent_connectivity(self):
        p = self.open('eco')
        child = self.cell(p, 'eco', 'update')
        child['devices'][0]['params']['w'] = '3u'
        with self.assertRaisesRegex(ValueError, 'physical device'):
            self.evaluate(p, 'eco', 'update')
        original = child['layout_ports']
        changed, report = propose(p, child['id'], [child['devices'][0]['id']])
        apply(p, changed, report)
        self.assertEqual(self.cell(p, 'eco', 'update')['layout_ports'], original)
        self.assertEqual(self.evaluate(p, 'eco', 'parent')['Verified parent instances'], 2)

    def test_noise_and_supply_comparisons_measure_current_layout(self):
        p = self.open('noise')
        spacing = self.cell(p, 'noise', 'space')
        labs.set_clock_spacing(p, spacing['id'], 3600)
        with tempfile.TemporaryDirectory() as td:
            noise = {case: self.evaluate(p, 'noise', case, [self.run_case(p, 'noise', case, td)])['Peak victim glitch (mV)']
                     for case in ('close', 'space', 'layer', 'shield')}
            self.assertGreater(noise['close'], noise['shield'])
            self.assertGreater(noise['shield'], noise['space'])
            self.assertEqual(noise['layer'], 0)

            p = self.open('supply')
            start = self.evaluate(p, 'supply', 'baseline', [self.run_case(p, 'supply', 'baseline', td)])
            labs._shape(self.cell(p, 'supply', 'repair'), 'supply_route')['width'] = 800
            finish = self.evaluate(p, 'supply', 'repair', [self.run_case(p, 'supply', 'repair', td)])
            self.assertEqual(start['Supply drop (mV)'], 400)
            self.assertEqual(finish['Supply drop (mV)'], 125)
