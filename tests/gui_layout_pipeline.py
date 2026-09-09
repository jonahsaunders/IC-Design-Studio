"""Native Qt pixels and interactions for rectangle batches and hierarchy queries."""
import argparse,json,os,sys,traceback
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);args=ap.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_CONFIG_HOME']=str(out/'qt-profile/config');os.environ['XDG_DATA_HOME']=str(out/'qt-profile/data')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QPointF,QRectF,Qt,QSettings
    from PySide6.QtTest import QTest
    from icstudio.canvas import Canvas
    from icstudio.gui import Studio
    from icstudio.model import example,clone,digest
    from icstudio.layout import rect
    from icstudio.design_ops import flatten_layout
    from icstudio.layout_scene import LayoutScene
    from icstudio import __version__
    from icstudio.build_info import WORKFLOW_SOURCE_HASH
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'qt-profile/settings'))
    app=QApplication([]);app.setStyle('Fusion');canvas=None;w=None;checks=[];errors=[];old_hook=sys.excepthook
    sys.excepthook=lambda t,v,tb:(errors.append(str(v)),traceback.print_exception(t,v,tb))
    try:
        p=example('empty');c=p['cells'][0]
        c['shapes']=[rect('metal1',50,50,70,80),rect('metal1',80,80,80,50),rect('metal2',90,60,80,60),rect('metal1',60,90,80,80),
                     {'id':'hole','kind':'polygon','layer':'metal1','points':[[200,50],[300,50],[300,150],[200,150]],'holes':[[[220,70],[280,70],[280,130],[220,130]]]},
                     {'id':'path','kind':'path','layer':'metal2','width':20,'points':[[60,220],[170,220],[170,270]]}]
        canvas=Canvas('layout');canvas.resize(800,600);canvas.show();app.processEvents();canvas.auto_fit=False;canvas.scale=1.3;canvas.offset=QPointF(30,35)
        for dark in (False,True):
            for selected in ([],[c['shapes'][0]['id'],c['shapes'][1]['id']]):
                canvas.dark=dark;canvas.set_data(c,p['pdk'],selected,revision=0);canvas.batch_rectangles=False;expected=canvas.grab().toImage();canvas.batch_rectangles=True
                assert canvas.grab().toImage()==expected,'Rectangle batching changed pixels.'
        checks.append('Batched rectangles exactly match individual paths with overlap, layer order, alpha and selection in both themes.')
        for offset,pattern in ((QPointF(30,35),'Solid'),(QPointF(50,45),'Hatch'),(QPointF(55,45),'Hatch')):
            canvas.offset=offset;canvas.layer_styles={'metal1':{'pattern':pattern}}
            canvas.cache_layout_pictures=False;expected=canvas.grab().toImage();canvas.cache_layout_pictures=True
            assert canvas.grab().toImage()==expected,'Native picture replay changed pixels.'
        canvas.layer_styles={}
        checks.append('Padded vector replay matches uncached pixels during pan and patterned-layer changes.')
        child={**c,'id':'master','name':'master'};top={**c,'shapes':[],'layout_instances':[{'id':'inst','name':'tile','cell':'master','x':0,'y':0,'nx':2,'ny':2,'a':[350,0],'b':[0,300],'rotation':90,'mirror':True}]};p['cells']=[top,child]
        scene=LayoutScene().update(p,p['top']);canvas.scale=.7;canvas.offset=QPointF(40,40);canvas.dark=False
        flattened={**top,'shapes':flatten_layout(p,p['top'])};canvas.set_data(flattened,p['pdk'],['inst'],revision=1);expected=canvas.grab().toImage()
        canvas.set_data({**top,'_layout_scene':scene},p['pdk'],['inst'],revision=2);actual=canvas.grab().toImage();actual.save(str(out/'hierarchy.png'));expected.save(str(out/'hierarchy-reference.png'))
        assert actual==expected,'Native hierarchical viewport changed flattened reference pixels.'
        assert canvas.editor_hit(QPointF(70,70))['id']=='inst';canvas.locked_layers={'metal1','metal2'};assert canvas.editor_hit(QPointF(70,70)) is None;canvas.locked_layers=set()
        assert canvas.editor_marquee(QRectF(50,50,100,100))==['inst'];canvas.box_mode='Inside';assert canvas.editor_marquee(QRectF(50,50,100,100))==[]
        checks.append('Native hierarchy exactly matches flattened pixels and preserves instance identity, locks, crossing and inside selection.')
        canvas.anchor=QPointF(0,0);canvas.drag=QPointF(-350,0);canvas.moving=True;preview=canvas.grab().toImage();canvas.cancel_gesture()
        moved=clone(p);moved['cells'][0]['layout_instances'][0]['x']-=350;scene.update(moved,p['top']);canvas.set_data({**moved['cells'][0],'_layout_scene':scene},p['pdk'],['inst'],revision=3)
        assert canvas.grab().toImage()==preview
        checks.append('Hierarchical drag uses inverse viewport queries and matches committed placement pixels.')
        canvas.close();canvas=None
        w=Studio(recover=False);w.maybe_save=lambda:True;w.error=lambda value:errors.append(str(value));w.resize(1400,900);w.show();w.live_check.setChecked(False)
        w.set_project(p);w.mode_combo.setCurrentIndex(1);QTest.qWait(50);w.select(['inst'],'layout');w.fit_selection();assert w.layout.cell.get('_layout_scene') is not None
        w.layout.grab().save(str(out/'studio-hierarchy.png'));w.set_hierarchy_depth(1);assert w.layout.cell['_layout_scene'].expanded_count==0;w.set_hierarchy_depth(0)
        assert w.layout.cell['_layout_scene'].expanded_count==len(flatten_layout(p,p['top']))
        checks.append('Studio hierarchy uses native queries, fits the selected array and respects display depth.')
        # Real mouse path, fast transaction and recovery stages are exercised by
        # gui_layout_performance.py; here also verify stale worker packets cannot
        # replace findings after a revision change.
        old_revision=w.project['revision'];w.history.commit(lambda q:q['cells'][0]['layout_instances'][0].update(x=5),'Move instance');w.refresh()
        w.live_checks_ready({'project_id':w.project['id'],'revision':old_revision,'cid':w.cid,'result':{'issues':[{'code':'STALE','message':'old'}],'guides':[]}})
        assert getattr(w,'_live_revision',None)!=old_revision or not any(v['code']=='STALE' for v in getattr(w,'_live_findings',[]))
        checks.append('Stale background packets cannot replace findings for a newer revision.')
        assert not errors,errors
        result={'status':'passed','version':__version__,'workflow_hash':WORKFLOW_SOURCE_HASH,'qt_platform':app.platformName(),'checks':checks,'errors':errors}
    except Exception:result={'status':'failed','version':__version__,'checks':checks,'errors':errors,'exception':traceback.format_exc()}
    finally:
        if canvas:canvas.close()
        if w:w.saved_hash=digest(w.project);w.close()
        app.processEvents();sys.excepthook=old_hook
    (out/'gui-pipeline.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
