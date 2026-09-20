"""Geometric matching, shielding and constraint-preserving resize transactions."""
import unittest
from icstudio.model import example, device, clone, validate, History
from icstudio.layout import rect
from icstudio.analog_constraints import findings as analog_findings, footprint, move_device
from icstudio.route_constraints import findings, enforce
from icstudio.layout_routing import matched_pair, shield, install
from icstudio.layout_eco_hierarchy import propose
from icstudio.layout_eco import apply


def endpoint(x,y,layer='metal1'):
    return dict(layer=layer,point=[x,y])


def pair():
    p=example('empty'); cid=p['top']
    proposal=matched_pair(p,cid,[endpoint(0,0),endpoint(0,5000)],
                          [endpoint(10000,0),endpoint(10000,5000)],['a','b'],400,layers=['metal1'])
    install(p,proposal)
    return p


def resistors():
    from icstudio.parametric import install as generate
    p=example('empty'); c=p['cells'][0]
    c['devices']=[device('R','R'+str(i+1),value='1k',nets={'p':'a'+str(i),'n':'b'+str(i)}) for i in range(2)]
    for i,d in enumerate(c['devices']): generate(p,c['id'],d['id'],dict(x=i*50000,width=1000))
    ids=[d['id'] for d in c['devices']]; centers=[footprint(p,c['id'],did)[2] for did in ids]
    c['analog_constraints']=[dict(id='match',name='Equal resistors',kind='matching',members=ids),
                             dict(id='axis',name='Pair axis',kind='symmetry',members=ids,axis='x',coordinate=sum(pt[0] for pt in centers)/2)]
    return p,ids


class MatchedRouting(unittest.TestCase):
    def test_width_and_per_layer_balance_are_checked_even_when_total_length_matches(self):
        p=pair();self.assertFalse(findings(p,p['top']))
        q=clone(p);q['cells'][0]['shapes'][0]['width']=600
        failure=findings(q,q['top'])[0]
        self.assertEqual(failure['metrics']['length_skew_nm'],0)
        self.assertEqual(failure['metrics']['width_errors'],1)
        self.assertTrue(failure['boxes']);self.assertTrue(failure['shape_ids'])
        with self.assertRaisesRegex(ValueError,'constraint'):enforce(p,q,p['top'])
        q=clone(p);q['cells'][0]['shapes'][1]['layer']='metal2'
        self.assertEqual(findings(q,q['top'])[0]['metrics']['layer_excess_nm'],20000)

    def test_saved_terminal_contact_detects_equal_length_translation(self):
        p=pair();q=clone(p)
        for pt in q['cells'][0]['shapes'][1]['points']:pt[0]+=1000
        result=findings(q,q['top'])[0]
        self.assertEqual(result['metrics']['length_skew_nm'],0)
        self.assertEqual(result['metrics']['endpoint_errors'],1)

    def test_disconnected_same_net_shapes_do_not_count_as_valid_matching(self):
        p=pair();q=clone(p);c=q['cells'][0];route=c['shapes'][0]
        route['points'][-1]=[5000,0]
        extra={**clone(route),'id':'detached','points':[[5000,1500],[10000,1500]]}
        c['shapes'].append(extra);c['routing_records'][0]['shape_ids'].append(extra['id'])
        result=findings(q,q['top'])[0]
        self.assertEqual(result['metrics']['length_skew_nm'],0)
        self.assertEqual(result['metrics']['disconnected_components'],1)

    def test_multilayer_pair_requires_corresponding_vias(self):
        p=example('empty');cid=p['top']
        with self.assertRaisesRegex(ValueError,'equal via'):
            matched_pair(p,cid,[endpoint(0,0),endpoint(0,10000)],
                         [endpoint(10000,0),endpoint(10000,10000,'metal2')],['a','b'],400)
        proposal=matched_pair(p,cid,[endpoint(0,0),endpoint(0,10000)],
                              [endpoint(10000,0,'metal2'),endpoint(10000,10000,'metal2')],['a','b'],400)
        install(p,proposal);self.assertFalse(findings(p,cid))
        q=clone(p);next(s for s in q['cells'][0]['shapes'] if s.get('via_group'))['via_group']='changed'
        self.assertGreater(findings(q,cid)[0]['metrics']['via_errors'],0)

    def test_invalid_or_stale_route_proposal_is_atomic(self):
        p=example('empty');cid=p['top'];r=matched_pair(p,cid,[endpoint(0,0),endpoint(0,5000)],[endpoint(5000,0),endpoint(5000,5000)],['a','b'],400,layers=['metal1'])
        old=clone(p);r['shapes'][0]['width']=600
        with self.assertRaisesRegex(ValueError,'constraint'):install(p,r)
        self.assertEqual(p,old)
        p['name']='Changed'
        with self.assertRaisesRegex(ValueError,'changed after routing'):install(p,r)

    def test_old_length_only_records_remain_length_only(self):
        p=pair();c=p['cells'][0];c['routing_records'][0]['version']=1
        c['shapes'][0]['width']=600;c['shapes'][1]['layer']='metal2'
        self.assertFalse(findings(p,p['top']))

    def test_persisted_intent_rejects_invalid_units_and_anchor_schema(self):
        p=pair();validate(p)
        for key,value in [('width_nm',float('nan')),('match_layers','yes'),('layer_tolerance_nm',-1)]:
            q=clone(p);q['cells'][0]['routing_records'][0]['matching'][key]=value
            with self.assertRaisesRegex(ValueError,'matching intent'):validate(q)
        p['cells'][0]['routing_records'][0]['endpoints'][0][0]={'kind':'point','layer':'metal1','point':[0]}
        with self.assertRaisesRegex(ValueError,'endpoint'):validate(p)


