"""Independent network oracle for nonzero unpowered-port incident waves."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from icstudio import inductor_em, openems_backend as backend, openems_waves as waves
from icstudio.model import digest, save_project, load_project
from test_openems import coil, column


class MeasuredWaveTests(unittest.TestCase):
    def test_known_passive_network_with_coupled_excitations_and_complex_scaling(self):
        z = np.array([[8+12j, 2+3j], [2+3j, 10+15j]])
        # Build voltages from independent current trials, without computing S
        # in the oracle. This also exercises cross-column mixing and phase.
        current = np.array([[.03+.01j, -.012+.007j], [.004-.009j, .022-.005j]])
        voltage = z @ current
        a = (voltage+50*current)/2; b = (voltage-50*current)/2
        for scale in (1., 1e-200, 1e200, .3+.7j):
            s, condition = waves.scattering((a*scale).tolist(), (b*scale).tolist())
            actual = 50*(np.eye(2)+s) @ np.linalg.inv(np.eye(2)-s)
            np.testing.assert_allclose(actual, z, rtol=1e-12, atol=1e-12)
            self.assertLess(condition, waves.MAX_CONDITION)
        old = np.column_stack([b[:,n]/a[n,n] for n in (0,1)])
        self.assertGreater(float(np.max(abs(50*(np.eye(2)+old)@np.linalg.inv(np.eye(2)-old)-z))), 1.)

    def test_singular_nearly_dependent_nonfinite_and_malformed_inputs_rejected(self):
        b = [[1., 0.], [0., 1.]]
        for a in ([[0., 0.], [0., 0.]], [[1., 2.], [2., 4.]],
                  [[1., 1.], [1., 1.+1e-12]], [[float('nan'), 0.], [0., 1.]],
                  [[1., 0.], [float('inf'), 1.]], [[1.], [0., 1.]]):
            with self.subTest(a=a), self.assertRaises(ValueError): waves.scattering(a, b)
        with self.assertRaisesRegex(ValueError, 'Non-finite'):
            waves.scattering(b, [[complex(1, float('nan')), 0], [0, 1]])

    def test_full_backend_preserves_known_impedance_and_rejects_missing_wave_columns(self):
        p, did = coil()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'run'; m = backend.prepare(p, p['top'], did, 'context', {'samples': 2}, root)
            columns = {backend.stage_name(s,p): column(m,s,p) for s,p in backend.stages(m['settings'])}
            a = np.array([[1., .03+.02j], [-.04+.01j, 1.]])
            for scale in (1., .7):
                pair = [columns[backend.stage_name(scale,p)] for p in (1,2)]
                for n in range(2):
                    s = np.column_stack([np.array(c['b_real'][n])+1j*np.array(c['b_imag'][n]) for c in pair])
                    b = s @ a
                    for j,c in enumerate(pair):
                        for prefix, matrix in (('a',a), ('b',b)):
                            c[prefix+'_real'][n] = matrix[:,j].real.tolist()
                            c[prefix+'_imag'][n] = matrix[:,j].imag.tolist()
            output = backend.finish(root,m,columns)
            np.testing.assert_allclose(output['z_real_ohm'], [3.6,3.6],rtol=1e-12)
            np.testing.assert_allclose(output['z_imag_ohm'], 2*np.pi*np.array(output['frequency_hz'])*2e-9,rtol=1e-12)
            self.assertGreater(output['solver_run']['wave_analysis']['base']['maximum_inactive_incident_ratio'], .04)
            for fault in ('absent', 'wrong-basis', 'partial', 'nan', 'boolean'):
                bad = copy.deepcopy(columns)
                if fault == 'absent': bad['base-1'].pop('wave_basis')
                if fault == 'wrong-basis': bad['base-2']['wave_basis']='unrecognized'
                if fault == 'partial': bad['base-2']['a_real'].pop()
                if fault == 'nan': bad['base-1']['a_imag'][0][0]=float('nan')
                if fault == 'boolean': bad['base-1']['a_real'][0][0]=True
                with self.subTest(fault=fault), self.assertRaises(ValueError): backend._pair_result(m,bad,1.)

    def test_legacy_columns_require_explicitly_legacy_model(self):
        p, did = coil()
        with tempfile.TemporaryDirectory() as folder:
            m=backend.prepare(p,p['top'],did,'context',{'samples':2},Path(folder)/'run')
            cols={backend.stage_name(1.,p):column(m,1.,p) for p in (1,2)}
            for c in cols.values():
                c.pop('wave_basis');c.pop('a_real');c.pop('a_imag')
                c['s_real']=c.pop('b_real');c['s_imag']=c.pop('b_imag')
            with self.assertRaisesRegex(ValueError,'representation'): backend._pair_result(m,cols,1.)
            m.pop('wave_basis'); _,result=backend._pair_result(m,cols,1.)
            self.assertAlmostEqual(result['z_real_ohm'][0],3.6)
            with self.assertRaisesRegex(ValueError,'Legacy openEMS columns'): backend.finish(Path(folder)/'run',m,cols)

    def test_old_saved_characterization_is_retained_but_not_reported_current(self):
        p,did=coil()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'run';m=backend.prepare(p,p['top'],did,'context',{'samples':2},root)
            cols={backend.stage_name(s,p):column(m,s,p) for s,p in backend.stages(m['settings'])}
            result=inductor_em.install_results(p,p['top'],did,backend.finish(root,m,cols))
            result['evidence']['solver_run'].pop('wave_basis')
            result['evidence_hash']=digest(result['evidence'])
            path=Path(folder)/'old.icproj';save_project(p,path);restored=load_project(path)
            self.assertIn('em_characterization',restored['cells'][0]['parametric_devices'][0])
            current,status=inductor_em.result_status(restored,restored['top'],did)
            self.assertIsNone(current);self.assertIn('Legacy openEMS',status)
            with self.assertRaisesRegex(ValueError,'Legacy openEMS'):
                inductor_em.install_results(restored,restored['top'],did,result['evidence'])


if __name__ == '__main__': unittest.main()
