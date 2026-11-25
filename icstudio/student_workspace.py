"""Local lesson bookmarks, snapshots, and separate blank practice projects."""

import json
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QSignalBlocker, QTimer, Qt
from PySide6.QtWidgets import QInputDialog, QMessageBox

from .model import clone, digest, load_project, save_project


def _settings(guide, kind):
    return f'student/{kind}/{guide.studio.project["id"]}/{guide.lesson["id"]}'


def _read(guide, kind, default):
    try:
        return json.loads(guide.studio.settings.value(_settings(guide,kind), '', str))
    except (ValueError, TypeError):
        return default


def _save(guide, kind, value):
    guide.studio.settings.setValue(_settings(guide,kind),json.dumps(value))


def capture_view(guide):
    studio = guide.studio
    view = {key: [canvas.scale, canvas.offset.x(), canvas.offset.y()]
            for key,canvas in (('schematic',studio.schematic),('layout',studio.layout))}
    dialog = getattr(guide,'signal_results',None)
    plot = studio.plot
    signal = None
    if dialog is not None and dialog.isVisible():
        plot = dialog.plot
        signal = dict(run=dialog.run_path, case=dialog.case.currentIndex(), trace=dialog.trace.currentText())
    result = studio.result
    return dict(step=guide.active_step['id'], cell=studio.cid, mode=studio.mode_combo.currentIndex(),
                selection=list(studio.selection), view=view,
                result={'created':result.get('created'),'hash':digest(result)} if result else None,
                signal=signal, cursors=[plot.a,plot.b], traces=list(plot.names),
                show_results=studio.results_dock.isVisible())


def _restore_canvas(canvas, values):
    if (isinstance(values,list) and len(values)==3 and
            all(isinstance(x,(int,float)) and math.isfinite(x) for x in values) and 0 < values[0] < 1e5):
        canvas.scale, x, y = values
        canvas.offset = QPointF(x,y)
        canvas.auto_fit = False
        canvas.update()


def restore_view(guide, context):
    if not isinstance(context,dict):
        return
    studio = guide.studio
    project_id, lesson_id = studio.project['id'], guide.lesson['id']
    step = next((i for i,s in enumerate(guide.lesson['steps']) if s['id']==context.get('step')),None)
    if step is not None:
        guide.steps.setCurrentIndex(step)
    cell = next((cell for cell in studio.project['cells'] if cell['id']==context.get('cell')),None)
    if cell is not None:
        # Keep the saved cell for schematic/layout. RTL lessons retain their normal workspace.
        from .digital_design import config
        if studio.project.get('mixed_signal') or not config(studio.project,studio.project['top']):
            studio.cid=cell['id']
            if context.get('mode') in (0,1,2):
                studio.mode_combo.setCurrentIndex(context['mode'])
            known={o['id'] for group in ('devices','wires','shapes','annotations','labels','layout_instances')
                   for o in cell.get(group,())}
            studio.selection=[key for key in context.get('selection',()) if key in known]
            studio.refresh()
    def late_restore():
        if studio.project['id']!=project_id or not guide.lesson or guide.lesson['id']!=lesson_id:
            return
        if step is not None and guide.steps.currentIndex()!=step:
            return
        for key,canvas in (('schematic',studio.schematic),('layout',studio.layout)):
            _restore_canvas(canvas, context.get('view',{}).get(key))
        plot = studio.plot
        signal = context.get('signal')
        if signal:
            from .student_signal_ui import SignalResults
            row = next((row for row in guide.step_run_rows(guide.lesson_rows())
                        if str(row['path'])==signal.get('run') and row.get('result')),None)
            if row is not None:
                guide.signal_results=SignalResults(studio,row)
                dialog=guide.signal_results
                dialog.case.setCurrentIndex(min(signal.get('case',0),dialog.case.count()-1))
                dialog.trace.setCurrentText(signal.get('trace',''))
                dialog.show()
                plot=dialog.plot
        elif saved:=context.get('result'):
            index=next((i for i,r in enumerate(studio.jobs)
                        if r.get('created')==saved['created'] and digest(r)==saved['hash']),None)
            if index is not None:
                studio.run_combo.setCurrentIndex(index)
                if 'traces' in context:
                    with QSignalBlocker(studio.traces):
                        for i in range(studio.traces.count()):
                            item=studio.traces.item(i)
                            item.setCheckState(Qt.Checked if item.text() in context['traces'] else Qt.Unchecked)
                    studio.update_plot()
                if context.get('show_results'):
                    studio.results_dock.show()
                    studio.results_tabs.setCurrentIndex(0)
        if plot.result and isinstance(context.get('cursors'),list) and len(context['cursors'])==2:
            plot.a, plot.b = context['cursors']
            plot.update()
    QTimer.singleShot(80,late_restore)


