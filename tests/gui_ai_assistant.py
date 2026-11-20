"""Exercise the Tools menu, real Qt HTTP transport and native project history."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from icstudio.gui import Studio
from icstudio.model import clone, example
from tests.test_ai_assistant import rc_spec


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append((self.path, self.headers.get('Authorization'), body))
        self.server.gate.wait(2)
        response = json.dumps({'choices':[{'message':{'content':self.server.answer}}]}).encode()
        self.send_response(self.server.code)
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        try:
            self.wfile.write(response)
        except OSError:
            pass


class AssistantDesktop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
        cls.server.requests = []
        cls.server.gate = threading.Event()
        cls.worker = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.gate.set()
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.settings_file = Path(tmp.name) / 'settings.ini'
        settings = QSettings(str(self.settings_file), QSettings.IniFormat)
        settings.setFallbacksEnabled(False)
        settings.setValue('onboarding/show',False)
        with patch('icstudio.gui.QSettings',return_value=settings), patch('icstudio.gui.QStandardPaths.writableLocation',return_value=tmp.name):
            self.studio = Studio(recover=False)
        self.studio.maybe_save = lambda: True
        self.studio.error = self.fail
        self.addCleanup(self.studio.close)
        self.studio.set_project(example())
        tools = self.studio.task_menus['Tools']
        next(a for a in tools.actions() if a.text() == 'AI Assistant…').trigger()
        self.panel = self.studio._ai_assistant
        self.panel.configure('custom', f'http://127.0.0.1:{self.server.server_port}/v1', 'local-test', 'session-secret')
        self.server.code = 200
        self.server.gate.set()

    def wait(self, predicate):
        end = time.monotonic() + 6
        while not predicate() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate(), self.panel.status.text())

    def ask(self, answer):
        self.server.answer = answer
        preview = self.panel.preview.toPlainText()
        count = len(self.server.requests)
        self.panel.send_button.click()
        self.wait(lambda: len(self.server.requests) > count and self.panel.reply is None)
        url, token, body = self.server.requests[-1]
        self.assertEqual((url,token), ('/v1/chat/completions','Bearer session-secret'))
        self.assertEqual(body['messages'][0]['content'],preview)
        self.assertNotIn('session-secret',preview)

    def test_selection_failed_run_and_testbench(self):
        studio, panel = self.studio, self.panel
        r1 = next(d for d in studio.cell['devices'] if d['name']=='R1')
        studio.selection = [r1['id']]
        count = len(self.server.requests)
        panel.send_button.click()
        self.assertEqual(len(self.server.requests), count)
        self.assertIn('selection or run changed', panel.status.text())
        self.ask('R1 and C1 set the pole.')
        self.assertIn('"R1"', panel.preview.toPlainText())
        self.assertNotIn('"C1"', panel.preview.toPlainText())
        self.assertIn('pole', panel.answer.toPlainText())
        job = dict(project=clone(studio.project),cell=studio.cid,settings={'type':'tran'},engine='ngspice')
        row = dict(id='failed_a',name='Transient A',state='Failed',job=job,log='Singular matrix at vout. API_KEY=privatevalue')
        bad_spec = dict(id='failed_b',name='Limit B',state='Complete',job=job,log='',
                        result={'specifications':[dict(name='Gain',status='FAIL',value=2,min=10)]})
        other = {**row,'id':'wrong','job':{**job,'project':example()}}
        studio.run_manager.rows = [row,bad_spec,other]
        panel.action.setCurrentIndex(panel.action.findData('failure'))
        self.assertEqual(panel.run.count(),2)
        self.assertIn('Gain',panel.preview.toPlainText())
        panel.run.setCurrentIndex(panel.run.findData('failed_a'))
        self.assertNotIn('privatevalue', panel.preview.toPlainText())
        self.assertIn('Singular matrix at vout', panel.preview.toPlainText())
        self.ask('Inspect the DC path at vout.')
        studio.run_manager.rows.clear()
        panel.action.setCurrentIndex(panel.action.findData('bench'))
        before = clone(studio.cell)
        self.ask(json.dumps(rc_spec()))
        self.assertTrue(panel.add_button.isEnabled(),panel.status.text())
        self.assertFalse(studio.project.get('testbenches'))
        panel.add_button.click()
        self.assertEqual(studio.project['testbenches'][0]['name'],'rc_check')
        self.assertEqual(studio.cell,before)
        studio.undo()
        self.assertFalse(studio.project.get('testbenches'))
        self.assertEqual(studio.cell,before)
        studio.settings.sync()
        self.assertNotIn('session-secret', self.settings_file.read_text())

    def test_invalid_stale_cancel_and_retry(self):
        panel = self.panel
        panel.action.setCurrentIndex(panel.action.findData('bench'))
        self.ask('not a testbench')
        self.assertFalse(panel.add_button.isEnabled())
        panel.answer.setPlainText(json.dumps(rc_spec()))
        panel.validate_button.click()
        self.assertTrue(panel.add_button.isEnabled(),panel.status.text())
        self.studio.commit(lambda p:p.update(name='A newer revision'), 'Rename')
        panel.add_button.click()
        self.assertIn('circuit changed',panel.status.text())
        self.assertFalse(self.studio.project.get('testbenches'))
        panel.action.setCurrentIndex(panel.action.findData('circuit'))
        self.server.code = 429
        self.ask('unused')
        self.assertIn('quota',panel.status.text())
        self.server.code = 200
        self.server.gate.clear()
        panel.send_button.click()
        self.assertIsNotNone(panel.reply)
        panel.cancel_button.click()
        self.assertIsNone(panel.reply)
        self.server.gate.set()
        self.ask('new answer')
        self.assertEqual(panel.answer.toPlainText(),'new answer')
        self.studio.set_project(example('empty'))
        self.assertFalse(panel.answer.toPlainText())
        self.assertFalse(panel.send_button.isEnabled())
