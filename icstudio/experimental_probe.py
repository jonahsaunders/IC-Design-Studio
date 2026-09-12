"""Desktop gestures shared by source, frozen packages and native acceptance."""
import time
from pathlib import Path


def run(w, output):
    from PySide6.QtCore import Qt,QPoint,QPointF,QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from .component_browser import ComponentBrowser
    from .component_preferences import ComponentPreferences
    from .symbol_io import default_symbol
    from .model import clone,example,device,save_project,load_project
    from .build_identity import diagnostic_report
    out=Path(output)/'experimental';out.mkdir(parents=True,exist_ok=True)
    before=clone(w.project);path=w.path;checks=[]
    app=QApplication.instance()
    def move(widget, point):
        assert widget.isVisible() and widget.window().childAt(widget.mapTo(widget.window(),point)) is widget
        if app.platformName() in ('offscreen','minimal'):
            # These backends need explicit hover events; they have no real cursor.
            app.sendEvent(widget,QMouseEvent(QEvent.MouseMove,QPointF(point),QPointF(widget.mapToGlobal(point)),Qt.NoButton,Qt.NoButton,Qt.NoModifier))
        else:
            QTest.mouseMove(widget,point);QTest.qWait(20)
    def wait(predicate, label, timeout=10):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            QTest.qWait(10)
        raise AssertionError(label)
    try:
        w.workflow_dock.hide();w.results_dock.hide();w.set_project(example('empty'))
        scope='desktop-probe-symbols';prefs=ComponentPreferences(w.settings,scope);w.settings.remove(prefs.key)
        entries=[dict(label=f'Device {i//2:05d}',source='Library B' if i%2 else 'Library A',key=str(i)) for i in range(10000)]
        symbol=default_symbol(['in','out']);loads=[];placed=[]
        def preview(entry):loads.append(entry['key']);return symbol,{}
        def browser():return ComponentBrowser(w,'Component acceptance',entries,preview,lambda e:placed.append(e['key']),scope=scope)
        start=time.perf_counter();dlg=browser();dlg.show();QTest.qWait(20);open_ms=(time.perf_counter()-start)*1000
        dlg.source.setCurrentText('Library B');dlg.search.setText('Device 0010');dlg.filter()
        first=dlg.selected_entry()['key'];dlg.favorite.click();assert dlg.preview.symbol
        dlg.search.setFocus();QTest.keyClick(dlg.search,Qt.Key_Down)
        second=dlg.selected_entry()['key'];assert second!=first
        QTest.keyClick(dlg.search,Qt.Key_Return);assert placed==[second]
        dlg=browser();dlg.show();assert dlg.source.currentText()=='Library B'
        dlg.collection.setCurrentText('Favorites');assert dlg.selected_entry()['key']==first
        dlg.collection.setCurrentText('Recently placed');assert dlg.selected_entry()['key']==second
        dlg.collection.setCurrentText('All components');dlg.search.setText('Device 0010')
        start=time.perf_counter();dlg.filter();filter_ms=(time.perf_counter()-start)*1000
        loaded=len(loads);dlg.show_preview();dlg.show_preview();assert len(loads)==loaded
        dlg.search.setText('no matching component');QTest.keyClick(dlg.search,Qt.Key_Return)
        assert placed==[second] and dlg.preview.symbol is None and not dlg.place_button.isEnabled()
        dlg.search.setText('Device 0010');dlg.filter();dlg.grab().save(str(out/'component-browser.png'));dlg.close()
        checks.append('10,000 component entries: source persistence, isolated favorites, recent choices, keyboard placement, cached previews and empty-result guard')

        w.show_library();w.library_source.setCurrentText('Generic components');w.library_search.setText('Resistor')
        w.library_collection.setCurrentText('All components')
        if w.library_list.currentItem().data(Qt.UserRole+5) not in w.component_preferences.favorites:w.library_favorite.click()
        w.library_collection.setCurrentText('Favorites');assert w.library_list.currentItem()
        w.library_search.setFocus();QTest.keyClick(w.library_search,Qt.Key_Return)
        assert w.schematic.placement['kind']=='R';w.cancel_tool();w.library_collection.setCurrentText('All components');w.library_search.clear()
        checks.append('Standard component library supports favorite filtering and Enter placement from search')

        p=example('empty');cell=p['cells'][0];resistor=device('R','R1',0,0);cell['devices']=[resistor]
        cell['wires']=[dict(id='overlap-wire',points=[[-40,40],[40,40]])]
        w.set_project(p);w.mode_combo.setCurrentIndex(0);canvas=w.schematic
        canvas.auto_fit=False;canvas.scale=1.5;canvas.offset=QPointF(180,100);app.processEvents()
        point=(canvas.offset+QPointF(0,40)*canvas.scale).toPoint()
        move(canvas,point);app.processEvents();assert canvas.preselection['id']=='overlap-wire'
        assert '2 overlapping' in canvas.selection_hint
        QTest.mouseClick(canvas,Qt.LeftButton,Qt.NoModifier,point);assert w.selection==['overlap-wire']
        QTest.keyClick(canvas,Qt.Key_Tab);assert w.selection==[resistor['id']]
        assert 'Click: Wire' in canvas.selection_hint
        canvas.grab().save(str(out/'selection-preview.png'))
        canvas.capture_filters={'devices'};move(canvas,point+QPoint(1,0));assert canvas.preselection['id']==resistor['id']
        canvas.capture_filters={'devices','wires','labels','annotations'}
        canvas.fit();assert canvas.preselection is None and not canvas.selection_hint
        checks.append('Hover and click agree at overlapping wire/device geometry; Tab cycles and filtering changes the preview')

        guide=w.design_workflow();wait(lambda:guide.analysis is not None,'Workflow inspection')
        assert 'missing devices' in guide.summary.text() and w.workflow_dock.isVisible()
        guide.tabs.setCurrentIndex(1);row=next(i for i,r in enumerate(guide.finding_rows) if r.get('device_id')==resistor['id'])
        guide.finding_table.selectRow(row);guide.go_to_finding();assert w.selection==[resistor['id']]
        guide.grab().save(str(out/'design-workflow.png'))
        w.save_editor_workspace('Experimental acceptance');w.workflow_dock.hide();w.load_editor_workspace('Experimental acceptance')
        assert w.workflow_dock.isVisible() and w.design_workflow() is guide
        wait(lambda:guide.analysis is not None,'Workflow restoration')
        w.commit(lambda q:q.update(name='Changed while findings open'),'Rename')
        try:guide.go_to_finding()
        except ValueError:pass
        else:raise AssertionError('Stale findings remained navigable')
        wait(lambda:guide.analysis_key and guide.analysis_key[1]==w.project['revision'],'Automatic workflow refresh')
        checks.append('Persistent workflow restores with the workspace, navigates findings, rejects stale rows and refreshes after edits')

        dock=w.results_dock;dock.show();dock.setFloating(True);dock.move(30,30);dock.resize(480,320);QTest.qWait(50)
        assert dock.titleBarWidget() is None and dock._floating_frame.border.isVisible()
        # Qt deliberately provides its own title bar on X11/Wayland.
        if app.platformName()!='xcb' and not app.platformName().startswith('wayland'):
            assert not dock.windowFlags()&Qt.FramelessWindowHint
        from .ui_style import palette
        from PySide6.QtGui import QColor
        pixels=dock.grab().toImage();edge=QColor(palette(w.dark)['muted'])
        for x,y in ((0,pixels.height()//2),(pixels.width()-1,pixels.height()//2),
                    (pixels.width()//2,0),(pixels.width()//2,pixels.height()-1)):
            assert pixels.pixelColor(x,y)==edge,('Floating border is not visible',x,y,pixels.pixelColor(x,y).name())
        grip=dock._floating_frame.grip;size=dock.size();pos=QPoint(7,7)
        QTest.mousePress(grip,Qt.LeftButton,Qt.NoModifier,pos);QTest.mouseMove(grip,pos+QPoint(70,55),30)
        QTest.mouseRelease(grip,Qt.LeftButton,Qt.NoModifier,pos+QPoint(70,55));app.processEvents()
        assert dock.width()>size.width() and dock.height()>size.height()
        saved=dock.geometry();w.save_editor_workspace('Experimental floating acceptance');dock.setFloating(False)
        w.load_editor_workspace('Experimental floating acceptance');QTest.qWait(50)
        assert dock.isFloating() and dock.titleBarWidget() is None and grip.isVisible()
        assert (dock.size()-saved.size()).width() in range(-8,9)
        dock.move(-20000,-20000);dock._floating_frame.keep_visible()
        assert any(screen.availableGeometry().intersects(dock.geometry()) for screen in app.screens())
        dock.grab().save(str(out/'floating-results.png'));dock.setFloating(False);dock.hide()
        checks.append('Visible floating border on all four edges, platform title bar, diagonal resize, saved size restoration and recovery of an offscreen window')
        target=out/'Project with spaces.icproj';save_project(w.project,target);restored=load_project(target)
        assert restored==w.project
        (out/'diagnostics.json').write_text(diagnostic_report(),encoding='utf-8')
        return dict(checks=checks,component_open_ms=open_ms,component_filter_ms=filter_ms,qt_platform=app.platformName())
    finally:
        w.cancel_tool();w.set_project(before,path)
