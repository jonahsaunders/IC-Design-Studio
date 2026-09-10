"""Two desktop editors, hierarchy ECO and million-instance overview acceptance."""
import argparse,json,os,sys,time
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_CONFIG_HOME']=str(out/'profile/config');os.environ['XDG_DATA_HOME']=str(out/'profile/data');sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QPointF,Qt,QSettings
    from PySide6.QtWidgets import QApplication,QDialogButtonBox
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import example,clone,device,digest
    from icstudio.layout import rect
    from icstudio.layout_scene import LayoutScene
    from icstudio.layout_collaboration import Session
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'profile/settings'))
    app=QApplication([]);app.setStyle('Fusion');windows=[];checks=[]
    try:
        for _ in range(2):
            w=Studio(recover=False);w.maybe_save=lambda:True;w.live_check.setChecked(False);w.show();windows.append(w)
        a,b=windows;p=example('empty');a.set_project(p);b.set_project(p);cid=p['top']
        a.layout_session=Session.create(out/'shared',a.project,'Alice');b.layout_session=Session.join(out/'shared','Bob');a.layout_session.claim(cid,['metal1']);b.layout_session.claim(cid,['metal2'])
        a.commit(lambda p:p['cells'][0]['shapes'].append(rect('metal1',0,0,600,600)),'Alice route');b.commit(lambda p:p['cells'][0]['shapes'].append(rect('metal2',1000,0,600,600)),'Bob route')
        a.shared_layout_publish();b.shared_layout_refresh();b.shared_layout_publish();a.shared_layout_refresh()
        assert a.project['cells']==b.project['cells'];assert len(a.cell['shapes'])==2
        a.shared_layout_dialog();a._collaboration_dialog.grab().save(str(out/'concurrent-ownership.png'));a._collaboration_dialog.close()
        checks.append(dict(name='two_desktop_sessions_merge_same_cell_disjoint_layers',status='passed'))
        for w in windows:w.shared_layout_leave()
        p=example('empty');c=p['cells'][0];c['devices']=[device('R','R1',value='1k',nets={'p':'a','n':'b'})];a.set_project(p)
        dlg=a.layout_eco_dialog();QTest.qWait(30);dlg.table.item(0,0).setCheckState(Qt.Checked);dlg.grab().save(str(out/'schematic-driven-review.png'));dlg.preview_button.click();QTest.qWait(30)
        review=a._review_dialog;apply=review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply);assert apply.isEnabled();apply.click();QTest.qWait(30)
        assert a.cell['parametric_devices'];a.undo();assert not a.cell.get('parametric_devices');a.redo();assert a.cell['parametric_devices']
        checks.append(dict(name='selected_schematic_layout_preview_apply_undo_redo',status='passed'))
        p=example('empty');top=p['cells'][0];master=dict(id='master',name='master',ports=[],devices=[],shapes=[rect('metal1',0,0,600,600)])
        p['cells'].append(master);top['layout_instances']=[dict(id='array',name='array',cell='master',x=0,y=0,nx=1000,ny=1000,a=[2000,0],b=[0,2000])]
        start=time.perf_counter();a.set_project(p);a.mode_combo.setCurrentIndex(1);a.layout.fit();QTest.qWait(30);a.layout.grab();scene=a.layout.cell['_layout_scene']
        assert scene.stats['detail_reduced'];assert scene.expanded_count==1000000;assert scene.stats['master_shapes']==1
        a.grab().save(str(out/'million-instance-overview.png'));elapsed=time.perf_counter()-start
        a.layout.auto_fit=False;a.layout.scale=.5;a.layout.offset=QPointF(60,60);a.layout.grab()
        assert not scene.stats['detail_reduced'];assert a.layout.editor_hit(QPointF(300,300))['id']=='array';a.grab().save(str(out/'million-instance-detail.png'))
        checks.append(dict(name='million_instances_bounded_overview_and_exact_pick',status='passed',overview_seconds=elapsed,master_shapes=1,expanded_shapes=1000000))
        (out/'report.json').write_text(json.dumps(dict(status='passed',qt_platform=app.platformName(),checks=checks),indent=2));print(json.dumps(checks))
    finally:
        for w in windows:
            w.maybe_save=lambda:True;w.close()
        app.processEvents()


if __name__=='__main__':main()
