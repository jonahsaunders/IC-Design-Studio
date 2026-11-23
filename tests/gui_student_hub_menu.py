"""Exercise Student Hub navigation, progression and interactive previews."""
import os
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

try:
    from PySide6.QtCore import QSettings, Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLabel, QPlainTextEdit, QScrollArea
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
        self.studio.show()
        self.app.processEvents()
        self.spaces = self.studio.app_workspaces
        self.assertLess(self.spaces.tabs.mapTo(self.studio, self.spaces.tabs.rect().bottomLeft()).y(),
                        self.studio.toolbar.geometry().top())
        self.assertIsNone(getattr(self.studio, '_student_hub', None))
        QTimer.singleShot(100, self.spaces.hub_menu.close)
        QTest.mouseClick(self.spaces.menu_button, Qt.LeftButton)
        self.app.processEvents()
        self.assertEqual(self.spaces.currentIndex(), 1)
        self.hub = self.studio._student_hub

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
        actions = {a.text(): a for a in self.spaces.menu_button.menu().actions()}
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
                self.assertEqual([a.data() for a in menu.actions() if a.isChecked()], [scale])

    def test_preview_answers_and_filters_preserve_project_and_progress(self):
        from icstudio.model import digest
        hub = self.hub
        before = digest(self.studio.project), digest(hub.portfolio.state)
        hub.world_map.cards['foundations'].click()
        hub.status_filter.setCurrentText('Ready to start')
        self.assertEqual(hub.selected()['id'], 'f-first')
        self.assertEqual(hub.lessons.count(), 1)
        hub.preview.setCurrentWidget(hub.study_notes)
        self.assertIn(hub.material['lessons']['f-first']['worked_example'], hub.study_notes.toPlainText())
        hub.preview.setCurrentWidget(hub.prediction)
        self.app.processEvents()
        prediction = hub.prediction
        step = prediction.step
        wrong = prediction.answers.button((step['answer'] + 1) % len(step['options']))
        QTest.mouseClick(wrong, Qt.LeftButton)
        self.assertIn('Try again.', prediction.result.text())
        right = prediction.answers.button(step['answer'])
        right.setFocus()
        QTest.keyClick(right, Qt.Key_Space)
        self.assertTrue(right.isChecked())
        self.assertIn('Correct. ' + step['explanation'], prediction.result.text())
        self.spaces.tabs.setCurrentIndex(0)
        self.spaces.tabs.setCurrentIndex(1)
        self.assertIs(hub.preview.currentWidget(), prediction)
        self.assertTrue(right.isChecked())
        self.assertEqual(before, (digest(self.studio.project), digest(hub.portfolio.state)))
        hub.status_filter.setCurrentText('Completed')
        self.assertEqual(hub.lessons.count(), 0)
        self.assertFalse(hub.start.isEnabled())
        self.assertTrue(hub.reset_filters.isVisible())
        QTest.mouseClick(hub.reset_filters, Qt.LeftButton)
        self.assertGreater(hub.lessons.count(), 1)
        hub.status_filter.setCurrentText('Prerequisites needed')
        hub.select_lesson('f-first')
        self.assertEqual(hub.selected()['id'], 'f-first')
        self.assertEqual(hub.status_filter.currentIndex(), 0)

    def test_world_map_uses_earned_progress_and_shares_selection_with_list(self):
        from icstudio.model import clone
        from icstudio.student_hub import lesson_stamp

        hub = self.hub
        self.assertTrue(hub.world_map.isVisible())
        self.assertEqual(set(hub.world_map.cards), set(hub.path_titles))
        card = hub.world_map.cards['foundations']
        self.assertGreaterEqual(card.height(), 100)
        self.studio.activateWindow()
        self.app.processEvents()
        card.setFocus()
        QTest.keyClick(card, Qt.Key_Space)
        self.app.processEvents()
        self.assertTrue(hub.trail.isVisible())
        self.assertTrue(hub.back.hasFocus())
        next_lesson = hub.trail.rows['f-connect']
        next_lesson.click()
        self.assertIn('Prerequisites needed', next_lesson.accessibleDescription())
        self.assertEqual(hub.start.text(), 'Practice lesson')

        state = clone(hub.portfolio.state)
        lesson = hub.by_id['f-first']
        state['lessons'][lesson['id']] = {
            'stamp': lesson_stamp(lesson),
            'steps': {step['id']: {'kind': step['kind'], 'evidence': {}} for step in lesson['steps']},
        }
        hub.portfolio.write(state)
        hub.fill()
        self.assertIn('Completed', hub.trail.rows['f-first'].accessibleDescription())
        self.assertIn('Ready to start', hub.trail.rows['f-connect'].accessibleDescription())
        self.assertEqual(card.progress.value(), 1)
        self.assertEqual(hub.selected()['id'], 'f-connect')

        hub.mode_buttons['list'].click()
        self.assertTrue(hub.lessons.isVisible())
        self.assertEqual(self.studio.settings.value('student/viewMode'), 'list')
        self.assertEqual(hub.selected()['id'], 'f-connect')
        hub.mode_buttons['map'].click()
        self.assertTrue(hub.trail.rows['f-connect'].isChecked())
        hub.status_filter.setCurrentText('Completed')
        self.assertEqual(set(hub.trail.rows), {'f-first'})
        self.assertIn('First circuits  ·  1/3',
                      [label.text() for label in hub.trail.widget().findChildren(QLabel)])
        hub.back.click()
        self.app.processEvents()
        self.assertTrue(card.hasFocus())
        hub.search.setText('LC filters')
        self.assertTrue(hub.lessons.isVisible())
        self.assertEqual(hub.selected()['id'], 'a-lc-bode')
        hub.search.clear()
        self.assertTrue(hub.world_map.isVisible())

    def test_hints_reveal_per_question_in_preview_and_guide(self):
        from icstudio.model import digest

        hub = self.hub
        hub.select_lesson('project-miller')
        hub.preview.setCurrentWidget(hub.prediction)
        preview = hub.prediction
        self.assertEqual(preview.questions.count(), 5)
        lesson = hub.selected()
        content = hub.material['hints'][lesson['id']]
        self.assertTrue(preview.hints.isHidden())
        before = digest(self.studio.project), digest(hub.portfolio.state)
        preview.hint_button.setFocus()
        QTest.keyClick(preview.hint_button, Qt.Key_Space)
        first, _, advice = preview.hints.rows[0]
        self.assertEqual(first.accessibleName(), content['miller-effect'][0][0])
        self.assertTrue(advice.isHidden())
        first.setFocus()
        QTest.keyClick(first, Qt.Key_Space)
        self.assertTrue(first.isChecked())
        self.assertTrue(advice.isVisible())
        self.assertEqual(advice.text(), content['miller-effect'][0][1])
        self.assertTrue(all(row[2].isHidden() for row in preview.hints.rows[1:]))
        preview.questions.setCurrentIndex(preview.questions.findData('null'))
        self.assertTrue(preview.hints.isHidden())
        self.assertFalse(first.isChecked())
        self.assertEqual(preview.step['id'], 'null')
        self.assertEqual(first.accessibleName(), content['null'][0][0])
        self.assertEqual(before, (digest(self.studio.project), digest(hub.portfolio.state)))

        hub.start_selected()
        guide = hub.guide
        index = next(i for i, step in enumerate(lesson['steps']) if step['id'] == 'sweep')
        guide.steps.setCurrentIndex(index)
        guide.lesson_tabs.setCurrentIndex(guide.hints_index)
        self.assertEqual(guide.hint_question.currentData(), 'sweep')
        first, _, advice = guide.hints.rows[0]
        self.assertEqual(first.accessibleName(), content['sweep'][0][0])
        before = digest(self.studio.project), digest(hub.portfolio.state)
        first.click()
        self.assertTrue(advice.isVisible())
        self.assertEqual(advice.text(), content['sweep'][0][1])
        guide.hint_question.setCurrentIndex(0)
        self.assertTrue(advice.isHidden())
        self.assertEqual(first.accessibleName(), content['miller-effect'][0][0])
        self.assertEqual(guide.active_step['id'], 'sweep')
        self.assertEqual(before, (digest(self.studio.project), digest(hub.portfolio.state)))

    def test_hints_wrap_at_large_text_sizes(self):
        from icstudio.student_hub_ui import QuestionHints, student_style

        entries = self.hub.material['hints']['c-temperature']['predict']
        area = QScrollArea()
        area.setWidgetResizable(True)
        panel = QuestionHints()
        area.setWidget(panel)
        area.resize(300, 450)
        panel.set_entries(entries)
        try:
            for dark in (False, True):
                with self.subTest(dark=dark):
                    area.setStyleSheet(student_style(dark, 200))
                    area.show()
                    self.app.processEvents()
                    for reveal, question, answer in panel.rows:
                        reveal.setChecked(True)
                        self.app.processEvents()
                        for text in (question, answer):
                            self.assertGreaterEqual(text.height(), text.heightForWidth(text.width()))
                    self.assertEqual(area.horizontalScrollBar().maximum(), 0)
                    self.assertGreater(area.verticalScrollBar().maximum(), 0)
        finally:
            area.close()

    def test_ask_ai_can_open_an_unconfigured_assistant_from_quick_check(self):
        hub, studio = self.hub, self.studio
        self.assertIsNone(getattr(studio, '_ai_assistant', None))
        hub.select_lesson('f-first')
        hub.preview.setCurrentWidget(hub.prediction)
        hub.prediction.ask_button.click()
        self.app.processEvents()
        panel = studio._ai_assistant
        self.assertTrue(panel.isVisible())
        self.assertFalse(panel.setup_button.isHidden())
        self.assertFalse(panel.send_button.isEnabled())
        self.assertIsNone(panel.reply)
        self.assertEqual(self.spaces.currentIndex(), 1)
        self.assertEqual(panel.scope_title.text(), hub.selected()['title'])
        self.assertIn('Predict the response', panel.preview.toPlainText())
        panel.close()
        self.assertIs(hub.preview.currentWidget(), hub.prediction)

    def test_layout_topics_open_and_resume_the_shared_amplifier(self):
        hub, studio = self.hub, self.studio
        hub.world_map.cards['layout'].click()
        self.assertEqual(hub.lessons.count(), 23)
        topics = {label.text().split('  ·', 1)[0] for label in hub.trail.widget().findChildren(QLabel)}
        self.assertTrue({'Device layout', 'Precision layout', 'Connectivity debug',
                         'Post-layout lab', 'Power & reliability'} <= topics)
        hub.select_lesson('l-match')
        hub.start_selected()
        self.assertEqual(hub.guide.lesson['id'], 'l-match')
        self.assertEqual(studio.mode_combo.currentIndex(), 1)
        saved_project = studio.project['id']
        self.spaces.tabs.setCurrentIndex(1)
        hub.select_lesson('l-lvs')
        hub.start_selected()
        self.assertEqual(studio.project['id'], saved_project)
        guide = hub.guide
        guide.steps.setCurrentIndex(next(i for i, s in enumerate(guide.lesson['steps']) if s['id']=='swap'))
        guide.workspace()
        case = next(c for c in studio.project['cells'] if c['id']==studio.cid)
        self.assertEqual(case['name'], 'lvs_swap')
        with patch('icstudio.student_hub_ui.QInputDialog.getItem', side_effect=lambda *args: (args[3][0], True)):
            guide.layout_action.click()
        case = next(c for c in studio.project['cells'] if c['id']==studio.cid)
        self.assertEqual(next(p['point'] for p in case['layout_ports'] if p['name']=='inp'), [12000, 4000])

    def test_macro_workflow_reuses_saved_project_and_reads_stream(self):
        from icstudio.student_layout_signoff import current_placement

        hub, studio = self.hub, self.studio
        hub.world_map.cards['layout'].click()
        topics = {label.text().split('  ·', 1)[0] for label in hub.trail.widget().findChildren(QLabel)}
        self.assertTrue({'Floorplanning', 'Chip integration', 'Process signoff',
                         'Isolation', 'RF & passives', 'Tapeout handoff'} <= topics)

        def open_step(key, step):
            self.spaces.tabs.setCurrentIndex(1)
            hub.select_lesson(key)
            hub.start_selected()
            guide = hub.guide
            guide.steps.setCurrentIndex(next(i for i, unit in enumerate(guide.lesson['steps']) if unit['id'] == step))
            self.assertEqual(guide.lesson['id'], key)
            return guide

        def submit(guide, values):
            guide.layout_action.click()
            dialog = studio._workflow_dialog
            self.assertTrue(dialog.isVisible())
            for field, value in values.items():
                widget = dialog.fields[field]
                if hasattr(widget, 'setCurrentText'):
                    widget.setCurrentText(value)
                else:
                    widget.setText(value)
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
            self.assertFalse(dialog.isVisible(), dialog.error.text())

        guide = open_step('l-floorplan', 'compact')
        identity = studio.project['id']
        submit(guide, {'pitch': '16', 'offset': '0'})
        self.assertEqual(current_placement(studio.project), (16000, 0))
        guide = open_step('l-access', 'route')
        self.assertEqual(studio.project['id'], identity)
        submit(guide, {'layers': 'Metal1 and metal2'})
        self.assertTrue(any(s.get('net') == 'mid' for s in studio.cell['shapes']))
        guide = open_step('l-handoff', 'fault')
        self.assertEqual(studio.project['id'], identity)

        def stream():
            guide.controls['Run lesson'].click()
            deadline = time.monotonic() + 12
            while studio.run_manager.busy and time.monotonic() < deadline:
                QTest.qWait(20)
            row = studio.run_manager.rows[-1]
            self.assertEqual(row['state'], 'Complete', row.get('log', ''))
            self.assertEqual(studio.result['settings'], row['job']['settings'])
            return row['result']['student_stream']['inspection']

        self.assertEqual(stream()['Missing labels'], ['OUT'])
        guide.controls['Results'].click()
        report = guide.layout_results.findChild(QPlainTextEdit)
        self.assertIn('Missing labels  OUT', report.toPlainText())
        guide.layout_results.close()
        guide.steps.setCurrentIndex(2)
        submit(guide, {'port': 'OUT'})
        self.assertEqual(stream()['Missing labels'], [])

    def test_temperature_monitor_navigation_calibration_and_results(self):
        from icstudio.model import load_project
        from icstudio.student_signal_labs import calibration

        hub, studio = self.hub, self.studio
        hub.world_map.cards['capstone'].click()
        topics = {label.text().split('  ·', 1)[0] for label in hub.trail.widget().findChildren(QLabel)}
        self.assertIn('Sensor calibration', topics)
        hub.mode_buttons['list'].click()
        hub.select_lesson('c-temperature')
        hub.start_selected()
        guide = hub.guide
        self.assertEqual(guide.lesson['id'], 'c-temperature')
        self.assertTrue(guide.controls['Open RTL'].isHidden())
        project_id = studio.project['id']

        def select(step):
            index = next(i for i, item in enumerate(guide.lesson['steps']) if item['id'] == step)
            guide.steps.setCurrentIndex(index)

        def edit(values):
            self.assertTrue(guide.signal_action.isEnabled())
            guide.signal_action.click()
            dialog = studio._workflow_dialog
            self.assertTrue(dialog.isVisible())
            for field, value in values.items():
                dialog.fields[field].setText(value)
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
            self.assertFalse(dialog.isVisible(), dialog.error.text())

        def run():
            self.assertTrue(guide.controls['Run lesson'].isEnabled())
            guide.controls['Run lesson'].click()
            deadline = time.monotonic() + 8
            while studio.run_manager.busy and time.monotonic() < deadline:
                QTest.qWait(20)
            row = studio.run_manager.rows[-1]
            self.assertEqual(row['state'], 'Complete', row.get('log', ''))
            self.assertEqual(studio.result['settings'], row['job']['settings'])
            self.assertTrue(guide.controls['Results'].isEnabled())
            return row['result']['student_signal']['measurements']

        select('baseline')
        run()
        select('anchor')
        self.assertFalse(guide.controls['Results'].isEnabled())
        edit({'RFIX': '6.8k'})
        cold, hot = (r['ADC code'] for r in run().values())
        select('validate')
        gain = round(80_000/(hot-cold))
        edit({'gain': str(gain), 'offset': str(-gain*cold)})
        self.assertEqual(calibration(studio.project), (gain, -gain*cold))
        run()
        guide.controls['Results'].click()
        dialog = guide.signal_results
        self.assertEqual(dialog.case.currentText(), 'Calibration at 1.6 V')
        self.assertIn('Error (°C)', dialog.plot.result['traces'])
        self.assertEqual(dialog.plot.result['x'], [5, 20, 35, 55, 75])
        dialog.close()
        self.assertTrue(guide.save_work())
        self.assertEqual(calibration(load_project(studio.path)), (gain, -gain*cold))
        self.spaces.tabs.setCurrentIndex(1)
        hub.select_lesson('c-temperature')
        hub.start_selected()
        self.assertEqual(studio.project['id'], project_id)
        self.assertEqual(calibration(studio.project), (gain, -gain*cold))


if __name__ == '__main__':
    unittest.main()
