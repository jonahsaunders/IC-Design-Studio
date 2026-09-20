"""Offscreen campaign lifecycle and bounded table smoke tests."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
import time
import unittest
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication,QWidget,QLabel
from icstudio.model import clone
from icstudio.run_manager import RunManager
from icstudio.test_plans import prepare
from icstudio.test_plan_ui import TestPlanWindow
from icstudio.campaign_ui import CampaignWindow,prepare_campaign
from icstudio.verification_campaigns import create
from tests.test_verification_campaigns import fixture,prepare_job


class StudioFixture(QWidget):
    def __init__(self,project):
        super().__init__();self.project=project;self.dark=False;self.run_manager=RunManager(self)
    def prepare_simulation(self,settings,engine='builtin',project=None,cid=None):
        return prepare_job(settings,engine,project or self.project,cid or self.project['top'])
    def flush_inspector(self):return True


class CampaignGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.windows=[]
        self.addCleanup(self.close_windows)

    def close_windows(self):
        for window in self.windows:
            if isinstance(window,CampaignWindow):window.shutdown()
            window.close();window.deleteLater()
        self.app.processEvents()

    def until(self,condition,timeout=20):
        deadline=time.monotonic()+timeout
        while not condition() and time.monotonic()<deadline:
            self.app.processEvents();time.sleep(.01)
        self.app.processEvents();self.assertTrue(condition(),'Timed out waiting for GUI campaign state')

    def test_interactive_matrix_pages_conditions_without_losing_export_data(self):
        p,plan=fixture(85);p['test_plans']=[plan];studio=StudioFixture(p);self.windows.append(studio)
        jobs=prepare(p,plan,prepare_job)
        studio.run_manager.rows=[dict(id=str(i),job=job,state='Queued',log='') for i,job in enumerate(jobs)]
        window=TestPlanWindow(studio);self.windows.insert(0,window)
        self.assertEqual(window.table.columnCount(),42);self.assertEqual(len(window.data['conditions']),85)
        window.move_conditions(1);self.assertIn('41–80',window.condition_label.text())
        window.move_conditions(1);self.assertEqual(window.table.columnCount(),7)
        self.assertFalse(window.next_conditions.isEnabled());self.assertTrue(window.previous_conditions.isEnabled())

    def test_background_capture_uses_saved_revision_and_results_are_paged(self):
        p,plan=fixture(105);studio=StudioFixture(p);self.windows.append(studio);note=QLabel(studio)
        original=clone(p)
        capture=prepare_campaign(studio,plan,self.root/'background',note)
        studio.project['name']='Edited during capture'
        self.until(lambda:not capture.isRunning() and bool(getattr(studio,'_campaign_windows',[])))
        window=studio._campaign_windows[0];self.windows.insert(0,window)
        self.assertEqual(window.campaign.job(1)['project']['name'],original['name'])
        self.assertEqual(studio.project['name'],'Edited during capture')
        self.assertEqual(window.table.rowCount(),100);window.move(1);self.assertEqual(window.table.rowCount(),5)
        window.close();self.assertFalse(window.campaign.counts()['paused'],'Closing an inspector must not pause other workers')

    def test_worker_pause_reopen_resume_preserves_project_and_waveforms(self):
        p,plan=fixture(5);studio=StudioFixture(p);self.windows.append(studio)
        campaign=create(self.root/'lifecycle',p,plan,prepare_job)
        window=CampaignWindow(studio,campaign.path);self.windows.insert(0,window);window.show();window.workers.setValue(1)
        window.run();self.until(lambda:bool(campaign.counts().get('Running')))
        studio.project['name']='Current unsaved work';window.close()
        self.until(lambda:window.process.state()==QProcess.NotRunning)
        self.assertTrue(campaign.counts()['paused'])
        reopened=CampaignWindow(studio,campaign.path);self.windows.insert(0,reopened);reopened.show();reopened.run()
        self.until(lambda:reopened.process.state()==QProcess.NotRunning,30)
        self.assertEqual(campaign.counts().get('Complete'),5,campaign.page())
        reopened.refresh();reopened.table.selectRow(0);reopened.open_case()
        self.windows.insert(0,reopened.inspector)
        self.assertTrue(reopened.inspector.result['traces'])
        self.assertEqual(studio.project['name'],'Current unsaved work')
        self.assertNotEqual(reopened.inspector.project['name'],studio.project['name'])


if __name__=='__main__':unittest.main()
