"""Source desktop tap placement, live resistance and unchanged saved identity."""
import argparse,json,math,os,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--font',type=Path);a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    for k in ('XDG_DATA_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','APPDATA','LOCALAPPDATA'):os.environ[k]=str(out/'profile'/k)
    from PySide6.QtCore import QSettings,QStandardPaths,Qt
    from PySide6.QtWidgets import QApplication,QLabel
    from PySide6.QtGui import QFontDatabase,QFont
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import digest,file_digest,load_project
    from icstudio.catalog import binding_for,parameter_values
    from icstudio.pdks import PDKRegistry
    from icstudio.project_hub import inventory,build_project
    from icstudio.interchange import spice
    from scripts.device_qualification_source import REVISIONS,PROMOTED as DEFAULT_MANIFESTS
    REVISION=REVISIONS['ihp-sg13g2'];PROMOTED=DEFAULT_MANIFESTS['ihp-sg13g2']
    from scripts.qualify_ihp_taps import resistance
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'));QStandardPaths.writableLocation=staticmethod(lambda k:str(out/'profile'/str(k.value)))
    errors=[]
    def exception(t,v,tb):
        text=''.join(traceback.format_exception(t,v,tb));errors.append(text);(out/'errors.log').write_text('\n'.join(errors));sys.stderr.write(text)
    sys.excepthook=exception
    app=QApplication([]);app.setStyle('Fusion')
    if a.font:
        fid=QFontDatabase.addApplicationFont(str(a.font.resolve()));assert fid>=0;app.setFont(QFont(QFontDatabase.applicationFontFamilies(fid)[0],10))
    reg=PDKRegistry(out/'registry');rows,notes=inventory(reg);assert not notes
    row=next(r for r in rows if r['id']=='ihp-sg13g2' and r['status']=='Available offline');assert row['revision']==REVISION
    project=build_project(reg,row,'IHP tap resistance','empty')['project'];reg.verify(row['key'])
    installed=Path(project['pdk']['package_root'])/'package.json';bundled=ROOT/'icstudio/assets/pdks/ihp-sg13g2/package.json'
    assert file_digest(bundled)==PROMOTED and json.loads(installed.read_bytes())==json.loads(bundled.read_bytes())
    w=Studio(recover=False);w.error=lambda text:errors.append(str(text));w.maybe_save=lambda:True;w.live_check.setChecked(False);w.set_project(project);w.sync_technology();w.resize(1440,930);w.show();w.show_library()
    w.library_category.setCurrentText('All devices');w.library_source.setCurrentIndex(0);w.library_collection.setCurrentText('All components')
    checks=[]
    for index,model in enumerate(('ntap1','ptap1')):
        key='sg13g2_pr/'+model+'.sym';w.library_search.setText(model);QTest.qWait(10)
        item=next(w.library_list.item(i) for i in range(w.library_list.count()) if w.library_list.item(i).data(Qt.UserRole)==key)
        assert not item.isHidden();w.library_list.setCurrentItem(item);assert w.place_library_button.isEnabled();w.place_library_button.click();w.place_device_at(300+index*350,300);w.cancel_tool()
        d=w.cell['devices'][-1];w.select([d['id']]);QTest.qWait(10);assert w.form_fields['modelparam:emit_r'].isReadOnly()
        assert not w.form_fields['modelparam:w'].isReadOnly() and not w.form_fields['modelparam:l'].isReadOnly()
        initial=parameter_values(binding_for(w.project['pdk'],d),d)['emit_r']
        w.form_fields['modelparam:w'].setText('2u');w.form_fields['modelparam:l'].setText('5u')
        preview=next(q for q in w.findChildren(QLabel) if q.accessibleName()=='Resolved PDK parameter values')
        assert 'Cannot apply' not in preview.text() and 'emit_r = '+format(resistance(2e-6,5e-6),'.9g') in preview.text(),preview.text()
        w.apply_inspector(True);assert not errors,errors;d=w.cell['devices'][-1]
        assert 'emit_r' not in d['model_params']
        updated=parameter_values(binding_for(w.project['pdk'],d),d)['emit_r']
        assert not math.isclose(initial,updated);assert math.isclose(updated,resistance(2e-6,5e-6),rel_tol=1e-12)
        checks.append(dict(model=model,initial_ohms=initial,edited_ohms=updated))
    w.path=out/'taps.icproj';assert w.save();p=load_project(w.path);assert p['pdk']['package_lock']==w.project['pdk']['package_lock'];text=spice(p)
    for d in p['cells'][0]['devices']:
        model=binding_for(p['pdk'],d)['model'];line=next(s for s in text.splitlines() if ' '+model+' ' in s);fields=line.split()
        assert fields[1:3]==[d['nets'][n] for n in ('p','m')] and len(set(fields[1:3]))==2
        params=dict(s.split('=',1) for s in fields[4:])
        assert math.isclose(float(params['w']),2e-6) and math.isclose(float(params['l']),5e-6),line
        assert math.isclose(float(params['r']),resistance(2e-6,5e-6),rel_tol=1e-10),line
        assert d['model_ref']['revision']==REVISION and 'emit_r' not in d['model_params']
    w.set_project(p);w.sync_technology();w.select([p['cells'][0]['devices'][-1]['id']]);assert w.form_fields['modelparam:emit_r'].isReadOnly()
    w.showNormal();w.resize(1440,930);QTest.qWait(50);assert w.grab().save(str(out/'taps.png'));assert not errors,errors
    w.analysis_dirty=False;w.saved_hash=digest(w.project);w.close()
    report=dict(status='PASS',scope='Current-source offscreen desktop; placement, parameter editing, computed resistance, save/reopen/netlist. Not installed acceptance.',revision=REVISION,checks=checks,source_sha256=file_digest(__file__),saved_sha256=file_digest(out/'taps.icproj'))
    (out/'report.json').write_bytes((json.dumps(report,indent=2)+'\n').encode());print(json.dumps(report),flush=True)


if __name__=='__main__':main()
