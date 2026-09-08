import os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['XDG_DATA_HOME']=str(ROOT/'build/cancel-profile/data');os.environ['XDG_CONFIG_HOME']=str(ROOT/'build/cancel-profile/config')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import clone,digest
app=QApplication([]);w=Studio(recover=False);w.show();QTest.qWait(50)
s={**w.project['analysis'],'step':'5n','stop':'100u'};w.start_job(s);QTest.qWait(10);w.cancel_job();deadline=time.monotonic()+8
while w.process and time.monotonic()<deadline:QTest.qWait(20)
assert w.process is None,'Cancellation did not terminate worker';assert not w.jobs,'A cancelled job was accepted as a completed result';w.saved_hash=digest(w.project);w.close();app.processEvents();print('PASS: cancellation terminates worker and does not publish a result.')
