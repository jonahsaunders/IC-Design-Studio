"""Retain mapping choices and manual SDC through editing and save/reopen."""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio.digital_constraints_ui import ConstraintEditor
    from icstudio.digital_examples import uart_project
    from icstudio.gui import Studio
    from icstudio.model import save_project,load_project,digest
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
    out=ROOT/'build/digital-mapping-ui';out.mkdir(parents=True,exist_ok=True)
    project=uart_project();config=project['digital']
    config['synthesis']={'mapping':'speed','delay_ns':8,'driving_cell':'gf180mcu_fd_sc_mcu9t5v0__buf_4','load_pf':0}
    original=[f for f in config['files'] if f['role']=='constraint']
    studio=Studio(recover=False);studio.set_project(project)
    editor=ConstraintEditor(studio,config)
    assert editor.mapping.currentData()=='speed' and editor.driver.text()==config['synthesis']['driving_cell']
    assert editor.load.value()==0 and editor.delay.value()==8
    assert not editor.generate.isChecked() and not editor.derive.isChecked()
    editor.show();editor.tabs.setCurrentIndex(2);QTest.qWait(150)
    assert editor.grab().save(str(out/'timing-mapping.png'))
    editor.apply();assert editor.value is not None,editor.error.text()
    assert [f for f in editor.value['files'] if f['role']=='constraint']==original
    project['digital']=editor.value
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'mapping.icproj';save_project(project,path);reopened=load_project(path)
        repeat=ConstraintEditor(studio,reopened['digital'])
        assert repeat.mapping.currentData()=='speed' and repeat.driver.text()==config['synthesis']['driving_cell']
        assert repeat.load.value()==0
        repeat.driver.clear();repeat.apply()
        assert repeat.value is None and 'driving cell' in repeat.error.text()
        repeat.mapping.setCurrentIndex(repeat.mapping.findData('default'));repeat.apply()
        assert repeat.value is not None and repeat.value['synthesis']['mapping']=='default'
    studio.saved_hash=digest(studio.project);studio.close()
    report={'status':'passed','checks':['Explicit mapping and driver/load retained','Manual SDC unchanged',
        'Save/reopen','Missing speed-mapping driver rejected','Return to default mapping']}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
