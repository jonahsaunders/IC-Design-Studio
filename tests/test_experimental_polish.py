import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.model import clone, example
from icstudio.layout import rect
from icstudio.recovery_snapshot import isolate
from icstudio.review_drafts import ReviewDrafts


class SnapshotTests(unittest.TestCase):
    def test_reuses_isolated_geometry_but_observes_in_place_edits(self):
        p=example('empty');p['cells'][0]['shapes']=[rect('metal1',i*1000,0,600,600) for i in range(100)]
        first=isolate(p);original=clone(first)
        p['cells'][0]['shapes'][50]['points'][0][0]+=5;p['analysis']['stop']='200u'
        second=isolate(p,first)
        self.assertEqual(first,original);self.assertEqual(second,p)
        self.assertIs(second['cells'][0]['shapes'][0],first['cells'][0]['shapes'][0])
        self.assertIsNot(second['cells'][0]['shapes'][50],first['cells'][0]['shapes'][50])
        p['cells'][0]['shapes'][0]['points'][0][0]+=10;p['analysis']['stop']='300u'
        self.assertEqual(first,original);self.assertNotEqual(second,p)
        third=isolate(p,second);self.assertEqual(third,p)

    def test_preserves_json_scalar_types_and_structure_changes(self):
        old=isolate({'a':[1,1.0,True,None,{'gone':1}],'gone':'x'})
        changed={'a':[True,1,1.0,None,{'added':2}],'new':[]}
        new=isolate(changed,old)
        self.assertEqual(json.dumps(new),json.dumps(changed))
        changed['new'].append(4);self.assertEqual(new['new'],[])
        self.assertEqual(isolate(changed,new),changed)


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.args=(Path(self.tmp.name)/'session.review-drafts','https://team.example','workspace','actor')
        self.drafts=ReviewDrafts(*self.args)

    def test_restart_retains_independent_checkpoints_and_reply_context(self):
        self.drafts.save('one','Unsent Ω comment');self.drafts.save('two','Unsent reply','thread')
        restored=ReviewDrafts(*self.args)
        self.assertEqual(restored.get('one'),dict(text='Unsent Ω comment',reply=''))
        self.assertEqual(restored.get('two'),dict(text='Unsent reply',reply='thread'))
        self.assertNotIn('token',restored.path.read_text())
        with self.assertRaisesRegex(ValueError,'different session'):
            ReviewDrafts(self.args[0],self.args[1],'different-workspace',self.args[3])

    def test_acknowledgement_never_erases_newer_text_or_another_thread(self):
        self.drafts.save('one','Posted text')
        req=dict(action='comment',checkpoint='one',text='Posted text')
        self.drafts.save('one','New unsent text');self.drafts.acknowledge(req)
        self.assertEqual(ReviewDrafts(*self.args).get('one')['text'],'New unsent text')
        self.drafts.save('one','Posted text','another-thread');self.drafts.acknowledge(req)
        self.assertEqual(self.drafts.get('one')['reply'],'another-thread')
        self.drafts.save('one','Posted text');self.drafts.acknowledge(req)
        self.assertEqual(ReviewDrafts(*self.args).get('one')['text'],'')

    def test_failed_storage_preserves_last_durable_draft_and_retry(self):
        self.drafts.save('one','Durable');before=self.args[0].read_bytes()
        with patch('icstudio.review_drafts.atomic_write',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.drafts.save('one','New text')
            with self.assertRaises(OSError):self.drafts.save('one','')
        self.assertEqual(self.args[0].read_bytes(),before)
        self.assertEqual(self.drafts.get('one')['text'],'Durable')
        self.drafts.save('one','New text');self.assertEqual(ReviewDrafts(*self.args).get('one')['text'],'New text')

    def test_corrupt_file_is_preserved_and_not_silently_overwritten(self):
        self.args[0].write_text('{broken')
        with self.assertRaises(ValueError):ReviewDrafts(*self.args)
        self.assertEqual(self.args[0].read_text(),'{broken')


class WindowGeometryTests(unittest.TestCase):
    def test_monitor_removal_recovers_title_bar_without_moving_visible_windows(self):
        from PySide6.QtCore import QRect
        from icstudio.window_geometry import reachable_geometry
        primary=QRect(0,0,1920,1040);secondary=QRect(-1280,0,1280,984)
        saved=QRect(-1200,100,700,500)
        self.assertEqual(reachable_geometry(saved,[primary,secondary]),saved)
        repaired=reachable_geometry(saved,[primary]);self.assertTrue(primary.contains(repaired))
        self.assertEqual(reachable_geometry(QRect(20,20,700,500),[primary]),QRect(20,20,700,500))


class BuildIdentityTests(unittest.TestCase):
    def test_frozen_identity_comes_from_embedded_metadata(self):
        from icstudio import build_info
        from icstudio.build_identity import identity
        with patch('sys.frozen',True,create=True),patch.object(build_info,'BUILD_COMMIT','a'*40,create=True),patch.object(build_info,'BUILD_BRANCH','experimental',create=True),patch.object(build_info,'BUILD_DIRTY',False,create=True):
            result=identity()
        self.assertEqual(result['commit'],'a'*40);self.assertEqual(result['branch'],'experimental');self.assertFalse(result['dirty'])

    def test_source_identity_detects_untracked_shipped_code(self):
        import subprocess
        from icstudio import build_identity
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'icstudio').mkdir();module=root/'icstudio/build_identity.py';module.write_text('# fixture\n')
            def git(*args):return subprocess.check_output(['git',*args],cwd=root,stderr=subprocess.DEVNULL,text=True).strip()
            git('init');git('add','icstudio');git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','fixture')
            with patch.object(build_identity,'__file__',str(module)):
                clean=build_identity.identity();self.assertFalse(clean['dirty']);self.assertEqual(clean['commit'],git('rev-parse','HEAD'))
                (root/'icstudio/new_component.py').write_text('# not committed\n')
                self.assertTrue(build_identity.identity()['dirty'])
