"""Exercise the Tools menu, real Qt HTTP transport and native project history."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt, QSignalBlocker, QTimer
from PySide6.QtTest import QTest
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

    def test_setup_and_request_disclosure(self):
        panel = self.panel
        panel.configure('custom',panel.profile('custom')[0],'','')
        self.assertFalse(panel.setup_button.isHidden())
        self.assertFalse(panel.send_button.isEnabled())
        self.assertIn('Set up',panel.status.text())
        self.assertIn('Whole circuit',panel.scope_detail.text())
        self.assertTrue(panel.preview.isHidden())
        QTest.keyClick(panel.disclosure, Qt.Key_Space)
        self.assertFalse(panel.preview.isHidden())
        self.assertIn('Studio context',panel.preview.toPlainText())
        QTest.keyClick(panel.disclosure, Qt.Key_Space)
        self.assertTrue(panel.preview.isHidden())

    def test_ask_ai_from_student_hub_and_lesson_guide(self):
        from icstudio.model import digest

        studio, panel = self.studio, self.panel
        studio.show()
        studio.project['name'] = 'Private open project marker'
        spaces = studio.app_workspaces
        spaces.tabs.setCurrentIndex(1)
        hub = spaces.hub()
        hub.select_lesson('project-miller')
        quick = hub.prediction
        hub.preview.setCurrentWidget(quick)
        quick.questions.setCurrentIndex(quick.questions.findData('null'))
        before = digest(studio.project), digest(hub.portfolio.state)
        base = panel.profile('custom')[0]
        panel.configure('custom', base, '', 'session-secret')
        count = len(self.server.requests)
        quick.ask_button.setFocus()
        QTest.keyClick(quick.ask_button, Qt.Key_Space)
        self.app.processEvents()
        self.assertEqual(spaces.currentIndex(), 1)
        self.assertTrue(panel.isVisible())
        self.assertTrue(panel.note.hasFocus())
        self.assertEqual(panel.action.currentData(), 'lesson')
        self.assertEqual(panel.windowTitle(), 'Resisty')
        self.assertTrue(panel.resisty_avatar.isVisible())
        self.assertTrue(panel.resisty_avatar.pixmap().hasAlphaChannel())
        self.assertEqual(panel.lesson_context['step'], quick.step['title'])
        self.assertIn(quick.step['instructions'], panel.preview.toPlainText())
        self.assertIn('You are Resisty', panel.preview.toPlainText())
        self.assertNotIn('Private open project marker', panel.preview.toPlainText())
        self.assertNotIn('session-secret', panel.preview.toPlainText())
        self.assertEqual(set(panel.lesson_context), {'lesson', 'overview', 'step', 'type', 'instructions'})
        self.assertTrue(panel.disclosure.isChecked())
        self.assertFalse(panel.setup_button.isHidden())
        self.assertFalse(panel.send_button.isEnabled())
        self.assertEqual(len(self.server.requests), count)

        panel.configure('custom', base, 'local-test', 'session-secret')
        panel.note.clear()
        self.assertFalse(panel.send_button.isEnabled())
        panel.send()
        self.assertEqual(len(self.server.requests), count)
        first_question = 'Which coefficient should I inspect?'
        panel.note.setText(first_question)
        with patch.object(studio, 'flush_inspector', side_effect=AssertionError('Lesson help reads authored text only')):
            self.ask('Look for the term that multiplies s.')
        self.assertEqual(panel.answer.toPlainText(), 'Look for the term that multiplies s.')
        self.assertEqual(len(self.server.requests), count + 1)
        self.assertIsNone(panel.pinned)
        self.assertEqual(before, (digest(studio.project), digest(hub.portfolio.state)))

        quick.ask_button.click()
        self.assertIn('multiplies s', panel.answer.toPlainText())
        panel.note.setText('What should I compare with the units of that coefficient?')
        self.assertIn(first_question, panel.preview.toPlainText())
        self.ask('Compare with the resistance on the second-stage branch.')
        self.assertEqual(len(self.server.requests), count + 2)
        quick.questions.setCurrentIndex(0)
        quick.ask_button.click()
        self.assertNotIn(first_question, panel.preview.toPlainText())
        self.assertEqual(panel.lesson_context['step'], quick.step['title'])
        self.assertEqual(len(self.server.requests), count + 2)

        hub.select_lesson('c-temperature')
        hub.start_selected()
        guide = hub.guide
        self.assertEqual(guide.ask_button.text(), 'Ask Resisty…')
        self.assertFalse(guide.ask_button.icon().pixmap(24,24).isNull())
        anchor = next(i for i, step in enumerate(guide.lesson['steps']) if step['id'] == 'anchor')
        guide.steps.setCurrentIndex(anchor)
        guide.ask_button.click()
        self.assertEqual(spaces.currentIndex(), 0)
        self.assertEqual(panel.lesson_context['step'], guide.active_step['title'])
        self.assertIn('RFIX', panel.preview.toPlainText())
        guide.lesson_tabs.setCurrentIndex(guide.hints_index)
        guide.ask_button.click()
        self.assertEqual(panel.lesson_context['type'], 'quiz')
        self.assertIn('two-point calibration', panel.preview.toPlainText())

        guide.steps.setCurrentIndex(len(guide.lesson['steps'])-1)
        with QSignalBlocker(guide.notes):
            guide.notes.setPlainText('Private student reflection marker')
        guide.ask_button.click()
        self.assertEqual(panel.lesson_context['type'], 'reflection')
        self.assertNotIn('Private student reflection marker', panel.preview.toPlainText())
        self.assertEqual(len(self.server.requests), count + 2)
        panel.action.setCurrentIndex(panel.action.findData('circuit'))
        self.assertEqual(panel.windowTitle(), 'AI Assistant')
        self.assertTrue(panel.resisty_avatar.isHidden())

    def test_compact_workspace_commands_and_view_picker(self):
        studio = self.studio
        self.panel.hide()
        studio.show()
        QTest.qWait(80)
        studio.resize(2200,900)
        QTest.qWait(30)
        self.assertFalse(studio.mode_combo.isHidden())
        bar = studio.ribbon.currentWidget()
        self.assertTrue(bar.more.isHidden(), (studio.size(), bar.size(), [b.sizeHint().width() for b in bar.buttons]))
        wide_height = studio.ribbon.height()
        studio.resize(920,680)
        QTest.qWait(30)
        self.assertFalse(studio.compact_view.isHidden())
        self.assertTrue(studio.mode_combo.isHidden())
        self.assertLessEqual(studio.ribbon.height(),wide_height+4)
        self.assertTrue(bar.more.isVisible())
        overflow = bar.more.menu()
        self.assertEqual(overflow.actions(),[b.defaultAction() for b in bar.buttons if b.isHidden()])
        source = studio.command_actions['Place wire']
        wire = next(b.defaultAction() for b in bar.buttons if b.text()=='Wire')
        source.setEnabled(False)
        self.assertFalse(wire.isEnabled())
        source.setEnabled(True)
        self.assertTrue(wire.isEnabled())
        # Open from the keyboard and dismiss before choosing a mode.
        opened = []
        def close_menu():
            opened.append(overflow.isVisible())
            overflow.close()
        QTimer.singleShot(30,close_menu)
        bar.more.setFocus()
        QTest.keyClick(bar.more,Qt.Key_Space)
        self.assertEqual(opened,[True])
        if wire in overflow.actions():
            wire.trigger()
        else:
            next(b for b in bar.buttons if b.defaultAction() == wire).click()
        self.assertEqual(studio.schematic.tool,'connect')
        studio.cancel_tool()
        studio.compact_view.setFocus()
        QTest.keyClick(studio.compact_view, Qt.Key_Down)
        self.assertEqual(studio.mode_combo.currentIndex(),1)
        self.assertEqual(studio.current_mode,'layout')
        studio.mode_combo.setCurrentIndex(2)
        self.assertEqual(studio.compact_view.currentText(),'Linked views')
        studio.resize(2200,900)
        QTest.qWait(30)
        self.assertFalse(studio.mode_combo.isHidden())
        self.assertEqual(studio.mode_combo.currentIndex(),2)

    def test_selection_failed_run_and_testbench(self):
        studio, panel = self.studio, self.panel
        r1 = next(d for d in studio.cell['devices'] if d['name']=='R1')
        studio.selection = [r1['id']]
        count = len(self.server.requests)
        panel.send_button.click()
        self.assertEqual(len(self.server.requests), count)
        self.assertIn('selection or run changed', panel.status.text())
        self.assertTrue(panel.disclosure.isChecked())
        self.assertIn('R1 (10k)', panel.scope_detail.text())
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
        self.assertIn('Transient A',panel.scope_title.text())
        self.assertNotIn('privatevalue', panel.preview.toPlainText())
        self.assertIn('Singular matrix at vout', panel.preview.toPlainText())
        self.assertIn('devices_mentioned_in_log', panel.preview.toPlainText())
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
