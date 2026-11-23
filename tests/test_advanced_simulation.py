"""Verify native RF numbers and external simulator capture with a real engine."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from icstudio import external_simulation, job_store, rf_network, worker
from icstudio.engines import parse_raw
from icstudio.model import device, example
from icstudio.spice_program import find_ngspice


NGSPICE = find_ngspice(os.environ.get('ICSTUDIO_TEST_NGSPICE', ''))


class AdvancedSimulationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.project = example('rc')
        self.cell = self.project['top']
        self.project['cells'][0]['devices'] = [device('R', 'Rpath', 100, 100, value='50', nets={'p': 'in', 'n': 'out'})]

    def execute(self, job, name='job', expected=0):
        folder = self.root/name
        folder.mkdir()
        (folder/'input.json').write_text(json.dumps(job), encoding='utf-8')
        self.assertEqual(worker.main(folder/'input.json', folder/'result.json'), expected)
        return folder

    def rf_job(self, ports):
        return rf_network.prepare(self.project, self.cell,
            dict(ports=rf_network.port_lines(ports), impedance=50, start=1e6, stop=3e6,
                 points=3, temperature=27, corner='nominal'), NGSPICE)

    @unittest.skipUnless(NGSPICE, 'Native ngspice is required')
    def test_one_port_reactive_impedance_and_touchstone(self):
        self.project['cells'][0]['devices'] = [device('C', 'C1', 100, 100, value='1n', nets={'p': 'in', 'n': '0'})]
        validated = self.execute(self.rf_job('in 0'))
        result = job_store.read_result(validated/'result.json', self.project['id'], False)
        tables = result['rf_network']['matrices']
        self.assertEqual(list(tables['S']), ['S11'])
        self.assertAlmostEqual(tables['Z']['Z11'][0][1], -159.154943091895)
        self.assertAlmostEqual(tables['Y']['Y11'][0][1], .00628318530718)
        self.assertEqual(len(rf_network.touchstone(result).splitlines()[1].split()), 3)

    @unittest.skipUnless(NGSPICE, 'Native ngspice is required')
    def test_series_resistor_scattering_and_undefined_impedance(self):
        folder = self.execute(self.rf_job('in 0\nout 0'))
        result = job_store.read_result(folder/'result.json', self.project['id'], False)
        self.assertEqual(result['x'], [1e6, 2e6, 3e6])
        tables = result['rf_network']['matrices']
        self.assertNotIn('Z', tables)
        for name, value in {'S11': 1/3, 'S22': 1/3, 'S21': 2/3, 'S12': 2/3}.items():
            for real, imag in tables['S'][name]:
                self.assertAlmostEqual(real, value, places=12)
                self.assertEqual(imag, 0)
        self.assertAlmostEqual(tables['Y']['Y11'][0][0], .02)
        exported = rf_network.touchstone(result)
        self.assertEqual(exported.splitlines()[0], '# Hz S RI R 50')
        self.assertEqual(len(exported.splitlines()[1].split()), 9)
        (folder/'rf.raw').write_text('invalid', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'artifacts'):
            job_store.read_result(folder/'result.json', self.project['id'], False)

    @unittest.skipUnless(NGSPICE, 'Native ngspice is required')
    def test_grounded_three_port_y_z_and_touchstone(self):
        self.project['cells'][0]['devices'].extend([
            device('R', 'Rreturn', 140, 100, value='50', nets={'p': 'out', 'n': '0'}),
            device('R', 'Raux', 170, 100, value='100', nets={'p': 'aux', 'n': '0'}),
        ])
        folder = self.execute(self.rf_job('in 0\nout 0\naux 0'))
        result = job_store.read_result(folder/'result.json', self.project['id'], False)
        tables = result['rf_network']['matrices']
        self.assertEqual(len(tables['S']), 9)
        self.assertAlmostEqual(tables['S']['S33'][0][0], 1/3)
        self.assertAlmostEqual(tables['Z']['Z11'][0][0], 100)
        self.assertAlmostEqual(tables['Z']['Z12'][0][0], 50)
        self.assertAlmostEqual(tables['Z']['Z33'][0][0], 100)
        self.assertAlmostEqual(tables['Y']['Y33'][0][0], .01)
        lines = rf_network.touchstone(result).splitlines()
        self.assertEqual([len(line.split()) for line in lines[1:4]], [7, 6, 6])

    @unittest.skipUnless(NGSPICE, 'Native ngspice is required')
    def test_external_engine_runs_the_snapshot_and_verifies_outputs(self):
        deck = self.root/'bench.cir'
        deck.write_text('Divider\nV1 in 0 1\nR1 in out 1k\n.include load.inc\n.op\n.end\n', encoding='ascii')
        load = self.root/'load.inc'
        load.write_text('R2 out 0 1k\n', encoding='ascii')
        job = external_simulation.prepare(self.project, self.cell, NGSPICE,
            ['-n', '-D', 'filetype=ascii', '-b', '-r', 'wave.raw', '{input}'],
            str(deck), ['load.inc'], ['wave.raw'])
        load.write_text('R2 out 0 2k\n', encoding='ascii')
        folder = self.execute(job)
        result = job_store.read_result(folder/'result.json', self.project['id'], False)
        self.assertIn('wave.raw', result['external_outputs'])
        raw = folder/'external'/'wave.raw'
        columns, samples, _ = parse_raw(raw)
        self.assertAlmostEqual(samples[0][columns.index('v(out)')], .5)
        raw.write_text('changed', encoding='ascii')
        with self.assertRaisesRegex(ValueError, 'artifacts'):
            job_store.read_result(folder/'result.json', self.project['id'], False)

    def test_csv_requires_one_ordered_sweep(self):
        path = self.root/'response.csv'
        path.write_text('INDEX,FREQ,VR(OUT),VI(OUT)\n0,0,0.4,0\n1,1e6,0.2,0.1\nEnd of Xyce(TM) Simulation\n', encoding='ascii')
        self.assertEqual(external_simulation.read_table(path),
                         ([0, 1e6], 'FREQ', {'VR(OUT)': [.4, .2], 'VI(OUT)': [0, .1]}))
        path.write_text('FREQ,V(OUT)\n100,0\n100,1\n', encoding='ascii')
        with self.assertRaisesRegex(ValueError, 'increasing sweep'):
            external_simulation.read_table(path)
