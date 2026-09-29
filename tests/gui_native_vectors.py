"""Real Qt array configuration, bus-label editing, history and native saving."""
import os
import sys
import tempfile
import argparse
import json
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=ROOT/'build/native-vectors-ui-evidence')
args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
profile=out/'profile';profile.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(profile/'data');os.environ['XDG_CONFIG_HOME']=str(profile/'config')
from PySide6.QtWidgets import QApplication,QInputDialog
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import example,device,flatten,save_project,load_project,digest
from icstudio.native_spice import netlist
from icstudio.native_vectors import display_name

app=QApplication([]);w=Studio(recover=False);errors=[];w.error=lambda message:errors.append(str(message))
p=example('empty');p['spice']={'version':1,'assets':{}}
p['cells'][0]['devices']=[device('R','Rbank',300,250,nets={'p':'in','n':'0'})]
w.set_project(p);w.resize(1200,900);w.show();QTest.qWait(50)
ident=w.cell['devices'][0]['id'];w.select([ident],'schematic')
with patch.object(QInputDialog,'getText',return_value=('3:0',True)):
    w.instance_array_action.trigger()
assert not errors,errors
assert w.cell['devices'][0]['array']=={'start':3,'end':0}
assert display_name(w.cell['devices'][0])=='Rbank[3:0]'
# The existing inspector is the native bus editor; no external source is needed.
w.select([ident],'schematic');w.form_fields['net:p'].setText('data[7:6],data[1:0]')
assert w.apply_inspector(True),w.property_error.text()
assert [d['nets']['p'] for d in flatten(w.project)]==['data[7]','data[6]','data[1]','data[0]']
w.undo();assert all(d['nets']['p']=='in' for d in flatten(w.project))
w.redo();assert len(flatten(w.project))==4
# The real placed-label flow accepts an isolated bus without joining its bits.
with patch.object(QInputDialog,'getText',return_value=('data[7:6],data[1:0]',True)):
    w.begin_label()
w.place_label({'kind':'point','point':[650,250]})
assert w.cell['labels'][-1]['name']=='data[7:6],data[1:0]'
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/'native-vectors.icproj';save_project(w.project,path);q=load_project(path)
    assert q['cells']==w.project['cells']
    text=netlist(q,tmp)
    assert 'Rbank__3 data[7] 0 ' in text and 'Rbank__0 data[0] 0 ' in text
assert not errors,errors
QTest.qWait(30);assert w.grab().save(str(out/'native-vectors.png'))
report={'status':'passed','platform':sys.platform,'members':len(flatten(w.project)),
        'checks':['Configure array through its QAction','Edit ordered bus slices in the terminal inspector',
                  'Undo and redo bus connections','Place an explicit bus label','Save and reopen compact native capture',
                  'Emit exact scalar native SPICE members'],'screenshot':'native-vectors.png'}
(out/'native-vectors.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
w.saved_hash=digest(w.project);w.close();print('Native vector GUI acceptance passed')
