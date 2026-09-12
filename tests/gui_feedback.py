"""Real desktop interactions for the component/library and panel feedback."""
import argparse
import json
import sys
import traceback
from pathlib import Path
from unittest.mock import patch


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import Qt,QPoint,QPointF,QSettings,QTimer
    from PySide6.QtWidgets import QApplication,QDialogButtonBox,QMenu
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import example,device,clone,uid,save_project,load_project
    from icstudio.symbol_io import default_symbol
    from icstudio.native_migration import review_path
    from icstudio.xschem_compat import review_project
    from icstudio.xschem_project import apply_review
    from test_xschem_compatible import fixture
    from test_layout_expansion import HierarchyECO
    app=QApplication([]);app.setStyle('Fusion');errors=[];checks=[];w=None
    sys.excepthook=lambda t,v,tb:(errors.append(str(v)),traceback.print_exception(t,v,tb))
    report={'checks':checks,'qt_platform':app.platformName()}
    try:
        settings=QSettings(str(out/'settings.ini'),QSettings.IniFormat);settings.setFallbacksEnabled(False);settings.clear()
        with patch('icstudio.gui.QSettings',return_value=settings),patch('icstudio.gui.QStandardPaths.writableLocation',return_value=str(out/'data')):
            w=Studio(recover=False)
        w.error=lambda e:errors.append(str(e));w.maybe_save=lambda:True;w.live_check.setChecked(False)
        w.resize(1400,980);w.show();assert QTest.qWaitForWindowExposed(w);QTest.qWait(180)
        def setup(project):
            w.cancel_tool();w.set_project(project);w.mode_combo.setCurrentIndex(0);QTest.qWait(80)
        def click(point,button=Qt.LeftButton,modifiers=Qt.NoModifier):
            pos=(w.schematic.offset+QPointF(*point)*w.schematic.scale).toPoint()
            QTest.mouseClick(w.schematic,button,modifiers,pos);app.processEvents()
        def accept(dlg):
            dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click();app.processEvents()

        # Standard library: source and category combine; no-results clears preview.
        p=example('empty');p['cells'].append(dict(id='custom',name='Custom_amplifier',ports=['in','out'],devices=[],shapes=[],symbol=default_symbol(['in','out'])))
        setup(p);w.show_library();w.library_source.setCurrentText('Project cells');w.library_category.setCurrentText('All devices')
        assert w.library_list.currentItem().data(Qt.UserRole)=={'cell':'custom'}
        assert w.capture_preview_label.symbol==p['cells'][1]['symbol']
        w.library_search.setText('no matching component');assert w.library_list.currentItem() is None and w.capture_preview_label.symbol is None
        assert not w.place_library_button.isEnabled()
        w.library_search.clear();w.library_source.setCurrentText('Generic components');w.library_search.setText('Resistor')
        assert w.capture_preview_label.symbol
        w.place_library_button.click();assert w.schematic.placement['kind']=='R';w.cancel_tool()
        print('Completed check',len(checks)+1,flush=True)
        checks.append('Standard source/category/search filters, hierarchical preview and empty-result placement guard')

        # Original and migrated symbol libraries both use the filtered preview dialog.
        path=fixture(out/'source');native=review_path(path)['candidate'];assert native
        definitions=[d for c in native['cells'] for d in c['devices'] if d.get('native_spice',{}).get('type')=='device']
        definitions[0]['component_source']='Library A'
        definitions[1]['component_source']='Library B'
        duplicate=clone(definitions[1]);duplicate.update(id=uid(),name='R99',x=600)
        duplicate['component_source']='Library A';native['cells'][0]['devices'].append(duplicate)
        setup(native);w.show_library();dlg=w._native_library_dialog
        assert {'Library A','Library B'}<={dlg.source.itemText(i) for i in range(dlg.source.count())}
        dlg.source.setCurrentText('Library B');dlg.search.setText(definitions[1]['native_spice']['label'])
        assert dlg.selected_entry()['source']=='Library B' and dlg.preview.symbol==definitions[1]['symbol']
        dlg.grab().save(str(out/'component-browser-dark.png'))
        dlg.search.setText('no matches');assert dlg.preview.symbol is None and not dlg.place_button.isEnabled()
        dlg.search.clear();dlg.place_button.click();assert w.schematic.placement['component_source']=='Library B';w.cancel_tool()
        setup(apply_review(review_project(path)));w.show_library();dlg=w._xschem_library_dialog
        dlg.source.setCurrentText('Xschem');dlg.search.setText('res');assert dlg.selected_entry()['source']=='Xschem' and dlg.preview.symbol
        dlg.source.setCurrentText('GF180MCU');assert dlg.selected_entry() is None
        dlg.search.setText('nfet');assert dlg.selected_entry()['source']=='GF180MCU' and dlg.preview.symbol
        dlg.grab().save(str(out/'xschem-component-browser.png'))
        dlg.place_button.click();assert 'nfet' in w.schematic.placement['xschem']['reference'];w.cancel_tool()
        print('Completed check',len(checks)+1,flush=True)
        checks.append('Native and Xschem library filtering, duplicate labels in different sources, symbol preview and placement')

        # Wire close to a component body: normal click selects wire, cycle selects device.
        p=example('empty');c=p['cells'][0];d=device('R','R1',0,0);c['devices']=[d]
        c['wires']=[dict(id='overlap-wire',points=[[-40,40],[40,40]])]
        setup(p);w.schematic.auto_fit=False;w.schematic.scale=2;w.schematic.offset=QPointF(180,180)
        click([0,40]);assert w.selection==['overlap-wire'],w.selection
        click([0,40],modifiers=Qt.AltModifier);assert w.selection==[d['id']],w.selection
        w.schematic.capture_filters={'devices'};click([0,40]);assert w.selection==[d['id']]
        w.schematic.capture_filters={'wires'};click([0,40]);assert w.selection==['overlap-wire']
        w.schematic.capture_filters={'devices','wires','labels','annotations'}
        print('Completed check',len(checks)+1,flush=True)
        checks.append('Wire-first pointer selection preserves overlap cycling and explicit selection filters')

        # Actual right-click path includes hierarchy commands and active key bindings.
        p=HierarchyECO().fixture();setup(p);w.schematic.auto_fit=False;w.schematic.scale=1;w.schematic.offset=QPointF(180,180)
        first=w.cell['devices'][0];w.select([first['id']],'schematic');w.set_capture_profile('Studio')
        QTimer.singleShot(50,lambda:w._canvas_context_menu.close());click([first['x'],first['y']],button=Qt.RightButton)
        menu=w._canvas_context_menu;action=next(a for a in menu.actions() if a.text().startswith('Enter schematic'))
        assert action.text().endswith('\tE');action.trigger();assert w.cid=='leaf'
        QTimer.singleShot(50,lambda:w._canvas_context_menu.close());click([120,120],button=Qt.RightButton)
        next(a for a in w._canvas_context_menu.actions() if a.text().startswith('Return to parent')).trigger();assert w.cid==p['top']
        print('Completed check',len(checks)+1,flush=True)
        checks.append('Right-click enter schematic/return to parent uses the existing navigation stack and displays the active shortcut')

        # Bulk transfer exercises the public command, reviewed Apply, undo and persistence.
        setup(p);before=clone(w.project['cells']);dlg=w.place_schematic_in_layout()
        assert dlg.table.rowCount()==3 and all(dlg.table.item(i,0).checkState()==Qt.Checked for i in range(3))
        dlg.grab().save(str(out/'schematic-to-layout.png'))
        dlg.preview_button.click();accept(w._review_dialog)
        assert len(w.project['cells'][0]['layout_instances'])==2 and len(w.project['cells'][1]['parametric_devices'])==1,errors
        after=clone(w.project['cells']);w.undo();assert w.project['cells']==before;w.redo();assert w.project['cells']==after
        saved=out/'transferred.icproj';save_project(w.project,saved);assert load_project(saved)['cells']==after
        dlg=w.place_schematic_in_layout();assert all(dlg.table.item(i,0).checkState()==Qt.Unchecked for i in range(dlg.table.rowCount()));dlg.close()
        print('Completed check',len(checks)+1,flush=True)
        checks.append('All missing hierarchy devices placed once with reviewed Apply, undo/redo, save/reopen and no duplicate placement')

        # A native frame supplies edges; the visible size grip supplies diagonal resizing.
        dock=w.results_dock;dock.show();dock.setFloating(True);QTest.qWait(100)
        assert dock.titleBarWidget() is None and not dock.windowFlags()&Qt.FramelessWindowHint
        grip=dock._floating_frame.grip;assert grip.isVisible()
        dock.move(20,20);dock.resize(480,360);QTest.qWait(30);start=dock.size();point=QPoint(7,7)
        QTest.mousePress(grip,Qt.LeftButton,Qt.NoModifier,point)
        QTest.mouseMove(grip,point+QPoint(60,45),30)
        QTest.mouseRelease(grip,Qt.LeftButton,Qt.NoModifier,point+QPoint(60,45));app.processEvents()
        assert dock.width()>start.width() and dock.height()>start.height(),(start,dock.size())
        dock.grab().save(str(out/'floating-results.png'))
        for _ in range(3):
            dock.setFloating(False);app.processEvents();assert dock.titleBarWidget() is not None and not grip.isVisible()
            dock.setFloating(True);app.processEvents();assert dock.titleBarWidget() is None and grip.isVisible()
        w.save_editor_workspace('Floating feedback');dock.setFloating(False);w.load_editor_workspace('Floating feedback');app.processEvents()
        assert dock.isFloating() and dock.titleBarWidget() is None and grip.isVisible()
        dock.setFloating(False)
        print('Completed check',len(checks)+1,flush=True)
        checks.append('Floating native border, real diagonal size-grip drag, repeated dock/undock and saved floating workspace restoration')
        assert not errors,errors
        report['status']='passed'
    except Exception:
        report['status']='failed';report['traceback']=traceback.format_exc();raise
    finally:
        (out/'report.json').write_text(json.dumps(report,indent=2))
        if w:w.close();app.processEvents()
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
