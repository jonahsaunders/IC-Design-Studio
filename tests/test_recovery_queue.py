"""Durable snapshots must remain exact while editing continues on the UI thread."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from icstudio.layout import rect
from icstudio.model import History, clone, digest, example
from icstudio.recovery import read
from icstudio.recovery_queue import RecoveryQueue, _write_snapshot


class SerializedRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import QCoreApplication
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.queue = RecoveryQueue()
        self.addCleanup(self.queue.shutdown)
        self.results = []
        self.queue.completed.connect(self.results.append)

    def recovered(self, project):
        restored, fallback = read(Path(self.folder.name) / (project['id'] + '.icproj'))
        self.assertFalse(fallback)
        return restored

    def test_dispatched_snapshot_survives_in_place_edits_and_preserves_json_scalars(self):
        project = example('empty')
        project['name'] = 'Snapshot Ω'
        project['snapshot_metadata'] = [1, 1.0, True, -0.0, 0.0]
        project['cells'][0]['shapes'] = [rect('metal1', 0, 0, 100, 100)]
        expected = clone(project)
        entered, release = threading.Event(), threading.Event()

        def blocked(snapshot, *args):
            entered.set()
            if not release.wait(5):
                raise TimeoutError('Test did not release recovery writer.')
            return _write_snapshot(snapshot, *args)

        with patch('icstudio.recovery_queue._write_snapshot', side_effect=blocked):
            self.queue.request(project, self.folder.name, None, 1)
            self.queue.dispatch()
            try:
                self.assertTrue(entered.wait(5))
                project['name'] = 'Edited while writing'
                project['snapshot_metadata'][3] = 0.0
                project['cells'][0]['shapes'][0]['points'][0][0] = 5
            finally:
                release.set()
            self.assertTrue(self.queue.flush())
        self.assertEqual(digest(self.recovered(project)), digest(expected))
        self.assertEqual(self.results[-1]['hash'], digest(expected))

        # Reusing the same caller containers must still capture every mutation.
        self.queue.request(project, self.folder.name, None, 1)
        self.assertTrue(self.queue.flush())
        self.assertEqual(digest(self.recovered(project)), digest(project))
        self.assertEqual(self.results[-1]['hash'], digest(project))

    def test_coalesced_move_undo_redo_while_writing_recovers_latest_history(self):
        project = example('empty')
        cell = project['cells'][0]
        shape = rect('metal1', 0, 0, 100, 100)
        cell['shapes'] = [shape]
        history = History(project)
        entered, release = threading.Event(), threading.Event()

        def blocked(snapshot, *args):
            entered.set()
            if not release.wait(5):
                raise TimeoutError('Test did not release recovery writer.')
            return _write_snapshot(snapshot, *args)

        with patch('icstudio.recovery_queue._write_snapshot', side_effect=blocked):
            self.queue.request(history.project, self.folder.name, None, 1)
            self.queue.dispatch()
            try:
                self.assertTrue(entered.wait(5))
                self.assertTrue(history.commit_shape_move(cell['id'], [shape['id']], 5, 0))
                self.queue.request(history.project, self.folder.name, None, 1, validated=True)
                history.undo()
                self.queue.request(history.project, self.folder.name, None, 1)
                history.redo()
                self.queue.request(history.project, self.folder.name, None, 1)
            finally:
                release.set()
            self.assertTrue(self.queue.flush())
        self.assertEqual(len(self.results), 2)
        self.assertEqual(digest(self.recovered(project)), digest(history.project))
        self.assertEqual(self.results[-1]['hash'], digest(history.project))

    def test_worker_validation_owns_its_tree(self):
        from icstudio.model import validate
        project = example('empty')
        original = clone(project)
        main_thread = threading.get_ident()
        validation_threads = []

        def normalize(snapshot):
            validation_threads.append(threading.get_ident())
            snapshot['name'] = 'Normalized snapshot'
            return validate(snapshot)

        with patch('icstudio.recovery.validate', side_effect=normalize):
            self.queue.request(project, self.folder.name, None, 1)
            self.assertTrue(self.queue.flush())
        self.assertEqual(project, original)
        self.assertEqual(self.recovered(project)['name'], 'Normalized snapshot')
        self.assertTrue(validation_threads)
        self.assertNotIn(main_thread, validation_threads)
        self.assertEqual(self.results[-1]['hash'], digest(self.recovered(project)))

    def test_encoding_and_validation_failures_preserve_recovery_then_retry(self):
        project = example('empty')
        self.queue.request(project, self.folder.name, None, 1)
        self.assertTrue(self.queue.flush())
        path = Path(self.folder.name) / (project['id'] + '.icproj')
        previous = path.read_bytes()
        project['snapshot_metadata'] = lambda: None
        self.queue.request(project, self.folder.name, None, 1)
        self.assertFalse(self.queue.flush())
        self.assertTrue(self.results[-1]['error'])
        self.assertEqual(path.read_bytes(), previous)
        del project['snapshot_metadata']

        project['analysis']['temperature'] = float('nan')
        self.queue.request(project, self.folder.name, None, 1)
        self.assertFalse(self.queue.flush())
        self.assertIn('JSON', self.results[-1]['error'])
        self.assertEqual(path.read_bytes(), previous)

        project['analysis']['temperature'] = 27
        project['name'] = ''
        self.queue.request(project, self.folder.name, None, 1)
        self.assertFalse(self.queue.flush())
        self.assertIn('name', self.results[-1]['error'])
        self.assertEqual(path.read_bytes(), previous)

        project['name'] = 'Valid retry'
        self.queue.request(project, self.folder.name, None, 1)
        self.assertTrue(self.queue.flush())
        self.assertIsNone(self.results[-1]['error'])
        self.assertEqual(digest(self.recovered(project)), digest(project))

    def test_invalid_tuple_coordinates_are_rejected_before_json_can_normalize_them(self):
        project = example('empty')
        self.queue.request(project, self.folder.name, None, 1)
        self.assertTrue(self.queue.flush())
        path = Path(self.folder.name) / (project['id'] + '.icproj')
        previous = path.read_bytes()
        shape = rect('metal1', 0, 0, 100, 100)
        shape['points'][0] = tuple(shape['points'][0])
        project['cells'][0]['shapes'] = [shape]
        self.queue.request(project, self.folder.name, None, 1)
        self.assertFalse(self.queue.flush())
        self.assertIn('Coordinates', self.results[-1]['error'])
        self.assertEqual(path.read_bytes(), previous)
