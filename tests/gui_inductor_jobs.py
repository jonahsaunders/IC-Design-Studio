"""Qt worker lifecycle checks: stale completions, failures and close safety."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject,Signal,QTimer
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest

from icstudio.model import example
from icstudio.inductor_ui import InductorDialog
from icstudio import inductor


class Owner(QWidget):
    def __init__(self):
        super().__init__();self.project=example('empty');self.cid=self.project['top'];self.cell=self.project['cells'][0]
        self.layout=type('Layout',(),{'locked_layers':set()})()


class WorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def wait(self,condition):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            self.app.processEvents()
            if condition():return
            QTest.qWait(5)
        self.fail('Worker completion timed out')

    def test_obsolete_completion_cannot_enable_apply_and_error_is_recoverable(self):
        owner=Owner();original=inductor.plan
        def slow(*args,**kwargs):
            time.sleep(.08)
            return original(*args,**kwargs)
        with patch('icstudio.inductor.plan',side_effect=slow):
            dialog=InductorDialog(owner);dialog.show();ticks=[];timer=QTimer(dialog);timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(1));timer.start()
            self.wait(lambda:bool(dialog.preview.paths))
            dialog.fields['turns'].setValue(7);dialog.refresh_preview()
            self.wait(lambda:dialog.proposal is not None)
            self.assertEqual(dialog.proposal['spec']['turns'],7);self.assertGreater(len(ticks),4)
        with patch('icstudio.inductor.plan',side_effect=RuntimeError('Injected validation failure')):
            dialog.refresh_preview();self.wait(lambda:dialog.last_error is not None)
            self.assertIn('Injected',dialog.error.text());self.assertFalse(dialog.apply_button.isEnabled());self.assertTrue(dialog.preview.paths)
        dialog.refresh_preview();self.wait(lambda:dialog.proposal is not None)
        dialog.close();owner.close()

    def test_close_cancels_pending_work_without_applying_project_changes(self):
        owner=Owner();original=inductor.plan
        def slow(*args,**kwargs):time.sleep(.08);return original(*args,**kwargs)
        with patch('icstudio.inductor.plan',side_effect=slow):
            dialog=InductorDialog(owner);dialog.show();self.wait(lambda:bool(dialog.preview.paths))
            dialog.close();self.wait(lambda:not dialog.jobs)
        self.assertTrue(dialog.closed);self.assertFalse(owner.cell['devices']);self.assertFalse(owner.cell['shapes']);owner.close()


if __name__=='__main__':unittest.main()
