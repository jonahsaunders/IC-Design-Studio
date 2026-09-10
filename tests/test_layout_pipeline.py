"""Correctness gates for bounded edits, local checks and hierarchical queries."""
import tempfile
import unittest
from pathlib import Path
from icstudio.model import example,clone,History,validate
from icstudio.layout import rect,polygon,drc
from icstudio.layout_topology import partition,move
from icstudio.layout_graph import GeometryGraph,IncrementalDRC
from icstudio.live_geometry import check_enclosures,IncrementalChecks,full
from icstudio.layout_scene import LayoutScene
from icstudio.design_ops import flatten_layout
from icstudio import recovery


def findings(rows):
    return sorted((v['code'],v['object'],v['message'],tuple(v.get('bbox') or ())) for v in rows)


def flat(count=100):
    p=example('empty');p['cells'][0]['shapes']=[rect('metal1',i*1000,0,600,600) for i in range(count)];return p


class LocalTransactions(unittest.TestCase):
    def test_shared_branches_exact_history_and_dirty_count(self):
        p=flat();h=History(p);old=h.project;cid=p['top'];sid=p['cells'][0]['shapes'][0]['id']
        self.assertTrue(h.commit_layout_move(cid,[sid],5,0));after=h.project
        self.assertIs(old['cells'][0]['shapes'][5],after['cells'][0]['shapes'][5]);self.assertIs(old['pdk'],after['pdk'])
        self.assertEqual(h.layout_stats['polygons_built'],1);self.assertEqual(h.layout_stats['shapes_replaced'],1)
        self.assertEqual(old['cells'],p['cells']);validate(after)
        h.undo();self.assertEqual(h.project['cells'],old['cells']);h.redo();self.assertEqual(h.project['cells'],after['cells'])
        self.assertTrue(h.commit_layout_move(cid,[sid],5,0));self.assertEqual(h.layout_stats['polygons_built'],1)

    def test_attached_leads_match_existing_solver(self):
        p=flat(2);c=p['cells'][0];c['shapes'][1]['points']=[[4700,0],[5300,600]]
        c['shapes'].append({'id':'lead','kind':'path','layer':'metal1','width':400,'points':[[300,300],[5000,300]],'net':''})
        h=History(p);expected=clone(p);sid=c['shapes'][0]['id'];move(expected,p['top'],[sid],0,1000)
        self.assertTrue(h.commit_layout_move(p['top'],[sid],0,1000));self.assertEqual(h.project['cells'],expected['cells'])
        self.assertEqual(partition(h.project,p['top']),partition(p,p['top']))

    def test_failures_are_atomic(self):
        p=flat(2);sid=p['cells'][0]['shapes'][0]['id'];h=History(p);old=h.project
        for dx,dy,locked in ((1000,0,()),(250,0,()),(1,0,()),(2**31,0,()),(5,0,('metal1',))):
            with self.assertRaises(ValueError):h.commit_layout_move(p['top'],[sid],dx,dy,locked)
            self.assertIs(h.project,old);self.assertFalse(h.undo_stack)
        self.assertTrue(h.commit_layout_move(p['top'],[sid],-5,0))

    def test_terminal_cannot_be_left_behind(self):
        p=flat(1);c=p['cells'][0];c['ports']=['p'];c['layout_ports']=[{'name':'p','layer':'metal1','point':[300,300]}]
        h=History(p)
        with self.assertRaises(ValueError):h.commit_layout_move(p['top'],[c['shapes'][0]['id']],1000,0)

    def test_complete_via_group_uses_constrained_transaction(self):
        p=flat(1);c=p['cells'][0];c['shapes'][0]['via_group']='v';h=History(p)
        self.assertTrue(h.commit_layout_move(p['top'],[c['shapes'][0]['id']],5,0));self.assertTrue(h.undo_stack)
        h.undo();self.assertEqual(h.project['cells'],p['cells'])

    def test_generic_transaction_after_local_edit_is_isolated(self):
        p=flat(2);h=History(p);h.commit_layout_move(p['top'],[p['cells'][0]['shapes'][0]['id']],5,0);old=h.project
        def broken(q):q['cells'][0]['shapes'][1]['points'][0][0]='bad'
        with self.assertRaises(ValueError):h.commit(broken)
        self.assertIs(h.project,old);self.assertEqual(old['cells'][0]['shapes'][1]['points'][0][0],1000)


