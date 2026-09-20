"""Geometry, unit, electrical topology and catalog regression contracts.

Actual pinned-engine qualification is scripts/qualify_sky130_devices.py.
"""
import json
import tempfile
import unittest
from pathlib import Path
from icstudio.model import clone, example, file_digest
from icstudio.catalog import create_device
from icstudio.sky130_devices import geometry, install, install_dummy, install_guard, guard_geometry, layers, specification
from icstudio.physical import connectivity
from icstudio.layout import polygon, kdb

ROOT=Path(__file__).resolve().parents[1]


def technology():
    root=ROOT/'icstudio/assets/pdks/sky130A';m=json.loads((root/'package.json').read_text())
    tech=m['technology'];tech.update(package_root=str(root),package_lock={k:m[k] for k in ('id','revision','files')})
    return tech


def passive(kind='cap',w=2,l=2):
    p=example('empty');p['pdk']=technology();c=p['cells'][0]
    key='sky130_fd_pr/'+('cap_mim_m3_1' if kind=='cap' else 'res_generic_po')+'.sym'
    d=create_device(p['pdk'],key,'C1' if kind=='cap' else 'R1');d['model_params'].update(w=w,l=l)
    d['nets']=dict(zip(d['nets'],('P','N')));c['devices']=[d]
    install(p,c['id'],d['id'])
    return p,c,d


