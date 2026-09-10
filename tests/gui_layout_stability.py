"""Real Qt drawing and recovery-failure UX; durable success is a separate gate."""
import argparse,errno,json,os,sys,traceback
from pathlib import Path
from unittest.mock import patch


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_CONFIG_HOME']=str(out/'qt-profile/config');os.environ['XDG_DATA_HOME']=str(out/'qt-profile/data')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QPointF,QSettings
    from PySide6.QtWidgets import QApplication
    from icstudio.canvas import Canvas
    from icstudio.gui import Studio
    from icstudio.model import example,clone,digest
    from icstudio.layout import rect
    from icstudio.layout_scene import LayoutScene
    from icstudio.build_info import WORKFLOW_SOURCE_HASH
    from icstudio import __version__
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'qt-profile/settings'))
    app=QApplication([]);app.setStyle('Fusion');checks=[];w=None;canvas=None
    try:
        p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',(i%100)*1000,(i//100)*1000,600,600) for i in range(10000)]
        canvas=Canvas('layout');canvas.resize(900,650);canvas.show();app.processEvents();canvas.auto_fit=False;canvas.scale=.1;canvas.offset=QPointF(20,20);canvas.set_data(c,p['pdk']);canvas.grab()
        built=sum(v.value is not None for v in canvas._geometry_cache.paths);assert 0<built<500,built
        assert canvas.editor_hit(QPointF(300,300))['id']==c['shapes'][0]['id']
        canvas.offset=QPointF(-8000,-8000);canvas.grab();assert sum(v.value is not None for v in canvas._geometry_cache.paths)>built
        checks.append({'name':'deferred_visible_paths_and_picking','status':'passed','initial_paths_built':built,'total_shapes':10000})
        p=example('empty');top=p['cells'][0]
        master={'id':'master','name':'master','ports':[],'devices':[],'shapes':[rect('metal1',0,0,600,600),rect('metal2',200,200,600,600)]};p['cells'].append(master)
        top['layout_instances']=[{'id':'array','name':'array','cell':'master','x':0,'y':0,'nx':30,'ny':30,'a':[1000,0],'b':[100,1000],'rotation':90,'mirror':True}]
        scene=LayoutScene().update(p,top['id']);canvas.offset=QPointF(80,80);canvas.scale=.04;canvas.set_data({**top,'_layout_scene':scene},p['pdk'],['array']);canvas.anchor=QPointF(0,0);canvas.moving=True
        for dark in (False,True):
            canvas.dark=dark
            for pattern in ('Solid','Hatch'):
                canvas.layer_styles={'metal1':{'pattern':pattern}}
                for delta in (QPointF(5,5),QPointF(200,300),QPointF(2500,1000),QPointF(-6000,5000),QPointF(12000,-2500)):
                    canvas.drag=delta;canvas.cache_layout_pictures=False;expected=canvas.grab().toImage();canvas.cache_layout_pictures=True
                    actual=canvas.grab().toImage()
                    if actual!=expected:
                        actual.save(str(out/'pixel-actual.png'));expected.save(str(out/'pixel-expected.png'))
                    assert actual==expected,'Array drag changed pixels at '+str((dark,pattern,delta))
        canvas.grab().save(str(out/'array-drag.png'));checks.append({'name':'array_drag_pixel_equivalence_across_cache_boundaries','status':'passed'});canvas.close();canvas=None
        w=Studio(recover=False);w.maybe_save=lambda:True;errors=[];w.error=lambda message:errors.append(str(message));w.live_check.setChecked(False);w.show()
        p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',0,0,600,600),rect('metal2',5000,2000,600,600)];w.set_project(p);w.recovery_dir=out/'recovery';w.recovery_dir.mkdir(exist_ok=True)
        target=w.recovery_dir/(w.project['id']+'.icproj');target.write_text(json.dumps(w.project));prior=target.read_bytes()
        with patch('os.fsync',side_effect=OSError(errno.EIO,'injected failing storage')) as sync:
            w.arrange_layout(w.cid,[s['id'] for s in w.cell['shapes']],'bottom')
            assert target.read_bytes()==prior;assert w.cell['shapes'][1]['points'][0][1]==0
            for fn in (w.refresh,w.undo,w.redo,w.refresh,w.retry_recovery):fn();assert 'recovery failed' in w.save_label.text()
            assert sync.call_count==4,sync.call_count
            assert len(errors)==1,errors
            roots=(w.recovery_dir,w.recovery_root,w.settings.value('storage/recovery_root'))
            try:w.use_recovery_folder(out/'other-recovery')
            except OSError:pass
            else:raise AssertionError('Failed destination was accepted')
            assert roots==(w.recovery_dir,w.recovery_root,w.settings.value('storage/recovery_root'))
            assert target.read_bytes()==prior
        checks.append({'name':'failed_recovery_survives_refresh_undo_redo_retry_and_folder_rejection','status':'passed','injected_failure':True})
        w.grab().save(str(out/'recovery-failed.png'));errors.clear()
        # No injected success and no fsync replacement in this acceptance gate.
        success=w.retry_recovery()
        checks.append({'name':'actual_durable_recovery_retry','status':'passed' if success else 'blocked','error':w._recovery_error})
        if success:
            from icstudio import recovery
            restored,_=recovery.read(target);assert restored['cells']==w.project['cells']
            assert 'recovery available' in w.save_label.text()
            assert w.use_recovery_folder(out/'healthy-recovery')
        report={'status':'partial' if not success else 'passed','checks':checks}
    except Exception:report={'status':'failed','checks':checks,'exception':traceback.format_exc()}
    finally:
        if canvas:canvas.close()
        if w:w.saved_hash=digest(w.project);w.close();app.processEvents()
    report.update(version=__version__,workflow_hash=WORKFLOW_SOURCE_HASH,qt_platform=app.platformName())
    (out/'gui-stability.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return 1 if report['status']=='failed' else 0


if __name__=='__main__':raise SystemExit(main())