class LocalChecks(unittest.TestCase):
    def test_contact_joins_splits_removal_and_vias(self):
        p=flat(3);c=p['cells'][0];graph=GeometryGraph()
        for action in ('initial','join','split','via','delete'):
            if action=='join':c['shapes'].append(rect('metal1',500,0,1800,400))
            if action=='split':c['shapes'][-1]['points']=[[9000,0],[9500,400]]
            if action=='via':c['shapes'] += [rect('via1',100,100,200,200),rect('metal2',0,0,600,600)]
            if action=='delete':del c['shapes'][0]
            graph.sync(c['shapes'],p['pdk']);self.assertEqual(graph.partition(p,p['top']),partition(p,p['top']),action)
        graph.sync(c['shapes'],p['pdk']);self.assertEqual(graph.stats['polygons_built'],0)

    def test_local_drc_matches_full_through_component_splits(self):
        p=flat(8);c=p['cells'][0];cache=IncrementalDRC()
        for step in range(6):
            if step==1:c['shapes'][0]['points']=[[0,0],[100,600]]
            if step==2:c['shapes'].append(rect('metal1',500,0,6800,300))
            if step==3:del c['shapes'][-1]
            if step==4:c['shapes'][0]['points']=[[0,0],[600,600]]
            if step==5:p['pdk']['layers'][3]['width']=650
            p['revision']+=1
            self.assertEqual(findings(cache.check(p,p['top'],c['shapes'])),findings(drc(p,p['top'])+check_enclosures(p,p['top'],c['shapes'])),step)

    def test_enclosure_and_rule_change_invalidation(self):
        p=flat(2);c=p['cells'][0];c['shapes'].append(rect('via1',100,100,150,150));p['pdk']['enclosures']=[{'cut':'via1','conductor':'metal1','minimum':100}]
        cache=IncrementalDRC()
        for minimum in (100,400,50):
            p['pdk']['enclosures'][0]['minimum']=minimum
            self.assertEqual(findings(cache.check(p,p['top'],c['shapes'])),findings(drc(p,p['top'])+check_enclosures(p,p['top'],c['shapes'])))

    def test_dirty_check_keeps_whole_polygon_and_reuses_far_results(self):
        p=flat(100);c=p['cells'][0];cache=IncrementalChecks();cache.check(p,p['top'])
        c['shapes'][0]['points']=[[0,0],[100,600]];p['revision']+=1
        result=cache.check(p,p['top']);self.assertTrue(result['incremental']);self.assertEqual(result['stats']['drc']['shapes_checked'],1)
        self.assertEqual(result['stats']['contacts']['polygons_built'],1)
        self.assertEqual(findings(result['issues']),findings(full(p,p['top'])['issues']))

    def test_large_connected_component_has_one_shared_partition(self):
        p=flat(300);c=p['cells'][0]
        for i,s in enumerate(c['shapes']):s['points']=[[i*500,0],[i*500+600,600]]
        g=GeometryGraph().sync(c['shapes'],p['pdk']);result=g.partition(p,p['top'])
        self.assertEqual(len(set(map(id,result.values()))),1);self.assertEqual(len(next(iter(result.values()))),300)


class RecoverySnapshots(unittest.TestCase):
    def test_validated_edit_is_durable_and_previous_tampering_is_detected(self):
        p=flat(3);h=History(p)
        with tempfile.TemporaryDirectory() as directory:
            path=recovery.write(h.project,directory);original=path.read_bytes()
            h.commit_layout_move(p['top'],[p['cells'][0]['shapes'][0]['id']],5,0)
            recovery.write(h.project,directory,validated=True);previous=path.with_suffix('.previous.icproj');self.assertEqual(previous.read_bytes(),original)
            path.write_text('{corrupted');h.commit_layout_move(p['top'],[p['cells'][0]['shapes'][0]['id']],5,0)
            recovery.write(h.project,directory,validated=True);self.assertEqual(previous.read_bytes(),original)
            restored,fallback=recovery.read(path);self.assertFalse(fallback);self.assertEqual(restored,h.project)
            path.write_text('interrupted');restored,fallback=recovery.read(path);self.assertTrue(fallback);self.assertEqual(restored,p)
            recovery.clear(path);self.assertFalse(list(Path(directory).iterdir()))


