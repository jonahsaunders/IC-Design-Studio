"""Real coupled run, replay, cancellation and source editing through the desktop."""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=ROOT/'build/mixed-signal-ui');args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
    from PySide6.QtCore import QSettings,QStandardPaths
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.mixed_signal_ui import show
    from icstudio.sar_example import sar_project
    from icstudio.model import clone,digest,save_project
    app=QApplication([]);app.setStyle('Fusion');errors=[]
    old=sys.excepthook
    def exception(t,v,tb):errors.append(str(v));old(t,v,tb)
    sys.excepthook=exception
    w=Studio(recover=False);w.error=errors.append;w.jobs_dir=out/'runs with spaces';w.set_project(sar_project())
    w.resize(1440,960);w.show();w.maybe_save=lambda:True
    for name in ('ngspice','iverilog','vvp'):
        path=os.environ.get('ICSTUDIO_TEST_'+name.upper()) or shutil.which(name)
        assert path,'Install '+name
        w.settings.setValue('mixed_signal/'+name,path)
    d=show(w);original=clone(w.project['mixed_signal']);d.voltage.setText('.4');d.apply()
    assert w.project['mixed_signal']['stimuli']['vin']==[[0.,.4]]
    w.undo();assert w.project['mixed_signal']==original
    try:d.apply()
    except ValueError as exc:assert 'configuration changed' in str(exc)
    else:raise AssertionError('Stale configuration overwrote Undo')
    d=show(w);d.run()
    def wait():
        deadline=time.monotonic()+60
        while w.run_manager.busy and time.monotonic()<deadline:QTest.qWait(20)
        assert not w.run_manager.busy,'Worker timeout'
        app.processEvents();assert not errors,errors
    wait();row=w.run_manager.rows[-1];assert row['state']=='Complete',row['log']
    assert row['result']['mixed_signal']['verification']['status']=='PASS'
    assert d.edges.rowCount()==10;assert 'code 8' in d.status.text()
    d.grab().save(str(out/'conversion.png'));d.waveforms();QTest.qWait(50)
    assert w.jobs[-1]['traces']['vdac'];w.grab().save(str(out/'waveforms.png'))
    path=out/'sar.icproj';save_project(w.project,path)
    w.set_project(w.project,path);d=show(w);assert d.runs.count()==1
    d.refresh_runs();assert 'code 8' in d.status.text()
    replay=w.run_manager.enqueue(clone(row['job']),w.jobs_dir,'Mixed-signal replay');wait()
    assert replay['state']=='Complete',replay['log']
    assert replay['result']['mixed_signal']['samples']==row['result']['mixed_signal']['samples']
    d.digital();window=w._digital_window;assert 'sar_controller' in window.editor.toPlainText()
    window.editor.insertPlainText('// UI edit\n');assert window.apply();w.leave_digital_workspace();d=show(w)
    assert 'earlier design' in d.status.text()
    w.undo();d=show(w);d.run();cancelled=w.run_manager.rows[-1]
    QTest.qWait(40);w.run_manager.cancel([cancelled]);wait()
    assert cancelled['state']=='Cancelled' and not cancelled.get('result')
    d.close();w.saved_hash=digest(w.project);w.close();app.processEvents()
    report=dict(status='PASS',qt_platform=app.platformName(),checks=['configuration undo','real worker conversion',
        'analog waveform display','save/reopen verified artifacts','deterministic replay','RTL edit and stale result','cancellation'])
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
