"""Qt acceptance for cached previews and actual connected mouse editing."""
import argparse
import json
import os
import sys
import traceback
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_CONFIG_HOME']=str(out/'qt-profile/config');os.environ['XDG_DATA_HOME']=str(out/'qt-profile/data')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QPointF,Qt,QSettings
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio.canvas import Canvas
    from icstudio.gui import Studio
    from icstudio.layout import rect
    from icstudio.layout_topology import partition
    from icstudio.model import example,clone,digest
    from icstudio import __version__
    from icstudio.build_info import WORKFLOW_SOURCE_HASH
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'qt-profile/settings'))
    app=QApplication([]);app.setStyle('Fusion');QSettings('ICDesignStudio','Studio').clear()
    checks=[];errors=[];window=None;canvas=None;old_hook=sys.excepthook
    sys.excepthook=lambda t,v,tb:(errors.append(str(v)),traceback.print_exception(t,v,tb))
    try:
        p=example('empty');c=p['cells'][0]
        c['shapes']=[rect('metal1',60,60,60,60),rect('metal2',200,200,40,40),
            {'id':'hole','kind':'polygon','layer':'metal1','points':[[140,60],[190,60],[190,110],[140,110]],'holes':[[[150,70],[180,70],[180,100],[150,100]]]},
            {'id':'wire','kind':'path','layer':'metal1','width':12,'points':[[60,160],[120,160],[120,210]]}]
        canvas=Canvas('layout');canvas.resize(500,400);canvas.show();app.processEvents();canvas.auto_fit=False;canvas.scale=1;canvas.offset=QPointF(20,20)
        ids=[s['id'] for s in c['shapes'] if s['layer']=='metal1'];canvas.set_data(c,p['pdk'],ids,revision=0);canvas.grab()
        paths=list(canvas._geometry_cache.paths);index=canvas._spatial;before=clone(c)
        canvas.anchor=QPointF(0,0);canvas.drag=QPointF(50,40);canvas.moving=True
        preview=canvas.grab().toImage();preview.save(str(out/'drag-preview.png'))
        assert c==before and canvas._spatial is index
        assert all(a is b for a,b in zip(paths,canvas._geometry_cache.paths))
        moved=clone(c)
        for s in moved['shapes']:
            if s['id'] in ids:
                s['points']=[[x+50,y+40] for x,y in s['points']]
                if s.get('holes'):s['holes']=[[[x+50,y+40] for x,y in hole] for hole in s['holes']]
        canvas.cancel_gesture();canvas.set_data(moved,p['pdk'],ids,revision=1)
        assert preview==canvas.grab().toImage(),'Cached drag differs from committed geometry (including holes and path widths).'
        checks.append('Origin-anchored drag matches committed pixels, preserves geometry, paths and index.')
        canvas.set_data(c,p['pdk'],ids,revision=2);assert canvas.grab().toImage()!=preview
        checks.append('Cancel restores the original display without a model edit.')
        array=clone(c);array['shapes']=[rect('metal1',800,70,30,30),rect('metal1',870,70,30,30)]
        for i,s in enumerate(array['shapes']):s.update(id='array',source_id='master',instance_path=str(i))
        canvas.set_data(array,p['pdk'],['array'],revision=3);canvas.anchor=QPointF(10,10);canvas.drag=QPointF(-690,10);canvas.moving=True
        array_preview=canvas.grab().toImage();expected=clone(array)
        for s in expected['shapes']:s['points']=[[x-700,y] for x,y in s['points']]
        canvas.cancel_gesture();canvas.set_data(expected,p['pdk'],['array'],revision=4)
        assert array_preview==canvas.grab().toImage()
        checks.append('Hierarchy identity and inverse viewport query draw offscreen instances moved into view.')
        canvas.selection=[];expected['shapes'][0]['points']=[[300,200],[330,230]];canvas.set_data(expected,p['pdk'])
        assert canvas.editor_hit(QPointF(310,210))['id']=='array'
        assert canvas.editor_hit(QPointF(110,80)) is None
        canvas.visible_layers=set();hidden=canvas.grab().toImage();canvas.visible_layers={'metal1'}
        assert hidden!=canvas.grab().toImage();canvas.locked_layers={'metal1'}
        assert canvas.editor_hit(QPointF(310,210)) is None
        checks.append('In-place update refreshes selection bounds; visibility and locks remain effective.')
        canvas.close();canvas=None
        # Full Studio integration through mouse events and the connected handler.
        p=example('empty');c=p['cells'][0]
        a=rect('metal1',-300,-300,600,600,net='signal');b=rect('metal1',4700,-300,600,600,net='signal')
        wire={'id':'lead','kind':'path','layer':'metal1','width':400,'points':[[0,0],[5000,0]],'net':'signal','device_id':''}
        c['shapes']=[wire,a,b]
        window=Studio(recover=False);window.error=lambda value:errors.append(str(value));window.maybe_save=lambda:True
        window.resize(1400,900);window.show();window.set_project(p);window.mode_combo.setCurrentIndex(1);QTest.qWait(80)
        layout=window.layout;layout.auto_fit=False;layout.scale=.08;layout.offset=QPointF(100,160)
        before=clone(window.project['cells']);connections=partition(window.project,window.cid)
        at=lambda x,y:(QPointF(x*layout.scale,y*layout.scale)+layout.offset).toPoint()
        start=at(5000,0);end=at(5000,1000)
        QTest.mousePress(layout,Qt.LeftButton,Qt.NoModifier,start);QTest.mouseMove(layout,end);app.processEvents()
        assert layout.moving and b['id'] in window.selection
        assert window.project['cells']==before
        layout.grab().save(str(out/'connected-mouse-preview.png'))
        QTest.mouseRelease(layout,Qt.LeftButton,Qt.NoModifier,end);app.processEvents()
        assert not errors,errors
        after=clone(window.project['cells']);assert after!=before
        assert partition(window.project,window.cid)==connections
        assert next(s for s in window.cell['shapes'] if s['id']==b['id'])['points']==[[4700,700],[5300,1300]]
        window.undo();assert window.project['cells']==before
        window.redo();assert window.project['cells']==after
        window.grab().save(str(out/'connected-mouse-committed.png'))
        checks.append('Studio mouse drag commits connected geometry with exact undo/redo and unchanged connectivity.')
        layout.auto_fit=False;layout.scale=.08;layout.offset=QPointF(100,160)
        QTest.mousePress(layout,Qt.LeftButton,Qt.NoModifier,at(0,0));QTest.mouseMove(layout,at(0,500));app.processEvents()
        assert layout.moving and a['id'] in window.selection
        QTest.mouseRelease(layout,Qt.LeftButton,Qt.NoModifier,at(0,500));app.processEvents()
        assert next(s for s in window.cell['shapes'] if s['id']==a['id'])['points']==[[-300,200],[300,800]]
        assert partition(window.project,window.cid)==connections
        window.undo();assert window.project['cells']==after
        checks.append('A real drag starting at model coordinate zero repaints and commits correctly.')
        layout.auto_fit=False;layout.scale=.08;layout.offset=QPointF(100,160)
        QTest.mousePress(layout,Qt.LeftButton,Qt.NoModifier,at(5000,1000));QTest.mouseMove(layout,at(5000,1500));QTest.keyClick(layout,Qt.Key_Escape);app.processEvents()
        assert window.project['cells']==after and not layout.moving
        checks.append('Escape cancels a live Studio gesture without a history edit.')
        assert not errors,errors
        result={'status':'passed','version':__version__,'workflow_hash':WORKFLOW_SOURCE_HASH,'qt_platform':app.platformName(),'checks':checks,'errors':errors}
    except Exception:
        result={'status':'failed','version':__version__,'checks':checks,'errors':errors,'exception':traceback.format_exc()}
    finally:
        if canvas:canvas.close()
        if window:window.saved_hash=digest(window.project);window.close()
        app.processEvents();sys.excepthook=old_hook
    (out/'gui-performance.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
