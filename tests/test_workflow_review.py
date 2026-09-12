"""Reviewer authorization, durable discussion semantics and isolated graph forks."""
import sqlite3
import tempfile
import unittest
from copy import copy
from contextlib import closing
from pathlib import Path
from icstudio.model import example, clone, uid, device
from icstudio.layout import rect
from icstudio.live_store import Store
from icstudio.live_protocol import LiveError, changes


class ReviewerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'team.sqlite3';self.key='x'*40
        self.store=Store(self.path,self.key);p=example('empty');p['cells'][0]['shapes']=[rect('metal1',0,0,500,500)]
        self.owner=self.store.create(self.key,p,'Owner');self.wid=self.owner['workspace']
        self.review=self.join('review');self.edit=self.join('edit');self.view=self.join('view')
        self.checkpoint=self.call(self.owner,'create_checkpoint',revision=0,name='Ready')['id']

    def tearDown(self):self.store.close();self.temp.cleanup()

    def join(self,role):
        inv=self.store.invite(self.wid,self.owner['token'],role)
        return self.store.join(self.wid,inv['invite'],role)

    def call(self,actor,action,**data):
        return self.store.review(self.wid,actor['token'],dict(action=action,id=uid(),**data))

    def test_reviewer_can_discuss_and_decide_but_cannot_edit_or_reserve(self):
        c=self.owner['project']['cells'][0]
        self.call(self.review,'comment',checkpoint=self.checkpoint,cell=c['id'],object=c['shapes'][0]['id'],text='Check clearance')
        self.call(self.review,'decide',checkpoint=self.checkpoint,status='changes_requested')
        snapshot=self.store.sync(self.wid,self.review['token'],presence=dict(cell=c['id'],view='layout',selection=[c['shapes'][0]['id']]))
        self.assertFalse(snapshot['leases']);self.assertEqual(snapshot['role'],'review')
        before=self.owner['project'];after=clone(before);after['cells'][0]['shapes'][0]['points'][0][0]+=5
        for action in ('edit','undo','redo'):
            with self.assertRaises(LiveError) as caught:
                self.store.edit(self.wid,self.review['token'],dict(id=uid(),revision=0,action=action,label='Forbidden',changes=changes(before,after)))
            self.assertEqual(caught.exception.status,403)
        for action in ('create_checkpoint','share_report'):
            with self.assertRaises(LiveError):self.call(self.review,action,revision=0,name='Forbidden')
        with self.assertRaises(LiveError):self.store.invite(self.wid,self.review['token'],'edit')
        self.assertEqual(self.store.sync(self.wid,self.owner['token'])['project'],before)

    def test_reply_inherits_anchor_and_survives_retry_and_restart(self):
        c=self.owner['project']['cells'][0]
        root=self.call(self.review,'comment',checkpoint=self.checkpoint,cell=c['id'],object=c['shapes'][0]['id'],text='Spacing?')['id']
        req=dict(action='reply',id=uid(),checkpoint=self.checkpoint,parent=root,text='I will inspect the route.')
        first=self.store.review(self.wid,self.edit['token'],req)
        self.assertEqual(first,self.store.review(self.wid,self.edit['token'],req))
        self.store.close();self.store=Store(self.path,self.key)
        self.assertEqual(first,self.store.review(self.wid,self.edit['token'],req))
        rows=self.call(self.view,'list')['comments'];self.assertEqual(len(rows),2)
        reply=next(r for r in rows if r['parent']);self.assertEqual((reply['parent'],reply['cell'],reply['object']),(root,c['id'],c['shapes'][0]['id']))
        with self.assertRaisesRegex(LiveError,'changed'):self.call(self.review,'resolve_comment',comment=root,version=1,status='resolved')
        self.call(self.review,'resolve_comment',comment=root,version=2,status='resolved')
        with self.assertRaisesRegex(LiveError,'Reopen'):self.call(self.edit,'reply',checkpoint=self.checkpoint,parent=root,text='Late reply')
        self.call(self.review,'resolve_comment',comment=root,version=3,status='open')
        self.call(self.edit,'reply',checkpoint=self.checkpoint,parent=root,text='Reopened discussion')

    def test_reply_cannot_cross_checkpoints_or_change_anchors(self):
        root=self.call(self.review,'comment',checkpoint=self.checkpoint,text='Root')['id']
        second=self.call(self.owner,'create_checkpoint',revision=0,name='Other')['id']
        for actor,data in ((self.view,{}),(self.edit,dict(checkpoint=second)),(self.edit,dict(object='other'))):
            request=dict(checkpoint=self.checkpoint,parent=root,text='Invalid');request.update(data)
            with self.assertRaises(LiveError):self.call(actor,'reply',**request)
        child=self.call(self.edit,'reply',checkpoint=self.checkpoint,parent=root,text='Valid')['id']
        with self.assertRaisesRegex(LiveError,'root'):self.call(self.edit,'reply',checkpoint=self.checkpoint,parent=child,text='Nested')
        with self.assertRaises(LiveError):self.call(self.edit,'resolve_comment',comment=root,version=2,status='resolved')

    def test_version_two_database_migrates_existing_comments_and_retry_ids(self):
        request=dict(action='comment',id=uid(),checkpoint=self.checkpoint,text='Old root')
        result=self.store.review(self.wid,self.owner['token'],request)
        self.store.close()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('ALTER TABLE review_comments DROP COLUMN parent');db.execute('PRAGMA user_version=2')
        self.store=Store(self.path,self.key)
        self.assertEqual(self.store.db.execute('PRAGMA user_version').fetchone()[0],3)
        self.assertEqual(self.store.review(self.wid,self.owner['token'],request),result)
        root=self.call(self.owner,'list')['comments'][0];self.assertEqual(root['parent'],'')
        self.call(self.review,'reply',checkpoint=self.checkpoint,parent=root['id'],text='New reply')


class GraphForkTests(unittest.TestCase):
    def test_speculative_join_and_split_do_not_mutate_prior_graph(self):
        from icstudio.layout_graph import GeometryGraph
        p=example('empty');shapes=[rect('metal1',i*1000,0,600,600) for i in range(100)]
        original=GeometryGraph().sync(shapes,p['pdk']);edges={k:set(v) for k,v in original.edges.items()};groups=dict(original.groups)
        changed=[*shapes,rect('metal1',500,0,1000,500)]
        fork=copy(original).sync(changed,p['pdk'],trusted=True)
        self.assertEqual(original.edges,edges);self.assertEqual(original.groups,groups)
        self.assertNotEqual(fork.groups,groups)
        self.assertLess(fork.stats['adjacency_copies'],5)
        split=copy(fork).sync(shapes,p['pdk'],trusted=True)
        self.assertEqual(split.groups,groups);self.assertNotEqual(fork.groups,groups)
        self.assertEqual(split.edges,edges)

    def test_device_impact_includes_pcell_geometry_and_connection_names(self):
        from icstudio.parametric import install
        from icstudio.layout_eco_review import device_impact,proposal_summary
        from icstudio.layout_eco_hierarchy import propose
        p=example('empty');c=p['cells'][0];d=device('R','Rbias',value='1k',nets={'p':'bias','n':'0'});c['devices']=[d]
        install(p,c['id'],d['id'],{});d['value']='2k'
        info=device_impact(p,c['id'],d['id']);self.assertTrue(info['layout_objects']);self.assertEqual(info['nets'],['0','bias'])
        q,report=propose(p,c['id'],[(c['id'],d['id'])],preserve_routes=False)
        summary=proposal_summary(p,q,report);self.assertIn('Rbias',summary);self.assertIn('bias',summary);self.assertIn('Re-run',summary)
