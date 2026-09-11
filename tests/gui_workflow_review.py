"""Desktop acceptance for workflow context, linked change review and reviewer threads."""
import argparse,json,sys,time,threading,traceback
from pathlib import Path
from unittest.mock import patch


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QSettings,QStandardPaths,Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication,QPushButton,QDialogButtonBox
    from icstudio.gui import Studio
    from icstudio.model import example,clone,uid,device
    from icstudio.parametric import install
    from icstudio.live_store import Store
    from icstudio.live_server import Server
    from icstudio.live_client import LiveClient
    from icstudio.live_protocol import LiveError
    from icstudio.ring_oscillator import reference
    from test_silicon import technology
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);app.setStyle('Fusion');windows=[];checks=[];errors=[];store=server=None
    def window():
        w=Studio(recover=False);w.maybe_save=lambda:True;w.error=lambda message:errors.append(str(message));w.live_check.setChecked(False);w.resize(1220,850);w.show();windows.append(w);return w
    def wait(predicate,label,seconds=20):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            app.processEvents()
            if predicate():return
            QTest.qWait(20)
        raise AssertionError(label+' / '+str(errors))
    try:
        w=window();assert QTest.qWaitForWindowExposed(w);QTest.qWait(200)
        p,cid,first=reference(technology());second=clone(p['testbenches'][0]);second.update(id=uid(),name='hot_corner');second['analysis']['temperature']=85;p['testbenches'].append(second)
        w.set_project(p);w.cid=cid;w._selected_testbench=second['id'];w.refresh(True)
        guide=w.design_workflow();wait(lambda:guide.analysis is not None,'Initial automatic checks')
        assert not guide.analysis.get('error'),guide.analysis
        assert guide.testbench.currentData()==second['id'] and '85' in guide.corner.text()
        w.mode_combo.setCurrentIndex(0);w.design_workflow();assert w._design_workflow is guide and guide.testbench.currentData()==second['id']
        w.mode_combo.setCurrentIndex(1);w.design_workflow();assert guide.testbench.currentData()==second['id']
        guide.testbench.setCurrentIndex(guide.testbench.findData(first));assert w._selected_testbench==first
        w.commit(lambda q:q.update(name='Renamed while workflow open'),'Rename')
        wait(lambda:guide.analysis_key and guide.analysis_key[1]==w.project['revision'],'Automatic revision refresh')
        assert guide.testbench.currentData()==first
        assert any(a.text()=='Design workflow…' for a in w.task_menus['Schematic'].actions())
        assert any(a.text()=='Design workflow…' for a in w.task_menus['Layout'].actions())
        guide.grab().save(str(out/'workflow-context.png'));guide.close()
        checks.append('Both editors share automatic workflow checks and an explicit testbench/corner that survives edits')

        p=example('empty');c=p['cells'][0];d=device('R','Rbias',200,200,value='1k',nets={'p':'bias','n':'0'});c['devices']=[d]
        install(p,c['id'],d['id'],{});w.set_project(p);w.commit(lambda q:q['cells'][0]['devices'][0].update(value='2k'),'Resize resistor')
        review=w.layout_eco_dialog();review.table.selectRow(0);assert 'bias' in review.impact.text() and '2k' in review.impact.text()
        review.schematic_button.click();assert w.mode_combo.currentIndex()==0 and d['id'] in w.selection
        review.physical_button.click();assert w.mode_combo.currentIndex()==1 and len(w.selection)>1
        before=clone(w.project);review.table.item(0,0).setCheckState(Qt.Checked);review.preview_button.click()
        apply_dialog=w._review_dialog;assert apply_dialog.isVisible()
        compare=next(b for b in apply_dialog.findChildren(QPushButton) if b.text()=='Inspect geometry before and after');compare.click()
        comparison=w._eco_comparison;QTest.qWait(100);assert comparison.table.topLevelItemCount()>0
        assert all(v.scene_model.items() for v in comparison.views)
        comparison.grab().save(str(out/'eco-comparison.png'));comparison.close()
        buttons=apply_dialog.findChild(QDialogButtonBox);buttons.button(QDialogButtonBox.Apply).click()
        assert not apply_dialog.isVisible() and w.project['cells']!=before['cells'],errors
        updated=clone(w.project['cells']);w.undo();assert w.project['cells']==before['cells'];w.redo();assert w.project['cells']==updated
        checks.append('Device impact links both views; a geometry preview applies as one undoable transaction')
        stale=w.layout_eco_dialog();w.commit(lambda q:q.update(name='Changed with review open'),'Rename')
        wait(lambda:not stale.preview_button.isEnabled(),'Stale ECO preview remained available');stale.close()
        checks.append('An open change review blocks preview after its source revision changes')
        w.finish_recovery()

        store=Store(out/'server.sqlite3','desktop-review-'+'x'*40);server=Server(('127.0.0.1',0),store)
        threading.Thread(target=server.serve_forever,daemon=True).start();url='http://127.0.0.1:'+str(server.server_port)
        owner=store.create(store.create_key,w.project,'Designer');inv=store.invite(owner['workspace'],owner['token'],'review');reviewer=store.join(owner['workspace'],inv['invite'],'Reviewer')
        b=window()
        for target,snapshot in ((w,owner),(b,reviewer)):
            target.live_attach(LiveClient(url,owner['workspace'],snapshot['token'],snapshot,out/(snapshot['actor']+'.json'),target))
            target.collaboration_dashboard(3)
        panel=w._collaboration_dashboard.review_panel;other=b._collaboration_dashboard.review_panel
        wait(lambda:all(not v.live_client.busy for v in windows) and not panel.busy and panel.loaded_version is not None,'Review connection')
        with patch('icstudio.team_review_ui.QInputDialog.getText',return_value=('Ready for review',True)):panel.create()
        wait(lambda:not panel.busy and panel.checkpoints.count()==1 and not other.busy and other.checkpoints.count()==1,'Checkpoint visibility')
        other.refresh_state();assert other.comment_button.isEnabled() and other.decision_button.isEnabled()
        assert not other.add_button.isEnabled() and not other.share_button.isEnabled()
        original=clone(b.project)
        try:b.live_client.editable();raise AssertionError('Reviewer received edit permission')
        except LiveError:pass
        other.comment.setPlainText('Please check the bias connection.');other.comment_button.click()
        wait(lambda:not other.busy and other.comments.topLevelItemCount()==1 and not panel.busy and panel.comments.topLevelItemCount()==1,'Reviewer comment')
        panel.comments.setCurrentItem(panel.comments.topLevelItem(0));panel.reply_button.click();panel.comment.setPlainText('The connection is preserved in this revision.');panel.comment_button.click()
        wait(lambda:not other.busy and other.comments.topLevelItem(0).childCount()==1,'Threaded reply')
        assert b.project==original
        other.comments.setCurrentItem(other.comments.topLevelItem(0).child(0));other.resolve_button.click()
        wait(lambda:not other.busy and other.comments.topLevelItem(0).text(2)=='resolved','Resolve complete discussion')
        other.resolve_button.click();wait(lambda:not other.busy and other.comments.topLevelItem(0).text(2)=='open','Reopen discussion')
        other.decision.setCurrentIndex(other.decision.findData('approved'));other.decision_button.click()
        wait(lambda:not other.busy and 'approved' in other.decisions.text(),'Reviewer approval')
        b._collaboration_dashboard.grab().save(str(out/'reviewer-threads.png'))
        assert all(not lease['actor']==reviewer['actor'] for lease in store.sync(owner['workspace'],owner['token'])['leases'])
        checks.append('Two HTTP-connected desktops support reviewer comments, threaded replies, resolve/reopen and approvals without design edits')
        assert not errors,errors;result=dict(status='passed',checks=checks)
    except Exception:result=dict(status='failed',checks=checks,traceback=traceback.format_exc(),errors=errors)
    finally:
        for w in windows:
            if w.live_client:w.live_client.active=False;w.live_client.timer.stop();w.live_client=None
            w.close()
        app.processEvents()
        if server:server.shutdown();server.server_close()
        if store:store.close()
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
