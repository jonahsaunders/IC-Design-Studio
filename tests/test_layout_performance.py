"""Cache correctness and transactional history regressions; no timing thresholds."""
import json
import random
import unittest
from copy import deepcopy
from icstudio.history_delta import difference,apply
from icstudio.layout_cache import LayoutGeometryCache,PatchedSpatialIndex
from icstudio.model import History,example,clone
from icstudio.layout import rect


class DeltaHistoryTests(unittest.TestCase):
    def assert_roundtrip(self,a,b):
        delta=difference(a,b);snapshot=deepcopy(delta)
        encoded=lambda v:json.dumps(v,sort_keys=True)
        self.assertEqual(encoded(apply(a,delta)),encoded(b))
        self.assertEqual(encoded(apply(b,delta,False)),encoded(a))
        self.assertEqual(delta,snapshot)

    def test_nested_edits_and_type_changes(self):
        self.assert_roundtrip({'a':[{'n':1,'x':True},None],'remove':[2]},
                              {'a':[{'n':1.0,'x':1},[]],'add':{'b':False}})

    def test_splices_and_reordering(self):
        a=[{'id':str(i),'points':[[i,0]]} for i in range(8)]
        for b in (a[:3]+a[4:],a[:3]+[{'id':'new'}]+a[3:],list(reversed(a)),[],[a[0]],a+[{'id':'tail'}]):
            with self.subTest(after=b):self.assert_roundtrip(a,b)

    def test_randomized_json_roundtrips(self):
        rng=random.Random(404)
        def tree(depth=0):
            if depth>2:return rng.choice([None,True,False,0,1,1.0,'text'])
            kind=rng.randrange(3)
            if kind==0:return [tree(depth+1) for _ in range(rng.randrange(5))]
            if kind==1:return {str(i):tree(depth+1) for i in range(rng.randrange(5))}
            return tree(3)
        for _ in range(100):self.assert_roundtrip(tree(),tree())

    def test_patch_values_do_not_alias_project_or_input(self):
        a={'a':[],'unchanged':{'x':1}};b={'a':[{'points':[[1,2]]}],'unchanged':{'x':1}}
        delta=difference(a,b);result=apply(a,delta);result['a'][0]['points'][0][0]=999
        self.assertEqual(b['a'][0]['points'][0][0],1)
        self.assertEqual(apply(a,delta)['a'][0]['points'][0][0],1)
        self.assertEqual(a['a'],[])

    def test_history_does_not_retain_unedited_shape_snapshots(self):
        p=example('empty');p['cells'][0]['shapes']=[rect('metal1',i*1000,0,400,400) for i in range(1000)]
        h=History(p)
        h.commit(lambda q:q['cells'][0]['shapes'][0]['points'][0].__setitem__(0,5))
        serialized=json.dumps(h.undo_stack)
        self.assertLess(len(serialized),2000)
        self.assertNotIn(p['cells'][0]['shapes'][-1]['id'],serialized)
        after=clone(h.project['cells']);h.undo();self.assertEqual(h.project['cells'],p['cells'])
        h.redo();self.assertEqual(h.project['cells'],after)

    def test_validation_failure_preserves_project_and_both_stacks(self):
        h=History(example('empty'));h.commit(lambda q:q.update(name='edited'));h.undo()
        before=clone(h.project);undo=deepcopy(h.undo_stack);redo=deepcopy(h.redo_stack);serial=h.serial
        with self.assertRaises(ValueError):h.commit(lambda q:q.update(top='missing'))
        self.assertEqual((h.project,h.undo_stack,h.redo_stack,h.serial),(before,undo,redo,serial))

    def test_callback_failure_is_atomic(self):
        h=History(example('empty'));before=clone(h.project)
        def bad(q):q['cells'].clear();raise RuntimeError('abort')
        with self.assertRaises(RuntimeError):h.commit(bad)
        self.assertEqual(h.project,before);self.assertFalse(h.undo_stack)

    def test_history_branch_limit_and_monotonic_revision(self):
        h=History(example('empty'))
        for i in range(105):h.commit(lambda q,i=i:q.update(name='name'+str(i)))
        self.assertEqual(len(h.undo_stack),100)
        published=clone(h.project);old=h.project
        h.undo();self.assertEqual(old,published);self.assertEqual(h.project['revision'],106)
        h.commit(lambda q:q.update(name='branch'));self.assertFalse(h.redo_stack)
        h.undo();self.assertEqual(h.project['name'],'name103')


