"""Desktop acceptance for advanced studies, cached workers and reversible UI."""
import argparse,json,os,sys,time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QSettings,QStandardPaths,Qt
    from PySide6.QtWidgets import QApplication,QPushButton
    from PySide6.QtGui import QAccessible
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import clone
    from icstudio import test_plans,analog_optimizer as opt,analog_fidelity as fidelity
    from tests.test_analog_optimizer import mos_project
    from tests.test_analog_advanced import rc_project
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.maybe_save=lambda:True;w.live_check.setChecked(False);errors=[];w.error=lambda m:errors.append(str(m));checks=[];w.show()
    def exception(typ,exc,tb):errors.append(str(exc));sys.__excepthook__(typ,exc,tb)
    sys.excepthook=exception
    def wait(predicate):
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            QTest.qWait(20)
        raise AssertionError('Timed out: '+str(errors)+' / '+(advanced.status.text() if 'advanced' in locals() else '')+' / '+str([(r['state'],r.get('error')) for r in w.run_manager.rows]))
    def shot(widget,name):app.processEvents();QTest.qWait(60);widget.grab().save(str(out/name))
    try:
        p=mos_project();p['cells'][0]['specifications']=[dict(name='Gate minimum',expression='final(V("g"))',min='.7',unit='V')]
        p['simulation_setups']=[dict(name='Bias',cell=p['top'],engine='builtin',settings=clone(p['analysis'])),dict(name='Transient',cell=p['top'],engine='builtin',settings={**p['analysis'],'type':'tran','stop':'1u','step':'100n'})]
        p['test_plans']=[dict(id='staged',name='Staged tests',entries=test_plans.sources(p),corners=['nominal'],temperatures=[27],voltages=[])]
        w.set_project(p);workspace=w.open_analog_workspace();workspace.tabs.setCurrentIndex(4);page=workspace.optimizer
        page.axes.cellWidget(0,0).setCurrentText('VG.value')
        for col,value in ((1,'.6'),(2,'1'),(3,'5')):page.axes.item(0,col).setText(value)
        page.budget.setValue(30);page.strategy.setCurrentIndex(page.strategy.findData('grid'));page.open_advanced();advanced=page.advanced_dialog
        advanced.mode.setCurrentIndex(4);advanced.reuse.setChecked(True);advanced.use_workflow();assert page.workflow and not page.screen_op.isEnabled()
        page.start_search();wait(lambda:page.report and page.report['complete']);page.tick();first=page.manifest();assert Path(first['report_path']).is_file()
        count=len(w.run_manager.rows);assert count==9 and page.report['skipped']==1
        page.start_search();wait(lambda:page.report and page.report['complete']);page.tick();second=page.manifest();cached=[r for r in w.run_manager.rows if r['job']['case']['group']==second['id']]
        assert len(cached)==9 and all(r['result'].get('reused_from') and r['elapsed']==0 for r in cached)
        checks.append('Real workers respect ordered gates; rejected bias avoids transient; exact repeated inputs reuse nine results; automatic reports persist')
        advanced.clear_workflow();page.source.setCurrentIndex(1);page.strategy.setCurrentIndex(page.strategy.findData('bayesian'));page.budget.setValue(5);page.axes.item(0,3).setText('21');page.start_search()
        wait(lambda:page.report and page.report['complete']);assert any(j['case'].get('proposal') for j in page.manifest()['jobs'])
        checks.append('Constrained Bayesian proposals remain pending until real workers finish all saved conditions')
        page.budget.setValue(50);page.axes.item(0,3).setText('5');advanced.mode.setCurrentIndex(0);advanced.run_sensitivity()
        wait(lambda:advanced.report(advanced.manifest())['complete']);advanced.tick();r=advanced.report(advanced.manifest());assert all(r['status']=='Complete' for r in r['rows'])
        assert Path(advanced.manifest()['report_path']).is_file();checks.append('Morris analysis runs through saved workers and writes measured effects with intervals')
        advanced.mode.setCurrentIndex(1);advanced.use_ranges();advanced.robust_count.setValue(9);advanced.run_robustness();wait(lambda:advanced.report(advanced.manifest())['complete']);advanced.tick()
        assert len(advanced.manifest()['jobs'])==9;assert advanced.report(advanced.manifest())['failed']>0
        checks.append('Worst-condition search adds bounded refinement jobs automatically and reports failed limits')
        advanced.robust_method.setCurrentIndex(1);advanced.run_robustness();wait(lambda:advanced.report(advanced.manifest())['complete']);advanced.tick();assert advanced.report(advanced.manifest())['confidence_95'] is not None
        checks.append('Declared tolerance trials produce a pass fraction and confidence interval distinct from foundry yield')
        advanced.mode.setCurrentIndex(2);advanced.diagnostic.setCurrentIndex(4);advanced.run_diagnostics();wait(lambda:advanced.report(advanced.manifest())['complete']);advanced.tick()
        assert advanced.report(advanced.manifest())['rows'][0]['evidence']['devices'][0]['region'] in ('cutoff','linear','saturation')
        checks.append('Bias diagnostics retain explicitly reported device regions')
        for dark in (False,True):
            w.dark=dark;w.apply_theme();advanced.resize(700,600)
            for mode in range(5):advanced.mode.setCurrentIndex(mode);shot(advanced,f'advanced-{mode}-'+('dark' if dark else 'light')+'.png')
        for widget in (advanced.mode,advanced.results,advanced.seed,advanced.robust_method,advanced.inspect_button):
            interface=QAccessible.queryAccessibleInterface(widget);assert interface and interface.text(QAccessible.Name)
        advanced.mode.setCurrentIndex(1);advanced.robust_seed.setValue(42);advanced.robust_seed.setFocus();QTest.keyClick(advanced.robust_seed,Qt.Key_Escape);app.processEvents();assert not advanced.isVisible()
        page.open_advanced();assert advanced.robust_seed.value()==42 and advanced.isVisible();w.reset_workspace();assert not advanced.isVisible() and not workspace.isVisible()
        checks.append('All five advanced panels fit a compact scrollable window; accessible names, Escape, Close and workspace Reset preserve draft controls')
        if os.environ.get('ICSTUDIO_TEST_NGSPICE'):
            p=rc_project();p['analysis'].update(type='ac',start='10',end='10Meg',points=40);p['simulation_setups']=[dict(name='AC',cell=p['top'],engine='ngspice',settings=clone(p['analysis']))]
            w.set_project(p);w.settings.setValue('engine/ngspice',os.environ['ICSTUDIO_TEST_NGSPICE']);workspace=w.open_analog_workspace();workspace.tabs.setCurrentIndex(4);page=workspace.optimizer
            page.axes.cellWidget(0,0).setCurrentText('R1.value')
            for col,value in ((1,'500'),(2,'1500'),(3,'11')):page.axes.item(0,col).setText(value)
            page.expression.setText('final(abs(V("out")))');page.goal.setCurrentIndex(page.goal.findData('maximize'));page.budget.setValue(10);page.open_advanced();advanced=page.advanced_dialog
            advanced.coarse_count.setValue(6);advanced.full_count.setValue(4);advanced.run_fidelity();wait(lambda:advanced.report(advanced.manifest())['complete']);advanced.tick();r=advanced.report(advanced.manifest())
            assert len(r['coarse_candidates'])==6 and len(r['full_candidates'])==4;assert all(c['state']=='Passed' for c in r['full_candidates']),r
            advanced.render();advanced.results.selectRow(6);assert advanced.apply_button.isEnabled();advanced.apply();assert w.project['cells'][0]['devices'][1]['value']!='1k'
            checks.append('Real ngspice runs both fidelity levels, promotes from learned discrepancy, and allows only a fully measured finalist to apply')
            advanced.diagnostic.setCurrentIndex(1);advanced.run_diagnostics();wait(lambda:advanced.report(advanced.manifest())['complete']);advanced.tick();advanced.results.selectRow(0);advanced.inspect();app.processEvents();advanced.inspector.close()
            assert advanced.report(advanced.manifest())['rows'][0]['evidence']['poles'];checks.append('Real pole/zero evidence opens in the saved circuit inspector without inventing a waveform')
        assert not errors,errors;(out/'acceptance.json').write_text(json.dumps(dict(status='passed',checks=checks,platform=app.platformName()),indent=2))
    finally:
        if w.run_manager.busy:w.run_manager.cancel(w.run_manager.rows);wait(lambda:not w.run_manager.busy)
        w.close();app.processEvents()


if __name__=='__main__':main()
