"""Real desktop save/open guards and folder snapshots, without external engines.

Run in a fresh process: a prior QCoreApplication cannot own these widgets.
Only dialog answers and selected paths are supplied by the test. Project
loading, dirty-state decisions, saving, editor drafts and controls are real.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFileDialog, QInputDialog, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton

from icstudio.gui import Studio, StudioCore
from icstudio.model import clone, digest, example, file_digest, load_project, save_project, uid
from icstudio.project_hub_ui import ProjectHub
from icstudio.project_store import load_directory, save_directory
from icstudio.project_ui import ProjectMixin


ROUTES = ('file', 'core', 'hub', 'manager')


class ProjectDataSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = tempfile.TemporaryDirectory(prefix='icstudio-data-safety-')
        cls.root = Path(cls.profile.name)
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        cls.settings = QSettings(str(cls.root / 'settings.ini'), QSettings.IniFormat)
        cls.settings.setFallbacksEnabled(False)
        with patch('icstudio.gui.QSettings', return_value=cls.settings), \
                patch('icstudio.gui.QStandardPaths.writableLocation', return_value=str(cls.root / 'data')):
            cls.window = Studio(recover=False)
        cls.errors = []
        cls.window.error = cls.errors.append
        cls.window.live_check.setChecked(False)
        cls.window.settings.setValue('digital/toolchain', 'custom')
        cls.old_excepthook = sys.excepthook
        sys.excepthook = lambda typ, value, tb: cls.errors.append(str(value))
        cls.serial = 0

    @classmethod
    def tearDownClass(cls):
        try:
            cls.window._inspector_dirty = False
            cls.window.analysis_dirty = False
            digital = getattr(cls.window, '_digital_window', None)
            if digital:
                digital.dirty = False
            cls.window.saved_hash = digest(cls.window.project)
            cls.window.close()
            cls.app.processEvents()
        finally:
            sys.excepthook = cls.old_excepthook
            cls.profile.cleanup()

    def prepare(self, dirty=True):
        """An isolated real saved project and one unapologetically unsaved edit."""
        w = self.window
        w._inspector_dirty = False
        w.analysis_dirty = False
        digital = getattr(w, '_digital_window', None)
        if digital:
            digital.dirty = False
        type(self).serial += 1
        folder = self.root / str(self.serial)
        folder.mkdir()
        path = folder / 'design with spaces.icproj'
        original = example()
        original['name'] = 'Original saved design'
        save_project(original, path)
        w.set_project(load_project(path), path)
        self.assertTrue(w.save())  # Persist generated wire IDs, as an ordinary Studio save does.
        original = clone(w.project)  # Include the editor's normal canonical defaults.
        if dirty:
            w.commit(lambda p: p.update(name='Important unsaved edit'), 'Audit edit')
        self.errors.clear()
        return path, original

    def invoke_open(self, route, target):
        """Exercise actual entry points; include the legacy dialog's Open button."""
        w = self.window
        dialog = None
        self.last_dialog_result = None
        try:
            with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(target), '')):
                if route == 'file':
                    w.open_project()
                elif route == 'core':
                    StudioCore.open_project(w)
                elif route == 'hub':
                    dialog = ProjectHub(w, 'projects')
                    dialog.open_path(target)
                    if dialog.state.text():
                        self.errors.append(dialog.state.text())
                else:
                    w.project_index.remember(w.project, target)
                    ProjectMixin.project_manager(w)
                    dialog = w._projects_dialog
                    items = dialog.findChild(QListWidget)
                    item = next(items.item(i) for i in range(items.count())
                                if items.item(i).data(Qt.UserRole)['path'] == str(Path(target).resolve()))
                    items.setCurrentItem(item)
                    next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Open').click()
                    self.errors.extend(label.text() for label in dialog.findChildren(QLabel)
                                       if label.text() and label.text() != 'PROJECT WORKSPACE')
        except (OSError, ValueError, KeyError) as exc:
            self.errors.append(str(exc))
        finally:
            if dialog:
                self.last_dialog_result = dialog.result()
                dialog.close()
                dialog.deleteLater()

    def test_same_file_save_reloads_saved_edits_and_next_save_preserves_them(self):
        for route in ROUTES:
            with self.subTest(route=route):
                path, _ = self.prepare()
                with patch.object(QMessageBox, 'question', return_value=QMessageBox.Save) as prompt:
                    self.invoke_open(route, path)
                self.assertEqual(prompt.call_count, 1)
                self.assertEqual(self.errors, [])
                self.assertEqual(self.window.project['name'], 'Important unsaved edit')
                self.assertEqual(load_project(path)['name'], 'Important unsaved edit')
                self.assertEqual(self.window.saved_hash, digest(self.window.project))
                self.assertEqual(self.window._disk_hash, file_digest(path))
                self.window.commit(lambda p: p['cells'][0].update(name='Next_edit'), 'Later edit')
                self.assertTrue(self.window.save())
                reopened = load_project(path)
                self.assertEqual(reopened['name'], 'Important unsaved edit')
                self.assertEqual(reopened['cells'][0]['name'], 'Next_edit')

    def test_same_file_save_flushes_real_pending_inspector_and_analysis_drafts(self):
        for route in ROUTES:
            with self.subTest(route=route):
                path, _ = self.prepare(dirty=False)
                rid = self.pending_resistor('22k')
                self.window.analysis_fields['stop'].setText('250u')
                with patch.object(QMessageBox, 'question', return_value=QMessageBox.Save):
                    self.invoke_open(route, path)
                self.assertEqual(self.errors, [])
                for project in (self.window.project, load_project(path)):
                    self.assertEqual(next(d for d in project['cells'][0]['devices'] if d['id'] == rid)['value'], '22k')
                    self.assertEqual(project['analysis']['stop'], '250u')

    def test_same_file_save_flushes_real_pending_digital_source(self):
        from icstudio.digital import counter_project
        for route in ('file', 'hub'):
            with self.subTest(route=route):
                path, _ = self.prepare(dirty=False)
                project = counter_project()
                save_project(project, path)
                self.window.set_project(load_project(path), path)
                digital = self.window.digital_window()
                digital.files.setCurrentRow(0)
                digital.editor.insertPlainText('// Pending open/save source\n')
                self.assertTrue(digital.dirty)
                with patch.object(QMessageBox, 'question', return_value=QMessageBox.Save):
                    self.invoke_open(route, path)
                self.assertEqual(self.errors, [])
                for project in (self.window.project, load_project(path)):
                    self.assertIn('Pending open/save source', project['digital']['files'][0]['text'])

    def test_save_as_over_selected_target_reloads_the_new_saved_document(self):
        for route in ROUTES:
            with self.subTest(route=route):
                path, _ = self.prepare()
                target = path.parent / 'selected target.icproj'
                save_project(example(), target)
                self.window.path = None
                self.window.saved_hash = None
                with patch.object(QMessageBox, 'question', return_value=QMessageBox.Save), \
                        patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
                    self.invoke_open(route, target)
                self.assertEqual(self.errors, [])
                self.assertEqual(self.window.project['name'], 'Important unsaved edit')
                self.assertEqual(load_project(target)['name'], 'Important unsaved edit')
                # Windows may canonicalize an 8.3 temp-path alias in the project index.
                self.assertTrue(self.window.path.samefile(target))

    def test_cancelled_save_never_replaces_current_document(self):
        for route in ROUTES:
            with self.subTest(route=route):
                path, _ = self.prepare()
                before = clone(self.window.project)
                with patch.object(QMessageBox, 'question', return_value=QMessageBox.Save), \
                        patch.object(self.window, 'save', return_value=False), \
                        patch.object(self.window, 'set_project', side_effect=AssertionError('Cancelled save replaced project')):
                    self.invoke_open(route, path)
                self.assertEqual(self.errors, [])
                self.assertEqual(digest(self.window.project), digest(before))

    def test_refused_document_switch_does_not_accept_hub_or_manager_dialog(self):
        for route in ('hub', 'manager'):
            with self.subTest(route=route):
                path, _ = self.prepare()
                before = clone(self.window.project)
                with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard), \
                        patch.object(self.window, 'set_project', return_value=False):
                    self.invoke_open(route, path)
                self.assertEqual(self.errors, [])
                self.assertEqual(self.last_dialog_result, 0)
                self.assertEqual(digest(self.window.project), digest(before))

    def test_discard_loads_disk_and_cancel_preserves_current_work(self):
        for route in ROUTES:
            for choice in (QMessageBox.Discard, QMessageBox.Cancel):
                with self.subTest(route=route, choice=choice):
                    path, original = self.prepare()
                    before = clone(self.window.project)
                    disk = path.read_bytes()
                    with patch.object(QMessageBox, 'question', return_value=choice) as prompt:
                        self.invoke_open(route, path)
                    self.assertEqual(prompt.call_count, 1)
                    self.assertEqual(self.errors, [])
                    self.assertEqual(path.read_bytes(), disk)
                    expected = original if choice == QMessageBox.Discard else before
                    self.assertEqual(digest(self.window.project), digest(expected))

    def test_invalid_or_missing_target_is_rejected_before_save_prompt(self):
        for route in ROUTES:
            for invalid in (False, True):
                with self.subTest(route=route, invalid=invalid):
                    path, _ = self.prepare()
                    target = path.parent / 'invalid.icproj'
                    if invalid:
                        target.write_text('{not a project', encoding='utf-8')
                    before = clone(self.window.project)
                    disk = path.read_bytes()
                    with patch.object(QMessageBox, 'question', side_effect=AssertionError('Must preflight target')):
                        self.invoke_open(route, target)
                    self.assertTrue(self.errors)
                    self.assertEqual(digest(self.window.project), digest(before))
                    self.assertEqual(path.read_bytes(), disk)
                    self.assertEqual(self.window.path, path)

    def test_failed_save_keeps_edits_current_and_original_file_intact(self):
        for route in ROUTES:
            with self.subTest(route=route):
                path, _ = self.prepare()
                before = clone(self.window.project)
                disk = path.read_bytes()
                with patch.object(QMessageBox, 'question', return_value=QMessageBox.Save), \
                        patch('icstudio.gui.save_project', side_effect=OSError('Injected disk full')):
                    self.invoke_open(route, path)
                self.assertTrue(any('Injected disk full' in error for error in self.errors), self.errors)
                self.assertEqual(digest(self.window.project), digest(before))
                self.assertEqual(path.read_bytes(), disk)
                self.assertNotEqual(self.window.saved_hash, digest(self.window.project))

    def test_target_changed_during_prompt_uses_latest_valid_bytes(self):
        for route in ROUTES:
            with self.subTest(route=route):
                path, _ = self.prepare()
                target = path.parent / 'other.icproj'
                other = example()
                save_project(other, target)
                def answer(*args, **kwargs):
                    other['name'] = 'Latest target revision'
                    save_project(other, target)
                    return QMessageBox.Discard
                with patch.object(QMessageBox, 'question', side_effect=answer):
                    self.invoke_open(route, target)
                self.assertEqual(self.errors, [])
                self.assertEqual(self.window.project['name'], 'Latest target revision')
                self.assertEqual(self.window._disk_hash, file_digest(target))

    def test_target_invalidated_during_prompt_does_not_replace_current_project(self):
        for route in ROUTES:
            for remove in (False, True):
                with self.subTest(route=route, remove=remove):
                    path, _ = self.prepare()
                    target = path.parent / 'other.icproj'
                    save_project(example(), target)
                    before = clone(self.window.project)
                    def answer(*args, **kwargs):
                        if remove:
                            target.unlink()
                        else:
                            target.write_text('{invalidated during prompt', encoding='utf-8')
                        return QMessageBox.Discard
                    with patch.object(QMessageBox, 'question', side_effect=answer):
                        self.invoke_open(route, target)
                    self.assertTrue(self.errors)
                    self.assertEqual(digest(self.window.project), digest(before))
                    self.assertEqual(self.window.path, path)

    def pending_resistor(self, value):
        resistor = next(d for d in self.window.cell['devices'] if d['kind'] == 'R')
        self.window.select([resistor['id']])
        self.window.form_fields['Value'].setText(value)
        self.assertTrue(self.window._inspector_dirty)
        return resistor['id']

    def test_folder_snapshot_contains_pending_inspector_and_analysis_fields(self):
        path, _ = self.prepare(dirty=False)
        original_saved_hash = self.window.saved_hash
        original_bytes = path.read_bytes()
        rid = self.pending_resistor('22k')
        self.window.analysis_fields['stop'].setText('250u')
        self.assertTrue(self.window.analysis_dirty)
        target = path.parent / 'folder snapshot'
        with patch.object(QFileDialog, 'getExistingDirectory', return_value=str(target)):
            self.window.save_project_folder()
        saved = load_directory(target)
        self.assertEqual(next(d for d in saved['cells'][0]['devices'] if d['id'] == rid)['value'], '22k')
        self.assertEqual(saved['analysis']['stop'], '250u')
        self.assertFalse(self.window._inspector_dirty)
        self.assertFalse(self.window.analysis_dirty)
        self.assertEqual(self.window.path, path, 'A snapshot must not move the active document')
        self.assertEqual(self.window.saved_hash, original_saved_hash)
        self.assertNotEqual(self.window.saved_hash, digest(self.window.project))
        self.assertEqual(path.read_bytes(), original_bytes)

    def test_folder_cancel_does_not_flush_or_create_any_snapshot(self):
        self.prepare(dirty=False)
        self.pending_resistor('22k')
        self.window.analysis_fields['stop'].setText('250u')
        before = clone(self.window.project)
        with patch.object(QFileDialog, 'getExistingDirectory', return_value=''), \
                patch.object(self.window, 'flush_inspector', side_effect=AssertionError('Cancelled snapshot flushed edits')), \
                patch.object(self.window, 'flush_analysis', side_effect=AssertionError('Cancelled snapshot flushed analysis')), \
                patch('icstudio.project_store.save_directory', side_effect=AssertionError('Cancelled snapshot wrote files')):
            self.window.save_project_folder()
        self.assertEqual(digest(self.window.project), digest(before))
        self.assertTrue(self.window._inspector_dirty)
        self.assertTrue(self.window.analysis_dirty)

    def test_invalid_folder_drafts_do_not_write_or_claim_success(self):
        for kind in ('inspector', 'analysis'):
            with self.subTest(kind=kind):
                path, _ = self.prepare(dirty=False)
                if kind == 'inspector':
                    self.pending_resistor('invalid resistance')
                else:
                    self.window.analysis_fields['stop'].setText('invalid time')
                target = path.parent / 'must not exist'
                with patch.object(QFileDialog, 'getExistingDirectory', return_value=str(target)), \
                        patch('icstudio.project_store.save_directory', side_effect=AssertionError('Invalid draft wrote snapshot')), \
                        patch.object(self.window.statusBar(), 'showMessage') as message:
                    self.assertFalse(self.window.save_project_folder())
                self.assertFalse(target.exists())
                self.assertFalse(any('snapshot saved' in str(call) for call in message.call_args_list))

    def test_folder_snapshot_includes_real_digital_source_draft(self):
        from icstudio.digital import counter_project
        path, _ = self.prepare(dirty=False)
        self.window.set_project(counter_project())
        digital = self.window.digital_window()
        digital.files.setCurrentRow(0)
        digital.editor.insertPlainText('// Pending folder snapshot source\n')
        self.assertTrue(digital.dirty)
        with patch.object(QFileDialog, 'getExistingDirectory', return_value=''), \
                patch.object(digital, 'apply', side_effect=AssertionError('Cancelled folder picker applied digital draft')):
            self.window.save_project_folder()
        self.assertTrue(digital.dirty)
        target = path.parent / 'digital snapshot'
        with patch.object(QFileDialog, 'getExistingDirectory', return_value=str(target)):
            self.window.save_project_folder()
        saved = load_directory(target)
        self.assertIn('Pending folder snapshot source', saved['digital']['files'][0]['text'])
        self.assertFalse(digital.dirty)

    def test_failed_digital_draft_does_not_write_folder_snapshot(self):
        from icstudio.digital import counter_project
        path, _ = self.prepare(dirty=False)
        self.window.set_project(counter_project())
        digital = self.window.digital_window()
        digital.editor.insertPlainText('// Retain this failed draft\n')
        target = path.parent / 'must not exist'
        before = clone(self.window.project)
        with patch.object(QFileDialog, 'getExistingDirectory', return_value=str(target)), \
                patch.object(digital, 'apply', side_effect=ValueError('Injected invalid source draft')), \
                patch('icstudio.project_store.save_directory', side_effect=AssertionError('Failed digital draft wrote snapshot')), \
                patch.object(self.window.statusBar(), 'showMessage') as message:
            self.assertFalse(self.window.save_project_folder())
        self.assertFalse(target.exists())
        self.assertEqual(digest(self.window.project), digest(before))
        self.assertTrue(digital.dirty)
        self.assertIn('Injected invalid source draft', digital.message.text())
        self.assertFalse(any('snapshot saved' in str(call) for call in message.call_args_list))

    def test_duplicate_contains_pending_inspector_and_analysis_without_saving_source(self):
        path, _ = self.prepare(dirty=False)
        original_bytes = path.read_bytes()
        original_saved_hash = self.window.saved_hash
        original_id = self.window.project['id']
        rid = self.pending_resistor('33k')
        self.window.analysis_fields['stop'].setText('987u')
        target = path.parent / 'independent analog copy.icproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
            self.window.duplicate_project_dialog()
        copied = load_project(target)
        self.assertEqual(copied['analysis']['stop'], '987u')
        self.assertEqual(next(d for d in copied['cells'][0]['devices'] if d['id'] == rid)['value'], '33k')
        self.assertNotEqual(copied['id'], original_id)
        self.assertEqual(copied['copied_from']['project_id'], original_id)
        self.assertEqual(self.window.project['id'], original_id)
        self.assertEqual(self.window.path, path)
        self.assertEqual(self.window.saved_hash, original_saved_hash)
        self.assertNotEqual(digest(self.window.project), original_saved_hash)
        self.assertEqual(path.read_bytes(), original_bytes)
        self.assertFalse(self.window.analysis_dirty)
        self.assertFalse(self.window._inspector_dirty)
        self.assertTrue(any(entry['id'] == copied['id'] for entry in self.window.project_index.entries()))

    def test_duplicate_contains_pending_digital_source_without_saving_original(self):
        from icstudio.digital import counter_project
        path, _ = self.prepare(dirty=False)
        save_project(counter_project(), path)
        self.window.set_project(load_project(path), path)
        self.assertTrue(self.window.save())
        original_bytes = path.read_bytes()
        original_saved_hash = self.window.saved_hash
        original_id = self.window.project['id']
        digital = self.window.digital_window()
        digital.files.setCurrentRow(0)
        digital.editor.insertPlainText('// Latest independent copy draft\n')
        self.assertTrue(digital.dirty)
        target = path.parent / 'independent digital copy.icproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
            self.window.duplicate_project_dialog()
        copied = load_project(target)
        self.assertIn('Latest independent copy draft', copied['digital']['files'][0]['text'])
        self.assertFalse(digital.dirty)
        self.assertNotEqual(copied['id'], original_id)
        self.assertEqual(copied['copied_from']['project_id'], original_id)
        self.assertEqual(self.window.project['id'], original_id)
        self.assertEqual(self.window.path, path)
        self.assertEqual(self.window.saved_hash, original_saved_hash)
        self.assertNotEqual(digest(self.window.project), original_saved_hash)
        self.assertEqual(path.read_bytes(), original_bytes)

    def test_duplicate_invalid_drafts_do_not_write_index_or_report_success(self):
        from icstudio.digital import counter_project
        for kind in ('inspector', 'analysis', 'digital'):
            with self.subTest(kind=kind):
                path, _ = self.prepare(dirty=False)
                digital = None
                if kind == 'inspector':
                    self.pending_resistor('invalid resistance')
                elif kind == 'analysis':
                    self.window.analysis_fields['stop'].setText('invalid time')
                else:
                    self.window.set_project(counter_project())
                    digital = self.window.digital_window()
                    digital.editor.insertPlainText('// Must remain a draft\n')
                before = clone(self.window.project)
                target = path.parent / 'must not exist.icproj'
                with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')), \
                        patch('icstudio.lifecycle_ui.duplicate_project', side_effect=AssertionError('Invalid draft wrote copy')), \
                        patch.object(self.window.project_index, 'remember', side_effect=AssertionError('Invalid draft indexed copy')), \
                        patch.object(self.window.statusBar(), 'showMessage') as message:
                    if digital:
                        with patch.object(digital, 'apply', side_effect=ValueError('Injected invalid digital copy draft')):
                            self.window.duplicate_project_dialog()
                        self.assertTrue(digital.dirty)
                        self.assertIn('Injected invalid digital copy draft', digital.message.text())
                    else:
                        self.window.duplicate_project_dialog()
                self.assertFalse(target.exists())
                self.assertEqual(digest(self.window.project), digest(before))
                self.assertFalse(any('Created ' in str(call) for call in message.call_args_list))

    def test_duplicate_explicit_draft_refusals_stop_before_writer_and_index(self):
        from icstudio.digital import counter_project
        for kind in ('inspector_after_picker', 'analysis', 'digital'):
            with self.subTest(kind=kind):
                path, _ = self.prepare(dirty=False)
                target = path.parent / 'refused copy.icproj'
                if kind == 'digital':
                    self.window.set_project(counter_project())
                    digital = self.window.digital_window()
                    digital.editor.insertPlainText('// Retain refused draft\n')
                    refusal = patch.object(digital, 'attempt', return_value=False)
                elif kind == 'analysis':
                    refusal = patch.object(self.window, 'flush_analysis', return_value=False)
                else:
                    # idle_edit's established pre-picker flush succeeds; the
                    # additional post-picker guard must still honor refusal.
                    refusal = patch.object(self.window, 'flush_inspector', side_effect=[True, False])
                before = clone(self.window.project)
                with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')), refusal, \
                        patch('icstudio.lifecycle_ui.duplicate_project', side_effect=AssertionError('Refused draft wrote copy')), \
                        patch.object(self.window.project_index, 'remember', side_effect=AssertionError('Refused draft indexed copy')), \
                        patch.object(self.window.statusBar(), 'showMessage') as message:
                    self.window.duplicate_project_dialog()
                self.assertFalse(target.exists())
                self.assertEqual(digest(self.window.project), digest(before))
                self.assertFalse(any('Created ' in str(call) for call in message.call_args_list))

    def test_duplicate_picker_cancel_preserves_analysis_and_digital_drafts(self):
        from icstudio.digital import counter_project
        for kind in ('analysis', 'digital'):
            with self.subTest(kind=kind):
                path, _ = self.prepare(dirty=False)
                if kind == 'analysis':
                    rid = self.pending_resistor('47k')
                    self.window.analysis_fields['stop'].setText('987u')
                    original_stop = self.window.project['analysis']['stop']
                    digital = None
                else:
                    save_project(counter_project(), path)
                    self.window.set_project(load_project(path), path)
                    self.assertTrue(self.window.save())
                    digital = self.window.digital_window()
                    digital.editor.insertPlainText('// Preserve cancelled copy draft\n')
                original_bytes = path.read_bytes()
                original_saved_hash = self.window.saved_hash
                with patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')), \
                        patch.object(self.window, 'flush_analysis', side_effect=AssertionError('Cancelled picker applied analysis')), \
                        patch('icstudio.lifecycle_ui.duplicate_project', side_effect=AssertionError('Cancelled picker wrote copy')), \
                        patch.object(self.window.project_index, 'remember', side_effect=AssertionError('Cancelled picker indexed copy')), \
                        patch.object(self.window.statusBar(), 'showMessage') as message:
                    if digital:
                        with patch.object(digital, 'apply', side_effect=AssertionError('Cancelled picker applied digital draft')):
                            self.window.duplicate_project_dialog()
                        self.assertTrue(digital.dirty)
                    else:
                        self.window.duplicate_project_dialog()
                        self.assertTrue(self.window.analysis_dirty)
                        self.assertEqual(self.window.project['analysis']['stop'], original_stop)
                        # Preserve existing behavior: idle_edit has always
                        # applied valid inspector edits before the picker.
                        self.assertFalse(self.window._inspector_dirty)
                        self.assertEqual(next(d for d in self.window.cell['devices'] if d['id'] == rid)['value'], '47k')
                self.assertEqual(self.window.path, path)
                self.assertEqual(self.window.saved_hash, original_saved_hash)
                self.assertEqual(path.read_bytes(), original_bytes)
                self.assertFalse(any('Created ' in str(call) for call in message.call_args_list))

    def test_duplicate_writer_failure_does_not_index_or_report_success(self):
        path, _ = self.prepare(dirty=False)
        self.window.analysis_fields['stop'].setText('987u')
        original_bytes = path.read_bytes()
        original_saved_hash = self.window.saved_hash
        target = path.parent / 'failed copy.icproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')), \
                patch('icstudio.lifecycle_ui.duplicate_project', side_effect=OSError('Injected copy disk full')), \
                patch.object(self.window.project_index, 'remember', side_effect=AssertionError('Failed copy indexed')), \
                patch.object(self.window.statusBar(), 'showMessage') as message:
            with self.assertRaisesRegex(OSError, 'Injected copy disk full'):
                self.window.duplicate_project_dialog()
        self.assertFalse(target.exists())
        self.assertEqual(self.window.project['analysis']['stop'], '987u')
        self.assertEqual(self.window.path, path)
        self.assertEqual(self.window.saved_hash, original_saved_hash)
        self.assertEqual(path.read_bytes(), original_bytes)
        self.assertFalse(any('Created ' in str(call) for call in message.call_args_list))

    def test_duplicate_keeps_existing_destination_and_source_intact(self):
        path, _ = self.prepare(dirty=False)
        self.window.analysis_fields['stop'].setText('987u')
        target = path.parent / 'already exists.icproj'
        save_project(example(), target)
        target_bytes = target.read_bytes()
        original_bytes = path.read_bytes()
        original_saved_hash = self.window.saved_hash
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')), \
                patch.object(self.window.project_index, 'remember', side_effect=AssertionError('Existing destination reindexed')), \
                patch.object(self.window.statusBar(), 'showMessage') as message:
            with self.assertRaises(FileExistsError):
                self.window.duplicate_project_dialog()
        self.assertEqual(target.read_bytes(), target_bytes)
        self.assertEqual(path.read_bytes(), original_bytes)
        self.assertEqual(self.window.path, path)
        self.assertEqual(self.window.saved_hash, original_saved_hash)
        self.assertEqual(self.window.project['analysis']['stop'], '987u')
        self.assertFalse(any('Created ' in str(call) for call in message.call_args_list))

    def test_xschem_export_contains_current_analysis_and_inspector_edits(self):
        path, _ = self.prepare(dirty=False)
        original_bytes = path.read_bytes()
        original_saved_hash = self.window.saved_hash
        rid = self.pending_resistor('22k')
        self.window.analysis_fields['stop'].setText('987u')
        target = path.parent / 'current xschem package'
        with patch.object(QFileDialog, 'getExistingDirectory', return_value=str(target)):
            self.window.export_sch()
        exported = load_project(target / 'project.icproj')
        self.assertEqual(exported['analysis']['stop'], '987u')
        self.assertEqual(next(d for d in exported['cells'][0]['devices'] if d['id'] == rid)['value'], '22k')
        deck = (target / 'simulation.cir').read_text(encoding='utf-8')
        transient = next(line.split() for line in deck.splitlines() if line.startswith('.tran '))
        self.assertAlmostEqual(float(transient[-1]), 987e-6)
        self.assertIn('22000', next(line for line in deck.splitlines() if line.startswith('R1 ')))
        self.assertIn('Xschem package exported', self.window.statusBar().currentMessage())
        self.assertEqual(self.window.path, path)
        self.assertEqual(self.window.saved_hash, original_saved_hash)
        self.assertNotEqual(digest(self.window.project), original_saved_hash)
        self.assertEqual(path.read_bytes(), original_bytes)
        self.assertFalse(self.window.analysis_dirty)
        self.assertFalse(self.window._inspector_dirty)

    def test_structural_verilog_export_contains_current_inspector_value(self):
        path, _ = self.prepare(dirty=False)
        original_bytes = path.read_bytes()
        original_saved_hash = self.window.saved_hash
        self.pending_resistor('22k')
        target = path.parent / 'current connectivity.v'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
            self.window.export_verilog()
        text = target.read_text(encoding='utf-8')
        resistor = next(line for line in text.splitlines() if 'IC_R #' in line)
        self.assertIn('.VALUE(22000.0)', resistor)
        self.assertNotIn('.VALUE(10000.0)', resistor)
        self.assertEqual(self.window.path, path)
        self.assertEqual(self.window.saved_hash, original_saved_hash)
        self.assertNotEqual(digest(self.window.project), original_saved_hash)
        self.assertEqual(path.read_bytes(), original_bytes)
        self.assertFalse(self.window._inspector_dirty)

    def test_native_xschem_export_retains_current_native_analysis_settings(self):
        path, _ = self.prepare(dirty=False)
        native = load_project(Path(__file__).resolve().parents[1] / 'examples/native-divider.icproj')
        save_project(native, path)
        self.window.set_project(load_project(path), path)
        self.assertTrue(self.window.save())
        original_bytes = path.read_bytes()
        original_saved_hash = self.window.saved_hash
        self.window.analysis_type.setCurrentIndex(self.window.analysis_type.findData('tran'))
        self.window.analysis_fields['stop'].setText('987u')
        self.window.analysis_fields['temperature'].setText('65')
        self.assertTrue(self.window.analysis_dirty)
        target = path.parent / 'native xschem package'
        with patch.object(QFileDialog, 'getExistingDirectory', return_value=str(target)):
            self.window.export_sch()
        exported = load_project(target / 'studio-project.icproj')
        self.assertEqual(exported['analysis']['type'], 'tran')
        self.assertEqual(exported['analysis']['stop'], '987u')
        self.assertEqual(float(exported['analysis']['temperature']), 65)
        self.assertEqual(exported['analysis']['dc_startup'], self.window.native_dc_startup.isChecked())
        self.assertFalse(self.window.analysis_dirty)
        self.assertEqual(self.window.path, path)
        self.assertEqual(self.window.saved_hash, original_saved_hash)
        self.assertNotEqual(digest(self.window.project), original_saved_hash)
        self.assertEqual(path.read_bytes(), original_bytes)

    def test_invalid_export_drafts_do_not_write_or_report_success(self):
        for kind, field in (('xschem', 'analysis'), ('xschem', 'inspector'), ('verilog', 'inspector')):
            with self.subTest(kind=kind, field=field):
                path, _ = self.prepare(dirty=False)
                original_bytes = path.read_bytes()
                original_saved_hash = self.window.saved_hash
                if field == 'analysis':
                    self.window.analysis_fields['stop'].setText('invalid time')
                else:
                    self.pending_resistor('invalid resistance')
                target = path.parent / 'must not exist'
                with patch.object(QFileDialog, 'getExistingDirectory', return_value=str(target)) as directory_picker, \
                        patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')), \
                        patch('icstudio.gui.export_xschem', side_effect=AssertionError('Invalid draft wrote Xschem')), \
                        patch('icstudio.feature_ui.atomic_write', side_effect=AssertionError('Invalid draft wrote Verilog')), \
                        patch.object(self.window.statusBar(), 'showMessage') as message:
                    (self.window.export_sch if kind == 'xschem' else self.window.export_verilog)()
                    if kind == 'xschem':
                        directory_picker.assert_not_called()
                self.assertFalse(target.exists())
                self.assertEqual(path.read_bytes(), original_bytes)
                self.assertEqual(self.window.saved_hash, original_saved_hash)
                self.assertFalse(any('exported' in str(call).lower() for call in message.call_args_list))

    def test_explicit_export_draft_refusals_stop_before_writer(self):
        for kind, guard in (('xschem', 'flush_inspector'), ('xschem', 'flush_analysis'), ('verilog', 'flush_inspector')):
            with self.subTest(kind=kind, guard=guard):
                path, _ = self.prepare(dirty=False)
                before = clone(self.window.project)
                target = path.parent / 'refused export'
                with patch.object(QFileDialog, 'getExistingDirectory', return_value=str(target)), \
                        patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')), \
                        patch.object(self.window, guard, return_value=False), \
                        patch('icstudio.gui.export_xschem', side_effect=AssertionError('Refused draft wrote Xschem')), \
                        patch('icstudio.feature_ui.atomic_write', side_effect=AssertionError('Refused draft wrote Verilog')), \
                        patch.object(self.window.statusBar(), 'showMessage') as message:
                    (self.window.export_sch if kind == 'xschem' else self.window.export_verilog)()
                self.assertEqual(digest(self.window.project), digest(before))
                self.assertFalse(target.exists())
                self.assertFalse(any('exported' in str(call).lower() for call in message.call_args_list))

    def test_export_picker_cancellation_preserves_each_routes_draft_semantics(self):
        for kind in ('xschem', 'verilog'):
            with self.subTest(kind=kind):
                path, _ = self.prepare(dirty=False)
                original_bytes = path.read_bytes()
                original_saved_hash = self.window.saved_hash
                rid = self.pending_resistor('22k')
                self.window.analysis_fields['stop'].setText('987u')
                original_stop = self.window.project['analysis']['stop']
                with patch.object(QFileDialog, 'getExistingDirectory', return_value=''), \
                        patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')), \
                        patch('icstudio.gui.export_xschem', side_effect=AssertionError('Cancelled picker wrote Xschem')), \
                        patch('icstudio.feature_ui.atomic_write', side_effect=AssertionError('Cancelled picker wrote Verilog')), \
                        patch.object(self.window.statusBar(), 'showMessage') as message:
                    if kind == 'verilog':
                        with patch.object(self.window, 'flush_inspector', side_effect=AssertionError('Cancelled Verilog picker applied inspector')):
                            self.window.export_verilog()
                        self.assertTrue(self.window._inspector_dirty)
                        self.assertTrue(self.window.analysis_dirty)
                        self.assertEqual(self.window.project['analysis']['stop'], original_stop)
                        self.assertEqual(next(d for d in self.window.cell['devices'] if d['id'] == rid)['value'], '10k')
                    else:
                        self.window.export_sch()
                        # Xschem has an existing pre-picker inspector guard;
                        # the new analysis guard follows the same behavior.
                        self.assertFalse(self.window._inspector_dirty)
                        self.assertFalse(self.window.analysis_dirty)
                        self.assertEqual(self.window.project['analysis']['stop'], '987u')
                        self.assertEqual(next(d for d in self.window.cell['devices'] if d['id'] == rid)['value'], '22k')
                self.assertEqual(self.window.path, path)
                self.assertEqual(self.window.saved_hash, original_saved_hash)
                self.assertEqual(path.read_bytes(), original_bytes)
                self.assertFalse(any('exported' in str(call).lower() for call in message.call_args_list))

    def test_export_writer_failures_leave_source_unsaved_and_do_not_report_success(self):
        for kind in ('xschem', 'verilog'):
            with self.subTest(kind=kind):
                path, _ = self.prepare(dirty=False)
                original_bytes = path.read_bytes()
                original_saved_hash = self.window.saved_hash
                self.pending_resistor('22k')
                target = path.parent / 'failed export'
                writer = 'icstudio.gui.export_xschem' if kind == 'xschem' else 'icstudio.feature_ui.atomic_write'
                with patch.object(QFileDialog, 'getExistingDirectory', return_value=str(target)), \
                        patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')), \
                        patch(writer, side_effect=OSError('Injected export disk full')), \
                        patch.object(self.window.statusBar(), 'showMessage') as message:
                    with self.assertRaisesRegex(OSError, 'Injected export disk full'):
                        (self.window.export_sch if kind == 'xschem' else self.window.export_verilog)()
                self.assertFalse(target.exists())
                self.assertEqual(self.window.path, path)
                self.assertEqual(self.window.saved_hash, original_saved_hash)
                self.assertNotEqual(digest(self.window.project), original_saved_hash)
                self.assertEqual(path.read_bytes(), original_bytes)
                self.assertFalse(any('exported' in str(call).lower() for call in message.call_args_list))


    def prepare_directory(self, filename='project.icstudio', sibling=False):
        source, _ = self.prepare(dirty=False)
        root = source.parent / 'folder project'
        canonical = save_directory(self.window.project, root)
        selected = root / filename
        if selected != canonical:
            canonical.rename(selected)
        if sibling:
            other = clone(self.window.project)
            other['id'] = uid()
            other['name'] = 'Unrelated canonical sibling'
            save_directory(other, root)
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(selected), '')):
            self.window.open_project_folder()
        self.assertEqual(self.window.path, selected)
        self.assertEqual(self.errors, [])
        return selected, canonical

    def test_canonical_manifest_save_preserves_directory_format_and_current_edits(self):
        selected, _ = self.prepare_directory()
        before = json.loads(selected.read_text(encoding='utf-8'))
        old_cells = {ref['path']: (selected.parent / ref['path']).read_bytes()
                     for ref in before['cell_files']}
        rid = self.pending_resistor('22k')
        self.window.analysis_fields['stop'].setText('987u')
        self.assertTrue(self.window.save())
        after = json.loads(selected.read_text(encoding='utf-8'))
        self.assertIn('cell_files', after)
        self.assertNotIn('cells', after)
        self.assertNotEqual(before['cell_files'], after['cell_files'])
        reopened = load_directory(selected)
        self.assertEqual(next(d for d in reopened['cells'][0]['devices'] if d['id'] == rid)['value'], '22k')
        self.assertEqual(reopened['analysis']['stop'], '987u')
        self.assertEqual(self.window.path, selected)
        self.assertEqual(self.window.saved_hash, digest(self.window.project))
        self.assertEqual(self.window._disk_hash, file_digest(selected))
        for path, data in old_cells.items():
            self.assertEqual((selected.parent / path).read_bytes(), data)

    def test_renamed_manifest_save_updates_only_selected_file_and_reopens_latest_edits(self):
        for with_sibling in (False, True):
            with self.subTest(with_sibling=with_sibling):
                selected, canonical = self.prepare_directory('amplifier.icstudio', sibling=with_sibling)
                selected_id = self.window.project['id']
                sibling_bytes = canonical.read_bytes() if with_sibling else None
                sibling_id = load_directory(canonical)['id'] if with_sibling else None
                self.window.commit(lambda p: p.update(name='Saved renamed project edit'), 'Rename edit')
                rid = self.pending_resistor('22k')
                self.window.analysis_fields['stop'].setText('987u')
                self.assertTrue(self.window.save())
                if with_sibling:
                    self.assertTrue(canonical.read_bytes() == sibling_bytes, 'Save overwrote unrelated canonical manifest')
                    self.assertEqual(load_directory(canonical)['id'], sibling_id)
                    self.assertNotEqual(sibling_id, selected_id)
                reopened = load_directory(selected)
                self.assertEqual(reopened['name'], 'Saved renamed project edit')
                self.assertEqual(reopened['id'], selected_id)
                self.assertEqual(next(d for d in reopened['cells'][0]['devices'] if d['id'] == rid)['value'], '22k')
                self.assertEqual(reopened['analysis']['stop'], '987u')
                self.assertEqual(self.window.path, selected)
                self.assertEqual(self.window.settings.value('last_project'), str(selected))
                self.assertEqual(self.window._disk_hash, file_digest(selected))
                self.assertEqual(self.window.saved_hash, digest(self.window.project))
                if not with_sibling:
                    self.assertFalse(canonical.exists())
                with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(selected), '')), \
                        patch.object(QMessageBox, 'question', side_effect=AssertionError('Saved manifest prompted again')):
                    self.window.open_project_folder()
                self.assertEqual(self.window.project['name'], 'Saved renamed project edit')
                self.window.commit(lambda p: p['cells'][0].update(name='Next_manifest_edit'), 'Later edit')
                self.assertTrue(self.window.save())
                latest = load_directory(selected)
                self.assertEqual(latest['name'], 'Saved renamed project edit')
                self.assertEqual(latest['cells'][0]['name'], 'Next_manifest_edit')
                if with_sibling:
                    self.assertEqual(canonical.read_bytes(), sibling_bytes)
                else:
                    self.assertFalse(canonical.exists())

    def test_uppercase_manifest_extension_stays_directory_project_after_save(self):
        selected, canonical = self.prepare_directory('amplifier.ICSTUDIO', sibling=True)
        sibling_bytes = canonical.read_bytes()
        self.window.commit(lambda p: p.update(name='Uppercase manifest edit'), 'Rename edit')
        self.assertTrue(self.window.save())
        manifest = json.loads(selected.read_text(encoding='utf-8'))
        self.assertIn('cell_files', manifest)
        self.assertNotIn('cells', manifest)
        self.assertEqual(load_directory(selected)['name'], 'Uppercase manifest edit')
        self.assertEqual(canonical.read_bytes(), sibling_bytes)
        self.assertEqual(self.window.path, selected)
        self.assertEqual(self.window._disk_hash, file_digest(selected))
        self.assertEqual(self.window.saved_hash, digest(self.window.project))
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(selected), '')):
            self.window.open_project_folder()
        self.assertEqual(self.window.project['name'], 'Uppercase manifest edit')

    def test_manifest_commit_failure_preserves_selected_file_sibling_and_unsaved_edits(self):
        from icstudio.project_store import atomic_write
        for filename in ('project.icstudio', 'amplifier.icstudio'):
            with self.subTest(filename=filename):
                selected, canonical = self.prepare_directory(filename, sibling=filename != 'project.icstudio')
                selected_bytes = selected.read_bytes()
                sibling_bytes = canonical.read_bytes()
                saved_hash = self.window.saved_hash
                disk_hash = self.window._disk_hash
                previous_last_project = self.window.settings.value('last_project')
                self.window.commit(lambda p: p.update(name='Still unsaved manifest edit'), 'Rename edit')
                self.pending_resistor('22k')
                writes = []

                def fail_manifest(path, text):
                    writes.append(Path(path))
                    if Path(path) == selected:
                        raise OSError('Injected manifest commit failure')
                    return atomic_write(path, text)

                with patch('icstudio.project_store.atomic_write', side_effect=fail_manifest), \
                        patch.object(self.window, 'clear_recovery') as clear_recovery, \
                        patch.object(self.window.project_index, 'remember') as remember:
                    with self.assertRaisesRegex(OSError, 'Injected manifest commit failure'):
                        self.window.save()
                self.assertEqual(writes[-1], selected)
                self.assertTrue(any('cells' in path.parts for path in writes[:-1]))
                self.assertEqual(selected.read_bytes(), selected_bytes)
                self.assertEqual(canonical.read_bytes(), sibling_bytes)
                self.assertEqual(load_directory(selected)['name'], 'Original saved design')
                self.assertEqual(self.window.project['name'], 'Still unsaved manifest edit')
                self.assertEqual(self.window.path, selected)
                self.assertEqual(self.window.saved_hash, saved_hash)
                self.assertNotEqual(digest(self.window.project), saved_hash)
                self.assertEqual(self.window._disk_hash, disk_hash)
                self.assertEqual(self.window.settings.value('last_project'), previous_last_project)
                clear_recovery.assert_not_called()
                remember.assert_not_called()

    def test_manifest_external_change_guard_does_not_write_selected_or_sibling(self):
        selected, canonical = self.prepare_directory('amplifier.icstudio', sibling=True)
        sibling_bytes = canonical.read_bytes()
        saved_hash = self.window.saved_hash
        disk_hash = self.window._disk_hash
        external = json.loads(selected.read_text(encoding='utf-8'))
        external['name'] = 'External manifest edit'
        selected.write_text(json.dumps(external), encoding='utf-8')
        external_bytes = selected.read_bytes()
        self.window.commit(lambda p: p.update(name='My unsaved manifest edit'), 'Rename edit')
        with patch('icstudio.project_store.atomic_write', side_effect=AssertionError('Conflict wrote a manifest')):
            with self.assertRaisesRegex(ValueError, 'changed on disk'):
                self.window.save()
        self.assertEqual(selected.read_bytes(), external_bytes)
        self.assertEqual(canonical.read_bytes(), sibling_bytes)
        self.assertEqual(self.window.path, selected)
        self.assertEqual(self.window.saved_hash, saved_hash)
        self.assertNotEqual(digest(self.window.project), saved_hash)
        self.assertEqual(self.window._disk_hash, disk_hash)


    def prepare_physical_finding(self):
        from icstudio.layout import rect
        from icstudio.physical import connectivity
        path, _ = self.prepare(dirty=False)
        w = self.window
        root, child = w.cid, uid()
        w.commit(lambda p: p['cells'].append({
            'id': child, 'name': 'Physical_child', 'ports': [], 'devices': [],
            'shapes': [rect('metal1', 0, 0, 400, 400, net='unconnected')],
        }), 'Add physical finding fixture')
        self.assertTrue(w.save())
        w.cell_combo.setCurrentIndex(w.cell_combo.findData(child))
        w.show_physical_result({
            'physical_result': connectivity(w.project, child),
            'revision': w.project['revision'], 'settings': {'type': 'connectivity'},
        })
        row = next(i for i, issue in enumerate(w.issues) if issue['code'] == 'LVS.FLOATING_LABEL')
        self.assertEqual(w.issues[row]['cell_id'], child)
        w.cell_combo.setCurrentIndex(w.cell_combo.findData(root))
        w.mode_combo.setCurrentIndex(0)
        rid = next(d['id'] for d in w.cell['devices'] if d['kind'] == 'R')
        w.select([rid])
        self.assertEqual(self.errors, [])
        return path, root, child, rid, row

    def test_physical_finding_commits_pending_edit_then_rejects_newly_stale_navigation(self):
        path, root, _, rid, row = self.prepare_physical_finding()
        w = self.window
        original_bytes, saved_hash = path.read_bytes(), w.saved_hash
        history_count = len(w.history.undo_stack)
        self.pending_resistor('22k')
        # Exercise the signal connected to the real Studio MRO, not one mixin.
        w.checks.cellClicked.emit(row, 0)
        original_cell = next(cell for cell in w.project['cells'] if cell['id'] == root)
        self.assertEqual(next(d for d in original_cell['devices'] if d['id'] == rid)['value'], '22k')
        self.assertEqual(w.cid, root)
        self.assertEqual(w.selection, [rid])
        self.assertEqual(w.current_mode, 'schematic')
        self.assertFalse(w._inspector_dirty)
        self.assertEqual(len(w.history.undo_stack), history_count + 1)
        self.assertNotEqual(w.check_revision, w.project['revision'])
        self.assertIn('stale', w.statusBar().currentMessage().lower())
        self.assertEqual(w.saved_hash, saved_hash)
        self.assertNotEqual(digest(w.project), saved_hash)
        self.assertEqual(path.read_bytes(), original_bytes)
        w.checks.cellClicked.emit(row, 0)
        self.assertEqual(w.cid, root)
        self.assertEqual(len(w.history.undo_stack), history_count + 1)
        w.undo()
        self.assertEqual(next(d for d in w.cell['devices'] if d['id'] == rid)['value'], '10k')
        w.redo()
        self.assertEqual(next(d for d in w.cell['devices'] if d['id'] == rid)['value'], '22k')
        self.assertTrue(w.save())
        self.assertEqual(next(d for d in load_project(path)['cells'][0]['devices'] if d['id'] == rid)['value'], '22k')
        self.assertEqual(self.errors, [])

    def test_physical_finding_rejects_invalid_pending_edit_without_discarding_it(self):
        path, root, _, rid, row = self.prepare_physical_finding()
        w = self.window
        before = digest(w.project)
        original_bytes, saved_hash = path.read_bytes(), w.saved_hash
        history_count = len(w.history.undo_stack)
        self.pending_resistor('invalid resistance')
        for _ in range(2):
            w.checks.cellClicked.emit(row, 0)
            self.assertEqual(w.cid, root)
            self.assertEqual(w.selection, [rid])
            self.assertEqual(w.current_mode, 'schematic')
            self.assertTrue(w._inspector_dirty)
            self.assertEqual(w.form_fields['Value'].text(), 'invalid resistance')
            self.assertTrue(w.property_error.text())
            self.assertEqual(digest(w.project), before)
            self.assertEqual(len(w.history.undo_stack), history_count)
            self.assertEqual(w.saved_hash, saved_hash)
            self.assertEqual(path.read_bytes(), original_bytes)
        self.assertEqual(self.errors, [])

    def test_physical_finding_without_pending_edit_navigates_repeatedly_without_mutation(self):
        path, _, child, _, row = self.prepare_physical_finding()
        w = self.window
        before = digest(w.project)
        original_bytes, saved_hash = path.read_bytes(), w.saved_hash
        history_count = len(w.history.undo_stack)
        oid = w.issues[row]['object']
        for _ in range(2):
            w.checks.cellClicked.emit(row, 0)
            self.assertEqual(w.cid, child)
            self.assertEqual(w.selection, [oid])
            self.assertEqual(w.current_mode, 'layout')
            self.assertTrue(w.layout.finding_box)
            self.assertFalse(w._inspector_dirty)
            self.assertEqual(digest(w.project), before)
            self.assertEqual(len(w.history.undo_stack), history_count)
            self.assertEqual(w.saved_hash, saved_hash)
            self.assertEqual(path.read_bytes(), original_bytes)
        self.assertEqual(self.errors, [])

    def test_stale_physical_finding_without_draft_does_not_navigate(self):
        for stale_by in ('revision', 'source_design_hash'):
            with self.subTest(stale_by=stale_by):
                path, root, _, rid, row = self.prepare_physical_finding()
                w = self.window
                if stale_by == 'revision':
                    w.commit(lambda p: p.update(name='Changed after verification'), 'Later edit')
                else:
                    w.issues[row]['source_design_hash'] = 'different saved design hash'
                before, history_count = digest(w.project), len(w.history.undo_stack)
                original_bytes = path.read_bytes()
                self.assertFalse(w._inspector_dirty)
                for _ in range(2):
                    w.checks.cellClicked.emit(row, 0)
                    self.assertEqual(w.cid, root)
                    self.assertEqual(w.selection, [rid])
                    self.assertEqual(w.current_mode, 'schematic')
                    self.assertIn('stale', w.statusBar().currentMessage().lower())
                    self.assertEqual(digest(w.project), before)
                    self.assertEqual(len(w.history.undo_stack), history_count)
                    self.assertEqual(path.read_bytes(), original_bytes)
                self.assertEqual(self.errors, [])


    def prepare_pending_layout_width(self, value):
        from icstudio.layout import rect
        path, _ = self.prepare(dirty=False)
        w = self.window
        shape = rect('metal1', 0, 0, 1000, 1000)
        w.commit(lambda p: p['cells'][0]['shapes'].append(shape), 'Layout width fixture')
        self.assertTrue(w.save())
        w.mode_combo.setCurrentIndex(1)
        w.select([shape['id']], 'layout')
        w.layer_combo.setCurrentText('metal1')
        self.assertEqual(w.form_fields['Width'].text(), '1')
        w.form_fields['Width'].setText(value)
        self.assertTrue(w._inspector_dirty)
        return path, shape['id']

    def click_layer_visibility(self, title):
        button = next(button for button in self.window.navtabs.widget(2).findChildren(QPushButton)
                      if button.text() == title)
        button.click()

    def test_layer_visibility_buttons_preserve_valid_and_invalid_geometry_drafts(self):
        for title in ('All', 'None', 'Solo'):
            for value in ('2', 'invalid width'):
                with self.subTest(title=title, value=value):
                    path, shape_id = self.prepare_pending_layout_width(value)
                    w = self.window
                    field = w.form_fields['Width']
                    before, saved_hash = digest(w.project), w.saved_hash
                    original_bytes = path.read_bytes()
                    history_counts = len(w.history.undo_stack), len(w.history.redo_stack)
                    names = {layer['name'] for layer in w.project['pdk']['layers']}
                    expected = names if title == 'All' else set() if title == 'None' else {'metal1'}
                    for _ in range(2):
                        self.click_layer_visibility(title)
                        self.assertIs(w.form_fields['Width'], field)
                        self.assertEqual(field.text(), value)
                        self.assertTrue(w._inspector_dirty)
                        self.assertTrue(w.apply_button.isEnabled())
                        self.assertEqual(w.selection, [shape_id])
                        self.assertEqual(w.current_mode, 'layout')
                        self.assertEqual(w.layout.visible_layers, expected)
                        for i in range(w.layers.count()):
                            item = w.layers.item(i)
                            self.assertEqual(item.checkState() == Qt.Checked,
                                             item.data(Qt.UserRole) in expected)
                        for row in range(w.layer_table.rowCount()):
                            name = w.layer_table.item(row, 0).data(Qt.UserRole)
                            self.assertEqual(w.layer_table.item(row, 1).checkState() == Qt.Checked,
                                             name in expected)
                        self.assertFalse(w.layers.signalsBlocked())
                        self.assertFalse(w.layer_table.signalsBlocked())
                        self.assertEqual(digest(w.project), before)
                        self.assertEqual(w.saved_hash, saved_hash)
                        self.assertEqual((len(w.history.undo_stack), len(w.history.redo_stack)), history_counts)
                        self.assertEqual(w.path, path)
                        self.assertEqual(path.read_bytes(), original_bytes)
                    self.assertEqual(self.errors, [])

    def test_geometry_draft_survives_visibility_changes_until_explicit_apply_and_save(self):
        path, shape_id = self.prepare_pending_layout_width('2')
        w = self.window
        before, saved_hash = digest(w.project), w.saved_hash
        original_bytes, history_count = path.read_bytes(), len(w.history.undo_stack)
        for title in ('None', 'Solo', 'All'):
            self.click_layer_visibility(title)
        self.assertEqual(w.form_fields['Width'].text(), '2')
        self.assertTrue(w._inspector_dirty)
        self.assertEqual(digest(w.project), before)
        self.assertEqual(len(w.history.undo_stack), history_count)
        w.apply_button.click()
        shape = next(shape for shape in w.cell['shapes'] if shape['id'] == shape_id)
        self.assertEqual(shape['points'][1][0] - shape['points'][0][0], 2000)
        self.assertFalse(w._inspector_dirty)
        self.assertEqual(w.selection, [shape_id])
        self.assertEqual(len(w.history.undo_stack), history_count + 1)
        self.assertEqual(w.saved_hash, saved_hash)
        self.assertNotEqual(digest(w.project), saved_hash)
        self.assertEqual(path.read_bytes(), original_bytes)
        self.assertTrue(w.save())
        saved = next(shape for shape in load_project(path)['cells'][0]['shapes'] if shape['id'] == shape_id)
        self.assertEqual(saved['points'][1][0] - saved['points'][0][0], 2000)
        self.assertEqual(w.saved_hash, digest(w.project))
        self.assertEqual(self.errors, [])

    def test_single_layer_visibility_checkbox_preserves_pending_geometry_draft(self):
        for value in ('2', 'invalid width'):
            with self.subTest(value=value):
                path, shape_id = self.prepare_pending_layout_width(value)
                w = self.window
                field = w.form_fields['Width']
                before, saved_hash = digest(w.project), w.saved_hash
                original_bytes = path.read_bytes()
                history_counts = len(w.history.undo_stack), len(w.history.redo_stack)
                row = next(i for i in range(w.layer_table.rowCount())
                           if w.layer_table.item(i, 0).data(Qt.UserRole) == 'metal1')
                item = w.layer_table.item(row, 1)
                for _ in range(2):
                    checked = item.checkState() != Qt.Checked
                    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                    self.assertEqual('metal1' in w.layout.visible_layers, checked)
                    self.assertIs(w.form_fields['Width'], field)
                    self.assertEqual(field.text(), value)
                    self.assertTrue(w._inspector_dirty)
                    self.assertEqual(w.selection, [shape_id])
                    self.assertEqual(digest(w.project), before)
                    self.assertEqual(w.saved_hash, saved_hash)
                    self.assertEqual((len(w.history.undo_stack), len(w.history.redo_stack)), history_counts)
                    self.assertEqual(path.read_bytes(), original_bytes)
                self.assertEqual(self.errors, [])


    def prepare_add_cell_draft(self, kind, value):
        if kind == 'layout':
            path, oid = self.prepare_pending_layout_width(value)
            return path, oid, 'Width'
        path, _ = self.prepare(dirty=False)
        self.window.mode_combo.setCurrentIndex(0)
        return path, self.pending_resistor(value), 'Value'

    def test_add_cell_repeated_refusal_preserves_invalid_property_draft(self):
        for kind in ('resistor', 'layout'):
            with self.subTest(kind=kind):
                path, oid, key = self.prepare_add_cell_draft(kind, 'invalid draft')
                w = self.window
                field = w.form_fields[key]
                root, selection, mode = w.cid, list(w.selection), w.current_mode
                before, saved_hash, disk_hash = digest(w.project), w.saved_hash, w._disk_hash
                original_bytes = path.read_bytes()
                history_counts = len(w.history.undo_stack), len(w.history.redo_stack)
                with patch.object(QInputDialog, 'getText', return_value=('Requested_child', True)) as dialog:
                    for _ in range(2):
                        w.command_actions['Add cell…'].trigger()
                        self.assertTrue(w._inspector_dirty)
                        self.assertIs(w.form_fields[key], field)
                        self.assertEqual(field.text(), 'invalid draft')
                        self.assertTrue(w.property_error.text())
                        self.assertEqual(w.cid, root)
                        self.assertEqual(w.selection, selection)
                        self.assertIn(oid, w.selection)
                        self.assertEqual(w.current_mode, mode)
                        self.assertEqual(digest(w.project), before)
                        self.assertFalse(any(c['name'] == 'Requested_child' for c in w.project['cells']))
                        self.assertEqual((len(w.history.undo_stack), len(w.history.redo_stack)), history_counts)
                        self.assertEqual(w.saved_hash, saved_hash)
                        self.assertEqual(w._disk_hash, disk_hash)
                        self.assertEqual(w.path, path)
                        self.assertEqual(path.read_bytes(), original_bytes)
                    self.assertEqual(dialog.call_count, 2)
                self.assertEqual(self.errors, [])

    def test_add_cell_valid_property_edit_and_new_cell_survive_undo_redo_and_save(self):
        for kind, draft, old, applied in (('resistor', '22k', '10k', '22k'), ('layout', '2', 1000, 2000)):
            with self.subTest(kind=kind):
                path, oid, _ = self.prepare_add_cell_draft(kind, draft)
                w = self.window
                root, count = w.cid, len(w.project['cells'])
                original_bytes, saved_hash = path.read_bytes(), w.saved_hash
                history_count = len(w.history.undo_stack)

                def value(project):
                    source = next(c for c in project['cells'] if c['id'] == root)
                    if kind == 'resistor':
                        return next(d['value'] for d in source['devices'] if d['id'] == oid)
                    shape = next(s for s in source['shapes'] if s['id'] == oid)
                    return shape['points'][1][0] - shape['points'][0][0]

                with patch.object(QInputDialog, 'getText', return_value=('Requested_child', True)):
                    w.command_actions['Add cell…'].trigger()
                child = w.cid
                self.assertNotEqual(child, root)
                self.assertEqual(w.cell['name'], 'Requested_child')
                self.assertEqual(len(w.project['cells']), count + 1)
                self.assertEqual(w.selection, [])
                self.assertEqual(value(w.project), applied)
                self.assertFalse(w._inspector_dirty)
                self.assertEqual(len(w.history.undo_stack), history_count + 2)
                self.assertEqual(w.saved_hash, saved_hash)
                self.assertEqual(path.read_bytes(), original_bytes)
                w.undo()
                self.assertFalse(any(c['id'] == child for c in w.project['cells']))
                self.assertEqual(value(w.project), applied)
                w.undo()
                self.assertEqual(value(w.project), old)
                w.redo()
                w.redo()
                self.assertEqual(value(w.project), applied)
                self.assertEqual(next(c['name'] for c in w.project['cells'] if c['id'] == child), 'Requested_child')
                self.assertEqual(path.read_bytes(), original_bytes)
                self.assertTrue(w.save())
                saved = load_project(path)
                self.assertEqual(value(saved), applied)
                self.assertEqual(next(c['name'] for c in saved['cells'] if c['id'] == child), 'Requested_child')
                self.assertEqual(w.path, path)
                self.assertEqual(w.saved_hash, digest(w.project))
                self.assertEqual(self.errors, [])

    def test_add_cell_cancel_preserves_valid_and_invalid_drafts_without_applying(self):
        for kind in ('resistor', 'layout'):
            for valid in (False, True):
                with self.subTest(kind=kind, valid=valid):
                    draft = ('22k' if kind == 'resistor' else '2') if valid else 'invalid draft'
                    path, oid, key = self.prepare_add_cell_draft(kind, draft)
                    w = self.window
                    field = w.form_fields[key]
                    root, mode = w.cid, w.current_mode
                    before, saved_hash = digest(w.project), w.saved_hash
                    original_bytes = path.read_bytes()
                    history_counts = len(w.history.undo_stack), len(w.history.redo_stack)
                    with patch.object(QInputDialog, 'getText', return_value=('', False)), \
                            patch.object(w, 'flush_inspector', side_effect=AssertionError('Cancel applied a draft')) as flush:
                        w.command_actions['Add cell…'].trigger()
                        flush.assert_not_called()
                    self.assertIs(w.form_fields[key], field)
                    self.assertEqual(field.text(), draft)
                    self.assertTrue(w._inspector_dirty)
                    self.assertEqual(w.cid, root)
                    self.assertEqual(w.selection, [oid])
                    self.assertEqual(w.current_mode, mode)
                    self.assertEqual(digest(w.project), before)
                    self.assertEqual((len(w.history.undo_stack), len(w.history.redo_stack)), history_counts)
                    self.assertEqual(w.saved_hash, saved_hash)
                    self.assertEqual(w.path, path)
                    self.assertEqual(path.read_bytes(), original_bytes)
                    self.assertEqual(self.errors, [])


    def custom_symbol_action(self):
        def walk(menu):
            for action in menu.actions():
                if action.menu():
                    yield from walk(action.menu())
                else:
                    yield action
        matches = {id(action): action for action in walk(self.window.menuBar())
                   if action.text().replace('&', '') == 'New custom symbol…'}
        self.assertEqual(len(matches), 1)
        action = next(iter(matches.values()))
        self.assertTrue(action.isEnabled())
        return action

    def test_new_symbol_repeated_refusal_keeps_invalid_draft_and_never_opens_editor(self):
        for kind in ('resistor', 'layout'):
            with self.subTest(kind=kind):
                path, oid, key = self.prepare_add_cell_draft(kind, 'invalid draft')
                w = self.window
                action, field = self.custom_symbol_action(), w.form_fields[key]
                before, saved_hash, disk_hash = digest(w.project), w.saved_hash, w._disk_hash
                root, mode, original_bytes = w.cid, w.current_mode, path.read_bytes()
                history_counts = len(w.history.undo_stack), len(w.history.redo_stack)
                answers = [('Requested_symbol', True), ('in out', True)] * 2
                with patch.object(QInputDialog, 'getText', side_effect=answers) as dialogs, \
                        patch.object(w, 'symbol_dialog') as editor:
                    for _ in range(2):
                        action.trigger()
                        editor.assert_not_called()
                        self.assertTrue(w._inspector_dirty)
                        self.assertIs(w.form_fields[key], field)
                        self.assertEqual(field.text(), 'invalid draft')
                        self.assertTrue(w.property_error.text())
                        self.assertEqual(w.cid, root)
                        self.assertEqual(w.selection, [oid])
                        self.assertEqual(w.current_mode, mode)
                        self.assertEqual(digest(w.project), before)
                        self.assertFalse(any(c['name'] == 'Requested_symbol' for c in w.project['cells']))
                        self.assertEqual((len(w.history.undo_stack), len(w.history.redo_stack)), history_counts)
                        self.assertEqual(w.saved_hash, saved_hash)
                        self.assertEqual(w._disk_hash, disk_hash)
                        self.assertEqual(w.path, path)
                        self.assertEqual(path.read_bytes(), original_bytes)
                    self.assertEqual(dialogs.call_count, 4)
                self.assertEqual(self.errors, [])

    def test_new_symbol_applies_valid_draft_and_opens_editor_for_created_symbol_cell(self):
        for kind, draft, applied in (('resistor', '22k', '22k'), ('layout', '2', 2000)):
            with self.subTest(kind=kind):
                path, oid, _ = self.prepare_add_cell_draft(kind, draft)
                w = self.window
                action = self.custom_symbol_action()
                root, count = w.cid, len(w.project['cells'])
                original_bytes, saved_hash = path.read_bytes(), w.saved_hash
                history_count = len(w.history.undo_stack)
                opened = []
                with patch.object(QInputDialog, 'getText', side_effect=[('Requested_symbol', True), ('in out', True)]), \
                        patch.object(w, 'symbol_dialog', side_effect=lambda: opened.append((w.cid, clone(w.cell)))):
                    action.trigger()
                child = w.cid
                self.assertNotEqual(child, root)
                self.assertEqual(len(w.project['cells']), count + 1)
                self.assertEqual(len(opened), 1)
                self.assertEqual(opened[0][0], child)
                self.assertEqual(opened[0][1]['name'], 'Requested_symbol')
                self.assertEqual(opened[0][1]['ports'], ['in', 'out'])
                self.assertEqual(set(opened[0][1]['symbol']['pins']), {'in', 'out'})
                self.assertEqual(w.selection, [])
                self.assertFalse(w._inspector_dirty)
                self.assertEqual(len(w.history.undo_stack), history_count + 2)
                self.assertEqual(w.saved_hash, saved_hash)
                self.assertEqual(path.read_bytes(), original_bytes)
                self.assertTrue(w.save())
                for project in (w.project, load_project(path)):
                    source = next(c for c in project['cells'] if c['id'] == root)
                    if kind == 'resistor':
                        value = next(d['value'] for d in source['devices'] if d['id'] == oid)
                    else:
                        shape = next(s for s in source['shapes'] if s['id'] == oid)
                        value = shape['points'][1][0] - shape['points'][0][0]
                    self.assertEqual(value, applied)
                    created = next(c for c in project['cells'] if c['id'] == child)
                    self.assertEqual(created['name'], 'Requested_symbol')
                    self.assertEqual(created['ports'], ['in', 'out'])
                    self.assertEqual(set(created['symbol']['pins']), {'in', 'out'})
                self.assertEqual(w.path, path)
                self.assertEqual(w.saved_hash, digest(w.project))
                self.assertEqual(self.errors, [])

    def test_new_symbol_cancel_at_either_dialog_preserves_pending_draft_without_flush(self):
        for kind in ('resistor', 'layout'):
            for valid in (False, True):
                for cancel_at in ('name', 'ports'):
                    with self.subTest(kind=kind, valid=valid, cancel_at=cancel_at):
                        draft = ('22k' if kind == 'resistor' else '2') if valid else 'invalid draft'
                        path, oid, key = self.prepare_add_cell_draft(kind, draft)
                        w = self.window
                        action, field = self.custom_symbol_action(), w.form_fields[key]
                        before, saved_hash = digest(w.project), w.saved_hash
                        root, mode, original_bytes = w.cid, w.current_mode, path.read_bytes()
                        history_counts = len(w.history.undo_stack), len(w.history.redo_stack)
                        answers = [('', False)] if cancel_at == 'name' else [('Requested_symbol', True), ('', False)]
                        with patch.object(QInputDialog, 'getText', side_effect=answers) as dialogs, \
                                patch.object(w, 'symbol_dialog') as editor, \
                                patch.object(w, 'flush_inspector', side_effect=AssertionError('Cancel applied a draft')) as flush:
                            action.trigger()
                            flush.assert_not_called()
                            editor.assert_not_called()
                            self.assertEqual(dialogs.call_count, len(answers))
                        self.assertIs(w.form_fields[key], field)
                        self.assertEqual(field.text(), draft)
                        self.assertTrue(w._inspector_dirty)
                        self.assertEqual(w.cid, root)
                        self.assertEqual(w.selection, [oid])
                        self.assertEqual(w.current_mode, mode)
                        self.assertEqual(digest(w.project), before)
                        self.assertEqual((len(w.history.undo_stack), len(w.history.redo_stack)), history_counts)
                        self.assertEqual(w.saved_hash, saved_hash)
                        self.assertEqual(w.path, path)
                        self.assertEqual(path.read_bytes(), original_bytes)
                        self.assertEqual(self.errors, [])


    def selected_device_symbol_editor(self):
        actions = [a for a in self.window.findChildren(QAction)
                   if a.text().replace('&', '') == 'Edit selected symbol…']
        self.assertEqual(len(actions), 1)
        self.assertTrue(actions[0].isEnabled())
        actions[0].trigger()
        dialog = self.window._symbol_dialog
        self.app.processEvents()
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.cell['name'], 'R1')
        return dialog

    def draw_symbol_rectangle(self, dialog):
        before = len(dialog.pad.symbol['primitives'])
        dialog.tool.setCurrentText('Rectangle')
        start = dialog.pad.rect().center() + QPoint(30, 30)
        end = start + QPoint(40, 40)
        QTest.mousePress(dialog.pad, Qt.LeftButton, pos=start)
        QTest.mouseMove(dialog.pad, end)
        QTest.mouseRelease(dialog.pad, Qt.LeftButton, pos=end)
        self.assertEqual(len(dialog.pad.symbol['primitives']), before + 1)
        self.assertEqual(dialog.error.text(), '')
        return clone(dialog.pad.symbol)

    def test_device_symbol_repeated_invalid_save_keeps_editor_artwork_and_draft(self):
        path, _ = self.prepare(dirty=False)
        w = self.window
        w.mode_combo.setCurrentIndex(0)
        rid = self.pending_resistor('invalid resistance')
        field, root = w.form_fields['Value'], w.cid
        before, saved_hash, disk_hash = digest(w.project), w.saved_hash, w._disk_hash
        original_bytes = path.read_bytes()
        history_counts = len(w.history.undo_stack), len(w.history.redo_stack)
        dialog = self.selected_device_symbol_editor()
        try:
            artwork = self.draw_symbol_rectangle(dialog)
            pad_history = clone(dialog.pad.history)
            for _ in range(2):
                dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
                self.assertFalse(dialog.saved)
                self.assertNotEqual(dialog.result(), QDialog.Accepted)
                self.assertTrue(dialog.isVisible())
                self.assertEqual(dialog.error.text(), 'Resolve pending property edits before saving.')
                self.assertEqual(dialog.pad.symbol, artwork)
                self.assertEqual(dialog.pad.history, pad_history)
                self.assertIs(w.form_fields['Value'], field)
                self.assertEqual(field.text(), 'invalid resistance')
                self.assertTrue(w._inspector_dirty)
                self.assertTrue(w.property_error.text())
                self.assertEqual(w.cid, root)
                self.assertEqual(w.selection, [rid])
                self.assertEqual(digest(w.project), before)
                self.assertEqual((len(w.history.undo_stack), len(w.history.redo_stack)), history_counts)
                self.assertEqual(w.saved_hash, saved_hash)
                self.assertEqual(w._disk_hash, disk_hash)
                self.assertEqual(w.path, path)
                self.assertEqual(path.read_bytes(), original_bytes)
            self.assertEqual(self.errors, [])
        finally:
            dialog.reject()
            dialog.deleteLater()

    def test_device_symbol_valid_save_applies_property_artwork_undo_redo_and_reopen(self):
        path, original = self.prepare(dirty=False)
        w = self.window
        w.mode_combo.setCurrentIndex(0)
        rid = self.pending_resistor('22k')
        root, saved_hash, original_bytes = w.cid, w.saved_hash, path.read_bytes()
        history_count = len(w.history.undo_stack)

        def resistor(project):
            cell = next(c for c in project['cells'] if c['id'] == root)
            return next(d for d in cell['devices'] if d['id'] == rid)

        dialog = self.selected_device_symbol_editor()
        try:
            artwork = self.draw_symbol_rectangle(dialog)
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
            self.assertTrue(dialog.saved)
            self.assertEqual(dialog.result(), QDialog.Accepted)
            self.assertFalse(dialog.isVisible())
            self.assertEqual(dialog.error.text(), '')
            self.assertEqual(resistor(w.project)['value'], '22k')
            self.assertEqual(resistor(w.project)['symbol'], artwork)
            self.assertFalse(w._inspector_dirty)
            self.assertEqual(w.cid, root)
            self.assertEqual(w.selection, [rid])
            self.assertEqual(len(w.history.undo_stack), history_count + 2)
            self.assertEqual(w.saved_hash, saved_hash)
            self.assertEqual(path.read_bytes(), original_bytes)
            for old_cell, new_cell in zip(original['cells'], w.project['cells']):
                self.assertEqual(old_cell.get('symbol'), new_cell.get('symbol'))
                for old_device, new_device in zip(old_cell['devices'], new_cell['devices']):
                    if old_device['id'] != rid:
                        self.assertEqual(old_device, new_device)
            w.undo()
            self.assertEqual(resistor(w.project).get('symbol'), resistor(original).get('symbol'))
            self.assertEqual(resistor(w.project)['value'], '22k')
            w.undo()
            self.assertEqual(resistor(w.project)['value'], '10k')
            w.redo()
            w.redo()
            self.assertEqual(resistor(w.project)['value'], '22k')
            self.assertEqual(resistor(w.project)['symbol'], artwork)
            self.assertEqual(path.read_bytes(), original_bytes)
            self.assertTrue(w.save())
            saved = load_project(path)
            self.assertEqual(resistor(saved)['value'], '22k')
            self.assertEqual(resistor(saved)['symbol'], artwork)
            self.assertEqual(w.saved_hash, digest(w.project))
            self.assertEqual(w.path, path)
            w.set_project(saved, path)
            w.select([rid])
            reopened = self.selected_device_symbol_editor()
            try:
                self.assertEqual(reopened.pad.symbol, artwork)
                self.assertEqual(resistor(w.project)['value'], '22k')
                reopened.findChild(QDialogButtonBox).button(QDialogButtonBox.Cancel).click()
                self.assertFalse(reopened.saved)
            finally:
                reopened.reject()
                reopened.deleteLater()
            self.assertEqual(self.errors, [])
        finally:
            dialog.reject()
            dialog.deleteLater()

    def test_device_symbol_cancel_preserves_valid_and_invalid_property_drafts(self):
        for draft in ('22k', 'invalid resistance'):
            with self.subTest(draft=draft):
                path, _ = self.prepare(dirty=False)
                w = self.window
                w.mode_combo.setCurrentIndex(0)
                rid = self.pending_resistor(draft)
                field, root = w.form_fields['Value'], w.cid
                before, saved_hash, disk_hash = digest(w.project), w.saved_hash, w._disk_hash
                original_bytes = path.read_bytes()
                history_counts = len(w.history.undo_stack), len(w.history.redo_stack)
                with patch.object(w, 'flush_inspector', side_effect=AssertionError('Cancel applied a draft')) as flush:
                    dialog = self.selected_device_symbol_editor()
                    try:
                        self.draw_symbol_rectangle(dialog)
                        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Cancel).click()
                        flush.assert_not_called()
                        self.assertFalse(dialog.saved)
                        self.assertEqual(dialog.result(), QDialog.Rejected)
                        self.assertFalse(dialog.isVisible())
                    finally:
                        dialog.reject()
                        dialog.deleteLater()
                self.assertIs(w.form_fields['Value'], field)
                self.assertEqual(field.text(), draft)
                self.assertTrue(w._inspector_dirty)
                self.assertEqual(w.cid, root)
                self.assertEqual(w.selection, [rid])
                self.assertEqual(digest(w.project), before)
                self.assertEqual((len(w.history.undo_stack), len(w.history.redo_stack)), history_counts)
                self.assertEqual(w.saved_hash, saved_hash)
                self.assertEqual(w._disk_hash, disk_hash)
                self.assertEqual(w.path, path)
                self.assertEqual(path.read_bytes(), original_bytes)
                self.assertEqual(self.errors, [])

    def test_device_symbol_commit_failure_keeps_unsaved_artwork_available(self):
        path, _ = self.prepare(dirty=False)
        w = self.window
        w.mode_combo.setCurrentIndex(0)
        rid = next(d['id'] for d in w.cell['devices'] if d['kind'] == 'R')
        w.select([rid])
        before, saved_hash, original_bytes = digest(w.project), w.saved_hash, path.read_bytes()
        history_counts = len(w.history.undo_stack), len(w.history.redo_stack)
        dialog = self.selected_device_symbol_editor()
        try:
            artwork = self.draw_symbol_rectangle(dialog)
            with patch.object(w, 'commit', side_effect=ValueError('Injected symbol commit failure')) as commit:
                dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
                commit.assert_called_once()
            self.assertFalse(dialog.saved)
            self.assertNotEqual(dialog.result(), QDialog.Accepted)
            self.assertTrue(dialog.isVisible())
            self.assertEqual(dialog.error.text(), 'Injected symbol commit failure')
            self.assertEqual(dialog.pad.symbol, artwork)
            self.assertEqual(digest(w.project), before)
            self.assertEqual((len(w.history.undo_stack), len(w.history.redo_stack)), history_counts)
            self.assertEqual(w.saved_hash, saved_hash)
            self.assertEqual(w.path, path)
            self.assertEqual(path.read_bytes(), original_bytes)
            self.assertEqual(self.errors, [])
        finally:
            dialog.reject()
            dialog.deleteLater()


    def project_settings_action(self):
        actions = [a for a in self.window.findChildren(QAction)
                   if a.text().replace('&', '') == 'Project settings…']
        self.assertEqual(len(actions), 1)
        self.assertTrue(actions[0].isEnabled())
        return actions[0]

    def prepare_settings_cell(self):
        path, _ = self.prepare(dirty=False)
        w = self.window
        self.addCleanup(w.setVisible, w.isVisible())
        w.show()
        w.inspector.show()
        w.mode_combo.setCurrentIndex(0)
        rid = next(d['id'] for d in w.cell['devices'] if d['kind'] == 'R')
        w.select([rid])
        w.layer_combo.setCurrentText('metal1')
        w.show_layers('solo')
        self.app.processEvents()
        return path, rid

    def settings_document_snapshot(self, path):
        w = self.window
        return (digest(w.project), len(w.history.undo_stack), len(w.history.redo_stack),
                w.path, w.saved_hash, w._disk_hash, path.read_bytes(), clone(w.project['pdk']),
                w.cid, list(w.selection), w.current_mode, set(w.layout.visible_layers))

    def open_real_project_settings(self):
        self.project_settings_action().trigger()
        dialog = self.window._settings_dialog
        self.app.processEvents()
        self.assertTrue(dialog.isVisible())
        self.assertFalse(dialog.isModal())
        return dialog

    def type_visible_settings_field(self, field, value):
        self.assertTrue(field.isVisible())
        self.assertTrue(field.isEnabled())
        QTest.mouseClick(field, Qt.LeftButton)
        QTest.keyClick(field, Qt.Key_A, Qt.ControlModifier)
        QTest.keyClicks(field, value)
        self.assertEqual(field.text(), value)

    def test_settings_repeated_refused_save_preserves_modeless_drafts_and_view(self):
        path, rid = self.prepare_settings_cell()
        w = self.window
        w.analysis_fields['stop'].setText('250u')
        before = self.settings_document_snapshot(path)
        dialog = self.open_real_project_settings()
        try:
            name = dialog.findChild(QLineEdit)
            self.type_visible_settings_field(name, 'Requested project name')
            field = w.form_fields['Value']
            self.type_visible_settings_field(field, 'invalid resistance')
            for _ in range(2):
                dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
                self.assertNotEqual(dialog.result(), QDialog.Accepted)
                self.assertTrue(dialog.isVisible())
                self.assertIn('Resolve pending property edits before saving project settings.',
                              [label.text() for label in dialog.findChildren(QLabel)])
                self.assertEqual(name.text(), 'Requested project name')
                self.assertIs(w.form_fields['Value'], field)
                self.assertEqual(field.text(), 'invalid resistance')
                self.assertTrue(w._inspector_dirty)
                self.assertTrue(w.property_error.text())
                self.assertEqual(w.selection, [rid])
                self.assertEqual(self.settings_document_snapshot(path), before)
                self.assertTrue(w.analysis_dirty)
                self.assertEqual(w.analysis_fields['stop'].text(), '250u')
            self.assertEqual(self.errors, [])
        finally:
            dialog.reject()
            dialog.deleteLater()

    def test_settings_corrected_draft_can_retry_same_dialog_and_save_both_edits(self):
        path, rid = self.prepare_settings_cell()
        w = self.window
        original_bytes, saved_hash = path.read_bytes(), w.saved_hash
        history_count = len(w.history.undo_stack)
        original_pdk = clone(w.project['pdk'])
        dialog = self.open_real_project_settings()
        try:
            name = dialog.findChild(QLineEdit)
            self.type_visible_settings_field(name, 'Requested project name')
            field = w.form_fields['Value']
            self.type_visible_settings_field(field, 'invalid resistance')
            save_button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save)
            save_button.click()
            self.assertTrue(dialog.isVisible())
            self.assertIs(w.form_fields['Value'], field)
            self.type_visible_settings_field(field, '22k')
            save_button.click()
            self.assertEqual(dialog.result(), QDialog.Accepted)
            self.assertFalse(dialog.isVisible())
            self.assertEqual(w.project['name'], 'Requested project name')
            self.assertEqual(next(d['value'] for d in w.cell['devices'] if d['id'] == rid), '22k')
            self.assertFalse(w._inspector_dirty)
            self.assertEqual(w.project['pdk'], original_pdk)
            self.assertEqual(w.selection, [rid])
            self.assertEqual(len(w.history.undo_stack), history_count + 2)
            self.assertEqual(w.path, path)
            self.assertEqual(w.saved_hash, saved_hash)
            self.assertEqual(path.read_bytes(), original_bytes)
            self.assertTrue(w.save())
            saved = load_project(path)
            self.assertEqual(saved['name'], 'Requested project name')
            self.assertEqual(next(d['value'] for d in saved['cells'][0]['devices'] if d['id'] == rid), '22k')
            self.assertEqual(saved['pdk'], original_pdk)
            self.assertEqual(self.errors, [])
        finally:
            dialog.reject()
            dialog.deleteLater()

    def test_settings_cancel_preserves_unchanged_valid_and_invalid_main_window_fields(self):
        for draft in (None, '22k', 'invalid resistance'):
            with self.subTest(draft=draft):
                path, _ = self.prepare_settings_cell()
                w = self.window
                w.analysis_fields['stop'].setText('250u')
                before = self.settings_document_snapshot(path)
                dialog = self.open_real_project_settings()
                try:
                    field = w.form_fields['Value']
                    if draft is not None:
                        self.type_visible_settings_field(dialog.findChild(QLineEdit), 'Cancelled name')
                        self.type_visible_settings_field(field, draft)
                    with patch.object(w, 'flush_inspector', side_effect=AssertionError('Settings Cancel applied a draft')) as flush:
                        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Cancel).click()
                        flush.assert_not_called()
                    self.assertEqual(dialog.result(), QDialog.Rejected)
                    self.assertFalse(dialog.isVisible())
                    self.assertIs(w.form_fields['Value'], field)
                    self.assertEqual(field.text(), draft or '10k')
                    self.assertEqual(w._inspector_dirty, draft is not None)
                    self.assertEqual(self.settings_document_snapshot(path), before)
                    self.assertTrue(w.analysis_dirty)
                    self.assertEqual(w.analysis_fields['stop'].text(), '250u')
                    self.assertEqual(self.errors, [])
                finally:
                    dialog.reject()
                    dialog.deleteLater()

    def test_settings_open_with_existing_invalid_property_remains_blocked(self):
        path, _ = self.prepare_settings_cell()
        w = self.window
        field = w.form_fields['Value']
        self.type_visible_settings_field(field, 'invalid resistance')
        before = self.settings_document_snapshot(path)
        previous = getattr(w, '_settings_dialog', None)
        for _ in range(2):
            self.project_settings_action().trigger()
            self.assertIs(getattr(w, '_settings_dialog', None), previous)
            self.assertIs(w.form_fields['Value'], field)
            self.assertEqual(field.text(), 'invalid resistance')
            self.assertTrue(w._inspector_dirty)
            self.assertTrue(w.property_error.text())
            self.assertEqual(self.settings_document_snapshot(path), before)
        self.assertEqual(self.errors, [])

    def test_settings_save_and_cancel_keep_valid_analysis_and_digital_drafts(self):
        from icstudio.digital import counter_project
        for decision in (QDialogButtonBox.Save, QDialogButtonBox.Cancel):
            with self.subTest(decision=decision):
                path, _ = self.prepare(dirty=False)
                w = self.window
                self.addCleanup(w.setVisible, w.isVisible())
                w.show()
                w.set_project(counter_project(), path)
                self.assertTrue(w.save())
                original_bytes, saved_hash = path.read_bytes(), w.saved_hash
                original_analysis = clone(w.project['analysis'])
                original_digital = clone(w.project['digital'])
                digital = w.digital_window()
                digital.files.setCurrentRow(0)
                digital.editor.insertPlainText('// Pending settings source\n')
                pending_source = digital.editor.toPlainText()
                self.assertTrue(digital.dirty)
                w.analysis_fields['stop'].setText('250u')
                dialog = self.open_real_project_settings()
                try:
                    self.type_visible_settings_field(dialog.findChild(QLineEdit), 'Requested digital name')
                    dialog.findChild(QDialogButtonBox).button(decision).click()
                    self.assertEqual(dialog.result(), QDialog.Accepted if decision == QDialogButtonBox.Save else QDialog.Rejected)
                    self.assertEqual(w.project['name'], 'Requested digital name' if decision == QDialogButtonBox.Save else 'Digital counter')
                    self.assertTrue(digital.dirty)
                    self.assertEqual(digital.editor.toPlainText(), pending_source)
                    self.assertTrue(w.analysis_dirty)
                    self.assertEqual(w.analysis_fields['stop'].text(), '250u')
                    self.assertEqual(w.project['analysis'], original_analysis)
                    self.assertEqual(w.project['digital'], original_digital)
                    self.assertEqual(w.saved_hash, saved_hash)
                    self.assertEqual(w.path, path)
                    self.assertEqual(path.read_bytes(), original_bytes)
                    self.assertEqual(self.errors, [])
                finally:
                    dialog.reject()
                    dialog.deleteLater()


if __name__ == '__main__':
    unittest.main()
