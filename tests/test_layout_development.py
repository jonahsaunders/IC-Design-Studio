import json
import tempfile
import unittest
from pathlib import Path
from icstudio.model import example, clone, uid, History, device, validate
from icstudio.layout import rect, polygon, kdb
from icstudio.layout_routing import plan, install, matched_pair, shield, RoutingCancelled, Geometry
from icstudio.layout_topology import move, stretch, partition


def path(points, net='a', layer='metal1', width=400):
    return {'id':uid(),'kind':'path','layer':layer,'width':width,'points':points,'net':net,'device_id':''}


class ConnectedLayoutTests(unittest.TestCase):
    def setUp(self):
        self.p=example('empty');self.c=self.p['cells'][0];self.cid=self.c['id']

    def pair(self):
        a=rect('metal1',-300,-300,600,600,net='a');b=rect('metal1',4700,-300,600,600,net='a')
        wire=path([[0,0],[5000,0]]);self.c['shapes']=[a,b,wire];return a,b,wire

    def test_move_retargets_attached_lead_and_exact_undo_redo(self):
        a,b,w=self.pair();h=History(self.p);before=partition(self.p,self.cid)
        for offset in (1000,-500,1500):
            old=clone(h.project['cells']);h.commit(lambda p:move(p,self.cid,[b['id']],0,offset),'Connected move')
            after=clone(h.project['cells']);self.assertEqual(before,partition(h.project,self.cid))
            h.undo();self.assertEqual(old,h.project['cells']);h.redo();self.assertEqual(after,h.project['cells'])
        points=h.project['cells'][0]['shapes'][2]['points']
        self.assertEqual((points[0],points[-1]),([0,0],[5000,2000]));self.assertEqual(len(points),3)

    def test_move_rejects_short_and_spacing_atomically(self):
        a,b,w=self.pair();self.c['shapes'].append(rect('metal1',4700,1700,600,600,net='other'));old=clone(self.p)
        with self.assertRaisesRegex(ValueError,'join or separate'):move(self.p,self.cid,[b['id']],0,2000)
        self.assertEqual(old,self.p)
        with self.assertRaisesRegex(ValueError,'spacing'):move(self.p,self.cid,[b['id']],0,1300)
        self.assertEqual(old,self.p)

    def test_locked_attached_wire_rejects_move(self):
        a,b,w=self.pair()
        with self.assertRaisesRegex(ValueError,'Unlock'):move(self.p,self.cid,[b['id']],0,1000,['metal1'])

    def test_hierarchy_spacing_checks_each_conductor_inside_an_instance(self):
        child={'id':uid(),'name':'child','ports':[],'devices':[],'shapes':[rect('metal1',0,0,600,600,net='a'),rect('metal1',2000,0,600,600,net='b')]}
        self.p['cells'].append(child);instance={'id':uid(),'name':'I1','cell':child['id'],'x':0,'y':0};self.c['layout_instances']=[instance]
        self.c['shapes']=[rect('metal1',2000,2000,600,600,net='c')];before=clone(self.p)
        with self.assertRaisesRegex(ValueError,'spacing'):move(self.p,self.cid,[instance['id']],0,1300)
        self.assertEqual(self.p,before)

    def test_connected_stretch_retains_both_terminals_and_branch(self):
        a,b,w=self.pair();branch=path([[2500,0],[2500,-3000]]);self.c['shapes'].append(branch)
        before=partition(self.p,self.cid);stretch(self.p,self.cid,w['id'],0,1000)
        after=partition(self.p,self.cid)
        self.assertTrue(all(after[key]&set(before)==group for key,group in before.items()))
        route=next(s for s in self.c['shapes'] if s['id']==w['id'])
        self.assertEqual(route['points'],[[0,0],[0,1000],[5000,1000],[5000,0]])
        self.assertTrue(any(s.get('connected_lead')==w['id'] for s in self.c['shapes']))

    def test_stretch_rejects_other_net_and_retains_document(self):
        a,b,w=self.pair();self.c['shapes'].append(rect('metal1',2000,700,1000,600,net='b'));old=clone(self.p)
        with self.assertRaises(ValueError):stretch(self.p,self.cid,w['id'],0,1000)
        self.assertEqual(old,self.p)

    def test_repeated_branch_stretches_reuse_the_same_lead(self):
        a,b,w=self.pair();self.c['shapes'].append(path([[2500,0],[2500,-3000]]))
        stretch(self.p,self.cid,w['id'],0,1000);lead=next(s['id'] for s in self.c['shapes'] if s.get('connected_lead'))
        for offset in (1000,-500,1000):stretch(self.p,self.cid,w['id'],1,offset)
        leads=[s for s in self.c['shapes'] if s.get('connected_lead')]
        self.assertEqual(len(leads),1);self.assertEqual(leads[0]['id'],lead);self.assertEqual(leads[0]['points'],[[2500,0],[2500,2500]])

    def test_parametric_terminals_follow_complete_footprint(self):
        from icstudio.parametric import install as generate
        d=device('R','R1',value='100');self.c['devices']=[d]
        r=generate(self.p,self.cid,d['id'],{'width':1000});pins=clone(self.c['layout_pins'])
        ids=[s['id'] for s in self.c['shapes']];move(self.p,self.cid,ids,2000,3000)
        self.assertEqual([v['point'] for v in self.c['layout_pins']],[[v['point'][0]+2000,v['point'][1]+3000] for v in pins])
        before=clone(self.p)
        with self.assertRaisesRegex(ValueError,'complete'):move(self.p,self.cid,ids[:1],1000,0)
        self.assertEqual(before,self.p)

    def test_instance_move_retargets_parent_and_preserves_child(self):
        from icstudio.physical_cells import place
        child={'id':uid(),'name':'child','ports':['a'],'devices':[],'shapes':[rect('metal1',-300,-300,600,600,net='a')],
               'layout_ports':[{'name':'a','layer':'metal1','point':[0,0]}]}
        self.p['cells'].append(child);d=device('X','X1',cell=child['id'],nets={'a':'a'});self.c['devices']=[d]
        instance=place(self.p,self.cid,d['id'],5000,0);self.c['shapes']=[path([[0,0],[5000,0]])];saved=clone(child)
        move(self.p,self.cid,[instance['id']],0,1000);self.assertEqual(saved,self.p['cells'][1])
        self.assertEqual(self.c['shapes'][0]['points'][-1],[5000,1000])


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.p=example('empty');self.c=self.p['cells'][0];self.cid=self.c['id']
    def endpoint(self,point,layer='metal1'):return {'point':point,'layer':layer}
    def test_multilayer_transition_and_stale_proposal(self):
        r=plan(self.p,self.cid,self.endpoint([0,0]),self.endpoint([5000,0],'metal2'),'a',400)
        self.assertEqual(r['via_count'],1);self.assertEqual(r['length_nm'],5000)
        ids=install(self.p,r);groups=partition(self.p,self.cid)
        self.assertTrue(all(len(group)==len(ids) for group in groups.values()))
        old=clone(self.p)
        with self.assertRaisesRegex(ValueError,'changed'):install(self.p,r)
        self.assertEqual(self.p,old)

    def test_router_escapes_two_bend_limit_and_avoids_all_obstacles(self):
        self.c['shapes']=[rect('metal1',x,-5000 if i%2 else -2000,500,7000,net='block') for i,x in enumerate((2000,4500,7000))]
        r=plan(self.p,self.cid,self.endpoint([0,0]),self.endpoint([9500,0]),'a',400,layers=['metal1'],margin=3000)
        self.assertGreater(len(r['shapes'][0]['points']),4)
        self.assertTrue(all(Geometry(self.p,self.cid,'a').clear(s) for s in r['shapes']))

    def test_router_can_cross_blockage_on_second_layer(self):
        self.c['shapes']=[rect('metal1',2000,-20000,1000,40000,net='b')]
        r=plan(self.p,self.cid,self.endpoint([0,0]),self.endpoint([5000,0]),'a',400,margin=2000)
        self.assertEqual(r['via_count'],2);self.assertTrue(any(s['layer']=='metal2' and s['kind']=='path' for s in r['shapes']))

    def test_via_cut_obstacle_and_locks_are_respected(self):
        self.c['shapes']=[rect('via1',-200,-200,400,400,net='b')]
        r=plan(self.p,self.cid,self.endpoint([0,0]),self.endpoint([5000,0],'metal2'),'a',400)
        self.assertTrue(all(Geometry(self.p,self.cid,'a').clear(s) for s in r['shapes']))
        with self.assertRaisesRegex(ValueError,'No clear route'):plan(self.p,self.cid,self.endpoint([0,0]),self.endpoint([0,0],'metal2'),'a',400,locked=['via1'])

    def test_cancellation_and_search_budget_leave_project_unchanged(self):
        old=clone(self.p)
        with self.assertRaises(RoutingCancelled):plan(self.p,self.cid,self.endpoint([0,0]),self.endpoint([5000,0]),'a',400,cancelled=lambda:True)
        with self.assertRaisesRegex(ValueError,'budget'):plan(self.p,self.cid,self.endpoint([0,0]),self.endpoint([5000,0]),'a',400,max_nodes=1)
        self.assertEqual(self.p,old)

    def test_matched_pair_tunes_shorter_path_in_clear_corridor(self):
        r=matched_pair(self.p,self.cid,[self.endpoint([0,0]),self.endpoint([0,5000])],
                       [self.endpoint([5000,0]),self.endpoint([7000,5000])],['a','b'],400,layers=['metal1'])
        self.assertEqual(r['lengths_nm'],[7000,7000]);self.assertEqual(r['skew_nm'],0);install(self.p,r)
        self.assertEqual(len(set(partition(self.p,self.cid).values())),2)

    def test_shields_have_physical_ground_ties(self):
        s=path([[0,0],[5000,0]]);self.c['shapes']=[s,rect('metal2',-3300,-300,600,600,net='0')]
        r=shield(self.p,self.cid,s['id'],self.endpoint([-3000,0],'metal2'))
        ids=install(self.p,r);groups=partition(self.p,self.cid)
        self.assertEqual(len(set(groups.values())),2)
        ground_group=groups[('shape',ids[0],'','')];self.assertTrue(all(('shape',i,'','') in ground_group for i in ids))

    def test_shield_rejects_floating_reference_and_pair_rejects_self_overlap(self):
        s=path([[0,0],[5000,0]]);self.c['shapes']=[s];old=clone(self.p)
        with self.assertRaisesRegex(ValueError,'existing conductor'):shield(self.p,self.cid,s['id'],self.endpoint([-3000,0],'metal2'))
        self.c['shapes']=[]
        with self.assertRaisesRegex(ValueError,'narrower'):matched_pair(self.p,self.cid,
            [self.endpoint([0,0]),self.endpoint([0,5000])],[self.endpoint([5000,0]),self.endpoint([5100,5000])],['a','b'],400,layers=['metal1'])

    def test_process_vias_still_require_locked_assets(self):
        from icstudio.analog import reference
        from icstudio.analog_layout import generate_mirror
        from test_silicon import technology
        p,cid,_=reference(technology());generate_mirror(p,cid);old=clone(p)
        with self.assertRaisesRegex(ValueError,'PDK lock'):plan(p,cid,self.endpoint([30000,30000],'m1'),self.endpoint([35000,30000],'m2'),'test',400,layers=['m1','m2'])
        self.assertEqual(old,p)


