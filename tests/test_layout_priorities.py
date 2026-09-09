import json, math, unittest
from pathlib import Path
from icstudio.model import example,clone,History,uid,validate
from icstudio.layout import rect,polygon,kdb
from icstudio.layout_arrange import arrange,plan,group_bounds,selection_groups
from test_layout_development import path
from test_silicon import technology


def coupons():
    samples={'resistance':[{'length_um':l,'width_um':w,'resistance_ohm':.12*l/w} for l,w in ((10,1),(30,2),(25,3))],
             'capacitance':[{'length_um':l,'width_um':w,'capacitance_f':l*w*2e-17+2*(l+w)*1e-17} for l,w in ((10,1),(20,3),(40,2))],
             'coupling':[{'overlap_um':l,'gap_um':g,'capacitance_f':3e-17*l/g} for l,g in ((10,1),(20,2),(30,3))]}
    return {'source':'Synthetic analytic coupon fixture, not measured process data','corner':'nominal','max_relative_error':.01,'layers':{'metal1':samples}}


class AlignmentTests(unittest.TestCase):
    def test_six_modes_fixed_reference_and_exact_history(self):
        for edge in ('left','right','bottom','top','center_x','center_y'):
            p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',200,300,600,800),rect('metal2',2500,4500,1000,1200)]
            ids=[s['id'] for s in c['shapes']];h=History(p);h.commit(lambda q:arrange(q,c['id'],ids,edge));after=clone(h.project['cells'])
            self.assertEqual(after[0]['shapes'][0],c['shapes'][0]);self.assertFalse(plan(h.project,c['id'],ids,edge))
            h.undo();self.assertEqual(h.project['cells'],p['cells']);h.redo();self.assertEqual(h.project['cells'],after)

    def test_fast_arrange_shares_unchanged_and_rolls_back_bad_plan(self):
        p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',0,0,600,600),rect('metal2',2000,2000,600,600)];ids=[s['id'] for s in c['shapes']];h=History(p);old=h.project
        self.assertTrue(h.commit_layout_arrange(c['id'],ids,'bottom',connected=True));self.assertIs(h.project['cells'][0]['shapes'][0],old['cells'][0]['shapes'][0]);self.assertEqual(h.layout_stats['indices'],[1]);after=clone(h.project['cells'])
        h.undo();self.assertEqual(h.project['cells'],p['cells']);h.redo();self.assertEqual(h.project['cells'],after);prior=h.project
        with self.assertRaises(ValueError):h.commit_layout_arrange(c['id'],ids,'left',offset=3)
        self.assertIs(h.project,prior)

    def test_rotated_skew_array_full_extent(self):
        from icstudio.design_ops import flatten_layout
        p=example('empty');c=p['cells'][0];child={'id':uid(),'name':'child','ports':[],'devices':[],'shapes':[rect('metal1',0,0,600,800)]};p['cells'].append(child)
        c['shapes']=[rect('metal1',12000,15000,600,800)];i={'id':uid(),'name':'array','cell':child['id'],'x':0,'y':0,'rotation':90,'mirror':True,'nx':3,'ny':2,'a':[-1500,500],'b':[500,2000]};c['layout_instances']=[i]
        ids=[c['shapes'][0]['id'],i['id']];arrange(p,c['id'],ids,'right')
        box=kdb().Box()
        for s in flatten_layout(p,c['id']):
            if s['id']==i['id']:box+=polygon(s).bbox()
        self.assertEqual(box.right,12600);self.assertEqual(i['a'],[-1500,500]);self.assertEqual(i['nx'],3)

    def test_distribute_gaps_and_centers(self):
        for edge in ('distribute_x','gap_x','distribute_y','gap_y'):
            p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',v,v,600,600) for v in (0,1500,6000)]
            ids=[s['id'] for s in c['shapes']];arrange(p,c['id'],ids,edge)
            pt=c['shapes'][1]['points'][0];self.assertEqual(pt[0] if edge.endswith('x') else pt[1],3000)
            self.assertEqual(c['shapes'][0]['points'][0],[0,0]);self.assertEqual(c['shapes'][2]['points'][0],[6000,6000])

    def test_grid_lock_and_partial_group_are_atomic(self):
        p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',0,0,600,600),rect('metal1',2000,0,605,600)];ids=[s['id'] for s in c['shapes']];before=clone(p)
        with self.assertRaisesRegex(ValueError,'grid'):arrange(p,c['id'],ids,'center_x')
        self.assertEqual(p,before)
        with self.assertRaisesRegex(ValueError,'Unlock'):arrange(p,c['id'],ids,'left',['metal1'])
        c['shapes'][0]['pcell_id']='group';c['shapes'][1]['pcell_id']='group'
        with self.assertRaisesRegex(ValueError,'complete'):selection_groups(p,c['id'],ids[:1])

    def test_offset_to_opposite_edge(self):
        p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',0,0,600,600),rect('metal1',2000,1000,600,600)]
        arrange(p,c['id'],[s['id'] for s in c['shapes']],'left',offset=400,reference_edge='right');self.assertEqual(c['shapes'][1]['points'][0],[1000,1000])

    def test_connected_alignment_keeps_route_and_rejects_short(self):
        p=example('empty');c=p['cells'][0];a=rect('metal1',0,0,600,600,net='a');b=rect('metal1',5000,1000,600,600,net='a');wire=path([[300,300],[5300,300],[5300,1300]])
        c['shapes']=[a,b,wire];arrange(p,c['id'],[a['id'],b['id']],'bottom',connected=True)
        self.assertEqual(c['shapes'][2]['points'][-1],[5300,300])
        old=clone(p)
        with self.assertRaises(ValueError):arrange(p,c['id'],[a['id'],b['id']],'left',connected=True)
        self.assertEqual(p,old)


