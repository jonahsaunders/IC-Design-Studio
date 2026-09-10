"""Grid/path input regressions, including real Studio commits and undo/redo."""
import argparse,json,os,sys,traceback
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_CONFIG_HOME']=str(out/'qt-profile/config');os.environ['XDG_DATA_HOME']=str(out/'qt-profile/data')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import Qt,QEvent,QPointF,QSettings
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from icstudio.canvas import Canvas
    from icstudio.gui import Studio
    from icstudio.model import example,clone,digest
    from icstudio import __version__
    from icstudio.build_info import WORKFLOW_SOURCE_HASH
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'qt-profile/settings'))
    QSettings('ICDesignStudio','Studio').clear()
    app=QApplication([]);app.setStyle('Fusion');canvas=None;w=None;checks=[];errors=[];exceptions=[];old_hook=sys.excepthook
    sys.excepthook=lambda t,v,tb:(exceptions.append(str(v)),traceback.print_exception(t,v,tb))
    def event(kind,point,button=Qt.NoButton,buttons=Qt.NoButton):
        app.sendEvent(canvas,QMouseEvent(kind,QPointF(*point),QPointF(*point),button,buttons,Qt.NoModifier));app.processEvents()
    def press(pt):event(QEvent.MouseButtonPress,pt,Qt.LeftButton,Qt.LeftButton)
    def release(pt):event(QEvent.MouseButtonRelease,pt,Qt.LeftButton)
    def move(pt):event(QEvent.MouseMove,pt)
    def click(pt):press(pt);release(pt)
    def at(x,y):return (x*canvas.scale+canvas.offset.x(),y*canvas.scale+canvas.offset.y())
    def done(name):
        assert not exceptions,exceptions
        checks.append({'name':name,'status':'passed'})
    try:
        p=example('empty');canvas=Canvas('layout');canvas.resize(850,620);canvas.show();app.processEvents();canvas.auto_fit=False;canvas.set_data(p['cells'][0],p['pdk']);shapes=[];canvas.shape_added.connect(shapes.append)
        for scale in (.037,.08,.71,1.3):
            canvas.cancel_gesture();canvas.tool='rect';canvas.scale=scale;canvas.offset=QPointF(-27,13)
            step=canvas.grid_interval();press((83,77));move((241,203));release((241,203))
            assert all(v%step==0 for pt in shapes[-1]['points'] for v in pt),(step,shapes[-1])
        done('Rectangle drag corners land on the visible grid at four zoom scales and a negative pan offset')

        canvas.cancel_gesture();canvas.tool='rect';canvas.scale=.08;canvas.offset=QPointF(27,13);n=len(shapes)
        click((83,77));assert canvas._rect_pending and len(shapes)==n;anchor=QPointF(canvas.anchor);step=canvas.snap_interval()
        canvas.scale=.16;assert canvas.snap_interval()==step
        event(QEvent.MouseButtonPress,(400,300),Qt.MiddleButton,Qt.MiddleButton);event(QEvent.MouseMove,(430,320),buttons=Qt.MiddleButton);event(QEvent.MouseButtonRelease,(430,320),Qt.MiddleButton)
        assert canvas.anchor==anchor
        click(at(anchor.x()+4*step,anchor.y()+3*step));assert len(shapes)==n+1
        assert all(v%step==0 for pt in shapes[-1]['points'] for v in pt)
        done('Click-click rectangle survives pan and zoom with its original snap spacing')

        canvas.cancel_gesture();canvas.tool='rect';canvas.grid_snap_enabled=False;canvas.scale=.08;canvas.offset=QPointF(27,13)
        expected=[[round(canvas.model(QPointF(*pt)).x()),round(canvas.model(QPointF(*pt)).y())] for pt in ((83,77),(241,203))]
        press((83,77));move((241,203));release((241,203));assert shapes[-1]['points']==expected
        assert any(v%canvas.grid_interval() for pt in expected for v in pt)
        done('Snap off creates rectangles at integer database coordinates without forcing them onto the drawing grid')

        canvas.cancel_gesture();canvas.tool='path';canvas.grid_snap_enabled=True;canvas.grid_snap_mode='fixed';canvas.grid_snap_step=50;canvas.scale=.1;canvas.offset=QPointF(40,40);canvas.orthogonal=True;canvas.line_width=300
        click(at(1000,1000));move(at(3000,2500));assert len(canvas.drawing)==1
        preview=canvas.grab().toImage();preview.save(str(out/'path-width-preview.png'))
        drawing=canvas.drawing;canvas.drawing=[];base=canvas.grab().toImage();canvas.drawing=drawing
        x,y=map(round,at(2000,1100));assert preview.pixelColor(x,y)!=base.pixelColor(x,y),'Full-width preview is missing'
        QTest.keyClick(canvas,Qt.Key_Return);assert shapes[-1]['points']==[[1000,1000],[3000,1000],[3000,2500]]
        done('One click plus hover plus Enter creates the complete Manhattan path with a full-width preview')

        click(at(1000,1000));move(at(3000,2500));QTest.keyClick(canvas,Qt.Key_Tab);click(at(3000,2500))
        assert canvas.drawing==[QPointF(1000,1000),QPointF(1000,2500),QPointF(3000,2500)]
        QTest.keyClick(canvas,Qt.Key_Backspace);assert canvas.drawing==[QPointF(1000,1000)]
        canvas.finish_drawing();assert canvas.drawing and 'endpoint' in canvas.drawing_notice
        event(QEvent.MouseButtonDblClick,at(3000,2500),Qt.LeftButton,Qt.LeftButton);release(at(3000,2500))
        assert shapes[-1]['points']==[[1000,1000],[1000,2500],[3000,2500]]
        done('Tab flips bend order; Backspace removes the whole last click; incomplete Finish retains draft; double-click includes endpoint')

        click(at(1000,1000));click(at(2000,1000));n=len(shapes);saved=list(canvas.drawing)
        canvas.commit_shape_callback=lambda shape:False;assert not canvas.finish_drawing();assert canvas.drawing==saved and len(shapes)==n
        QTest.keyClick(canvas,Qt.Key_Escape);assert not canvas.drawing and canvas._drawing_grid is None
        canvas.close();canvas=None;done('Rejected document commit retains the draft; Escape clears it without creating geometry')

        w=Studio(recover=False);w.maybe_save=lambda:True;w.error=lambda text:errors.append(str(text));w.live_check.setChecked(False);w.resize(1450,960);w.show();w.set_project(example('empty'));w.mode_combo.setCurrentIndex(1);QTest.qWait(180);canvas=w.layout;canvas.auto_fit=False;canvas.scale=.08;canvas.offset=QPointF(40,40)
        assert w.grid_settings_action in w.task_menus['View'].actions();w.grid_settings_action.trigger();app.processEvents();dlg=w._grid_dialog
        enabled,mode,spacing,error=dlg.snap_fields['layout'];assert enabled.isChecked();mode.setCurrentIndex(mode.findData('fixed'));spacing.setText('0.05');spacing.editingFinished.emit();assert canvas.grid_snap_step==50
        spacing.setText('0.003');spacing.editingFinished.emit();assert error.text() and canvas.grid_snap_step==50
        enabled.setChecked(False);assert not canvas.grid_snap_enabled;enabled.setChecked(True);assert canvas.grid_snap_enabled
        spacing.setText('0.05');spacing.editingFinished.emit();style=dlg.fields['layout'][0];style.setCurrentIndex(style.findData('off'));assert canvas.grid_snap_active()
        style.setCurrentIndex(style.findData('lines'));dlg.grab().save(str(out/'grid-settings.png'));mode.setCurrentIndex(mode.findData('visible'));dlg.close()
        w.grid_snap_action.trigger();assert not canvas.grid_snap_enabled and not w.editor_grid_snap.isChecked()
        w.editor_grid_snap.setChecked(True);assert canvas.grid_snap_enabled and w.grid_snap_action.isChecked()
        assert w.settings.value('display/layout/grid_snap_step',type=int)==50
        done('View Grid Settings exposes exact spacing, rejects off-process spacing, keeps visibility separate, and synchronizes menu/toolbar snap toggles')

        w.start_layout_tool('path');w.editor_width.setText('0.5');w.apply_editor_options();canvas.scale=.08;canvas.offset=QPointF(40,40);canvas.auto_fit=False
        before=clone(w.cell['shapes']);click(at(1000,1000));assert not w.editor_finish.isEnabled();move(at(4000,2500))
        horizontal=canvas.path_horizontal;QTest.keyClick(canvas,Qt.Key_Tab);assert canvas.path_horizontal!=horizontal;QTest.keyClick(canvas,Qt.Key_Tab);assert canvas.path_horizontal==horizontal
        w.grab().save(str(out/'studio-path-preview.png'));QTest.keyClick(canvas,Qt.Key_Return)
        assert len(w.cell['shapes'])==len(before)+1 and not canvas.drawing
        shape=clone(w.cell['shapes'][-1]);assert shape['points']==[[1000,1000],[4000,1000],[4000,2500]] and shape['width']==500
        w.undo();assert w.cell['shapes']==before;w.redo();assert w.cell['shapes'][-1]==shape
        done('Actual Studio Enter commits the shown path and width; undo/redo restores exact geometry and identity')

        w.start_layout_tool('path');canvas.scale=.08;canvas.offset=QPointF(40,40);click(at(1000,5000));click(at(4000,5000));assert w.editor_finish.isEnabled()
        w.editor_net.setCurrentText('invalid net');n=len(w.cell['shapes']);w.editor_finish.click()
        assert len(w.cell['shapes'])==n and canvas.drawing and 'net name' in w.drawing_help.text()
        w.editor_net.setCurrentText('');w.editor_finish.click();assert len(w.cell['shapes'])==n+1 and not canvas.drawing
        done('Invalid routing net retains the draft with inline feedback; fixing it and clicking Finish creates one path')

        w.start_layout_tool('path');canvas.scale=.08;canvas.offset=QPointF(40,40);click(at(1000,8000));click(at(4000,8000));canvas.locked_layers.add(canvas.layer);n=len(w.cell['shapes']);w.editor_finish.click()
        assert len(w.cell['shapes'])==n and canvas.drawing and 'Unlock' in w.drawing_help.text()
        canvas.locked_layers.remove(canvas.layer);w.editor_width.setText('0.005');w.editor_finish.click()
        assert len(w.cell['shapes'])==n and canvas.drawing and 'Route blocked' in w.drawing_help.text()
        w.editor_width.setText('0.5');w.editor_finish.click();assert len(w.cell['shapes'])==n+1
        w.start_layout_tool('rect');canvas.scale=.08;canvas.offset=QPointF(40,40);n=len(w.cell['shapes']);press(at(6000,1000));move(at(8000,3000));release(at(8000,3000));assert len(w.cell['shapes'])==n+1
        done('Locked layers and width-rule failures keep path drafts; correction succeeds; actual Studio rectangle commit remains functional')
        w.grab().save(str(out/'studio-completed.png'))
        w.resize(1000,850);w.start_layout_tool('path');QTest.qWait(100)
        for widget in (w.editor_grid_snap,w.editor_bends,w.editor_flip,w.editor_back,w.editor_finish,w.editor_cancel):
            assert widget.width()>=widget.minimumSizeHint().width(),widget.text() if hasattr(widget,'text') else str(widget)
        assert w.drawing_help.height()>=w.drawing_help.heightForWidth(w.drawing_help.width())
        w.grab().save(str(out/'studio-narrow.png'));w.toggle_theme();app.processEvents();w.grab().save(str(out/'studio-narrow-light.png'))
        done('Drawing controls wrap at a narrow window without clipped controls or instructions; both themes inspected')
        unexpected=[error for error in errors if '[Errno 5]' not in error];assert not unexpected,unexpected
        result={'status':'passed','checks':checks,'recovery_errors':errors,'durable_recovery_status':'blocked_by_host_io' if errors else 'no_error_reported'}
    except Exception:result={'status':'failed','checks':checks,'exception':traceback.format_exc(),'errors':errors}
    finally:
        if w:w.saved_hash=digest(w.project);w.close()
        elif canvas:canvas.close()
        app.processEvents();sys.excepthook=old_hook
    result.update(version=__version__,workflow_hash=WORKFLOW_SOURCE_HASH,qt_platform=app.platformName(),qt_exceptions=exceptions)
    (out/'gui-grid-paths.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
