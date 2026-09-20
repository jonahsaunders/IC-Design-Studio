"""Saved OP readouts come from actual MOS vectors, including absent adapters."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from icstudio.model import clone, device, example, uid, validate
from icstudio.saved_bias import capture, annotate, FIELDS
from icstudio.testbenches import create, native_subcircuit, simulate

ROOT = Path(__file__).resolve().parents[1]
ENGINE = Path(os.environ.get('ICSTUDIO_TEST_NGSPICE', ROOT / 'build/runtime/ngspice-run'))
PDK = Path(os.environ.get('ICSTUDIO_TEST_SKY130_PDK', ROOT / 'build/physical-adapter/sky130A'))


def fixture():
    p = example('empty'); bench = p['cells'][0]
    mos = device('NMOS', 'M1', nets={'d': 'D', 'g': 'G', 's': 'S', 'b': 'S'})
    mos['params'].update(w='4u', l='1u', vto='.4', kp='1m', **{'lambda': '.02'})
    dut = dict(id=uid(), name='mos_dut', ports=['D', 'G', 'S'], devices=[mos], shapes=[])
    p['cells'].append(dut)
    bench['devices'] = [device('V', 'VD', value='1.2', nets={'p': 'drain', 'n': '0'}),
        device('V', 'VG', value='.8', nets={'p': 'gate', 'n': '0'}),
        device('X', 'XDUT', cell=dut['id'], nets={'D': 'drain', 'G': 'gate', 'S': '0'})]
    p['analysis']['type'] = 'op'; t = create(p, bench['id'], 'bias_fixture')
    t['analysis']['diagnostic'] = {'kind': 'bias'}; p['testbenches'] = [t]
    return validate(p), t


class SavedBiasTests(unittest.TestCase):
    def test_bias_requires_op_and_unknown_subcircuit_fields_remain_absent(self):
        p, t = fixture(); bad = clone(p)
        bad['testbenches'][0]['analysis']['type'] = 'ac'
        with self.assertRaisesRegex(ValueError, 'bias/OP'): validate(bad)
        text = '.subckt mos_dut D G S\nXOPA D G S S unknown_macro\n.ends mos_dut\n'
        evidence = capture(p, t, text)
        self.assertNotIn('@', evidence['directive'])
        result = {'device_operating_point': {}}
        annotate(result, evidence)
        self.assertEqual(result['bias_capture']['devices'][0]['status'], 'unavailable')
        row = result['diagnostics']['devices'][0]
        self.assertEqual(row['device'], 'XDUT/XOPA')
        self.assertIsNone(row['headroom_V']); self.assertIsNone(row['gm_Id_per_V'])
        self.assertEqual(result['device_operating_point'], {})

    def test_implementation_changed_during_readout_is_rejected(self):
        p, t = fixture()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'included.spice'
            source.write_text(native_subcircuit(p, t['dut_cell']))
            def changed(*args, **kwargs):
                source.write_text(source.read_text() + '* concurrent edit\n')
                return {}
            with patch('icstudio.engines.run_deck', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'implementation changed'):
                    simulate(p, t, str(ENGINE), Path(directory) / 'run', source)

    @unittest.skipUnless(ENGINE.is_file(), 'Actual ngspice required')
    def test_actual_generic_mos_reports_saturation_and_below_vdsat(self):
        p, t = fixture()
        with tempfile.TemporaryDirectory() as directory:
            first = simulate(p, t, str(ENGINE), Path(directory) / 'saturated')
            d = first['device_operating_point']['XDUT/M1']
            self.assertTrue(set(FIELDS) <= d.keys()); self.assertGreater(d['id'], 0)
            self.assertGreater(d['headroom'], .7)
            self.assertAlmostEqual(d['gm'] / d['id'], 5., places=5)
            p['cells'][0]['devices'][0]['value'] = '.05'
            second = simulate(p, t, str(ENGINE), Path(directory) / 'linear')
            self.assertLess(second['device_operating_point']['XDUT/M1']['headroom'], 0)
            self.assertEqual(second['diagnostics']['devices'][0]['bias_status'], 'Below model VDSAT')
            self.assertEqual(second['x'], [0])
            self.assertEqual(second['operating_point']['drain'], .05)

    @unittest.skipUnless(ENGINE.is_file() and (PDK / 'package.json').is_file(), 'Actual linked SKY130 and ngspice required')
    def test_actual_sky130_internal_path_and_extracted_names(self):
        from icstudio.two_stage_opamp import reference
        package = json.loads((PDK / 'package.json').read_text())
        tech = package['technology']; tech.update(package_root=str(PDK.resolve()),
            package_lock={key: package[key] for key in ('id', 'revision', 'files')})
        p, cid, key = reference(tech)
        t = next(t for t in p['testbenches'] if t['id'] == key)
        t['analysis'].update(corner='ss', temperature=0, diagnostic={'kind': 'bias'})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = simulate(p, t, str(ENGINE), root / 'schematic')
            self.assertEqual(len(first['diagnostics']['devices']), 8)
            self.assertTrue(all(row['status'] == 'available' for row in first['bias_capture']['devices']))
            self.assertAlmostEqual(first['device_operating_point']['XDUT/M8']['id'] / 5e-6, 1., places=5)
            source = root / 'renamed.spice'
            source.write_text(native_subcircuit(p, cid).replace('X_M8 ', 'XEXTRACTED8 '))
            second = simulate(p, t, str(ENGINE), root / 'implementation', source)
            self.assertNotIn('XDUT/M8', second['device_operating_point'])
            actual = second['device_operating_point']['XDUT/XEXTRACTED8']
            self.assertAlmostEqual(actual['id'], first['device_operating_point']['XDUT/M8']['id'], places=12)
            self.assertIn('no schematic device-name correspondence', second['bias_capture']['scope'])


if __name__ == '__main__': unittest.main()