class PCellLibraryTests(unittest.TestCase):
    def setUp(self):
        from icstudio.pcell_library import register
        self.p=example('empty')
        self.definition=json.loads((Path(__file__).resolve().parents[1]/'examples/pcells/metal_comb.json').read_text())
        register(self.p,self.definition)

    def test_parametric_repetition_roles_and_stable_regeneration(self):
        from icstudio.pcell_library import create_cell,regenerate,audit
        cid=create_cell(self.p,'comb','metal_comb',{});c=self.p['cells'][-1];ids=[s['id'] for s in c['shapes']]
        h=History(self.p);h.commit(lambda p:regenerate(p,cid,{'height':5000}),'Regenerate')
        self.assertEqual(ids,[s['id'] for s in h.project['cells'][-1]['shapes']]);self.assertEqual(audit(h.project)[0]['state'],'Current')
        h.undo();self.assertEqual(h.project['cells'],self.p['cells'])

    def test_invalid_parameters_and_unsafe_expressions_reject_atomically(self):
        from icstudio.pcell_library import create_cell,register
        before=clone(self.p)
        for values in ({'height':1001},{'fingers':2000},{'unknown':3}):
            with self.subTest(values=values),self.assertRaises(ValueError):create_cell(self.p,'bad','metal_comb',values)
        for expression in ('{__import__("os").getcwd()}','{height / 0}','{height ** 4000}'):
            bad=clone(self.definition);bad['shapes'][0]['height']=expression
            with self.subTest(expression=expression),self.assertRaises(ValueError):register(self.p,bad)
        self.assertEqual(before,self.p)

    def test_definition_update_and_manual_geometry_have_distinct_stale_states(self):
        from icstudio.pcell_library import create_cell,register,regenerate,audit
        cid=create_cell(self.p,'comb','metal_comb',{});definition=clone(self.definition);definition['revision']='2';register(self.p,definition)
        self.assertEqual(audit(self.p)[0]['state'],'Definition changed');regenerate(self.p,cid,{})
        self.p['cells'][-1]['shapes'][0]['points'][1][1]+=500
        self.assertEqual(audit(self.p)[0]['state'],'Geometry edited');old=clone(self.p)
        with self.assertRaisesRegex(ValueError,'edited'):regenerate(self.p,cid,{})
        self.assertEqual(old,self.p)

    def test_parent_route_disconnect_blocks_regeneration(self):
        from icstudio.pcell_library import create_cell,regenerate
        cid=create_cell(self.p,'comb','metal_comb',{});c=self.p['cells'][0]
        c['layout_instances']=[{'id':uid(),'name':'I1','cell':cid,'x':0,'y':0}]
        c['shapes']=[path([[200,3500],[-3000,3500]])];old=clone(self.p)
        with self.assertRaisesRegex(ValueError,'join or separate'):regenerate(self.p,cid,{'height':2000})
        self.assertEqual(old,self.p)

    def test_project_serialization_keeps_library_and_regeneration(self):
        from icstudio.pcell_library import create_cell,regenerate,audit
        cid=create_cell(self.p,'comb','metal_comb',{})
        restored=validate(json.loads(json.dumps(self.p)));regenerate(restored,cid,{'fingers':6})
        self.assertEqual(len(restored['cells'][-1]['shapes']),7);self.assertEqual(audit(restored)[0]['state'],'Current')


