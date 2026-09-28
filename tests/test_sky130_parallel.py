"""Parallel recipe electrical topology, parameter semantics and ECO identity.

These tests use polygon connectivity, not labels as inferred electrical ties.
Actual device extraction and process DRC remain separate engine gates.
"""
import unittest

from icstudio.catalog import create_device
from icstudio.layout import polygon, kdb
from icstudio.layout_eco import regenerate
from icstudio.layout_topology import partition, shape_key
from icstudio.model import clone, example, validate
from icstudio.physical import connectivity
from icstudio.sky130_layout import install_mos, specification, audit
from tests.test_sky130_devices import technology


def project(kind='NMOS', fingers=1, count=3, tied=False):
    p=example('empty');p['pdk']=technology();c=p['cells'][0]
    suffix={'NMOS':'nfet_01v8','PMOS':'pfet_01v8','cap':'cap_mim_m3_1','res':'res_generic_po'}[kind]
    d=create_device(p['pdk'],'sky130_fd_pr/'+suffix+'.sym','M1' if kind in ('NMOS','PMOS') else 'P1')
    if kind in ('NMOS','PMOS'):
        d['params'].update(w=str(fingers)+'u',l='.5u');d['model_params'].update(nf=fingers,mult=count)
        d['nets']={pin:pin.upper() for pin in ('d','g','s','b')}
        if tied:d['nets']['b']='S';d['physical_body_tie']='source'
    else:
        d['model_params'].update(w=2,l=2,**{'mf' if kind=='cap' else 'mult':count})
        d['nets']=dict(zip(d['nets'],('P','N')))
    c['devices']=[d];install_mos(p,c['id'],d['id']);validate(p)
    return p,c,d


