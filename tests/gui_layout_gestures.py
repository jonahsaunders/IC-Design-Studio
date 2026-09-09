"""Actual Qt mouse/key events for object snapping and navigation isolation."""
import argparse,json,os,sys,traceback
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_CONFIG_HOME']=str(out/'qt-profile/config');os.environ['XDG_DATA_HOME']=str(out/'qt-profile/data')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import Qt,QPointF,QEvent,QSettings
    from PySide6.QtGui import QMouseEvent,QFocusEvent
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio.canvas import Canvas
    from icstudio.layout import rect
    from icstudio.layout_scene import LayoutScene
    from icstudio.model import example,clone,digest
    from icstudio.gui import Studio
    from icstudio import __version__
    from icstudio.build_info import WORKFLOW_SOURCE_HASH
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'qt-profile/settings'))
    app=QApplication([]);app.setStyle('Fusion');checks=[];errors=[];canvas=None;window=None;old_hook=sys.excepthook
    sys.excepthook=lambda t,v,tb:(errors.append(str(v)),traceback.print_exception(t,v,tb))

    def mouse(kind,point,button=Qt.NoButton,buttons=Qt.NoButton):
        event=QMouseEvent(kind,QPointF(*point),QPointF(*point),button,buttons,Qt.NoModifier)
        QApplication.sendEvent(canvas,event);app.processEvents()

    def move(point,buttons=Qt.NoButton):mouse(QEvent.MouseMove,point,buttons=buttons)
    def press(point,button=Qt.LeftButton,buttons=None):mouse(QEvent.MouseButtonPress,point,button,button if buttons is None else buttons)
    def release(point,button=Qt.LeftButton,buttons=Qt.NoButton):mouse(QEvent.MouseButtonRelease,point,button,buttons)
    def click(point):press(point);release(point)
    def model_point(point):return tuple(point[i]*canvas.scale+(canvas.offset.x(),canvas.offset.y())[i] for i in (0,1))
    def done(name):
        assert not errors,errors
        checks.append({'name':name,'status':'passed'})

    try:
        p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',100,100,200,200),
            {'id':'route','kind':'path','layer':'metal2','width':30,'points':[[400,100],[400,400]]}]
        c['layout_ports']=[{'id':'port','name':'OUT','layer':'metal2','point':[550,300]}]
        canvas=Canvas('layout');canvas.resize(800,600);canvas.show();app.processEvents();canvas.auto_fit=False;canvas.scale=1;canvas.offset=QPointF(20,20);canvas.set_data(c,p['pdk']);canvas.tool='path';canvas.orthogonal=True
        committed=[];canvas.shape_added.connect(committed.append);before=clone(c)
        move(model_point((298,103)));assert canvas.drag==QPointF(300,100);assert canvas.snap_target.kind=='Corner'
        click(model_point((298,103)));move(model_point((403,233)))
        assert canvas.drag==QPointF(400,235);assert canvas.snap_target.kind=='Segment'
        preview=canvas.path_preview(canvas.drag);click(model_point((403,233)))
        assert canvas.drawing[-len(preview):]==preview
        QTest.keyClick(canvas,Qt.Key_Return);assert committed[-1]['points']==[[300,100],[400,100],[400,235]]
        assert c==before
        move(model_point((403,233)));canvas.grab().save(str(out/'path-snap.png'))
        done('Mouse path starts at omitted rectangle corner and ends exactly on another layer route centerline; preview equals commit')

        canvas.snap_to_terminals=False;move(model_point((307,233)));step=canvas.snap_interval();assert canvas.drag==QPointF(round(307/step)*step,round(233/step)*step);assert canvas.snap_target is None
        canvas.snap_to_terminals=True;canvas.visible_layers={'metal1'};move(model_point((403,233)));assert canvas.snap_target is None
        canvas.visible_layers={'metal1','metal2'};canvas.locked_layers={'metal2'};move(model_point((403,233)));assert canvas.drag==QPointF(400,235)
        move(model_point((553,298)));assert canvas.snap_target.kind=='Terminal';assert canvas.drag==QPointF(550,300)
        done('Grid-only disables snapping; hidden layers are ignored; locked geometry remains an unchanged snap reference; ports snap')

        master={'id':'master','name':'master','devices':[],'ports':[],'shapes':[c['shapes'][1]]}
        top={**c,'shapes':[],'layout_ports':[],'layout_instances':[{'id':'array','name':'X','cell':'master','x':0,'y':0,'nx':2,'ny':1,'a':[0,400],'b':[0,0],'rotation':90,'mirror':True}]}
        p['cells']=[top,master];scene=LayoutScene().update(p,top['id']);canvas.set_data({**top,'_layout_scene':scene},p['pdk'])
        move(model_point((233,403)));assert canvas.drag==QPointF(235,400);assert canvas.snap_target.kind=='Segment';assert canvas.snap_target.owner=='array'
        canvas.set_data(c,p['pdk']);canvas.locked_layers=set()
        done('Rotated mirrored hierarchical routes preserve their centerline snap targets')

        for tool in ('rect','ruler','select','edge','vertex','stretch','move_ref','copy_ref'):
            canvas.cancel_gesture();canvas.tool=tool;canvas.offset=QPointF(20,20);canvas.selection=[];count=len(committed)
            press((350,240),Qt.MiddleButton);move((390,275),Qt.MiddleButton)
            assert canvas.anchor is None and canvas.drag is None and canvas.ruler is None
            assert canvas.offset==QPointF(60,55)
            while_panning=canvas.grab().toImage();release((390,275),Qt.MiddleButton)
            assert canvas.grab().toImage()==while_panning,'Navigation painted a transient shape: '+tool
            assert not canvas.pan and len(committed)==count
        canvas.tool='rect';canvas.grab().save(str(out/'pan-clean.png'))
        done('Middle-button pan in eight layout tools has identical pixels before and after release and emits no shape')

        canvas.cancel_gesture();canvas.tool='path';canvas.offset=QPointF(20,20);click(model_point((300,100)));move(model_point((350,250)))
        points=list(canvas.drawing);drag=QPointF(canvas.drag);count=len(committed)
        press((370,270),Qt.MiddleButton);move((410,300),Qt.MiddleButton)
        assert canvas.drawing==points and canvas.drag==drag and canvas.anchor is None
        # A second mouse button must neither terminate panning nor add a point.
        press((410,300),Qt.LeftButton,Qt.LeftButton|Qt.MiddleButton);release((410,300),Qt.LeftButton,Qt.MiddleButton)
        assert canvas.pan and canvas.drawing==points;release((410,300),Qt.MiddleButton)
        mouse(QEvent.MouseButtonDblClick,(410,300),Qt.MiddleButton,Qt.MiddleButton);release((410,300),Qt.MiddleButton)
        assert len(committed)==count and canvas.drawing==points
        click(model_point((403,233)));QTest.keyClick(canvas,Qt.Key_Return)
        assert committed[-1]['points']==[[300,100],[400,100],[400,235]]
        done('Pan during path preserves placed points and frozen preview; extra button and MMB double-click cannot finish the path')

        for tool in ('rect','ruler','path','select'):
            canvas.cancel_gesture();canvas.tool=tool;canvas.offset=QPointF(20,20);count=len(committed)
            QTest.keyPress(canvas,Qt.Key_Space);press((350,240));move((390,275),Qt.LeftButton)
            QTest.keyRelease(canvas,Qt.Key_Space);assert canvas.pan
            release((390,275));assert canvas.offset==QPointF(60,55) and not canvas.pan and canvas.anchor is None
            assert not canvas.drawing and len(committed)==count
        done('Space plus left drag pans in four tools even when Space is released before the mouse')

        canvas.cancel_gesture();canvas.tool='rect';canvas.offset=QPointF(20,20);count=len(committed)
        press((350,240));move((370,260),Qt.LeftButton);anchor=QPointF(canvas.anchor);drag=QPointF(canvas.drag)
        press((370,260),Qt.MiddleButton,Qt.LeftButton|Qt.MiddleButton);move((410,290),Qt.LeftButton|Qt.MiddleButton)
        assert canvas.anchor==anchor and canvas.drag==drag
        release((410,290),Qt.LeftButton,Qt.MiddleButton);assert canvas.pan and canvas.anchor is None
        release((410,290),Qt.MiddleButton);assert len(committed)==count
        canvas.tool='edge';canvas.vertex_pick=('route',0);canvas.anchor=QPointF(100,100);editor=[];canvas.editor_requested.connect(lambda *v:editor.append(v))
        press((350,240),Qt.MiddleButton);move((390,275),Qt.MiddleButton);release((390,275),Qt.MiddleButton)
        assert not editor and canvas.vertex_pick==('route',0)
        canvas.cancel_gesture();press((100,100),Qt.MiddleButton);QApplication.sendEvent(canvas,QFocusEvent(QEvent.FocusOut));assert not canvas.pan and canvas._pan_anchor is None
        done('Interrupted drawing drag cancels safely; middle release cannot commit a vertex; focus loss clears navigation state')

        canvas.cancel_gesture();canvas.tool='route_cursor';requested=[];hovers=[]
        canvas.route_point_requested.connect(lambda x,y:requested.append((x,y)));canvas.route_hover_requested.connect(lambda x,y:hovers.append((x,y)))
        click(model_point((403,233)));assert requested[-1]==(400,235)
        move(model_point((553,298)));assert hovers[-1]==(550,300);count=len(hovers)
        press((350,240),Qt.MiddleButton);move((390,275),Qt.MiddleButton);release((390,275),Qt.MiddleButton)
        assert len(requested)==1 and len(hovers)==count
        done('Cursor route uses the same snapped endpoints; pan does not submit route points or hover jobs')

        canvas.close();canvas=Canvas('schematic');canvas.resize(800,600);canvas.show();app.processEvents();canvas.auto_fit=False;canvas.scale=1;canvas.offset=QPointF(20,20)
        p=example('empty');canvas.set_data(p['cells'][0],p['pdk']);canvas.tool='connect';click((120,120));move((220,220));points=clone(canvas.wire_points);drag=QPointF(canvas.drag);wires=[];canvas.wire_added.connect(wires.append)
        press((220,220),Qt.MiddleButton);move((260,250),Qt.MiddleButton);release((260,250),Qt.MiddleButton)
        assert canvas.wire_points==points and canvas.drag==drag and not wires
        canvas.close();canvas=None;done('Schematic wire navigation preserves its unfinished wire and preview')

        window=Studio(recover=False);window.maybe_save=lambda:True;window.error=lambda message:errors.append(str(message));window.live_check.setChecked(False);window.show();window.set_project(p);window.mode_combo.setCurrentIndex(1)
        window.start_layout_tool('path');assert window.layout.snap_to_terminals
        window.editor_snap.setCurrentIndex(1);assert not window.layout.snap_to_terminals
        window.editor_snap.setCurrentIndex(0);assert window.layout.snap_to_terminals
        window.grab().save(str(out/'studio-path-options.png'));done('Complete Studio path command and Grid + objects control activate the canvas settings')
        result={'status':'passed','checks':checks}
    except Exception:result={'status':'failed','checks':checks,'exception':traceback.format_exc()}
    finally:
        if canvas:canvas.close()
        if window:window.saved_hash=digest(window.project);window.close()
        app.processEvents();sys.excepthook=old_hook
    result.update(version=__version__,workflow_hash=WORKFLOW_SOURCE_HASH,qt_platform=app.platformName(),errors=errors)
    (out/'gui-gestures.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
