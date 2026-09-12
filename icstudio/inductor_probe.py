"""Inductor creator acceptance shared by source and installed desktop builds."""
import time
from pathlib import Path


def run(w,output):
    from PySide6.QtCore import Qt,QPoint
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from .model import clone,example,scalar,save_project,load_project
    from .physical import connectivity
    out=Path(output)/'inductor';out.mkdir(parents=True,exist_ok=True)
    before=clone(w.project);path=w.path;dialog=None;app=QApplication.instance();checks=[]
    def wait(predicate,label):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            QTest.qWait(10)
        raise AssertionError(label)
    def click(button):
        assert button.isVisible() and button.isEnabled(),button.text()
        QTest.mouseClick(button,Qt.LeftButton);app.processEvents()
    try:
        w.set_project(example('empty'));w.workflow_dock.hide();w.results_dock.hide()
        action=next(a for a in w.task_menus['Tools'].actions() if a.text()=='Inductor creator…')
        action.trigger();dialog=w._inductor_dialog;assert QTest.qWaitForWindowExposed(dialog)
        wait(lambda:dialog.proposal is not None,'Initial spiral preview')
        screen=dialog.screen().availableGeometry()
        if app.platformName() not in ('offscreen','minimal'):
            assert dialog.frameGeometry().width()<=screen.width() and dialog.frameGeometry().height()<=screen.height(),(dialog.frameGeometry(),screen)
        dialog.resize(min(900,screen.width()-30),max(400,min(460,screen.height()-60)));QTest.qWait(30)
        assert dialog.rect().contains(dialog.apply_button.mapTo(dialog,dialog.apply_button.rect().center()))
        dialog.fields['turns'].setValue(4);dialog.fields['width'].setValue(12);dialog.fields['inner'].setValue(100)
        dialog.rotation.setCurrentIndex(1);dialog.mirror.setChecked(True);dialog.p_net.setText('RF_IN');dialog.n_net.setText('RF_OUT')
        wait(lambda:dialog.proposal is not None,'Edited spiral preview');assert dialog.proposal['outer_nm']==214000
        assert len(dialog.preview.paths)==29 and dialog.proposal['via_count']==8
        initial=clone(w.project);dialog.fields['spacing'].setValue(.01)
        wait(lambda:bool(dialog.error.text()),'Invalid spacing feedback');assert not dialog.apply_button.isEnabled() and not dialog.preview.paths
        assert w.project==initial
        dialog.fields['spacing'].setValue(3);wait(lambda:dialog.proposal is not None,'Corrected spacing preview')
        estimate=dialog.proposal['estimate_h'];QTest.qWait(30)
        assert 'Estimated DC L:' in dialog.summary.text() and dialog.summary.height()>=dialog.summary.fontMetrics().height()*3
        assert dialog.grab().save(str(out/'creator.png'))
        click(dialog.apply_button);assert not dialog.isVisible();dialog=None
        c=w.cell;did=c['devices'][0]['id'];ids=[s['id'] for s in c['shapes']]
        assert c['devices'][0]['nets']==dict(p='RF_IN',n='RF_OUT')
        assert abs(scalar(c['devices'][0]['value'])/estimate-1)<1e-10
        assert not connectivity(w.project,w.cid)['issues'];assert w.mode_combo.currentIndex()==1
        created=clone(c);w.undo();assert not w.cell['shapes'] and not w.cell['devices'];w.redo();assert w.cell==created
        checks.append('Tools menu, compact live preview, dimensions/orientation, invalid-input guard, linked labelled L and single-step undo/redo')

        w.select(ids,'layout');action.trigger();dialog=w._inductor_dialog
        assert dialog.target.currentData()==did and dialog.fields['inner'].value()==100 and not dialog.use_estimate.isChecked()
        assert dialog.rotation.currentData()==90 and dialog.mirror.isChecked()
        old_value=w.cell['devices'][0]['value'];dialog.fields['inner'].setValue(120)
        wait(lambda:dialog.proposal is not None,'Regeneration preview');click(dialog.apply_button);dialog=None
        assert [s['id'] for s in w.cell['shapes']]==ids and w.cell['devices'][0]['value']==old_value
        w.select([did],'schematic');dialog=w.parametric_dialog();assert dialog.target.currentData()==did
        dialog.use_estimate.setChecked(True);wait(lambda:dialog.proposal is not None,'Estimate opt-in');estimate=dialog.proposal['estimate_h'];click(dialog.apply_button);dialog=None
        assert abs(scalar(w.cell['devices'][0]['value'])/estimate-1)<1e-10
        file=out/'saved-spiral.icproj';save_project(w.project,file);saved=clone(w.cell);w.set_project(load_project(file),file)
        assert w.cell==saved and not connectivity(w.project,w.cid)['issues']
        checks.append('Reopen from layout and placement checklist, stable regeneration identities, explicit estimate opt-in and saved recipe reload')

        w.select(ids,'layout');action.trigger();dialog=w._inductor_dialog;initial=clone(w.project)
        w.layout.locked_layers.add('via1');click(dialog.apply_button)
        assert w.project==initial and not dialog.apply_button.isEnabled() and 'Unlock' in dialog.error.text()
        w.layout.locked_layers.discard('via1');dialog.refresh_preview();assert dialog.proposal
        w.commit(lambda p:p.update(name='Changed while preview was open'),'External design edit');initial=clone(w.project)
        click(dialog.apply_button);assert w.project==initial and 'design changed' in dialog.error.text() and not dialog.apply_button.isEnabled()
        dialog.reject();dialog=None;w.layout.fit();QTest.qWait(50);assert w.grab().save(str(out/'layout.png'))
        checks.append('Apply-time layer lock and stale design guards leave the design unchanged')
        return dict(status='passed',checks=checks,platform=app.platformName(),estimated_h=estimate,shape_count=len(w.cell['shapes']))
    finally:
        if dialog:dialog.close()
        w.layout.locked_layers.discard('via1');w.set_project(before,path)
