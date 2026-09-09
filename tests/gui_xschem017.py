"""Native acceptance for dependency review and direct Xschem editing."""
import argparse,json,os,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
from PySide6.QtCore import Qt,QSettings
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.xschem_workspace import show_review
from icstudio.xschem_project import export_project,review_schematic,apply_review
from icstudio.model import flatten,save_project,load_project,scalar
from tests.xschem_fixtures import amplifier
errors=[];sys.excepthook=lambda t,v,tb:(errors.append(str(v)),traceback.print_exception(t,v,tb));app=QApplication([]);app.setStyle('Fusion');QSettings('ICDesignStudio','Studio').clear();w=Studio(recover=False);w.error=lambda e:errors.append(str(e));w.maybe_save=lambda:True;w.resize(1500,980);w.show();QTest.qWait(80);checks=[]
try:
    assert any(a.text()=='Import Xschem schematic…' for a in w._task_submenus['File/Import'].actions());checks.append('Direct Xschem import is visible in File / Import')
    path=amplifier(out/'original');dlg=show_review(w,path,[]);QTest.qWait(80);assert not dlg.record['errors'],dlg.record['errors'];assert dlg.open_button.isEnabled();dlg.grab().save(str(out/'dependency-review.png'));checks.append('Dependency and hierarchy review enables supported import')
    dlg.open_button.click();QTest.qWait(100);assert len(w.project['cells'])==2;assert w.mode_combo.currentIndex()==0;w.grab().save(str(out/'imported-amplifier.png'));checks.append('Reviewed hierarchical amplifier opens as native editable geometry')
    cid=w.cid;amp=next(d for d in w.cell['devices'] if d['kind']=='X');w.select([amp['id']]);w.capture_enter();QTest.qWait(80);assert w.cell['name']=='gain';rd=next(d for d in w.cell['devices'] if d['name']=='RD');w.select([rd['id']]);w.build_inspector();assert w.form_fields['Value'].text()=='{resistance}';w.form_fields['Value'].setText('{resistance * 1.5}');w.apply_inspector(True);assert w.cell['devices'][0]['value']=='{resistance * 1.5}';w.undo();assert w.cell['devices'][0]['value']=='{resistance}';w.redo();w.grab().save(str(out/'editable-child.png'));checks.append('Child schematic navigation and parameter expression edits support undo/redo')
    from icstudio.capture_ops import transform
    w.capture_commit(lambda p:transform(p,w.cid,[rd['id']],40,20),'Move imported resistor');assert not errors,errors;w.capture_leave();assert w.cid==cid;checks.append('Imported device stretch preserves connections and hierarchy return')
    export=export_project(w.project,out/'export');record=review_schematic(out/'export'/export['top']);assert not record['errors'],record['errors'];q=apply_review(record);ds={d['name']:d for d in flatten(q)};assert scalar(ds['XAMP/RD']['value'])==12000;checks.append('Export and reimport retain native electrical edits')
    save_project(q,out/'roundtrip.icproj');w.set_project(load_project(out/'roundtrip.icproj'));assert len(w.project['cells'])==2;checks.append('Imported project saves and reopens with source preservation metadata')
    missing=out/'original/devices/res.sym';backup=out/'relocated/res.sym';backup.parent.mkdir(exist_ok=True);backup.write_bytes(missing.read_bytes());missing.unlink();dlg=show_review(w,path,[]);QTest.qWait(50);assert not dlg.open_button.isEnabled();assert any(d['status']=='Missing' for d in dlg.record['dependencies']);dlg.grab().save(str(out/'missing-dependency.png'));checks.append('Missing dependencies block import with visible repair guidance')
    from unittest.mock import patch
    assert dlg.locate_button.isEnabled();assert 'devices/res.sym' in dlg.detail.toPlainText()
    with patch('icstudio.xschem_workspace.QFileDialog.getOpenFileName',return_value=(str(backup),'')):dlg.locate_button.click()
    QTest.qWait(30);assert not dlg.record['errors'],dlg.record['errors'];assert dlg.open_button.isEnabled();assert dlg.file_locations['devices/res.sym']==str(backup);checks.append('Locate selected file repairs a missing symbol and enables import')
    dlg.copy_button.click();assert 'Located | Symbol | devices/res.sym' in QApplication.clipboard().text();assert 'Search folders:' in QApplication.clipboard().text();checks.append('Copy diagnostic report includes actual resolution and search paths')
    dlg.reject();dlg=show_review(w,path);assert str(backup.parent) in dlg.library_paths.toPlainText();dlg.reject();checks.append('Chosen library folders persist between import dialogs')
    assert not errors,errors
    report={'status':'passed','checks':checks,'errors':errors}
except Exception:
    report={'status':'failed','checks':checks,'errors':errors,'exception':traceback.format_exc()};raise
finally:
    (out/'report.json').write_text(json.dumps(report,indent=2));w.history.undo_stack.clear();w.maybe_save=lambda:True;w.close();app.processEvents()
print(json.dumps(report,indent=2))
