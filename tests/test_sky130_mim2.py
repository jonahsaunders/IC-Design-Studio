"""Second MiM topology, physical dimensions and editing regression checks."""
import tempfile
import unittest
from pathlib import Path

from icstudio.catalog import create_device
from icstudio.model import clone, example, save_project, load_project
from icstudio.sky130_devices import install, geometry
from icstudio.sky130_mim2 import layers, specification
from icstudio.physical import connectivity
from icstudio.layout import polygon, kdb
from tests.test_sky130_devices import technology


def fixture(w=2, l=2, count=1):
    p = example('empty');p['pdk'] = technology();c = p['cells'][0]
    d = create_device(p['pdk'], 'sky130_fd_pr/cap_mim_m3_2.sym', 'C1')
    d['model_params'].update(w=w, l=l, mf=count);d['nets'] = dict(c0='P', c1='N')
    c['devices'] = [d];install(p, c['id'], d['id'])
    return p, c, d


class Sky130Mim2Tests(unittest.TestCase):
    def test_second_plate_keeps_electrodes_separate_with_actual_cut_geometry(self):
        from icstudio.layout_routing import conductors
        for w, l, count in ((2,2,1), (3.005,3.005,1), (10,10,3), (30,30,1), (2,2,16)):
            with self.subTest(w=w,l=l,count=count):
                p,c,d = fixture(w,l,count);ls=layers(p['pdk'])
                self.assertFalse(connectivity(p,c['id'])['issues'])
                self.assertNotIn(ls['cap2m'], conductors(p['pdk']))
                self.assertEqual({v['layer'] for v in c['layout_pins']}, {ls['m5']})
                self.assertEqual(specification(p['pdk'],d)['dimensions_nm'],dict(w=round(w*1000),l=round(l*1000)))
                cuts=kdb().Region()
                for s in c['shapes']:
                    if s['layer']==ls['via4']:
                        b=polygon(s).bbox();self.assertEqual((b.width(),b.height()),(800,800));cuts.insert(polygon(s))
                self.assertTrue(cuts.space_check(800).is_empty())
                rails=[s for s in c['shapes'] if s.get('generator_role','').startswith('parallel:rail:')]
                self.assertEqual(len(rails),2 if count>1 else 0)
                self.assertTrue(all(s['width']==1600 for s in rails))

    def test_missing_dielectric_produces_a_real_short_and_restoration_clears_it(self):
        p,c,d=fixture();ls=layers(p['pdk'])
        mask=next(s for s in c['shapes'] if s['layer']==ls['cap2m']);old=clone(mask)
        mask['points']=[[x+50000,y] for x,y in mask['points']]
        self.assertIn('LVS.SHORT',{i['code'] for i in connectivity(p,c['id'])['issues']})
        mask.update(old);self.assertFalse(connectivity(p,c['id'])['issues'])

    def test_invalid_dimensions_bindings_and_missing_layers_fail_without_changes(self):
        p,c,d=fixture();before=clone(p)
        for change in ({'w':1.995},{'w':2.001},{'l':30.005},{'w':2,'l':3},{'mf':0},{'mf':1.5},{'mf':17}):
            q=clone(d);q['model_params'].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):geometry(p['pdk'],q)
        for pair in ((71,20),(72,20),(71,44),(97,44)):
            t=clone(p['pdk']);t['layers']=[v for v in t['layers'] if (v['gds'],v['datatype'])!=pair]
            with self.assertRaisesRegex(ValueError,'requires metal4'):geometry(t,d)
        t=clone(p['pdk']);t['simulation']['catalog'][d['model_ref']['device']]['pin_order']=['c1','c0']
        with self.assertRaisesRegex(ValueError,'binding'):geometry(t,d)
        self.assertEqual(p,before)

    def test_resize_and_save_preserve_terminals_roles_and_catalog_emission(self):
        from icstudio.layout_eco import regenerate
        from icstudio.testbenches import native_subcircuit
        p,c,d=fixture(2,2,3);pins={v['pin']:v['id'] for v in c['layout_pins']}
        roles={s['generator_role']:s['id'] for s in c['shapes']}
        d['model_params'].update(w=4,l=4);regenerate(p,c['id'],d['id'])
        self.assertEqual({v['pin']:v['id'] for v in c['layout_pins']},pins)
        self.assertTrue(all(s['id']==roles[s['generator_role']] for s in c['shapes'] if s['generator_role'] in roles))
        self.assertFalse(connectivity(p,c['id'])['issues'])
        line=next(v for v in native_subcircuit(p,c['id']).splitlines() if v.startswith('X_C1 '))
        self.assertEqual(line.split()[:4],['X_C1','P','N','sky130_fd_pr__cap_mim_m3_2'])
        self.assertEqual(set(line.split()[4:]),{'w=4','l=4','mf=3','m=3'})
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'mim2.icproj';save_project(p,path);q=load_project(path)
            self.assertEqual(p['cells'],q['cells']);self.assertFalse(connectivity(q,q['top'])['issues'])

if __name__=='__main__':unittest.main()
