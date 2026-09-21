"""Desktop acceptance: navigation recovery and staged optimizer execution."""
import argparse,json,sys,time,os
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QSettings,QStandardPaths,Qt
    from PySide6.QtWidgets import QApplication,QPushButton
    from PySide6.QtTest import QTest
    from PySide6.QtGui import QAccessible
    from icstudio.gui import Studio
    from icstudio.model import clone
    from icstudio import test_plans,analog_optimizer as opt
    from tests.test_analog_optimizer import mos_project
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.maybe_save=lambda:True;w.live_check.setChecked(False);errors=[];w.error=lambda m:errors.append(str(m));w.show();checks=[]
    def wait(predicate):
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            QTest.qWait(20)
        raise AssertionError('Timed out: '+str(errors))
    def shot(widget,name):app.processEvents();QTest.qWait(80);widget.grab().save(str(out/name))
    try:
        QTest.qWait(250);app.processEvents();assert w.workflow_dock.isHidden()
        menus={name:[a.text() for a in menu.actions()] for name,menu in w.task_menus.items()}
        assert menus['Simulate'].count('Analog design workspace…')==1
        assert all('Analog design workspace…' not in menus[k] for k in ('Layout','Verify','Schematic'))
        assert any(group=='Analysis' and action.text()=='Analog design workspace…' for group,action in w._commands)
        assert w.menuBar().actions()[-1].menu() is w.task_menus['Help']
        assert any(group=='Digital' and action.text()=='Digital flow…' for group,action in w._commands)
        groups=dict(w.result_groups);assert groups['Layout']==[w.physical_assistant_tab] and groups['Job log']==[2]
        covered=[i for _,indices in w.result_groups for i in indices]
        assert len(covered)==len(set(covered))==w.results_tabs.count()
        for name,indices in w.result_groups:
            for index in indices:
                w.open_engineering_tab(index);app.processEvents()
                assert w.result_categories.tabText(w.result_categories.currentIndex())==name
                assert w.result_sections.tabText(w.result_sections.currentIndex())==w.results_tabs.tabText(index)
        checks.append('Every results page has one task category; analog design has one Analysis menu entry and matching command-palette location')
        for size in ((1000,680),(1440,900)):
            w.reset_workspace();w.resize(*size);app.processEvents();QTest.qWait(250);before=w.canvases.size()
            guide=w.design_workflow();app.processEvents();assert not w.workflow_dock.isHidden();assert w.canvases.height()>100
            assert w.workflow_dock.height()<w.height()*.55,(size,w.workflow_dock.height())
            close=next(b for b in w.workflow_dock.titleBarWidget().findChildren(QPushButton) if b.text()=='Close')
            QTest.mouseClick(close,Qt.LeftButton);app.processEvents();QTest.qWait(250);assert w.workflow_dock.isHidden();assert w.canvases.height()>=before.height()-2,(size,before,w.canvases.size())
            w.design_workflow();guide.next_action.setFocus();QTest.keyClick(guide.next_action,Qt.Key_Escape);app.processEvents();assert w.workflow_dock.isHidden()
            QTest.mouseClick(w.workflow_button,Qt.LeftButton);app.processEvents();assert not w.workflow_dock.isHidden()
            QTest.mouseClick(w.workflow_button,Qt.LeftButton);app.processEvents();assert w.workflow_dock.isHidden()
        w.design_workflow();w.save_editor_workspace('Audit workflow');w.reset_workspace();assert w.workflow_dock.isHidden()
        w.load_editor_workspace('Audit workflow');app.processEvents();assert not w.workflow_dock.isHidden()
        checks.append('Compact and normal workflows close by title button, Escape and toolbar toggle; canvas space returns; named arrangements still restore')
        inventory=dict(menus=menus,result_groups=[dict(category=name,pages=[w.results_tabs.tabText(i) for i in indices]) for name,indices in w.result_groups],navigator=[w.navtabs.tabText(i) for i in range(w.navtabs.count())],inspector=[w.inspector_tabs.tabText(i) for i in range(w.inspector_tabs.count())])
        (out/'navigation-inventory.json').write_text(json.dumps(inventory,indent=2))
        for dark in (False,True):
            w.dark=dark;w.apply_theme();w.resize(1200,800);w.design_workflow();shot(w,'workflow-'+('dark' if dark else 'light')+'.png')
        w.reset_workspace();shot(w,'editor-restored.png')
        p=mos_project();p['cells'][0]['specifications']=[dict(name='Gate minimum',expression='final(V("g"))',min='.7',unit='V')]
        p['simulation_setups']=[dict(name='Bias',cell=p['top'],engine='builtin',settings=clone(p['analysis'])),dict(name='Transient',cell=p['top'],engine='builtin',settings={**p['analysis'],'type':'tran'})]
        p['test_plans']=[dict(id='screen-plan',name='Screened plan',entries=test_plans.sources(p),corners=['nominal'],temperatures=[27],voltages=[])]
        w.set_project(p);ws=w.open_analog_workspace();ws.tabs.setCurrentIndex(4);page=ws.optimizer
        page.axes.cellWidget(0,0).setCurrentText('VG.value')
        for col,value in ((1,'.6'),(2,'1'),(3,'3')):page.axes.item(0,col).setText(value)
        page.budget.setValue(6);page.screen_op.setChecked(True);page.start_search()
        wait(lambda:page.report and page.report['complete']);assert len(w.run_manager.rows)==5
        assert page.report['skipped']==1
        rejected=next(i for i,c in enumerate(page.report['candidates']) if c['state']=='Screened out');passed=next(i for i,c in enumerate(page.report['candidates']) if c['state']=='Passed')
        page.results.selectRow(rejected);assert not page.apply_button.isEnabled();page.results.selectRow(passed);assert page.apply_button.isEnabled()
        page.restore_settings();assert page.screen_op.isChecked()
        shot(ws,'screened-search.png');checks.append('Real workers run three OP checks and only two transient checks; screened candidate cannot apply and saved screening settings restore')
        page.parameter_cell.setCurrentIndex(page.parameter_cell.findData(p['top']));page.axes.setRowCount(0)
        for _ in range(8):page.add_axis()
        assert page.axes.rowCount()==8;page.add_axis();assert page.axes.rowCount()==8
        spacing=page.axes.cellWidget(0,5);spacing.setCurrentIndex(spacing.findData('log'));assert page.axes_spec()[0]['scale']=='log'
        page.open_library();dialog=page.library_dialog;dialog.sweeps['length'].setText('.5u, 1u');dialog.sweeps['vgs'].setText('.55,.65,.75,.85');dialog.sweeps['vds'].setText('1.8');dialog.start()
        wait(lambda:dialog.data and dialog.data['complete']);assert all('intrinsic_gain' in v['values'] for v in dialog.data['points'])
        dialog.plot_metric.setCurrentIndex(2);dialog.compare_lengths.setChecked(True);assert dialog.plot.overlays
        dialog.plot_metric.setCurrentIndex(4);assert dialog.plot.result is None
        dialog.plot_metric.setCurrentIndex(2);dialog.query['gmid'].setText('10');dialog.estimate();assert dialog.verify_button.isEnabled()
        if os.environ.get('ICSTUDIO_TEST_NGSPICE'):
            from icstudio.analog_characterization import verification_result
            w.settings.setValue('engine/ngspice',os.environ['ICSTUDIO_TEST_NGSPICE']);dialog.verify_sizing()
            wait(lambda:opt.evaluate(dialog.verification,w.run_manager.rows)['complete'])
            dialog.refresh();verified=verification_result(dialog.verification,w.run_manager.rows)
            assert verified['state']=='Verified',verified
            checks.append('Real ngspice verifies proposed isolated sizing within the current and gm/Id tolerance')
        for dark in (False,True):
            w.dark=dark;w.apply_theme();dialog.plot.dark=dark;dialog.resize(800,640);dialog.tabs.setCurrentIndex(0);shot(dialog,'device-data-'+('dark' if dark else 'light')+'.png')
        dialog.setup_toggle.setChecked(False);dialog.resize(1050,920);dialog.tabs.widget(0).verticalScrollBar().setValue(0);shot(dialog,'measured-device-data.png')
        for widget in (dialog.plot_metric,dialog.results,dialog.verify_button,page.screen_op,page.batch_size):
            interface=QAccessible.queryAccessibleInterface(widget);assert interface and interface.text(QAccessible.Name)
        checks.append('Eight editable axes, logarithmic selector, measured intrinsic gain, length overlays, honest unavailable capacitance and accessible sizing-verification control')
        dialog.show();ws.variables.setPlainText('unsaved_bias = 0.9');w.reset_workspace();app.processEvents();assert not ws.isVisible() and not dialog.isVisible() and w.workflow_dock.isHidden()
        assert w.mode_combo.currentIndex()==0;w.open_analog_workspace();assert ws.variables.toPlainText()=='unsaved_bias = 0.9';ws.close()
        checks.append('Reset closes analog workspace and preserves its draft when reopened')
        assert not errors,errors;(out/'acceptance.json').write_text(json.dumps(dict(status='passed',checks=checks,platform=app.platformName()),indent=2))
    finally:
        if w.run_manager.busy:w.run_manager.cancel(w.run_manager.rows);wait(lambda:not w.run_manager.busy)
        w.close();app.processEvents()


if __name__=='__main__':main()
