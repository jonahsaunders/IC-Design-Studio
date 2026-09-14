"""Real Icarus runs through the desktop scheduler and digital waveform UI."""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--evidence',type=Path,default=ROOT/'build/digital-ui')
    args=parser.parse_args();out=args.evidence.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.digital import counter_project
    from icstudio.model import digest,save_project
    app=QApplication([]);app.setStyle('Fusion');errors=[]
    def exception(t,v,tb):errors.append(str(v));sys.__excepthook__(t,v,tb)
    sys.excepthook=exception
    w=Studio(recover=False);w.error=errors.append;w.jobs_dir=out/'runs with spaces'
    for name in ('iverilog','vvp'):
        path=os.environ.get('ICSTUDIO_TEST_'+name.upper()) or shutil.which(name)
        if not path:raise RuntimeError('Install '+name+' or set ICSTUDIO_TEST_'+name.upper())
        w.settings.setValue('engine/'+name,path)
    w.set_project(counter_project());w.resize(1440,960);w.show();d=w.digital_window()
    def wait():
        deadline=time.monotonic()+90
        while w.run_manager.busy and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        assert not w.run_manager.busy,'Digital worker timed out'
        assert not errors,errors
        app.processEvents()
    assert d.files.count()==3
    original=w.project['digital']['files'][0]['text']
    d.editor.insertPlainText('// Desktop edit\n');assert d.apply()
    assert w.project['digital']['files'][0]['text']!=original
    w.undo();assert w.project['digital']['files'][0]['text']==original
    assert d.editor.toPlainText()==original
    d.shell.mode(0);QTest.qWait(50);d.grab().save(str(out/'sources.png'))
    assert w.centralWidget() is d
    row=d.run();wait();assert row['state']=='Complete',row['log']
    assert d.wave.data and d.wave.data['timescale']=='1ps'
    assert 'Current inputs' in d.summary.text()
    assert not w.jobs,'Digital payload was sent to the analog plot'
    d.shell.mode(1);d.wave.cursor_b=185000;d.wave.cursor=165000;d.wave.update();QTest.qWait(80);d.grab().save(str(out/'waveforms.png'))
    d.files.setCurrentRow(0);d.editor.insertPlainText('// New revision\n');assert d.apply()
    assert 'earlier inputs' in d.summary.text()
    d.shell.show_captured({'path':'counter.sv','line':3})
    assert 'New revision' not in d.shell.captured_editor.toPlainText()
    assert d.shell.captured_editor.isReadOnly()
    w.leave_digital_workspace();assert w.centralWidget() is not d
    assert w.digital_window() is d and w.centralWidget() is d
    path=out/'counter.icproj';save_project(w.project,path)
    w.set_project(w.project,path);d=w.digital_window()
    assert d.runs.count()==1 and d.wave.data
    d.replay();wait();assert w.run_manager.rows[-1]['state']=='Complete'
    # A deliberate functional fault must retain diagnostics, never a waveform result.
    d.shell.mode(0);d.files.setCurrentRow(0)
    d.editor.setPlainText(d.editor.toPlainText().replace("count + 1'b1","count + 2'd2"))
    row=d.run();wait();assert row['state']=='Failed';assert row.get('result') is None
    assert 'Counter mismatch' in row['log'];assert d.wave.data is None
    # Cancellation goes through the shared RunManager and process-tree teardown.
    d.files.setCurrentRow(1);d.editor.setPlainText('module counter_tb; initial forever #1; endmodule')
    row=d.run();QTest.qWait(300);d.stop();wait()
    assert row['state']=='Cancelled';assert row.get('result') is None
    # Unapplied edits participate in the application's save path.
    d.files.setCurrentRow(0);d.editor.insertPlainText('// Save through Studio\n')
    assert d.dirty;w.path=path;assert w.save();assert not d.dirty
    from icstudio.model import load_project
    assert 'Save through Studio' in load_project(path)['digital']['files'][0]['text']
    report={'status':'passed','qt_platform':app.platformName(),'checks':[
        'Source edits and undo','Real Icarus worker and four-state waveform',
        'Digital results bypass analog plots','Stale source indication',
        'Run history reload and snapshot replay','Deliberate functional failure',
        'Cancellation','Studio save includes source draft'],
        'versions':w.run_manager.rows[0]['result']['digital_result']['versions']}
    (out/'report.json').write_text(json.dumps(report,indent=2))
    w.saved_hash=digest(w.project);w.close();print(json.dumps({'status':'passed','evidence':str(out)}))


if __name__=='__main__':main()
