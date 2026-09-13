"""Real QProcess/Qt lifecycle checks; the external fixture is not a field solver."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QTimer, QSettings, QProcess
from PySide6.QtWidgets import QApplication, QWidget

from icstudio import inductor_em, openems_backend
from icstudio.inductor_em_ui import CharacterizationDialog
from icstudio.openems_ui import OpenEMSJob
from icstudio.model import clone
from icstudio.layout import rect
from test_openems import coil


class Owner(QWidget):
    def __init__(self, root):
        super().__init__(); self.project, self.did = coil(); self.jobs_dir = root/'runs'
        self.settings = QSettings(str(root/'settings.ini'), QSettings.IniFormat); self.commits = 0

    def idle_edit(self): return True

    def commit(self, operation, label):
        p = clone(self.project); operation(p); self.project = p; self.commits += 1


class JobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([]); cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.exceptions = []; self.old_hook = sys.excepthook
        sys.excepthook = lambda kind, value, tb: self.exceptions.append(str(value))
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.owner = Owner(self.root); self.owner.show()
        self.characterization = CharacterizationDialog(self.owner, self.owner.project['top'], self.owner.did)
        self.characterization.show(); self.characterization.openems(); self.dialog = self.characterization._openems
        self.dialog.python.setText(sys.executable); self.dialog.fields['samples'][0].setValue(3)
        self.patch = patch.object(openems_backend, 'DRIVER', Path(__file__).parent/'fixtures/openems_fake_driver.py'); self.patch.start()

    def tearDown(self):
        self.dialog.reject(); self.wait(lambda: not self.dialog.job.running)
        self.characterization.reject(); self.owner.close(); self.patch.stop(); self.temp.cleanup()
        sys.excepthook = self.old_hook
        self.assertEqual(self.exceptions, [], "Unhandled Qt callback exceptions")

    def wait(self, condition, seconds=10):
        if condition(): return
        loop = QEventLoop(); timer = QTimer(); limit = QTimer(); limit.setSingleShot(True)
        timer.timeout.connect(lambda: loop.quit() if condition() else None); limit.timeout.connect(loop.quit)
        timer.start(5); limit.start(seconds*1000)
        try: loop.exec()
        finally: timer.stop(); limit.stop()
        self.assertTrue(condition(), 'Qt job completion timed out: '+self.dialog.status.text())

    def test_probe_four_stages_responsiveness_and_automatic_attachment(self):
        ticks = []; timer = QTimer(); timer.setInterval(5); timer.timeout.connect(lambda: ticks.append(1)); timer.start()
        self.dialog.start(True); self.wait(lambda: not self.dialog.job.running)
        self.assertIn('Installation ready', self.dialog.status.text())
        self.dialog.start(False); self.wait(lambda: not self.dialog.job.running); timer.stop()
        self.assertEqual(self.owner.commits, 1, self.dialog.status.text()); self.assertGreater(len(ticks), 5)
        self.assertEqual(len(self.dialog.job.columns), 4)
        self.assertTrue(self.dialog.folder.isEnabled())
        self.assertIn("ICSTUDIO_EM:", self.dialog.log.toPlainText())
        self.assertTrue((self.dialog.job.directory/'results.s2p').exists())
        result, _ = inductor_em.result_status(self.owner.project, self.owner.project['top'], self.owner.did)
        self.assertAlmostEqual(result['rows'][0]['inductance_h'], 2e-9, places=15)
        if os.environ.get('ICSTUDIO_EM_SCREENSHOT'):
            self.dialog.grab().save(os.environ['ICSTUDIO_EM_SCREENSHOT'])

    def test_cancel_close_and_timeout_reap_process_without_attachment(self):
        with patch.dict(os.environ, ICSTUDIO_TEST_EM_MODE='hang'):
            self.dialog.start(False); self.wait(lambda: 'cells' in self.dialog.status.text())
            self.dialog.job.cancel(); self.wait(lambda: not self.dialog.job.running)
            self.assertEqual(self.dialog.job.process.state(), QProcess.NotRunning)
            self.dialog.fields['timeout_s'][0].setValue(1); self.dialog.start(False)
            self.wait(lambda: not self.dialog.job.running)
            self.assertIn('time limit', self.dialog.status.text())
            self.dialog.fields['timeout_s'][0].setValue(60); self.dialog.start(False)
            self.wait(lambda: 'cells' in self.dialog.status.text()); self.characterization.reject()
            self.wait(lambda: not self.dialog.job.running)
        self.assertEqual(self.owner.commits, 0); self.assertTrue(self.dialog.closed)
        self.dialog.start(False); self.assertFalse(self.dialog.job.running)

    def test_failures_and_unconverged_zero_exit_are_recoverable(self):
        for mode in ('missing', 'crash', 'unconverged'):
            with patch.dict(os.environ, ICSTUDIO_TEST_EM_MODE=mode):
                self.dialog.start(False); self.wait(lambda: not self.dialog.job.running)
            self.assertEqual(self.owner.commits, 0); self.assertTrue(self.dialog.run.isEnabled())
        self.dialog.start(False); self.wait(lambda: not self.dialog.job.running)
        self.assertEqual(self.owner.commits, 1, self.dialog.status.text())

    def test_changed_context_and_project_cannot_receive_completed_results(self):
        self.dialog.start(False); self.wait(lambda: self.dialog.job.mode == 'base-1')
        self.owner.project['cells'][0]['shapes'].append(rect('RDL_B', 200000, 200000, 10000, 10000))
        self.wait(lambda: not self.dialog.job.running)
        self.assertEqual(self.owner.commits, 0); self.assertIn('not attached', self.dialog.status.text())
        self.dialog.start(False); self.wait(lambda: self.dialog.job.mode == 'base-1')
        self.owner.project['id'] = 'another-project'; self.wait(lambda: not self.dialog.job.running)
        self.assertEqual(self.owner.commits, 0); self.assertIn('open project changed', self.dialog.status.text())

    def test_automatic_setup_compact_controls_and_remembered_options(self):
        from icstudio.openems_ui import OpenEMSDialog
        self.dialog.reject()
        self.owner.settings.setValue('engine/openems_settings', '{broken')
        with patch('icstudio.openems_runtime.discover', return_value=(sys.executable, 'Included openEMS')):
            self.dialog = OpenEMSDialog(self.characterization); self.dialog.show()
        self.assertEqual(self.dialog.python.text(), sys.executable)
        self.assertFalse(self.dialog.advanced.isVisible()); self.assertFalse(self.dialog.log.isVisible())
        self.dialog.quality.setCurrentIndex(1)
        self.assertFalse(self.dialog.mesh_check.isChecked()); self.assertIn('not checked', self.dialog.quality_note.text())
        self.dialog.fields['samples'][0].setValue(3)
        self.dialog.fields['f_start_hz'][0].setValue(2)
        self.dialog.fields['f_stop_hz'][0].setValue(4)
        self.dialog.run.click(); self.wait(lambda: not self.dialog.job.running)
        self.assertEqual(self.owner.commits, 1, self.dialog.status.text())
        self.assertEqual(len(self.dialog.job.columns), 2)
        self.dialog.reject(); self.dialog = OpenEMSDialog(self.characterization)
        self.assertEqual(self.dialog.fields['f_start_hz'][0].value(), 2)
        self.assertEqual(self.dialog.fields['f_stop_hz'][0].value(), 4)
        self.assertEqual(self.dialog.quality.currentIndex(), 1)

    def test_run_and_cancel_stay_visible_in_small_windows(self):
        self.dialog.advanced_toggle.setChecked(True); self.dialog.log_toggle.setChecked(True)
        self.dialog.resize(520, 400); self.app.processEvents()
        self.assertLessEqual(self.dialog.height(), 400)
        for button in (self.dialog.run, self.dialog.cancel_button, self.dialog.folder):
            bottom = button.mapTo(self.dialog, button.rect().bottomRight()).y()
            self.assertLess(bottom, self.dialog.height())
        self.assertGreater(self.dialog.body_scroll.verticalScrollBar().maximum(), 0)

    def test_single_job_limit_and_missing_executable(self):
        self.dialog.python.setText(str(self.root/'absent'))
        self.dialog.start(False); self.assertFalse(self.dialog.job.running)
        self.dialog.python.setText(sys.executable)
        with patch.dict(os.environ, ICSTUDIO_TEST_EM_MODE='hang'):
            self.dialog.start(False); self.wait(lambda: self.dialog.job.mode == 'base-1')
            other = OpenEMSJob()
            with self.assertRaisesRegex(ValueError, 'Another openEMS'): other.start(sys.executable)
        self.assertEqual(self.owner.commits, 0)


if __name__ == '__main__': unittest.main()
