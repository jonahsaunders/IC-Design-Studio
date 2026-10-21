"""SPICE multiplicity retains its positive-value contract through source aliases."""
import json
from pathlib import Path
import unittest

from icstudio.catalog import create_device, parameter_values
from icstudio.interchange import spice
from icstudio.model import clone, example

ROOT = Path(__file__).resolve().parents[1]


class CatalogMultiplicityTests(unittest.TestCase):
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
        self.assertEqual(counts, {'sky130A': 94, 'gf180mcuC': 77, 'gf180mcuD': 77, 'ihp-sg13g2': 38})


if __name__ == '__main__': unittest.main()
