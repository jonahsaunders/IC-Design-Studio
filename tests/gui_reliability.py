import os,sys,time,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
profile=ROOT/'build/reliability-profile';profile.mkdir(parents=True,exist_ok=True);os.environ['XDG_DATA_HOME']=str(profile/'data');os.environ['XDG_CONFIG_HOME']=str(profile/'config')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import clone,digest,example,save_project,load_project
from icstudio import recovery
app=QApplication([]);w=Studio(False);w.show();QTest.qWait(70)
# Detect competing saves before replacing a user's changed file.
f=profile/'shared.icproj';save_project(w.project,f);w.set_project(load_project(f),f);external=clone(w.project);external['name']='Another session';save_project(external,f);w.commit(lambda p:p.update(name='My edits'))
try:w.save();raise AssertionError('External edits overwritten')
except ValueError as e:assert 'changed on disk' in str(e)
w.finish_recovery()
assert load_project(f)['name']=='Another session';saved,_=recovery.read(w.recovery_dir/(w.project['id']+'.icproj'));assert saved['name']=='My edits'
# A running job cannot publish into a different project; cancellation persists.
w.start_job({**w.project['analysis'],'step':'5n'});job=w.active_job
try:w.set_project(example('empty'));raise AssertionError('Project switched during a job')
except ValueError as e:assert 'Stop the active job' in str(e)
w.cancel_job();deadline=time.monotonic()+8
while w.process and time.monotonic()<deadline:QTest.qWait(20)
assert not w.process and not w.jobs;assert json.loads((job/'status.json').read_text())['status']=='cancelled'
p=clone(w.project);w.set_project(p);assert not w.jobs
w.saved_hash=digest(w.project);w.close();print('PASS: competing-save protection, recovery retains edits, project-switch guard, durable cancellation and replay rejection.')