class SKY130DevicesTests(unittest.TestCase):
    def test_cap_uses_catalog_micrometres_and_distinct_actual_electrodes(self):
        p,c,d=passive();self.assertFalse(connectivity(p,c['id'])['issues'])
        self.assertEqual(specification(p['pdk'],d)['dimensions_nm'],{'w':2000,'l':2000})
        pins={v['pin']:v['point'] for v in c['layout_pins']}
        self.assertEqual(pins,{'c0':[1000,1000],'c1':[3500,1000]})
        from icstudio.layout_routing import conductors
        self.assertNotIn(layers(p['pdk'])['capm'],conductors(p['pdk']))
        from icstudio.testbenches import native_subcircuit
        line=next(v for v in native_subcircuit(p,c['id']).splitlines() if v.startswith('X_C1 '))
        self.assertEqual(line.split()[:4],['X_C1','P','N','sky130_fd_pr__cap_mim_m3_1'])
        self.assertEqual(set(line.split()[4:]),{'w=2','l=2','mf=1','m=1'})

    def test_insulating_mask_is_required_and_incremental_graph_observes_edits(self):
        p,c,d=passive();self.assertFalse(connectivity(p,c['id'])['issues'])
        mask=next(s for s in c['shapes'] if s['layer']==layers(p['pdk'])['capm'])
        before=clone(mask);mask['points']=[[x+20000,y] for x,y in mask['points']]
        self.assertIn('LVS.SHORT',{i['code'] for i in connectivity(p,c['id'])['issues']})
        mask.update(before);self.assertFalse(connectivity(p,c['id'])['issues'])

    def test_unsupported_passive_units_multiplicity_and_dimensions_fail_before_mutation(self):
        p,c,d=passive();before=clone(p)
        for params in ({'w':'2u'},{'w':1.995},{'l':30.005},{'w':2.001},{'mf':2},{'w':2,'l':20}):
            q=clone(d);q['model_params'].update(params)
            with self.subTest(params=params),self.assertRaises(ValueError):geometry(p['pdk'],q)
        self.assertEqual(p,before)

    def test_resistor_source_prefix_and_marker_dimensions(self):
        p,c,d=passive('res',1,20);self.assertFalse(connectivity(p,c['id'])['issues'])
        from icstudio.testbenches import native_subcircuit
        line=next(v for v in native_subcircuit(p,c['id']).splitlines() if v.startswith('R_R1 '))
        self.assertEqual(line.split()[:4],['R_R1','P','N','sky130_fd_pr__res_generic_po'])
        self.assertEqual(set(line.split()[4:]),{'w=1','l=20','m=1'})
        marker=next(s for s in c['shapes'] if s['layer']==layers(p['pdk'])['polyres'])
        box=polygon(marker).bbox();self.assertEqual((box.width(),box.height()),(20000,1000))
        binding=p['pdk']['simulation']['catalog'][d['model_ref']['device']];binding['prefix']='X'
        with self.assertRaisesRegex(ValueError,'reindex legacy'):specification(p['pdk'],d)

    def test_ecos_preserve_passive_terminal_and_role_ids(self):
        from icstudio.layout_eco import regenerate
        p,c,d=passive();pins={v['pin']:v['id'] for v in c['layout_pins']};roles={s['generator_role']:s['id'] for s in c['shapes']}
        d['model_params']['w']=3;regenerate(p,c['id'],d['id'])
        self.assertEqual({v['pin']:v['id'] for v in c['layout_pins']},pins)
        self.assertTrue(all(s['id']==roles[s['generator_role']] for s in c['shapes'] if s['generator_role'] in roles))
        self.assertFalse(connectivity(p,c['id'])['issues'])

    def test_dummy_is_electrically_explicit_and_regenerates_all_straps(self):
        from icstudio.layout_eco import regenerate
        p=example('empty');p['pdk']=technology();cid=p['top']
        d=install_dummy(p,cid,'MD1','NMOS','VSS',w='2u',l='1u');c=p['cells'][0]
        self.assertEqual(set(d['nets'].values()),{'VSS'});self.assertTrue(d['physical_dummy'])
        self.assertFalse(connectivity(p,cid)['issues'])
        c['devices'][0]['params']['w']='3u';regenerate(p,cid,d['id'])
        self.assertEqual(sum(s.get('generator_role','').startswith('dummy_tie') for s in c['shapes']),4)
        self.assertFalse(connectivity(p,cid)['issues'])
        c['devices'][0]['nets']['g']='OTHER'
        with self.assertRaisesRegex(ValueError,'tied'):regenerate(p,cid,d['id'])

    def test_wide_mos_is_bounded_at_30um_and_keeps_four_contacts(self):
        from icstudio.sky130_layout import specification as mos_specification
        p=example('empty');p['pdk']=technology()
        d=install_dummy(p,p['top'],'MWIDE','PMOS','VDD',w='30u',l='.5u')
        self.assertEqual(mos_specification(p['pdk'],d)['dimensions_nm'],{'w':30000,'l':500})
        self.assertFalse(connectivity(p,p['top'])['issues'])
        for key,value in [('w','30.005u'),('l','10.005u')]:
            bad=clone(d);bad['params'][key]=value
            with self.assertRaises(ValueError):mos_specification(p['pdk'],bad)

    def test_guard_contacts_have_corner_clearance_for_nonpitch_dimensions(self):
        tech=technology()
        for w,h,t in ((16000,16000,800),(148000,45000,800),(16105,17555,805)):
            data=guard_geometry(tech,dict(x=0,y=0,width=w,height=h,thickness=t))
            cuts=kdb().Region()
            for s in data['shapes']:
                if s['layer']==layers(tech)['mcon']:cuts.insert(polygon(s))
            # Official mcon spacing is 190nm; corner cuts must not almost meet.
            self.assertTrue(cuts.space_check(190).is_empty())

    def test_guard_body_tie_and_atomic_rejection(self):
        p=example('empty');p['pdk']=technology();cid=p['top']
        d=install_dummy(p,cid,'MD1','NMOS','VSS',w='2u',l='1u',x=5000,y=5000);c=p['cells'][0]
        spec=dict(x=0,y=0,width=16000,height=16000);before=clone(p)
        with self.assertRaisesRegex(ValueError,'existing conductor'):install_guard(p,cid,spec,'VSS',tie=dict(layer=layers(p['pdk'])['m1'],point=[-5000,-5000]))
        self.assertEqual(p,before)
        pin=next(v for v in c['layout_pins'] if v['pin']=='b')
        record=install_guard(p,cid,spec,'VSS',tie=dict(layer=pin['layer'],point=pin['point']),members=[d['id']])
        self.assertTrue(record['route_ids']);self.assertFalse(connectivity(p,cid)['issues'])
        from icstudio.analog_constraints import findings
        self.assertFalse(findings(p,cid))

    def test_import_respects_original_explicit_R_name_and_model_type(self):
        from icstudio.pdk_import import scan_local
        source=ROOT/'icstudio/assets/pdks/sky130A/libs.tech/xschem/sky130_fd_pr/res_generic_po.sym'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'sky130A';ng=root/'libs.tech/ngspice';symbols=root/'libs.tech/xschem/sky130_fd_pr';klayout=root/'libs.tech/klayout'
            for folder in (ng,symbols,klayout):folder.mkdir(parents=True)
            (ng/'sky130.lib.spice').write_text('.lib tt\n.model sky130_fd_pr__res_generic_po r rsh=48.2\n.subckt sky130_fd_pr__res_generic_po P N w=1 l=1\nR1 P N 10k\n.ends\n.endl tt\n')
            (symbols/source.name).write_bytes(source.read_bytes())
            (klayout/'layers.lyp').write_text('<layer-properties><properties><name>poly</name><source>66/20@1</source></properties></layer-properties>')
            m=scan_local(root);binding=m['technology']['simulation']['catalog']['sky130_fd_pr/res_generic_po.sym']
            self.assertFalse(binding['unavailable']);self.assertEqual(binding['prefix'],'R')
            self.assertEqual(binding['model_source'],'libs.tech/ngspice/sky130.lib.spice')
            self.assertEqual(m['files']['libs.tech/xschem/sky130_fd_pr/res_generic_po.sym'],file_digest(source))


if __name__=='__main__':unittest.main()
