"""Exercise scoped answers, evidence navigation and the real simulation queue."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog, QInputDialog
from icstudio import ai_fixture_ui, ai_investigation as evidence, analog_guided, simulation, specifications
from icstudio.ai_trial_ui import Trial
from icstudio.model import clone, design_digest, load_project
from tests import gui_ai_assistant as desktop
from tests.test_ai_assistant import rc_spec


class InvestigationDesktop(unittest.TestCase):
    setUpClass = classmethod(desktop.AssistantDesktop.setUpClass.__func__)
    tearDownClass = classmethod(desktop.AssistantDesktop.tearDownClass.__func__)
    setUp = desktop.AssistantDesktop.setUp
    wait = desktop.AssistantDesktop.wait
    ask = desktop.AssistantDesktop.ask

    def saved(self, capacitance, temp):
        s = self.studio
        p = clone(s.project)
        c = next(c for c in p['cells'] if c['id']==s.cid)
        next(d for d in c['devices'] if d['name']=='C1')['value'] = capacitance
        c['specifications'] = [dict(name='Output swing', expression='max(V("vout"))',min=1,unit='V')]
        settings = {**p['analysis'], 'type':'tran','stop':'100u','step':'200n','temperature':temp}
        job = s.prepare_simulation(settings,'builtin',p,s.cid)
        result = simulation.run(p,s.cid,settings)
        specifications.attach(job,result)
        return s.run_manager.enqueue(job,s.jobs_dir,'Transient '+str(temp)+' C',dict(id='fixture',result=result))

    def test_failure_to_waveform_followup_and_one_change(self):
        s, panel = self.studio, self.panel
        baseline = self.saved('100n',85)
        passing = self.saved('1n',27)
        self.assertEqual(evidence.checks(baseline)[0]['actual']['status'],'FAIL')
        self.assertEqual(evidence.checks(passing)[0]['actual']['status'],'PASS')
        active_hash = design_digest(s.project)
        s.ask_about(row=baseline,requirement='Output swing')
        self.assertIn('85',panel.evidence_note.text())
        self.assertIn('min 1 V',panel.evidence_note.text())
        self.assertTrue(panel.wave_button.isEnabled())
        self.assertTrue(panel.pass_button.isEnabled())
        panel.wave_button.click()
        inspector = panel.windows[-1]
        self.assertEqual(inspector.project,baseline['job']['project'])
        self.assertTrue(inspector.plot.names)
        inspector.close()
        with patch.object(QInputDialog,'getItem',return_value=('C1',True)):
            panel.device_button.click()
        self.assertIn('C1',panel.windows[-1].note.text())
        panel.windows[-1].close()
        panel.pass_button.trigger()
        self.assertIsNotNone(panel.windows[-1].layout().itemAt(0).widget().plot.compare)
        panel.windows[-1].close()
        panel.note.setText('Why did the output miss its limit?')
        self.ask('The recorded output swing missed the 1 V limit.')
        panel.note.setText('Does it also fail at room temperature?')
        prompt = panel.preview.toPlainText()
        self.assertIn('Why did the output miss',prompt)
        self.assertIn('other_recorded_conditions',prompt)
        self.assertIn('"temperature": 27',prompt)
        self.ask('The 27 °C run passed. Try the smaller load.\n```experiment\n{"target":"C1.value","value":"1n"}\n```')
        self.assertEqual(panel.suggestion,('C1.value','1n'))
        panel.experiment_button.trigger()
        trial = panel.windows[-1]
        self.assertIsInstance(trial,Trial)
        self.assertEqual(trial.target.currentData(),'C1.value')
        self.assertFalse(trial.rows)
        trial.start.click()
        self.wait(lambda: trial.rows and all(r['state'] not in ('Running','Queued') for r in trial.rows))
        self.assertEqual([r['state'] for r in trial.rows],['Complete','Complete'])
        self.assertIsNotNone(trial.overlay.plot.compare)
        self.assertEqual(evidence.checks(trial.rows[1])[0]['actual']['status'],'PASS')
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td)/'variant.icproj')
            with patch.object(QFileDialog,'getSaveFileName',return_value=(path,'')):
                trial.keep.click()
            variant = load_project(path)
            self.assertNotEqual(variant['id'],s.project['id'])
            self.assertEqual(evidence.parameters({**baseline['job'],'project':variant})['C1.value'],1e-9)
        self.assertEqual(design_digest(s.project),active_hash)
        trial.close()
        panel.remove_attachment('requirement')
        self.assertFalse(panel.turns)
        self.assertIsNone(panel.check)
        panel.remove_attachment('run')
        self.assertFalse(panel.preview.toPlainText())

    def test_schematic_pin_survives_navigation_and_visual_draft(self):
        s, panel = self.studio, self.panel
        from icstudio.model import example
        p, cid = analog_guided.teaching_example(example(),'differential_pair')
        s.set_project(p)
        s.ask_about()
        name = panel.pinned.cell['name']
        first = panel.preview.toPlainText()
        s.cid = cid
        s.refresh()
        panel.note.setText('Which cell did I select?')
        self.assertEqual(panel.pinned.cell['name'],name)
        self.assertIn('"circuit": "'+name+'"',first)
        self.assertIn('"circuit": "'+name+'"',panel.preview.toPlainText())
        panel.action.setCurrentIndex(panel.action.findData('bench'))
        cell = s.cell
        ports = cell['ports']
        candidates = [p for p in ports if 'OUT' in p.upper()][:2]
        self.assertEqual(len(candidates),2)
        connections = {n:dict(kind='observe') for n in ports}
        connections['VDD'] = dict(kind='dc',value='1.8')
        connections['VSS'] = dict(kind='ground')
        spec = dict(name='diff_visual',analysis={'type':'op'},connections=connections,probes=['@output'],
                    measurements=[dict(name='output',node='@output',max='1.8')],output_candidates=candidates)
        self.ask(json.dumps(spec))
        self.assertFalse(panel.add_button.isEnabled())
        self.assertEqual(panel.fixture_view.candidates,set(candidates))
        editor = ai_fixture_ui.FixtureEditor(panel,spec)
        editor.output.setCurrentText(candidates[1])
        editor.connections['VDD'][1]['value'].setText('1.5')
        editor.measure.item(0,3).setText('1.5')
        edited = editor.preview()
        self.assertEqual(edited['probes'],[candidates[1]])
        self.assertEqual(edited['measurements'][0]['max'],'1.5')
        editor.close()
        panel.fixture_view.resize(400,300)
        panel.fixture_view.fit()
        pt = next(pt for name,pt in panel.fixture_view.marks() if name==candidates[0])
        QTest.mouseClick(panel.fixture_view, Qt.LeftButton, pos=pt.toPoint())
        self.assertTrue(panel.add_button.isEnabled())
        self.assertEqual(panel.proposal[1]['probes'],[candidates[0]])

    def test_run_draft_without_saving(self):
        from icstudio.spice_program import find_ngspice
        if not find_ngspice():
            self.skipTest('ngspice required for a native saved bench')
        s, panel = self.studio, self.panel
        panel.action.setCurrentIndex(panel.action.findData('bench'))
        self.ask(json.dumps(rc_spec()))
        editor = ai_fixture_ui.FixtureEditor(panel,rc_spec())
        editor.overrides['C1.value'][0].setText('2n')
        self.assertEqual(editor.preview()['overrides']['C1.value'],'2n')
        editor.close()
        before = design_digest(s.project)
        panel.draft_button.click()
        trial = panel.windows[-1]
        trial.start.click()
        self.wait(lambda: trial.rows and trial.rows[0]['state'] not in ('Running','Queued'))
        self.assertEqual(trial.rows[0]['state'],'Complete',trial.status.text())
        self.assertTrue(trial.overlay.trace.count())
        self.assertEqual(design_digest(s.project),before)
        self.assertFalse(s.project.get('testbenches'))

    def test_stale_followup_and_incompatible_measurement(self):
        s, panel = self.studio, self.panel
        failed = self.saved('100n',85)
        other = self.saved('1n',27)
        other['job']['project']['cells'][0]['specifications'][0]['min'] = 0.5
        s.ask_about(row=failed,requirement='Output swing')
        self.assertFalse(panel.pass_button.isEnabled())
        self.assertNotIn(other['name'],panel.preview.toPlainText())
        invalid = 'Try a load.\n```experiment\n{"target":"C1.value","value":true}\n```'
        self.assertEqual(evidence.split_suggestion(invalid,{'C1.value':1e-9}),('Try a load.',None))
        panel.action.setCurrentIndex(panel.action.findData('bench'))
        self.ask(json.dumps(rc_spec()))
        s.commit(lambda p:p.update(name='Changed since draft'),'Rename')
        panel.note.setText('Try the same test again')
        self.ask(json.dumps(rc_spec()))
        self.assertFalse(panel.add_button.isEnabled())
        self.assertIn('circuit changed',panel.status.text())
        s.ask_about()
        panel.remove_attachment('circuit')
        self.assertFalse(panel.send_button.isEnabled())
