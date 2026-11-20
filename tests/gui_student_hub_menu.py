"""Exercise the top workspace menu and interactive lesson previews."""
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

try:
    from PySide6.QtCore import QSettings, Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication, 'PySide6 is required for menu signal regression')
class StudentHubMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from icstudio.gui import Studio
        from icstudio.student_hub_ui import StudentHub
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        settings = QSettings(str(root/'settings.ini'), QSettings.IniFormat)
        settings.setFallbacksEnabled(False)
        with patch('icstudio.gui.QSettings', return_value=settings), patch(
                'icstudio.gui.QStandardPaths.writableLocation', return_value=str(root/'data')):
            self.studio = Studio(recover=False)
        self.studio.maybe_save = lambda: True
        self.callbacks = ExitStack()
        self.invoked = {name: self.callbacks.enter_context(patch.object(StudentHub, name))
                        for name in ('continue_learning', 'setup', 'export', 'locate', 'reload_progress')}
        self.studio.show()
        self.app.processEvents()
        self.spaces = self.studio.app_workspaces
        self.assertLess(self.spaces.tabs.mapTo(self.studio, self.spaces.tabs.rect().bottomLeft()).y(),
                        self.studio.toolbar.geometry().top())
        self.assertIsNone(getattr(self.studio, '_student_hub', None))
        QTimer.singleShot(100, self.spaces.hub_menu.close)
        QTest.mouseClick(self.spaces.menu_button, Qt.LeftButton)
        self.app.processEvents()
        self.assertEqual(self.spaces.currentIndex(), 1)
        self.hub = self.studio._student_hub

    def tearDown(self):
        self.hub.reject()
        self.studio.close()
        self.app.processEvents()
        self.callbacks.close()
        self.folder.cleanup()

    def test_more_commands_receive_their_callback_instead_of_checked_state(self):
        commands = {
            'Continue learning': ('continue_learning', (), {}),
            'Engine setup…': ('setup', (), {}),
            'Export learning record…': ('export', (), {}),
            'Export portfolio report…': ('export', (), {'report': True}),
            'Locate lesson project…': ('locate', (), {}),
            'Reload progress': ('reload_progress', (), {}),
        }
        actions = {a.text(): a for a in self.spaces.menu_button.menu().actions()}
        for title, (method, args, kwargs) in commands.items():
            with self.subTest(command=title):
                invoked = self.invoked[method]
                invoked.reset_mock()
                actions[title].trigger()
                invoked.assert_called_once_with(*args, **kwargs)
        with patch.object(self.studio, 'open_editor_doc') as opened:
            actions['Feature map'].trigger()
            opened.assert_called_once_with('STUDENT_HUB.md')

    def test_text_size_actions_apply_each_named_scale(self):
        menu = self.hub.text_size_menu
        for scale, action in zip((100, 125, 150, 200), menu.actions()):
            with self.subTest(scale=scale):
                action.trigger()
                self.assertEqual(self.hub.text_scale, scale)
                self.assertEqual(self.studio.settings.value('student/textScale', type=int), scale)
                self.assertEqual([a.data() for a in menu.actions() if a.isChecked()], [scale])

    def test_preview_answers_and_filters_preserve_project_and_progress(self):
        from icstudio.model import digest
        hub = self.hub
        before = digest(self.studio.project), digest(hub.portfolio.state)
        hub.status_filter.setCurrentText('Ready to start')
        self.assertEqual(hub.selected()['id'], 'f-first')
        self.assertEqual(hub.lessons.count(), 1)
        hub.preview.setCurrentWidget(hub.study_notes)
        self.assertIn(hub.material['lessons']['f-first']['worked_example'], hub.study_notes.toPlainText())
        hub.preview.setCurrentWidget(hub.prediction)
        self.app.processEvents()
        prediction = hub.prediction
        step = prediction.step
        wrong = prediction.answers.button((step['answer'] + 1) % len(step['options']))
        QTest.mouseClick(wrong, Qt.LeftButton)
        self.assertIn('Try again.', prediction.result.text())
        right = prediction.answers.button(step['answer'])
        right.setFocus()
        QTest.keyClick(right, Qt.Key_Space)
        self.assertTrue(right.isChecked())
        self.assertIn('Correct. ' + step['explanation'], prediction.result.text())
        self.spaces.tabs.setCurrentIndex(0)
        self.spaces.tabs.setCurrentIndex(1)
        self.assertIs(hub.preview.currentWidget(), prediction)
        self.assertTrue(right.isChecked())
        self.assertEqual(before, (digest(self.studio.project), digest(hub.portfolio.state)))
        hub.status_filter.setCurrentText('Completed')
        self.assertEqual(hub.lessons.count(), 0)
        self.assertFalse(hub.start.isEnabled())
        self.assertTrue(hub.reset_filters.isVisible())
        QTest.mouseClick(hub.reset_filters, Qt.LeftButton)
        self.assertGreater(hub.lessons.count(), 1)
        hub.status_filter.setCurrentText('Prerequisites needed')
        hub.select_lesson('f-first')
        self.assertEqual(hub.selected()['id'], 'f-first')
        self.assertEqual(hub.status_filter.currentIndex(), 0)


if __name__ == '__main__':
    unittest.main()