class ParallelDeviceTests(unittest.TestCase):
    def test_mos_and_passive_copies_are_physically_connected(self):
        for kind in ('NMOS','PMOS','cap','res'):
            for count in (2,3,16):
                for fingers in ((1,4,8) if kind in ('NMOS','PMOS') else (1,)):
                    with self.subTest(kind=kind,count=count,fingers=fingers):
                        p,c,d=project(kind,fingers,count)
                        self.assertFalse(connectivity(p,c['id'])['issues'])
                        parts=partition(p,c['id'])
                        for net in set(d['nets'].values()):
                            groups={parts[shape_key(s)] for s in c['shapes'] if s.get('net')==net and shape_key(s) in parts}
                            self.assertEqual(len(groups),1,net)
                        self.assertEqual(len(c['layout_pins']),len(d['nets']))
                        self.assertEqual(c['pdk_layouts'][0]['parallel_units']['count'],count)
                        self.assertEqual(len({s['generator_role'] for s in c['shapes']}),len(c['shapes']))

    def test_model_multiplicity_maps_to_unit_count_once(self):
        from icstudio.testbenches import native_subcircuit
        for kind,marker in (('NMOS','poly'),('cap','capm'),('res','polyres')):
            p,c,d=project(kind,count=4)
            masks={(row['gds'],row['datatype']):row['name'] for row in p['pdk']['layers']}
            layer=masks[{'poly':(66,20),'capm':(89,44),'polyres':(66,13)}[marker]]
            shapes=[s for s in c['shapes'] if s['layer']==layer]
            # A single MOS uses one gate and one contact pad; passives each
            # have exactly one marker, with invariant unit W/L in every copy.
            self.assertEqual(len(shapes),8 if kind=='NMOS' else 4)
            spec=specification(p['pdk'],d);self.assertEqual(spec['multiplicity'],4)
            emitted=native_subcircuit(p,c['id']);self.assertIn('m=4',emitted)
            if kind=='cap':self.assertIn('mf=4',emitted)
            unit_widths={polygon(s).bbox().width() for s in shapes}
            self.assertEqual(unit_widths,{500,440} if kind=='NMOS' else {2000})

    def test_breaking_one_copy_access_is_an_open_despite_same_net_labels(self):
        p,c,d=project(count=3)
        c['shapes']=[s for s in c['shapes'] if s.get('generator_role')!='parallel:access:d:2:via']
        self.assertIn('LVS.FLOATING_LABEL',{row['code'] for row in connectivity(p,c['id'])['issues']})

    def test_body_source_tie_requires_matching_nets_and_survives_copies(self):
        for kind in ('NMOS','PMOS'):
            p,c,d=project(kind,4,3,True)
            self.assertFalse(connectivity(p,c['id'])['issues'])
            self.assertEqual(sum(s['generator_role'].endswith('body_source_tie') for s in c['shapes']),3)
            d['nets']['b']='OTHER'
            before=clone(p)
            with self.assertRaisesRegex(ValueError,'same explicit'):regenerate(p,c['id'],d['id'])
            self.assertEqual(p,before)

    def test_source_tie_form_contract_marks_existing_layout_stale(self):
        from icstudio.sky130_devices_ui import body_tie_field,set_body_tie
        p,c,d=project(count=2)
        self.assertEqual(body_tie_field(p['pdk'],d)[0][2],['None','Source'])
        with self.assertRaisesRegex(ValueError,'same schematic'):set_body_tie(p,c['id'],d['id'],{'body_tie':'Source'})
        self.assertNotIn('physical_body_tie',d)
        d['nets']['b']=d['nets']['s'];set_body_tie(p,c['id'],d['id'],{'body_tie':'Source'})
        self.assertTrue(audit(p,c['id']));regenerate(p,c['id'],d['id'])
        self.assertFalse(audit(p,c['id']));self.assertFalse(connectivity(p,c['id'])['issues'])
        set_body_tie(p,c['id'],d['id'],{'body_tie':'None'})
        self.assertTrue(audit(p,c['id']))
        other,cell,passive=project('cap')
        self.assertEqual(body_tie_field(other['pdk'],passive),[])
        with self.assertRaisesRegex(ValueError,'supported SKY130'):set_body_tie(other,cell['id'],passive['id'],{'body_tie':'Source'})

    def test_regeneration_preserves_roles_and_public_pins_across_count_changes(self):
        for kind in ('NMOS','cap','res'):
            p,c,d=project(kind,count=2)
            original={s['generator_role']:s['id'] for s in c['shapes']};pins=clone(c['layout_pins'])
            key='mf' if kind=='cap' else 'mult';d['model_params'][key]=4
            self.assertTrue(audit(p,c['id']));regenerate(p,c['id'],d['id'])
            self.assertFalse(audit(p,c['id']));self.assertEqual(c['layout_pins'],pins)
            self.assertTrue(all(s['id']==original[s['generator_role']] for s in c['shapes'] if s['generator_role'] in original))
            self.assertFalse(connectivity(p,c['id'])['issues'])
            d['model_params'][key]=1;regenerate(p,c['id'],d['id'])
            self.assertNotIn('parallel_units',c['pdk_layouts'][0]);self.assertEqual(c['layout_pins'],pins)
            self.assertFalse(any(s['generator_role'].startswith('parallel:') for s in c['shapes']))

    def test_parallel_inverter_separates_full_footprints(self):
        from icstudio.sky130_layout import reference_project, generate_inverter
        p,cid=reference_project(technology());c=next(c for c in p['cells'] if c['id']==cid)
        for d in c['devices']:d['model_params']['mult']=3
        generate_inverter(p,cid)
        self.assertFalse(connectivity(p,cid)['issues']);self.assertFalse(audit(p,cid))
        bounds=[]
        for d in c['devices']:
            region=kdb().Region()
            for s in c['shapes']:
                if s.get('generated_device')==d['id']:region.insert(polygon(s))
            bounds.append(region.bbox())
        self.assertFalse(bounds[0].overlaps(bounds[1]))


if __name__=='__main__':unittest.main()
