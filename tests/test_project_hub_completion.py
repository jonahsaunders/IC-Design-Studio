"""A completed worker remains busy until its queued GUI result is applied."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from icstudio.project_hub_ui import ProjectHub


class Control:
    def __init__(self): self.enabled=True; self.text=''
    def setEnabled(self, value): self.enabled=value
    def setText(self, value): self.text=value


class Worker:
    def __init__(self, operation, parent):
        self.operation=operation; self.running=False; self.result=None; self.error=''
        self.finished=SimpleNamespace(connect=lambda callback:setattr(self,'deliver',callback))
    def start(self): self.running=True
    def isRunning(self): return self.running
    def finish_without_delivery(self):
        try: self.result=self.operation()
        except Exception as exc: self.error=str(exc)
        self.running=False


def hub():
    value=SimpleNamespace(worker=None,_operation_pending=False,window=SimpleNamespace(),
                          pages=Control(),nav=Control(),refresh_button=Control(),state=Control(),updates=[])
    value.busy=lambda:ProjectHub.busy(value)
    value.update_create=lambda:value.updates.append(value.busy())
    return value


class HubCompletionTests(unittest.TestCase):
    def test_close_and_second_operation_stay_blocked_until_result_delivery(self):
        value=hub();applied=[]
        def done(result):
            self.assertTrue(value.busy())
            applied.append(result)
        with patch('icstudio.project_hub_ui.HubWorker',Worker):
            ProjectHub.run_operation(value,lambda:'selected-project',done,'Preparing')
            worker=value.worker;worker.finish_without_delivery()
            self.assertFalse(worker.isRunning());self.assertTrue(value.busy())
            ignored=[];ProjectHub.closeEvent(value,SimpleNamespace(ignore=lambda:ignored.append(True)))
            self.assertEqual(ignored,[True])
            ProjectHub.reject(value)
            self.assertEqual(value.state.text,'Finishing the current PDK operation…')
            ProjectHub.run_operation(value,lambda:'wrong-project',applied.append,'Second operation')
            self.assertIs(value.worker,worker);self.assertEqual(applied,[])
            worker.deliver()
        self.assertEqual(applied,['selected-project']);self.assertFalse(value.busy())
        self.assertTrue(all(c.enabled for c in (value.pages,value.nav,value.refresh_button)))
        self.assertEqual(value.updates,[False])

    def test_public_refresh_remains_blocked_while_owned_result_can_refresh(self):
        value=hub();refreshes=[]
        value._refresh_contents=lambda:refreshes.append(value.busy())
        value._operation_pending=True
        ProjectHub.refresh(value)
        self.assertEqual(refreshes,[])
        value._refresh_contents()
        self.assertEqual(refreshes,[True])
        value._operation_pending=False
        ProjectHub.refresh(value)
        self.assertEqual(refreshes,[True,False])

    def test_worker_error_restores_controls_without_applying_a_result(self):
        value=hub();applied=[]
        def fail():raise ValueError('Original package failed verification')
        with patch('icstudio.project_hub_ui.HubWorker',Worker):
            ProjectHub.run_operation(value,fail,applied.append,'Preparing')
            value.worker.finish_without_delivery();self.assertTrue(value.busy());value.worker.deliver()
        self.assertEqual(applied,[]);self.assertFalse(value.busy())
        self.assertEqual(value.state.text,'Original package failed verification')
        self.assertTrue(value.pages.enabled)

    def test_result_handler_failure_and_start_failure_do_not_leave_hub_stuck(self):
        value=hub()
        def fail_result(_):raise ValueError('Could not apply selected project')
        with patch('icstudio.project_hub_ui.HubWorker',Worker):
            ProjectHub.run_operation(value,lambda:{},fail_result,'Preparing')
            value.worker.finish_without_delivery();value.worker.deliver()
        self.assertFalse(value.busy());self.assertEqual(value.state.text,'Could not apply selected project')
        class FailedStart(Worker):
            def start(self):raise RuntimeError('Could not start worker')
        with patch('icstudio.project_hub_ui.HubWorker',FailedStart):
            with self.assertRaisesRegex(RuntimeError,'Could not start worker'):
                ProjectHub.run_operation(value,lambda:{},lambda _:None,'Preparing')
        self.assertFalse(value.busy());self.assertTrue(value.pages.enabled)


if __name__=='__main__':unittest.main()
