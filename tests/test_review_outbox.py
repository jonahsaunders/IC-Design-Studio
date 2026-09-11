import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.review_outbox import ReviewOutbox
from icstudio.live_store import Store
from icstudio.model import example, uid


class ReviewOutboxTests(unittest.TestCase):
    def test_lost_acknowledgement_and_both_process_restarts_do_not_duplicate_comment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);key='outbox-test-'+'x'*40;store=Store(root/'server.db',key)
            try:
                owner=store.create(key,example('empty'),'Designer');wid=owner['workspace'];token=owner['token']
                checkpoint=store.review(wid,token,dict(action='create_checkpoint',id=uid(),revision=0,name='Review'))
                args=(root/'session.review.json','http://127.0.0.1:8765',wid,owner['actor'])
                box=ReviewOutbox(*args)
                request=dict(id=uid(),action='comment',checkpoint=checkpoint['id'],text='Retain this note')
                box.stage(request)
                accepted=store.review(wid,token,request)  # response is deliberately lost
                store.close();store=Store(root/'server.db',key);box=ReviewOutbox(*args)
                self.assertEqual(box.pending,request)
                self.assertEqual(store.review(wid,token,box.pending),accepted)
                box.acknowledge(request['id'])
                self.assertIsNone(ReviewOutbox(*args).pending)
                self.assertEqual(len(store.review(wid,token,dict(action='list'))['comments']),1)
                self.assertNotIn(token,args[0].read_text())
            finally:store.close()

    def test_failed_storage_preserves_previous_request_and_cannot_claim_acknowledgement(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=(Path(tmp)/'review.json','http://127.0.0.1:8765','workspace','actor');box=ReviewOutbox(*args)
            request=dict(id=uid(),action='comment',text='Keep me');box.stage(request)
            with patch('icstudio.review_outbox.atomic_write',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):box.acknowledge(request['id'])
            self.assertEqual(ReviewOutbox(*args).pending,request)
            box.acknowledge('different-id');self.assertEqual(box.pending,request)
            with self.assertRaises(ValueError):box.stage(dict(request,text='Replaced'))

    def test_cross_session_replay_is_rejected_and_failure_details_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=(Path(tmp)/'review.json','http://127.0.0.1:8765','workspace','actor');box=ReviewOutbox(*args)
            request=dict(id=uid(),action='reply',text='Keep me');box.stage(request);box.failed(request['id'],'Reconnect')
            self.assertEqual(ReviewOutbox(*args).error,'Reconnect')
            with self.assertRaises(ValueError):ReviewOutbox(args[0],args[1],args[2],'another actor')
            box.discard();self.assertIsNone(ReviewOutbox(*args).pending)