class HierarchicalScene(unittest.TestCase):
    def fixture(self):
        p=flat(1);c=p['cells'][0];c['shapes']=[]
        tile={'id':'tile','name':'tile','ports':[],'devices':[],'shapes':[rect('metal1',0,0,600,400),{'id':'hole','kind':'polygon','layer':'metal2','points':[[800,0],[1400,0],[1400,600],[800,600]],'holes':[[[900,100],[1300,100],[1300,500],[900,500]]],'net':'n'}]}
        p['cells'].append(tile);c['layout_instances']=[{'id':'array','name':'array','cell':'tile','x':-3000,'y':-4000,'rotation':90,'mirror':True,'nx':4,'ny':3,'a':[2000,500],'b':[-100,2000]}];return p

    def test_native_query_matches_flattened_geometry_and_identity(self):
        p=self.fixture();scene=LayoutScene().update(p,p['top']);expected=flatten_layout(p,p['top']);actual=scene.query((-100000,-100000,100000,100000))
        def rows(shapes):return [(s['id'],s.get('source_id'),s.get('instance_path'),s.get('net',''),polygon(s).to_s()) for s in shapes]
        self.assertEqual(rows(actual),rows(expected));self.assertEqual(scene.expanded_count,len(expected))
        self.assertEqual(scene.stats['master_shapes'],2)

    def test_sparse_window_and_master_invalidation(self):
        p=self.fixture();inst=p['cells'][0]['layout_instances'][0];inst.update(nx=100,ny=100,a=[2000,0],b=[0,2000],rotation=0,mirror=False,x=0,y=0)
        scene=LayoutScene().update(p,p['top']);scene.query((0,0,600,400));self.assertEqual(len(scene.query((100,100,200,200))),1);self.assertLess(scene.stats['query_rows'],20);self.assertEqual(scene.expanded_count,20000)
        scene.update(p,p['top']);self.assertEqual(scene.stats['masters_rebuilt'],0)
        p['cells'][1]['shapes'][0]['points'][1][0]+=5;scene.update(p,p['top']);self.assertEqual(scene.stats['masters_rebuilt'],1)
        self.assertEqual(scene.query((0,0,600,400))[0]['points'][1][0],605)

    def test_nested_net_mapping_and_array_paths(self):
        from icstudio.model import device
        p=self.fixture();top,tile=p['cells'];tile['ports']=['p'];tile['shapes'][1]['net']='p'
        middle={'id':'middle','name':'middle','ports':['p'],'devices':[device('X','Xchild',cell='tile',nets={'p':'p'})],'shapes':[]}
        middle['layout_instances']=[{'id':'inner','name':'inner','cell':'tile','device_id':middle['devices'][0]['id'],'x':200,'y':300,'rotation':270,'mirror':True,'nx':2,'ny':1,'a':[-2000,500],'b':[0,0]}]
        top['devices']=[device('X','Xmid',cell='middle',nets={'p':'signal'})];top['layout_instances'][0].update(cell='middle',device_id=top['devices'][0]['id']);p['cells'].append(middle);validate(p)
        actual=LayoutScene().update(p,p['top']).query((-100000,-100000,100000,100000));expected=flatten_layout(p,p['top'])
        def rows(shapes):return [(s['id'],s.get('source_id'),s.get('instance_path'),s.get('device_id'),s.get('net'),polygon(s).to_s()) for s in shapes]
        self.assertEqual(rows(actual),rows(expected))

    def test_large_overview_is_bounded_and_zoom_query_stays_exact(self):
        p=self.fixture();p['cells'][0]['layout_instances'][0].update(nx=1000,ny=1000,a=[2000,0],b=[0,2000],rotation=0,mirror=False,x=0,y=0)
        validate(p);scene=LayoutScene().update(p,p['top'])
        self.assertEqual(scene.expanded_count,2000000);self.assertEqual(scene.stats['master_shapes'],2)
        rows=scene.query((-1,-1,2000000,2000000),render=True)
        self.assertTrue(rows[0]['_overview']);self.assertTrue(scene.stats['detail_reduced']);self.assertEqual(scene.stats['query_rows'],12000)
        rows=scene.query((10,10,100,100),cache=False)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['instance_path'],'array[0,0]/');self.assertTrue(scene.stats['detail_reduced'])
        scene.query((10,10,100,100),render=True);self.assertFalse(scene.stats['detail_reduced'])

    def test_depth_and_hierarchy_full_check_fallback(self):
        p=self.fixture();scene=LayoutScene().update(p,p['top'],0);self.assertEqual(scene.expanded_count,0);self.assertEqual(scene.query((-10000,-10000,10000,10000)),[])
        result=IncrementalChecks().check(p,p['top']);self.assertFalse(result['incremental']);self.assertEqual(findings(result['issues']),findings(full(p,p['top'])['issues']))


if __name__=='__main__':unittest.main()
