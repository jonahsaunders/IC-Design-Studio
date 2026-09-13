"""Geometry, units, differential conversion and convergence gates."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from icstudio import inductor, inductor_em as em, openems_backend as backend
from icstudio.layout import kdb, polygon, rect
from icstudio.model import clone, digest
from test_inductor_pdks import fixture


def coil(shape='square', **changes):
    p = fixture(); proposal = inductor.plan(p, p['top'], {**inductor.defaults(p), 'shape': shape, **changes})
    inductor.install(p, proposal)
    return p, proposal['device_id']


def column(data, scale, port, resistance=4.):
    """Independent reciprocal Z = [[2+jwL, .2], [.2, 2+jwL]]."""
    frequency = [data['settings']['f_start_hz'], data['settings']['f_stop_hz']]; real = []; imag = []
    for f in frequency:
        a = complex(resistance/2, 2*3.141592653589793*f*1e-9); mutual = .2
        det = (a+50)**2-mutual**2
        diagonal = ((a-50)*(a+50)-mutual**2)/det
        off = 100*mutual/det
        values = [diagonal, off] if port == 1 else [off, diagonal]
        real.append([v.real for v in values]); imag.append([v.imag for v in values])
    return dict(run_hash=data['run_hash'], scale=scale, port=port, frequency_hz=frequency,
                s_real=real, s_imag=imag, versions={'openEMS': 'synthetic test'},
                cells=1000, mesh_lines=[11, 11, 11], energy_db=-55)


class OpenEMSTests(unittest.TestCase):
    def test_exact_masks_all_shapes_rotations_and_pdk_aliases(self):
        db = kdb()
        for shape in inductor.SHAPES:
            for rotation in (0, 90, 180, 270):
                p, did = coil(shape, rotation=rotation, mirror=True)
                data = em.manifest(p, p['top'], did); m = backend.model(data, {})
                actual = {}; expected = {}
                for solid in m['solids']:
                    poly = db.Polygon([db.Point(round(x*1000), round(y*1000)) for x, y in solid['points_um']])
                    actual.setdefault(solid['layer'], db.Region()).insert(poly)
                for s in data['context_geometry']:
                    expected.setdefault(data['physical_layer_map'][s['layer']], db.Region()).insert(polygon(s))
                for name in expected: self.assertTrue((expected[name]^actual[name]).is_empty(), (shape, rotation, name))
                self.assertEqual(m['layers'], data['stackup']['layers'])
                for pin, port in zip(sorted(data['pins'], key=lambda p: p['pin'], reverse=True), m['ports']):
                    self.assertEqual(pin['pin'].upper(), port['name'])
                    for axis in (0, 1): self.assertAlmostEqual(pin['point'][axis]/1000, (port['start_um'][axis]+port['stop_um'][axis])/2)

    def test_holes_preserved_and_context_port_obstruction_rejected(self):
        p, did = coil(); data = em.manifest(p, p['top'], did)
        hole = dict(kind='polygon', layer='RDL_B', points=[[200000, 0], [240000, 0], [240000, 40000], [200000, 40000]],
                    holes=[[[210000, 10000], [230000, 10000], [230000, 30000], [210000, 30000]]])
        data['context_geometry'].append(hole)
        m = backend.model(data, {}); region = kdb().Region()
        for s in m['solids']:
            if s['layer'] == 'Top copper': region.insert(kdb().Polygon([kdb().Point(round(x*1000), round(y*1000)) for x, y in s['points_um']]))
        self.assertTrue((region & kdb().Region(kdb().Box(211000, 11000, 229000, 29000))).is_empty())
        layer = clone(data['stackup']['layers'][0]); layer.update(name='Blocker', z_um=5)
        data['stackup']['layers'].append(layer); data['physical_layer_map']['foreign'] = 'Blocker'
        x, y = data['pins'][0]['point']; data['context_geometry'].append(rect('foreign', x-5000, y-5000, 10000, 10000))
        with self.assertRaisesRegex(ValueError, 'intersects Blocker'): backend.model(data, {})

    def test_settings_and_missing_materials_rejected(self):
        for bad in ({'f_start_hz': float('nan')}, {'f_stop_hz': 1e7}, {'samples': 2.5}, {'max_cells': True}, {'mesh_check': 'yes'}, {'unexpected': 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError): backend.settings(bad)
        p, did = coil(); p['pdk'].pop('em_stackup')
        with self.assertRaisesRegex(ValueError, 'physical EM profile'): backend.model(em.manifest(p, p['top'], did), {})

    def test_preparation_cancellation_and_immutable_job_identity(self):
        p, did = coil()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'run'
            with self.assertRaises(InterruptedError): backend.prepare(p, p['top'], did, 'context', {}, root, lambda: True)
            self.assertFalse(root.exists())
            m = backend.prepare(p, p['top'], did, 'context', {}, root)
            self.assertEqual(m['run_hash'], digest({k: v for k, v in m.items() if k != 'run_hash'}))
            with self.assertRaises(FileExistsError): backend.prepare(p, p['top'], did, 'context', {}, root)
            self.assertTrue((root/'exchange.zip').exists())

    def test_zero_exit_requires_decay_evidence_and_matched_excitation(self):
        p, did = coil()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'run'; m = backend.prepare(p, p['top'], did, 'context', {'samples': 2}, root)
            (root/'base-1.json').write_text(json.dumps(column(m, 1., 1)))
            for log in ('', 'Energy (-35dB)', 'Energy (-55dB)\nMax. number of timesteps was reached'):
                with self.assertRaises(ValueError): backend.check_completion(log, root, m, 1., 1)
            self.assertEqual(backend.check_completion('Max. number of timesteps: 1000000\nEnergy (- 55.03dB)', root, m, 1., 1)['energy_db'], -55.03)
            wrong = column(m, 1., 2); (root/'base-1.json').write_text(json.dumps(wrong))
            with self.assertRaisesRegex(ValueError, 'match'): backend.check_completion('Energy (-55dB)', root, m, 1., 1)

    def test_two_excitation_conversion_mesh_loss_gate_and_saved_evidence(self):
        p, did = coil()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'run'; m = backend.prepare(p, p['top'], did, 'context', {'samples': 2}, root)
            columns = {backend.stage_name(s, p): column(m, s, p) for s, p in backend.stages(m['settings'])}
            result = backend.finish(root, m, columns)
            self.assertAlmostEqual(result['z_real_ohm'][0], 3.6, places=10)
            result = em.install_results(p, p['top'], did, result)
            self.assertAlmostEqual(result['rows'][0]['inductance_h'], 2e-9, places=15)
            self.assertIn('solver_run', result['evidence']); self.assertIn('current', em.result_status(p, p['top'], did)[1].lower())
            result['evidence']['solver_run']['fixture'] = 'changed'
            self.assertIsNone(em.result_status(p, p['top'], did)[0])
            for port in (1, 2): columns[backend.stage_name(.7, port)] = column(m, .7, port, resistance=6.)
            with self.assertRaisesRegex(ValueError, 'Mesh refinement'): backend.finish(root, m, columns)
            self.assertTrue((root/'mesh-comparison.json').exists())

    def test_gui_job_lifecycle_in_subprocess(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, str(root/'tests/gui_openems.py'), '-v'], cwd=root,
                                env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONPATH': str(root)},
                                capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout+'\n'+result.stderr)


if __name__ == '__main__': unittest.main()