class Shielding(unittest.TestCase):
    def fixture(self):
        p=example('empty');c=p['cells'][0]
        s=dict(id='signal',kind='path',layer='metal1',width=400,points=[[0,0],[10000,0]],net='sig',device_id='')
        c['shapes']=[s,rect('metal2',-3200,-200,400,400,net='0')]
        install(p,shield(p,p['top'],'signal',endpoint(-3000,0,'metal2')))
        return p

    def test_bounded_shield_gap_and_signal_net_survive_edit_checks(self):
        p=self.fixture();self.assertFalse(findings(p,p['top']))
        q=clone(p);s=next(s for s in q['cells'][0]['shapes'] if s.get('shield_for'))
        for pt in s['points']:pt[1]-=1000
        result=findings(q,q['top'])[0]
        self.assertGreater(result['metrics']['gap_excess_nm'],0)
        q=clone(p);q['cells'][0]['shapes'][0]['net']='0'
        self.assertIn('signal net',findings(q,q['top'])[0]['message'])


class ResizeTransactions(unittest.TestCase):
    def test_equivalent_total_and_per_finger_symbols_match_in_mirror_recipe(self):
        from tests.test_process_mos import project
        from icstudio.analog_layout import generate_mirror,matching_findings
        from icstudio.physical import connectivity
        p,a=project();_,b=project(per_finger=True);b['name']='M2'
        a['model_params']['nf']=4;b['model_params']['nf']=4;b['params']['w']='1u'
        a['nets']={'d':'bias','g':'bias','s':'vss','b':'vss'};b['nets']={'d':'out','g':'bias','s':'vss','b':'vss'}
        c=p['cells'][0];c['devices']=[a,b];c['ports']=['bias','out','vss']
        generate_mirror(p,p['top']);c['analog_constraints']=[dict(id='pair',kind='matching',members=[a['id'],b['id']])]
        self.assertFalse(analog_findings(p,p['top']));self.assertFalse(matching_findings(p,p['top']))
        self.assertFalse(connectivity(p,p['top'])['issues'])
        b['params']['w']='2u'
        self.assertGreater(analog_findings(p,p['top'])[0]['metrics']['electrical_mismatches'],0)

    def test_generic_poly_dummy_pattern_and_guard_survive_matched_mos_resize(self):
        from icstudio.parametric import install as generate
        p=example('empty');c=p['cells'][0]
        c['devices']=[device('NMOS','M'+str(i),nets={'d':'d'+str(i),'g':'g'+str(i),'s':'s','b':'b'}) for i in range(2)]
        for i,d in enumerate(c['devices']):
            d['params'].update(w='8u',l='1u')
            generate(p,p['top'],d['id'],dict(x=i*50000,fingers=4,dummies=2,guard=True))
        ids=[d['id'] for d in c['devices']];c['analog_constraints']=[dict(id='match',kind='matching',members=ids)]
        dummy_ids={s['id'] for s in c['shapes'] if s.get('pcell_role','').startswith('dummy_')}
        for d in c['devices']:d['params']['w']='12u'
        q,r=propose(p,p['top'],[(p['top'],did) for did in ids],strict_constraints=True)
        self.assertFalse(analog_findings(q,p['top']));self.assertEqual(len(r['preserved_centers']),2)
        self.assertEqual(dummy_ids,{s['id'] for s in q['cells'][0]['shapes'] if s.get('pcell_role','').startswith('dummy_')})
        for record in q['cells'][0]['parametric_devices']:
            self.assertEqual(record['electrical']['dummy_type'],'poly-only edge patterns')
            self.assertEqual(record['electrical']['width_nm'],12000)
            self.assertEqual(record['electrical']['dummies_per_edge'],2)

    def test_child_master_resize_checks_constraints_on_parent_instances(self):
        from icstudio.parametric import install as generate
        p=example('empty');top=p['cells'][0]
        child=dict(id='unit',name='unit',ports=[],devices=[device('R','R1',value='1k')],shapes=[])
        p['cells'].append(child);generate(p,'unit',child['devices'][0]['id'],{})
        top['devices']=[device('X','X1',cell='unit',nets={}),device('X','X2',cell='unit',nets={})]
        top['layout_instances']=[dict(id='placement'+str(i),name=d['name'],cell='unit',device_id=d['id'],x=i*50000,y=0) for i,d in enumerate(top['devices'])]
        members=[d['id'] for d in top['devices']]
        centers=[footprint(p,p['top'],did)[2] for did in members]
        top['analog_constraints']=[dict(id='parent_axis',kind='symmetry',members=members,axis='x',coordinate=sum(v[0] for v in centers)/2)]
        child['devices'][0]['value']='2k';old=clone(p)
        for active in (p['top'],'unit'):
            with self.assertRaisesRegex(ValueError,'constraint'):
                propose(p,active,[('unit',child['devices'][0]['id'])],preserve_routes=False)
        self.assertEqual(p,old)

    def test_paired_resize_preserves_centers_matching_routes_and_undo(self):
        p,ids=resistors();cid=p['top'];c=p['cells'][0]
        centers={did:footprint(p,cid,did)[2] for did in ids}
        for i,d in enumerate(c['devices']):
            pin=next(v for v in c['layout_pins'] if v['device_id']==d['id'] and v['pin']=='n')
            pt=pin['point'];c['shapes'].append(dict(id='lead'+str(i),kind='path',layer=pin['layer'],width=400,points=[clone(pt),[pt[0],pt[1]+20000]],net=d['nets']['n']))
            d['value']='2k'
        old=clone(p);q,r=propose(p,cid,[(cid,did) for did in ids],strict_constraints=True)
        self.assertEqual(p,old);self.assertEqual(len(r['preserved_centers']),2)
        self.assertEqual(set(r['adjusted_routes']),{'lead0','lead1'})
        self.assertFalse(analog_findings(q,cid));self.assertFalse(r['constraint_findings'][cid])
        self.assertEqual({did:footprint(q,cid,did)[2] for did in ids},centers)
        h=History(p);h.commit(lambda target:apply(target,q,r),'Resize constrained pair')
        h.undo();self.assertEqual(h.project['cells'],p['cells']);h.redo();self.assertEqual(h.project['cells'],q['cells'])

    def test_partial_resize_cannot_hide_geometry_mismatch_behind_electrical_mismatch(self):
        p,ids=resistors();cid=p['top'];p['cells'][0]['devices'][0]['value']='2k';old=clone(p)
        self.assertEqual(analog_findings(p,cid)[0]['metrics']['electrical_mismatches'],1)
        with self.assertRaisesRegex(ValueError,'constraint worsened'):
            propose(p,cid,[(cid,ids[0])],preserve_routes=False)
        self.assertEqual(p,old)

    def test_existing_violation_can_remain_or_improve_but_cannot_worsen(self):
        p,ids=resistors();cid=p['top'];move_device(p,cid,ids[1],1000,0)
        for d in p['cells'][0]['devices']:d['value']='2k'
        q,r=propose(p,cid,[(cid,did) for did in ids],preserve_routes=False)
        self.assertEqual(r['constraint_findings'][cid][0]['metrics']['axis_error_nm'],1000)
        with self.assertRaisesRegex(ValueError,'constraint'):
            propose(p,cid,[(cid,did) for did in ids],preserve_routes=False,strict_constraints=True)
        bad=clone(p);move_device(bad,cid,ids[1],500,0)
        with self.assertRaisesRegex(ValueError,'worsened'):enforce(p,bad,cid)
        better=clone(p);move_device(better,cid,ids[1],-500,0);enforce(p,better,cid)

    def test_stale_source_and_tampered_candidate_never_apply(self):
        p,ids=resistors();cid=p['top']
        for d in p['cells'][0]['devices']:d['value']='2k'
        q,r=propose(p,cid,[(cid,did) for did in ids],preserve_routes=False)
        old=clone(p);q['cells'][0]['shapes'][0]['points'][0][0]+=5
        with self.assertRaisesRegex(ValueError,'candidate changed'):apply(p,q,r)
        self.assertEqual(p,old)
        p['name']='Edited'
        with self.assertRaisesRegex(ValueError,'stale'):apply(p,q,r)


if __name__=='__main__':unittest.main()
