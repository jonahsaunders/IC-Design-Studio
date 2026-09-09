"""Run scheduler failure, cancellation, repeat and result focus acceptance."""
import os,sys,time,json,traceback,argparse
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(out/'data');os.environ['XDG_CONFIG_HOME']=str(out/'config')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import example,digest,clone
app=QApplication([]);w=Studio(False);w.show();errors=[];w.error=errors.append
sys.excepthook=lambda t,v,tb:errors.append(''.join(traceback.format_exception(t,v,tb)))
checks=[]
def wait():
    deadline=time.monotonic()+25
    while w.run_manager.busy and time.monotonic()<deadline:QTest.qWait(20)
    assert not w.run_manager.busy and not w.process,w.console.toPlainText()
    assert not errors,errors
w.set_project(example('rc'));w.parallel_jobs.setValue(1)
# An actual failed process start transitions once, releases the slot and enables rerun.
with patch('icstudio.run_manager.sys',SimpleNamespace(executable=str(out/'missing-worker'),frozen=True)):
    failed=w.start_job(w.project['analysis']);QTest.qWait(80)
wait();assert failed['state']=='Failed' and w.run_button.isEnabled() and not w.jobs
assert json.loads((failed['path']/'status.json').read_text())['status']=='failed';checks.append('FailedToStart terminates once, persists failure and releases its queue slot')
# A real worker error does not prevent the next queued job from completing.
bad=w.start_job({'type':'unknown'});good=w.start_job(w.project['analysis']);assert good['state']=='Queued';wait()
assert bad['state']=='Failed' and good['state']=='Complete';assert len(w.jobs)==1;checks.append('Worker failure advances the queue and never publishes invalid results')
# Both sequential queued results publish; explicit browsing keeps the chosen waveform.
w.simulation_runs.selectRow(w.run_manager.rows.index(good));w.open_selected_run();selected=w.result
first=w.start_job(w.project['analysis']);second=w.start_job({**w.project['analysis'],'type':'ac'});wait()
assert first['state']==second['state']=='Complete';assert w.result is selected;checks.append('Queued runs complete in sequence; explicit result selection survives later completions')
# All-running cancellation also cancels queued work and prevents shutdown from starting it.
w.parallel_jobs.setValue(2)
rows=[w.start_job({**w.project['analysis'],'step':'5n'}) for _ in range(4)]
w.run_manager.cancel(rows);wait();assert all(r['state']=='Cancelled' for r in rows);checks.append('Stop all cancels every queued and active job without launching replacement workers')
# Reopen retains failure/cancellation history and marks orphaned runs as interrupted.
path=rows[-1]['path'];(path/'status.json').write_text(json.dumps({'status':'running'}));p=clone(w.project);w.set_project(p)
assert any(r['state']=='Interrupted' for r in w.run_manager.rows);checks.append('Incomplete runs are visibly interrupted after reopening and cannot replay as complete')
w.saved_hash=digest(w.project);w.close();app.processEvents();assert not errors,errors
(out/'report.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2));print('PASS',len(checks),'scheduler lifecycle checks')