class Box:
    def __init__(self,s):
        xs,ys=zip(*s['points']);self.values=(min(xs),min(ys),max(xs),max(ys))
    def left(self):return self.values[0]
    def top(self):return self.values[1]
    def right(self):return self.values[2]
    def bottom(self):return self.values[3]


class GeometryCacheTests(unittest.TestCase):
    def setUp(self):
        self.built=[]
        def path(s):self.built.append(s['id']);return object()
        self.cache=LayoutGeometryCache(Box,path)
        self.shapes=[{'id':str(i),'kind':'rect','layer':'metal1','points':[[i*10,0],[i*10+5,5]]} for i in range(100)]

    def test_one_edit_reuses_paths_and_spatial_tree(self):
        self.cache.update(self.shapes,1);before=list(self.cache.paths);base=self.cache.index.base
        changed=deepcopy(self.shapes);changed[20]['points'][0][0]-=2;self.built.clear();self.cache.update(changed,2)
        self.assertEqual(self.built,['20']);self.assertIs(self.cache.paths[19],before[19]);self.assertIsNot(self.cache.paths[20],before[20])
        self.assertIs(self.cache.index.base,base)
        self.assertEqual(self.cache.index.query((198,0,198,0)),[20])

    def test_revision_and_unversioned_in_place_updates(self):
        self.cache.update(self.shapes,1);self.shapes[0]['points'][0][0]=-10;self.built.clear();self.cache.update(self.shapes,2)
        self.assertEqual(self.built,['0']);self.assertEqual(self.cache.index.query((-10,0,-10,0)),[0])
        self.shapes[0]['points'][0][0]=-20;self.built.clear();self.cache.update(self.shapes)
        self.assertEqual(self.built,['0']);self.assertEqual(self.cache.index.query((-20,0,-20,0)),[0])

    def test_metadata_reorder_removal_and_layer_changes(self):
        self.cache.update(self.shapes,1);paths=list(self.cache.paths);self.built.clear()
        changed=deepcopy(list(reversed(self.shapes)));changed[0]['layer']='metal2';changed[0]['net']='a'
        self.cache.update(changed,2);self.assertEqual(self.built,[]);self.assertIs(self.cache.paths[0],paths[-1])
        self.assertEqual(self.cache.index.query((0,0,5,5)),[99])
        self.cache.update(changed[:-1],3);self.assertEqual(self.cache.index.query((0,0,5,5)),[])

    def test_hierarchy_identity_and_undo_cache(self):
        for i,s in enumerate(self.shapes):s.update(id='array',source_id='master',instance_path='array['+str(i)+']/')
        self.cache.update(self.shapes,1);paths=list(self.cache.paths)
        self.assertEqual(self.cache.selected_indices(['array']),list(range(100)))
        changed=deepcopy(self.shapes);changed[5]['points'][0][0]-=1;self.cache.update(changed,2)
        self.cache.update(self.shapes,1);self.assertIs(self.cache.paths[5],paths[5])

    def test_width_holes_and_kind_invalidate_paths(self):
        self.cache.update(self.shapes);self.built.clear()
        self.shapes[0].update(kind='path',width=10)
        self.shapes[1]['holes']=[[[10,1],[11,1],[10,2]]]
        self.cache.update(self.shapes)
        self.assertEqual(self.built,['0','1'])

    def test_spatial_updates_match_exhaustive_queries_and_rebuild(self):
        rng=random.Random(55);boxes=tuple((i*10,0,i*10+4,4) for i in range(100));index=PatchedSpatialIndex(boxes);base=index.base
        for step in range(50):
            boxes=list(boxes);i=step;dx=rng.randrange(-1000,1000);boxes[i]=(dx,-1,dx+4,4);boxes=tuple(boxes)
            index=PatchedSpatialIndex(boxes,index)
            for _ in range(10):
                x=rng.randrange(-1000,1000);q=(x,-2,x+50,5)
                expected={i for i,b in enumerate(boxes) if b[0]<=q[2] and b[2]>=q[0] and b[1]<=q[3] and b[3]>=q[1]}
                self.assertEqual(set(index.query(q)),expected)
        self.assertIsNot(index.base,base)


if __name__=='__main__':unittest.main()
