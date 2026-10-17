"""Source desktop placement and saved identity for the corrected SKY130 LI view."""
import argparse,json,os,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--font',type=Path);a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    for k in ('XDG_DATA_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','APPDATA','LOCALAPPDATA'):os.environ[k]=str(out/'profile'/k)
    from PySide6.QtCore import QSettings,QStandardPaths,Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase,QFont
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import digest,file_digest,load_project
    from icstudio.pdks import PDKRegistry
    from icstudio.project_hub import inventory,build_project
    from icstudio.interchange import spice
    from scripts.sky130_li_source import REVISION,PROMOTED
    from scripts.prepare_sky130_li_qualification import KEY
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'));QStandardPaths.writableLocation=staticmethod(lambda k:str(out/'profile'/str(k.value)))
    errors=[]
    def exception(t,v,tb):
        text=''.join(traceback.format_exception(t,v,tb));errors.append(text);(out/'errors.log').write_text('\n'.join(errors));sys.stderr.write(text)
    sys.excepthook=exception
    app=QApplication([]);app.setStyle('Fusion')
    if a.font:
        fid=QFontDatabase.addApplicationFont(str(a.font.resolve()));assert fid>=0;app.setFont(QFont(QFontDatabase.applicationFontFamilies(fid)[0],10))
    reg=PDKRegistry(out/'registry');rows,notes=inventory(reg);assert not notes
    row=next(r for r in rows if r['id']=='sky130A' and r['status']=='Available offline');assert row['revision']==REVISION
    project=build_project(reg,row,'LI resistor acceptance','empty')['project'];installed=Path(project['pdk']['package_root'])/'package.json';bundled=ROOT/'icstudio/assets/pdks/sky130A/package.json'
    assert file_digest(bundled)==PROMOTED;assert json.loads(installed.read_bytes())==json.loads(bundled.read_bytes());reg.verify(row['key'])
    w=Studio(recover=False);w.error=lambda text:errors.append(str(text));w.maybe_save=lambda:True;w.live_check.setChecked(False);w.set_project(project);w.sync_technology();w.resize(1440,930);w.show();w.show_library()
    w.library_category.setCurrentText('All devices');w.library_source.setCurrentIndex(0);w.library_collection.setCurrentText('All components');w.library_search.setText('res_generic_li');QTest.qWait(10)
    item=next(w.library_list.item(i) for i in range(w.library_list.count()) if w.library_list.item(i).data(Qt.UserRole)==KEY)
    assert not item.isHidden();w.library_list.setCurrentItem(item);assert w.place_library_button.isEnabled();w.place_library_button.click();w.place_device_at(400,300);w.cancel_tool()
    d=w.cell['devices'][-1];w.select([d['id']]);assert all('modelparam:'+k in w.form_fields for k in ('w','l','mult'));assert d['model_ref']['revision']==REVISION
    d['model_params'].update(w=2,l=5,mult=3);w.path=out/'resistor.icproj';assert w.save()
    reopened=load_project(w.path);assert reopened['pdk']['package_lock']==w.project['pdk']['package_lock'];text=spice(reopened)
    saved=reopened['cells'][0]['devices'][0];assert len(set(saved['nets'].values()))==2
    line=next(s for s in text.splitlines() if 'sky130_fd_pr__res_generic_l1 ' in s);fields=line.split();assert fields[1:4]==[saved['nets']['m'],saved['nets']['p'],'sky130_fd_pr__res_generic_l1'];assert dict(s.split('=',1) for s in fields[4:])==dict(w='2',l='5',m='3')
    w.showNormal();w.resize(1440,930);QTest.qWait(50)
    assert w.grab().save(str(out/'resistor.png'));assert not errors,errors;w.analysis_dirty=False;w.saved_hash=digest(w.project);w.close()
    report=dict(status='PASS',scope='Offscreen current-source desktop; not an installed release.',revision=REVISION,bundled_manifest_sha256=PROMOTED,installed_manifest_sha256=file_digest(installed),source_sha256=file_digest(__file__),saved_sha256=file_digest(out/'resistor.icproj'))
    (out/'report.json').write_bytes((json.dumps(report,indent=2)+'\n').encode());print(json.dumps(report),flush=True)


if __name__=='__main__':main()
