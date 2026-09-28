import unittest
from icstudio.model import example, device, uid, clone, History, validate
from icstudio.physical_variants import propose, materialize, electrical_signature
from icstudio.physical_cells import place, terminals


def physical_project():
    from icstudio.parametric import install
    p = example('empty'); top = p['cells'][0]
    leaf = {'id': uid(), 'name': 'leaf', 'ports': ['a', 'b'],
            'parameters': {'r': '1k'}, 'devices': [device('R', 'R1', value='1k', nets={'p': 'a', 'n': 'b'})], 'shapes': []}
    p['cells'].append(leaf)
    install(p, leaf['id'], leaf['devices'][0]['id'], {'kind': 'resistor'})
    leaf['layout_ports'] = [{'name': v['pin'].replace('p', 'a').replace('n', 'b'), 'layer': v['layer'], 'point': clone(v['point'])} for v in leaf['layout_pins']]
    leaf['devices'][0]['value'] = '{r}'
    top['devices'] = [device('X', 'X1', cell=leaf['id'], nets={'a': 'in', 'b': 'out'}, parameters={'r': '2k'})]
    return validate(p), top['id'], leaf['id']


class PhysicalMaterializationTests(unittest.TestCase):
    def test_regenerates_geometry_ports_and_reuses_persistent_cache(self):
        p, cid, source = physical_project(); old = clone(p)
        q, report = materialize(p, cid)
        self.assertEqual(p, old); self.assertEqual(report['variants'], 1)
        variant = next(c for c in q['cells'] if c['id'] == q['cells'][0]['devices'][0]['cell'])
        self.assertEqual(variant['parametric_devices'][0]['electrical']['target'], 2000)
        self.assertEqual(next(v['point'] for v in variant['layout_ports'] if v['name'] == 'b'), [20000, 500])
        self.assertEqual(electrical_signature(p, cid), electrical_signature(q, cid))
        q['cells'][0]['devices'].append(device('X', 'X2', cell=source, nets={'a': 'in2', 'b': 'out2'}, parameters={'r': '2k'}))
        r, reused = materialize(q, cid)
        self.assertEqual(reused['variants'], 0); self.assertEqual(reused['reused_variants'], 1)
        self.assertEqual(r['cells'][0]['devices'][0]['cell'], r['cells'][0]['devices'][1]['cell'])
        no_op, empty = materialize(r, cid)
        self.assertEqual(no_op, r); self.assertEqual(empty['instances'], [])

    def test_cache_rejects_edited_implementation_and_changed_technology(self):
        for fault in ('geometry', 'technology', 'source'):
            p, cid, source = physical_project(); q, _ = materialize(p, cid)
            original = q['cells'][0]['devices'][0]['cell']
            q['cells'][0]['devices'].append(device('X', 'X2', cell=source, nets={'a': 'in2', 'b': 'out2'}, parameters={'r': '2k'}))
            if fault == 'geometry': next(c for c in q['cells'] if c['id'] == original)['shapes'][0]['points'][0][0] += 5
            elif fault == 'technology': q['pdk']['layers'][0]['color'] = '#aabbcc'
            else: next(c for c in q['cells'] if c['id'] == source)['name'] = 'edited_source'
            r, report = materialize(q, cid)
            self.assertEqual(report['variants'], 1)
            self.assertNotEqual(r['cells'][0]['devices'][1]['cell'], original)

    def test_place_is_atomic_parameter_correct_and_undoable(self):
        p, cid, source = physical_project(); before = clone(p); did = p['cells'][0]['devices'][0]['id']
        with self.assertRaisesRegex(ValueError, 'grid'):
            place(p, cid, did, 1, 0)
        self.assertEqual(p, before)
        h = History(p)
        h.commit(lambda q: place(q, cid, did, 30000, 10000, 90, True), 'Place parameterized cell')
        cell = h.project['cells'][0]
        self.assertNotEqual(cell['devices'][0]['cell'], source)
        self.assertEqual(cell['layout_instances'][0]['device_id'], did)
        self.assertEqual(next(v['point'] for v in terminals(h.project, cid) if v['pin'] == 'b'), [30500, 30000])
        h.undo(); self.assertEqual(h.project['cells'], p['cells'])
        h.redo(); self.assertEqual(h.project['cells'][0]['layout_instances'][0]['device_id'], did)

    def test_manual_parameter_dependent_geometry_fails_without_mutation(self):
        p, cid, _ = physical_project(); p['cells'][1].pop('parametric_devices'); before = clone(p)
        with self.assertRaisesRegex(ValueError, 'no regenerable footprint'): materialize(p, cid)
        self.assertEqual(p, before)

    def test_stale_review_rejected_by_shared_apply(self):
        from icstudio.layout_eco import apply
        p, cid, _ = physical_project(); q, report = materialize(p, cid)
        q['cells'][0]['name'] = 'tampered'
        with self.assertRaisesRegex(ValueError, 'candidate changed'): apply(p, q, report)

    def test_fresh_and_cached_master_retarget_existing_parent_route_and_port(self):
        for cached in (False, True):
            p,cid,source=physical_project(); top=p['cells'][0]; d=top['devices'][0]
            d['parameters']={};place(p,cid,d['id'],0,0)
            top['shapes']=[{'id':uid(),'kind':'path','layer':'metal1','width':200,
                            'points':[[10000,500],[15000,500]],'net':'out'}]
            top['ports']=['out'];top['layout_ports']=[{'name':'out','layer':'metal1','point':[10000,500]}]
            if cached:
                cache=device('X','XCACHE',x=600,cell=source,nets={'a':'cache_a','b':'cache_b'},parameters={'r':'2k'})
                top['devices'].append(cache);p,_=materialize(p,cid,{cache['id']})
            top=p['cells'][0];top['devices'][0]['parameters']={'r':'2k'}
            q,report=materialize(p,cid,{d['id']})
            self.assertEqual(report['reused_variants'],int(cached))
            self.assertEqual(q['cells'][0]['shapes'][0]['points'],[[20000,500],[15000,500]])
            self.assertEqual(q['cells'][0]['layout_ports'][0]['point'],[20000,500])

    def test_nested_parameter_variants_follow_child_ports_and_transforms(self):
        p,cid,leafid=physical_project();top=p['cells'][0];leaf=p['cells'][1]
        child=device('X','Xleaf',cell=leafid,nets={'a':'a','b':'b'},parameters={'r':'{outer}'})
        wrapper={'id':uid(),'name':'wrapper','ports':['a','b'],'parameters':{'outer':'1k'},
                 'devices':[child],'shapes':[], 'layout_ports':clone(leaf['layout_ports']),
                 'layout_instances':[{'id':uid(),'name':'Xleaf','cell':leafid,'device_id':child['id'],'x':0,'y':0,'rotation':0,'mirror':False}]}
        p['cells'].append(wrapper)
        d=top['devices'][0];d.update(cell=wrapper['id'],parameters={'outer':'2k'})
        top['layout_instances']=[{'id':uid(),'name':d['name'],'cell':wrapper['id'],'device_id':d['id'],
                                  'x':30000,'y':10000,'rotation':90,'mirror':True}]
        validate(p);q,report=materialize(p,cid)
        self.assertEqual(report['variants'],2)
        self.assertEqual(electrical_signature(q,cid),electrical_signature(p,cid))
        self.assertEqual(next(pin['point'] for pin in terminals(q,cid) if pin['pin']=='b'),[30500,30000])
        source=next(c for c in q['cells'] if c['id']==leafid)
        self.assertEqual(source['parametric_devices'][0]['electrical']['target'],1000)