class DeviceUpdateTests(unittest.TestCase):
    def single(self,nf=1):
        from icstudio.sky130_layout import reference_project,install_mos
        p,cid=reference_project(technology());c=next(c for c in p['cells'] if c['id']==cid);d=c['devices'][0];d['model_params']['nf']=nf;d['params']['w']='4u';install_mos(p,cid,d['id']);return p,cid,c,d

    def test_regeneration_preserves_roles_pins_origin_and_orientation(self):
        from icstudio.physical_cells import transform_selection
        from icstudio.layout_eco import regenerate
        p,cid,c,d=self.single(2);ids={s['id'] for s in c['shapes']};pins={v['pin']:v['id'] for v in c['layout_pins']}
        transform_selection(p,cid,ids,dx=2000,dy=3000,rotation=90,mirror=True);origin=clone(c['pdk_layouts'][0]['origin']);d['params']['w']='6u'
        regenerate(p,cid,d['id']);self.assertEqual({s['id'] for s in c['shapes']},ids);self.assertEqual({v['pin']:v['id'] for v in c['layout_pins']},pins)
        self.assertEqual(c['pdk_layouts'][0]['origin'],origin);self.assertEqual(c['pdk_layouts'][0]['orientation'],{'rotation':90,'mirror':True});validate(p)

    def test_eco_review_route_retarget_and_stale_rejection(self):
        from icstudio.layout_eco import inventory,propose,apply
        p,cid,c,d=self.single();pin=next(v for v in c['layout_pins'] if v['pin']=='d');end=[pin['point'][0]+4000,pin['point'][1]];wire=path([pin['point'][:],end],net=d['nets']['d'],layer='m1');c['shapes'].append(wire)
        d['params']['w']='6u';self.assertIn('changed',[r['status'] for r in inventory(p,cid)['devices']]);old=clone(p)
        q,report=propose(p,cid,[d['id']]);self.assertEqual(p,old);self.assertEqual(report['adjusted_routes'],[wire['id']])
        qc=next(c for c in q['cells'] if c['id']==cid);self.assertEqual(next(s for s in qc['shapes'] if s['id']==wire['id'])['points'][-1],end)
        p['name']='changed'
        with self.assertRaisesRegex(ValueError,'stale'):apply(p,q,report)

    def test_generated_fast_move_keeps_metadata_and_undo(self):
        p,cid,c,d=self.single(2);h=History(p);ids=[s['id'] for s in c['shapes']];self.assertTrue(h.commit_layout_move(cid,ids,5000,0))
        nc=next(c for c in h.project['cells'] if c['id']==cid);self.assertEqual(nc['pdk_layouts'][0]['origin'],[5000,0]);self.assertEqual(nc['layout_pins'][0]['point'][0],c['layout_pins'][0]['point'][0]+5000)
        h.undo();self.assertEqual(h.project['cells'],p['cells'])

    def test_legacy_hidden_body_catalog_instantiation_preserves_binding(self):
        from icstudio.catalog import create_device
        from icstudio.symbol_io import validate_symbol
        t=technology();b=t['simulation']['catalog']['NMOS'];b['symbol']={'pins':{'d':[0,0],'g':[20,0],'s':[40,0],'b':[60,0]},'pin_order':['d','g','s'],'primitives':[]};b['notes']=['Hidden body net exposed as terminal b; connect it explicitly.'];before=clone(b)
        d=create_device(t,'NMOS','M1');validate_symbol(d['symbol'],d['nets']);self.assertEqual(b,before);self.assertEqual(d['symbol']['pin_order'],['d','g','s','b'])

    def test_mirror_finger_range_connectivity(self):
        from icstudio.analog import reference
        from icstudio.analog_layout import generate_mirror,matching_findings
        from icstudio.physical import connectivity
        for nf in (1,2,4,8):
            p,cid,_=reference(technology());c=next(c for c in p['cells'] if c['id']==cid)
            for d in c['devices']:d['model_params']['nf']=nf
            generate_mirror(p,cid);self.assertFalse(connectivity(p,cid)['issues']);self.assertFalse(matching_findings(p,cid));validate(p)


