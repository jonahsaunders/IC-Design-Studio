"""Capacitor evidence must reject missing ports, wrong phase and wrong copies."""
import cmath, math, tempfile, unittest
from copy import deepcopy
from pathlib import Path
from scripts.qualify_capacitor_families import compare, scaling, FREQUENCIES
from scripts.build_ngspice_runtime import correct_capacitor_multiplier
from scripts.verify_ngspice_capacitors import validate, CASES


class CapacitorQualificationTests(unittest.TestCase):
    def fixture(self):
        rows = [dict(tag='c0s0m'+str(m), copies=m, pins=('a', 'b', 'body')) for m in (1, 3)]
        result = dict(x=FREQUENCIES, currents={}, current_phase={})
        for row in rows:
            for port, gain in enumerate((-1, .8, .2)):
                values = [2j*math.pi*f*1e-12*row['copies']*gain for f in FREQUENCIES]
                key = 'v'+row['tag']+'p'+str(port)
                result['currents'][key] = [abs(v) for v in values]
                result['current_phase'][key] = [math.degrees(cmath.phase(v)) for v in values]
        return rows, result

    def test_every_port_and_phase_is_required(self):
        rows, ref = self.fixture(); self.assertEqual(compare(ref, ref, rows, 0)['status'], 'PASS')
        for section in ('currents', 'current_phase'):
            for key in ref[section]:
                changed = deepcopy(ref); del changed[section][key]
                with self.subTest(section=section, key=key), self.assertRaises(ValueError): compare(changed, ref, rows, 0)
        changed = deepcopy(ref); changed['current_phase']['vc0s0m1p2'] = [0]*26
        self.assertEqual(compare(changed, ref, rows, 0)['status'], 'MISMATCH')

    def test_zero_reference_and_wrong_frequency_cannot_pass(self):
        rows, ref = self.fixture()
        for fault in ('zero', 'frequency', 'nonfinite'):
            changed = deepcopy(ref)
            if fault == 'zero': changed['currents']['vc0s0m1p0'] = [0]*26
            elif fault == 'frequency': changed['x'] = [f*10 for f in FREQUENCIES]
            else: changed['currents']['vc0s0m1p0'][0] = math.nan
            with self.subTest(fault=fault), self.assertRaises(ValueError): compare(changed, changed, rows, 0)

    def test_wrong_parallel_count_is_detected_independently(self):
        rows, ref = self.fixture(); self.assertEqual(scaling(ref, rows)['status'], 'PASS')
        for factor in (1/3, 1.2, 3):
            changed = deepcopy(ref)
            for key, values in changed['currents'].items():
                if 'm3' in key: changed['currents'][key] = [v*factor for v in values]
            self.assertEqual(scaling(changed, rows)['status'], 'MISMATCH')

    def test_unreviewed_engine_source_cannot_be_patched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root/'src/frontend/inpcom.c'; source.parent.mkdir(parents=True)
            source.write_bytes(b'unreviewed simulator'); retained = root/'retained'; retained.mkdir()
            with self.assertRaisesRegex(ValueError, 'Unexpected ngspice'): correct_capacitor_multiplier(root, retained)
            self.assertEqual(source.read_bytes(), b'unreviewed simulator'); self.assertEqual(list(retained.iterdir()), [])

    def test_analytical_engine_probe_rejects_gain_and_phase_faults(self):
        cases = {**{n: v[1] for n, v in CASES.items()}, 'nested': 3, 'charge': 3}
        variables = ['frequency']+['i(v'+n+')' for n in cases]
        rows = [[complex(f)]+[-2j*math.pi*f*m*1e-12 for m in cases.values()] for f in FREQUENCIES]
        self.assertEqual(validate(variables, rows, True, 0)['status'], 'PASS')
        for factor in (0, -1, 1.2, 1j):
            bad = deepcopy(rows)
            for row in bad: row[2] *= factor
            with self.assertRaisesRegex(ValueError, 'mismatch'): validate(variables, bad, True, 0)


if __name__ == '__main__': unittest.main()
