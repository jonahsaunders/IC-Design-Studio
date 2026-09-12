"""Exercise real via controls, canvas clicks and Autovia preview installation."""
import argparse
import json
import os
import sys
import traceback
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--project',type=Path,help='Also check an imported overvoltage bench artifact.')
    args=ap.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
    os.environ['XDG_DATA_HOME']=str(out/'profile/data')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import Qt,QPointF,QSettings
    from PySide6.QtWidgets import QApplication,QDialogButtonBox,QPushButton
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import example,clone,digest,save_project,load_project
    from icstudio.layout import rect,polygon,kdb
    from icstudio.layout_topology import partition
    from test_silicon import technology
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'profile/settings'))
    app=QApplication([]);app.setStyle('Fusion');checks=[];errors=[];w=None
    report={'checks':checks,'qt_platform':app.platformName()}
    try:
        w=Studio(recover=False);w.error=lambda msg:errors.append(str(msg));w.maybe_save=lambda:True
        w.live_check.setChecked(False);w.resize(1440,1000);w.show()
        def setup(p):
            w.cancel_tool();w.set_project(p);w.mode_combo.setCurrentIndex(1);QTest.qWait(150)
            w.layout.auto_fit=False;w.layout.scale=.3;w.layout.offset=QPointF(100,100)
        def click(point):
            screen=(w.layout.offset+QPointF(*point)*w.layout.scale).toPoint()
            QTest.mouseMove(w.layout,screen);QTest.qWait(80)
            QTest.mouseClick(w.layout,Qt.LeftButton,Qt.NoModifier,screen);app.processEvents()
        def accept(dlg):
            QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok),Qt.LeftButton)
            app.processEvents()
        def via_button():
            return next(button for button,tool in w.ribbon_buttons if tool=='via' and button.isVisible())

        setup(example('empty'));before=clone(w.project['cells'])
        QTest.mouseClick(via_button(),Qt.LeftButton)
        assert w.layout.tool=='via' and w._via_configuration[1]=='M1 to M2'
        click([1000,1000]);assert len(w.cell['shapes'])==3,errors
        assert {s['layer'] for s in w.cell['shapes']}=={'metal1','via1','metal2'}
        assert len(set(partition(w.project,w.cid).values()))==1
        after=clone(w.project['cells']);w.undo();assert w.project['cells']==before
        w.redo();assert w.project['cells']==after
        checks.append('Via toolbar click creates three connected shapes; undo and redo are exact')

        p=example('empty');p['pdk']=technology();setup(p)
        QTest.mouseClick(via_button(),Qt.LeftButton)
        w.editor_via.setCurrentText('Local interconnect to M1')
        assert w._via_configuration[1]=='Local interconnect to M1'
        click([1000,1000]);assert {s['layer'] for s in w.cell['shapes']}=={'li','mcon','m1'},errors
        w.editor_via.setCurrentText('M1 to M2');click([2000,1000])
        assert {s['layer'] for s in w.cell['shapes'][-3:]}=={'m1','via','m2'},errors
        checks.append('Changing the SKY130 via dropdown changes the placed cut and conductors immediately')
        old=clone(w.project['cells']);w.layout.locked_layers.add('via');click([3000,1000])
        assert w.project['cells']==old and 'Unlock' in errors.pop()
        w.layout.locked_layers.clear();w.cancel_tool()
        dlg=w.via_dialog();dlg.fields['placement'].setCurrentText('Coordinates')
        dlg.fields['connection'].setCurrentText('Local interconnect to M1')
        dlg.fields['x'].setText('3');dlg.fields['y'].setText('1');accept(dlg)
        assert {s['layer'] for s in w.cell['shapes'][-3:]}=={'li','mcon','m1'}
        assert polygon(w.cell['shapes'][-2]).bbox().center()==kdb().Point(3000,1000)
        checks.append('Locked layers reject canvas clicks atomically; coordinate dialog places the chosen via')

        p=example('empty');cell=p['cells'][0]
        cell['shapes']=[rect('metal1',0,0,2000,1000,net='signal'),
                        rect('metal2',500,-500,1000,2000,net='signal')]
        setup(p);ids=[s['id'] for s in w.cell['shapes']];w.select(ids,'layout')
        before=clone(w.project['cells'])
        auto=next(button for button,tool in w.ribbon_buttons if button.text()=='Autovia' and button.isVisible())
        QTest.mouseClick(auto,Qt.LeftButton);app.processEvents()
        dlg=next(d for d in app.topLevelWidgets() if d.windowTitle()=='Autovia' and d.isVisible());accept(dlg)
        preview=w._layout_proposal_dialog
        assert preview.windowTitle()=='Autovia preview' and w.project['cells']==before
        QTest.qWait(100);assert preview.grab().save(str(out/'autovia-preview.png'))
        button=next(b for b in preview.findChildren(QPushButton) if b.text()=='Place vias')
        QTest.mouseClick(button,Qt.LeftButton);QTest.qWait(100)
        assert len(w.cell['shapes'])==29,errors
        assert len(set(partition(w.project,w.cid).values()))==1
        after=clone(w.project['cells']);w.undo();assert w.project['cells']==before
        w.redo();assert w.project['cells']==after
        save_project(w.project,out/'autovia.icproj');w.set_project(load_project(out/'autovia.icproj'))
        assert w.project['cells']==after and len(set(partition(w.project,w.cid).values()))==1
        w.mode_combo.setCurrentIndex(1);w.layout.fit();QTest.qWait(100)
        assert w.grab().save(str(out/'autovia-editor.png'))
        checks.append('Autovia preview is non-mutating; Place vias connects the overlap with nine vias')
        checks.append('Autovia is one undoable edit and survives native save/reopen')
        if args.project:
            from icstudio.layout_edit import via_options
            from icstudio.design_ops import flatten_layout
            p=load_project(args.project);cid=next(c['id'] for c in p['cells'] if c['name']=='level_shifter')
            setup(p);w.cid=cid;w.refresh();QTest.qWait(100)
            a,cut,b,_,_=via_options(w.project)['M1 to M2']
            masks={l['name']:(l['gds'],l['datatype']) for l in p['pdk']['layers']}
            assert [masks[n] for n in (a,cut,b)]==[(68,20),(68,44),(69,20)]
            box=kdb().Region([polygon(s) for s in flatten_layout(p,cid)]).bbox()
            x=((box.right+10000)//1000)*1000;y=((box.top+10000)//1000)*1000
            w.layout.auto_fit=False;w.layout.scale=.3;w.layout.offset=QPointF(150-x*.3,150-y*.3)
            before=clone(w.project['cells']);QTest.mouseClick(via_button(),Qt.LeftButton);click([x,y])
            assert {s['layer'] for s in w.cell['shapes'][-3:]}=={a,cut,b},errors
            w.undo();assert w.project['cells']==before;w.cancel_tool()
            def crossing(q):
                c=next(c for c in q['cells'] if c['id']==cid)
                c['shapes'] += [rect(layer,x,y,1000,1000,net='autovia_probe') for layer in (a,b)]
            w.commit(crossing,'Test overlap');ids=[s['id'] for s in w.cell['shapes'][-2:]];w.select(ids,'layout')
            before=clone(w.project['cells']);dlg=w.autovia_dialog();accept(dlg);preview=w._layout_proposal_dialog
            button=next(b for b in preview.findChildren(QPushButton) if b.text()=='Place vias')
            QTest.mouseClick(button,Qt.LeftButton);app.processEvents()
            placed=[s for s in w.cell['shapes'] if s not in next(c for c in before if c['id']==cid)['shapes']]
            assert len(placed)==27 and {s['layer'] for s in placed}=={a,cut,b},errors
            groups=partition(w.project,cid)
            assert groups[('shape',ids[0],'','')]==groups[('shape',ids[1],'','')]
            w.undo();assert w.project['cells']==before
            checks.append('GitHub overvoltage artifact: manual vias and Autovia use real SKY130 masks in level_shifter; undo preserves imported cells')
        assert not errors,errors
        report['status']='passed'
    except Exception:
        report.update(status='failed',error=traceback.format_exc(),errors=errors)
    finally:
        if w:w.saved_hash=digest(w.project);w.close();app.processEvents()
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