class InspectionTests(unittest.TestCase):
    def setUp(self):self.p=example('empty');self.c=self.p['cells'][0];self.cid=self.c['id']

    def test_query_preserves_array_instance_paths_and_truncation(self):
        from icstudio.layout_inspection import query
        child={'id':uid(),'name':'child','ports':[],'devices':[],'shapes':[rect('metal1',0,0,1000,1000,net='a')]}
        self.p['cells'].append(child);self.c['layout_instances']=[{'id':uid(),'name':'I1','cell':child['id'],'x':0,'y':0,'nx':3,'ny':1,'a':[2000,0]}]
        r=query(self.p,self.cid,layer='metal1',limit=2)
        self.assertEqual(r['total'],3);self.assertTrue(r['truncated']);self.assertNotEqual(r['rows'][0]['instance_path'],r['rows'][1]['instance_path'])
        self.assertEqual(query(self.p,self.cid,box=[3500,-500,5500,1500])['total'],1)

    def test_density_merges_overlap_and_clips_edge_tiles(self):
        from icstudio.layout_inspection import density
        self.c['shapes']=[rect('metal1',0,0,1000,1000),rect('metal1',0,0,1000,1000)]
        r=density(self.p,self.cid,'metal1',[0,0,1500,1000],1000)
        self.assertEqual([v['density'] for v in r['rows']],[1,0]);self.assertEqual(r['maximum'],1)

    def test_fill_obeys_all_layer_keepout_and_undo(self):
        from icstudio.layout_inspection import fill
        self.c['shapes']=[rect('active',0,0,3000,3000)];h=History(self.p)
        h.commit(lambda p:fill(p,self.cid,'metal1',[0,0,10000,10000]),'Fill')
        obstacle=kdb().Region(polygon(self.c['shapes'][0])).sized(1000)
        added=h.project['cells'][0]['shapes'][1:];self.assertTrue(added)
        self.assertTrue(all((kdb().Region(polygon(s))&obstacle).is_empty() for s in added))
        h.undo();self.assertEqual(h.project['cells'],self.p['cells'])

    def test_rounding_grid_identity_and_connection_rejection(self):
        from icstudio.layout_inspection import round_corners
        s=rect('metal1',0,0,2000,2000,net='a');self.c['shapes']=[s]
        round_corners(self.p,self.cid,[s['id']],0,400)
        shaped=self.c['shapes'][0];self.assertEqual(shaped['id'],s['id']);self.assertLess(polygon(shaped).area(),4000000)
        self.assertTrue(all(v%5==0 for pt in shaped['points'] for v in pt))
        self.c['ports']=['a'];self.c['layout_ports']=[{'name':'a','layer':'metal1','point':[5,5]}]
        # Restore a square with a terminal at its corner, then reject its removal.
        self.c['shapes']=[clone(s)];before=clone(self.p)
        with self.assertRaisesRegex(ValueError,'join or separate'):round_corners(self.p,self.cid,[s['id']],0,400)
        self.assertEqual(before,self.p)

    def write_layout(self,path,dbu=.001,size=1000,datatype=0,extra=0):
        db=kdb();ly=db.Layout();ly.dbu=dbu;top=ly.create_cell('top');layer=ly.layer(7,datatype)
        top.shapes(layer).insert(db.Box(0,0,size,size))
        for i in range(extra):
            child=ly.create_cell('cell'+str(i));child.shapes(layer).insert(db.Box(0,0,size,size));top.insert(db.CellInstArray(child.cell_index(),db.Trans((i+1)*size*2,0)))
        ly.write(str(path))

    def test_gds_oasis_xor_normalizes_units_and_reports_exact_area(self):
        from icstudio.layout_inspection import compare_files
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a.gds';b=Path(tmp)/'b.oas';self.write_layout(a);self.write_layout(b,.0005,2000)
            r=compare_files(a,b);self.assertTrue(r['equal_geometry']);self.assertEqual(r['comparison_dbu_um'],.0005)
            self.write_layout(b,.001,2000);r=compare_files(a,b)
            self.assertFalse(r['equal_geometry']);self.assertAlmostEqual(sum(l['added_um2'] for l in r['layers']),3)

    def test_comparison_handles_more_than_100_cells_and_enforces_budget(self):
        from icstudio.layout_inspection import compare_files
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a.gds';b=Path(tmp)/'b.gds';self.write_layout(a,extra=120);self.write_layout(b,extra=120)
            r=compare_files(a,b);self.assertTrue(r['equal_geometry']);self.assertEqual(r['expanded_shapes'],[121,121])
            with self.assertRaisesRegex(ValueError,'budget'):compare_files(a,b,max_shapes=50)
            with self.assertRaises(InterruptedError):compare_files(a,b,cancelled=lambda:True)

    def test_comparison_keeps_layer_datatypes_separate(self):
        from icstudio.layout_inspection import compare_files
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a.gds';b=Path(tmp)/'b.gds';self.write_layout(a,datatype=0);self.write_layout(b,datatype=1)
            r=compare_files(a,b,limit=1);self.assertFalse(r['equal_geometry']);self.assertEqual(r['total'],2);self.assertTrue(r['truncated'])

    def test_comparison_replay_uses_hashed_reference_after_source_deletion(self):
        from icstudio.layout_jobs import run,replay_job
        from icstudio.model import file_digest
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.gds';self.write_layout(source)
            work=root/'first';work.mkdir();settings={'type':'layout_compare','reference':str(source),'reference_sha256':file_digest(source)}
            job={'project':clone(self.p),'cell':self.cid,'engine':'builtin','settings':settings}
            result=run(self.p,self.cid,settings,work);source.unlink()
            row={'job':job,'result':result,'path':work};replay=replay_job(row);other=root/'second';other.mkdir()
            rerun=run(self.p,self.cid,replay['settings'],other)
            self.assertEqual(result['layout_comparison']['layers'],rerun['layout_comparison']['layers'])
            (work/result['reference_snapshot_file']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'missing or changed'):replay_job(row)


