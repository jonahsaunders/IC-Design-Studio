"""Document targeting, unapplied edits, exit recovery and simulation Stop on Qt."""
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QContextMenuEvent, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

from icstudio.getting_started import examples
from icstudio.gui import Studio
from icstudio.model import clone, digest, example, load_project, save_project
from icstudio.project_hub_ui import ProjectHub


class EditingUsabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        if sys.platform=='win32' and cls.app.platformName()=='offscreen':
            fonts=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
            for name in ('segoeui.ttf','segoeuib.ttf','arial.ttf'):
                assert QFontDatabase.addApplicationFont(str(fonts/name))>=0, f'Could not load {name}'

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        settings = QSettings(str(self.root/'settings.ini'), QSettings.IniFormat)
        settings.setFallbacksEnabled(False)
        settings.setValue('onboarding/show', False)
        with patch('icstudio.gui.QSettings', return_value=settings), patch(
                'icstudio.gui.QStandardPaths.writableLocation', return_value=str(self.root/'data')):
            self.w = Studio(recover=False)
        self.w.set_project(example('rc'))
        self.w.saved_hash = digest(self.w.project)
        self.w.live_check.setChecked(False)
        self.w.show()
        self.errors = []
        self.w.error = self.errors.append
        self.hook = patch.object(sys, 'excepthook', side_effect=lambda kind, value, tb:self.errors.append(str(value)))
        self.hook.start()
        self.app.processEvents()

    def tearDown(self):
        self.w.run_manager.cancel(list(self.w.run_manager.rows))
        self.finish_runs()
        self.w._inspector_dirty = False
        self.w.analysis_dirty = False
        self.w.saved_hash = digest(self.w.project)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            self.w.close()
        self.app.processEvents()
        self.w.finish_recovery()
        self.hook.stop()
        self.folder.cleanup()
        self.assertEqual(self.errors, [])

    def finish_runs(self):
        deadline = time.monotonic()+20
        while self.w.run_manager.busy and time.monotonic()<deadline:
            QTest.qWait(20)
        self.assertFalse(self.w.run_manager.busy, 'Simulation workers did not stop.')

    def resistor(self):
        return next(d for d in self.w.cell['devices'] if d['kind']=='R')

    def test_tiny_tapeout_export_keeps_unapplied_rtl_edits(self):
        from zipfile import ZipFile

        from icstudio.digital_examples import uart_project
        from icstudio.tapeout_ui import TapeoutSourceDialog

        self.w.set_project(uart_project())
        window = self.w.digital_window()
        original = digest(self.w.project)
        marker = '\n// Source in the editor\n'
        window.editor.setPlainText(window.editor.toPlainText() + marker)
        self.assertTrue(window.dirty)
        action = next(action for action in self.w.task_menus['Digital'].actions()
                      if action.text() == 'Export Tiny Tapeout Source…')
        output = self.root / 'UART source package.zip'
        observed = {}

        def interact():
            dialog = self.app.activeModalWidget()
            try:
                observed['dialog'] = isinstance(dialog, TapeoutSourceDialog)
                observed['focus'] = dialog.focusWidget().accessibleName()
                QTest.keyClick(dialog.author, Qt.Key_Return)
                observed['validation'] = dialog.message.text()
                QTest.keyClicks(dialog.author, 'Studio Test')
                QTest.keyClick(dialog.author, Qt.Key_Return)
                observed['still_open'] = dialog.isVisible()
                QTest.keyClick(dialog.author, Qt.Key_Return)
            finally:
                if isinstance(dialog, TapeoutSourceDialog) and dialog.isVisible():
                    dialog.reject()

        with patch.object(QFileDialog, 'getSaveFileName', side_effect=[('', ''), (str(output), '')]) as chooser:
            QTimer.singleShot(0, interact)
            action.trigger()
        self.assertTrue(observed['dialog'])
        self.assertEqual(observed['focus'], 'Author')
        self.assertIn('Enter the author', observed['validation'])
        self.assertTrue(observed['still_open'])
        self.assertEqual(chooser.call_count, 2)
        self.assertIn('stream precheck are pending', self.w.statusBar().currentMessage())
        self.assertEqual(digest(self.w.project), original)
        self.assertTrue(window.dirty)
        with ZipFile(output) as archive:
            self.assertTrue(archive.read('src/uart_tx.sv').endswith(marker.encode()))

    def test_named_project_versions_from_file_menu_restore_without_overwriting_the_project(self):
        from icstudio.project_versions import ProjectVersions
        from icstudio.project_versions_ui import SaveVersionDialog, VersionHistoryDialog

        path = self.root / 'Filter with spaces.icproj'

        def invoke(command, dialog_type, interaction):
            dialog_seen = []

            def use_dialog():
                dialog = self.app.activeModalWidget()
                dialog_seen.append(dialog)
                try:
                    self.assertIsInstance(dialog, dialog_type)
                    interaction(dialog)
                finally:
                    if dialog and dialog.isVisible():
                        dialog.reject()

            menu = next(a.menu() for a in self.w.task_menus['File'].actions() if a.text() == 'Versions')
            action = next(a for a in menu.actions() if a.text() == command)
            QTimer.singleShot(0, use_dialog)
            action.trigger()
            self.assertEqual(len(dialog_seen), 1)

        def write_version(dialog, name, note):
            self.assertFalse(dialog.save_button.isEnabled())
            QTest.keyClicks(dialog.name, name)
            dialog.note.setPlainText(note)
            QTest.keyClick(dialog.name, Qt.Key_Return)
            self.assertIsNotNone(dialog.version)

        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')):
            invoke('Save Version…', SaveVersionDialog, lambda d: write_version(d, 'Baseline', 'Before tuning'))
        self.w.select([self.resistor()['id']], 'schematic')
        value = self.w.form_fields['Value']
        value.selectAll()
        QTest.keyClicks(value, '20k')
        invoke('Save Version…', SaveVersionDialog, lambda d: write_version(d, 'Tuned', 'Doubling R1'))
        self.assertEqual(self.resistor()['value'], '20k')
        self.assertEqual(load_project(path)['cells'][0]['devices'][1]['value'], '10k')
        self.assertTrue(self.w.save())
        self.w.set_project(load_project(path), path)

        def browse(dialog):
            self.assertEqual(dialog.versions.count(), 2)
            QTest.keyClick(dialog.versions, Qt.Key_Down)
            self.assertEqual(dialog.selected.name, 'Baseline')
            self.assertIn('R1 · Value · 20k → 10k', dialog.preview.toPlainText())
            self.assertIn('Before tuning', dialog.preview.toPlainText())
            dialog.comparison.setCurrentIndex(1)
            self.assertIn('Tuned', dialog.comparison.currentText())
            QTest.keyClick(dialog.versions, Qt.Key_Return)
            self.assertEqual(self.resistor()['value'], '20k')
            with patch.object(ProjectVersions, 'save', side_effect=OSError('Disk full')):
                dialog.restore_button.click()
            self.assertIn('Disk full', dialog.message.text())
            self.assertEqual(self.resistor()['value'], '20k')
            dialog.restore_button.click()
            self.assertEqual(self.resistor()['value'], '10k')

        invoke('Browse Versions…', VersionHistoryDialog, browse)
        self.assertEqual(load_project(path)['cells'][0]['devices'][1]['value'], '20k')
        store = ProjectVersions(path, self.w.project['id'])
        self.assertEqual(store.list()[0].name, 'Before restoring Baseline')
        self.w.undo_action.trigger()
        self.assertEqual(self.resistor()['value'], '20k')
        self.w.redo_action.trigger()
        self.assertEqual(self.resistor()['value'], '10k')

    @unittest.skipUnless(shutil.which('git'), 'Git is required for the branch workflow')
    def test_branch_merge_reviews_conflicts_before_changing_the_design(self):
        from icstudio.project_branches_ui import BranchesDialog, MergeDialog
        from icstudio.project_versions_ui import version_store

        path = self.root / 'Branch review.icproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')):
            self.assertTrue(self.w.save())
        version_store(self.w).save(self.w.project, 'Earlier local version')
        dialog = BranchesDialog(self.w)
        self.addCleanup(dialog.deleteLater)
        dialog.show()
        dialog.buttons['start'].click()
        self.assertEqual(dialog.active.name, 'main')

        def select(name):
            row = next(i for i in range(dialog.list.count())
                       if dialog.list.item(i).data(Qt.UserRole).name == name)
            dialog.list.setCurrentRow(row)

        def edit(value):
            self.w.select([self.resistor()['id']], 'schematic')
            field = self.w.form_fields['Value']
            field.selectAll()
            QTest.keyClicks(field, value)
            self.assertTrue(self.w.flush_inspector())

        with patch.object(QInputDialog, 'getText', return_value=('tuning', True)):
            dialog.buttons['new'].click()
        self.assertEqual(dialog.active.name, 'tuning')
        edit('47k')
        select('main')
        dialog.buttons['switch'].click()
        self.assertIn('Save a version', dialog.message.text())
        version_store(self.w).save(self.w.project, 'Try 47k')
        dialog.reload()
        select('main')
        dialog.buttons['switch'].click()
        self.assertEqual(self.resistor()['value'], '10k')
        edit('20k')
        version_store(self.w).save(self.w.project, 'Tune to 20k')
        dialog.reload()
        self.assertIn('Earlier local version', [row.name for row in version_store(self.w).list()])
        select('tuning')
        prior = dialog.active.head

        def review(commit):
            window = self.app.activeModalWidget()
            try:
                self.assertIsInstance(window, MergeDialog)
                self.assertEqual(window.conflict_list.count(), 1)
                self.assertIn('R1 / Value', window.conflict_list.item(0).text())
                self.assertEqual([v.toPlainText() for v in window.values], ['"20k"', '"47k"'])
                self.assertEqual(window.base_value.toPlainText(), '"10k"')
                self.assertFalse(window.merge_button.isEnabled())
                QTest.keyClick(window.conflict_list, Qt.Key_Return)
                self.assertEqual(self.resistor()['value'], '20k')
                window.choice.setCurrentIndex(window.choice.findData('incoming'))
                self.assertIn('20k → 47k', window.changes.toPlainText())
                if commit:
                    window.merge_button.click()
                else:
                    QTest.keyClick(window, Qt.Key_Escape)
            finally:
                if window and window.isVisible():
                    window.reject()

        QTimer.singleShot(0, lambda: review(False))
        dialog.buttons['merge'].click()
        self.assertEqual(dialog.git.active().head, prior)
        self.assertEqual(self.resistor()['value'], '20k')
        QTimer.singleShot(0, lambda: review(True))
        dialog.buttons['merge'].click()
        self.assertNotEqual(dialog.git.active().head, prior)
        self.assertEqual(self.resistor()['value'], '47k')
        self.assertEqual(load_project(path)['cells'][0]['devices'][1]['value'], '10k')
        dialog.reject()
        self.w.undo_action.trigger()
        self.assertEqual(self.resistor()['value'], '20k')

    def test_github_pull_request_create_review_and_merge_from_branch_window(self):
        from PySide6.QtWidgets import QComboBox, QDialog, QLineEdit, QPlainTextEdit, QPushButton
        from icstudio.github_pull_requests import GitHubPullRequests
        from icstudio.github_pull_requests_ui import PullRequestsDialog
        from icstudio.project_branches_ui import BranchesDialog
        from tests.test_github_pull_requests import pull_json

        class GitHubFixture(GitHubPullRequests):
            def __init__(self):
                super().__init__('https://github.com/designer/filter.git')
                self.requests = {21: pull_json(21)}
                self.reviews = []
                self.merges = []

            def api(self, endpoint, *, method='GET', data=None, paginate=False):
                if endpoint == '':
                    return {'default_branch': 'main', 'allow_rebase_merge': False}
                if endpoint.startswith('/branches?'):
                    return [{'name': 'main'}, {'name': 'tuning'}]
                if endpoint.startswith('/pulls?'):
                    return [clone(row) for row in self.requests.values() if row['state'] == 'open']
                if endpoint == '/pulls' and method == 'POST':
                    self.requests[42] = pull_json(title=data['title'])
                    return clone(self.requests[42])
                pieces = endpoint.split('?')[0].split('/')
                number = int(pieces[2])
                if len(pieces) == 3:
                    return clone(self.requests[number])
                if pieces[3] == 'files':
                    return [{'filename': 'project.icproj', 'patch': '-10k\n+20k', 'status': 'modified',
                             'additions': 1, 'deletions': 1}]
                if pieces[3] == 'reviews':
                    if method == 'POST':
                        row = {'state': 'APPROVED', 'body': data['body'], 'commit_id': data['commit_id'],
                               'user': {'login': 'reviewer'}}
                        self.reviews.append(row)
                        return row
                    return clone(self.reviews)
                if pieces[3] == 'merge' and method == 'PUT':
                    self.merges.append(data)
                    self.requests[number].update(merged=True, state='closed')
                    return {'merged': True}
                raise AssertionError(endpoint)

        path = self.root / 'Pull requests.icproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')):
            self.assertTrue(self.w.save())
        branch_window = BranchesDialog(self.w)
        self.addCleanup(branch_window.deleteLater)
        branch_window.remote = 'https://github.com/designer/filter.git'
        branch_window.controls()
        branch_window.show()
        client = GitHubFixture()

        def wait_for(ready):
            deadline = time.monotonic() + 6
            while not ready() and time.monotonic() < deadline:
                QTest.qWait(10)
            self.assertTrue(ready(), 'Pull request operation did not finish')

        def form(window, heading, action):
            timer = QTimer(window)

            def use():
                dialog = self.app.activeModalWidget()
                if not isinstance(dialog, QDialog) or dialog.windowTitle() != heading:
                    return
                timer.stop()
                try:
                    action(dialog)
                finally:
                    if dialog.isVisible():
                        dialog.reject()

            timer.timeout.connect(use)
            timer.start(10)
            return timer

        def widget(dialog, kind, name):
            return next(w for w in dialog.findChildren(kind) if w.accessibleName() == name)

        def click(dialog, text):
            next(b for b in dialog.findChildren(QPushButton) if b.text() == text).click()

        def create(form_dialog):
            title = widget(form_dialog, QLineEdit, 'Pull request title')
            QTest.keyClicks(title, 'Tune the RC filter')
            click(form_dialog, 'Create Pull Request')

        def approve(form_dialog):
            action = widget(form_dialog, QComboBox, 'Review action')
            action.setCurrentIndex(action.findData('APPROVE'))
            widget(form_dialog, QPlainTextEdit, 'Review comment').setPlainText('Checked the new resistance.')
            click(form_dialog, 'Submit Review')

        def confirm(form_dialog):
            method = widget(form_dialog, QComboBox, 'Merge method')
            method.setCurrentIndex(method.findData('squash'))
            self.assertFalse(any(b.isDefault() for b in form_dialog.findChildren(QPushButton)))
            click(form_dialog, 'Merge Pull Request')

        def use_window():
            window = self.app.activeModalWidget()
            try:
                self.assertIsInstance(window, PullRequestsDialog)
                wait_for(lambda: window.detail is not None and window.worker is None)
                timer = form(window, 'New Pull Request', create)
                window.new_button.click()
                wait_for(lambda: window.detail is not None and window.detail.request.number == 42 and window.worker is None)
                timer.stop()
                self.assertEqual(window.requests.count(), 2)
                self.assertIn('+20k', window.patch.toPlainText())
                self.assertIn('Tune the RC filter', window.overview.toPlainText())

                timer = form(window, 'Review Pull Request #42', approve)
                window.review_button.click()
                wait_for(lambda: 'Checked the new resistance.' in window.reviews.toPlainText() and window.worker is None)
                timer.stop()
                self.assertEqual(client.reviews[0]['commit_id'], 'a' * 40)

                client.requests[42]['head']['sha'] = 'c' * 40
                timer = form(window, 'Merge Pull Request #42', confirm)
                window.merge_button.click()
                wait_for(lambda: 'The base or head changed' in window.message.text() and window.worker is None)
                timer.stop()
                self.assertEqual(client.merges, [])
                window.refresh_button.click()
                wait_for(lambda: window.detail is not None and window.detail.request.head_sha == 'c' * 40)
                timer = form(window, 'Merge Pull Request #42', confirm)
                window.merge_button.click()
                wait_for(lambda: window.detail is not None and window.detail.request.merged)
                timer.stop()
                self.assertEqual(client.merges, [{'sha': 'c' * 40, 'merge_method': 'squash'}])
                self.assertFalse(window.merge_button.isEnabled())
                self.assertEqual(self.resistor()['value'], '10k')
            finally:
                if window and window.isVisible():
                    window.reject()

        with patch('icstudio.github_pull_requests_ui.GitHubPullRequests', return_value=client):
            QTimer.singleShot(0, use_window)
            branch_window.buttons['pr'].click()
        branch_window.reject()

    def other_cell(self):
        p = clone(self.w.project)
        child = example('empty')['cells'][0]
        child['name'] = 'Other_cell'
        p['cells'].append(child)
        self.w.set_project(p)
        self.app.processEvents()
        return child['id']

    def context_menu(self, target, action=None):
        item = next(self.w.tree.topLevelItem(i) for i in range(self.w.tree.topLevelItemCount())
                    if self.w.tree.topLevelItem(i).data(0, Qt.UserRole)[1]==target)
        self.w.tree.expandAll()
        self.app.processEvents()
        pos = self.w.tree.visualItemRect(item).center()
        # Deliver the actual tree context event; simulate only menu dismissal
        # or selection so headless/native runners need no pointer interaction.
        with patch('icstudio.project_ui.QMenu') as menu_type:
            callbacks = {}
            menu_type.return_value.addAction.side_effect = lambda title, fn:callbacks.update({title:fn})
            if action:
                menu_type.return_value.exec.side_effect = lambda *_:callbacks[action]()
            QApplication.sendEvent(self.w.tree.viewport(), QContextMenuEvent(
                QContextMenuEvent.Mouse, pos, self.w.tree.viewport().mapToGlobal(pos)))

    def save_current(self):
        path = self.root/'current.icproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')):
            self.assertTrue(self.w.save())
        return path

    def test_dismissing_other_cell_menu_preserves_canvas_and_property_draft(self):
        target = self.other_cell()
        original = self.w.cid
        r = self.resistor()
        self.w.select([r['id']])
        self.w.form_fields['Value'].setText('22k')
        self.context_menu(target)
        self.assertEqual(self.w.cid, original)
        self.assertEqual(self.w.schematic.cell['id'], original)
        self.assertEqual(self.w.form_fields['Value'].text(), '22k')
        self.assertTrue(self.w._inspector_dirty)
        self.w.begin_placement(1)
        self.w.place_device_at(120, 90)
        self.assertEqual(len(self.w.cell['devices']), 4)
        self.assertEqual(next(d for d in self.w.cell['devices'] if d['id']==r['id'])['value'], '22k')
        self.assertEqual(next(c for c in self.w.project['cells'] if c['id']==target)['devices'], [])

    def test_context_action_applies_old_cell_draft_then_visibly_activates_target(self):
        target = self.other_cell()
        original = self.w.cid
        r = self.resistor()
        self.w.select([r['id']])
        self.w.form_fields['Value'].setText('22k')
        with patch.object(QInputDialog, 'getText', return_value=('Renamed_child', True)):
            self.context_menu(target, 'Rename cell…')
        self.assertEqual(self.w.cid, target)
        self.assertEqual(self.w.schematic.cell['id'], target)
        self.assertEqual(self.w.cell['name'], 'Renamed_child')
        old = next(c for c in self.w.project['cells'] if c['id']==original)
        self.assertEqual(next(d for d in old['devices'] if d['id']==r['id'])['value'], '22k')

    def test_invalid_property_prevents_context_action_without_retargeting(self):
        target = self.other_cell()
        original = self.w.cid
        self.w.select([self.resistor()['id']])
        self.w.form_fields['X'].setText('invalid coordinate')
        before = clone(self.w.project)
        with patch.object(QInputDialog, 'getText') as rename:
            self.context_menu(target, 'Rename cell…')
            rename.assert_not_called()
        self.assertEqual(self.w.cid, original)
        self.assertEqual(self.w.project, before)
        self.assertTrue(self.w._inspector_dirty)
        self.assertEqual(self.w.form_fields['X'].text(), 'invalid coordinate')
        self.assertTrue(self.w.property_error.text())

    def test_undo_resolves_pending_property_before_earlier_committed_operation(self):
        self.w.commit(lambda p:p.update(name='Committed rename'), 'Rename project')
        self.w.select([self.resistor()['id']])
        self.w.form_fields['Value'].setText('22k')
        self.w.undo_action.trigger()
        self.assertEqual(self.w.project['name'], 'Committed rename')
        self.assertEqual(self.resistor()['value'], '10k')
        self.w.redo_action.trigger()
        self.assertEqual(self.resistor()['value'], '22k')

    def test_redo_preserves_pending_property_as_a_new_history_branch(self):
        self.w.commit(lambda p:p.update(name='Committed rename'), 'Rename project')
        self.w.undo_action.trigger()
        self.w.select([self.resistor()['id']])
        self.w.form_fields['Value'].setText('22k')
        self.w.redo_action.trigger()
        self.assertEqual(self.w.project['name'], 'RC low-pass')
        self.assertEqual(self.resistor()['value'], '22k')
        self.assertEqual(self.w.form_fields['Value'].text(), '22k')
        self.assertFalse(self.w._inspector_dirty)
        self.assertFalse(self.w.history.redo_stack)

    def test_invalid_properties_block_undo_and_redo_without_losing_input(self):
        for action in ('undo_action', 'redo_action'):
            with self.subTest(action=action):
                self.w._inspector_dirty = False
                self.w.set_project(example('rc'))
                self.w.commit(lambda p:p.update(name='Committed rename'), 'Rename project')
                if action=='redo_action':self.w.undo_action.trigger()
                self.w.select([self.resistor()['id']])
                self.w.form_fields['X'].setText('invalid coordinate')
                before = clone(self.w.project)
                getattr(self.w, action).trigger()
                self.assertEqual(self.w.project, before)
                self.assertEqual(self.w.form_fields['X'].text(), 'invalid coordinate')
                self.assertTrue(self.w._inspector_dirty)

    def test_save_never_discards_or_publishes_invalid_analysis_settings(self):
        path = self.save_current()
        before = path.read_bytes()
        self.w.analysis_fields['step'].setText('0')
        with patch.object(QMessageBox, 'question') as prompt:
            self.assertFalse(self.w.save())
            prompt.assert_not_called()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.w.analysis_fields['step'].text(), '0')
        self.assertTrue(self.w.analysis_dirty)

    def test_cancel_close_preserves_invalid_analysis_and_document(self):
        before = clone(self.w.project)
        self.w.analysis_fields['step'].setText('0')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel) as prompt:
            self.assertFalse(self.w.close())
            self.assertEqual(prompt.call_args.args[1], 'Invalid analysis settings')
        self.assertTrue(self.w.isVisible())
        self.assertEqual(self.w.project, before)
        self.assertEqual(self.w.analysis_fields['step'].text(), '0')
        self.assertTrue(self.w.analysis_dirty)

    def test_discard_invalid_analysis_can_close_without_changing_saved_project(self):
        path = self.save_current()
        before = path.read_bytes()
        step = self.w.project['analysis']['step']
        self.w.analysis_fields['step'].setText('0')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            self.assertTrue(self.w.close())
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(load_project(path)['analysis']['step'], step)
        self.assertEqual(self.w.analysis_fields['step'].text(), str(step))
        self.assertFalse(self.w.analysis_dirty)

    def test_pristine_gallery_navigation_resolves_invalid_analysis_before_shortcut(self):
        self.w._initial_document = digest(self.w.project)
        original = self.w.project['id']
        self.w.analysis_fields['step'].setText('0')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel):
            self.assertFalse(self.w.open_gallery_example(examples()[0]))
        self.assertEqual(self.w.project['id'], original)
        self.assertEqual(self.w.analysis_fields['step'].text(), '0')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            self.assertTrue(self.w.open_gallery_example(examples()[0]))
        self.assertNotEqual(self.w.project['id'], original)

    def test_project_hub_open_offers_cancel_or_discard_for_invalid_analysis(self):
        path = self.root/'other.icproj'
        save_project(example('inverter'), path)
        before = path.read_bytes()
        original = self.w.project['id']
        hub = ProjectHub(self.w, 'projects')
        self.w.analysis_fields['step'].setText('0')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel):
            hub.open_path(path)
        self.assertEqual(self.w.project['id'], original)
        self.assertEqual(self.w.analysis_fields['step'].text(), '0')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            hub.open_path(path)
        self.assertEqual(self.w.path, path)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(self.w.analysis_dirty)
        hub.close()

    def test_pristine_gallery_valid_analysis_edit_requires_save_decision(self):
        self.w._initial_document = digest(self.w.project)
        original = self.w.project['id']
        self.w.analysis_fields['step'].setText('400n')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel) as prompt:
            self.assertFalse(self.w.open_gallery_example(examples()[0]))
            self.assertEqual(prompt.call_args.args[1], 'Save project?')
        self.assertEqual(self.w.project['id'], original)
        self.assertEqual(self.w.project['analysis']['step'], '400n')
        self.assertEqual(self.w.analysis_fields['step'].text(), '400n')

    def test_batch_run_respects_an_empty_plan_and_unchecked_setups(self):
        for setup_count in (0, 2):
            with self.subTest(setup_count=setup_count):
                self.w.set_project(example('rc'))
                for row in range(setup_count):
                    self.w.add_simulation_setup()
                    self.w.setup_table.item(row, 0).setCheckState(Qt.Unchecked)
                before = clone(self.w.project)
                self.w.run_enabled_setups()
                self.assertEqual(self.w.project, before)
                self.assertEqual(self.w.run_manager.rows, [])

    def test_run_selected_setup_uses_the_saved_settings_and_creates_one_result(self):
        for stop in ('25u', '50u'):
            self.w.analysis_fields['stop'].setText(stop)
            self.w.add_simulation_setup()
        self.w.setup_table.item(0, 0).setCheckState(Qt.Unchecked)
        self.w.setup_table.clearSelection()
        self.assertFalse(self.w.run_selected_setup_button.isEnabled())
        self.w.setup_table.selectRow(0)
        self.w.open_simulation_explorer()
        self.assertTrue(self.w.run_selected_setup_button.isEnabled())
        self.w.run_selected_setup_button.click()
        self.finish_runs()
        self.assertEqual(len(self.w.run_manager.rows), 1)
        row = self.w.run_manager.rows[0]
        self.assertEqual(row['state'], 'Complete', row['log'])
        self.assertEqual(row['job']['settings']['stop'], '25u')
        self.assertGreater(max(row['result']['traces']['vout']), 0)
        self.assertEqual(self.w.setup_table.item(0, 0).checkState(), Qt.Unchecked)

    def test_rc_edits_compare_historical_runs_and_reopen_only_completed_results(self):
        import shutil
        from icstudio import job_store

        self.w.add_simulation_setup()
        original=self.resistor()['value']
        for value in (original,'24k','47k'):
            if value!=self.resistor()['value']:
                self.w.select([self.resistor()['id']]);self.w.form_fields['Value'].setText(value)
            self.w.quick_run();self.finish_runs()
            self.assertEqual(self.w.run_manager.rows[-1]['state'],'Complete')
        self.w.undo();self.assertEqual(self.resistor()['value'],'24k')
        self.w.redo();self.assertEqual(self.resistor()['value'],'47k')
        runs=list(self.w.jobs)
        self.w.compare_combo.setCurrentIndex(self.w.compare_combo.findData(0))
        self.assertIs(self.w.plot.result,runs[2]);self.assertIs(self.w.plot.compare,runs[0])
        self.assertGreater(abs(runs[2]['traces']['vout'][50]-runs[0]['traces']['vout'][50]),.05)
        self.assertIn('r'+str(runs[0]['revision']),self.w.compare_combo.currentText())
        self.assertIn(runs[0]['engine'],self.w.compare_combo.currentText())
        failed=self.w.run_manager.rows[0]['path'].with_name('cancelled result on disk')
        shutil.copytree(self.w.run_manager.rows[0]['path'],failed)
        job_store.state(failed,'cancelled')
        folder=self.root/'Project with spaces';folder.mkdir()
        path=folder/'RC comparison.icproj'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(path),'')):
            self.assertTrue(self.w.save())
        self.w.set_project(example('empty'))
        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(path),'')),\
                patch.object(QMessageBox,'question',return_value=QMessageBox.Discard):
            self.w.open_project()
        self.assertEqual(self.resistor()['value'],'47k')
        self.assertEqual(len(self.w.project['simulation_setups']),1)
        self.assertCountEqual([r['design_hash'] for r in self.w.jobs],[r['design_hash'] for r in runs])
        self.assertIn('Run was not completed',self.w.console.toPlainText())

    def test_edit_saved_program_restores_its_waveforms_and_runtime(self):
        from icstudio.native_migration import review_path
        from tests.test_native_migration import divider

        source = divider(self.root/'Program source with spaces', hierarchical=True, include=True)
        reviewed = review_path(source)
        self.assertEqual(reviewed['status'], 'Complete', reviewed['items'])
        self.w.set_project(reviewed['candidate'])
        for probes, minutes in (('v(out)', 23), ('v(in)', 41)):
            self.w.xschem_probes.setText(probes)
            self.w.xschem_timeout.setValue(minutes)
            self.w.add_simulation_setup()
        self.w.setup_table.selectRow(0)
        self.w.edit_simulation_setup()
        self.assertEqual(self.w.xschem_probes.text(), 'v(out)')
        self.assertEqual(self.w.xschem_timeout.value(), 23)
        self.w.update_simulation_setup()
        self.assertEqual(self.w.project['simulation_setups'][0]['settings']['timeout'], 23*60)

    def test_main_stop_cancels_new_worker_when_completed_run_is_selected(self):
        self.w.quick_run()
        self.finish_runs()
        completed = self.w.run_manager.rows[0]
        self.assertEqual(completed['state'], 'Complete', completed['log'])
        self.w.simulation_runs.selectRow(0)
        row = self.w.start_job(clone(self.w.project['analysis']), 'builtin')
        self.assertEqual(self.w.selected_simulation_runs(), [completed])
        self.w.cancel_action.trigger()
        self.assertIn(row['state'], ('Stopping', 'Cancelled'))
        self.finish_runs()
        self.assertEqual(row['state'], 'Cancelled')
        self.assertEqual(completed['state'], 'Complete')
        self.assertNotIn('result', row)

    def test_main_stop_prefers_running_fallback_but_honors_selected_queued_run(self):
        self.w.parallel_jobs.setValue(1)
        self.w.quick_run()
        self.finish_runs()
        self.assertEqual(self.w.run_manager.rows[0]['state'], 'Complete')
        for select_queued in (False, True):
            with self.subTest(select_queued=select_queued):
                self.w.simulation_runs.selectRow(0)
                running = self.w.start_job(clone(self.w.project['analysis']), 'builtin')
                queued = self.w.start_job(clone(self.w.project['analysis']), 'builtin')
                self.assertEqual((running['state'], queued['state']), ('Running', 'Queued'))
                if select_queued:self.w.simulation_runs.selectRow(self.w.run_manager.rows.index(queued))
                self.w.cancel_action.trigger()
                if select_queued:
                    self.assertEqual(queued['state'], 'Cancelled')
                    self.assertEqual(running['state'], 'Running')
                else:
                    self.assertIn(running['state'], ('Stopping', 'Cancelled'))
                    self.assertEqual(queued['state'], 'Queued')
                self.finish_runs()
                self.assertEqual(running['state'], 'Complete' if select_queued else 'Cancelled')
                self.assertEqual(queued['state'], 'Cancelled' if select_queued else 'Complete')


if __name__=='__main__':
    unittest.main()
