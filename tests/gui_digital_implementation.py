"""Actual mapped/timing/physical jobs through the central desktop workspace."""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--evidence',type=Path,default=ROOT/'build/digital-implementation-ui')
    out=parser.parse_args().evidence.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
    from PySide6.QtWidgets import QApplication,QDockWidget
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio import digital,digital_platform,digital_design
    from icstudio.model import digest,clone
    app=QApplication([]);app.setStyle('Fusion');errors=[]
    def exception(t,v,tb):errors.append(str(v));sys.__excepthook__(t,v,tb)
    sys.excepthook=exception
    p=digital.counter_project();p['digital']['platform']=digital_platform.from_orfs(os.environ['ICSTUDIO_TEST_ORFS']);p['digital']['timeout']=300
    w=Studio(recover=False);w.error=errors.append;w.jobs_dir=out/'runs'
    w.settings.setValue('digital/toolchain','custom')
    for name in ('yosys','sta','openroad','make'):
        path=os.environ.get('ICSTUDIO_TEST_'+name.upper()) or shutil.which(name)
        if not path:raise RuntimeError('Install '+name)
        w.settings.setValue('engine/'+name,path)
    w.settings.setValue('digital/orfs',os.environ['ICSTUDIO_TEST_ORFS'])
    w.set_project(p);w.resize(1600,1050);w.show();d=w.digital_window()
    assert w.centralWidget() is d and d.stage.count()==13
    def run(stage):
        d.stage.setCurrentIndex(d.stage.findData(stage));row=d.run();deadline=time.monotonic()+300
        while w.run_manager.busy and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        assert not w.run_manager.busy,'Worker timed out'
        assert not errors,errors
        assert row['state']=='Complete',row['log'][-5000:]
        app.processEvents();return row
    mapped=run('mapped');d.workspace.publish();assert len(digital_design.cell(w.project,w.cid)['ports'])==6
    assert d.workspace.netlist.rowCount()>0
    loc=next(i for i in d.workspace.index if i['locations']);d.workspace.probe(loc)
    assert d.shell.source_mode.currentIndex()==1 and d.shell.captured_files.currentText().endswith('.sv')
    d.shell.mode(1);d.workspace.use_selected.setChecked(True);timing=run('timing')
    assert timing['result']['digital_result']['verdict']=='PASS';assert d.workspace.timing.rowCount()>0
    d.workspace.probe_path(d.workspace.timing.item(0,0).data(Qt.UserRole));QTest.qWait(100);w.grab().save(str(out/'timing.png'))
    d.runs.setCurrentIndex(d.runs.findData(mapped['id']));physical=run('route')
    assert d.workspace.physical.objects
    d.workspace.physical.highlight([next(iter(d.workspace.physical.objects))])
    QTest.qWait(100);w.grab().save(str(out/'physical.png'))
    # A timing path opens the same physical geometry and can select its cells.
    timed=run('timing');path=next(p for p in timed['result']['digital_result']['timing']['paths'] if any('/' in pin for pin in p['pins']))
    d.workspace.probe_path(path)
    assert d.workspace.physical.scene().selectedItems()
    assert d.workspace.linked_physical.scene().selectedItems()
    assert d.workspace.timing.isVisible() and d.workspace.linked_physical.isVisible()
    d.workspace.refresh_comparison();assert d.workspace.comparison.rowCount()==4
    old=w.cid;created=[];w.commit(lambda p:created.append(digital_design.new_cell(p,'second',clone(p['digital']))),'New RTL block')
    d.workspace.switch_cell(created[0]);assert d.cell_id==created[0] and d.runs.count()==0
    w.undo();assert len(w.project['cells'])==1 and d.cell_id==old
    assert d.runs.count()==4
    d.workspace.use_selected.setChecked(False);d.flow.start('place');deadline=time.monotonic()+600
    while (d.flow.active or w.run_manager.busy) and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert d.flow.record['state']=='Complete',d.flow.record
    assert any(step['state']=='Reused' for step in d.flow.record['steps'])
    assert not errors,errors
    report={'status':'passed','checks':['Central workspace','Mapped symbol and source cross-probe','OpenSTA path table','Routed checkpoint preview','Timing-to-layout selection','Run comparisons','Independent cell RTL and undo'],
        'versions':physical['result']['digital_result']['versions'],'platform':p['digital']['platform']['revision']}
    (out/'report.json').write_text(json.dumps(report,indent=2));w.saved_hash=digest(w.project);w.close();print(json.dumps(report))


if __name__=='__main__':main()
