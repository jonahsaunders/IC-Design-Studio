import tempfile
import unittest
from pathlib import Path
from icstudio.model import example, clone, History, device, uid, save_project, load_project
from icstudio.layout import rect, polygon, kdb
from icstudio.layout_edit import place_via, via_options
from icstudio.layout_vias import plan, install
from icstudio.layout_topology import partition
from icstudio.live_geometry import check_enclosures


class ViaTests(unittest.TestCase):
    def setUp(self):
        self.p = example('empty'); self.c = self.p['cells'][0]; self.cid = self.c['id']

    def overlap(self, size=1000, nets=('signal', 'signal')):
        self.c['shapes'] = [rect(layer, 0, 0, size, size, net=net)
                            for layer, net in zip(('metal1', 'metal2'), nets)]
        return [s['id'] for s in self.c['shapes']]

    def test_manual_generic_geometry_connects_and_survives_reopen(self):
        self.overlap(350)
        ids = place_via(self.p, self.cid, 'M1 to M2', [175,175], 'signal')
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(set(partition(self.p,self.cid).values())), 1)
        self.assertFalse(check_enclosures(self.p,self.cid,self.c['shapes']))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'vias.icproj';save_project(self.p,path)
            self.assertEqual(load_project(path)['cells'],self.p['cells'])

    def test_manual_process_needs_only_mapped_via_masks(self):
        for family, pairs, size, pad in [('sky130A',[(68,20),(68,44),(69,20)],150,340),
                                        ('gf180mcuC',[(34,0),(35,0),(36,0)],260,440)]:
            with self.subTest(family=family):
                p=example('empty');tech=p['pdk'];tech['revision']='fixture'
                tech['package_lock']={'id':family,'revision':'fixture','files':{}}
                tech['layers']=[dict(name=n,gds=g,datatype=d,color='#8899aa',width=0,space=0)
                                for n,(g,d) in zip(('bottom','cut','top'),pairs)]
                self.assertEqual(via_options(tech)['M1 to M2'],('bottom','cut','top',size,pad))
                place_via(p,p['top'],'M1 to M2',[0,0])
                self.assertEqual(len(set(partition(p,p['top']).values())),1)
                from icstudio.process_adapters import physical_adapter
                with self.assertRaises(ValueError):physical_adapter(p['pdk']).engine_assets(p['pdk'])

    def test_manual_locks_invalid_recipe_and_grid_fail_atomically(self):
        for args in [dict(locked=['via1']),dict(point=[1,0]),dict(net='bad net')]:
            old=clone(self.p)
            with self.assertRaises(ValueError):
                place_via(self.p,self.cid,'M1 to M2',**({'point':[0,0]}|args))
            self.assertEqual(self.p,old)
        self.p['pdk']['routing_vias']=[dict(name='invalid',lower='metal1',cut='via1',upper='metal2',size=151,enclosure=100)]
        with self.assertRaisesRegex(ValueError,'on-grid'):via_options(self.p['pdk'])

    def test_native_array_spacing_survives_unqualified_import_layer_defaults(self):
        from test_silicon import technology
        for connection,lower,cut,upper,space in [('M1 to M2','m1','via','m2',170),
                                                ('Local interconnect to M1','li','mcon','m1',190)]:
            p=example('empty');p['pdk']=technology();c=p['cells'][0]
            c['shapes']=[rect(layer,0,0,1000,1000,net='a') for layer in (lower,upper)]
            r=plan(p,p['top'],[s['id'] for s in c['shapes']],connection)
            self.assertGreater(r['via_count'],1)
            cuts=kdb().Region([polygon(s) for s in r['shapes'] if s['layer']==cut])
            self.assertTrue(cuts.space_check(space).is_empty())
            self.assertEqual(sum(1 for _ in cuts.merged().each()),r['via_count'])

    def test_custom_spacing_and_imported_geometry_preview(self):
        ids=self.overlap();self.p['pdk']['layers'][4]['space']=0
        with self.assertRaisesRegex(ValueError,'positive via cut spacing'):plan(self.p,self.cid,ids)
        from icstudio.live_geometry import preview
        p=example('empty');p['pdk']['layers']=[dict(name='layer_80_20',gds=80,datatype=20,color='#123456',width=0,space=0)]
        self.assertFalse(preview(p,p['top'],[rect('layer_80_20',0,0,1000,1000)]))

    def test_legacy_attached_project_uses_imported_masks_not_generic_layers(self):
        p=example('empty');old=clone(p['pdk'])
        p['spice']={'library_lock':{'variant':'sky130A'}};p['layout_attachment']={'schema':1}
        for g,d in [(68,20),(68,44),(69,20)]:
            p['pdk']['layers'].append(dict(name=f'layer_{g}_{d}',gds=g,datatype=d,color='#123456',width=0,space=0))
        expected=('layer_68_20','layer_68_44','layer_69_20',150,340)
        self.assertEqual(via_options(p)['M1 to M2'],expected)
        before=clone(p);place_via(p,p['top'],'M1 to M2',[0,0])
        self.assertEqual({s['layer'] for s in p['cells'][0]['shapes']},set(expected[:3]))
        self.assertNotIn('package_lock',p['pdk'])
        self.assertEqual(p['pdk']['status'],old['status'])
        self.assertIn(['metal1','via1','metal2'],p['pdk']['connectivity']['vias'])
        self.assertEqual(len(set(partition(p,p['top']).values())),1)
        # Explicit technology recipes override import recovery. Layer numbers or
        # simulation metadata alone must never imply a different process.
        before['pdk']['routing_vias']=[];self.assertFalse(via_options(before))
        del before['pdk']['routing_vias'];del before['layout_attachment']
        self.assertEqual(via_options(before)['M1 to M2'][:3],('metal1','via1','metal2'))

    def test_array_is_on_grid_enclosed_spaced_and_one_undo(self):
        ids=self.overlap();before=clone(self.p);proposal=plan(self.p,self.cid,ids)
        self.assertEqual(self.p,before);self.assertEqual(proposal['via_count'],9)
        h=History(self.p);h.commit(lambda p:install(p,proposal),'Autovia')
        after=clone(h.project['cells']);self.assertEqual(len(set(partition(h.project,self.cid).values())),1)
        shapes=after[0]['shapes'];self.assertFalse(check_enclosures(h.project,self.cid,shapes))
        cuts=kdb().Region([polygon(s) for s in shapes if s['layer']=='via1'])
        self.assertTrue(cuts.space_check(150).is_empty())
        self.assertTrue(all(v%5==0 for s in proposal['shapes'] for pt in s['points'] for v in pt))
        h.undo();self.assertEqual(h.project['cells'],before['cells']);h.redo();self.assertEqual(h.project['cells'],after)

    def test_exact_fit_negative_coordinates_and_narrow_overlap(self):
        ids=self.overlap(350)
        for s in self.c['shapes']:s['points']=[[x-1000,y-1000] for x,y in s['points']]
        r=plan(self.p,self.cid,ids);self.assertEqual(r['via_count'],1)
        self.assertEqual(polygon(r['shapes'][1]).bbox().center(),kdb().Point(-825,-825))
        ids=self.overlap(345)
        with self.assertRaisesRegex(ValueError,'No new via'):plan(self.p,self.cid,ids)

    def test_concave_polygon_holes_and_paths_use_real_geometry(self):
        ring=dict(id=uid(),kind='polygon',layer='metal1',net='signal',
                  points=[[0,0],[2000,0],[2000,2000],[0,2000]],
                  holes=[[[700,700],[700,1300],[1300,1300],[1300,700]]])
        wire=dict(id=uid(),kind='path',layer='metal2',net='signal',width=500,
                  points=[[250,0],[250,1750],[1750,1750]])
        self.c['shapes']=[ring,wire];r=plan(self.p,self.cid,[ring['id'],wire['id']])
        region=kdb().Region(polygon(ring)) & kdb().Region(polygon(wire))
        self.assertGreater(r['via_count'],0)
        for s in r['shapes']:
            self.assertTrue((kdb().Region(polygon(s))-region).is_empty())

    def test_repeated_operation_does_not_duplicate_cuts(self):
        ids=self.overlap();r=plan(self.p,self.cid,ids);install(self.p,r);old=clone(self.p)
        with self.assertRaisesRegex(ValueError,'existing cuts'):plan(self.p,self.cid,ids)
        self.assertEqual(self.p,old)

    def test_existing_cut_in_child_blocks_site_without_editing_child(self):
        ids=self.overlap(350)
        child=dict(id=uid(),name='cut_cell',ports=[],devices=[],shapes=[rect('via1',100,100,150,150)])
        self.p['cells'].append(child);self.c['layout_instances']=[dict(id=uid(),name='I1',cell=child['id'],x=0,y=0)]
        old=clone(self.p)
        with self.assertRaisesRegex(ValueError,'No new via'):plan(self.p,self.cid,ids)
        self.assertEqual(self.p,old)

    def test_conflicting_net_elsewhere_on_connected_shape_is_rejected(self):
        ids=self.overlap(nets=('','b'))
        self.c['shapes'].append(rect('metal1',1000,0,1000,1000,net='a'))
        old=clone(self.p)
        with self.assertRaisesRegex(ValueError,'conflicting nets'):plan(self.p,self.cid,ids)
        self.assertEqual(self.p,old)

    def test_blank_bridge_cannot_join_two_separate_named_nets(self):
        self.c['shapes']=[rect('metal1',0,0,3000,1000),rect('metal2',0,0,1000,1000,net='a'),
                          rect('metal2',2000,0,1000,1000,net='b')]
        with self.assertRaisesRegex(ValueError,'conflicting nets'):
            plan(self.p,self.cid,[s['id'] for s in self.c['shapes']])

    def test_assigned_terminals_protect_unlabeled_conductors(self):
        ids=self.overlap(nets=('',''));d=device('R','R1',nets={'p':'a','n':'b'});self.c['devices']=[d]
        self.c['layout_pins']=[dict(id=uid(),device_id=d['id'],pin=pin,layer=layer,point=[500,500])
                               for pin,layer in [('p','metal1'),('n','metal2')]]
        with self.assertRaisesRegex(ValueError,'conflicting nets'):plan(self.p,self.cid,ids)

    def test_stale_and_locked_install_leave_project_unchanged(self):
        ids=self.overlap();r=plan(self.p,self.cid,ids);old=clone(self.p)
        with self.assertRaisesRegex(ValueError,'Unlock'):install(self.p,r,['via1'])
        self.assertEqual(self.p,old)
        self.p['name']='Changed';old=clone(self.p)
        with self.assertRaisesRegex(ValueError,'changed'):install(self.p,r)
        self.assertEqual(self.p,old)

    def test_unsupported_selection_locks_and_budget_are_actionable(self):
        ids=self.overlap()
        for args, message in [(dict(ids=ids[:1]),'Select'),(dict(locked=['via1']),'Unlock'),
                              (dict(max_vias=2),'limit')]:
            with self.subTest(args=args),self.assertRaisesRegex(ValueError,message):
                plan(self.p,self.cid,**({'ids':ids}|args))
        ids=self.overlap(100000)
        with self.assertRaisesRegex(ValueError,'search exceeds'):plan(self.p,self.cid,ids)


if __name__=='__main__':unittest.main()
