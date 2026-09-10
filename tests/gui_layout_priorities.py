"""Actual Qt cursor, alignment command and cache acceptance; retain I/O failures."""
import argparse,json,os,sys,traceback
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);args=ap.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_CONFIG_HOME']=str(out/'qt-profile/config');os.environ['XDG_DATA_HOME']=str(out/'qt-profile/data')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import Qt,QPointF,QSettings
    from PySide6.QtWidgets import QApplication,QDialogButtonBox
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.canvas import Canvas
    from icstudio.model import example,clone,digest
    from icstudio.layout import rect
    from icstudio.build_info import WORKFLOW_SOURCE_HASH
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'qt-profile/settings'))
    app=QApplication([]);app.setStyle('Fusion');checks=[];errors=[];report={'workflow_hash':WORKFLOW_SOURCE_HASH,'qt_platform':app.platformName(),'checks':checks};w=None;canvas=None
    try:
        p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',500,500,600,600),rect('metal1',800,700,600,600),rect('metal2',4000,500,800,600)]
        canvas=Canvas('layout');canvas.resize(900,650);canvas.show();app.processEvents();canvas.auto_fit=False;canvas.scale=.12;canvas.offset=QPointF(80,80);canvas.set_data(c,p['pdk'],[c['shapes'][0]['id']]);canvas.batch_rectangles=False
        for dark in (False,True):
            canvas.dark=dark;canvas.layer_styles={'metal1':{'pattern':'Hatch'}}
            for scale in (.12,.15,.09,.21):
                canvas.scale=scale;canvas.cache_layout_pictures=False;expected=canvas.grab().toImage();canvas.cache_layout_pictures=True;actual=canvas.grab().toImage()
                assert actual==expected,'Scale-independent recording changed pixels.'
            canvas.anchor=QPointF(0,0);canvas.moving=True
            for delta in (QPointF(500,0),QPointF(-200,400),QPointF(1000,500)):
                canvas.drag=delta;canvas.cache_layout_pictures=False;expected=canvas.grab().toImage();canvas.cache_layout_pictures=True
                assert canvas.grab().toImage()==expected,'Stationary drag recording changed pixels.'
            canvas.cancel_gesture()
        canvas.grab().save(str(out/'cache-pixels.png'));checks.append({'name':'zoom_and_partial_drag_pixels_both_themes','status':'passed'});canvas.close();canvas=None
        w=Studio(recover=False);w.maybe_save=lambda:True;w.error=lambda msg:errors.append(str(msg));w.recovery_dir=out/'recovery';w.resize(1400,900);w.show();w.live_check.setChecked(False)
        p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',0,0,600,600),rect('metal2',5000,2000,600,600)];w.set_project(p);w.mode_combo.setCurrentIndex(1);QTest.qWait(60)
        w.select([s['id'] for s in c['shapes']],'layout');before=clone(w.project['cells']);dlg=w.align_dialog();dlg.fields['edge'].setCurrentText('Bottom');dlg.fields['routing'].setCurrentText('Keep coordinates')
        QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok),Qt.LeftButton);app.processEvents()
        assert w.cell['shapes'][1]['points'][0][1]==0;after=clone(w.project['cells']);w.undo();assert w.project['cells']==before;w.redo();assert w.project['cells']==after
        w.layout.grab().save(str(out/'aligned-layout.png'));checks.append({'name':'actual_align_dialog_geometry_and_undo_redo','status':'passed'})
        if errors:
            assert all('Recovery save failed' in e for e in errors),errors
            assert 'recovery failed' in w.save_label.text()
        checks.append({'name':'align_command_durable_recovery','status':'blocked' if errors else 'passed','errors':list(errors)})
        errors.clear();w.set_project(example('empty'));w.mode_combo.setCurrentIndex(1);QTest.qWait(30)
        w.layout.auto_fit=False;w.layout.scale=.08;w.layout.offset=QPointF(50,50)
        dlg=w.cursor_route_dialog();QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok),Qt.LeftButton);app.processEvents();assert w.layout.tool=='route_cursor'
        start=(w.layout.offset+QPointF(1000,1000)*w.layout.scale).toPoint();end=(w.layout.offset+QPointF(5000,3000)*w.layout.scale).toPoint()
        QTest.mouseClick(w.layout,Qt.LeftButton,Qt.NoModifier,start);QTest.mouseMove(w.layout,end);QTest.qWait(100)
        assert w._cursor_route['start']['point']==[1000,1000];assert w.layout.cursor_route_preview;assert not w.layout.cursor_route_blocked
        w.layout.grab().save(str(out/'cursor-route.png'));QTest.keyClick(w.layout,Qt.Key_Escape);app.processEvents();assert w._cursor_route is None;assert not w.layout.cursor_route_preview
        checks.append({'name':'cursor_start_hover_legal_preview_and_escape','status':'passed'})
        assert not errors,errors
        report['status']='partial' if any(c['status']=='blocked' for c in checks) else 'passed'
    except Exception as e:report.update(status='failed',error=str(e),traceback=traceback.format_exc())
    finally:
        if canvas:canvas.close()
        if w:w.saved_hash=digest(w.project);w.close();app.processEvents()
        (out/'gui-priorities.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return 1 if report['status']=='failed' else 0


if __name__=='__main__':raise SystemExit(main())
