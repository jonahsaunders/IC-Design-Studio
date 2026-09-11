"""Actual desktop schematic gestures, review rendering, recovery and hierarchy."""
import argparse
import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QPointF,QSettings,QStandardPaths,Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication,QDialog
    from icstudio.gui import Studio
    from icstudio.live_client import LiveClient
    from icstudio.live_server import Server
    from icstudio.live_store import Store
    from icstudio.model import clone,uid
    from icstudio.team_review_ui import RevisionComparison
    from test_schematic_collaboration import circuit

    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'profile/settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);app.setStyle('Fusion')
    store=Store(out/'server.sqlite3','gui-schematic-key-'+'x'*32);server=Server(('127.0.0.1',0),store)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url='http://127.0.0.1:'+str(server.server_port)
    windows=[];checks=[]
    def wait(predicate,description,seconds=15):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            app.processEvents()
            if predicate():return
            QTest.qWait(20)
        raise AssertionError(description+' / '+' / '.join(w.live_client.message for w in windows if w.live_client))
    def idle(w):return not w.live_client.pending and not w.live_client.busy and w.live_client.connected
    def synchronized(revision):return all(idle(w) and w.live_client.revision==revision for w in windows)
    def point(canvas,x,y):return (QPointF(x,y)*canvas.scale+canvas.offset).toPoint()
    try:
        p=circuit();owner=store.create(store.create_key,p,'Alice');wid=owner['workspace']
        invite=store.invite(wid,owner['token'],'edit');editor=store.join(wid,invite['invite'],'Bob')
        for snapshot in (owner,editor):
            w=Studio(recover=False);w.maybe_save=lambda:True;w.error=lambda text:(_ for _ in ()).throw(AssertionError(text));w.live_check.setChecked(False)
            w.resize(1220,850);w.show();windows.append(w)
            w.live_attach(LiveClient(url,wid,snapshot['token'],snapshot,out/(snapshot['actor']+'.json'),w))
            w.mode_combo.setCurrentIndex(0);w._collaboration_dashboard.hide();w.schematic.fit()
        a,b=windows;wait(lambda:synchronized(0),'Initial sync')
        canvas=a.schematic;canvas.setFocus();QTest.keyClick(canvas,Qt.Key_W)
        QTest.mouseClick(canvas,Qt.LeftButton,pos=point(canvas,0,50));QTest.mouseClick(canvas,Qt.LeftButton,pos=point(canvas,500,50))
        QTest.keyClick(canvas,Qt.Key_Escape)
        wait(lambda:synchronized(1),'Draw wire between two components')
        assert a.cell['devices'][0]['nets']['n']==b.cell['devices'][1]['nets']['n']
        assert len(a.cell['wires'])==1
        checks.append('Mouse-drawn schematic wire and authoritative connectivity synchronize between desktop editors')
        initial=clone(a.project);ident=a.cell['devices'][0]['id'];a.select([ident],'schematic');a.move([ident],100,0,'schematic')
        wait(lambda:synchronized(2),'Move connected device')
        assert [100,50] in b.cell['wires'][0]['points']
        a.select([],'schematic');b.select([],'schematic')
        b.commit(lambda p:p['cells'][0]['devices'][1].update(value='22k'),'Change R2 value')
        wait(lambda:synchronized(3),'Remote property edit')
        a.undo();wait(lambda:synchronized(4),'Personal schematic undo')
        assert b.cell['devices'][0]['x']==0 and b.cell['devices'][1]['value']=='22k'
        assert b.cell['wires']==initial['cells'][0]['wires']
        checks.append('Device moves stretch wires atomically; personal undo preserves a teammate’s parameter edit')
        client=a.live_client;client.presence=lambda:dict(cell=a.cid,view='schematic',selection=[ident],cursor=[0,0])
        wait(lambda:any(p['id']==client.info['actor'] and p.get('view')=='schematic' for p in b.schematic.live_presence),'Schematic presence')
        b.schematic.grab().save(str(out/'schematic-presence.png'))
        dashboard=b.collaboration_dashboard(1);wait(lambda:b.live_people.count()==2,'Participant list')
        item=next(b.live_people.item(i) for i in range(b.live_people.count()) if b.live_people.item(i).data(Qt.UserRole)['id']==client.info['actor'])
        b.live_go_to_person(item);assert b.mode_combo.currentIndex()==0 and b.cid==a.cid
        client.presence=a.live_presence_data;a.select([],'schematic');b.select([],'schematic')
        wait(lambda:not store.sync(wid,owner['token'])['leases'],'Release reservations')
        checks.append('Schematic cursors, selections and participant navigation use the correct cell and view')
        comparison=RevisionComparison(a,initial,a.project);comparison.show();QTest.qWait(150)
        assert comparison.view_mode.currentIndex()==1 and all(v.scene_model.items() for v in comparison.views)
        assert any('22k' in comparison.table.topLevelItem(i).text(2) for i in range(comparison.table.topLevelItemCount()))
        comparison.grab().save(str(out/'schematic-revisions.png'));comparison.close()
        checks.append('Revision review renders complete schematics with changed values and connections')
        panel=a.collaboration_dashboard(3).review_panel
        wait(lambda:not panel.busy and panel.loaded_version is not None and idle(a),'Review ready')
        with patch('icstudio.team_review_ui.QInputDialog.getText',return_value=('Wired schematic',True)):panel.create()
        wait(lambda:not panel.busy and panel.checkpoints.count()==1,'Checkpoint saved')
        a.select([ident],'schematic');panel.anchor.setChecked(True);panel.anchor_kind.setCurrentText('Terminal');panel.comment.setPlainText('Check this terminal connection')
        with patch('icstudio.team_review_ui.QInputDialog.getItem',side_effect=lambda *args: (args[3][0],True)):panel.post_comment()
        wait(lambda:not panel.busy and panel.comments.topLevelItemCount()==1,'Terminal comment')
        panel.comments.setCurrentItem(panel.comments.topLevelItem(0));panel.navigate();assert a.selection==[ident]
        a._collaboration_dashboard.hide();a.select([],'schematic');wait(lambda:idle(a) and idle(b),'Review finished')
        checks.append('Checkpoint review accepts terminal comments and navigates back to their schematic objects')
        b.live_client.timer.stop();wait(lambda:not b.live_client.busy,'Pause remote polls')
        a.commit(lambda p:p['cells'][0]['devices'][0].update(value='15k'),'Alice R1 change');wait(lambda:idle(a) and a.live_client.revision==5,'First conflicting edit')
        b.commit(lambda p:p['cells'][0]['devices'][0].update(value='18k'),'Bob R1 proposal')
        wait(lambda:b.live_client.conflict is not None,'Retain conflicting schematic proposal');b.live_client.timer.start()
        wait(lambda:idle(b) and b.live_client.revision==5,'Fetch shared revision for conflict')
        b.live_review_conflict();dialog=b._live_conflict_review;QTest.qWait(150)
        assert dialog.view_mode.currentIndex()==1 and all(v.scene_model.items() for v in dialog.views)
        assert not dialog.reapply_button.isEnabled()
        dialog.grab().save(str(out/'schematic-conflict.png'));dialog.close();b.live_discard_conflict()
        checks.append('Overlapping component edits retain a three-way schematic comparison without overwriting values')
        wait(lambda:synchronized(5),'Ready for lost acknowledgement')
        original=a.live_client.transport.post;lost=[]
        def lose_ack(server,path,token,data,callback):
            def complete(status,result):
                if path.endswith('/edit') and status==200 and not lost:lost.append(data['id']);callback(0,{'error':'Lost acknowledgement'})
                else:callback(status,result)
            return original(server,path,token,data,complete)
        a.live_client.transport.post=lose_ack
        a.commit(lambda p:p['cells'][0]['devices'][0].update(value='16k'),'Retained schematic edit')
        wait(lambda:bool(lost) and a.live_client.pending is not None and not a.live_client.busy,'Lost schematic acknowledgement')
        old=a.live_client;old.timer.stop();old.active=False;journal=old.journal;a.live_client=None
        resumed=LiveClient.resume(journal,a);a.live_attach(resumed);a._collaboration_dashboard.hide()
        wait(lambda:synchronized(6),'Resume schematic journal')
        assert a.cell['devices'][0]['value']=='16k' and len(store.db.execute('SELECT * FROM events WHERE request=?',(lost[0],)).fetchall())==1
        checks.append('Restarting a desktop client retries a saved schematic transaction exactly once')
        child=uid();a.commit(lambda p:p['cells'].append(dict(id=child,name='child',ports=[],devices=[],shapes=[])),'Create shared cell')
        wait(lambda:synchronized(7),'Create shared child cell');b.cid=child;b.refresh(True)
        a.commit(lambda p:p.update(cells=[c for c in p['cells'] if c['id']!=child]),'Delete shared child cell')
        wait(lambda:synchronized(8),'Delete shared child cell');assert b.cid==b.project['top']
        checks.append('Hierarchy creation/deletion synchronizes and a teammate viewing a deleted cell returns to the top cell')
        modal=QDialog(a);modal.setWindowModality(Qt.WindowModal);modal.show();QTest.qWait(30)
        assert not a.live_can_install()
        b.commit(lambda p:p['cells'][0]['devices'][1].update(value='24k'),'Edit while teammate reviews a dialog')
        wait(lambda:idle(b) and b.live_client.revision==9,'Remote edit during modal dialog')
        assert a.live_client.revision==8
        modal.accept();wait(lambda:synchronized(9),'Install remote edit after modal dialog closes')
        checks.append('Modal symbol/settings dialogs retain their starting revision until closed')
        (out/'report.json').write_text(json.dumps(dict(checks=checks,status='passed'),indent=2));print(json.dumps(checks))
    finally:
        for w in windows:
            if w.live_client:w.live_leave()
            w.close()
        QTest.qWait(100);server.shutdown();server.server_close();thread.join(5);store.close()


if __name__=='__main__':main()
