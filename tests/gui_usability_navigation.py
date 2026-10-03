"""Small-screen project creation, linked help, keyboard search and progress scopes."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from icstudio.gui import Studio
from icstudio.model import digest
from icstudio.project_hub_ui import ProjectHub
from icstudio.student_hub_ui import StudentHub


class UsabilityNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        settings = QSettings(str(self.root/'settings.ini'), QSettings.IniFormat)
        settings.setFallbacksEnabled(False)
        settings.setValue('onboarding/show', False)
        with patch('icstudio.gui.QSettings', return_value=settings), \
             patch('icstudio.gui.QStandardPaths.writableLocation', return_value=str(self.root/'data')):
            self.studio = Studio(recover=False)
        self.studio.show()
        self.errors = []
        self.studio.error = self.errors.append
        self.hook = patch.object(sys, 'excepthook', side_effect=lambda kind,value,tb:self.errors.append(str(value)))
        self.hook.start()
        QTest.qWait(30)

    def tearDown(self):
        for dialog in self.studio.findChildren(ProjectHub):
            dialog.close()
        self.studio.saved_hash = digest(self.studio.project)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            self.studio.close()
        self.app.processEvents()
        self.hook.stop()
        self.folder.cleanup()
        self.assertEqual(self.errors, [])

    def test_project_hub_fits_scaled_screens_and_keeps_create_reachable(self):
        hub = ProjectHub(self.studio)
        hub.show()
        available = self.studio.screen().availableGeometry()
        self.assertLessEqual(hub.width(), available.width())
        self.assertLessEqual(hub.height(), available.height())
        original = digest(self.studio.project)
        for width,height in ((911,512),(960,540)):
            with self.subTest(logical_screen=(width,height)):
                hub.resize(width,height)
                QTest.qWait(30)
                self.assertEqual((hub.width(),hub.height()), (width,height))
                self.assertEqual(hub.sidebar.width(), 150)
                self.assertTrue(hub.pdks.visualItemRect(hub.pdks.currentItem()).intersects(hub.pdks.viewport().rect()))
                hub.content_scroll.ensureWidgetVisible(hub.create_button)
                self.app.processEvents()
                viewport = hub.content_scroll.viewport()
                center = hub.create_button.mapTo(viewport,hub.create_button.rect().center())
                self.assertTrue(viewport.rect().contains(center))
                self.assertTrue(hub.create_button.isEnabled())
                self.assertEqual(digest(self.studio.project), original)
        hub.resize(1160,790)
        self.app.processEvents()
        self.assertEqual(hub.sidebar.width(), 190)
        self.assertEqual(hub.back_button.text(), 'Back to workspace')

    def test_f1_opens_current_linked_guide_and_preserves_historical_access(self):
        self.studio.help_dialog()
        dialog = self.studio._document_dialog
        self.app.processEvents()
        self.assertEqual(Path(dialog.browser.source().toLocalFile()).name, 'USER_GUIDE.md')
        text = dialog.browser.toPlainText()
        self.assertNotIn('[your first circuit](GETTING_STARTED.md)', text)
        self.assertNotIn('# Working with IC Design Studio 0.3', text)
        dialog.browser.anchorClicked.emit(QUrl('GETTING_STARTED.md'))
        self.app.processEvents()
        self.assertEqual(Path(dialog.browser.source().toLocalFile()).name, 'GETTING_STARTED.md')
        dialog.browser.backward()
        self.app.processEvents()
        self.assertEqual(Path(dialog.browser.source().toLocalFile()).name, 'USER_GUIDE.md')
        dialog.close()
        self.studio.open_editor_doc('WORKFLOWS_0.3.md')
        self.assertIn('Historical snapshot.', self.studio._document_dialog.browser.toPlainText())
        self.studio._document_dialog.close()

    def test_help_enter_moves_between_matches_and_wraps_without_closing(self):
        self.studio.help_dialog()
        dialog = self.studio._document_dialog
        dialog.search.setText('waveform')
        dialog.search.setFocus()
        first = dialog.browser.textCursor().selectionStart()
        self.assertEqual(dialog.browser.textCursor().selectedText().lower(), 'waveform')
        QTest.keyClick(dialog.search, Qt.Key_Return)
        second = dialog.browser.textCursor().selectionStart()
        self.assertGreater(second, first)
        self.assertTrue(dialog.isVisible())
        QTest.keyClick(dialog.search, Qt.Key_Return, Qt.ShiftModifier)
        self.assertEqual(dialog.browser.textCursor().selectionStart(), first)
        dialog.next_match.click()
        self.assertEqual(dialog.browser.textCursor().selectionStart(), second)
        dialog.previous_match.click()
        self.assertEqual(dialog.browser.textCursor().selectionStart(), first)
        QTest.keyClick(dialog.search, Qt.Key_Return, Qt.ShiftModifier)
        self.assertGreater(dialog.browser.textCursor().selectionStart(), second)
        dialog.search.clear()
        self.assertFalse(dialog.previous_match.isEnabled())
        self.assertFalse(dialog.next_match.isEnabled())
        QTest.keyClick(dialog.search, Qt.Key_Return)
        self.assertTrue(dialog.isVisible())
        dialog.close()

    def test_readme_link_uses_main_when_source_identity_is_unknown(self):
        self.studio.open_editor_doc('USER_GUIDE.md')
        dialog = self.studio._document_dialog
        for commit,expected in (('unknown','main'),('f954c3c1c837c5ff88733a292a163cd2982b504f','f954c3c1c837c5ff88733a292a163cd2982b504f')):
            with self.subTest(commit=commit), patch('icstudio.build_identity.identity',return_value={'commit':commit}), \
                 patch.object(QDesktopServices,'openUrl',return_value=True) as opened:
                dialog.browser.anchorClicked.emit(QUrl('../README.md#features'))
                self.assertEqual(opened.call_args.args[0].toString(), 'https://github.com/jonahsaunders/IC-Design-Studio/blob/'+expected+'/README.md#features')
        dialog.close()

    def test_student_progress_labels_match_selected_and_all_pdk_scopes(self):
        hub = StudentHub(self.studio)
        state = hub.portfolio.state
        from icstudio.student_hub import complete
        available = [l for l in hub.data['lessons'] if not l.get('inverter_profile') or hub.inverter_profiles[l['inverter_profile']]['ready']]
        selected = [l for l in available if not l.get('inverter_profile') or l['inverter_profile']==hub.process_picker.currentData()]
        self.assertGreater(len(available),len(selected))
        self.assertIn(f'0 of {len(selected)} lessons complete · selected inverter PDK',hub.total.text())
        self.assertIn(f'0 of {len(available)} across all available PDK revisions',hub.total.text())
        hub.process_picker.setCurrentIndex((hub.process_picker.currentIndex()+1)%hub.process_picker.count())
        selected = [l for l in available if not l.get('inverter_profile') or l['inverter_profile']==hub.process_picker.currentData()]
        self.assertIn(f'{sum(complete(state,l) for l in selected)} of {len(selected)} lessons complete',hub.total.text())
        hub.guide.close()
        hub.close()


if __name__ == '__main__':
    unittest.main()
