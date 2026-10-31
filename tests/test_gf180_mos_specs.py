"""Public numeric limits must remain independent from simulated results."""
from pathlib import Path
import json
import math
import shutil
import tempfile
import unittest
from unittest.mock import patch
from icstudio.model import clone
from scripts.qualify_gf180_mos_specs import SOURCES,source_contract,bound,threshold,rows,PINS,compare,raw,fixture,altered,independent
from scripts.qualify_standard_mos import load_technology


class GF180MosSpecificationTests(unittest.TestCase):
    def test_locked_table_preserves_signed_units_and_one_sided_limits(self):
        c=source_contract();n,p=c['limits']['n'],c['limits']['p']
        self.assertEqual((n['idsat_uA_um']['minimum'],n['idsat_uA_um']['maximum']),(430,590))
        self.assertEqual((p['idsat_uA_um']['minimum'],p['idsat_uA_um']['maximum']),(-290,-210))
        self.assertEqual((n['ioff_pA_um']['minimum'],n['ioff_pA_um']['maximum']),(None,100))
        self.assertEqual((p['ioff_pA_um']['minimum'],p['ioff_pA_um']['maximum']),(-20,None))
        self.assertEqual((c['width_um'],c['length_um'],c['temperature_c']),(10,.28,25))

    def test_rounding_and_numeric_tolerance_cannot_widen_a_published_bound(self):
        n=source_contract()['limits']['n']['idsat_uA_um'];p=source_contract()['limits']['p']['idsat_uA_um']
        for value in (430,510,590):self.assertEqual(bound(value,n)['status'],'PASS')
        for value in (429.999999999,590.000000001,590.277):self.assertEqual(bound(value,n)['status'],'OUTSIDE_PUBLISHED_BOUND')
        self.assertEqual(bound(-290.39,p)['status'],'OUTSIDE_PUBLISHED_BOUND')
        for value in (math.nan,math.inf,-math.inf):
            with self.assertRaises(ValueError):bound(value,n)

    def test_changed_source_cannot_be_approved_by_rewriting_its_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'source';shutil.copytree(SOURCES,root);p=root/'docs/analog/spice/elec_specs/tables_clear/1_Low_Voltage_Devices.csv'
            p.write_bytes(p.read_bytes().replace(b'430,510,590',b'430,510,999'))
            from icstudio.model import file_digest
            lock=json.loads((root/'sources.json').read_bytes());lock[p.relative_to(root).as_posix()]['sha256']=file_digest(p);(root/'sources.json').write_text(json.dumps(lock),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Changed public specification source'):source_contract(root)

    def test_linear_threshold_recovers_known_channel_voltage_for_both_polarities(self):
        # Exact linear-region I = beta * VDS * (VGS - VT - VDS/2).
        # Mobility reduction at larger gate values creates an interior gm peak.
        x=[i*.01 for i in range(201)];amps=[0.001*.05*max(0,v-.525)/(1+max(0,v-1)) for v in x]
        for pol,sign in (('n',1),('p',-1)):
            m=threshold(x,[sign*i for i in amps],pol)
            self.assertAlmostEqual(m['tangent_intercept_v'],sign*.525,places=10)
            self.assertAlmostEqual(m['linear_threshold_v'],sign*.5,places=10)
            self.assertFalse(m['used_for_acceptance'])
        with self.assertRaises(ValueError):threshold(x,[0]*len(x),'n')
        with self.assertRaises(ValueError):threshold(x[::-1],amps,'n')
        with self.assertRaises(ValueError):threshold(x,amps[:-1],'n')

    def response(self):
        return dict(x=list(range(9)),currents={row['tag']+pin:[(i+1)*1e-12 for i in range(9)] for row in rows() for pin in PINS})

    def test_missing_samples_or_nonfinite_currents_cannot_escape_comparison(self):
        data=self.response();self.assertEqual(compare(data,clone(data))['status'],'PASS')
        for fault in ('short','missing','nan','scale'):
            bad=clone(data)
            if fault=='short':bad['currents']['nlind'].pop()
            elif fault=='missing':del bad['currents']['plinb']
            elif fault=='nan':bad['currents']['noffd'][0]=math.nan
            else:bad['currents']['noffd']=[v*2 for v in bad['currents']['noffd']]
            if fault=='scale':self.assertEqual(compare(bad,data)['status'],'MISMATCH')
            else:
                with self.assertRaises(ValueError):compare(bad,data)

    def test_actual_terminal_bias_and_current_conservation_are_checked(self):
        step=3.3/8;names=['v-sweep'];columns=[[i*step for i in range(9)]]
        for row in rows():
            for pin in PINS:
                names.append('v('+row['tag']+pin+')');columns.append([row['sign']*v for v in columns[0]] if pin=='g' and row['mode']!='off' else [row['drain_v'] if pin=='d' else 0]*9)
                names.append('i(v'+row['tag']+pin+')');columns.append([row['sign']*(1e-6 if pin=='d' else -1e-6 if pin=='s' else 0)]*9)
        data=[list(v) for v in zip(*columns)]
        with patch('scripts.qualify_gf180_mos_specs.file_digest',return_value='a'*64):
            with patch('scripts.qualify_gf180_mos_specs.parse_raw',return_value=(names,data,False)):
                self.assertEqual(len(raw(Path('unused'),step)['currents']),24)
            for column in ('v(nsatd)','i(vpsatb)'):
                bad=clone(data);bad[3][names.index(column)]+=.01
                with patch('scripts.qualify_gf180_mos_specs.parse_raw',return_value=(names,bad,False)),self.assertRaises(ValueError):raw(Path('unused'),step)

    def test_faults_change_devices_and_keep_the_reference_and_probes_intact(self):
        tech,_=load_technology('gf180mcuC');p,_=fixture(tech);before=clone(p)
        for fault in ('wrong-multiplicity','wrong-width','gate-drain-swap'):
            changed=altered(p,fault)
            a=[d for d in p['cells'][0]['devices'] if not d.get('model_ref')];b=[d for d in changed['cells'][0]['devices'] if not d.get('model_ref')];self.assertEqual(a,b)
            self.assertEqual(len([d for d in changed['cells'][0]['devices'] if d.get('model_ref')]),6)
            self.assertNotEqual(p,changed)
        self.assertEqual(p,before)
        text=independent(tech,'gf180mcuC','sf',.005)
        self.assertIn('nfet_03v3 w=1e-05 l=2.8e-07',text);self.assertIn('.temp 25',text);self.assertIn('V={-3.63}',text)


if __name__=='__main__':unittest.main()
