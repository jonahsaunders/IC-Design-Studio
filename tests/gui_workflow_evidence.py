"""UI regression using synthetic saved results, not engine qualification."""
import argparse,json,sys,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    from PySide6.QtCore import QSettings,QStandardPaths,Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication,QPushButton
    from icstudio.gui import Studio
    from icstudio.model import clone,design_digest,uid
    from icstudio.ring_oscillator import reference
    from icstudio.test_plans import prepare,sources
    from icstudio.getting_started import examples,example_copy
    from tests.test_silicon import technology
    app=QApplication([]);app.setStyle('Fusion')
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    w=Studio(recover=False);w.maybe_save=lambda:True;errors=[];w.error=lambda msg:errors.append(str(msg));w.live_check.setChecked(False)
    w.resize(1400,960);w.show()
    def wait(predicate):
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            QTest.qWait(20)
        raise AssertionError(errors)
    try:
        p,cid,bench_id=reference(technology());bench=p['testbenches'][0]
        bench['measurements']=[];bench['specifications']=[dict(name='Output',expression='final(V("out"))',min='0',max='1',unit='V')]
        plan=dict(id=uid(),name='Operating corners',entries=sources(p)[:1],corners=['nominal'],temperatures=[0,27,85],voltages=[])
        p['test_plans']=[plan];w.set_project(p);w.cid=cid;guide=w.design_workflow()
        wait(lambda:guide.analysis is not None)
        assert guide.plan.currentData()==plan['id']
        assert guide.evidence_states['electrical']['status']=='Not run'
        jobs=prepare(w.project,plan,lambda settings,engine,project,cid:dict(settings=settings,engine=engine,project=project,cell=cid,executable='ui-fixture'))
        def row(job):
            return dict(id=uid(),name='UI fixture',job=job,state='Complete',elapsed=0,progress=100,log='',process=None,
                result=dict(project_id=job['project']['id'],design_hash=design_digest(job['project']),
                            specifications=[dict(name='Output',status='PASS',value=.5)]))
        cases=[row(job) for job in jobs]
        electrical=row(dict(project=clone(w.project),cell=bench['bench_cell'],engine='ngspice',settings=dict(type='testbench',testbench=bench_id)))
        physical=row(dict(project=clone(w.project),cell=bench['bench_cell'],engine='ngspice',settings=dict(type='silicon',testbench=bench_id)))
        physical['result']['silicon_report']=dict(cell_id=cid,status='passed')
        w.run_manager.rows=[electrical,physical]+cases
        guide.refresh()
        assert all(s['status']=='Passed' for s in guide.evidence_states.values()),guide.evidence_states
        # Isolate completed-step navigation from this deliberately incomplete
        # layout fixture. Actual inventory inspection runs in gui_workflow_review.
        guide.analysis.update(inventory=dict(design_hash=design_digest(w.project),devices=[]),connections=[],constraints=[])
        guide.render();assert guide.next_action.text()=='Verification complete · optional team review'
        cases[-1]['result']['specifications'][0]['status']='FAIL';guide.render()
        assert guide.plan_state['status']=='Failed' and 'plan evidence' in guide.next_action.text()
        window=guide.open_plan_evidence()
        assert window.failed.isChecked() and window.table.currentItem().data(Qt.UserRole)==cases[-1]['id']
        window.grab().save(str(out/'failed-condition.png'));window.close()
        physical['result']['silicon_report']['status']='blocked';guide.render()
        assert guide.evidence_states['physical']['status']=='Blocked'
        retry=next(b for b in guide.steps.cellWidget(3,2).findChildren(QPushButton) if b.text()=='Rerun')
        assert retry.isEnabled()
        QTest.qWait(30)
        assert len(guide.steps.cellWidget(3,2).findChildren(QPushButton))==2
        physical['state']='Running';guide.render();assert guide.evidence_states['physical']['status']=='Running'
        physical['state']='Complete';physical['result']['silicon_report']['status']='passed'
        cases[-1]['result']['specifications'][0]['status']='PASS'
        w.commit(lambda q:q.update(name='Edited'),'Rename');wait(lambda:guide.analysis_key[1]==w.project['revision'])
        assert all(s['status']=='Stale' for s in guide.evidence_states.values())
        entry=next(e for e in examples() if e['id']=='gf180-banba-layout')
        w.set_project(example_copy(entry));w.cid=w.project['top'];guide.refresh();wait(lambda:guide.analysis is not None)
        assert 'Fill coupling' in guide.reference.toPlainText() and 'Blocked' in guide.reference.toPlainText()
        guide.tabs.setCurrentWidget(guide.reference);w.resizeDocks([w.workflow_dock],[440],Qt.Vertical)
        wait(lambda:guide.reference.isVisible());guide.grab().save(str(out/'reference-evidence.png'))
        gallery=w.start_here();gallery.search.setText('Lay out the Banba');assert 'Archived qualification' in gallery.details.toPlainText()
        gallery.grab().save(str(out/'gallery-qualification.png'));gallery.close()
        assert not errors,errors
        (out/'report.json').write_text(json.dumps(dict(status='passed',scope='Synthetic saved-result UI regression; no engine or consumer acceptance claim',
            checks=['Not run / Passed / Failed / Blocked / Running / Stale states','Completed flow reaches optional team review',
                    'Failed plan opens the exact operating condition','Failed physical flow offers rerun',
                    'Gallery and workflow share bounded reference status']),indent=2))
    finally:
        w.run_manager.rows=[];w.finish_recovery();w.close();app.processEvents()


if __name__=='__main__':main()
