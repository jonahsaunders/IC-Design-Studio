"""Exercise saved implementation selection, transactions and the simulation worker."""
import argparse,json,os,sys,time,traceback
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--reference-project',type=Path);parser.add_argument('--parameter-project',type=Path)
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtWidgets import QApplication,QDialogButtonBox,QFileDialog,QInputDialog,QTabWidget,QLabel
    from PySide6.QtGui import QFontDatabase
    from icstudio.gui import Studio
    from icstudio.model import clone,digest,load_project,save_project
    from tests.test_implementation_views import fixture
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'profile/settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);app.setStyle('Fusion')
    if sys.platform=='win32' and app.platformName()=='offscreen':
        for name in ('segoeui.ttf','segoeuib.ttf','seguisb.ttf','consola.ttf'):
            QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name))
    studio=Studio(recover=False)
    studio.maybe_save=lambda:True;studio.live_check.setChecked(False);errors=[];studio.error=lambda msg:errors.append(str(msg))
    studio.settings.setValue('engine/ngspice',os.environ['ICSTUDIO_TEST_NGSPICE']);studio.jobs_dir=out/'runs'
    studio.resize(1450,950);studio.show();checks=[]
    def imported(dialog):
        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(netlist),'')),patch.object(QInputDialog,'getItem',side_effect=[('physical',True),('Extracted RC',True)]),patch.object(QInputDialog,'getText',return_value=('captured',True)):
            dialog.implementation.import_button.click()
        assert not dialog.implementation.error.text(),dialog.implementation.error.text()
    try:
        p,t,view=fixture();p.pop('implementation_views');t.pop('implementation_view')
        t['analysis'].update(type='dc',source='VDD',dc_start='.5',dc_stop='1',dc_step='.1',dc_startup=True)
        t['measurements'][0].update(min='.2',max='.6')
        netlist=out/'captured.spice';netlist.write_text(view['netlist'],encoding='utf-8')
        studio.set_project(p);studio._selected_testbench=t['id'];before=digest(studio.project)
        dialog=studio.edit_testbench();assert dialog.dc_startup.isChecked();imported(dialog);dialog.reject()
        assert digest(studio.project)==before;checks.append('Cancel leaves the source project unchanged')
        dialog=studio.edit_testbench();imported(dialog)
        tabs=dialog.findChild(QTabWidget);tabs.setCurrentIndex(next(i for i in range(tabs.count()) if tabs.tabText(i)=='Circuit implementation'))
        app.processEvents();dialog.grab().save(str(out/'implementation-selector.png'))
        dialog.buttons.button(QDialogButtonBox.Save).click();assert not dialog.error.text(),dialog.error.text()
        assert studio.selected_testbench()['analysis']['dc_startup'] is True
        assert studio.selected_testbench()['implementation_view']==studio.project['implementation_views'][0]['id']
        checks.append('Save commits the named view, selection and DC startup in one transaction')
        studio.undo();assert not studio.project.get('implementation_views');studio.redo()
        target=out/'saved.icproj';save_project(studio.project,target);studio.set_project(load_project(target),target)
        assert studio.selected_testbench()['implementation_view'];checks.append('Undo, redo and reopen retain the selection')
        if args.reference_project:
            studio.set_project(load_project(args.reference_project),args.reference_project)
        studio.open_testbenches();studio.compare_testbench_implementation();deadline=time.monotonic()+180
        while studio.run_manager.busy and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        assert not studio.run_manager.busy,'Comparison worker timed out'
        row=studio.run_manager.rows[-1];assert row['state']=='Complete',row.get('log')
        result=row['result'];comparison=result['implementation_comparison'];assert comparison['status']=='passed',comparison
        studio.open_testbenches();studio.results_dock.setFloating(True);studio.results_dock.resize(1240,740);app.processEvents()
        assert studio.bench_measurements.rowCount()==len(comparison['measurements'])+len(comparison['specifications'])
        assert studio.results_dock.grab().save(str(out/'comparison-results.png'))
        checks.append('Real ngspice comparison runs through the desktop worker and displays measurements and requirements')
        if args.parameter_project:
            from icstudio.catalog import binding_for,parameter_values
            studio.set_project(load_project(args.parameter_project),args.parameter_project)
            cell=next(c for c in studio.project['cells'] if any(d['name']=='MTAIL' for d in c['devices']))
            device=next(d for d in cell['devices'] if d['name']=='MTAIL');studio.cid=cell['id'];studio.refresh(True);studio.select([device['id']],'schematic')
            binding=binding_for(studio.project['pdk'],device);before=parameter_values(binding,device)['ad']
            width=studio.form_fields['param:w'];width.setText('57.82u')
            preview=next(w for w in studio.findChildren(QLabel) if w.accessibleName()=='Resolved PDK parameter values')
            assert 'ad = '+format(before*2,'.9g') in preview.text(),preview.text()
            studio.form_fields['modelparam:ad'].setText('9e-12');assert 'ad = 9e-12' in preview.text()
            studio.form_fields['modelparam:ad'].clear();assert 'ad = '+format(before*2,'.9g') in preview.text()
            assert studio.apply_inspector(True),errors
            updated=next(d for d in studio.cell['devices'] if d['id']==device['id'])
            assert 'ad' not in updated['model_params'] and abs(parameter_values(binding,updated)['ad']/before-2)<1e-10
            checks.append('Original bandgap MTAIL updates live diffusion formulas and blank restores the PDK default')
        assert not errors,errors
        report={'status':'passed','platform':app.platformName(),'checks':checks}
    except Exception:report={'status':'failed','checks':checks,'traceback':traceback.format_exc()}
    finally:studio.close();app.processEvents()
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
