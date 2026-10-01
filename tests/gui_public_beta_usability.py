"""Keyboard, draft recovery, run availability and compact mixed-signal controls."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAccessible, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QDialog, QLineEdit

from icstudio.gui import Studio
from icstudio.model import clone, digest
from icstudio.mixed_signal_ui import show
from icstudio.sar_example import sar_project


class PublicBetaUsabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        if sys.platform == 'win32' and cls.app.platformName() == 'offscreen':
            fonts = Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'
            for name in ('segoeui.ttf', 'segoeuib.ttf', 'arial.ttf'):
                if QFontDatabase.addApplicationFont(str(fonts/name)) < 0:
                    raise RuntimeError('Could not load '+name+' for GUI measurements.')

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(); root = Path(self.folder.name)
        settings = QSettings(str(root/'settings.ini'), QSettings.IniFormat)
        settings.setFallbacksEnabled(False); settings.setValue('onboarding/show', False)
        settings.setValue('engine/ngspice', '/custom/simulator/ngspice')
        with patch('icstudio.gui.QSettings', return_value=settings), \
                patch('icstudio.gui.QStandardPaths.writableLocation', return_value=str(root/'data')):
            self.studio = Studio(recover=False)
        self.studio.set_project(sar_project()); self.studio.saved_hash = digest(self.studio.project)
        self.studio.show(); self.errors = []
        self.studio.error = self.errors.append
        self.hook = patch.object(sys, 'excepthook', side_effect=lambda kind, value, tb: self.errors.append(str(value)))
        self.hook.start(); self.dialog = show(self.studio); self.app.processEvents()

    def tearDown(self):
        self.studio.run_manager.rows.clear()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            self.dialog.close(); self.studio.saved_hash = digest(self.studio.project); self.studio.close()
        self.app.processEvents(); self.hook.stop(); self.folder.cleanup()
        self.assertEqual(self.errors, [])

    def test_bad_json_is_recoverable_without_uncaught_signals(self):
        d = self.dialog; original = clone(self.studio.project)
        for text in ('[]', 'null', '{', json.dumps(dict(d.base_config, inputs=[None])),
                     json.dumps(dict(d.base_config, stimuli={'vin':[]}))):
            with self.subTest(text=text):
                d.config.setPlainText(text); self.app.processEvents()
                self.assertIn('Correct the bridge configuration', d.status.text())
                self.assertFalse(d.controls['Apply configuration'].isEnabled())
                self.assertFalse(d.controls['Run coupled simulation'].isEnabled())
                self.assertEqual(self.studio.project, original)
                self.assertEqual(self.errors, [])
        d.config.setPlainText(json.dumps(d.base_config)); self.app.processEvents()
        self.assertTrue(d.controls['Apply configuration'].isEnabled())
        self.assertTrue(d.period.isEnabled()); self.assertTrue(d.voltage.isEnabled())

    def test_buttons_follow_run_and_result_availability(self):
        d = self.dialog; manager = self.studio.run_manager
        self.assertFalse(d.controls['Show analog waveforms'].isEnabled())
        self.assertFalse(d.controls['Cancel selected run'].isEnabled())
        self.assertNotIn('Default: 0.93', d.status.text())
        row = dict(id='active', name='SAR fixture', state='Running', progress=10, log='',
                   job=dict(settings={'type':'mixed_signal'}, project=clone(self.studio.project)))
        manager.rows.append(row); d.refresh_runs()
        self.assertFalse(d.controls['Run coupled simulation'].isEnabled())
        self.assertTrue(d.controls['Cancel selected run'].isEnabled())
        with patch.object(manager, 'enqueue') as enqueue:
            d.call(d.run); enqueue.assert_not_called()
        self.assertIn('already has an active coupled run', d.status.text())
        row['state'] = 'Stopping'; d.refresh_runs()
        self.assertFalse(d.controls['Cancel selected run'].isEnabled())
        row['state'] = 'Cancelled'; d.refresh_runs()
        self.assertTrue(d.controls['Run coupled simulation'].isEnabled())
        self.assertFalse(d.controls['Show analog waveforms'].isEnabled())

    def test_navigation_retains_draft_and_close_offers_apply_discard_cancel(self):
        d = self.dialog; original = self.studio.project['mixed_signal']['stimuli']['vin'][0][1]
        d.voltage.setText('.4'); d.analog(); self.assertFalse(d.isVisible())
        self.assertIs(show(self.studio), d); self.assertEqual(d.voltage.text(), '.4')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel):
            self.assertFalse(d.close()); self.assertFalse(self.studio.maybe_save())
        self.assertEqual(d.voltage.text(), '.4')
        self.assertEqual(self.studio.project['mixed_signal']['stimuli']['vin'][0][1], original)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Apply):
            self.assertTrue(d.close())
        self.assertEqual(self.studio.project['mixed_signal']['stimuli']['vin'], [[0., .4]])
        self.studio.undo(); self.assertEqual(self.studio.project['mixed_signal']['stimuli']['vin'][0][1], original)
        d = self.dialog = show(self.studio); d.voltage.setText('.6')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            self.assertTrue(d.close())
        self.assertFalse(d.has_draft()); self.assertIs(show(self.studio), d)
        self.assertEqual(float(d.voltage.text()), original)

    def test_invalid_draft_cannot_close_or_be_applied_over_external_edit(self):
        d = self.dialog; d.config.setPlainText('[]')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Apply):
            self.assertFalse(d.close())
        self.assertTrue(d.isVisible()); self.assertEqual(d.config.toPlainText(), '[]')
        d.config.setPlainText(json.dumps(d.base_config)); d.voltage.setText('.4')
        self.studio.commit(lambda p: p['mixed_signal']['stimuli'].update(vin=[[0., .8]]), 'External bridge edit')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Apply):
            self.assertIs(show(self.studio), d)
        self.assertIn('configuration changed', d.status.text())
        self.assertEqual(self.studio.project['mixed_signal']['stimuli']['vin'], [[0., .8]])

    def test_compact_layout_keyboard_and_engine_names(self):
        d = self.dialog; self.assertEqual(d.paths['ngspice'].text(), '/custom/simulator/ngspice')
        for size in (13, 26):
            d.setStyleSheet(f'QWidget {{ font-size: {size}px; }}'); d.resize(720, 600)
            for tab in range(d.tabs.count()):
                d.tabs.setCurrentIndex(tab); QTest.qWait(30)
                self.assertEqual(d.width(), 720)
                for button in d.findChildren(QPushButton):
                    if button.isVisible():
                        self.assertFalse(button.autoDefault())
                        self.assertGreater(button.width(), 0)
                        self.assertTrue(d.rect().contains(button.mapTo(d, button.rect().topLeft())))
                        self.assertLessEqual(button.mapTo(d, button.rect().bottomRight()).x(), d.width())
        d.setStyleSheet(''); d.tabs.setCurrentIndex(0)
        d.period.setFocus(); QTest.keyClick(d.period, Qt.Key_Return); self.app.processEvents()
        self.assertTrue(d.isVisible()); self.assertFalse(d.has_draft())
        d.tabs.setCurrentIndex(1)
        names = [QAccessible.queryAccessibleInterface(b).text(QAccessible.Name)
                 for b in d.findChildren(QPushButton) if b.text() == 'Browse…']
        self.assertEqual(set(names), {'Browse for '+name+' executable' for name in d.paths})
        before = digest(self.studio.project); gallery = self.studio.start_here(); gallery.activateWindow()
        gallery.search.setText('waveform'); gallery.search.setFocus(); QTest.keyClick(gallery.search, Qt.Key_Return)
        self.app.processEvents(); self.assertEqual(digest(self.studio.project), before)
        self.assertTrue(gallery.example_list.hasFocus())
        self.assertTrue(all(not b.autoDefault() and not b.isDefault() for b in gallery.findChildren(QPushButton)))
        gallery.search.setText('no matching example'); self.assertFalse(gallery.open_button.isEnabled()); gallery.close()

    def test_close_still_works_after_project_switch(self):
        self.dialog.revision_timer.stop(); self.studio.set_project(sar_project())
        self.dialog.controls['Close'].click(); self.assertFalse(self.dialog.isVisible())

    def test_saved_numeric_units_do_not_create_an_unedited_draft(self):
        self.studio.commit(lambda p: p['mixed_signal'].update(period='1u', stimuli={'vin':[[0, '.93']]}), 'Unit strings')
        d = self.dialog = show(self.studio); before = digest(self.studio.project)
        self.assertFalse(d.has_draft()); self.assertTrue(d.apply())
        self.assertEqual(digest(self.studio.project), before)
        with patch.object(QMessageBox, 'question', side_effect=AssertionError('No edits require no prompt')):
            self.assertTrue(d.close())


if __name__ == '__main__': unittest.main()
