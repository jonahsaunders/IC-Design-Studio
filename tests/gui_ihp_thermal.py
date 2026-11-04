"""Source-desktop placement and saved five-terminal HBT interfaces."""
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
    from icstudio.catalog import binding_for
    from icstudio.catalog_migration import symbol_context
    from icstudio.symbol_geometry import visible_text
    from icstudio.pdks import PDKRegistry
    from icstudio.project_hub import inventory,build_project
    from icstudio.interchange import spice
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'));QStandardPaths.writableLocation=staticmethod(lambda k:str(out/'profile'/str(k.value)))
    errors=[]
    def exception(t,v,tb):
        text=''.join(traceback.format_exception(t,v,tb));errors.append(text);(out/'errors.log').write_text('\n'.join(errors));sys.stderr.write(text)
    sys.excepthook=exception
    app=QApplication([]);app.setStyle('Fusion')
    if a.font:
        fid=QFontDatabase.addApplicationFont(str(a.font.resolve()));assert fid>=0;app.setFont(QFont(QFontDatabase.applicationFontFamilies(fid)[0],10))
    reg=PDKRegistry(out/'registry');rows,notes=inventory(reg);assert not notes
    row=next(r for r in rows if r['id']=='ihp-sg13g2' and r['status']=='Available offline')
    project=build_project(reg,row,'IHP thermal terminals','empty')['project'];reg.verify(row['key'])
    w=Studio(recover=False);w.error=lambda text:errors.append(str(text));w.maybe_save=lambda:True;w.live_check.setChecked(False);w.set_project(project);w.sync_technology();w.resize(1440,930);w.show();w.show_library()
    w.library_category.setCurrentText('All devices');w.library_source.setCurrentIndex(0);w.library_collection.setCurrentText('All components')
    for index,model in enumerate(('npn13G2_5t','npn13G2l_5t','npn13G2v_5t')):
        key='sg13g2_pr/'+model+'.sym';w.library_search.setText(model);QTest.qWait(10)
        item=next(w.library_list.item(i) for i in range(w.library_list.count()) if w.library_list.item(i).data(Qt.UserRole)==key)
        assert not item.isHidden();w.library_list.setCurrentItem(item);assert w.place_library_button.isEnabled();w.place_library_button.click();w.place_device_at(250+index*250,300);w.cancel_tool()
        d=w.cell['devices'][-1];w.select([d['id']]);assert 'modelparam:nx' in w.form_fields
        assert {p:w.form_fields['net:'+p].accessibleName() for p in d['nets']}==dict(c='Collector',b='Base',e='Emitter',s='Substrate',t='Temperature rise')
        w.form_fields['modelparam:nx'].setText('4')
        if index:assert 'modelparam:el' in w.form_fields;w.form_fields['modelparam:el'].setText('2.5')
        w.apply_inspector(True)
        d=w.cell['devices'][-1];context=symbol_context(d,w.project['pdk']);assert context['Nx']=='4'
        if index:assert context['El']=='2.5'
        labels=[visible_text(i,context) for i in d['symbol']['primitives'] if i['kind']=='text'];assert not any('@Nx' in t or '@El' in t for t in labels)
    w.path=out/'thermal.icproj';assert w.save();p=load_project(w.path);text=spice(p);checks=[]
    for d in p['cells'][0]['devices']:
        model=binding_for(p['pdk'],d)['model'];line=next(s for s in text.splitlines() if ' '+model+' ' in s);fields=line.split()
        assert fields[1:6]==[d['nets'][n] for n in ('c','b','e','s','t')];assert len(set(fields[1:6]))==5 and fields[5]!='0'
        params=dict(s.split('=',1) for s in fields[7:]);assert params['nx']=='4'
        if model!='npn13G2_5t':assert params['el']=='2.5'
        checks.append(dict(model=model,thermal_node=fields[5],parameters=params))
    assert len(checks)==3 and not errors,errors
    w.showNormal();w.resize(1440,930);QTest.qWait(50);assert w.grab().save(str(out/'thermal.png'));w.analysis_dirty=False;w.saved_hash=digest(w.project);w.close()
    report=dict(status='PASS',scope='Current-source desktop placement, parameter editing and saved five-terminal netlist. Not an installed release or numerical simulation.',revision=row['revision'],checks=checks,source_sha256=file_digest(__file__),saved_sha256=file_digest(out/'thermal.icproj'))
    (out/'report.json').write_bytes((json.dumps(report,indent=2)+'\n').encode());print(json.dumps(report),flush=True)


if __name__=='__main__':main()
