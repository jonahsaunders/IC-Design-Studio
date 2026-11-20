"""Exercise the selected-schematic command through the provider, review and Undo."""
import json
from pathlib import Path
import tempfile
import unittest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from icstudio import ai_schematic_edits as edits, simulation
from icstudio.model import clone, design_digest, example
from tests import gui_ai_assistant as desktop


def reply(*changes,summary='Proposed schematic updates.'):
    return json.dumps(dict(summary=summary,changes=list(changes)))


def resize_resistor(value='22k',name='R1'):
    return dict(op='set',part=name,field='value',value=value)


def add_load():
    return dict(op='add',kind='C',value='10p',p='vout',n='0')


class SchematicEditDesktop(unittest.TestCase):
    setUpClass = classmethod(desktop.AssistantDesktop.setUpClass.__func__)
    tearDownClass = classmethod(desktop.AssistantDesktop.tearDownClass.__func__)
    setUp = desktop.AssistantDesktop.setUp
    wait = desktop.AssistantDesktop.wait
    ask = desktop.AssistantDesktop.ask

    def start(self,names=('R1',)):
        s = self.studio
        ids = [d['id'] for d in s.cell['devices'] if d['name'] in names]
        s.select(ids,'schematic')
        s.ask_about(edit=True)
        self.panel.note.setText('Set R1 to 22k and add a 10p output load.')

    def test_menu_preview_apply_and_single_undo(self):
        s,panel = self.studio,self.panel
        part = next(d for d in s.cell['devices'] if d['name']=='R1')
        s.select([part['id']],'schematic')
        QTimer.singleShot(0,lambda:s._canvas_context_menu.close())
        s.canvas_context(s.schematic,QPoint(10,10))
        action = next(a for a in s._canvas_context_menu.actions() if a.text()=='Request a Change…')
        self.assertTrue(action.isEnabled())
        action.trigger()
        self.assertEqual(panel.action.currentData(),'edit')
        panel.note.setText('Set R1 to 22k and add a 10p output load.')
        context = edits.selection(panel.pinned)
        self.assertEqual(set(context['parts']),{'R1'})
        before = clone(s.cell)
        undo = len(s.history.undo_stack)
        self.ask(reply(resize_resistor(),add_load()))
        review = panel.change_window
        self.assertIsNotNone(review,panel.status.text())
        self.assertEqual(s.cell,before)
        self.assertEqual(len(s.history.undo_stack),undo)
        self.assertEqual(review.changes.rowCount(),2)
        self.assertEqual(review.changes.item(0,2).text(),'10k')
        self.assertEqual(review.changes.item(0,3).text(),'22k')
        self.assertIn('vout',review.changes.item(1,3).text())
        after = clone(panel.change.after)
        review.states.setFocus()
        QTest.keyClick(review.states, Qt.Key_Left)
        self.assertEqual(review.canvas.cell,before)
        QTest.keyClick(review.states, Qt.Key_Right)
        self.assertEqual(review.canvas.cell,after)
        review.tabs.setCurrentIndex(1)
        self.assertIn('22k',review.diff.toPlainText())
        review.close()
        self.assertEqual(s.cell,before)
        panel.review_change.click()
        panel.change_window.apply.click()
        self.assertEqual(s.cell,after)
        self.assertEqual(len(s.history.undo_stack),undo+1)
        component = next(d for d in after['devices'] if d['name']=='C2')
        self.assertEqual(component['nets'],{'p':'vout','n':'0'})
        self.assertIn('vout',simulation.run(s.project,s.cid,s.project['analysis'])['traces'])
        s.undo()
        self.assertEqual(s.cell,before)
        s.redo()
        self.assertEqual(s.cell,after)

    def test_scope_discard_and_stale_design(self):
        s,panel = self.studio,self.panel
        self.start()
        original = design_digest(s.project)
        for invalid in (resize_resistor('1n','C1'),{**add_load(),'n':'outside'},resize_resistor(False),
                        {'op':'remove','part':'C1'},resize_resistor('0')):
            with self.subTest(invalid=invalid):
                self.ask(reply(resize_resistor(),invalid))
                self.assertIsNone(panel.change_window)
                self.assertIsNone(panel.change)
                self.assertEqual(design_digest(s.project),original)
        self.ask(reply(resize_resistor()))
        panel.change_window.discard.click()
        self.assertIsNone(panel.change)
        self.assertEqual(design_digest(s.project),original)
        panel.note.setText('Only change the resistor.')
        self.ask(reply(resize_resistor()))
        win = panel.change_window
        s.select([],'schematic')
        self.assertFalse(win.check_current())
        s.select(panel.pinned.selection,'schematic')
        self.assertTrue(win.check_current())
        s.commit(lambda p:p.update(name='New revision'),'Rename')
        self.assertFalse(win.check_current())
        win.commit()
        self.assertEqual(next(d['value'] for d in s.cell['devices'] if d['name']=='R1'),'10k')
        with self.assertRaisesRegex(ValueError,'design changed'):
            panel.change.apply(clone(s.project))

    def test_no_selection_and_wire_only_request(self):
        s,panel = self.studio,self.panel
        s.select([],'schematic')
        panel.action.setCurrentIndex(panel.action.findData('edit'))
        panel.note.setText('Change this.')
        self.assertFalse(panel.send_button.isEnabled())
        wire = next(w for w in s.cell['wires'] if w['net']=='vout')
        s.select([wire['id']],'schematic')
        s.ask_about(edit=True)
        panel.note.setText('Add a 10pF load here.')
        self.assertEqual(edits.selection(panel.pinned)['parts'],{})
        self.ask(reply(summary='What capacitance do you want?'))
        self.assertIsNone(panel.change)
        panel.note.setText('Use 10pF.')
        self.ask(reply(add_load()))
        self.assertEqual(len(panel.change.edits),1)
        self.assertEqual(panel.change.after['devices'][-1]['nets']['p'],'vout')
        s.set_project(example('inverter'))
        self.assertIsNone(panel.change_window)
        self.assertIsNone(panel.change)

    def test_multiple_selected_parts_and_native_source(self):
        s,panel = self.studio,self.panel
        self.start(('R1','C1'))
        self.ask(reply(resize_resistor(),resize_resistor('2n','C1')))
        self.assertEqual([e.before for e in panel.change.edits],['10k','1n'])
        panel.change_window.apply.click()
        self.assertEqual([d['value'] for d in s.cell['devices'] if d['name'] in ('R1','C1')],['22k','2n'])
        from icstudio.native_migration import review_path
        from tests.test_native_migration import divider
        with tempfile.TemporaryDirectory() as folder:
            migrated = review_path(divider(Path(folder)/'source'))
            s.set_project(migrated['candidate'])
            self.start(('V1',))
            panel.note.setText('Set the supply DC level to 2 V.')
            self.ask(reply(dict(op='set',part='V1',field='native.dc_level',value='2')))
            self.assertIn('ac 1',panel.change.edits[0].after.lower())
            source = next(d for d in panel.change.after['devices'] if d['name']=='V1')
            self.assertEqual(source['native_spice']['parameters']['value'],source['symbol_context']['value'])

    def test_unnamed_net_shows_required_label_in_review(self):
        from icstudio import wiring
        s,panel = self.studio,self.panel
        project = clone(s.project)
        cell = project['cells'][0]
        for d in cell['devices']:
            d['net_labels'] = {k:n for k,n in d['net_labels'].items() if n!='vout'}
        wiring.rebuild(cell,project)
        s.set_project(project)
        self.start(('C1',))
        net = next(d['nets']['p'] for d in s.cell['devices'] if d['name']=='C1')
        self.assertTrue(net.startswith('N_'))
        panel.note.setText('Place 10pF in parallel with C1.')
        self.ask(reply({**add_load(),'p':net}))
        self.assertEqual([e.name for e in panel.change.edits],['C2','C1'])
        self.assertEqual(panel.change.edits[1].field,'Label pin p')
        self.assertIn(net,panel.change.details())
