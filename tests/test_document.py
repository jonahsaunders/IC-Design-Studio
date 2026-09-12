import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.model import History, clone, device, example, flatten, validate
from icstudio.layout import rect


class DocumentTests(unittest.TestCase):
    def test_sparse_move_preserves_unchanged_data_and_exact_undo(self):
        p = example('empty'); c = p['cells'][0]
        c['shapes'] = [rect('metal1', i*1000, 0, 500, 500) for i in range(10000)]
        h = History(p); before = h.project; sid = c['shapes'][37]['id']
        self.assertTrue(h.commit_shape_move(c['id'], [sid], 50, -25))
        self.assertIs(h.project['pdk'], before['pdk'])
        self.assertIs(h.project['cells'][0]['shapes'][500], before['cells'][0]['shapes'][500])
        self.assertEqual(h.last_change.objects, (sid,))
        self.assertEqual(h.last_change.cells, (c['id'],))
        self.assertEqual(before['cells'], p['cells'])
        validate(h.project); moved = clone(h.project['cells'])
        h.undo(); self.assertEqual(h.project['cells'], p['cells']); self.assertEqual(h.last_change.kind, 'undo')
        h.redo(); self.assertEqual(h.project['cells'], moved)

    def test_invalid_move_never_changes_document_or_history(self):
        p = example('empty'); c = p['cells'][0]; c['shapes'] = [rect('metal1', 0, 0, 500, 500)]
        h = History(p); before = clone(h.project); ids = [c['shapes'][0]['id']]
        for delta, locks in [((3, 0), ()), ((5, 0), ('metal1',)), ((2**31, 0), ())]:
            with self.assertRaises(ValueError):h.commit_shape_move(c['id'], ids, *delta, locks)
            self.assertEqual(h.project, before); self.assertFalse(h.undo_stack)
        h.project['cells'][0]['shapes'][0]['generated_device'] = 'owned'
        self.assertFalse(h.commit_shape_move(c['id'], ids, 5, 0))

    def test_removal_and_structure_are_in_change_record(self):
        h = History(example('rc')); cid = h.project['cells'][0]['id']; sid = h.project['cells'][0]['devices'][-1]['id']
        h.commit(lambda p: p['cells'][0]['devices'].pop(), 'Remove capacitor')
        self.assertIn(sid, h.last_change.removed)
        self.assertEqual(h.last_change.cells, (cid,))
        h.undo(); self.assertFalse(h.last_change.removed)
        h.commit(lambda p: p['cells'][0].update(name='renamed'), 'Rename')
        self.assertTrue(h.last_change.structure)

    def test_larger_native_circuit_keeps_educational_solver_bound(self):
        p = example('empty'); c = p['cells'][0]
        c['devices'] = [device('R', 'R'+str(i), i*10, 0, value='1k', nets={'p':'n'+str(i), 'n':'0'}) for i in range(1000)]
        validate(p); self.assertEqual(len(flatten(p)), 1000)
        from icstudio.simulation import Circuit
        with self.assertRaisesRegex(ValueError, 'Choose ngspice'):Circuit(p, c['id'])

    def test_patch_change_records_match_independent_document_comparison(self):
        from icstudio.document import describe
        h=History(example('rc'))
        for edit in (lambda p:p['cells'][0]['devices'][1].update(value='2k'),
                     lambda p:p['cells'][0].update(name='renamed'),
                     lambda p:p['cells'][0]['devices'].pop(),
                     lambda p:p['pdk'].update(name='Renamed technology')):
            before=h.project;h.commit(edit,'Edit')
            self.assertEqual(h.last_change,describe(before,h.project,'Edit'))
            before=h.project;h.undo();self.assertEqual(h.last_change,describe(before,h.project,'Edit','undo'))
            before=h.project;h.redo();self.assertEqual(h.last_change,describe(before,h.project,'Edit','redo'))

    @unittest.skipUnless(os.environ.get('ICSTUDIO_TEST_NGSPICE'),'The desktop gates supply a real ngspice executable')
    def test_thousand_device_ladder_runs_in_ngspice(self):
        from icstudio.engines import run_ngspice
        p=example('empty');c=p['cells'][0]
        c['devices']=[device('R','R'+str(i),i*10,0,value='1k',nets={'p':'n'+str(i),'n':'0' if i==999 else 'n'+str(i+1)}) for i in range(1000)]
        c['devices'].append(device('V','VDD',0,100,value='1',nets={'p':'n0','n':'0'}));validate(p)
        with tempfile.TemporaryDirectory() as tmp:
            r=run_ngspice(p,c['id'],{**p['analysis'],'type':'op'},os.environ['ICSTUDIO_TEST_NGSPICE'],Path(tmp))
            self.assertAlmostEqual(r['traces']['n500'][0],.5,places=6)


class RecoveryQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import QCoreApplication
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_coalescing_writes_latest_snapshot_and_flush_fences_discard(self):
        from icstudio.recovery_queue import RecoveryQueue
        from icstudio.recovery import read
        q = RecoveryQueue(); results = []; q.completed.connect(results.append)
        try:
            with tempfile.TemporaryDirectory() as folder:
                p = example('empty'); original = clone(p)
                q.request(p, folder, None, 1)
                p = clone(p); p['name'] = 'Latest'; p['revision'] += 1
                q.request(p, folder, None, 1)
                self.assertTrue(q.flush()); self.assertEqual(len(results), 1)
                path = Path(folder)/(p['id']+'.icproj')
                self.assertEqual(read(path)[0]['name'], 'Latest')
                q.request(original, folder, None, 1); q.dispatch()
                q.request(p, folder, None, 1); q.flush(discard=True)
                path.unlink(); self.app.processEvents()
                self.assertFalse(path.exists()); self.assertFalse(q.busy)
        finally:q.shutdown()

    def test_failed_write_preserves_prior_recovery_and_can_retry(self):
        from icstudio.recovery_queue import RecoveryQueue
        q = RecoveryQueue(); results = []; q.completed.connect(results.append)
        try:
            with tempfile.TemporaryDirectory() as folder:
                p = example('empty'); q.request(p, folder, None, 1); q.flush()
                path = Path(folder)/(p['id']+'.icproj'); before = path.read_bytes()
                p = clone(p); p['name'] = 'Changed'
                with patch('os.fsync', side_effect=OSError(28, 'disk full')):
                    q.request(p, folder, None, 1); self.assertFalse(q.flush())
                self.assertEqual(path.read_bytes(), before); self.assertIn('disk full', results[-1]['error'])
                q.request(p, folder, None, 1); self.assertTrue(q.flush()); self.assertIsNone(results[-1]['error'])
        finally:q.shutdown()
