"""Fast native-workflow desktop acceptance, using actual ngspice workers."""
import argparse, json, os, sys, time, traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--evidence',type=Path,default=Path('build/native-workflow-evidence'));parser.add_argument('--require-windows',action='store_true');args=parser.parse_args()
    if args.require_windows and sys.platform!='win32':raise RuntimeError('This gate requires real Windows execution.')
    root=args.evidence.resolve();root.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_DATA_HOME']=str(root/'profile/data');os.environ['XDG_CONFIG_HOME']=str(root/'profile/config')
    from PySide6.QtWidgets import QApplication,QDialogButtonBox
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import digest,save_project,clone
    from icstudio.native_migration import review_path
    from icstudio.native_exchange import export_project
    from icstudio.xschem_workspace import show_review
    from icstudio.spice_program import find_ngspice
    from tests.test_native_migration import divider
    from icstudio.design_search import evaluate
    from icstudio import __version__
    errors=[]
    def exception(t,v,tb):
        errors.append(''.join(traceback.format_exception(t,v,tb)));sys.__excepthook__(t,v,tb)
    sys.excepthook=exception
    app=QApplication([]);w=Studio(recover=False);w.error=lambda msg:errors.append(str(msg));w.resize(1600,1000);w.show()
    p=review_path(divider(root/'small source café',include=True))['candidate'];p['native_migration'].pop('archive',None)
    p['cells'][0]['specifications']=[{'name':'Output','expression':'final(V("out"))','min':'0','max':'1','unit':'V'}]
    path=root/'native.icproj';save_project(p,path);w.set_project(p,path)
    exe=find_ngspice(os.environ.get('ICSTUDIO_TEST_NGSPICE',''))
    if not exe:raise RuntimeError('A real ngspice executable is required.')
    w.settings.setValue('engine/ngspice',exe);w.jobs_dir=root/'IC Design Studio café/runs';w.inspector_tabs.setCurrentIndex(1)
    def wait():
        deadline=time.monotonic()+90
        while w.run_manager.busy and time.monotonic()<deadline:QTest.qWait(20)
        assert not w.run_manager.busy,'Worker timeout';assert not errors,errors
        for row in w.run_manager.rows:assert row['state']=='Complete',(row['state'],row['log'])
    analyses=[]
    for typ in ('op','tran','dc','ac','noise'):
        w.analysis_type.setCurrentIndex(w.analysis_type.findData(typ));w.analysis_source.setCurrentText('V1')
        w.analysis_fields['stop'].setText('100u');w.analysis_fields['step'].setText('10u');w.analysis_fields['points'].setText('5');w.native_noise_output.setText('out')
        assert w.analysis_type.isEnabled();assert w.xschem_controls.isHidden()
        before=len(w.run_manager.rows);w.quick_run();assert len(w.run_manager.rows)==before+1,w.analysis_error.text();wait()
        r=w.run_manager.rows[-1]['result'];assert r['settings']['type']==typ;assert r['traces']['out'];analyses.append({'type':typ,'points':len(r['x']),'final':r['traces']['out'][-1]})
    w.analysis_type.setCurrentIndex(w.analysis_type.findData('op'))
    # Review a real sensitivity matrix through its controls, then run its cases.
    dlg=w.search_dialog('sensitivity');dlg.fields['targets'].setText('R1.native.value');dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
    matrix=w._case_matrix_dialog;assert matrix.case_table.rowCount()==3;matrix.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click();wait()
    sensitivity=evaluate(w.selected_manifest(),w.run_manager.rows);assert abs(sensitivity['sensitivities'][0]['normalized']+.5)<1e-4
    dlg=w.search_dialog('optimization');dlg.fields['lower'].setText('1000');dlg.fields['upper'].setText('3000');dlg.fields['count'].setText('3');dlg.fields['objective'].setText('.25');dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
    matrix=w._case_matrix_dialog;matrix.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click();wait()
    search=evaluate(w.selected_manifest(),w.run_manager.rows);assert search['best']['case']==3
    w.apply_search_values();assert next(d for d in w.cell['devices'] if d['name']=='R1')['native_spice']['parameters']['value']=='3000.0';w.undo()
    w.open_engineering_tab(w.cases_tab);QTest.qWait(80);w.grab().save(str(root/'native-studies.png'))
    # Exercise both steps of the native geometry binding dialog.
    d=next(d for d in w.cell['devices'] if d['name']=='R1');w.select([d['id']],'schematic');dlg=w.native_binding_dialog();dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
    mapping=w._workflow_dialog
    for role,pin in zip(('p','n'),d['symbol']['pin_order']):mapping.fields['pin_'+role].setCurrentText(pin)
    mapping.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click();assert not mapping.error.text(),mapping.error.text()
    dlg=w.parametric_dialog();dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click();assert not dlg.error.text(),dlg.error.text();assert w.cell['shapes']
    # Opening an exchange with edits must expose review rather than auto-accept.
    w.saved_hash=digest(w.project);out=export_project(w.project,root/'Xschem exchange');dlg=show_review(w,Path(out['directory'])/out['top'],[],auto_open=True)
    assert dlg.isVisible();assert not dlg.record['errors'],dlg.record['errors'];assert dlg.record['mode']=='native';dlg.grab().save(str(root/'native-exchange-review.png'));dlg.reject()
    assert not errors,errors
    result={'version':__version__,'status':'passed','platform':sys.platform,'native_windows':sys.platform=='win32','analyses':analyses,'sensitivity':sensitivity,'bounded_search':search,'worker_count':len(w.run_manager.rows),'checks':['Five graphical analyses through real workers','Native source selector and noise output','Sensitivity review matrix','Bounded search, apply and undo','Two-step native geometry binding and generation','Xschem exchange review with physical links','Paths containing spaces and Unicode']}
    (root/'native-workflows.json').write_text(json.dumps(result,indent=2));w.saved_hash=digest(w.project);w.close();print(json.dumps(result,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
