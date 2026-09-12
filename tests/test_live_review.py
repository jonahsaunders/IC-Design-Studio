"""Conflict recovery preserves foreign changes and handles a whole transaction."""
import json
from pathlib import Path
import tempfile
import unittest

from icstudio.layout import rect
from icstudio.live_protocol import LiveError
from icstudio.live_review import reapply_conflict, recent_sessions, reservation_rows
from icstudio.model import clone, example


class LiveReviewTests(unittest.TestCase):
    def setUp(self):
        self.base = example('empty')
        self.base['cells'][0]['shapes'] = [rect('metal1', 0, 0, 100, 100), rect('metal1', 400, 0, 100, 100)]
        self.proposed = clone(self.base)
        self.proposed['cells'][0]['shapes'][0]['points'] = [[10, 0], [110, 100]]
        self.conflict = dict(before=self.base, proposed=self.proposed)

    def test_reapply_translation_preserves_foreign_resize_and_other_objects(self):
        shared = clone(self.base)
        shared['cells'][0]['shapes'][0]['points'][1][1] = 250
        shared['cells'][0]['shapes'][1]['points'][1][0] = 750
        before = clone(shared)
        result = reapply_conflict(self.conflict, shared)
        self.assertEqual(result['cells'][0]['shapes'][0]['points'], [[10, 0], [110, 250]])
        self.assertEqual(result['cells'][0]['shapes'][1], shared['cells'][0]['shapes'][1])
        self.assertEqual(shared, before)
        self.assertEqual(self.conflict['before'], self.base)

    def test_one_unsupported_overlap_rejects_entire_transaction(self):
        self.proposed['cells'][0]['shapes'][1]['layer'] = 'metal2'
        shared = clone(self.base)
        shared['cells'][0]['shapes'][1]['layer'] = 'poly'
        before = clone(shared)
        with self.assertRaises(LiveError):
            reapply_conflict(self.conflict, shared)
        self.assertEqual(shared, before)

    def test_deleted_object_is_not_resurrected(self):
        shared = clone(self.base)
        shared['cells'][0]['shapes'].pop(0)
        with self.assertRaises(LiveError):
            reapply_conflict(self.conflict, shared)

    def test_already_applied_transaction_is_unchanged(self):
        self.assertEqual(reapply_conflict(self.conflict, self.proposed), self.proposed)

    def test_polygon_holes_follow_translation(self):
        shape = self.base['cells'][0]['shapes'][0]
        shape.update(kind='polygon', points=[[0, 0], [100, 0], [100, 100], [0, 100]],
                     holes=[[[20, 20], [40, 20], [40, 40], [20, 40]]])
        proposed = clone(self.base)
        p = proposed['cells'][0]['shapes'][0]
        p['points'] = [[x + 10, y] for x, y in p['points']]
        p['holes'] = [[[x + 10, y] for x, y in hole] for hole in p['holes']]
        shared = clone(self.base)
        shared['cells'][0]['shapes'][0]['net'] = 'signal'
        result = reapply_conflict(dict(before=self.base, proposed=proposed), shared)
        self.assertEqual(result['cells'][0]['shapes'][0]['holes'], p['holes'])
        self.assertEqual(result['cells'][0]['shapes'][0]['net'], 'signal')

    def test_recent_workspace_metadata_never_returns_session_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'session.json'
            path.write_text(json.dumps(dict(schema=1, project=self.base, server='https://example.org',
                token='private-session-token', info=dict(name='Alice', role='owner'), pending={'secret': 'private-edit'}, conflict=None)))
            (Path(directory) / 'broken.json').write_text('{broken')
            records = recent_sessions(directory)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]['name'], self.base['name'])
            self.assertTrue(records[0]['attention'])
            self.assertNotIn('private-session-token', json.dumps(records))
            self.assertNotIn('private-edit', json.dumps(records))

    def test_reservations_explain_whole_cell_net_and_expiry(self):
        cid = self.base['top']
        info = dict(actor='me', leases=[
            dict(resource=json.dumps([cid, '*', '*']), actor='other', name='Alice', expires=110),
            dict(resource=json.dumps([cid, 'net', 'vout']), actor='me', name='Bob', expires=105),
            dict(resource=json.dumps([cid, '*', '*']), actor='old', name='Expired', expires=99)])
        rows = reservation_rows(self.base, info, 100)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['owner'], 'Alice')
        self.assertIn('Whole cell', rows[0]['scope'])
        self.assertEqual((rows[1]['owner'], rows[1]['scope'], rows[1]['seconds']), ('You', 'Net vout', 5))
