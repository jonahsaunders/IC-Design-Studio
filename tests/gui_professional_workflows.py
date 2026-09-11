"""Real desktop acceptance for precise editing, queued test plans and workflow guidance."""
import argparse,json,os,sys,time,traceback,threading
from pathlib import Path
from unittest.mock import patch


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QSettings,QStandardPaths,QPointF,Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from icstudio.gui import Studio
    from icstudio.model import example,clone,uid,design_digest
    from icstudio.layout import rect
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'profile/settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.maybe_save=lambda:True
    errors=[];w.error=lambda text:errors.append(str(text));w.live_check.setChecked(False);w.show();checks=[];server=store=None
    def wait(predicate,description,timeout=20):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            QTest.qWait(20)
        raise AssertionError(description+' / '+str(errors))
    try:
        p=example('rc');c=p['cells'][0]
        c['shapes']=[rect('metal1',0,0,1000,1000),rect('metal2',0,0,1000,1000)]
        second=clone(c['devices'][1]);second.update(id=uid(),name='R2');c['devices'].append(second)
        c['specifications']=[dict(name='Output range',expression='final(V("vout"))',min='0',max='2',unit='V')]
        p['simulation_setups']=[dict(name=title,cell=c['id'],engine='builtin',settings={**clone(p['analysis']),'type':kind}) for title,kind in [('Bias','op'),('Settling','tran')]]
        w.set_project(p);w.connected_layout_action.setChecked(False);w.mode_combo.setCurrentIndex(1);w.select([c['shapes'][0]['id']],'layout')
        before=clone(w.project);dialog=w.precise_move();dialog.x.setText('2');dialog.preview_button.click();app.processEvents()
        assert w.layout.moving and w.project==before
        dialog.reject();assert not w.layout.moving and w.project==before
        dialog=w.precise_move();dialog.x.setText('0.003');dialog.apply_button.click();assert w.project==before and 'multiple' in dialog.status.text()
        dialog.x.setText('2');dialog.apply_button.click();assert w.cell['shapes'][0]['points'][0]==[2000,0]
        w.undo();assert w.project['cells']==before['cells'];w.redo();assert w.cell['shapes'][0]['points'][0]==[2000,0]
        dialog=w.precise_move();dialog.x.setText('1');dialog.preview_button.click();w.commit(lambda q:q.update(name='New revision'),'Rename project')
        wait(lambda:not dialog.apply_button.isEnabled(),'A stale numeric preview remained applicable');assert not w.layout.moving;dialog.reject()
        checks.append('Numeric move previews and cancellation preserve the document; apply, undo, redo and stale-selection protection work')
        w.mode_combo.setCurrentIndex(0);w.select([],'schematic');w.schematic.fit();QTest.qWait(80)
        pos=QPointF(second['x'],second['y'])*w.schematic.scale+w.schematic.offset
        assert len(w.schematic.capture_candidates(w.schematic.model(pos)))>=2,[(d['name'],d['x'],d['y']) for d in w.cell['devices']]
        QTest.mouseClick(w.schematic,Qt.LeftButton,Qt.AltModifier,pos.toPoint());first=list(w.selection)
        QTest.mouseClick(w.schematic,Qt.LeftButton,Qt.AltModifier,pos.toPoint());assert first and w.selection and first!=w.selection,(first,w.selection)
        checks.append('Alt-click cycles overlapping schematic objects through actual pointer events')
        window=w.test_plan_window();editor=window.edit();editor.name.setText('Desktop acceptance');editor.temperatures.setText('0, 27');editor.save()
        assert not editor.isVisible() and len(w.project['test_plans'])==1,editor.error.text()
        base=design_digest(w.project);window.run()
        wait(lambda:len(w.run_manager.rows)==4 and all(r['state'] in ('Complete','Failed') for r in w.run_manager.rows),'The four real simulation jobs did not complete')
        assert all(r['state']=='Complete' for r in w.run_manager.rows),[(r['state'],r.get('log','')) for r in w.run_manager.rows]
        window.refresh();assert window.table.rowCount()==2 and window.table.columnCount()==4
        assert all('PASS' in window.table.item(i,j).text() for i in range(2) for j in (2,3)),[[window.table.item(i,j).text() for j in (2,3)] for i in range(2)]
        assert design_digest(w.project)==base;window.grab().save(str(out/'test-plan-matrix.png'))
        first_group=window.runs.currentData();window.run();wait(lambda:len(w.run_manager.rows)==8 and all(r['state']=='Complete' for r in w.run_manager.rows),'Baseline comparison jobs failed')
        window.refresh();window.baseline.setCurrentIndex(window.baseline.findData(first_group))
        assert all('Δ +0' in window.table.item(i,j).text() for i in range(2) for j in (2,3))
        window.delete();assert not w.project['test_plans'];w.undo();assert w.project['test_plans']
        checks.append('Saved multi-test plan executes four independent jobs, shows exact-requirement baselines and can be deleted and restored')
        guide=w.design_workflow();assert guide.steps.rowCount()==6;guide.grab().save(str(out/'design-workflow.png'))
        w.commit(lambda q:q.update(name='Changed after checks'),'Rename');guide.mark_changed();assert all(guide.steps.item(i,1).text()=='Refresh required' for i in range(6))
        guide.close();window.close();w.finish_recovery()
        from icstudio.live_store import Store
        from icstudio.live_server import Server
        from icstudio.live_client import LiveClient
        store=Store(out/'review/server.sqlite3','acceptance-'+'x'*40)
        server=Server(('127.0.0.1',0),store);threading.Thread(target=server.serve_forever,daemon=True).start()
        shared=store.create('acceptance-'+'x'*40,w.project,'Reviewer')
        client=LiveClient('http://127.0.0.1:'+str(server.server_port),shared['workspace'],shared['token'],shared,out/'review/session.json',w);w.live_attach(client)
        job=w.prepare_simulation({**clone(w.project['analysis']),'type':'op'},'builtin')
        row=w.run_manager.enqueue(job,w.jobs_dir,'Shared operating point');wait(lambda:row['state']=='Complete','Shared result did not simulate')
        dashboard=w.collaboration_dashboard();dashboard.tabs.setCurrentIndex(3);panel=dashboard.review_panel
        wait(lambda:not panel.busy and panel.loaded_version is not None and not client.busy,'Review panel did not connect')
        with patch('icstudio.team_review_ui.QInputDialog.getText',return_value=('Verified input',True)):panel.create()
        wait(lambda:not panel.busy and panel.checkpoints.count()==1,'Verified checkpoint did not persist')
        completed=[r for r in w.run_manager.rows if r['state']=='Complete' and r.get('result')];choice=str(completed.index(row)+1)+' · '+row['name']
        with patch('icstudio.team_review_ui.QInputDialog.getItem',return_value=(choice,True)):panel.share_report()
        wait(lambda:not panel.busy and panel.reports.count()==1,'Saved input and result were not shared')
        size=len(w.run_manager.rows);panel.rerun_report()
        wait(lambda:len(w.run_manager.rows)==size+1 and w.run_manager.rows[-1]['state']=='Complete','Teammate result was not reproduced with local tools')
        assert w.run_manager.rows[-1]['result']['traces']==row['result']['traces']
        assert w.run_manager.rows[-1]['job']['shared_origin']['input_hash']==row['result']['design_hash']
        checks.append('A real simulation is shared with its immutable checkpoint and reproduced through HTTP using local tools')
        dashboard.close();w.live_leave()
        assert not errors,errors;report=dict(status='passed',checks=checks)
    except Exception:report=dict(status='failed',checks=checks,traceback=traceback.format_exc())
    finally:
        w.run_manager.cancel([r for r in w.run_manager.rows if r['state'] in ('Queued','Running')]);w.close();app.processEvents()
        if server:server.shutdown();server.server_close()
        if store:store.close()
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
