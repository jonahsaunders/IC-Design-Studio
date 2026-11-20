"""Contextual commands resolve their evidence at invocation, including keyboard selection."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QPushButton
from . import ai_investigation as investigation


def context_menu(widget, resolve, ask, follow=None):
    def popup(point):
        item = widget.itemAt(point) if point.x() >= 0 else widget.currentItem()
        if item is not None:
            widget.setCurrentItem(item)
            if point.x() < 0:
                point = widget.visualItemRect(item).center()
        args = resolve(item) if item else None
        menu = QMenu(widget)
        action = menu.addAction('Ask About This…')
        action.setEnabled(bool(args))
        link=menu.addAction('Follow in Layout Assistant…') if follow and args else None
        picked=menu.exec(widget.viewport().mapToGlobal(point))
        if picked == action and args:
            ask(**args)
        elif link is not None and picked==link:
            follow(**args)
    widget.setContextMenuPolicy(Qt.CustomContextMenu)
    widget.customContextMenuRequested.connect(popup)


def row_for_result(studio, result):
    if result:
        for row in reversed(studio.run_manager.rows):
            if row.get('result') is result:
                return row
        keys = ('project_id','cell_id','design_hash','created','deck_hash')
        if result.get('created') and result.get('design_hash'):
            matches = [r for r in studio.run_manager.rows if r.get('result') and
                       all(r['result'].get(k) == result.get(k) for k in keys)]
            if len(matches)==1:
                return matches[0]


def install(studio, show):
    def ask_layout(marker=None,selection=None):
        if marker and marker.get('source_design_hash'):
            from .model import design_digest
            if marker['source_design_hash']!=design_digest(studio.project):
                studio.statusBar().showMessage('This finding is stale. Run the layout check again.')
                return
        if not studio.flush_inspector():return
        panel = show()
        panel.cancel()
        panel.reset_context()
        panel.action.blockSignals(True)
        panel.action.setCurrentIndex(panel.action.findData('layout'))
        panel.action.blockSignals(False)
        panel.note.clear()
        panel.call_local(lambda:panel.layout_tools.reload(marker,selection))
        panel.refresh()
        panel.note.setFocus()
        return panel
    studio.ask_layout = ask_layout
    def finding(item,live):
        rows = getattr(studio,'_live_findings',[]) if live else studio.issues
        revision = getattr(studio,'_live_revision',None) if live else studio.check_revision
        if revision!=studio.project['revision'] or item.row()>=len(rows):return
        if live and getattr(studio,'_live_context',None)!=(studio.project['id'],revision,studio.cid):return
        row=rows[item.row()]
        if not live and not (row.get('bbox') or row.get('shape_ids') or
                             row.get('object') in {s['id'] for s in studio.cell['shapes']}):return
        return dict(marker=row)
    def inspect_marker(marker):
        from .model import design_digest
        if marker.get('source_design_hash') and marker['source_design_hash']!=design_digest(studio.project):return
        if not studio.flush_inspector():return
        cid=marker.get('cell_id') or studio.cid
        if cid!=studio.cid:
            if cid not in {c['id'] for c in studio.project['cells']}:return
            studio.cid=cid
            studio.refresh()
        ask_layout(marker)
    context_menu(studio.checks,lambda item:finding(item,False),inspect_marker)
    context_menu(studio.live_table,lambda item:finding(item,True),inspect_marker)
    def ask(row=None, requirement=None, probe=None, device=None, *, edit=False):
        if not row and not studio.flush_inspector():
            return
        panel = show()
        panel.call_local(lambda:panel.investigate(row,requirement,probe,device,edit))
        panel.note.setFocus()
        studio.raise_()
        studio.activateWindow()
        return panel
    studio.ask_about = ask
    def selected(*_):
        panel = getattr(studio,'_ai_assistant',None)
        if panel and panel.action.currentData()=='edit' and not panel.pinned and panel.reply is None:
            panel.update_preview()
    studio.schematic.selected.connect(selected)
    def wave_args(item=None):
        row = row_for_result(studio, studio.result)
        if not row:
            return None
        item = item or studio.traces.currentItem()
        name = item.text() if item else next(iter(studio.plot.names),'')
        result = row['result']
        return dict(row=row,probe=('voltage',name)) if name in result.get('traces',{}) else None
    def wave():
        args = wave_args()
        if args:
            ask(**args)
        else:
            studio.statusBar().showMessage('Select a trace from a saved simulation run.',6000)
    button = QPushButton('Ask About This…')
    button.setAccessibleName('Ask about selected waveform')
    button.clicked.connect(wave)
    studio.run_combo.parentWidget().layout().addWidget(button)
    button.setEnabled(False)
    def sync_wave(*_):
        button.setEnabled(bool(wave_args()))
    studio.plot.result_changed.connect(sync_wave)
    studio.traces.currentRowChanged.connect(sync_wave)
    def follow_wave(row,probe):
        from .model import design_digest
        job=row['job']
        if job['cell']!=studio.cid or design_digest(job['project'])!=design_digest(studio.project):
            studio.statusBar().showMessage('Open the saved circuit revision to follow this waveform into layout.')
            return
        panel=ask_layout()
        if panel:
            panel.call_local(lambda:panel.layout_tools.follow_wave(row,probe[1]))
    context_menu(studio.traces,wave_args,ask,follow_wave)
    def simulation(item):
        row = next((r for r in studio.run_manager.rows if r['id']==item.data(Qt.UserRole)),None)
        return dict(row=row) if row else None
    context_menu(studio.simulation_runs,simulation,ask)
    def measurement(widget, result, item):
        row = row_for_result(studio,result)
        name = widget.item(item.row(),0).text()
        if row and investigation.saved_check(row,name):
            return dict(row=row,requirement=name)
    context_menu(studio.spec_results,lambda item:measurement(studio.spec_results,studio.result,item),ask)
    context_menu(studio.bench_measurements,lambda item:measurement(studio.bench_measurements,getattr(studio,'_bench_result',None),item),ask)


def install_matrix(window):
    def selected(item):
        row = next((r for r in window.studio.run_manager.rows if r['id']==item.data(Qt.UserRole)),None)
        definition = item.data(Qt.UserRole+1) or {}
        return dict(row=row, requirement=definition.get('name')) if row else None
    def ask(**args):
        window.hide()
        window.studio.ask_about(**args)
    context_menu(window.table,selected,ask)


def install_inspector(window, row, selector_layout):
    if not row.get('id') or not hasattr(window.studio, 'ask_about'):
        return
    def ask(**args):
        window.hide()
        window.studio.ask_about(row=row, **args)
    button = QPushButton('Ask About This…')
    button.setAccessibleName('Ask about this saved waveform')
    button.clicked.connect(lambda:ask(probe=window.probe.currentData()))
    selector_layout.addWidget(button)
    context_menu(window.requirements,lambda it:dict(requirement=window.requirement_rows[it.row()]['name']),ask)
    def follow_device(device):
        from .model import design_digest
        studio=window.studio
        if design_digest(row['job']['project'])!=design_digest(studio.project):
            window.note.setText('Open the saved circuit revision to follow this device into layout.')
            return
        record=next((d for d in window.device_rows if d['name']==device),None)
        if not record or not studio.flush_inspector():return
        if studio.cid!=record['cell_id']:
            studio.cid=record['cell_id']
            studio.refresh(True)
        window.hide()
        studio.ask_layout(selection=[record['object']])
    context_menu(window.devices,lambda it:dict(device=window.device_rows[it.row()]['name']),ask,follow_device)
