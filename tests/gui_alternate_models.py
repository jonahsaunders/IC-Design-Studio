"""Exercise source desktop search, placement, inspector and saved model identity."""
import argparse,json,os,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--font',type=Path,help='Local host font for headless platforms without a system font database; never copied into the project.')
    args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    for key in ('XDG_DATA_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','APPDATA','LOCALAPPDATA'):
        os.environ[key]=str(out/'profile'/key)
    from PySide6.QtCore import QSettings,QStandardPaths,Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase,QFont
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import clone,digest,example,file_digest,load_project
    from scripts.prepare_alternate_models import NOTE
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    errors=[]
    def exception(t,v,tb):errors.append(''.join(traceback.format_exception(t,v,tb)))
    sys.excepthook=exception
    app=QApplication([]);app.setStyle('Fusion')
    if args.font:
        font_id=QFontDatabase.addApplicationFont(str(args.font.resolve()));assert font_id>=0
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0],10))
    w=Studio(recover=False);w.error=lambda text:errors.append(str(text));w.maybe_save=lambda:True
    w.live_check.setChecked(False);w.resize(1440,930);w.show();checks=[]
    for target in ('sky130A','gf180mcuC','gf180mcuD'):
        folder=ROOT/'icstudio/assets/pdks'/target;package=json.loads((folder/'package.json').read_bytes());note=json.loads((folder/NOTE).read_bytes())
        tech=clone(package['technology']);tech.update(package_root=str(folder),package_lock={k:package[k] for k in ('id','revision','files')})
        project=example('empty');project['pdk']=tech;w.set_project(project);w.sync_technology();w.show_library()
        w.library_category.setCurrentText('All devices');w.library_source.setCurrentIndex(0);w.library_collection.setCurrentText('All components')
        for row in note['choices']:
            w.library_search.setText(row['model']);QTest.qWait(1)
            items=[w.library_list.item(i) for i in range(w.library_list.count())]
            item=next(i for i in items if i.data(Qt.UserRole)==row['device'])
            assert not item.isHidden(),row['device'];w.library_list.setCurrentItem(item)
            available=row['status']=='AVAILABLE';assert w.place_library_button.isEnabled()==available
            if not available:
                assert 'definition is absent' in w.library_info.text()
            else:
                w.place_library_button.click();assert w.schematic.placement['model_ref']['device']==row['device']
                w.place_device_at(400,300);d=w.cell['devices'][-1];w.cancel_tool();w.select([d['id']])
                assert d['model_ref']['device']==row['device'] and d['model_ref']['revision']==package['revision']
                if row['parent']=='sky130_fd_pr/vpp_cap.sym':
                    assert 'modelparam:mult' in w.form_fields and 'modelparam:w' not in w.form_fields and 'modelparam:l' not in w.form_fields
            checks.append(dict(target=target,device=row['device'],status='placed' if available else 'blocked-missing-model'))
        w.path=out/(target+'.icproj');assert w.save();reopened=load_project(w.path)
        expected={r['device'] for r in note['choices'] if r['status']=='AVAILABLE'}
        assert {d['model_ref']['device'] for d in reopened['cells'][0]['devices']}==expected
        assert reopened['pdk']['package_lock']==w.project['pdk']['package_lock']
        w.library_search.clear();QTest.qWait(10);w.showNormal();w.resize(1440,930);QTest.qWait(10)
        assert w.grab().save(str(out/(target+'.png')))
    assert not errors,errors
    w.analysis_dirty=False;w.saved_hash=digest(w.project);w.close()
    report=dict(status='PASS',scope='Offscreen source desktop, not an installed executable or consumer-display acceptance.',
        placed=sum(c['status']=='placed' for c in checks),blocked=sum(c['status']=='blocked-missing-model' for c in checks),
        checks=checks,source_sha256=file_digest(__file__))
    assert (report['placed'],report['blocked'])==(44,3)
    (out/'report.json').write_bytes((json.dumps(report,indent=2)+'\n').encode());print('PASS: 44 model views searched, placed, inspected and saved; three missing models blocked.',flush=True)


if __name__=='__main__':main()
