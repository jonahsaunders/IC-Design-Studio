"""Desktop acceptance for the shape/search/EM workflow, also run in packages."""
import json
import math
import time
from pathlib import Path
from unittest.mock import patch


def run(w,output):
    from PySide6.QtCore import QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from . import inductor,inductor_em
    from .model import example,clone,save_project,load_project
    app=QApplication.instance();before=clone(w.project);path=w.path;dialog=None;em=None
    output=Path(output)/'design';output.mkdir(parents=True,exist_ok=True);checks=[]
    def wait(predicate,label,seconds=20):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            QTest.qWait(10)
        raise AssertionError(label)
    try:
        p=example('empty')
        p['pdk']['parasitics']={'metal1':{'sheet_ohm':.08},'metal2':{'sheet_ohm':.04}}
        p['pdk']['via_resistance_ohm']={'M1 to M2':2.}
        p['pdk']['em_stackup']={'source':'Synthetic desktop acceptance stack; not process data','layers':[
            dict(name='metal1',kind='conductor',z_um=1,thickness_um=.5,conductivity_s_m=3e7),
            dict(name='via1',kind='via',z_um=1.5,thickness_um=.5,conductivity_s_m=3e7),
            dict(name='metal2',kind='conductor',z_um=2,thickness_um=1,conductivity_s_m=3e7),
            dict(name='oxide',kind='dielectric',z_um=0,thickness_um=10,epsilon_r=3.9)]}
        # PDK setup is available independently, including before via rules have
        # been supplied and before an inductor can be generated.
        incomplete=clone(p);incomplete['pdk']['routing_vias']=[];incomplete['pdk'].pop('em_stackup')
        w.set_project(incomplete)
        setup=next(a for a in w.task_menus['Tools'].actions() if a.text()=='Physical EM profile…')
        setup.trigger();assert w._em_profile.isVisible();assert w._em_profile.layers.rowCount()==0
        w._em_profile.reject()
        w.set_project(p);action=next(a for a in w.task_menus['Tools'].actions() if a.text()=='Inductor creator…')
        action.trigger();dialog=w._inductor_dialog
        for shape in inductor.SHAPES:
            dialog.shape.setCurrentIndex(dialog.shape.findData(shape))
            wait(lambda:dialog.proposal is not None and dialog.proposal['spec']['shape']==shape,shape+' preview')
            assert dialog.fields['inner_y'].isEnabled()==(shape=='rectangle')
            assert dialog.grab().save(str(output/(shape+'.png')))
        checks.append('Five shape previews, dimensions, model selection and rectangle aspect control')
        # Burst changes exercise revision gating while a timer proves that the
        # event loop continues to service input during actual target search.
        ticks=[];heartbeat=QTimer(dialog);heartbeat.setInterval(10);heartbeat.timeout.connect(lambda:ticks.append(1));heartbeat.start()
        dialog.tabs.setCurrentIndex(1);dialog.search_fields['width_max'].setValue(12)
        dialog.find_candidates();wait(lambda:bool(dialog.candidates),'Target-L candidates')
        heartbeat.stop();assert len(ticks)>=2
        assert any(c['within_tolerance'] for c in dialog.candidates)
        assert dialog.grab().save(str(output/'target-search.png'))
        dialog.choose_candidate();wait(lambda:dialog.proposal is not None,'Selected candidate placement check')
        dialog.fields['spacing'].setValue(.01)
        wait(lambda:getattr(dialog.last_error,'field',None)=='spacing','Field-specific spacing error')
        assert dialog.preview.paths and not dialog.apply_button.isEnabled()
        dialog.fix_error();wait(lambda:dialog.proposal is not None,'Explicit suggested spacing fix')
        # Cancelled searches cannot repopulate the candidate list later.
        dialog.find_candidates();dialog.cancel_search(clear=True);QTest.qWait(100);app.processEvents()
        assert not dialog.candidates
        dialog.series_rl.setChecked(True);wait(lambda:dialog.proposal is not None,'DC series RL preview')
        assert dialog.proposal['resistance']['total_ohm']>0
        dialog.apply();dialog=None;did=w.cell['devices'][0]['id']
        assert w.cell['devices'][0]['inductor_rl']['resistance_ohm']>0
        checks.append('Responsive bounded target search, candidate selection, cancellation, explicit fixes and series-RL opt-in')

        w.select([did],'schematic');action.trigger();dialog=w._inductor_dialog
        wait(lambda:dialog.proposal is not None,'Saved generated coil')
        assert dialog.series_rl.isChecked();dialog.open_em();em=dialog._em_dialog
        assert em.parent() is dialog
        # Author and reuse a profile through the actual editor. Physical names
        # need not match layout names; bad material input must stay atomic.
        em.edit_profile();profile=em._profile;app.processEvents()
        original_profile=clone(w.project);profile.layers.item(0,3).setText('0');profile.apply()
        assert w.project==original_profile and profile.error.text()
        profile.layers.item(0,3).setText('0.5');profile.layers.item(0,0).setText('Return conductor')
        for row in range(profile.mapping.rowCount()):
            if profile.mapping.item(row,0).text()=='metal1':profile.mapping.item(row,2).setText('Return conductor')
        profile_file=output/'synthetic-pdk-profile.json'
        with patch('icstudio.em_profile_ui.QFileDialog.getSaveFileName',return_value=(str(profile_file),'JSON')):profile.save()
        assert profile_file.is_file(),profile.error.text()
        app.processEvents();assert profile.grab().save(str(output/'pdk-profile.png'))
        profile.apply();assert not profile.isVisible(),profile.error.text()
        assert w.project['pdk']['em_stackup']['layout_map']['metal1']=='Return conductor'
        w.undo();assert w.project['pdk']==original_profile['pdk'];w.redo();em.refresh()
        em.edit_profile();profile=em._profile
        with patch('icstudio.em_profile_ui.QFileDialog.getOpenFileName',return_value=(str(profile_file),'JSON')):profile.load()
        assert not profile.error.text(),profile.error.text();profile.reject()
        checks.append('PDK profile editor, explicit layer aliases, invalid-data atomicity, reusable file and undo/redo')
        bundle=output/'em-exchange.zip'
        with patch('icstudio.inductor_em_ui.QFileDialog.getSaveFileName',return_value=(str(bundle),'ZIP')):em.export()
        assert bundle.is_file(),em.error.text()
        manifest=inductor_em.manifest(w.project,w.cid,did)
        frequency=[1e8,1e9,3e9,5e9,8e9,1e10]
        zs=[1/(1/complex(2,2*math.pi*f*2e-9)+2j*math.pi*f*.5e-12) for f in frequency]
        evidence=dict(schema=1,fingerprint=manifest['fingerprint'],port_definition=manifest['port_definition'],
                      source='Synthetic analytic RL || C desktop acceptance; no EM solver claim',
                      frequency_hz=frequency,z_real_ohm=[z.real for z in zs],z_imag_ohm=[z.imag for z in zs])
        results=output/'synthetic-impedance.json';results.write_text(json.dumps(evidence))
        with patch('icstudio.inductor_em_ui.QFileDialog.getOpenFileName',return_value=(str(results),'JSON')):em.import_results()
        assert not em.error.text(),em.error.text();assert len(em.plot.rows)==6;assert 'SRF bracket' in em.summary.text()
        app.processEvents();assert em.grab().save(str(output/'em-results.png'))
        saved=output/'characterized.icproj';save_project(w.project,saved)
        loaded=load_project(saved);assert inductor_em.result_status(loaded,w.cid,did)[0]
        # Loading different physical material data makes the evidence stale.
        stack=clone(w.project['pdk']['em_stackup']);stack['layers'][0]['conductivity_s_m']*=2
        file=output/'different-stack.json';file.write_text(json.dumps(stack))
        with patch('icstudio.inductor_em_ui.QFileDialog.getOpenFileName',return_value=(str(file),'JSON')):em.load_stackup()
        assert not em.plot.rows and 'Stale characterization' in em.status.text()
        checks.append('EM bundle export, imported L/Q/SRF, project persistence and stale material-data rejection')
        return checks
    finally:
        if em:em.close()
        if dialog:dialog.close()
        w.set_project(before,path);app.processEvents()
