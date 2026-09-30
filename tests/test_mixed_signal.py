"""Clock-boundary coupling, portable snapshots and real SAR fault detection."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from icstudio import mixed_signal as ms
from icstudio.model import History, clone, design_digest, load_project, save_project, validate
from icstudio.sar_example import sar_project, conversion_report


def tools():
    return {name: os.environ.get('ICSTUDIO_TEST_'+name.upper()) or shutil.which(name)
            for name in ('ngspice', 'iverilog', 'vvp')}


class MixedSignalModelTests(unittest.TestCase):
    def test_portable_project_and_undo_capture_both_domains(self):
        p = sar_project(); original = design_digest(p); h = History(p)
        h.commit(lambda q: q['mixed_signal']['stimuli'].update(vin=[[0, .4]]))
        self.assertNotEqual(original, design_digest(h.project)); h.undo()
        self.assertEqual(p['mixed_signal'], h.project['mixed_signal'])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'sar.icproj'; save_project(p, path); q = load_project(path)
            self.assertEqual(p['mixed_signal'], q['mixed_signal'])
            self.assertEqual(p['cells'][1]['digital'], q['cells'][1]['digital'])

    def test_bridge_rejects_conflicting_drivers_and_bad_clock_contracts(self):
        p = sar_project()
        for change in (lambda c: c.update(period=float('nan')),
                       lambda c: c.update(cycles=500),
                       lambda c: c['outputs'][0]['nodes'].__setitem__(1, 'd0'),
                       lambda c: c['stimuli'].update(d0=[[0, 1]]),
                       lambda c: c['stimuli'].update(vin=[[1e-6, 0]]),
                       lambda c: c['inputs'][0].update(values=[1]),
                       lambda c: c['inputs'][2].update(high=.1),
                       lambda c: c['inputs'][2].update(sample_when={'port':'missing','value':1})):
            q = clone(p); change(q['mixed_signal'])
            with self.assertRaises((ValueError, KeyError)): validate(q)

    def test_unknown_levels_and_missing_edges_never_become_zero(self):
        c = sar_project()['mixed_signal']; spec = c['inputs'][2]
        for value in (.9, float('nan'), float('inf')):
            with self.assertRaises(ValueError): ms.logic_input(value, spec)
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            ms.decode_outputs('ICMS 0 xxxx 0000 1 0 0 0', c, 1)
        with self.assertRaisesRegex(ValueError, 'every bridge edge'):
            ms.decode_outputs('', c, 1)


@unittest.skipUnless(all(tools().values()), 'Requires local ngspice, iverilog and vvp')
class MixedSignalEngineTests(unittest.TestCase):
    def simulate(self, project, root):
        job = ms.prepare(project, tools()); (root/'input.json').write_text(json.dumps(job))
        result = ms.run(job, root); (root/'result.json').write_text(json.dumps(result))
        ms.validate_result(result, job, root)
        return job, result

    def test_real_closed_loop_and_captured_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); p = sar_project(); job, r = self.simulate(p, root)
            self.assertEqual(conversion_report(r, 8)['status'], 'PASS')
            decisions = [s['outputs']['dac'] for s in r['mixed_signal']['samples'][3:8]]
            self.assertEqual(decisions, [8, 12, 10, 9, 8])
            p['mixed_signal']['stimuli']['vin'][0][1] = .1
            self.assertEqual(job['project']['mixed_signal']['stimuli']['vin'][0][1], .93)
            altered = clone(r); altered['mixed_signal']['samples'][4]['outputs']['dac'] = 0
            with self.assertRaisesRegex(ValueError, 'captured waveforms or samples'):
                ms.validate_result(altered, job, root)
            (root/'bridge/bridge.vcd').write_text('damaged')
            with self.assertRaisesRegex(ValueError, 'artifact changed'):
                ms.validate_result(r, job, root)

    def test_analog_and_rtl_faults_are_detected(self):
        for fault in ('dac_weight', 'rtl_decision', 'too_fast'):
            p = sar_project(); expected = 8
            if fault == 'dac_weight':
                next(d for d in p['cells'][0]['devices'] if d['name']=='Rbit3')['value'] = '20k'
            elif fault == 'rtl_decision':
                source = p['cells'][1]['digital']['files'][0]
                source['text'] = source['text'].replace('if (!cmp)', 'if (cmp)')
            else:
                p['mixed_signal'].update(period=10e-9, max_step=1e-10, rise=1e-10)
                p['mixed_signal']['stimuli']['vin'] = [[0, .3]]; expected = 2
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                try: _, r = self.simulate(p, Path(tmp))
                except ValueError as exc:
                    self.assertIn('Ambiguous analog', str(exc))
                else: self.assertEqual(conversion_report(r, expected)['status'], 'FAIL')

    def test_reset_and_two_conversions_preserve_analog_history(self):
        p = sar_project(); c = p['mixed_signal']; c.pop('verification'); c['cycles'] = 17
        c['inputs'][0]['values'] = [1,1]+[0]*15
        c['inputs'][1]['values'] = [int(k in (2,9)) for k in range(17)]
        c['stimuli']['vin'] = [[0, .4], [8e-6, .4], [8.001e-6, 1.2]]
        with tempfile.TemporaryDirectory() as tmp:
            _, r = self.simulate(p, Path(tmp))
            completed = [s for s in r['mixed_signal']['samples'] if s['outputs']['done']]
            self.assertEqual([(s['edge'], s['outputs']['code']) for s in completed], [(7,3),(14,10)])
            # Input changes during hold; the prior sample survives until acquisition.
            held = next(s for s in r['mixed_signal']['samples'] if s['edge']==9)['analog']['held']
            self.assertAlmostEqual(held, .4, places=5)


if __name__ == '__main__': unittest.main()
