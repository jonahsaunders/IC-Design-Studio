"""Preserve independent library/interconnect selections through editing and reopen."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio import digital_platform
    from icstudio.digital_constraints_ui import ConstraintEditor
    from icstudio.digital_examples import uart_project
    from icstudio.gui import Studio
    from icstudio.model import save_project,load_project,digest
    from tests.test_digital_rc import DigitalRCTests
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
    out=ROOT/'build/digital-corner-ui';out.mkdir(parents=True,exist_ok=True)
    project=uart_project()
    with tempfile.TemporaryDirectory() as td:
        path=os.environ.get('ICSTUDIO_TEST_CORNER_PLATFORM')
        platform=digital_platform.read_manifest(path) if path else DigitalRCTests().fixture(Path(td))['platform']
        config=digital_platform.bind(project['digital'],platform);project['digital']=config
        original=[f for f in config['files'] if f['role']=='constraint']
        studio=Studio(recover=False);studio.set_project(project)
        editor=ConstraintEditor(studio,config);editor.show();editor.tabs.setCurrentIndex(2);QTest.qWait(150)
        assert len(editor.rc_checks)==3 and all(c.isChecked() for _,c in editor.rc_checks)
        assert editor.grab().save(str(out/'timing-corners.png'))
        editor.rc_checks[0][1].setChecked(False);editor.apply()
        assert editor.value is not None,editor.error.text()
        assert editor.value['rc_corners']==config['rc_corners'][1:]
        assert editor.value['timing_corners']==config['timing_corners']
        assert [f for f in editor.value['files'] if f['role']=='constraint']==original
        project['digital']=editor.value;destination=Path(td)/'corners.icproj';save_project(project,destination)
        repeat=ConstraintEditor(studio,load_project(destination)['digital'])
        assert [name for name,c in repeat.rc_checks if c.isChecked()]==config['rc_corners'][1:]
        for _,check in repeat.rc_checks:check.setChecked(False)
        repeat.apply();assert repeat.value is None and 'interconnect' in repeat.error.text()
        repeat.rc_checks[0][1].setChecked(True);repeat.apply()
        assert repeat.value is not None and repeat.value['rc_corners']==config['rc_corners'][:1]
        from icstudio.digital_workspace import Workspace
        created=[];view=SimpleNamespace(window=SimpleNamespace(config=config,studio=studio),switch_cell=created.append)
        with patch('icstudio.digital_workspace.QInputDialog.getText',return_value=('corner_child',True)):
            Workspace.new_cell(view)
        child=next(c for c in studio.project['cells'] if c['id']==created[0])
        assert not any(key in child['digital'] for key in ('platform','timing_corners','rc_corners'))
        studio.saved_hash=digest(studio.project);studio.close()
    report={'status':'passed','platform_revision':platform['revision'],
        'scope':'Offscreen editor workflow; no engine or process qualification',
        'checks':['Independent RC selection','Unchanged library selection and manual SDC','Save/reopen','Empty RC selection rejected','New cell clears detached platform corner selections']}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
