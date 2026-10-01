"""Actual QAction signals must preserve Student Hub callbacks and scale values."""
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

try:
    from PySide6.QtCore import QSettings
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
        self.hub = StudentHub(self.studio)

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
        actions = {a.text(): a for a in self.hub.more.menu().actions()}
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


if __name__ == '__main__':
    unittest.main()
