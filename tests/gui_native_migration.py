"""Cross-platform native migration acceptance through the actual GUI worker.

Use ICSTUDIO_TEST_NGSPICE or the bundled runtime. --project accepts the user's
migrated GF180 design; --full retains its complete program rather than a short
diagnostic. --require-windows prevents a Linux result being called Windows QA.
"""
import argparse
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--evidence',type=Path,default=Path('build/native-migration-evidence'))
    parser.add_argument('--project',type=Path);parser.add_argument('--full',action='store_true');parser.add_argument('--require-windows',action='store_true');args=parser.parse_args()
    if args.require_windows and sys.platform!='win32':raise RuntimeError('Native Windows execution is required for this acceptance gate.')
    root=args.evidence.resolve();root.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_DATA_HOME']=str(root/'profile/data');os.environ['XDG_CONFIG_HOME']=str(root/'profile/config')
    from PySide6.QtWidgets import QApplication,QDialogButtonBox
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio import __version__
    from icstudio.model import load_project,save_project,digest,clone
    from icstudio.native_migration import review_path
    from icstudio.electrical_identity import partition
    from icstudio.spice_program import find_ngspice
    errors=[];sys.excepthook=lambda t,v,tb:errors.append(''.join(traceback.format_exception(t,v,tb)))
    app=QApplication([]);w=Studio(recover=False);w.error=lambda msg:errors.append(str(msg));w.resize(1600,1000);w.show()
    if args.project:p=load_project(args.project)
    else:
        from tests.test_native_migration import divider
        source=divider(root/'Original source café',hierarchical=True,include=True);result=review_path(source)
        assert result['status']=='Complete',result['items'];p=result['candidate'];shutil.rmtree(source.parent)
    assert p.get('spice',{}).get('version')==1
    p['native_migration'].pop('archive',None)
    if args.project and not args.full:
        for c in p['cells']:
            for d in c['devices']:
                info=d.get('native_spice',{})
                if info.get('type')=='program' and '.control' in info['text']:
                    info['text']=info['text'].split('.control')[0]+'.control\nop\ntran 100n 20u\nac dec 5 1 1Meg\n.endc'
    relocated=root/'Moved native project café';relocated.mkdir(exist_ok=True);path=relocated/'design.icproj';save_project(p,path)
    w.set_project(load_project(path),path);assert w.current_analysis_settings()['type']=='program'
    w.inspector_tabs.setCurrentIndex(1);QTest.qWait(30);assert not w.xschem_controls.isHidden()
    report=w.show_migration_review({'status':'Complete','candidate':None,'items':p['native_migration']['items']},readonly=True)
    assert report.table.rowCount()>0;report.grab().save(str(root/'migration-review.png'));report.reject()
    # Exercise the native property editor, including a real validation/undo transaction.
    target=next(d for d in w.cell['devices'] if d.get('native_spice',{}).get('type')=='device' and d['native_spice']['parameters'])
    key=next((k for k in ('value','r','m') if k in target['native_spice']['parameters']),next(iter(target['native_spice']['parameters'])))
    original=target['native_spice']['parameters'][key];dlg=w.edit_native_properties(target['id'])
    changed='2k' if key in ('value','r') else '2'
    dlg.editor[key].setText(changed);dlg.buttons.button(QDialogButtonBox.Save).click();assert not dlg.isVisible()
    assert next(d for d in w.cell['devices'] if d['id']==target['id'])['native_spice']['parameters'][key]==changed
    w.undo();assert next(d for d in w.cell['devices'] if d['id']==target['id'])['native_spice']['parameters'][key]==original
    # Move a real device repeatedly and verify connectivity and stable net IDs.
    target=next(d for d in w.cell['devices'] if d['name']==('M5' if args.project else 'X1'))
    ident=target['id'];before=partition(w.cell);nets=clone(target['net_ids']);wire_count=len(w.cell['wires'])
    for _ in range(3):
        w.move([ident],20,0,'schematic');w.move([ident],-20,0,'schematic')
    assert not errors,errors;assert partition(w.cell)==before
    assert next(d for d in w.cell['devices'] if d['id']==ident)['net_ids']==nets
    assert len(w.cell['wires'])<=wire_count+2
    save_project(w.project,path);w.set_project(load_project(path),path)
    executable=find_ngspice(os.environ.get('ICSTUDIO_TEST_NGSPICE',''))
    if not executable:raise RuntimeError('A real ngspice executable is required for this gate.')
    w.settings.setValue('engine/ngspice',executable);w.jobs_dir=root/'IC Design Studio/runs'
    w.xschem_timeout.setValue(240 if args.full else 2);w.quick_run();deadline=time.monotonic()+(14500 if args.full else 150)
    while w.run_manager.busy and time.monotonic()<deadline:QTest.qWait(25)
    assert not w.run_manager.busy,'Simulation timed out'
    row=w.run_manager.rows[-1];assert row['state']=='Complete',row['log'];r=row['result']
    assert r['program_status']=='Complete',r['warnings'];cases=r['analysis_cases']
    assert len(cases)==(144 if args.full and args.project else 3)
    w.refresh_xschem_cases();assert w.xschem_case_table.rowCount()==len(cases)
    w.select_xschem_case_data(cases[0]['number']);op=dict(w.result['traces'])
    if args.project:assert abs(op['vref'][0]-1.195093286891953)<1e-6
    else:assert abs(op['out'][0]-.5)<1e-9
    for case in cases[:3]:w.select_xschem_case_data(case['number'])
    w.results_dock.show();w.open_engineering_tab(w.xschem_tab);QTest.qWait(80);w.grab().save(str(root/'native-analysis.png'))
    assert not errors,errors
    evidence={'version':__version__,'status':'passed','platform':sys.platform,'native_windows':sys.platform=='win32','project':'supplied GF180' if args.project else 'hierarchical divider','full_program':bool(args.full),'archive_removed':True,'case_count':len(cases),'program_status':r['program_status'],'operating_point':{k:v[0] for k,v in op.items()},'checks':['Migration report','Native parameter editor','Repeated connected device movement','Persistent net and terminal IDs','Save and reopen from moved folder','Real GUI simulation worker','Case table and waveform switching']}
    (root/'native-migration.json').write_text(json.dumps(evidence,indent=2));w.saved_hash=digest(w.project);w.close();print(json.dumps(evidence,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
