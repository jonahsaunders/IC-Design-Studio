"""Exercise public-design DRC/LVS through the actual desktop action and worker."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('evidence','pdk','out'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--managed',action='store_true')
    for name in ('magic','netgen'):ap.add_argument('--'+name,default='')
    a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import clone,digest,load_project
    from icstudio.layout import rect
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([])
    if sys.platform=='win32' and app.platformName()=='offscreen':
        from PySide6.QtGui import QFontDatabase
        for name in ('segoeui.ttf','segoeuib.ttf','seguisb.ttf','consola.ttf'):
            QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name))
    w=Studio(recover=False);w.live_check.setChecked(False);w.resize(1500,1000)
    errors=[];checks=[];w.error=lambda e:errors.append(str(e));w.maybe_save=lambda:True;w.jobs_dir=out/'runs with spaces'
    w.settings.setValue('physical/toolchain','included' if a.managed else 'custom')
    for name in ('magic','netgen'):w.settings.setValue('engine/'+name,getattr(a,name))
    result=dict(status='failed',checks=checks,platform=sys.platform,frozen=bool(getattr(sys,'frozen',False)),scope='Source Qt desktop and real queued external DRC/LVS engines.')
    from icstudio.build_identity import identity
    result['build']=identity()
    def wait(name):
        deadline=time.monotonic()+600
        while w.process and time.monotonic()<deadline:QTest.qWait(100)
        if w.process:raise TimeoutError('Desktop verification exceeded ten minutes.')
        if not w.result or not w.result.get('silicon_report'):raise AssertionError('The desktop action returned no physical report.')
        r=w.result['silicon_report'];(out/(name+'.json')).write_text(json.dumps(r,indent=2)+'\n')
        if a.managed:assert r.get('execution',{}).get('runtime',{}).get('kind')==('wsl' if os.name=='nt' else 'linux'),r
        return r
    try:
        rows=json.loads((a.evidence/'desktop-cases.json').read_text())
        assert len(rows)==4,'All three original circuits and the explicit amplifier repair must be available.'
        for row in rows:
            p=load_project(a.evidence/row['project']);p['pdk']['package_root']=str(a.pdk.resolve())
            w.set_project(p);w.cid=p['top'];w.refresh(True);w.mode_combo.setCurrentIndex(1);w.show()
            w.simple_form=lambda *args,row=row,**kwargs:{'Schematic SPICE file':str((a.evidence/row['reference']).resolve()),'Schematic cell':row['top']}
            w.result=None;w.command_actions['Run layout DRC / LVS only…'].trigger();r=wait(row['name'])
            assert r['status']==row['expected'],r
            assert r['mode']=='drc_lvs' and r['drc_count']==0,r
            assert row['expected'].upper() in w.silicon_status.text()
            checks.append(dict(name=row['name'],status=r['status'],drc=r['drc_count']))
            QTest.qWait(100);assert w.grab().save(str(out/(row['name']+'.png')))
            if row['name']=='comparator':
                original=clone(w.cell['shapes']);metal=next(l['name'] for l in p['pdk']['layers'] if (l['gds'],l['datatype'])==(68,20))
                w.commit(lambda q:next(c for c in q['cells'] if c['id']==q['top'])['shapes'].append(rect(metal,1000000,1000000,100,100)),'Deliberate DRC width fault')
                w.refresh_silicon();assert 'STALE' in w.silicon_status.text()
                w.command_actions['Run layout DRC / LVS only…'].trigger();r=wait('comparator-defect')
                assert r['status']=='failed' and r['drc_count']>0,r
                finding=next(i for i,x in enumerate(w.issues) if x.get('bbox'))
                w.check_selected(finding,0);QTest.qWait(100);assert w.mode_combo.currentIndex()==1
                assert w.grab().save(str(out/'drc-finding.png'))
                w.undo();assert w.cell['shapes']==original
                w.command_actions['Run layout DRC / LVS only…'].trigger();r=wait('comparator-repaired');assert r['status']=='passed',r
                checks.append(dict(name='edit-invalidates-defect-navigates-undo-repairs',status='passed'))
        assert not errors,errors
        result['status']='passed'
    except Exception:result.update(error=traceback.format_exc(),errors=errors)
    finally:
        w.saved_hash=digest(w.project);w.close();app.processEvents()
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
