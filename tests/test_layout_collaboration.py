"""Two-process ownership/publication, stale edits and interruption recovery."""
import json
import multiprocessing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.model import example, clone, digest
from icstudio.layout import rect
from icstudio.layout_collaboration import Session, merge


def worker(root,layer,ready,start,results):
    try:
        s=Session.join(root,layer);s.claim(s.base['top'],[layer]);p=clone(s.base)
        p['cells'][0]['shapes'].append(rect(layer,0,0,600,600));ready.put(layer);start.wait(15);s.publish(p);s.release();results.put('ok')
    except Exception as exc:results.put(str(exc))


class ConcurrentLayout(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.p=example('empty');self.a=Session.create(self.root,self.p,'Alice');self.b=Session.join(self.root,'Bob')
    def tearDown(self):self.temp.cleanup()

    def test_same_cell_disjoint_layers_publish_and_refresh_local_edits(self):
        cid=self.p['top'];self.a.claim(cid,['metal1']);self.b.claim(cid,['metal2'])
        pa=clone(self.p);pb=clone(self.p);a=rect('metal1',0,0,600,600);b=rect('metal2',0,0,600,600)
        pa['cells'][0]['shapes'].append(a);pb['cells'][0]['shapes'].append(b)
        self.a.publish(pa);pb=self.b.refresh(pb);self.assertEqual({s['id'] for s in pb['cells'][0]['shapes']},{a['id'],b['id']})
        result=self.b.publish(pb);self.assertEqual(len(result['cells'][0]['shapes']),2)
        self.assertEqual(self.a.refresh(pa)['cells'],result['cells'])

    def test_overlap_expiry_reclaim_conflict_and_unauthorized_changes(self):
        cid=self.p['top'];self.a.claim(cid)
        with self.assertRaisesRegex(ValueError,'Alice'):self.b.claim(cid,['metal1'])
        q=clone(self.p);q['cells'][0]['shapes'].append(rect('metal1',0,0,600,600))
        with self.assertRaisesRegex(ValueError,'active claim'):self.b.publish(q)
        self.a.publish(q);self.a.release();self.b.refresh(self.p);self.b.claim(cid)
        a=clone(q);b=clone(q);a['cells'][0]['shapes'][0]['net']='a';b['cells'][0]['shapes'][0]['net']='b';self.b.publish(b)
        self.b.release();self.a.claim(cid)
        with self.assertRaisesRegex(ValueError,'conflict'):self.a.publish(a)
        state=json.loads((self.root/'workspace.json').read_text());state['claims'][0]['expires']=0;(self.root/'workspace.json').write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError,'active claim'):self.a.publish(a)
        self.b.claim(cid)
        q=clone(self.b.base);q['pdk']['grid']=10
        with self.assertRaisesRegex(ValueError,'layout only'):self.b.publish(q)

    def test_interrupted_write_keeps_last_publication_and_local_base(self):
        self.a.claim(self.p['top']);q=clone(self.p);q['cells'][0]['shapes'].append(rect('metal1',0,0,600,600));before=(self.root/'workspace.json').read_bytes()
        with patch('icstudio.model.os.replace',side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):self.a.publish(q)
        self.assertEqual((self.root/'workspace.json').read_bytes(),before);self.assertEqual(self.a.base,self.p)
        self.assertEqual(len(self.a.publish(q)['cells'][0]['shapes']),1)

    def test_separate_processes_publish_without_lost_updates(self):
        ctx=multiprocessing.get_context('spawn');ready=ctx.Queue();results=ctx.Queue();start=ctx.Event()
        ps=[ctx.Process(target=worker,args=(str(self.root),layer,ready,start,results)) for layer in ('metal1','metal2')]
        for p in ps:p.start()
        try:
            self.assertEqual({ready.get(timeout=20),ready.get(timeout=20)},{'metal1','metal2'});start.set()
            self.assertEqual([results.get(timeout=20),results.get(timeout=20)],['ok','ok'])
        finally:
            for p in ps:
                p.join(20)
                if p.is_alive():p.terminate();p.join()
            for q in (ready,results):q.close();q.join_thread()
        state=self.a.status();self.assertEqual(state['revision'],2);self.assertEqual({s['layer'] for s in state['project']['cells'][0]['shapes']},{'metal1','metal2'})


if __name__=='__main__':unittest.main()
