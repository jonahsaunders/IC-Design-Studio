"""The hosting probe must let Python workers and Qt callbacks make progress."""
import sys
import threading
import time
import unittest

from PySide6.QtCore import QCoreApplication, QTimer

from icstudio.host_annotations_probe import wait


class HostingWaitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_python_worker_and_qt_callbacks_both_progress(self):
        started, finished = threading.Event(), threading.Event()
        ticks = []

        def work():
            started.wait()
            # Multiple I/O-like waits require the worker to reacquire the GIL.
            for _ in range(20):
                time.sleep(.002)
            finished.set()

        worker = threading.Thread(target=work)
        timer = QTimer()
        timer.timeout.connect(lambda: (ticks.append(True), started.set()))
        interval = sys.getswitchinterval()
        try:
            # Expose reliance on incidental interpreter thread switches.
            sys.setswitchinterval(.1)
            worker.start()
            timer.start(5)
            wait(finished.is_set, 'Python worker was starved', seconds=1)
            self.assertGreater(len(ticks), 1)
        finally:
            timer.stop()
            sys.setswitchinterval(interval)
            started.set()
            worker.join(timeout=5)
        self.assertFalse(worker.is_alive())

    def test_timeout_reports_current_state_and_stops_polling(self):
        state = ['starting']
        polls = []
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: state.__setitem__(0, 'connection rejected'))
        timer.start(10)
        try:
            with self.assertRaisesRegex(AssertionError, 'connection rejected'):
                wait(lambda: polls.append(True) or False, lambda: state[0], seconds=.08)
        finally:
            timer.stop()
        count = len(polls)
        self.app.processEvents()
        self.assertEqual(len(polls), count)

    def test_completed_predicate_does_not_evaluate_diagnostics(self):
        def message():
            self.fail('Successful waits must not evaluate failure diagnostics')

        wait(lambda: True, message, seconds=0)


if __name__ == '__main__':
    unittest.main()
