"""Desktop acceptance for analog setup, immutable run inspection and layout."""
import argparse,json,sys,time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QSettings,QStandardPaths,Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import example,clone,design_digest
    from icstudio.analog_run_ui import RunInspector
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.maybe_save=lambda:True;w.live_check.setChecked(False)
    errors=[];w.error=lambda text:errors.append(str(text));w.show()
    def wait(predicate):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            QTest.qWait(20)
        raise AssertionError('Timed out: '+str(errors))
    try:
        p=example('rc');c=p['cells'][0];p['parameters']={'load':'10k'};c['devices'][1]['value']='{load}'
        c['specifications']=[dict(name='Output',expression='final(V("vout"))',min='0',max='2',unit='V')]
        p['simulation_setups']=[dict(name='Settling',cell=c['id'],engine='builtin',settings=clone(p['analysis']))]
        w.set_project(p);window=w.open_analog_workspace();QTest.qWait(150)
        assert window.tabs.count()==4
        window.variables.setPlainText('load = 12k');window.save_setup();assert w.project['parameters']['load']=='12k'
        w.undo();assert w.project['parameters']['load']=='10k';window.reload_setup()
        editor=window.edit();editor.variables.setPlainText('load = 20k');editor.temperatures.setText('0, 27');editor.save()
        assert not editor.isVisible(),editor.error.text();window.run()
        wait(lambda:len(w.run_manager.rows)==2 and all(r['state'] in ('Complete','Failed') for r in w.run_manager.rows))
        assert all(r['state']=='Complete' for r in w.run_manager.rows),[(r['state'],r['log']) for r in w.run_manager.rows]
        window.refresh();window.tabs.setCurrentIndex(1);app.processEvents();window.grab().save(str(out/'analog-matrix.png'))
        window.table.setCurrentCell(0,2);before=clone(w.project);window.open_run();inspector=window.run_inspector
        assert w.project==before and inspector.project['parameters']['load']=='20k'
        assert inspector.probe.currentData()==('voltage','vout')
        inspector.select_device(1);app.processEvents();assert inspector.plot.names
        inspector.grab().save(str(out/'saved-run-inspector.png'))
        window.tabs.setCurrentIndex(0);window.grab().save(str(out/'analog-setup.png'))
        window.variables.setPlainText('load = 30k');w.commit(lambda q:q['parameters'].update(load='40k'),'External change')
        window.call(window.save_setup);assert 'changed elsewhere' in window.workspace_note.text();assert w.project['parameters']['load']=='40k'
        # A retained requirement failure must be retryable even if its worker completed.
        row=w.run_manager.rows[0];row['result']['specifications'][0]['status']='FAIL';window.refresh();window.retry()
        wait(lambda:len(w.run_manager.rows)==3 and w.run_manager.rows[-1]['state']=='Complete')
        assert w.run_manager.rows[-1]['job']['project']['parameters']['load']=='20k'
        # Location uses the saved layout even when the working document changed.
        from icstudio.layout import rect
        snapshot=clone(w.project);cell=snapshot['cells'][0];shape=rect('metal1',1000,2000,1000,1000);cell['shapes']=[shape]
        result=dict(project_id=snapshot['id'],cell_id=cell['id'],design_hash=design_digest(snapshot),physical_result={'issues':[dict(code='DRC.WIDTH',cell_id=cell['id'],object=shape['id'],bbox=[1000,2000,2000,3000],message='Fixture marker')]})
        physical=RunInspector(w,dict(name='Location fixture',state='Complete',log='',job=dict(project=snapshot,cell=cell['id'],settings={'type':'drc'}),result=result))
        physical.locate_finding(0);assert physical.layout_canvas.cell['shapes'][0]['id']==shape['id'];assert not w.cell['shapes']
        physical.close();inspector.close();window.close()
        assert not errors,errors
        (out/'acceptance.json').write_text(json.dumps(dict(status='passed',checks=['Setup save/undo','Immutable PVT overrides','Result matrix to saved circuit and probes','Stale setup rejection','Completed requirement failure retry','Saved verification geometry navigation']),indent=2))
    finally:w.close();app.processEvents()


if __name__=='__main__':main()
