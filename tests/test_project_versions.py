from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import tempfile
import unittest

from icstudio.model import History, example
from icstudio.project_versions import ProjectVersions, compare, restore_contents, same_design


class ProjectVersionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'RC #1 with spaces.icstudio'
        self.history = History(example('rc'))
        self.store = ProjectVersions(self.path, self.history.project['id'])

    def capture(self, name='Baseline', note=''):
        return self.store.save(self.history.project, name, note)

    def test_versions_reopen_and_keep_a_separate_identity(self):
        self.assertEqual(self.store.list(), [])
        self.assertFalse(self.store.path.exists())
        initial = self.capture('Entrée', 'Référence RC')
        self.history.commit(lambda p: p.update(name='Filter'), 'Rename')
        current = self.capture('Filter')
        reopened = ProjectVersions(self.path, self.history.project['id'])
        self.assertEqual(reopened.list(), [current, initial])
        self.assertEqual(reopened.load(initial.id)['name'], 'RC low-pass')
        foreign = ProjectVersions(self.path, example()['id'])
        self.assertEqual(foreign.list(), [])
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            foreign.load(initial.id)
        moved = self.path.parent / 'Moved.icproj'
        target = ProjectVersions(moved, self.history.project['id'])
        shutil.move(self.store.path, target.path)
        self.assertEqual(target.list(), [current, initial])

    def test_concurrent_captures_publish_complete_entries_and_share_snapshot(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            recorded = list(pool.map(self.capture, ('Input filter', 'Harness', 'Review', 'Demo')))
        self.assertCountEqual(self.store.list(), recorded)
        for version in recorded:
            self.assertEqual(self.store.load(version.id), self.history.project)
        with self.store.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM snapshots').fetchone(), (1,))

    def test_rejects_changed_snapshot_without_removing_history(self):
        recorded = self.capture()
        with self.store.database(write=True) as db:
            db.execute('UPDATE snapshots SET data=?', (b'{}',))
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.store.load(recorded.id)
        self.assertEqual(self.store.list(), [recorded])
        retry = self.capture('Recaptured design')
        self.assertEqual(self.store.load(recorded.id), self.store.load(retry.id))

    def test_restore_is_a_new_revision_with_undo_and_redo(self):
        recorded = self.capture()
        baseline = self.store.load(recorded.id)
        self.history.commit(lambda p: p['cells'][0]['devices'][1].update(value='20k'), 'Edit R1')
        modified = self.history.project
        self.assertTrue(any('R1 · Value · 10k → 20k' in line for line in compare(baseline, modified)))
        self.history.commit(lambda p: restore_contents(p, baseline), 'Restore version')
        self.assertGreater(self.history.project['revision'], modified['revision'])
        self.assertTrue(same_design(baseline, self.history.project))
        self.history.undo()
        self.assertTrue(same_design(modified, self.history.project))
        self.history.redo()
        self.assertTrue(same_design(baseline, self.history.project))
