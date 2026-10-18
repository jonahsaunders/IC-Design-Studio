import json
from pathlib import Path
import tempfile
import unittest
from icstudio.catalog import create_device, parameter_values
from icstudio.model import clone, file_digest
from scripts.prepare_sky130_rf_qualification import BASE, COMMON, ROOT, derivative, prepare, public_sources


class RFCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.base=ROOT/'icstudio/assets/pdks/sky130A';cls.out=Path(cls.tmp.name)/'candidate'
        cls.result=prepare(cls.base,cls.out);cls.package=json.loads((cls.out/'package.json').read_bytes())
        cls.tech=clone(cls.package['technology']);cls.tech['package_lock']={k:cls.package[k] for k in ('id','revision','files')}

    def test_exact_originals_and_all_old_bindings_are_retained(self):
        original=json.loads((self.base/'package.json').read_bytes())
        self.assertEqual(file_digest(self.base/'package.json'), BASE)
        for name,expected in original['files'].items():
            self.assertEqual(file_digest(self.out/name), expected, name)
        old=original['technology']['simulation']['catalog'];new=self.package['technology']['simulation']['catalog']
        changed={key for key in old if old[key]!=new[key]}
        self.assertEqual(changed, {'sky130_fd_pr/diode__'+COMMON+'rf_diode_'+m+'.sym' for m in ('ps2nw','pw2dn')})
        self.assertEqual(set(old),set(new));self.assertFalse(self.result['qualified']);self.assertFalse(self.result['default_promoted'])
        lock,sources=public_sources()
        for name,content in sources.items():
            self.assertEqual((self.out/('libs.tech/ngspice/icstudio-rf-diodes/original/'+name)).read_bytes(),content)
        self.assertEqual(lock['license'],'Apache-2.0')

    def test_geometry_is_derived_and_terminal_roles_are_explicit(self):
        for model in ('ps2nw','pw2dn'):
            key='sky130_fd_pr/diode__'+COMMON+'rf_diode_'+model+'.sym'
            binding=self.tech['simulation']['catalog'][key];d=create_device(self.tech,key,'DUT')
            self.assertEqual(binding['prefix'],'X');self.assertEqual(binding['pin_order'],['d0','d1'])
            d['model_params']={'w':4,'l':2}
            self.assertEqual(parameter_values(binding,d),dict(w=4,l=2,area=8,perim=12))
            for override in (dict(w=0),dict(l=-1),dict(area=4),dict(perim=8),dict(m=2)):
                bad=clone(d);bad['model_params'].update(override)
                with self.assertRaises(ValueError):parameter_values(binding,bad)

    def test_derivative_requires_original_hash_and_only_adds_perimeter(self):
        _,sources=public_sources()
        for model in ('ps2nw','pw2dn'):
            source=sources[COMMON+'rf_diode_'+model+'.model.spice']
            actual=derivative(model,source).split(b'\n',2)[2]
            self.assertEqual(actual.replace(b'area = 1.0e-18 pj = {perim}',b'area = 1.0e-18'),source)
            with self.assertRaises(ValueError):derivative(model,source+b'\n')
        with self.assertRaises(ValueError):derivative('other',b'')

    def test_build_never_overwrites_existing_output(self):
        before=(self.out/'package.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'new RF candidate'):
            prepare(self.base,self.out)
        self.assertEqual((self.out/'package.json').read_bytes(),before)


if __name__ == '__main__':unittest.main()
