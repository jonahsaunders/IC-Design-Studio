"""Exercise every ordered pair of the app's workspace entry points on Qt."""
import itertools
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from icstudio.gui import Studio
from icstudio.getting_started import examples
from icstudio.model import digest
from icstudio.sar_example import sar_project
from icstudio.student_hub_ui import show as student
from icstudio.mixed_signal_ui import show as mixed
from icstudio.project_hub_ui import show as projects


class WorkspaceTransitions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        settings = QSettings(str(root/'settings.ini'), QSettings.IniFormat)
        settings.setFallbacksEnabled(False)
        settings.setValue('onboarding/show', False)
        with patch('icstudio.gui.QSettings', return_value=settings), patch(
                'icstudio.gui.QStandardPaths.writableLocation', return_value=str(root/'data')):
            self.w = Studio(recover=False)
        self.errors = []
        self.w.error = self.errors.append
        self.hook = patch.object(sys, 'excepthook', side_effect=lambda t, v, tb:self.errors.append(str(v)))
        self.hook.start()
        self.w.set_project(sar_project())
        self.w.resize(1440, 930)
        self.w.show()
        self.app.processEvents()

    def tearDown(self):
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            self.w.saved_hash = digest(self.w.project)
            for d in self.w.findChildren(QDialog):
                if d.isWindow():d.close()
            self.w.close()
        self.app.processEvents()
        self.w.finish_recovery()
        self.hook.stop()
        self.folder.cleanup()
        self.assertEqual(self.errors, [])

    def settle(self):
        self.app.processEvents()
        self.assertTrue(self.w.isEnabled())
        self.assertIsNone(self.app.activeModalWidget())
        self.assertEqual(self.errors, [])

    def enter(self, mode):
        w = self.w
        # Close is the published return path from auxiliary dialogs.
        for d in w.findChildren(QDialog):
            if d.isWindow() and d.isVisible():
                self.assertTrue(d.close())
        if mode.startswith('circuit:'):
            self.trigger_menu('View', ['Schematic','Layout','Linked views'][int(mode[-1])])
            self.assertEqual(w.app_workspaces.currentIndex(), 0)
            self.assertIsNot(w.design_widget(), getattr(w, '_digital_window', None))
        elif mode.startswith('digital:'):
            self.trigger_menu('Digital', 'Digital flow…')
            d = w._digital_window
            QTest.mouseClick(d.shell.mode_group.button(int(mode[-1])), Qt.LeftButton)
            self.assertIs(w.design_widget(), d)
            self.assertFalse(w.toolbar.isVisible())
        elif mode.startswith('analog:'):
            self.trigger_menu('Simulate', 'Analog design workspace…')
            d = w.analog_workspace
            d.tabs.setCurrentIndex(int(mode[-1]))
            self.assertTrue(d.isVisible())
            self.assertEqual(w.app_workspaces.currentIndex(), 0)
        elif mode == 'mixed':
            self.trigger_menu('Simulate', 'Mixed-signal experiment…')
            self.assertTrue(w._mixed_signal_dialog.isVisible())
            self.assertEqual(w.app_workspaces.currentIndex(), 0)
        elif mode == 'student':
            self.trigger_menu('View', 'Student Hub')
            self.assertTrue(w._student_hub.isVisible())
            self.assertEqual(w.app_workspaces.currentIndex(), 1)
            self.assertFalse(w.toolbar.isVisible())
        elif mode == 'gallery':
            self.assertTrue(w.start_here().isVisible())
        elif mode.startswith('projects:'):
            d = projects(w, mode.split(':')[1])
            self.app.processEvents()
            self.assertIs(self.app.activeModalWidget(), d)
            self.assertTrue(d.close())
        self.settle()

    def trigger_menu(self, menu, title):
        def actions(parent):
            for action in parent.actions():
                if action.menu():yield from actions(action.menu())
                else:yield action
        action=next(a for a in actions(self.w.task_menus[menu]) if a.text().replace('&','')==title)
        self.assertTrue(action.isEnabled())
        action.trigger()

    def test_every_ordered_pair(self):
        modes = ([f'circuit:{i}' for i in range(3)] + [f'digital:{i}' for i in range(3)] +
                 [f'analog:{i}' for i in range(5)] + ['mixed', 'student', 'gallery'] +
                 ['projects:projects', 'projects:pdks', 'projects:new'])
        identity = self.w.project['id']
        for source, target in itertools.permutations(modes, 2):
            with self.subTest(source=source, target=target):
                self.enter(source)
                self.enter(target)
                self.assertEqual(self.w.project['id'], identity)
        print(f'PASS {len(modes)*(len(modes)-1)} ordered workspace transitions', flush=True)

    def test_each_gallery_example_from_student_and_rtl(self):
        for origin in ('student', 'digital'):
            for entry in examples():
                with self.subTest(origin=origin, example=entry['id']):
                    self.w.set_project(sar_project())
                    if origin == 'student':student(self.w)
                    else:
                        self.w.cid=self.w.project['mixed_signal']['digital_cell']
                        self.w.digital_window()
                    self.w.saved_hash = digest(self.w.project)
                    gallery = self.w.start_here()
                    for i in range(gallery.example_list.count()):
                        if gallery.example_list.item(i).data(Qt.UserRole)['id'] == entry['id']:
                            gallery.example_list.setCurrentRow(i);break
                    QTest.mouseClick(gallery.open_button, Qt.LeftButton)
                    QTest.qWait(90)
                    self.assertFalse(gallery.isVisible())
                    self.assertEqual(self.w.app_workspaces.currentIndex(), 0)
                    self.assertTrue(self.w.schematic.isVisible())
                    self.settle()
        print('PASS 26 Student Hub / RTL to gallery example transitions', flush=True)

    def test_lesson_to_example_hides_stale_guide(self):
        hub = student(self.w)
        self.w.saved_hash = digest(self.w.project)
        hub.select_lesson('f-first');hub.start_selected()
        self.assertTrue(hub.guide.isVisible())
        self.w.saved_hash = digest(self.w.project)
        self.assertTrue(self.w.open_gallery_example(examples()[0]))
        self.assertFalse(hub.guide.isVisible())
        self.assertFalse(hub.isVisible())
        self.settle()

    def test_cancel_keeps_lesson_and_tab(self):
        hub = student(self.w)
        identity = self.w.project['id']
        observed = []
        def cancel():
            prompt = self.app.activeModalWidget()
            observed.append(prompt.windowTitle())
            QTest.mouseClick(prompt.button(QMessageBox.Cancel), Qt.LeftButton)
        QTimer.singleShot(50, cancel)
        hub.select_lesson('f-first');hub.start_selected()
        self.assertEqual(observed, ['Save project?'])
        self.assertEqual(self.w.project['id'], identity)
        self.assertTrue(hub.isVisible())
        self.settle()

    def test_rapid_example_switch_does_not_open_stale_experiment(self):
        self.w.saved_hash = digest(self.w.project)
        self.w.open_gallery_example(next(e for e in examples() if e['id']=='sar-adc'))
        self.w.saved_hash = digest(self.w.project)
        self.w.open_gallery_example(examples()[0])
        QTest.qWait(100)
        d = getattr(self.w, '_mixed_signal_dialog', None)
        self.assertTrue(d is None or not d.isVisible())
        self.settle()

    def test_hub_roundtrip_retains_rtl_draft(self):
        self.w.cid=self.w.project['mixed_signal']['digital_cell']
        d = self.w.digital_window()
        d.editor.insertPlainText('// retained draft\n')
        text = d.editor.toPlainText()
        student(self.w)
        self.w.show_design_workspace()
        self.assertIs(self.w.design_widget(), d)
        self.assertEqual(d.editor.toPlainText(), text)
        self.assertTrue(d.dirty)
        self.assertFalse(self.w.toolbar.isVisible())

    def test_invalid_rtl_draft_prevents_switch_and_example_replacement(self):
        self.w.cid=self.w.project['mixed_signal']['digital_cell']
        d=self.w.digital_window()
        d.top.selectAll();QTest.keyClicks(d.top,'invalid module name')
        self.assertTrue(d.dirty)
        identity=self.w.project['id']
        self.trigger_menu('View','Schematic')
        self.assertIs(self.w.design_widget(),d)
        self.assertTrue(d.dirty)
        self.assertIn('Verilog module identifier',d.message.text())
        self.assertFalse(self.w.open_gallery_example(examples()[0]))
        self.assertEqual(self.w.project['id'],identity)
        self.assertEqual(d.top.text(),'invalid module name')
        self.assertIn('Verilog module identifier',d.message.text())
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):
            d.reload_sources()
        self.assertFalse(d.dirty)

    def test_closing_from_hub_preserves_design_panels(self):
        from PySide6.QtWidgets import QDockWidget
        panels={dock.objectName():not dock.isHidden() for dock in self.w.findChildren(QDockWidget)}
        student(self.w)
        self.w.saved_hash=digest(self.w.project)
        self.assertTrue(self.w.close())
        self.assertEqual(self.w.app_workspaces.currentIndex(),0)
        self.w.load_editor_workspace('Last session')
        for dock in self.w.findChildren(QDockWidget):
            if dock.objectName() in panels:self.assertEqual(not dock.isHidden(),panels[dock.objectName()])

    def test_cancel_close_returns_to_hub(self):
        student(self.w)
        with patch.object(self.w,'maybe_save',return_value=False):
            self.assertFalse(self.w.close())
        self.assertEqual(self.w.app_workspaces.currentIndex(),1)
        self.assertTrue(self.w._student_hub.isVisible())
        self.settle()

    def test_reopening_gallery_reuses_one_window(self):
        first=self.w.start_here()
        for _ in range(12):
            first.reject()
            student(self.w)
            self.assertIs(self.w.start_here(),first)
            self.w.show_design_workspace()
        first.reject()
        self.settle()


if __name__ == '__main__':
    unittest.main()
