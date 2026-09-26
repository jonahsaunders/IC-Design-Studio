"""Real Qt worker: verify, break, navigate, repair, invalidate and block."""
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
    for name in ('pdk','out'):ap.add_argument('--'+name,type=Path,required=True)
    for name in ('magic','netgen','ngspice'):ap.add_argument('--'+name,required=True)
    a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import digest,clone
    from icstudio.sky130_layout import reference_project,generate_inverter,layers
    from icstudio.layout import rect
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);errors=[];checks=[]
    w.error=lambda e:errors.append(str(e));w.maybe_save=lambda:True;w.jobs_dir=out/'runs with spaces'
    result=dict(status='failed',checks=checks,scope='Real source desktop with external physical engines; not an installed/frozen application test.')
    def wait(stage):
        deadline=time.monotonic()+240
        while w.process and time.monotonic()<deadline:QTest.qWait(100)
        if w.process:raise TimeoutError('Physical desktop worker exceeded its deadline.')
        if not w.result or not w.result.get('silicon_report'):raise AssertionError('Worker returned no physical report.')
        report=w.result['silicon_report']
        (out/(stage+'.json')).write_text(json.dumps(report,indent=2)+'\n')
        return report
    try:
        m=json.loads((a.pdk/'package.json').read_text());tech=m['technology']
        tech['package_root']=str(a.pdk.resolve());tech['package_lock']={'id':m['id'],'revision':m['revision'],'files':m['files']}
        p,cid=reference_project(tech);generate_inverter(p,cid)
        w.live_check.setChecked(False);w.set_project(p);w.cid=cid;w.refresh(True);w.resize(1400,960);w.show()
        for name in ('magic','netgen','ngspice'):w.settings.setValue('engine/'+name,getattr(a,name))
        w.run_silicon();r=wait('nominal');assert r['status']=='passed',r
        checks.append('Real queued DRC, LVS, extraction and before/after simulation pass')
        original=clone(w.cell['shapes'])
        def break_layout(project):
            c=next(c for c in project['cells'] if c['id']==cid)
            c['shapes'].append(rect(layers(tech)['m1'],10000,0,100,100))
        w.commit(break_layout,'Deliberate narrow-metal qualification fault');w.refresh_silicon()
        assert 'STALE' in w.silicon_status.text()
        checks.append('Editing invalidates the previous passing physical result')
        w.run_silicon();r=wait('defect');assert r['status']=='failed' and r.get('drc_count',0)>0,r
        rows=[i for i,v in enumerate(w.issues) if v.get('bbox')]
        assert rows,'DRC findings must have navigable physical coordinates'
        w.check_selected(rows[0],0);QTest.qWait(100)
        assert w.mode_combo.currentIndex()==1
        assert w.grab().save(str(out/'drc-finding.png'))
        checks.append('A deliberate defect fails DRC and clicking its finding navigates to geometry')
        w.undo();assert w.cell['shapes']==original
        w.run_silicon();r=wait('repaired');assert r['status']=='passed',r
        checks.append('Undo repairs the layout and a fresh verification passes')
        tools={name:getattr(a,name) for name in ('magic','netgen','ngspice')}
        tools['magic']=str(out/'missing magic executable')
        w.start_job({'type':'silicon','tools':tools});r=wait('missing-engine')
        assert r['status']=='blocked',r
        assert 'BLOCKED' in w.silicon_status.text()
        checks.append('A missing physical executable is shown as blocked, never passed')
        assert not errors,errors
        result['status']='passed'
    except Exception:result.update(error=traceback.format_exc(),errors=errors)
    finally:
        w.saved_hash=digest(w.project);w.close();app.processEvents()
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
