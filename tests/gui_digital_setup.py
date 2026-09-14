"""Exercise the real setup subprocess and its visible failure/retry state.

The archive is deliberately corrupt. This is UI/error-path evidence; successful
engine qualification is performed separately with the real release payload.
"""
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
out=ROOT/'build/digital-setup-ui'; out.mkdir(parents=True,exist_ok=True)
os.environ['ICSTUDIO_DIGITAL_PAYLOAD']=str(out/'payload')
os.environ['ICSTUDIO_DIGITAL_STATE']=str(out/'profile')
payload=Path(os.environ['ICSTUDIO_DIGITAL_PAYLOAD']); payload.mkdir(exist_ok=True)
(payload/'runtime.tar.gz').write_bytes(b'deliberately damaged acceptance fixture')
(payload/'manifest.json').write_text(json.dumps({'schema':1,'system':'ubuntu-24.04-x86_64','archive':'runtime.tar.gz','sha256':'0'*64}))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from icstudio.digital_setup_ui import DigitalSetupDialog
from icstudio.digital_runtime import status

app=QApplication([]); app.setStyle('Fusion')
dialog=DigitalSetupDialog(); dialog.show(); QTest.qWait(100)
dialog.grab().save(str(out/'setup.png'))
dialog.setup(); deadline=time.monotonic()+30
while dialog.process and time.monotonic()<deadline: app.processEvents(); time.sleep(.01)
assert dialog.process is None,'Setup subprocess did not finish'
assert status()['state']!='ready'
assert 'damaged' in dialog.log.toPlainText(),dialog.log.toPlainText()
assert dialog.start.isEnabled()
assert 'did not complete' in dialog.status.text()
QTest.qWait(100); dialog.grab().save(str(out/'failed-package.png'))
(out/'report.json').write_text(json.dumps({'status':'PASS','scope':'UI and damaged-package rejection, not engine qualification',
    'checks':['Nonblocking subprocess','Corrupt archive rejected','Ready not published','Retry enabled'],'qt_platform':app.platformName()},indent=2))
dialog.close(); print('Digital setup GUI passed')