class RuleBundleTests(unittest.TestCase):
    def test_verification_job_uses_captured_entry_directory_and_records_hashes(self):
        from unittest.mock import patch
        from icstudio.rule_bundle import capture
        from icstudio.klayout_verification import run
        from icstudio.model import digest,file_digest
        import klayout.rdb as rdb
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir();entry=source/'main.drc';entry.write_text("load './helper.rb'\n")
            (source/'helper.rb').write_text('width = 0.14\n');bundle=capture(entry);executable=root/'test-engine';executable.write_text('synthetic engine identity')
            p=example('empty');settings={'runset_text':entry.read_text(),'runset_hash':digest(entry.read_text()),'rule_bundle':bundle,'bundle_hash':digest(bundle),
                'executable':str(executable),'executable_sha256':file_digest(executable)}
            entry.unlink();(source/'helper.rb').unlink()
            def execute(args,cwd,**kwargs):
                self.assertEqual((Path(cwd)/'helper.rb').read_text(),'width = 0.14\n')
                self.assertEqual(Path(args[3]).name,'main.drc')
                report=rdb.ReportDatabase('Synthetic adapter test');report.top_cell_name='top';report.save(str(root/'run/findings.lyrdb'))
                return 'synthetic execution boundary\n'
            with patch('icstudio.engines.execute',side_effect=execute):result=run(p,p['top'],settings,root/'run')
            self.assertEqual(result['settings']['bundle_hash'],digest(bundle));self.assertEqual(result['klayout_report']['count'],0)
            manifest=json.loads((root/'run/rule-bundle.json').read_text());self.assertEqual(manifest['sha256'],digest(bundle))

    def test_capture_survives_source_deletion_with_exact_helpers(self):
        from icstudio.rule_bundle import capture,materialize
        from icstudio.model import digest
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';source.mkdir();(source/'helpers').mkdir()
            entry=source/'main.drc';entry.write_text("load './helpers/width.rb'\n")
            (source/'helpers/width.rb').write_text('width = 0.14\n');bundle=capture(entry)
            entry.unlink();(source/'helpers/width.rb').unlink()
            restored=materialize(bundle,digest(bundle),Path(tmp)/'run')
            self.assertEqual(restored.read_text(),"load './helpers/width.rb'\n")
            self.assertEqual((restored.parent/'helpers/width.rb').read_text(),'width = 0.14\n')

    def test_traversal_stale_content_and_symlinks_rejected(self):
        from icstudio.rule_bundle import capture,materialize
        from icstudio.model import digest
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bundle={'version':1,'entry':'../escape.drc','files':{'../escape.drc':'bad'}}
            with self.assertRaisesRegex(ValueError,'paths'):materialize(bundle,digest(bundle),root/'run')
            good={'version':1,'entry':'main.drc','files':{'main.drc':'old'}};expected=digest(good);good['files']['main.drc']='new'
            with self.assertRaisesRegex(ValueError,'changed'):materialize(good,expected,root/'run')
            (root/'main.drc').write_text('ok');(root/'link.rb').symlink_to(root/'main.drc')
            with self.assertRaisesRegex(ValueError,'symbolic'):capture(root/'main.drc')
            self.assertFalse((root/'run').exists())


if __name__=='__main__':unittest.main()
