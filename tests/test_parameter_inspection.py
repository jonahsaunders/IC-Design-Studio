"""The same formula responds to edited dimensions in both bundled processes."""
import json
from pathlib import Path
import unittest
from icstudio.model import clone
from icstudio.catalog import create_device, parameter_values, parameter_details, _formula_tree

ROOT=Path(__file__).resolve().parents[1]


class ParameterInspection(unittest.TestCase):
    def processes(self):
        for name in ('gf180mcuD','sky130A'):
            package=json.loads((ROOT/'icstudio/assets/pdks'/name/'package.json').read_text())
            tech=package['technology'];tech['package_lock']={key:package[key] for key in ('id','revision','files')}
            key=next(k for k,b in tech['simulation']['catalog'].items() if b['kind']=='NMOS' and not b.get('unavailable'))
            yield tech['simulation']['catalog'][key],create_device(tech,key,'M1')

    def test_live_diffusion_defaults_override_and_reset_in_both_process_units(self):
        for binding,device in self.processes():
            original=parameter_values(binding,device)
            device['params']['w']='4u';wide=parameter_values(binding,device)
            self.assertAlmostEqual(wide['ad']/original['ad'],wide['w']/original['w'])
            device['model_params']['ad']='9';rows={r['name']:r for r in parameter_details(binding,device)}
            self.assertEqual(rows['ad']['source'],'override');self.assertEqual(rows['ad']['value'],9)
            del device['model_params']['ad'];self.assertEqual(parameter_values(binding,device),wide)
            self.assertEqual(next(r for r in parameter_details(binding,device) if r['name']=='ad')['source'],'default')

    def test_constraints_apply_to_dimensions_and_finger_count(self):
        for binding,device in self.processes():
            for key,value in [('w','0'),('l','-1u')]:
                changed=clone(device);changed['params'][key]=value
                with self.assertRaisesRegex(ValueError,key+' must be positive'):parameter_values(binding,changed)
            device['model_params']['nf']='1.5'
            with self.assertRaisesRegex(ValueError,'whole number'):parameter_values(binding,device)
            device['model_params'].clear();binding=clone(binding)
            binding['parameters']['w']['minimum']=parameter_values(binding,device)['w']*2
            with self.assertRaisesRegex(ValueError,'PDK minimum'):parameter_values(binding,device)

    def test_cached_syntax_never_reuses_a_previous_numeric_result(self):
        from icstudio.catalog import numeric_formula
        _formula_tree.cache_clear()
        self.assertEqual(numeric_formula('w / nf',{'w':8,'nf':2}),4)
        self.assertEqual(numeric_formula('w / nf',{'w':20,'nf':4}),5)
        self.assertEqual(_formula_tree.cache_info().hits,1)
        with self.assertRaises(ValueError):numeric_formula('__import__("os")',{})

