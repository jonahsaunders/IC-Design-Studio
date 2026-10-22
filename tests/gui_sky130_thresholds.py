"""Generate, undo, regenerate and reopen all six threshold-MOS catalog views."""
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
    errors=[];studio.error=lambda text:errors.append(str(text));studio.show();rows=[]
    def accept(dialog):
        if dialog is not None:
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click();app.processEvents()
        review=studio._review_dialog;button=review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply)
        assert button.isEnabled(),errors;button.click();app.processEvents();assert not review.isVisible(),errors
    try:
        package=json.loads((root/'icstudio/assets/pdks/sky130A/package.json').read_bytes())
        for model in ('nfet_01v8_lvt','pfet_01v8_lvt','pfet_01v8_hvt'):
            for suffix in ('','_nf'):
                p=example('empty');p['pdk']=clone(package['technology'])
                p['pdk'].update(package_root=str(root/'icstudio/assets/pdks/sky130A'),package_lock={k:package[k] for k in ('id','revision','files')})
                d=create_device(p['pdk'],'sky130_fd_pr/'+model+suffix+'.sym','M1')
                d['params'].update(w='1u' if suffix else '2u',l='.5u');d['model_params'].update(nf=2,mult=3)
                d['nets']=dict(d='D',g='G',s='S',b='B');p['cells'][0]['devices']=[d]
                studio.set_project(p);studio.selection=[d['id']];studio.refresh()
                accept(studio.mos_layout_dialog());assert not audit(studio.project,studio.cid)
                assert studio.cell['pdk_layouts'][0]['parallel_units']['count']==3
                model_name=studio.cell['pdk_layouts'][0]['spec']['model'];assert model_name=='sky130_fd_pr__'+model
                studio.undo();assert not studio.cell.get('pdk_layouts');studio.redo()
                studio.commit(lambda project:project['cells'][0]['devices'][0]['params'].update(w='4u'),'Change device width')
                studio.selection=[d['id']];studio.refresh();accept(studio.mos_layout_dialog())
                assert not audit(studio.project,studio.cid)
                path=out/(model+suffix+'.icproj');save_project(studio.project,path)
                reopened=load_project(path);assert reopened['cells']==studio.project['cells']
                rows.append(dict(view=model+suffix,status='PASS',model=model_name))
        assert not errors,errors
        result=dict(status='PASS',cases=rows,platform=app.platformName(),scope='Source Qt generation/review, undo/redo, regeneration and save/reopen; not frozen desktop acceptance.')
    except Exception:result=dict(status='FAIL',cases=rows,errors=errors,traceback=traceback.format_exc())
    finally:studio.close();app.processEvents()
    (out/'record.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
