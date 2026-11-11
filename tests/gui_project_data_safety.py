"""Real desktop save/open guards and folder snapshots, without external engines.

Run in a fresh process: a prior QCoreApplication cannot own these widgets.
Only dialog answers and selected paths are supplied by the test. Project
loading, dirty-state decisions, saving, editor drafts and controls are real.
"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QListWidget, QMessageBox, QPushButton

from icstudio.gui import Studio, StudioCore
from icstudio.model import clone, digest, example, file_digest, load_project, save_project
from icstudio.project_hub_ui import ProjectHub
from icstudio.project_store import load_directory
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


if __name__ == '__main__':
    unittest.main()
