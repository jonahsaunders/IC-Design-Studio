import unittest
from icstudio.model import example, clone, uid
from icstudio.history_delta import difference
from icstudio.document import plain_geometry_change,plain_schematic_change


class GeometryRefreshTests(unittest.TestCase):
    def test_schematic_coordinates_only_and_undo_redo(self):
        from icstudio.model import History
        p=example();history=History(p);cid=p['top'];did=p['cells'][0]['devices'][0]['id']
        self.assertTrue(history.commit_schematic_transform(cid,[did],20,0))
        self.assertEqual(history.plain_schematic_change,cid)
        history.undo();self.assertEqual(history.plain_schematic_change,cid)
        history.redo();self.assertEqual(history.plain_schematic_change,cid)
        for field,value in [('value','22k'),('name','Changed'),('nets',{'p':'other','n':'0'})]:
            changed=clone(p);changed['cells'][0]['devices'][0][field]=value
            self.assertIsNone(plain_schematic_change(changed,difference(p,changed)))
        changed=clone(p);changed['cells'][0]['devices'].pop()
        self.assertIsNone(plain_schematic_change(changed,difference(p,changed)))
    def fixture(self):
        p=example('empty');p['cells'][0]['shapes']=[dict(id=uid(),layer='metal1',kind='rect',points=[[0,0],[10,10]])]
        q=clone(p);q['cells'][0]['shapes'][0]['points']=[[10,0],[20,10]]
        return p,q

    def test_only_flat_unowned_coordinate_edits_use_local_refresh(self):
        p,q=self.fixture()
        self.assertEqual(plain_geometry_change(q,difference(p,q)),dict(cell=p['cells'][0]['id'],indices=[0]))
        for key,value in [('device_id','device'),('generated_route','route'),('via_id','via'),('pcell_id','pcell')]:
            p,q=self.fixture();p['cells'][0]['shapes'][0][key]=value;q['cells'][0]['shapes'][0][key]=value
            with self.subTest(key=key):self.assertIsNone(plain_geometry_change(q,difference(p,q)))
        for key,value in [('layer','metal2'),('net','output'),('id',uid())]:
            p,q=self.fixture();q['cells'][0]['shapes'][0][key]=value
            self.assertIsNone(plain_geometry_change(q,difference(p,q)))
        p,q=self.fixture();q['cells'][0]['shapes'].append(clone(q['cells'][0]['shapes'][0]))
        self.assertIsNone(plain_geometry_change(q,difference(p,q)))

    def test_live_check_snapshot_is_isolated_from_subsequent_edits(self):
        from icstudio.physical_workspace import PhysicalCheckThread
        p,_=self.fixture();original=clone(p)
        class Checker:
            def check(self,project,cid):
                self.project=project
                return dict(issues=[],guides=[])
        checker=Checker();worker=PhysicalCheckThread(p,p['top'],None,checker)
        p['cells'][0]['shapes'][0]['points'][0][0]=900
        worker.run()
        self.assertEqual(checker.project,original)