class PhysicalArrayMaterializationTests(unittest.TestCase):
    def array_project(self, wired=False):
        p, cid, leaf = physical_project(); top=p['cells'][0]; d=top['devices'][0]
        d.update(array={'start':2,'end':0}, nets={'a':'in[2:0]','b':'out[2:0]'})
        top['layout_instances']=[{'id':uid(),'name':d['name'],'cell':leaf,'device_id':d['id'],
                                  'x':30000,'y':10000,'rotation':90,'mirror':True,'nx':1,'ny':1}]
        if wired:
            from icstudio.wiring import migrate
            migrate(top,p)
        return validate(p), cid, d['id']

    def test_stable_members_transforms_parameter_cache_connections_and_undo(self):
        from icstudio.physical_cells import materialize_array
        from icstudio.electrical_identity import terminal_id
        p,cid,did=self.array_project(); before=clone(p); q=clone(p)
        result=materialize_array(q,cid,did,a=[0,50000])
        r=clone(p);materialize_array(r,cid,did,a=[0,50000])
        self.assertEqual(result['placements'],3)
        self.assertEqual([d['id'] for d in q['cells'][0]['devices']],[d['id'] for d in r['cells'][0]['devices']])
        self.assertEqual([i['id'] for i in q['cells'][0]['layout_instances']],[i['id'] for i in r['cells'][0]['layout_instances']])
        self.assertEqual(len({d['cell'] for d in q['cells'][0]['devices']}),1)
        self.assertEqual(electrical_signature(q,cid),electrical_signature(p,cid))
        self.assertEqual([v['point'] for v in terminals(q,cid) if v['pin']=='b'],[[30500,30000],[30500,80000],[30500,130000]])
        self.assertEqual([d['nets']['a'] for d in q['cells'][0]['devices']],['in[2]','in[1]','in[0]'])
        self.assertEqual(len({terminal_id(d,'a') for d in q['cells'][0]['devices']}),3)
        h=History(p);h.commit(lambda target:materialize_array(target,cid,did,a=[0,50000]),'Materialize array');h.undo()
        self.assertEqual(h.project['cells'],before['cells']);h.redo();validate(h.project)

    def test_negative_controls_are_atomic(self):
        from icstudio.physical_cells import materialize_array
        for opts,fragment in [({'a':[0,0]},'distinct'),({'a':[1,0]},'grid'),({'nx':2,'ny':2},'member count')]:
            p,cid,did=self.array_project();before=clone(p)
            with self.assertRaisesRegex(ValueError,fragment):materialize_array(p,cid,did,**opts)
            self.assertEqual(p,before)
        p,cid,did=self.array_project();p['cells'][0]['devices'].append(device('R','X1__2',value='1k'));before=clone(p)
        with self.assertRaisesRegex(ValueError,'collid|Duplicate'):materialize_array(p,cid,did,a=[30000,0])
        self.assertEqual(p,before)

    def test_wired_capture_keeps_electrical_meaning_and_labels(self):
        from icstudio.physical_cells import materialize_array
        from icstudio.wiring import pins, rebuild
        p,cid,did=self.array_project(wired=True);top=p['cells'][0]
        point=pins(top,p)[(did,'a')]
        top['wires']=[{'id':uid(),'points':[[point[0]-100,point[1]],point]}]
        top['labels']=[{'id':uid(),'kind':'net_label','name':'in[2:0]',
                        'anchor':{'kind':'pin','id':did,'pin':'a'},'offset':[10,-12],'rotation':0}]
        rebuild(top,p);before=electrical_signature(p,cid);wire=clone(top['wires'][0])
        materialize_array(p,cid,did,a=[0,50000]);self.assertEqual(electrical_signature(p,cid),before)
        self.assertEqual(p['cells'][0]['wires'][0]['points'],wire['points'])
        self.assertTrue(all(d['net_labels']==d['nets'] for d in p['cells'][0]['devices']))
        self.assertTrue(all(label['anchor']['kind']!='pin' or label['anchor']['id']!=did for label in p['cells'][0]['labels']))
        validate(p)

    def test_compact_array_never_appears_as_one_physical_terminal_set(self):
        p,cid,did=self.array_project()
        from icstudio.physical_cells import audit
        self.assertEqual(terminals(p,cid),[])
        self.assertTrue(any(issue['code']=='LAYOUT.ARRAY' for issue in audit(p,cid)))


