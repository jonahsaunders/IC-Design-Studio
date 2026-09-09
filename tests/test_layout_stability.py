"""Storage failure containment and optimized geometry equivalence regressions."""
import errno
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.model import atomic_write,example,clone,History
from icstudio.layout import rect,polygon
from icstudio.layout_index import LayoutBoxIndex
from icstudio.layout_cache import DeferredPath,geometry_key
from icstudio.layout_graph import GeometryGraph
from icstudio.layout_topology import partition
from icstudio.layout_arrange import arrange


class StorageFailureTests(unittest.TestCase):
    def test_sync_failure_retains_previous_destination_and_errno(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'design.icproj';path.write_bytes(b'previous saved project')
            with patch('os.fsync',side_effect=OSError(errno.EIO,'injected synchronization failure')) as sync:
                with self.assertRaises(OSError) as caught:atomic_write(path,b'new candidate')
            self.assertEqual(sync.call_count,1)
            self.assertEqual(caught.exception.errno,errno.EIO)
            self.assertEqual(caught.exception.filename,str(path))
            self.assertIn('synchronize',str(caught.exception))
            self.assertEqual(path.read_bytes(),b'previous saved project')
            self.assertEqual(list(Path(directory).iterdir()),[path])

    def test_no_new_destination_is_published_after_sync_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'new.icproj'
            with patch('os.fsync',side_effect=OSError(errno.ENOSPC,'injected full device')):
                with self.assertRaises(OSError) as caught:atomic_write(path,'new candidate')
            self.assertEqual(caught.exception.errno,errno.ENOSPC)
            self.assertFalse(path.exists());self.assertFalse(list(Path(directory).iterdir()))


class NativeIndexTests(unittest.TestCase):
    def test_point_pick_shrinks_an_overview_cache(self):
        from icstudio.layout_scene import LayoutScene
        p=example('empty');c=p['cells'][0]
        p['cells'].append({'id':'tile','name':'tile','ports':[],'devices':[],'shapes':[rect('metal1',0,0,600,600)]})
        c['layout_instances']=[{'id':'array','name':'array','cell':'tile','x':0,'y':0,'nx':100,'ny':100,'a':[1000,0],'b':[0,1000]}]
        scene=LayoutScene().update(p,c['id']);self.assertEqual(len(scene.query((-1,-1,100000,100000))),10000)
        hits=scene.query((300,300,300,300));self.assertEqual(len(hits),1);self.assertEqual(hits[0]['id'],'array')
        self.assertLess(scene.stats['query_rows'],20)

    def test_exact_boundary_and_zero_area_queries(self):
        rng=random.Random(779)
        entries=[((i*10-1,-1,i*10+4,4),i) for i in range(120)]
        index=LayoutBoxIndex([b for b,_ in entries])
        for q in [(5,0,8,0),(-1,-1,-1,-1)]+[(x,0,x+rng.randrange(15),4) for x in (rng.randrange(-50,1300) for _ in range(200))]:
            expected={i for b,i in entries if b[0]<=q[2] and b[2]>=q[0] and b[1]<=q[3] and b[3]>=q[1]}
            self.assertEqual(set(index.query(q)),expected)

    def test_patched_index_is_immutable_and_rebuilds_after_many_edits(self):
        bounds=tuple((i*10,0,i*10+4,4) for i in range(200));base=LayoutBoxIndex(bounds);index=base
        for step in range(45):
            current=list(index.bounds);current[step]=(-step*10-10,0,-step*10-6,4)
            previous=index;index=LayoutBoxIndex(current,index)
            self.assertEqual(previous.query((step*10,0,step*10,0)),[step])
            self.assertEqual(index.query((step*10,0,step*10,0)),[])
            self.assertEqual(index.query((-step*10-10,0,-step*10-10,0)),[step])
        self.assertIsNot(index.db,base.db);self.assertEqual(base.query((0,0,0,0)),[0])

    def test_deferred_paths_capture_geometry_before_in_place_mutation(self):
        shape=rect('metal1',0,0,600,600);calls=[]
        def build(s):calls.append(s);return polygon(s)
        delayed=DeferredPath(build,geometry_key(shape));shape['points'][0][0]=100
        self.assertEqual(calls,[]);self.assertEqual(delayed.get().bbox().left,0)
        self.assertIs(delayed.get(),delayed.get());self.assertEqual(len(calls),1)


class GraphEquivalenceTests(unittest.TestCase):
    def test_incremental_matches_fresh_graph_across_join_split_and_layer_changes(self):
        p=example('empty');c=p['cells'][0]
        c['shapes']=[rect('metal1',i*1000,0,600,600) for i in range(60)]
        graph=GeometryGraph().sync(c['shapes'],p['pdk'])
        rng=random.Random(615)
        for step in range(50):
            shapes=clone(c['shapes']);s=shapes[rng.randrange(len(shapes))]
            s['points']=[[rng.randrange(15)*1000,0],[rng.randrange(15)*1000+600,600]]
            s['layer']='metal2' if step%3==0 else 'metal1';c['shapes']=shapes
            graph.sync(shapes,p['pdk']);self.assertEqual(graph.partition(p,c['id']),partition(p,c['id']))

    def test_connected_bulk_edit_and_history_match_general_operation(self):
        p=example('empty');c=p['cells'][0];ids=[]
        for i in range(70):
            x=(i%11)*25;y=i*2000;s=rect('metal1',x,y,600,600);ids.append(s['id']);c['shapes'].append(s)
            c['shapes'].append({'id':'route'+str(i),'kind':'path','layer':'metal1','width':200,'points':[[x+600,y+300],[x+1600,y+300]]})
        before=partition(p,c['id']);expected=clone(p);arrange(expected,c['id'],ids,'left',connected=True)
        self.assertEqual(partition(expected,c['id']),before)
        h=History(p);self.assertTrue(h.commit_layout_arrange(c['id'],ids,'left',connected=True));self.assertEqual(h.project['cells'],expected['cells'])
        h.undo();self.assertEqual(h.project['cells'],p['cells']);h.redo();self.assertEqual(h.project['cells'],expected['cells'])

    def test_large_component_checks_each_undirected_contact_once(self):
        p=example('empty');shapes=[rect('metal1',i*500,0,600,600) for i in range(1200)]
        graph=GeometryGraph().sync(shapes,p['pdk'])
        self.assertEqual(graph.stats['edge_tests'],len(shapes)-1)
        moved=clone(shapes)
        for s in moved:
            for pt in s['points']:pt[1]+=5
        graph.sync(moved,p['pdk']);self.assertEqual(len(set(graph.groups.values())),1)
        self.assertEqual(graph.stats['edge_tests'],len(shapes)-1)


if __name__=='__main__':unittest.main()
