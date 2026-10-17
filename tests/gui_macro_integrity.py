"""The desktop export action rejects changed inputs without overwriting a bundle."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')


def main():
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import clone,digest
    from tests.test_digital_macro import DigitalMacroTests
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
    out=ROOT/'build/macro-integrity-ui';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);job,result=DigitalMacroTests().fixture(root)
        settings=QSettings(str(root/'settings.ini'),QSettings.IniFormat);settings.setFallbacksEnabled(False)
        settings.setValue('onboarding/show',False);settings.setValue('digital/toolchain','custom')
        with patch('icstudio.gui.QSettings',return_value=settings), \
                patch('icstudio.gui.QStandardPaths.writableLocation',return_value=str(root/'data')), \
                patch('icstudio.digital_runtime.installed',return_value=None):
            studio=Studio(recover=False);studio.set_project(job['project']);studio.resize(1440,900);studio.show()
            window=studio.digital_window();QTest.qWait(75)
            action=next(a for a in window.findChildren(QAction) if a.text()=='Export implemented macro…')
            destination=root/'macro.zip'
            with patch.object(window,'selected_run',return_value={'result':result,'path':root}), \
                    patch('icstudio.digital_workspace.QFileDialog.getSaveFileName',return_value=(str(destination),'')):
                action.trigger();QTest.qWait(30)
                assert 'Exported macro' in window.message.text(),window.message.text()
                original=destination.read_bytes();changed=clone(job)
                changed['project']['digital']['top']='changed_after_implementation'
                (root/'input.json').write_text(json.dumps(changed))
                action.trigger();QTest.qWait(30)
                assert 'captured job inputs do not match' in window.message.text(),window.message.text()
                assert destination.read_bytes()==original and not (root/'macro.zip.partial').exists()
                (root/'input.json').write_text(json.dumps(job));action.trigger();QTest.qWait(30)
                assert 'Exported macro' in window.message.text(),window.message.text()
            studio.saved_hash=digest(studio.project);studio.close();QTest.qWait(20)
    report={'status':'passed','checks':['Actual export menu action','Valid export','Changed input rejection message',
        'Existing export preserved','Export recovers after original input restored'],
        'scope':'Offscreen desktop workflow with artifact fixtures; real captured-job checks are separate'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
