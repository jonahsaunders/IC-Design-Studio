"""Desktop acceptance for guided setup, adaptive trade-offs and model lookup."""
import argparse,json,sys,time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QSettings,QStandardPaths,Qt
    from PySide6.QtWidgets import QApplication,QPushButton,QScrollArea
    from PySide6.QtTest import QTest
    from PySide6.QtGui import QAccessible
    from icstudio.gui import Studio
    from icstudio.model import example,clone,design_digest
    from tests.test_analog_optimizer import mos_project,setup
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.maybe_save=lambda:True;w.live_check.setChecked(False);errors=[];w.error=lambda message:errors.append(str(message));w.show();checks=[]
    def exception(typ,exc,tb):errors.append(str(exc));sys.__excepthook__(typ,exc,tb)
    sys.excepthook=exception
    def wait(predicate):
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            QTest.qWait(20)
        raise AssertionError('Timed out: '+str(errors)+str([(r['state'],r.get('log','')[-300:]) for r in w.run_manager.rows]))
    def screenshot(window,name):app.processEvents();QTest.qWait(100);window.grab().save(str(out/name))
    def reachable(window):
        for button in window.findChildren(QPushButton):
            if button.isHidden() or not button.isVisibleTo(window):continue
            assert button.geometry().left()>=0 and button.geometry().right()<button.parentWidget().width()+2,(button.text(),button.geometry(),button.parentWidget().size())
    try:
        w.set_project(example('empty'));ws=w.open_analog_workspace();ws.guided_setup();guide=ws.guide;guide.example();guide.values['gain_min'].setText('100');guide.values['settling_max'].setText('10u')
        before=clone(w.project);guide.preview();assert guide.proposal and guide.create_button.isEnabled(),guide.note.text();assert w.project==before
        screenshot(guide,'guided-setup.png');guide.name.setText('my_amplifier');assert not guide.create_button.isEnabled();guide.preview();guide.create()
        assert len(w.project['simulation_setups'])==3 and len(w.project['testbenches'])==3;assert ws.plan()['name']=='my_amplifier'
        page=ws.optimizer;assert page.source.currentData()['name']=='my_amplifier';assert page.parameter_cell.currentData()==guide.report['dut_cell'];checks.append('Guided fixture preview, invalidation after edits, atomic creation and optimizer/PVT plan selection')
        ws.tabs.setCurrentIndex(1);ws.run();wait(lambda:not w.run_manager.busy)
        from icstudio.analog_run_ui import RunInspector
        ac=next(r for r in w.run_manager.rows if r['job']['settings']['type']=='ac');assert ac['state']=='Complete',ac.get('log')
        inspector=RunInspector(w,ac);inspector.show();failure=next(r for r in inspector.requirement_rows if r['status']=='FAIL');inspector.focus_requirement(failure)
        assert inspector.schematic.selection and inspector.schematic.net=='OUT';assert 'abs(' in inspector.plot.result.get('expression','')
        screenshot(inspector,'failure-navigation.png');assert w.project!=before;inspector.close()
        op=next(r for r in w.run_manager.rows if r['job']['settings']['type']=='op');inspector=RunInspector(w,op)
        mos=next(i for i,r in enumerate(inspector.device_rows) if r['values'].get('gmid'));inspector.select_device(mos)
        assert any('gm/Id' in text for text in inspector.schematic.simulation_annotations.values());inspector.close();checks.append('Failed gain opens captured transfer waveform and connected DUT devices; saved OP contains gm/Id annotations')
        ws.close()
        p=mos_project();entry=setup(p);p['simulation_setups']=[dict(name=entry['name'],cell=p['top'],engine='builtin',settings=clone(p['analysis']))];w.set_project(p);ws=w.open_analog_workspace();page=ws.optimizer;ws.tabs.setCurrentIndex(4)
        page.axes.cellWidget(0,0).setCurrentText('VG.value');page.axes.item(0,1).setText('.55');page.axes.item(0,2).setText('.95');page.axes.item(0,3).setText('9');page.budget.setValue(7)
        page.expression.setText('abs(final(I("VD")))');page.unit.setCurrentText('A');page.goal.setCurrentIndex(page.goal.findData('maximize'));page.add_objective();page.goal.setCurrentIndex(page.goal.findData('minimize'))
        before=clone(w.project);page.start_search();ws.hide();wait(lambda:page.report and page.report['complete']);ws.show();page.render()
        assert len(page.manifest()['jobs'])==7;assert len(page.report['pareto'])==7 and page.report['best'] is None;assert page.sensitivity_table.rowCount()==2
        assert w.project==before;page.results.selectRow(3);assert page.apply_button.isEnabled();page.inspect_sensitivity(0);assert page.inspector.schematic.selection;page.inspector.close()
        page.budget.setValue(1);page.restore_settings();assert page.budget.value()==7 and page.more_objectives.rowCount()==1
        screenshot(ws,'adaptive-tradeoffs.png');checks.append('Adaptive continuation while workspace hidden, hard budget, multiple Pareto choices and schematic-linked sensitivity')
        page.open_library();dialog=page.library_dialog;dialog.sweeps['length'].setText('1u');dialog.sweeps['vgs'].setText('.55, .65, .75, .85');dialog.sweeps['vds'].setText('1.8');dialog.start()
        wait(lambda:dialog.data and dialog.data['complete']);assert all(p['status']=='Passed' for p in dialog.data['points']),dialog.note.text()
        dialog.query['gmid'].setText('10');dialog.estimate();assert dialog.estimates;before=clone(w.project);dialog.seed();assert w.project==before
        assert page.axes.rowCount()==2 and page.seed_values;count=len(w.run_manager.rows);dialog.start();assert len(w.run_manager.rows)==count and 'Reused' in dialog.note.text()
        dialog.estimate();dialog.results.selectRow(1);dialog.inspect();dialog.inspector.close();screenshot(dialog,'sizing-suggestions.png');dialog.tabs.setCurrentIndex(0);screenshot(dialog,'characterization-library.png');checks.append('Isolated measured lookup, sizing interpolation, unchanged circuit, search seed transfer and zero-job cache reuse')
        for dark in (False,True):
            w.dark=dark;w.apply_theme();dialog.plot.dark=dark
            for window in (ws,dialog):window.resize(800,640);app.processEvents();reachable(window)
            screenshot(dialog,'library-'+('dark' if dark else 'light')+'-compact.png')
        for widget in (dialog.results,dialog.suggestions,dialog.plot,page.failure_choice,page.sensitivity_table):
            iface=QAccessible.queryAccessibleInterface(widget);assert iface and iface.text(QAccessible.Name),widget
        checks.append('Light/dark compact layouts, reachable controls and native Qt accessibility names')
        dialog.close();ws.close();assert not errors,errors
        (out/'acceptance.json').write_text(json.dumps(dict(status='passed',checks=checks,platform=app.platformName()),indent=2))
    finally:
        w.run_manager.limit=0
        if w.run_manager.busy:w.run_manager.cancel(w.run_manager.rows);wait(lambda:not w.run_manager.busy)
        w.close();app.processEvents()


if __name__=='__main__':main()
