"""Physical integer multiplicity preserves unit dimensions and terminal routes."""
from pathlib import Path
import tempfile
import unittest
import klayout.db as db

from icstudio.catalog import create_device
from icstudio.interchange import export_layout
from icstudio.layout import polygon
from icstudio.layout_eco import regenerate, inventory
from icstudio.model import clone, example, load_project, save_project
from icstudio.physical import connectivity
from icstudio.physical_cells import transform_selection
from icstudio.sky130_devices import install
from icstudio.sky130_metal_resistors import geometry, layers, LAYERS, specification
from tests.test_sky130_devices import technology


def fixture(model='m1', count=1, width=2, length=5):
    p=example('empty');p['pdk']=technology();c=p['cells'][0]
    symbol='li' if model=='l1' else model
    d=create_device(p['pdk'],'sky130_fd_pr/res_generic_'+symbol+'.sym','R1')
    d['model_params'].update(w=width,l=length,mult=count);d['nets']={'m':'A','p':'B'}
    c['devices']=[d];install(p,c['id'],d['id'])
    return p,c,d


class ParallelResistorTests(unittest.TestCase):
    def test_single_unit_keeps_original_spec_geometry_roles_and_pin_positions(self):
        for key in LAYERS:
            for w,l in ((.5,.5),(2,5),(10,10),(.505,2.005)):
                p,c,d=fixture(key,1,w,l);data=geometry(p['pdk'],d,1000,-1500)
                self.assertEqual(set(data['record']),{'device_id','spec','origin'})
                self.assertEqual(set(data['record']['spec']),{'api','recipe','model','layer','model_ref','kind','values','dimensions_nm','nets'})
                wn,ln=round(w*1000),round(l*1000)
                self.assertEqual([s['generator_role'] for s in data['shapes']],['metal_resistor:conductor','metal_resistor:marker'])
                self.assertEqual([s['points'] for s in data['shapes']],
                    [[[1000,-2000],[1000+wn,-1500+ln+500]],[[1000,-1500],[1000+wn,-1500+ln]]])
                self.assertEqual([v['point'] for v in data['pins']],[[1000+5*(wn//10),-1750],[1000+5*(wn//10),-1500+ln+250]])

    def test_all_integer_counts_and_models_keep_distinct_markers_two_landing_groups(self):
        for key in LAYERS:
            for count in range(2,17):
                with self.subTest(key=key,count=count):
                    p,c,d=fixture(key,count);ls=layers(p['pdk'],key)
                    masks={name:db.Region() for name in ls.values()}
                    for shape in c['shapes']:masks[shape['layer']].insert(polygon(shape))
                    marker=masks[ls['marker']].merged();ends=(masks[ls['conductor']]-marker).merged()
                    self.assertEqual(marker.count(),count);self.assertEqual(marker.area(),count*2000*5000)
                    self.assertEqual(ends.count(),2)
                    self.assertEqual(len(c['shapes']),2*count+2)
                    self.assertEqual(len({s['generator_role'] for s in c['shapes']}),len(c['shapes']))
                    self.assertFalse(connectivity(p,c['id'])['issues'])
                    buses=[s for s in c['shapes'] if ':parallel_bus:' in s['generator_role']]
                    self.assertTrue(all((db.Region(polygon(s)) & marker).is_empty() for s in buses))

    def test_dimensions_boundaries_and_rotations_keep_bus_clearance(self):
        for key in LAYERS:
            for w,l in ((.5,.5),(.5,10),(10,.5),(10,10)):
                for count in (2,3,16):
                    p,c,d=fixture(key,count,w,l);ls=layers(p['pdk'],key)
                    transform_selection(p,c['id'],[s['id'] for s in c['shapes']],rotation=90,include_annotations=True)
                    marker=db.Region();buses=db.Region()
                    for shape in c['shapes']:
                        if shape['layer']==ls['marker']:marker.insert(polygon(shape))
                        elif ':parallel_bus:' in shape['generator_role']:buses.insert(polygon(shape))
                    self.assertTrue((marker & buses).is_empty())
                    self.assertEqual(marker.merged().count(),count)
                    self.assertEqual(marker.area(),count*round(w*1000)*round(l*1000))
                    self.assertFalse(connectivity(p,c['id'])['issues'])

    def test_count_eco_keeps_retained_roles_pin_ids_routes_and_saved_orientation(self):
        for key in LAYERS:
            p,c,d=fixture(key);ls=layers(p['pdk'],key)
            pins={v['pin']:v['id'] for v in c['layout_pins']}
            first={s['generator_role']:s['id'] for s in c['shapes']}
            routes=[dict(id='route-a',kind='path',layer=ls['conductor'],points=[[1000,-250],[-2000,-250]],width=400,net='A',device_id=''),
                    dict(id='route-b',kind='path',layer=ls['conductor'],points=[[1000,5250],[-2000,5250]],width=400,net='B',device_id='')]
            c['shapes'].extend(clone(routes))
            for count in (3,16,2,1):
                d['model_params']['mult']=count;regenerate(p,c['id'],d['id'])
                self.assertEqual(pins,{v['pin']:v['id'] for v in c['layout_pins']})
                self.assertEqual(first,{s['generator_role']:s['id'] for s in c['shapes'] if s.get('generator_role') in first})
                self.assertEqual([s for s in c['shapes'] if s['id'] in ('route-a','route-b')],routes)
                generated=[s for s in c['shapes'] if s.get('device_id')==d['id']]
                self.assertEqual(len(generated),2 if count==1 else 2*count+2)
                self.assertEqual(sum(s['layer']==ls['marker'] for s in generated),count)
                self.assertEqual(inventory(p,c['id'])['devices'][0]['status'],'current')
                self.assertFalse(connectivity(p,c['id'])['issues'])
            c['shapes']=[s for s in c['shapes'] if s['id'] not in ('route-a','route-b')]
            transform_selection(p,c['id'],[s['id'] for s in c['shapes']],rotation=90,include_annotations=True)
            d['model_params']['mult']=3;regenerate(p,c['id'],d['id'])
            self.assertEqual(c['pdk_layouts'][0]['orientation'],{'rotation':90,'mirror':False})
            self.assertFalse(connectivity(p,c['id'])['issues'])

    def test_invalid_counts_fail_before_mutating_project(self):
        p,c,d=fixture();before=clone(p)
        for count in (0,-1,.5,1.5,16.5,17,float('nan'),float('inf')):
            changed=clone(d);changed['model_params']['mult']=count
            with self.subTest(count=count),self.assertRaises(ValueError):geometry(p['pdk'],changed)
        self.assertEqual(p,before)

    def test_removed_array_marker_or_external_bypass_exposes_a_short(self):
        from icstudio.layout_graph import GeometryGraph
        from scripts.qualify_sky130_metal_resistor_parallel import fault_project
        for key in LAYERS:
            p,c,d=fixture(key,3);graph=GeometryGraph();graph.sync(c['shapes'],p['pdk'])
            initial=len(set(graph.groups.values()));self.assertEqual(initial,2)
            marker=next(s for s in c['shapes'] if s['generator_role']=='parallel:2:metal_resistor:marker')
            c['shapes'].remove(marker);graph.sync(c['shapes'],p['pdk'])
            self.assertEqual(len(set(graph.groups.values())),1)
            self.assertTrue(connectivity(p,c['id'])['issues'])
            c['shapes'].append(marker);graph.sync(c['shapes'],p['pdk']);self.assertEqual(len(set(graph.groups.values())),initial)
            short=fault_project(p,dict(model=key,width_um=2,length_um=5,multiplicity=3),'bus-short')
            self.assertTrue(connectivity(short,short['top'])['issues'])

    def test_parallel_save_reopen_and_actual_stream_keep_all_unit_masks(self):
        for key in LAYERS:
            p,c,d=fixture(key,16)
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);save_project(p,root/'saved.icproj');loaded=load_project(root/'saved.icproj')
                self.assertEqual(loaded['cells'],p['cells'])
                export_layout(loaded,root/'layout.gds');stream=db.Layout();stream.read(str(root/'layout.gds'))
                region=db.Region(stream.top_cell().begin_shapes_rec(stream.layer(LAYERS[key],13))).merged()
                self.assertEqual(region.count(),16);self.assertEqual(region.area(),16*2000*5000)


class ParallelAcceptanceContractTests(unittest.TestCase):
    def test_predeclared_case_matrix_and_actual_app_reference(self):
        from scripts import qualify_sky130_metal_resistor_parallel as run
        spec=run.contract();rows=run.selection(spec)
        self.assertEqual(len(rows)*2,280)
        self.assertEqual(sum((r['width_um'],r['length_um'],r['multiplicity'])==(2,5,3) for r in rows)*5,25)
        self.assertEqual(sum((r['width_um'],r['length_um'])==(2,5) and r['multiplicity'] in (2,3,16) for r in rows)*2,30)
        for key in LAYERS:
            row=dict(model=key,width_um=2,length_um=5,multiplicity=16)
            p=run.editor_project(technology(),row)
            self.assertIn('m=16',run.application_reference(p,row))

    def test_native_array_rejects_merged_count_and_incorrect_graph(self):
        from scripts import qualify_sky130_metal_resistor_parallel as run
        row=dict(model='m1',width_um=2,length_um=5,multiplicity=3)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'extracted.spice'
            valid='.subckt coupon R1 R2\n'+''.join(f'R{i} R1 R2 sky130_fd_pr__res_generic_m1 w=2 l=5\n' for i in range(3))+'.ends\n'
            path.write_text(valid);self.assertEqual(len(run.check_native(path,row)['units']),3)
            for bad in [valid.replace('R2 sky130','floating sky130',1),valid.replace('R2 R1 R2','R1 R1 R2'),'.subckt coupon R1 R2\nR0 R1 R2 sky130_fd_pr__res_generic_m1 w=2 l=5 m=3\n.ends\n']:
                path.write_text(bad)
                with self.assertRaises(ValueError):run.check_native(path,row)

    def test_native_fault_geometry_preserves_untouched_markers(self):
        from scripts import qualify_sky130_metal_resistor_parallel as run
        from scripts.qualification_geometry import regions
        for key in LAYERS:
            row=dict(model=key,width_um=2,length_um=5,multiplicity=3)
            p=run.editor_project(technology(),row);original=regions(p);layer=LAYERS[key]
            short=regions(run.fault_project(p,row,'bus-short'))
            self.assertTrue((short[(layer,13)]^original[(layer,13)]).is_empty())
            self.assertEqual((short[(layer,20)]-short[(layer,13)]).merged().count(),1)
            missing=regions(run.fault_project(p,row,'missing-unit'));self.assertEqual(missing[(layer,13)].count(),2)
            opened=regions(run.fault_project(p,row,'broken-branch'));self.assertEqual((opened[(layer,20)]-opened[(layer,13)]).merged().count(),3)
            wide=regions(run.fault_project(p,row,'one-unit-width'));self.assertEqual(sorted(poly.bbox().width() for poly in wide[(layer,13)].each()),[2000,2000,3000])

    def test_electrical_deck_uses_actual_entire_native_array_once(self):
        from scripts import qualify_sky130_metal_resistor_parallel as run
        row=dict(name='m1-w2-l5-m16',model='m1',width_um=2,length_um=5,multiplicity=16)
        text=run.deck(run.contract(),row,90,'ac',{'tt':'.lib models tt'},Path('/tmp/array'))
        self.assertEqual(text.count('.include '),2)
        self.assertEqual(text.count('XN in_n out_n native_wrapper'),1)
        self.assertIn('r90/physical/lvs-extraction/extracted.spice',text)
        self.assertIn('.temp 27',text);self.assertIn('.ac dec 3 1k 10g',text)
        self.assertNotIn('.param mc_',text)

    def test_rotated_exchange_preserves_gds_presentation_and_oasis_port_geometry(self):
        from scripts import qualify_sky130_metal_resistor_parallel as run
        from scripts.qualification_geometry import same_masks
        import json
        row=dict(model='m1',width_um=2,length_um=5,multiplicity=3)
        p=run.editor_project(technology(),row);c=p['cells'][0]
        transform_selection(p,c['id'],[s['id'] for s in c['shapes']],rotation=90,pivot=(0,0),include_annotations=True)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=run.transfer(p,technology(),root);same_masks(p,out)
            result=json.loads((root/'exchange.json').read_bytes())
            self.assertEqual(set(result),{'gds','oasis','cross_format'})
            self.assertTrue((root/'gds-reimported.gds').is_file())

    def test_parallel_reduced_property_faults_require_exact_summed_widths(self):
        from scripts.qualify_sky130_metal_resistor_parallel import netgen_mismatch
        for fault,other in [('missing-unit',4),('reference-count',4),('one-unit-width',7)]:
            log=f'sky130_fd_pr__res_generic_m1\n w circuit1: 6   circuit2: {other}   (delta=40%, cutoff=1%)\nFinal result: Circuits match uniquely.\nProperty errors were found.\n'
            netgen_mismatch(log,'m1',fault)
            for bad in (log.replace('Property errors were found.',''),log.replace(f'circuit2: {other}','circuit2: 8'),log.replace('res_generic_m1','res_generic_m2')):
                with self.assertRaises(ValueError):netgen_mismatch(bad,'m1',fault)


if __name__=='__main__':unittest.main()
