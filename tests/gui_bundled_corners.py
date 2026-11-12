"""Exercise actual installed corner selection after runtime qualification."""
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
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio import digital, digital_runtime
    from icstudio.digital_platform import PLATFORM_LABELS
    from icstudio.digital_constraints_ui import ConstraintEditor
    from icstudio.gui import Studio
    from icstudio.model import digest, save_project, load_project
    runtime=digital_runtime.installed()
    if not runtime:raise ValueError('Qualify the actual included runtime before this GUI acceptance check.')
    values=digital_runtime.platforms(runtime)
    assert list(values['sky130hd']['corners'])==['typical','slow','fast']
    assert list(values['sky130hd']['extraction']['corners'])==['minimum','nominal','maximum']
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
    out=ROOT/'build/bundled-corner-ui';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);settings=QSettings(str(root/'settings.ini'),QSettings.IniFormat)
        settings.setFallbacksEnabled(False);settings.setValue('onboarding/show',False)
        settings.setValue('digital/toolchain','included')
        with patch('icstudio.gui.QSettings',return_value=settings), \
                patch('icstudio.gui.QStandardPaths.writableLocation',return_value=str(root/'data')):
            studio=Studio(recover=False);studio.set_project(digital.counter_project());studio.resize(1280,850);studio.show()
            window=studio.digital_window();QTest.qWait(50)
            def select(name):
                def choose(parent,title,label,items,*args):
                    if title=='Digital platform':return 'Included · '+PLATFORM_LABELS[name],True
                    assert title=='Library corner';return 'typical',True
                with patch('icstudio.digital_workspace.QInputDialog.getItem',side_effect=choose), \
                    patch('icstudio.digital_workspace.QFileDialog.getExistingDirectory',side_effect=AssertionError('Included platform asked for external files')):
                    window.workspace.import_platform()
                assert window.apply();QTest.qWait(30)
            select('sky130hd')
            config=window.config
            assert config['timing_corners']==['typical','slow','fast']
            assert config['rc_corners']==['minimum','nominal','maximum']
            editor=ConstraintEditor(studio,config);editor.show();editor.tabs.setCurrentIndex(2);QTest.qWait(150)
            assert len(editor.rc_checks)==3 and all(check.isChecked() for _,check in editor.rc_checks)
            assert editor.grab().save(str(out/'included-sky130-corners.png'))
            editor.close()
            path=root/'saved.icproj';save_project(studio.project,path)
            assert load_project(path)['digital']['rc_corners']==config['rc_corners']
            select('gf180');assert 'rc_corners' not in window.config
            studio.undo();QTest.qWait(30)
            assert studio.project['digital']['rc_corners']==['minimum','nominal','maximum']
            studio.saved_hash=digest(studio.project);studio.close();QTest.qWait(20)
    report={'status':'passed','runtime':runtime,'backend':digital_runtime.backend_identity(),
        'platform_revision':values['sky130hd']['revision'],'platform_fingerprint':values['sky130hd']['fingerprint'],
        'checks':['Actual included platform selection','All 3 library and 3 interconnect corners selected',
                  'Corner editor from installed platform','Save/reopen','Switch to GF180 clears incompatible RC choices','Undo restores SKY130 choices'],
        'scope':'Offscreen workflow against an installed qualified runtime; not consumer desktop acceptance'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
