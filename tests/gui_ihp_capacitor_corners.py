"""Focused real GUI exercise; run in an isolated process and output directory."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import clone, example, load_project
from icstudio.catalog import create_device
from icstudio.ihp_capacitor_corners import CAP, CHOICES, KEY
from icstudio.interchange import spice
from icstudio.pdks import stage_model_deck
from icstudio.bundled_pdks import bundle_root
from scripts.qualify_standard_mos import load_technology

def main(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication.instance() or QApplication([]);w=Studio(recover=False);errors=[];w.error=lambda text:errors.append(str(text));w.maybe_save=lambda:True
    tech=load_technology('ihp-sg13g2')[0];p=example('empty');p['pdk']=tech;p['analysis']['corner']='fast'
    p['cells'][0]['devices']=[create_device(tech,'sg13g2_pr/cap_cmim.sym','C1'),create_device(tech,'sg13g2_pr/sg13_lv_nmos.sym','M1')]
    try:
        w.live_check.setChecked(False);w.show();w.set_project(p);QTest.qWait(50)
        assert not w.ihp_cap_corner_button.isHidden()
        prior=clone(w.project['pdk']);assert w.project['analysis']['corner']=='fast'
        w.ihp_cap_corner_button.click();assert not errors and w.project['analysis']['corner']=='fast';assert KEY in w.project['pdk']
        w.undo();assert w.project['pdk']==prior and w.project['analysis']['corner']=='fast'
        w.redo();assert w.project['analysis']['corner']=='fast'
        for key,(section,label) in CHOICES.items():
            idx=w.corner_combo.findData(key);assert idx>=0 and w.corner_combo.itemText(idx)==label
            w.corner_combo.setCurrentIndex(idx);w.corner_combo.activated.emit(idx);assert w.project['analysis']['corner']==key
            path=out/(key+'.icproj');w.path=path;assert w.save();q=load_project(path)
            assert q['analysis']['corner']==key and KEY in q['pdk'] and q['pdk']['package_lock']==prior['package_lock']
            w.set_project(q,path);assert w.corner_combo.currentData()==key and w.corner_combo.currentText()==label
            directory=out/(key+'-staged');deck=stage_model_deck(q['pdk'],spice(q,settings=q['analysis']),directory)
            (directory/'schematic.spice').write_bytes(deck.encode('utf-8'))
            mapping=json.loads((directory/'pdk-model-files.json').read_bytes());entries={v:k for k,v in mapping.items()}
            for item in prior['simulation']['includes']:
                expected=section if item['path']==CAP else item['sections']['nominal']
                assert '.lib '+entries[item['path']]+' '+expected in deck
            assert 'cap_cmim' in deck and 'sg13_lv_nmos' in deck
        native=load_project(bundle_root().parents[2]/'examples/native-divider.icproj');native['pdk']=prior;w.set_project(native);QTest.qWait(20)
        assert w.ihp_cap_corner_button.isHidden();before=clone(w.project['pdk']);w.enable_ihp_capacitor_corners()
        assert errors and 'catalog-backed' in errors[-1] and w.project['pdk']==before
        (out/'result.json').write_text(json.dumps({'status':'PASS_SOURCE_GUI_ONLY','aliases':list(CHOICES),'native_rejected':True},indent=2)+'\n')
    finally:w.close();app.processEvents()

if __name__=='__main__':main(sys.argv[1])