class PhysicalVectorInterfaceTests(unittest.TestCase):
    def test_vector_ports_array_materialization_connectivity_and_rc_flattening(self):
        from icstudio.parametric import install
        from icstudio.physical_cells import materialize_array
        from icstudio.physical import connectivity
        from icstudio.rc_hierarchy import flatten_for_rc
        p=example('empty');top=p['cells'][0]
        leaf={'id':uid(),'name':'vector_leaf','ports':['a[1:0]','b[1:0]'], 'devices':[], 'shapes':[],'layout_ports':[]}
        p['cells'].append(leaf)
        for index in (1,0):
            d=device('R','R'+str(index),value='1k',nets={'p':f'a[{index}]','n':f'b[{index}]'})
            leaf['devices'].append(d);install(p,leaf['id'],d['id'],{'kind':'resistor','y':index*50000})
        leaf['layout_ports']=[{'name':next(d for d in leaf['devices'] if d['id']==v['device_id'])['nets'][v['pin']],
                              'layer':v['layer'],'point':clone(v['point'])} for v in leaf['layout_pins']]
        d=device('X','XBANK',cell=leaf['id'],nets={'a[1:0]':'IN[3:0]','b[1:0]':'OUT[3:0]'},array={'start':1,'end':0})
        top['devices']=[d];top['layout_instances']=[{'id':uid(),'name':d['name'],'device_id':d['id'],'cell':leaf['id'],'x':0,'y':0}]
        validate(p);before=electrical_signature(p,top['id']);materialize_array(p,top['id'],d['id'],a=[30000,0])
        self.assertEqual(electrical_signature(p,top['id']),before)
        self.assertEqual([d['nets']['a[1:0]'] for d in p['cells'][0]['devices']],['IN[3],IN[2]','IN[1],IN[0]'])
        self.assertEqual(len(terminals(p,top['id'])),8)
        self.assertFalse(connectivity(p,top['id'])['issues'])
        flat,report=flatten_for_rc(p,top['id']);root=next(c for c in flat['cells'] if c['id']==top['id'])
        self.assertEqual(len(root['devices']),4)
        self.assertEqual({d['nets']['p'] for d in root['devices']},{'IN[3]','IN[2]','IN[1]','IN[0]'})
        self.assertEqual(len(report['occurrences']),2)


if __name__ == '__main__': unittest.main()
