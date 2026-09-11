import tempfile
import unittest
from pathlib import Path
from icstudio.live_store import Store
from icstudio.live_protocol import LiveError, changes
from icstudio.model import example,clone,uid,design_digest
from icstudio.layout import rect


class TeamReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'server.db';self.key='review-test-'+'x'*40
        self.store=Store(self.path,self.key);p=example('empty');p['cells'][0]['shapes']=[rect('metal1',0,0,500,500)]
        self.owner=self.store.create(self.key,p,'Owner');self.wid=self.owner['workspace']
        invitation=self.store.invite(self.wid,self.owner['token'],'edit');self.editor=self.store.join(self.wid,invitation['invite'],'Editor')
        invitation=self.store.invite(self.wid,self.owner['token'],'view');self.viewer=self.store.join(self.wid,invitation['invite'],'Viewer')
        self.checkpoint=self.call('create_checkpoint',revision=0,name='First')

    def tearDown(self):self.store.close();self.temp.cleanup()

    def call(self,action,actor=None,**data):
        return self.store.review(self.wid,(actor or self.owner)['token'],dict(action=action,id=uid(),**data))

    def test_checkpoint_is_immutable_and_decisions_do_not_follow_new_edits(self):
        before=self.call('checkpoint',checkpoint=self.checkpoint['id'])
        self.call('decide',actor=self.editor,checkpoint=self.checkpoint['id'],status='approved',text='Looks good')
        p=clone(self.owner['project']);p['cells'][0]['shapes'][0]['points']=[[100,0],[600,500]]
        self.store.edit(self.wid,self.owner['token'],dict(id=uid(),revision=0,action='edit',label='Move',changes=changes(self.owner['project'],p)))
        self.assertEqual(self.call('checkpoint',checkpoint=self.checkpoint['id']),before)
        with self.assertRaisesRegex(LiveError,'changed'):self.call('create_checkpoint',revision=0,name='Stale')
        new=self.call('create_checkpoint',revision=1,name='Second');rows=self.call('list')
        self.assertTrue(all(d['checkpoint']!=new['id'] for d in rows['decisions']))

    def test_comment_anchor_permission_and_version_checks(self):
        c=self.owner['project']['cells'][0];key=self.checkpoint['id']
        row=self.call('comment',actor=self.editor,checkpoint=key,cell=c['id'],object=c['shapes'][0]['id'],text='Check spacing')
        with self.assertRaisesRegex(LiveError,'absent'):self.call('comment',checkpoint=key,cell=c['id'],object='missing',text='Bad anchor')
        with self.assertRaises(LiveError):self.call('comment',actor=self.viewer,checkpoint=key,text='No edit access')
        self.assertEqual(len(self.call('list',actor=self.viewer)['comments']),1)
        self.call('resolve_comment',comment=row['id'],version=1,status='resolved')
        with self.assertRaisesRegex(LiveError,'changed'):self.call('resolve_comment',comment=row['id'],version=1,status='open')

    def test_retry_identity_and_restart_preserve_review(self):
        request=dict(action='comment',id=uid(),checkpoint=self.checkpoint['id'],text='Retained note')
        a=self.store.review(self.wid,self.owner['token'],request)
        self.assertEqual(a,self.store.review(self.wid,self.owner['token'],request))
        with self.assertRaises(LiveError):self.store.review(self.wid,self.owner['token'],dict(request,text='Different'))
        self.store.close();self.store=Store(self.path,self.key)
        rows=self.call('list');self.assertEqual(len(rows['comments']),1);self.assertEqual(rows['comments'][0]['text'],'Retained note')

    def test_shared_result_must_match_input_and_checkpoint(self):
        p=self.owner['project'];cid=p['top'];hash_=design_digest(p)
        job=dict(project=p,cell=cid,engine='builtin',settings={'type':'op','executable':'private-path'},executable='private-path')
        result=dict(project_id=p['id'],cell_id=cid,design_hash=hash_,x=[0],traces={'out':[.5]})
        published=self.call('share_report',checkpoint=self.checkpoint['id'],name='Operating point',job=job,result=result)
        shared=self.call('report',actor=self.viewer,report=published['id'])
        self.assertEqual(shared['job']['project'],p);self.assertNotIn('executable',shared['job']);self.assertNotIn('executable',shared['job']['settings'])
        with self.assertRaisesRegex(LiveError,'does not match'):self.call('share_report',checkpoint=self.checkpoint['id'],name='Wrong',job=job,result=dict(result,design_hash='wrong'))
        self.store.delete_workspace(self.wid,self.owner['token'],0)
        from icstudio.live_review_store import TABLES
        for table in TABLES:self.assertEqual(self.store.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
