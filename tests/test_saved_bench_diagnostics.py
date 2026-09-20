"""Shared saved diagnostic requirements, units and real SPICE before/after data."""
import math
import os
import tempfile
import unittest
from pathlib import Path

from icstudio.model import clone, device, example, uid, validate
from icstudio.testbenches import create, deck, measure, native_subcircuit, simulate

ROOT=Path(__file__).resolve().parents[1]
ENGINE=Path(os.environ.get('ICSTUDIO_TEST_NGSPICE',str(ROOT/'build/runtime/ngspice-run')))


def fixture(typ='noise'):
    p=example('empty');bench=p['cells'][0]
    dut=dict(id=uid(),name='resistor',ports=['IN','OUT'],devices=[device('R','R1',value='1k',nets={'p':'IN','n':'OUT'})],shapes=[])
    p['cells'].append(dut)
    bench['devices']=[device('V','VIN',value='1',nets={'p':'inp','n':'0'}),
                      device('X','XDUT',cell=dut['id'],nets={'IN':'inp','OUT':'out'})]
    p['analysis'].update(type=typ,output='out',noise_source='VIN',start='100',end='100k',points=30)
    if typ=='tran':bench['devices'].append(device('C','CL',value='1n',nets={'p':'out','n':'0'}))
    t=create(p,bench['id'],'saved_diagnostic')
    if typ=='noise':
        t['analysis']['diagnostic']=dict(kind='noise',output='out',source='VIN')
        t['measurements']=[dict(name='input_noise',kind='input_noise',max='10u'),dict(name='output_noise',kind='output_noise',max='10u')]
    elif typ=='tran':
        t['analysis'].update(stop='100u',step='100n',diagnostic=dict(kind='startup',output='out',source='VIN',
            minimum='.99',maximum='1.01',ramp='10u',stop='100u',initial_node='out',initial_voltage='0',supply='1'))
        t['measurements']=[dict(name='settling',kind='startup_settling',max='30u')]
    p['testbenches']=[t]
    return validate(p),t


class SavedDiagnostics(unittest.TestCase):
    def test_hierarchical_bsim_noise_vectors_include_device_subtotals(self):
        from icstudio.analog_diagnostics import noise_report
        parent='onoise.m.xdut.x_m8.msky130_fd_pr__nfet_01v8'
        variables=['frequency','onoise_spectrum','inoise_spectrum',parent,parent+'.id',parent+'.1overf']
        report=noise_report(variables,[[10,5,2,5,3,4],[110,5,2,5,3,4]])
        rows={r['vector']:r for r in report['contributors']}
        self.assertEqual(report['output_rms_V'],50.)
        self.assertEqual(report['input_rms_V'],20.)
        self.assertTrue(rows[parent]['subtotal'])
        self.assertFalse(rows[parent+'.id']['subtotal'])
        self.assertEqual(rows[parent+'.1overf']['rms_V'],40.)

    def test_noise_voltage_units_and_mismatched_diagnostic_are_rejected(self):
        p,t=fixture()
        t['measurements'].append(dict(name='density_as_voltage',kind='voltage',node='out'))
        with self.assertRaisesRegex(ValueError,'density'):
            validate(p)
        t['measurements'].pop();t['analysis']['diagnostic']['output']='inp'
        with self.assertRaisesRegex(ValueError,'source/output'):
            validate(p)

    def test_loop_measurements_require_captured_crossing(self):
        t={'analysis':{'type':'ac'},'probes':['out'], 'measurements':[dict(name='margin',kind='phase_margin',min='45')]}
        result={'x':[1.,10.],'traces':{'out':[10.,9.]},'diagnostics':{'kind':'loop','unity_crossings':[]}}
        row=measure(result,t)['measurements'][0]
        self.assertEqual(row['status'],'failed')
        self.assertIn('No measured unity-gain crossing',row['error'])
        result['diagnostics']['unity_crossings']=[{'frequency_Hz':10.,'phase_margin_deg':70.},{'frequency_Hz':20.,'phase_margin_deg':30.}]
        row=measure(result,t)['measurements'][0]
        self.assertEqual(row['value'],30.)
        self.assertEqual(row['unit'],'deg')
        self.assertEqual(row['status'],'failed')

    def test_startup_deck_uses_actual_pvt_supply_once_and_keeps_extracted_include(self):
        p,t=fixture('tran')
        p['cells'][0]['devices'][0]['value']='.8'
        t['analysis']['uic']=True
        text=deck(p,t,Path('/tmp/extracted.spice'))
        self.assertIn('PWL(0 0 1e-05 0.8 0.0001 0.8)',text)
        self.assertEqual(text.lower().count(' uic'),1)
        self.assertIn('.include "/tmp/extracted.spice"',text)

    @unittest.skipUnless(ENGINE.is_file(),'Set ICSTUDIO_TEST_NGSPICE for real saved diagnostic verification')
    def test_actual_resistor_noise_matches_thermal_noise_and_extracted_resistance(self):
        p,t=fixture()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            before=simulate(p,t,str(ENGINE),root/'schematic')
            expected=math.sqrt(4*1.380649e-23*300.15*1000*(100000-100))
            for row in before['measurements']['measurements']:
                self.assertEqual(row['status'],'passed')
                self.assertAlmostEqual(row['value']/expected,1.,places=3)
                self.assertEqual(row['unit'],'V')
            modified=clone(p);modified['cells'][1]['devices'][0]['value']='2k'
            source=root/'extracted.spice';source.write_text(native_subcircuit(modified,t['dut_cell']))
            after=simulate(p,t,str(ENGINE),root/'post-layout',source,['IN','OUT'])
            self.assertAlmostEqual(after['diagnostics']['input_rms_V']/before['diagnostics']['input_rms_V'],math.sqrt(2),places=3)
            strict=clone(t);strict['measurements'][0]['max']='1n'
            self.assertEqual(measure(after,strict)['status'],'failed')

    @unittest.skipUnless(ENGINE.is_file(),'Set ICSTUDIO_TEST_NGSPICE for real saved diagnostic verification')
    def test_actual_startup_detects_wrong_supply_and_retains_saved_settings(self):
        p,t=fixture('tran')
        with tempfile.TemporaryDirectory() as folder:
            before=simulate(p,t,str(ENGINE),Path(folder)/'good')
            self.assertEqual(before['measurements']['status'],'passed')
            # A permanent sub-band final voltage must never count as settled.
            p['cells'][0]['devices'][0]['value']='.8'
            after=simulate(p,t,str(ENGINE),Path(folder)/'bad')
            self.assertEqual(after['measurements']['status'],'failed')
            self.assertEqual(after['settings'],t['analysis'])
            self.assertEqual(after['effective_analysis']['diagnostic']['supply'],.8)


if __name__=='__main__':unittest.main()
