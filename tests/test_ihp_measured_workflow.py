import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_ihp_measured_coil as workflow


class MeasuredWorkflowTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Upstream shared-temp path fallback is Windows-specific.')
    def test_long_windows_destination_is_rejected_before_shared_temp_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/('reference-'+'x'*140)
            self.assertGreater(len(str(root/'isolated/mesh2/port1/output')), 200)
            with self.assertRaisesRegex(ValueError, 'shorter output path'): workflow.prepare(root, 2)
            self.assertFalse(root.exists())

    def test_staging_preserves_source_and_rejects_native_input_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = workflow.prepare(Path(folder)/'new', 2)
            for port in (1, 2): workflow.inputs(root, 2, port)
            with self.assertRaises(FileExistsError): workflow.prepare(root, 2)
            stage = root/'isolated/mesh2/port1'; script = stage/'run.py'
            script.write_text(script.read_text().replace("settings['energy_limit'] = energylimit", "settings['energy_limit'] = -20"))
            with self.assertRaisesRegex(ValueError, 'native script'): workflow.inputs(root, 2, 1)
            script.write_text(workflow.render(2, 1))
            source = stage/'L6n2_with_ports.gds'; source.write_bytes(source.read_bytes()+b'x')
            with self.assertRaisesRegex(ValueError, 'geometry or stackup'): workflow.inputs(root, 2, 1)

    def test_workflow_inventory_and_unexpected_module_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'workflow'; shutil.copytree(workflow.WORKFLOW, root)
            workflow.verify_workflow(root)
            extra = root/'gds2openEMS/unexpected.py'; extra.write_text('')
            with self.assertRaisesRegex(ValueError, 'module set'): workflow.verify_workflow(root)
            extra.unlink(); module = root/'gds2openEMS/util_meshlines.py'; module.write_bytes(module.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError, 'workflow module'): workflow.verify_workflow(root)

    def test_native_completion_requires_target_markers_and_correct_order(self):
        first = 'Starting FDTD simulation for excitation  [1]'
        last = 'FDTD simulation completed successfully for excitation  [1]'
        body = 'Max. number of timesteps\nRunning FDTD engine\nEnergy: residual (-60.2dB)\n'
        good = first+'\n'+body+last+'\nICSTUDIO_SINGLE_PORT_COMPLETE'
        self.assertEqual(workflow.energy(good, 1), -60.2)
        for bad in (good.replace('-60.2', '-59.9'), good.replace('-60.2', 'nan'),
                    good.replace(last, ''), good+'\n'+last,
                    last+'\n'+first+'\n'+body+'ICSTUDIO_SINGLE_PORT_COMPLETE'):
            with self.subTest(log=bad), self.assertRaises(ValueError): workflow.energy(bad, 1)
        with self.assertRaises(ValueError): workflow.energy(good, 2)

    def test_direct_fourier_readback_has_known_amplitude_and_phase(self):
        np = workflow.reference.np
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'port'; t = np.arange(100)*1e-9
            # One coherent cosine and two coherent sine cycles. Their exact
            # one-sided transform is duration and -i*duration respectively.
            values = np.cos(2*np.pi*1e7*t)+np.sin(2*np.pi*2e7*t)
            header = '% start-coordinates: (0,0,0) m\n% stop-coordinates: (0,0,1e-6) m\n'
            with path.open('w') as stream:
                stream.write(header); np.savetxt(stream, np.column_stack((t, values)))
            observed, _, _ = workflow.read_probe(path, np.array([1e7, 2e7]))
            np.testing.assert_allclose(observed, [1e-7, -1e-7j], rtol=1e-12, atol=1e-20)
            text = path.read_text(); path.write_text(text.replace(') m', ') mm'))
            with self.assertRaisesRegex(ValueError, 'coordinate'): workflow.read_probe(path, np.array([1e7]))
            path.write_text(text.replace('(0,0,0)', '(nan,0,0)'))
            with self.assertRaisesRegex(ValueError, 'coordinate'): workflow.read_probe(path, np.array([1e7]))
            with path.open('w') as stream:
                stream.write(header); t[50] += 1e-10; np.savetxt(stream, np.column_stack((t, values)))
            with self.assertRaisesRegex(ValueError, 'Nonuniform'): workflow.read_probe(path, np.array([1e7]))

    def test_timeout_retains_failed_execution_without_a_second_excitation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = workflow.prepare(Path(folder)/'new', 1)
            with patch.object(workflow.subprocess, 'run', side_effect=subprocess.TimeoutExpired('solver', 1)):
                with self.assertRaisesRegex(ValueError, 'Native excitation failed'):
                    workflow.execute(root, 1, 1, sys.executable, timeout=1)
            record = json.loads((root/'isolated/mesh1/port1/execution.json').read_bytes())
            self.assertTrue(record['timed_out']); self.assertIsNone(record['returncode'])
            self.assertTrue(record['inputs_unchanged'])
            self.assertFalse((root/'isolated/mesh1/port2/native.log').exists())

    def test_complex_response_export_preserves_phase_ports_and_existing_outputs(self):
        np = workflow.reference.np
        # Unequal complex off-diagonal terms expose port transposition. Check
        # the literal Touchstone S11, S21, S12, S22 order as well as readback.
        matrix = np.array([[.1+.2j, .03+.04j], [.05+.06j, -.2+.1j]])
        matrices = np.array([matrix, matrix*.9, matrix*.8])
        result = dict(mesh_um=2, frequency_hz=[1e8, 1e9, 2e9],
                      s_real=matrices.real.tolist(), s_imag=matrices.imag.tolist())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); target = root/'audit.json'; workflow.save_result(result, target)
            record = json.loads(target.read_bytes()); self.assertFalse(record['touchstone']['qualified'])
            data = workflow.reference.network((root/'audit.s2p').read_text())
            np.testing.assert_array_equal(data['scattering'], matrices)
            first = next(line for line in (root/'audit.s2p').read_text().splitlines() if not line.startswith(('!', '#')))
            self.assertEqual([float(v) for v in first.split()][1:], [.1, .2, .05, .06, .03, .04, -.2, .1])
            before = target.read_bytes()
            with self.assertRaises(FileExistsError): workflow.save_result(result, target)
            self.assertEqual(target.read_bytes(), before)
            with self.assertRaises(FileExistsError): workflow.save_result(result, root/'new.s2p')
            self.assertFalse((root/'new.s2p').exists())

    def test_completed_probe_bytes_are_bound_to_execution_and_legacy_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); directory = root/'isolated/mesh2/port1/output/run_mesh2_limit-60_data/sub-1'
            directory.mkdir(parents=True)
            for name in ('port_ut_1', 'port_it_1', 'port_ut_2', 'port_it_2'):
                (directory/name).write_text('original raw samples '+name)
            record = dict(schema=2, timed_out=False, output_error='', outputs=workflow.probe_bindings(root, 2, 1))
            self.assertTrue(workflow.verify_probe_bindings(record, root, 2, 1))
            (directory/'port_it_2').write_text('changed raw samples')
            with self.assertRaisesRegex(ValueError, 'changed after execution'):
                workflow.verify_probe_bindings(record, root, 2, 1, allow_legacy=True)
            with self.assertRaisesRegex(ValueError, 'explicit acknowledgement'):
                workflow.verify_probe_bindings({}, root, 2, 1)
            self.assertFalse(workflow.verify_probe_bindings({}, root, 2, 1, allow_legacy=True))
            with self.assertRaises(ValueError): workflow.verify_probe_bindings({'schema': 3}, root, 2, 1, allow_legacy=True)
            (directory/'port_ut_1').write_text('')
            with self.assertRaisesRegex(ValueError, 'Missing or empty'): workflow.probe_bindings(root, 2, 1)

    def test_successful_exit_without_native_probes_is_rejected_and_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            root = workflow.prepare(Path(folder)/'new', 2)
            def no_probes(command, **kwargs):
                kwargs['stdout'].write(b'Starting FDTD simulation for excitation  [1]\nMax. number of timesteps\nRunning FDTD engine\nEnergy: residual (-60.2dB)\nFDTD simulation completed successfully for excitation  [1]\nICSTUDIO_SINGLE_PORT_COMPLETE\n')
                kwargs['stdout'].flush()
                return subprocess.CompletedProcess(command, 0)
            with patch.object(workflow.subprocess, 'run', side_effect=no_probes):
                with self.assertRaisesRegex(ValueError, 'Native excitation failed'):
                    workflow.execute(root, 2, 1, sys.executable)
            record = json.loads((root/'isolated/mesh2/port1/execution.json').read_bytes())
            self.assertEqual(record['returncode'], 0)
            self.assertIn('Missing or empty', record['output_error'])
            self.assertEqual(record['outputs'], {})


if __name__ == '__main__': unittest.main()
