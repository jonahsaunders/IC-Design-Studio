"""Import the reduced user schematic through Qt and run all six real analyses."""
import argparse,json,os,sys,time,traceback
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--evidence',type=Path,default=ROOT/'build/bandgap-gui-evidence')
    args=parser.parse_args();out=args.evidence.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
    from PySide6.QtWidgets import QApplication,QDialogButtonBox,QFileDialog
    from PySide6.QtCore import QSettings
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import digest,load_project
    from icstudio.migration_ui import show
    from icstudio.pdks import PDKRegistry
    from icstudio.bundled_pdks import packages
    from icstudio.spice_program import find_ngspice
    errors=[]
    def exception(t,v,tb):errors.append(''.join(traceback.format_exception(t,v,tb)));traceback.print_exception(t,v,tb)
    sys.excepthook=exception
    app=QApplication([]);app.setStyle('Fusion');QSettings('ICDesignStudio','Studio').clear()
    w=Studio(recover=False);w.error=lambda message:errors.append(str(message));w.resize(1550,950);w.show()
    engine=find_ngspice(os.environ.get('ICSTUDIO_TEST_NGSPICE',''))
    if not engine:raise RuntimeError('A real ngspice executable is required.')
    w.settings.setValue('engine/ngspice',engine);w.jobs_dir=out/'runs with spaces'
    w.pdk_registry=PDKRegistry(out/'registry with spaces')
    package=next(p for p in packages() if p['name']=='gf180mcuD')
    key=w.pdk_registry.install(Path(package['path'])/'package.json')
    w.saved_hash=digest(w.project)
    dlg=show(w,source=ROOT/'examples/gf180-bandgap/5vfullv2-compatibility.sch')
    dlg.technology.setCurrentIndex(dlg.technology.findData(key))
    assert dlg.result_data['converted']==60 and dlg.result_data['unmatched']==0
    save=dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Save);assert save.isEnabled()
    QTest.qWait(30);dlg.grab().save(str(out/'migration.png'))
    path=out/'six-case-native.icproj'
    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(path),'')):save.click()
    assert path.is_file() and not dlg.isVisible(),errors
    w.set_project(load_project(path),path)
    assert w.analysis_engine.currentData()=='ngspice' and w.current_analysis_settings()['type']=='program'
    w.quick_run();deadline=time.monotonic()+180
    while w.run_manager.busy and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert not w.run_manager.busy,'Six-case GUI run timed out'
    row=w.run_manager.rows[-1];assert row['state']=='Complete',row['log'];result=row['result']
    assert result['program_status']=='Complete',result['warnings']
    cases=result['analysis_cases'];assert len(cases)==6
    assert [c['analysis'] for c in cases]==['tran','dc','dc','dc','ac','ac']
    assert all(c['state']=='Complete' for c in cases)
    w.refresh_xschem_cases();assert w.xschem_case_table.rowCount()==6
    for c in cases:
        w.select_xschem_case_data(c['number']);assert w.result['plot_kind']==c['analysis'] and w.result['traces']['vref']
    w.select_xschem_case_data(1);assert abs(w.result['traces']['vref'][-1]-1.1950723506143166)<1e-6
    assert len(cases[0].get('measurements',[]))==5,'Startup measurement missing from the result table'
    w.results_dock.show();w.open_engineering_tab(w.xschem_tab);w.fit_active();QTest.qWait(80)
    assert w.grab().save(str(out/'six-cases.png'))
    assert not errors,errors
    report={'status':'passed','platform':sys.platform,'analysis_count':6,'native_models':60,
            'startup_vref_v':result['traces']['vref'][-1],'program_status':result['program_status'],
            'checks':['Native catalog migration UI','Save and reopen','Real GUI simulation worker','Six completed cases','Five startup measurements','Transient/DC/AC waveform switching'],'errors':errors}
    (out/'report.json').write_text(json.dumps(report,indent=2));w.saved_hash=digest(w.project);w.close();print(json.dumps(report,indent=2))


if __name__=='__main__':main()
