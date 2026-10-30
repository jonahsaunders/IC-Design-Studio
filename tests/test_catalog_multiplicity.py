"""SPICE multiplicity retains its positive-value contract through source aliases."""
import json
from pathlib import Path
import unittest

from icstudio.catalog import create_device, parameter_values
from icstudio.interchange import spice
from icstudio.model import clone, example

ROOT = Path(__file__).resolve().parents[1]


class CatalogMultiplicityTests(unittest.TestCase):
    def test_pre_pw2dn_default_retains96_bindings_and_new_candidate97(self):
        from scripts.sky130_pw2dn_source import predecessor,BASE
        from icstudio.model import file_digest
        with predecessor(ROOT/'icstudio/assets/pdks/sky130A') as source:
            self.assertEqual(file_digest(source/'package.json'),BASE)
            old=json.loads((source/'package.json').read_bytes())['technology']['simulation']['catalog']
            available=[entry for entry in old.values() if not entry.get('unavailable') and not entry.get('utility')]
            self.assertEqual(len(available),96)
            self.assertFalse(old['sky130_fd_pr/nfet_g5v0d10v5_nvt_esd.sym']['unavailable'])
            key='sky130_fd_pr/diode__sky130_fd_pr__model__parasitic__rf_diode_pw2dn.sym'
            self.assertTrue(old[key]['unavailable'])

    def test_alias_cannot_bypass_multiplicity_checks_but_other_signed_values_remain_valid(self):
        for emitted in ('m', 'M'):
            binding = dict(parameters={'copies': {'default': '1'}, 'offset': {'default': '-2'}},
                           emit_parameters={emitted: 'copies', 'shift': 'offset'})
            for value in ('0', '-1', '-2*3'):
                with self.subTest(emitted=emitted, value=value), self.assertRaisesRegex(ValueError, 'copies must be positive'):
                    parameter_values(binding, dict(kind='PDK', model_params={'copies': value}))
            for value in ('.5', '1', '2'):
                result = parameter_values(binding, dict(kind='PDK', model_params={'copies': value}))
                self.assertEqual(result, {'copies': float(value), 'offset': -2.})

    def test_actual_sky130_mim_aliases_reject_nonpositive_exports(self):
        package = json.loads((ROOT/'icstudio/assets/pdks/sky130A/package.json').read_bytes())
        tech = clone(package['technology']); tech['package_lock'] = {k: package[k] for k in ('id', 'revision', 'files')}
        tech['package_root'] = str(ROOT/'icstudio/assets/pdks/sky130A')
        for name in ('cap_mim_m3_1', 'cap_mim_m3_2'):
            key = 'sky130_fd_pr/'+name+'.sym'; entry = tech['simulation']['catalog'][key]
            self.assertEqual(entry['emit_parameters']['m'], 'mf')
            p = example('empty'); p['pdk'] = clone(tech)
            d = create_device(p['pdk'], key, 'C1'); p['cells'][0]['devices'] = [d]
            for value in ('0', '-1'):
                d['model_params']['mf'] = value
                with self.subTest(model=name, value=value), self.assertRaisesRegex(ValueError, 'mf must be positive'):
                    spice(p)
            d['model_params']['mf'] = '.5'
            line = next(line for line in spice(p).splitlines() if line.startswith('X_C1 '))
            self.assertIn(' m=0.5 ', line)

    def test_every_available_bundled_default_keeps_valid_multiplicity(self):
        counts = {}
        for target in ('sky130A', 'gf180mcuC', 'gf180mcuD', 'ihp-sg13g2'):
            package = json.loads((ROOT/'icstudio/assets/pdks'/target/'package.json').read_bytes())
            tech = clone(package['technology']); tech['package_lock'] = {k: package[k] for k in ('id', 'revision', 'files')}
            count = 0
            for key, entry in tech['simulation']['catalog'].items():
                if entry.get('unavailable'): continue
                d = create_device(tech, key, 'DUT'); values = parameter_values(entry, d)
                for emitted, source in entry.get('emit_parameters', {}).items():
                    if emitted.casefold() == 'm': self.assertGreater(values[source], 0, (target, key))
                count += 1
            counts[target] = count
        self.assertEqual(counts, {'sky130A': 97, 'gf180mcuC': 77, 'gf180mcuD': 77, 'ihp-sg13g2': 38})


    def test_current_esd_default_keeps_source_multiplier_one_and_rejects_nonpositive_values(self):
        from scripts.prepare_sky130_esd_nvt import KEY,MODEL
        package=json.loads((ROOT/'icstudio/assets/pdks/sky130A/package.json').read_bytes())
        tech=clone(package['technology']);tech['package_lock']={k:package[k] for k in ('id','revision','files')}
        entry=tech['simulation']['catalog'][KEY];d=create_device(tech,KEY,'ESD')
        self.assertFalse(entry['unavailable']);self.assertEqual(entry['model'],MODEL)
        self.assertEqual(entry['emit_parameters']['m'],'mult');self.assertEqual(parameter_values(entry,d)['mult'],1)
        for value in ('.5','1','3'):
            d['model_params']['mult']=value;self.assertEqual(parameter_values(entry,d)['mult'],float(value))
        for value in ('0','-1','-2*3'):
            d['model_params']['mult']=value
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'mult must be positive'):parameter_values(entry,d)

    def test_historical_rf_default_retains_95_available_bindings_and_original_multiplicity(self):
        from scripts.prepare_sky130_esd_nvt import predecessor,BASE,KEY
        from icstudio.model import file_digest
        with predecessor(ROOT/'icstudio/assets/pdks/sky130A') as source:
            self.assertEqual(file_digest(source/'package.json'),BASE)
            package=json.loads((source/'package.json').read_bytes());tech=clone(package['technology'])
            tech['package_lock']={k:package[k] for k in ('id','revision','files')}
            self.assertTrue(tech['simulation']['catalog'][KEY]['unavailable'])
            available=[(key,entry) for key,entry in tech['simulation']['catalog'].items() if not entry.get('unavailable')]
            self.assertEqual(len(available),95)
            for key,entry in available:
                values=parameter_values(entry,create_device(tech,key,'DUT'))
                for emitted,name in entry.get('emit_parameters',{}).items():
                    if emitted.casefold()=='m':self.assertGreater(values[name],0,(key,name))

if __name__ == '__main__': unittest.main()