def bookmark(guide):
    guide.require_idle()
    view=capture_view(guide)
    if guide.save_work():
        _save(guide,'bookmark',view)
        guide.feedback.setText('Bookmarked this checkpoint, view, and available waveform cursors.')


def restore_bookmark(guide, *, required=False):
    state = _read(guide,'bookmark',None)
    if state is None and required:
        raise ValueError('Set a bookmark in this lesson first.')
    if state is not None:
        restore_view(guide,state)


def savepoint(guide):
    from .project_versions_ui import version_store
    guide.flush()
    guide.require_idle()
    name, ok = QInputDialog.getText(guide,'Name this savepoint','Savepoint name')
    name = name.strip()
    if not ok or not name:
        return
    store=version_store(guide.studio)
    if any(item.name.casefold()==name.casefold() for item in store.list()):
        raise ValueError('A savepoint with that name already exists.')
    version=store.save(guide.studio.project,name)
    _save(guide,'versionView/'+version.id,capture_view(guide))
    guide.feedback.setText(f'Savepoint saved · {name}')


def restore_savepoint(guide):
    from .project_versions import restore_contents
    from .project_versions_ui import version_store
    guide.flush()
    guide.require_idle()
    store=version_store(guide.studio)
    items={f'{row.name} · {row.created[:19]} · {row.id[:8]}':row for row in store.list()}
    if not items:
        raise ValueError('Save a named version of this lesson first.')
    name,ok=QInputDialog.getItem(guide,'Restore a savepoint','Savepoint',list(items),0,False)
    if not ok:
        return
    item=items[name]
    snapshot=store.load(item.id)
    if QMessageBox.question(guide,'Restore savepoint?',f'Restore {name}? Use Undo to recover the current design.',
                            QMessageBox.Yes|QMessageBox.Cancel, QMessageBox.Cancel)!=QMessageBox.Yes:
        return
    guide.studio.commit(lambda p:restore_contents(p,snapshot),f'Restore savepoint · {item.name}')
    restore_view(guide,_read(guide,'versionView/'+item.id,None))


def starter_path(hub, project_id):
    return hub.portfolio.root/'starters'/(project_id+'.icproj')


def _one_device(project, current_cell, current_device):
    cell = next((item for item in project['cells'] if item['id']==current_cell['id']),None)
    if cell is None:
        cell=next((item for item in project['cells'] if item['name']==current_cell['name']),None)
    if cell is None:
        return None
    return next((d for d in cell['devices'] if d['id']==current_device['id']),None) or next(
        (d for d in cell['devices'] if d['name']==current_device['name'] and d['kind']==current_device['kind']),None)


def starter_fields(current, original):
    """Enumerate scalar editable values without changing nets, models, or geometry."""
    fields={}
    for prefix in ((),('params',),('source',),('model_params',),('native_spice','parameters')):
        left,right=current,original
        for key in prefix:
            left,right=left.get(key,{}),right.get(key,{})
        for key,a in left.items():
            if not prefix and key!='value':
                continue
            b=right.get(key)
            if key!='type' and isinstance(a,(int,float,str)) and isinstance(b,(int,float,str)) and a!=b:
                fields[(*prefix,key)]=(a,b)
    return fields