class RoutingIntentTests(unittest.TestCase):
    def test_cursor_dogleg_obstacle_and_lock(self):
        from icstudio.route_interaction import CursorRoute
        p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',2000,-500,600,2000,net='other')]
        r=CursorRoute(p,c['id'],'a',400,['metal1']);preview=r.preview({'layer':'metal1','point':[0,0]},{'layer':'metal1','point':[5000,3000]})
        self.assertTrue(preview['clear']);self.assertEqual(preview['shapes'][0]['points'][1],[0,3000])
        with self.assertRaisesRegex(ValueError,'unlocked'):CursorRoute(p,c['id'],'a',400,['metal1'],['metal1'])

    def test_cursor_legal_via(self):
        from icstudio.route_interaction import CursorRoute
        p=example('empty');c=p['cells'][0];r=CursorRoute(p,c['id'],'a',400,['metal1','metal2'])
        preview=r.preview({'layer':'metal1','point':[0,0]},{'layer':'metal2','point':[5000,0]})
        self.assertTrue(preview['clear']);self.assertEqual(len(preview['shapes']),4)

    def test_matched_route_finding_and_enforcement(self):
        from icstudio.layout_routing import matched_pair,install
        from icstudio.route_constraints import findings,enforce
        p=example('empty');c=p['cells'][0];starts=[{'layer':'metal1','point':[0,y]} for y in (0,3000)];ends=[{'layer':'metal1','point':[5000,y]} for y in (0,3000)]
        install(p,matched_pair(p,c['id'],starts,ends,['a','b'],400,layers=['metal1']));self.assertFalse(findings(p,c['id']))
        q=clone(p);q['cells'][0]['shapes'][0]['points'][-1][0]+=1000
        self.assertTrue(findings(q,c['id']))
        with self.assertRaisesRegex(ValueError,'constraint'):enforce(p,q,c['id'])


class CalibrationTests(unittest.TestCase):
    def test_fit_reproduces_known_coefficients_and_corner_binding(self):
        from icstudio.rc_calibration import calibrate,install,coefficients
        t=example('empty')['pdk'];r=calibrate(t,coupons());c=r['coefficients']['metal1']
        self.assertAlmostEqual(c['sheet_ohm'],.12);self.assertAlmostEqual(c['cap_f_per_um2']/2e-17,1);self.assertAlmostEqual(c['edge_f_per_um']/1e-17,1)
        install(t,r);self.assertEqual(coefficients(t,'nominal')[0],r['coefficients'])
        with self.assertRaisesRegex(ValueError,'corner'):coefficients(t,'ss')
        t['grid']=10
        with self.assertRaisesRegex(ValueError,'stale'):coefficients(t,'nominal')

    def test_singular_bad_residual_and_tamper_rejected(self):
        from icstudio.rc_calibration import calibrate,install,coefficients
        t=example('empty')['pdk'];a=coupons();a['layers']['metal1']['capacitance']*=1;a['layers']['metal1']['capacitance']=[a['layers']['metal1']['capacitance'][0]]*3
        with self.assertRaisesRegex(ValueError,'vary'):calibrate(t,a)
        a=coupons();a['layers']['metal1']['resistance'][0]['resistance_ohm']*=2
        with self.assertRaisesRegex(ValueError,'residual'):calibrate(t,a)
        install(t,calibrate(t,coupons()));t['parasitic_corners']['nominal']['coefficients']['metal1']['sheet_ohm']=99
        with self.assertRaisesRegex(ValueError,'changed'):coefficients(t,'nominal')




class CalibratedComparisonTests(unittest.TestCase):
    def test_two_rc_corners_use_same_specifications_and_change_network(self):
        import tempfile
        from test_professional016 import rc_design
        from icstudio.rc_calibration import calibrate,install
        from icstudio.distributed_rc import compare_job
        p=rc_design();a=coupons();install(p['pdk'],calibrate(p['pdk'],a));b=clone(a);b['corner']='slow_rc'
        for row in b['layers']['metal1']['resistance']:row['resistance_ohm']*=3
        for kind in ('capacitance','coupling'):
            for row in b['layers']['metal1'][kind]:row['capacitance_f']*=2
        install(p['pdk'],calibrate(p['pdk'],b));results=[]
        with tempfile.TemporaryDirectory() as td:
            for corner in ('nominal','slow_rc'):
                settings={**p['analysis'],'corner':corner};job={'project':p,'cell':p['top'],'settings':{'type':'rc_compare','analysis':settings},'engine':'builtin'}
                result=compare_job(p,job,Path(td)/corner);results.append(result)
                self.assertEqual(result['extraction']['corner'],corner);self.assertEqual(result['extraction']['calibration']['corner'],corner)
                self.assertEqual([r['name'] for r in result['rc_comparison']],['Output'])
                self.assertNotEqual(result['before_waveform']['traces']['vout'],result['after_waveform']['traces']['vout'])
        self.assertEqual(results[0]['before_waveform']['traces'],results[1]['before_waveform']['traces'])
        self.assertNotEqual(results[0]['extraction']['coefficient_hash'],results[1]['extraction']['coefficient_hash'])
        self.assertNotEqual(results[0]['after_waveform']['traces'],results[1]['after_waveform']['traces'])


if __name__=='__main__':unittest.main()
