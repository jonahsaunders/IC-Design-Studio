"""Exercise fresh placement and persisted edits through the source desktop."""
import argparse,json,sys,traceback
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtWidgets import QApplication,QFileDialog
    from unittest.mock import patch
    from icstudio.gui import Studio
    from icstudio.model import example,clone,digest,load_project,scalar
    from scripts.qualify_standard_mos import load_technology
    expected={'nfet3_03v3_nvt':(1,.5),'nfet3_05v0_nvt':(1,.9),'nfet3_g5v0d10v5':(1,.5),
        'nfet3_g5v0d16v0':(5,.7),'pfet3_01v8_lvt':(1,.35),'pfet3_g5v0d10v5':(1,.5),'pfet3_g5v0d16v0':(5,.66)}
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'profile/settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);studio=Studio(recover=False);studio.maybe_save=lambda:True;studio.live_check.setChecked(False)
    errors=[];studio.error=lambda text:errors.append(str(text));studio.show();cases=[]
    try:
        tech,identity=load_technology('sky130A');before=digest(tech)
        for name,wl in expected.items():
            p=example('empty');p['pdk']=clone(tech);studio.set_project(p);studio.sync_technology()
            studio.begin_placement('sky130_fd_pr/'+name+'.sym');studio.rotate();studio.place_device_at(300,250);studio.cancel_tool();app.processEvents()
            d=studio.cell['devices'][-1];assert d['rotation']==90
            assert all(abs(scalar(d['params'][k])*1e6-v)<1e-10 for k,v in zip(('w','l'),wl))
            assert set(d['nets'])=={'d','g','s','b'}
            studio.select([d['id']]);studio.duplicate();assert len(studio.cell['devices'])==2
            assert studio.cell['devices'][-1]['params']==d['params'];studio.undo();assert len(studio.cell['devices'])==1
            studio.redo();assert len(studio.cell['devices'])==2;studio.undo()
            studio.select([d['id']]);studio.form_fields['param:w'].setText('7u');studio.inspector_changed();assert studio.flush_inspector()
            assert abs(scalar(studio.cell['devices'][0]['params']['w'])-7e-6)<1e-15
            path=out/(name+'.icproj')
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(path),'')):assert studio.save()
            reopened=load_project(path);assert reopened['cells']==studio.project['cells']
            studio.set_project(reopened);assert abs(scalar(studio.cell['devices'][0]['params']['w'])-7e-6)<1e-15
            cases.append(dict(view=name,status='PASS',initial_um=dict(zip(('w','l'),wl)),persisted_width_um=7))
        assert digest(tech)==before and not errors,errors
        result=dict(status='PASS',cases=cases,package=identity,platform=app.platformName(),scope='Source desktop placement, rotation, duplicate, undo/redo, property edit and save/reopen. Not frozen desktop acceptance.')
    except Exception:result=dict(status='FAIL',cases=cases,errors=errors,traceback=traceback.format_exc())
    finally:studio.saved_hash=digest(studio.project);studio.close();app.processEvents()
    (out/'record.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result,indent=2))
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