def restore_starter_value(guide):
    guide.flush()
    guide.require_idle()
    studio=guide.studio
    selected=[d for d in studio.cell['devices'] if d['id'] in studio.selection]
    if len(selected)!=1:
        raise ValueError('Select one schematic component first.')
    current=selected[0]
    path=starter_path(guide.hub,studio.project['id'])
    starter=load_project(path) if path.is_file() else guide.hub.make_starter(guide.lesson)
    original=_one_device(starter,studio.cell,current)
    if original is None or original['kind']!=current['kind']:
        raise ValueError('No matching component was found in the starter.')
    changes=starter_fields(current,original)
    if not changes:
        raise ValueError('The selected component already has its starter values.')
    choices={f'{".".join(keys)} · {value} → {old}':(keys,old) for keys,(value,old) in changes.items()}
    selected,ok=QInputDialog.getItem(guide,'Restore one starter value',current['name'],list(choices),0,False)
    if not ok:
        return
    keys,value=choices[selected]
    cid=studio.cid
    def apply(project):
        cell=next(cell for cell in project['cells'] if cell['id']==cid)
        device=next(part for part in cell['devices'] if part['id']==current['id'])
        for key in keys[:-1]:
            device=device[key]
        device[keys[-1]]=value
    studio.commit(apply,'Restore '+current['name']+' '+'.'.join(keys))


def blank_practice(hub):
    from .model import example
    lesson=hub.selected()
    if lesson is None:
        return
    studio=hub.studio
    hub.guide.save_note()
    if not studio._replace_document():
        return
    path=hub.portfolio.root/'blank-practice'/(lesson['id']+'.icproj')
    if path.is_file():
        project=load_project(path)
        if project.get('student_blank_practice')!=lesson['id']:
            raise ValueError('This file is not the saved blank practice project for this lesson.')
    else:
        project=example('empty')
        project['name']='Blank practice · '+lesson['title'][:100]
        project['pdk']=clone(hub.make_starter(lesson)['pdk'])
        project['student_blank_practice']=lesson['id']
        save_project(project,path)
    if studio.set_project(project,path) is False:
        return
    studio.show_design_workspace()
    studio.activate_circuit_view(int(lesson['path']=='layout'))
    hub.guide.open_lesson(lesson)
    hub.guide.show()
    hub.guide.restore_guide_position()
    hub.guide.raise_()
    hub.guide.feedback.setText('Build your circuit on this blank canvas. Use Studio’s analysis tools to check it. Save with Ctrl+S.')
    hub.guide.update_run_state()


def screenshare(studio, enabled):
    """Temporarily enlarge lesson and schematic text and simplify the editor."""
    hub=getattr(studio,'_student_hub',None)
    spaces=studio.app_workspaces
    if enabled:
        prior=dict(spaces.panels) if spaces.currentIndex()==1 else {}
        studio._study_sharing_panels=[(panel,prior.get(panel,not panel.isHidden()))
                                     for panel in (studio.nav,studio.inspector)]
        if spaces.currentIndex()==0:
            for panel,_ in studio._study_sharing_panels:
                panel.hide()
    else:
        saved=dict(getattr(studio,'_study_sharing_panels',()))
        if spaces.currentIndex()==0:
            for panel,visible in saved.items():
                panel.setVisible(visible)
        else:
            spaces.panels=[(panel,saved.get(panel,visible)) for panel,visible in spaces.panels]
    studio.schematic.share_text_scale=1.45 if enabled else 1
    studio.schematic.update()
    studio.plot.share_text_scale=1.25 if enabled else 1
    studio.plot.update()
    if hub:
        hub.apply_theme()
