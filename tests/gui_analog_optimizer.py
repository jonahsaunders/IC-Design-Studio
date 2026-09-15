"""Real Qt acceptance and repeatable evidence for the analog optimizer/HIG audit."""
import argparse
import json
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--out', type=Path, required=True); args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True); sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QSettings, QStandardPaths, Qt
    from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea, QFileDialog
    from PySide6.QtGui import QAccessible
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import example, clone, design_digest, uid
    from icstudio.analog_optimizer import get_target, source_plan
    from tests.test_analog_optimizer import mos_project, setup
    QSettings.setDefaultFormat(QSettings.IniFormat); QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(out / 'settings'))
    QStandardPaths.writableLocation = staticmethod(lambda kind: str(out / 'profile' / str(kind.value)))
    app = QApplication([]); app.setStyle('Fusion'); w = Studio(recover=False); w.maybe_save = lambda: True; w.live_check.setChecked(False)
    errors = []; w.error = lambda text: errors.append(str(text))
    def report_exception(typ, exc, tb):
        errors.append(str(exc)); sys.__excepthook__(typ, exc, tb)
    sys.excepthook = report_exception; w.show()
    checks = []

    def wait(predicate):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate(): return
            QTest.qWait(20)
        raise AssertionError('Timed out: ' + str(errors))

    def screenshot(window, name):
        app.processEvents(); QTest.qWait(100); window.grab().save(str(out / name))

    def all_buttons_reachable(window):
        # Scrollable page controls may be outside the viewport, but must fit their
        # content widget and be reachable by scroll/focus, never clipped in a row.
        for button in window.findChildren(QPushButton):
            if button.isHidden() or not button.isVisibleTo(window): continue
            parent = button.parentWidget()
            assert button.geometry().left() >= 0, button.text()
            assert button.geometry().right() < parent.width() + 2, (button.text(), button.geometry(), parent.size())

    try:
        p = example('rc'); cid = p['top']; p['cells'][0]['specifications'] = [dict(name='Output', expression='final(V("vout"))', min=0, max=2, unit='V')]
        entry = dict(id='setup:0', name='Settling', cell=cid, engine='builtin', settings=clone(p['analysis']))
        p['simulation_setups'] = [dict(name=entry['name'], cell=cid, engine='builtin', settings=clone(p['analysis']))]
        plan = source_plan(entry); plan.update(id=uid(), name='RC temperature checks', temperatures=[0, 80]); p['test_plans'] = [plan]
        w.set_project(p); window = w.open_analog_workspace(); window.tabs.setCurrentIndex(4); page = window.optimizer
        assert page.start_button.isEnabled() and not page.apply_button.isEnabled()
        page.axes.cellWidget(0, 0).setCurrentText('R1.value'); page.axes.item(0, 3).setText('3'); page.goal.setCurrentIndex(page.goal.findData('maximize'))
        baseline = clone(w.project); w.run_manager.limit = 0
        page.start_search(); assert len(w.run_manager.rows) == 6 and all(r['state'] == 'Queued' for r in w.run_manager.rows)
        assert w.project == baseline; page.cancel(); assert all(r['state'] == 'Cancelled' for r in w.run_manager.rows)
        w.run_manager.limit = 2; page.resume(); wait(lambda: not w.run_manager.busy)
        page.render(); assert page.report['terminal'] == 6 and page.report['best'], [(r['state'], r['log']) for r in w.run_manager.rows]
        page.results.selectRow(page.report['best']['candidate'] - 1); assert page.apply_button.isEnabled()
        assert page.run_choice.count() == 2; page.inspect(); assert page.inspector.project == page.report['current'][1]['job']['project']; page.inspector.close()
        checks.append('Immutable PVT candidate search, cancel/resume, worst-condition ranking and saved-run inspection')
        w.dark = False; w.apply_theme(); window.resize(1180, 980); screenshot(window, 'optimizer-light.png')
        page.apply(); assert design_digest(w.project) != design_digest(baseline); assert 'Candidate applied' in page.summary.text()
        w.undo(); assert get_target(w.project,cid,'R1.value')==get_target(baseline,cid,'R1.value'); window.reload_setup(); page.render(); page.results.selectRow(0)
        w.commit(lambda q: q['cells'][0]['devices'][1].update(value='20k'), 'Concurrent edit'); window.reload_setup(); page.render()
        assert not page.apply_button.isEnabled(); before = clone(w.project); page.call(page.apply); assert w.project == before and 'circuit changed' in page.summary.text()
        checks.append('Review/apply/undo and stale-circuit rejection')
        window.close()

        p = mos_project(); entry = setup(p); p['simulation_setups'] = [dict(name=entry['name'], cell=p['top'], engine='builtin', settings=clone(p['analysis']))]
        w.set_project(p); window = w.open_analog_workspace(); window.tabs.setCurrentIndex(4); page = window.optimizer; page.modes.setCurrentIndex(1)
        page.bias.setCurrentText('VG.value'); page.bias_lower.setText('.6'); page.bias_upper.setText('1'); page.samples.setValue(5)
        before = clone(w.project); page.start_gmid(); wait(lambda: not w.run_manager.busy); page.render()
        assert all(c['state'] == 'Passed' for c in page.report['candidates']), page.summary.text()
        assert abs(page.report['candidates'][2]['points'][0]['gmid'] - 2 / .35) < 1e-5
        page.results.selectRow(2); assert page.estimate_button.isEnabled() and not page.apply_button.isEnabled(); page.estimate()
        assert 'Estimated total W' in page.details.toPlainText(); assert w.project == before
        page.load_history(); assert page.manifest()['spec']['kind'] == 'analog_gmid'; page.results.selectRow(2)
        original = QFileDialog.getSaveFileName; QFileDialog.getSaveFileName = lambda *a, **kw: (str(out / 'gmid.csv'), '')
        try: page.export()
        finally: QFileDialog.getSaveFileName = original
        assert 'gm/Id (1/V)' in (out / 'gmid.csv').read_text()
        checks.append('Captured MOS gm/Id, bias plot, width estimate, CSV export and durable experiment reload')

        # Native Qt accessibility metadata and keyboard activation, without claiming VoiceOver.
        for widget in (page.source, page.axes, page.results, page.progress, page.device, page.bias, page.details):
            interface = QAccessible.queryAccessibleInterface(widget)
            assert interface and interface.text(QAccessible.Name), widget
        page.results.setFocus(); QTest.keyClick(page.results, Qt.Key_Down); assert page.results.currentRow() == 3
        page.inspect_button.setFocus(); QTest.keyClick(page.inspect_button, Qt.Key_Space); app.processEvents()
        assert page.inspector.isVisible(); page.inspector.close()
        window.tabs.setCurrentIndex(0); window.variables.setPlainText('bias = 1')
        window.close(); window = w.open_analog_workspace(); assert window.variables.toPlainText() == 'bias = 1'
        page.call(page.start_gmid); assert 'unsaved edits' in page.summary.text(); window.reload_setup()
        checks.append('Qt accessibility names, keyboard row navigation/action activation and preserved unsaved drafts')

        for dark in (False, True):
            w.dark = dark; w.apply_theme(); page.plot.dark = dark
            window.resize(1180, 980); window.tabs.setCurrentIndex(4); page.modes.setCurrentIndex(1)
            screenshot(window, 'gmid-' + ('dark' if dark else 'light') + '.png')
            for index in range(window.tabs.count()):
                window.tabs.setCurrentIndex(index); window.resize(800, 640); app.processEvents(); QTest.qWait(50)
                assert window.width() == 800 and window.height() == 640, window.size()
                all_buttons_reachable(window)
            screenshot(window, 'optimizer-compact-' + ('dark' if dark else 'light') + '.png')
        window.resize(1180, 980); window.tabs.setCurrentIndex(0); screenshot(window, 'setup-audited.png')
        # Increased text size stays reachable through scrolling instead of forcing a wider window.
        window.setStyleSheet('QWidget { font-size: 18px; }'); window.resize(800, 640)
        for index in range(window.tabs.count()):
            window.tabs.setCurrentIndex(index); app.processEvents(); all_buttons_reachable(window)
            assert window.width() == 800, window.size()
        screenshot(window, 'optimizer-large-text.png'); window.setStyleSheet('')
        checks.append('All five tabs at 800×640 and 1180×980, light/dark appearances, enlarged text and wrapping actions')
        assert not errors, errors
        (out / 'acceptance.json').write_text(json.dumps(dict(status='passed', checks=checks, limits=['Qt offscreen on Linux; macOS VoiceOver, native menu conventions and hardware display checks remain unverified.']), indent=2))
        window.close()
    finally:
        if w.run_manager.busy:
            w.run_manager.cancel(w.run_manager.rows); wait(lambda: not w.run_manager.busy)
        w.close(); app.processEvents()


if __name__ == '__main__': main()
