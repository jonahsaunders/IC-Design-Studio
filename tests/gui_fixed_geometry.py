"""Exercise the real property editor for typed and five-terminal fixed MOS views."""
import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import digest,example
from icstudio.catalog import create_device
from icstudio.sky130_fixed_geometry import CONTRACTS
from scripts.qualify_standard_mos import load_technology


def main():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['XDG_DATA_HOME']=tmp+'/data';os.environ['XDG_CONFIG_HOME']=tmp+'/config'
        app=QApplication([]);w=Studio(recover=False);errors=[];w.error=lambda text:errors.append(str(text))
        tech,_=load_technology('sky130A');p=example('empty');p['pdk']=tech
        keys=[k for k,e in tech['simulation']['catalog'].items() if e.get('model') in CONTRACTS]
        assert len(keys)==7
        checked=0
        for key in keys:
            d=create_device(tech,key,'DUT');p['cells'][0]['devices']=[d];w.set_project(p)
            w.selection={d['id']};w.build_inspector();app.processEvents()
            for dimension in ('w','l'):
                field=w.form_fields[('param:' if d['kind'] in ('NMOS','PMOS') else 'modelparam:')+dimension]
                assert field.isReadOnly(),key
                before=field.text();field.setFocus();field.selectAll();QTest.keyClicks(field,'100')
                assert field.text()==before,key
                assert 'does not support scaling' in field.toolTip();checked+=1
            mult=w.form_fields['modelparam:mult'];assert not mult.isReadOnly(),key
        assert not errors,errors
        w.analysis_dirty=False;w.saved_hash=digest(w.project);w.close()
        print('PASS: 14 fixed dimension fields reject typing across seven views; all seven parallel factors remain editable.')


if __name__=='__main__':main()
