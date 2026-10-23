"""Source desktop generation, undo, regeneration and reopen of second MiM."""
import argparse,json,sys,traceback
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);a=ap.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtWidgets import QApplication,QDialogButtonBox
    from icstudio.gui import Studio
    from icstudio.catalog import create_device
    from icstudio.model import example,clone,save_project,load_project
    from icstudio.sky130_layout import audit
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'profile/settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);studio=Studio(recover=False);studio.maybe_save=lambda:True;studio.live_check.setChecked(False)
    errors=[];studio.error=lambda text:errors.append(str(text));studio.show()
    def accept(dialog):
        if dialog is not None:dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click();app.processEvents()
        review=studio._review_dialog;button=review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply)
        assert button.isEnabled(),errors;button.click();app.processEvents();assert not review.isVisible(),errors
    try:
        package=json.loads((root/'icstudio/assets/pdks/sky130A/package.json').read_bytes())
        p=example('empty');p['pdk']=clone(package['technology'])
        p['pdk'].update(package_root=str(root/'icstudio/assets/pdks/sky130A'),package_lock={k:package[k] for k in ('id','revision','files')})
        d=create_device(p['pdk'],'sky130_fd_pr/cap_mim_m3_2.sym','C1')
        d['model_params'].update(w=2,l=2,mf=3);d['nets']=dict(c0='P',c1='N');p['cells'][0]['devices']=[d]
        studio.set_project(p);studio.selection=[d['id']];studio.refresh()
        accept(studio.mos_layout_dialog());assert not audit(studio.project,studio.cid)
        assert studio.cell['pdk_layouts'][0]['parallel_units']['count']==3
        studio.undo();assert not studio.cell.get('pdk_layouts');studio.redo()
        studio.commit(lambda project:project['cells'][0]['devices'][0]['model_params'].update(w=4,l=4),'Resize capacitor')
        studio.selection=[d['id']];studio.refresh();accept(studio.mos_layout_dialog());assert not audit(studio.project,studio.cid)
        path=out/'mim2.icproj';save_project(studio.project,path);reopened=load_project(path);assert reopened['cells']==studio.project['cells']
        from icstudio.interchange import spice
        line=next(s for s in spice(reopened).splitlines() if s.startswith('X_C1 '))
        assert set(line.split()[4:])=={'w=4','l=4','mf=3','m=3'},line
        studio.commit(lambda project:project['cells'][0]['devices'][0]['model_params'].update(w=3.005,l=5.005),'Resize rectangular capacitor')
        studio.selection=[d['id']];studio.refresh();accept(studio.mos_layout_dialog());assert not audit(studio.project,studio.cid)
        path=out/'rectangular-mim2.icproj';save_project(studio.project,path);reopened=load_project(path)
        assert reopened['cells']==studio.project['cells']
        line=next(s for s in spice(reopened).splitlines() if s.startswith('X_C1 '))
        assert set(line.split()[4:])=={'w=3.005','l=5.005','mf=3','m=3'},line
        assert reopened['pdk']['package_lock']==studio.project['pdk']['package_lock']
        assert not errors,errors
        result=dict(status='PASS',platform=app.platformName(),scope='Source Qt generation/review, undo/redo, regeneration and save/reopen; not frozen desktop acceptance.')
    except Exception:result=dict(status='FAIL',errors=errors,traceback=traceback.format_exc())
    finally:studio.close();app.processEvents()
    (out/'record.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result,indent=2))
    return int(result['status']!='PASS')

if __name__=='__main__':raise SystemExit(main())
