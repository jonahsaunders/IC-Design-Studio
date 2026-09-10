"""Dark-default migration, remembered choice, and job-state smoke checks."""
import os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
profile=ROOT/'build'/'dark-v021-profile';profile.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(profile/'data');os.environ['XDG_CONFIG_HOME']=str(profile/'config')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import digest,clone
from icstudio.ui_style import palette
app=QApplication([]);app.setStyle('Fusion');settings=QSettings('ICDesignStudio','Studio');settings.clear();settings.setValue('dark',False)
errors=[]
def exception(t,v,tb):
 import traceback
 errors.append(str(v));traceback.print_exception(t,v,tb)
sys.excepthook=exception
w=Studio(recover=False);w.resize(1440,900);w.show();QTest.qWait(100)
assert w.dark and w.schematic.dark and w.layout.dark and w.plot.dark
assert w.palette().window().color().name()==palette(True)['panel']
# An explicit choice in the new version persists across sessions.
w.toggle_theme();assert not w.dark;w.saved_hash=digest(w.project);w.close();w=Studio(recover=False);w.show();assert not w.dark
w.toggle_theme();assert w.dark;w.saved_hash=digest(w.project);w.close();w=Studio(recover=False);w.resize(1440,900);w.show();assert w.dark;QTest.qWait(50)
assert w.results_dock.isHidden();w.select([w.cell['devices'][1]['id']]);w.quick_run();assert w.run_button.text()=='Running…';assert not w.run_button.isEnabled()
deadline=time.monotonic()+20
while w.process and time.monotonic()<deadline:QTest.qWait(20)
assert not w.process and w.result and w._job_state=='complete';assert w.run_button.text()=='Run' and w.run_button.isEnabled();assert w.stop_button.isHidden();assert w.result_status.text()=='Current revision';w.fit_active();w.schematic.setFocus();QTest.qWait(80);assert w.grab().save(str(ROOT/'build'/'workspace-dark-0.2.1.png'))
# A worker error must restore Run and present a failure, not an idle running state.
w.result=None;w.plot.result=None;bad=clone(w.project['analysis']);bad['type']='unsupported';w.start_job(bad)
deadline=time.monotonic()+10
while w.process and time.monotonic()<deadline:QTest.qWait(20)
assert not w.process and w._job_state=='failed';assert w.run_button.isEnabled();assert w.result_status.text()=='Failed · see Job log';assert not w.analysis_error.isHidden()
w.saved_hash=digest(w.project);w.close();assert not errors,errors
print('PASS: dark default over legacy preference, remembered explicit theme, dark canvases/palette, running/completed/failed job feedback, screenshot.')
