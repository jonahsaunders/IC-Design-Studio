"""Included platform selection, corner reset, saving and undo with catalog fixtures."""
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
    from icstudio.digital_platform import BUNDLED_PLATFORMS, PLATFORM_LABELS, read_manifest
    from icstudio.model import clone, digest, load_project, save_project
    from icstudio.gui import Studio
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
    out=ROOT/'build/digital-platform-ui';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);values={}
        for name in BUNDLED_PLATFORMS:
            folder=root/name;folder.mkdir();(folder/'cells.lib').write_text('library fixture {}\n')
            corners={'typical':['cells.lib']} if name=='sky130hd' else {c:['cells.lib'] for c in ('typical','slow','fast')}
            path=folder/'manifest.json';path.write_text(json.dumps({'version':1,'name':name,'revision':'UI fixture',
                'corner':'typical','corners':corners,'files':['cells.lib']}))
            values[name]=read_manifest(path)
        settings=QSettings(str(root/'settings.ini'),QSettings.IniFormat);settings.setFallbacksEnabled(False)
        settings.setValue('onboarding/show',False);settings.setValue('digital/toolchain','included')
        with patch('icstudio.gui.QSettings',return_value=settings), \
             patch('icstudio.gui.QStandardPaths.writableLocation',return_value=str(root/'data')), \
             patch.object(digital_runtime,'status',return_value={'state':'ready','message':'Fixture tools ready'}), \
             patch.object(digital_runtime,'installed',return_value={'kind':'fixture'}), \
             patch.object(digital_runtime,'platform',side_effect=lambda _,name=None:clone(values[name or 'sky130hd'])), \
             patch.object(digital_runtime,'platforms',side_effect=lambda _:clone(values)):
            studio=Studio(recover=False);studio.set_project(digital.counter_project());studio.resize(1280,850);studio.show()
            window=studio.digital_window();QTest.qWait(50)
            def select(name):
                def choose(parent,title,label,items,*args):
                    if title=='Digital platform':
                        assert all('Included · '+PLATFORM_LABELS[n] in items for n in BUNDLED_PLATFORMS)
                        return 'Included · '+PLATFORM_LABELS[name],True
                    assert title=='Library corner'
                    return items[0],True
                with patch('icstudio.digital_workspace.QInputDialog.getItem',side_effect=choose), \
                     patch('icstudio.digital_workspace.QFileDialog.getExistingDirectory',side_effect=AssertionError('Included selection asked for an external checkout')):
                    window.workspace.import_platform()
                assert window.config['platform']['name']==name
                assert window.config['timing_corners']==list(values[name]['corners'])
                assert window.apply();QTest.qWait(30)
            select('gf180');path=root/'saved.icproj';save_project(studio.project,path)
            assert load_project(path)['digital']['platform']['name']=='gf180'
            select('ihp-sg13g2');studio.undo();QTest.qWait(30)
            assert studio.project['digital']['platform']['name']=='gf180'
            assert window.config['timing_corners']==['typical','slow','fast']
            select('sky130hd');assert window.config['timing_corners']==['typical']
            select('gf180');studio.resize(1440,900);window.shell.inspector.show()
            window.shell.outer.setSizes([220,960,260]);QTest.qWait(50)
            assert studio.width()==1440
            studio.grab().save(str(out/'included-gf180.png'))
            studio.saved_hash=digest(studio.project);studio.close();QTest.qWait(20)
    print(json.dumps({'status':'passed','checks':['Included choices require no checkout','Every captured corner selected','Save/reopen','Platform switch undo','Incompatible corner reset'],
                      'scope':'GUI catalog fixtures; real package qualification is separate'}))


if __name__=='__main__':main()
