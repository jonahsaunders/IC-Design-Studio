"""Physical/electrical acceptance for saved square spiral inductors."""
import math
import tempfile
import unittest
from pathlib import Path

from icstudio import inductor
from icstudio.model import example,clone,device,uid,validate,History,save_project,load_project,scalar
from icstudio.layout import polygon,kdb,rect,drc
from icstudio.layout_graph import GeometryGraph
from icstudio.physical import connectivity
from icstudio.live_geometry import full,IncrementalChecks,check_enclosures
from icstudio.layout_topology import partition,move


class InductorTests(unittest.TestCase):
    def setUp(self):
        self.p=example('empty');self.cid=self.p['top'];self.spec=inductor.defaults(self.p)

    def create(self,**changes):
        proposal=inductor.plan(self.p,self.cid,{**self.spec,**changes});inductor.install(self.p,proposal)
        return self.p['cells'][0],proposal

    def codes(self,p=None,cid=None):return {v['code'] for v in connectivity(p or self.p,cid or self.cid)['issues']}

    def test_dimensions_estimate_scaling_and_lead_exclusion(self):
        a=inductor.geometry(self.p['pdk'],self.spec)
        self.assertEqual(a['outer_nm'],152000);self.assertAlmostEqual(a['estimate_h']*1e9,1.6378276784,places=9)
        b=inductor.geometry(self.p['pdk'],{**self.spec,**{k:2*self.spec[k] for k in ('width','spacing','inner','lead')}})
        self.assertAlmostEqual(b['estimate_h']/a['estimate_h'],2)
        c=inductor.geometry(self.p['pdk'],{**self.spec,'lead':60000})
        self.assertEqual(c['estimate_h'],a['estimate_h']);self.assertGreater(c['winding_length_nm'],a['winding_length_nm'])

    def test_turns_have_open_winding_and_complete_via_connected_metal(self):
        for turns in (1,2,3,8,32):
            with self.subTest(turns=turns):
                p=example('empty');proposal=inductor.plan(p,p['top'],{**self.spec,'turns':turns});inductor.install(p,proposal);c=p['cells'][0]
                raw=GeometryGraph().sync(c['shapes'],p['pdk'])
                self.assertEqual(len(set(raw.groups.values())),1)
                winding=polygon(next(s for s in c['shapes'] if s['pcell_role']=='body.coil'))
                self.assertEqual(winding.holes(),0,'Winding must not close into a shorted turn')
                self.assertEqual(len(set(partition(p,p['top']).values())),2)
                self.assertFalse(drc(p,p['top']));self.assertFalse(check_enclosures(p,p['top'],c['shapes']))

    def test_rotation_mirror_and_translation_preserve_area_grid_and_estimate(self):
        base=inductor.geometry(self.p['pdk'],self.spec)
        areas=[polygon(s).area() for s in base['shapes']]
        for angle in (0,90,180,270):
            for mirror in (False,True):
                proposal=inductor.plan(self.p,self.cid,{**self.spec,'rotation':angle,'mirror':mirror,'x':120005,'y':-340005})
                self.assertEqual([polygon(s).area() for s in proposal['shapes']],areas)
                self.assertEqual(proposal['estimate_h'],base['estimate_h'])
                self.assertTrue(all(v%5==0 for s in proposal['shapes'] for pt in s['points'] for v in pt))

    def test_invalid_specs_names_and_locks_are_atomic(self):
        before=clone(self.p)
        for change in ({'turns':0},{'turns':33},{'turns':1.5},{'width':10001},{'spacing':10},{'inner':-10},
                       {'lead':1000},{'x':1},{'width':float('nan')},{'via_rows':9},{'width':300,'via_rows':8},
                       {'via':'missing'},{'metal':'poly'},{'rotation':45},{'mirror':1}):
            with self.subTest(change=change),self.assertRaises(ValueError):inductor.plan(self.p,self.cid,{**self.spec,**change})
            self.assertEqual(self.p,before)
        for args in ({'name':'R1'},{'nets':{'p':'a','n':'a'}},{'locked':['via1']}):
            with self.assertRaises(ValueError):inductor.plan(self.p,self.cid,self.spec,**args)
        self.assertEqual(self.p,before)

    def test_missing_via_mapping_is_explicit_and_no_technology_is_invented(self):
        self.p['pdk']['revision']='unmapped';before=clone(self.p)
        with self.assertRaisesRegex(ValueError,'mapped via'):inductor.defaults(self.p)
        self.assertEqual(self.p,before)

    def test_mapped_process_masks_use_declared_stacks_without_qualification(self):
        from test_silicon import technology
        self.p['pdk']=technology();self.spec=inductor.defaults(self.p);c,proposal=self.create()
        self.assertTrue(all(s['layer'] in {l['name'] for l in self.p['pdk']['layers']} for s in c['shapes']))
        self.assertFalse(check_enclosures(self.p,self.cid,c['shapes']));self.assertFalse(self.codes())
        self.assertIn('Estimated DC',proposal['qualification'])

    def test_existing_value_preserved_until_estimate_requested(self):
        d=device('L','Lold',value='5n',nets={'p':'a','n':'b'});self.p['cells'][0]['devices'].append(d)
        r=inductor.plan(self.p,self.cid,self.spec,did=d['id']);inductor.install(self.p,r)
        self.assertEqual(self.p['cells'][0]['devices'][0]['value'],'5n')
        r=inductor.plan(self.p,self.cid,self.spec,did=d['id'],use_estimate=True);inductor.install(self.p,r)
        self.assertAlmostEqual(scalar(self.p['cells'][0]['devices'][0]['value'])/r['estimate_h'],1)

    def test_new_device_is_labelled_and_history_save_reload_preserve_recipe(self):
        from icstudio.wiring import migrate,rebuild
        migrate(self.p['cells'][0],self.p);history=History(self.p);r=inductor.plan(history.project,self.cid,self.spec,name='Lcoil',nets=dict(p='RF_IN',n='RF_OUT'))
        history.commit(lambda p:inductor.install(p,r),'Create inductor');created=clone(history.project)
        c=history.project['cells'][0];rebuild(c,history.project)
        self.assertEqual(c['devices'][0]['nets'],dict(p='RF_IN',n='RF_OUT'))
        history.undo();self.assertFalse(history.project['cells'][0]['shapes']);history.redo();self.assertEqual(history.project['cells'],created['cells'])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'spiral.icproj';save_project(history.project,path);loaded=load_project(path)
            self.assertEqual(loaded['cells'],history.project['cells']);self.assertFalse(self.codes(loaded))

    def test_generated_schematic_value_drives_rl_ac_response_and_spice_deck(self):
        from icstudio.simulation import run
        from icstudio.interchange import spice
        c,r=self.create();nets=c['devices'][0]['nets']
        for kind,name,x,p,n,value in (('V','V1',100,nets['p'],'0','1'),('R','Rload',600,nets['n'],'0','50')):
            c['devices'].append(device(kind,name,x=x,nets=dict(p=p,n=n),net_labels=dict(p=p,n=n),value=value))
        validate(self.p)
        self.assertIn('L1 L1_p L1_n '+c['devices'][0]['value'],spice(self.p))
        result=run(self.p,self.cid,{**self.p['analysis'],'type':'ac','start':'100meg','end':'1e9','points':3})
        for frequency,magnitude in zip(result['x'],result['traces']['L1_n']):
            expected=50/math.hypot(50,2*math.pi*frequency*r['estimate_h'])
            self.assertAlmostEqual(magnitude,expected,places=6)

    def test_stale_preview_and_changed_layer_locks_reject_install(self):
        r=inductor.plan(self.p,self.cid,self.spec);before=clone(self.p)
        with self.assertRaisesRegex(ValueError,'Unlock'):inductor.install(self.p,r,locked=['via1'])
        self.assertEqual(self.p,before);self.p['name']='Changed';before=clone(self.p)
        with self.assertRaisesRegex(ValueError,'design changed'):inductor.install(self.p,r)
        self.assertEqual(self.p,before)

    def test_collision_rejected_without_changing_existing_design(self):
        self.create();before=clone(self.p)
        with self.assertRaises(ValueError):inductor.plan(self.p,self.cid,self.spec,name='L2')
        self.assertEqual(self.p,before)

    def test_real_external_short_remains_visible(self):
        c,r=self.create();p,n=[v['point'] for v in r['pins']]
        c['shapes'].append(dict(id=uid(),kind='path',layer=self.spec['metal'],width=1000,points=[p,[n[0],p[1]],n],net=''))
        self.assertIn('LVS.SHORT',self.codes())

    def test_internal_taps_on_metal_and_via_are_reported(self):
        c,_=self.create();coil=next(s for s in c['shapes'] if s['pcell_role']=='body.coil');x,y=coil['points'][2]
        for layer in ('metal2','via1'):
            q=clone(self.p);q['cells'][0]['shapes'].append(rect(layer,x-100,y-100,200,200))
            self.assertIn('INDUCTOR.TAP',self.codes(q))
        # Edge-only contact must not disappear in an area-only intersection.
        q=clone(self.p);q['cells'][0]['shapes'].append(rect('metal2',x+5000,y,200,200))
        self.assertIn('INDUCTOR.TAP',self.codes(q))

    def test_removed_cut_manual_winding_and_tampered_signature_fail_closed(self):
        from icstudio.parametric import geometry_signature
        self.create()
        for edit in ('delete_cut','move_body','forge_hash','move_pin'):
            q=clone(self.p);c=q['cells'][0]
            if edit=='delete_cut':c['shapes'].remove(next(s for s in c['shapes'] if s['layer']=='via1'))
            elif edit=='move_pin':c['layout_pins'][0]['point'][0]+=5
            else:
                c['shapes'][0]['points'][2][0]+=5
                if edit=='forge_hash':c['parametric_devices'][0]['geometry_signature']=geometry_signature(c['shapes'])
            self.assertIn('INDUCTOR.STALE',self.codes(q))
            self.assertEqual(inductor.contact_shapes(q,self.cid),c['shapes'])

    def test_incremental_and_full_findings_agree_after_tap_and_deletion(self):
        c,_=self.create();checks=IncrementalChecks()
        def compare():
            normalize=lambda report:sorted((v['code'],v['message']) for v in report['issues'])
            self.assertEqual(normalize(checks.check(self.p,self.cid)),normalize(full(self.p,self.cid)))
        compare();coil=c['shapes'][0];x,y=coil['points'][2];c['shapes'].append(rect('metal2',x,y,300,300));compare()
        c['shapes'].pop();c['shapes'][0]['points'][2][0]+=5;compare()

    def test_translation_regeneration_and_value_eco_retain_stable_ids(self):
        from icstudio.layout_eco_hierarchy import inventory,propose
        from icstudio.parametric import install
        c,r=self.create();did=r['device_id'];ids=[s['id'] for s in c['shapes']]
        move(self.p,self.cid,ids,10000,20000);c=self.p['cells'][0]
        spec=inductor.current_spec(c,c['parametric_devices'][0]);self.assertEqual((spec['x'],spec['y']),(10000,20000))
        install(self.p,self.cid,did,self.spec);c=self.p['cells'][0]
        self.assertEqual([s['id'] for s in c['shapes']],ids);self.assertFalse(self.codes())
        c['devices'][0]['value']='2n';self.assertEqual(inventory(self.p,self.cid)['devices'][0]['status'],'changed')
        q,review=propose(self.p,self.cid,[(self.cid,did)])
        self.assertEqual(review['after']['devices'][0]['status'],'current');self.assertEqual(q['cells'][0]['parametric_devices'][0]['spec']['x'],10000)

    def test_attached_route_and_lower_via_contact_survive_or_block_regeneration(self):
        c,r=self.create();did=r['device_id'];point=r['pins'][1]['point']
        for layer in ('metal2','metal1'):
            q=clone(self.p);c=q['cells'][0]
            c['shapes'].append(dict(id=uid(),kind='path',layer=layer,width=300,points=[point,[point[0]-20000,point[1]]],net='L1_n'))
            self.assertFalse(self.codes(q));inductor.plan(q,self.cid,self.spec,did=did)
            with self.assertRaisesRegex(ValueError,'disconnect'):inductor.plan(q,self.cid,{**self.spec,'x':50000},did=did)

    def test_connected_edit_fallback_protects_winding_and_routes(self):
        from icstudio.layout_transaction import propose
        c,r=self.create();ids=[s['id'] for s in c['shapes']]
        self.assertIsNone(propose(self.p,self.cid,ids,10000,0))
        with self.assertRaisesRegex(ValueError,'complete'):move(self.p,self.cid,[ids[0]],10000,0)
        # Moving an unrelated conductor onto the winding is rejected atomically.
        route=rect('metal2',200000,0,300,300);c['shapes'].append(route);before=clone(self.p)
        with self.assertRaises(ValueError):move(self.p,self.cid,[route['id']],-129000,0)
        self.assertEqual(self.p,before)

    def test_hierarchy_keeps_two_terminals_and_reports_child_taps(self):
        from icstudio.physical_cells import place
        from icstudio.design_ops import flatten_layout
        c,r=self.create();c['ports']=['L1_p','L1_n'];c['layout_ports']=[dict(name='L1_'+v['pin'],layer=v['layer'],point=v['point']) for v in r['pins']]
        top=dict(id=uid(),name='parent',ports=[],devices=[device('X','X1',cell=c['id'],nets={'L1_p':'a','L1_n':'b'})],shapes=[])
        self.p['cells'].append(top);self.p['top']=top['id'];place(self.p,top['id'],top['devices'][0]['id'],300000,400000,90,True);validate(self.p)
        self.assertFalse(self.codes(self.p,top['id']));self.assertEqual(len(set(partition(self.p,top['id']).values())),2)
        self.assertEqual(len(flatten_layout(self.p,top['id'])),len(c['shapes']))
        x,y=c['shapes'][0]['points'][2];c['shapes'].append(rect('metal2',x,y,300,300))
        self.assertIn('INDUCTOR.TAP',self.codes(self.p,top['id']))

    def test_export_retains_winding_and_recipe_while_rc_estimators_refuse(self):
        from icstudio.interchange import export_layout,import_layout
        from icstudio.physical import capacitance_estimate
        from icstudio.distributed_rc import extract
        c,_=self.create()
        for fn in (capacitance_estimate,extract):
            with self.assertRaisesRegex(ValueError,'EM/device'):fn(self.p,self.cid)
        with tempfile.TemporaryDirectory() as directory:
            for ext in ('gds','oas'):
                path=Path(directory)/('spiral.'+ext);export_layout(self.p,path);loaded,_=import_layout(path)
                self.assertEqual(loaded['cells'],self.p['cells'])
                raw=kdb().Layout();raw.read(str(path));self.assertGreater(raw.top_cell().bbox().width(),152000)

    def test_unlinked_physical_master_still_blocks_rc_and_reports_stale_winding(self):
        from icstudio.distributed_rc import extract
        c,_=self.create();top=dict(id=uid(),name='physical_parent',ports=[],devices=[],shapes=[],
            layout_instances=[dict(id=uid(),name='coil',cell=c['id'],x=0,y=0)])
        self.p['cells'].append(top)
        with self.assertRaisesRegex(ValueError,'EM/device'):extract(self.p,top['id'])
        c['shapes'][0]['points'][2][0]+=5
        self.assertIn('INDUCTOR.STALE',self.codes(self.p,top['id']))


if __name__=='__main__':unittest.main()
