"""Native Qt integration of project/PDK/symbol/layer workflows."""
import os,sys,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));profile=ROOT/'build/gui-project-pdk-profile';profile.mkdir(parents=True,exist_ok=True);os.environ['XDG_DATA_HOME']=str(profile/'data');os.environ['XDG_CONFIG_HOME']=str(profile/'config')
from PySide6.QtWidgets import QApplication,QFileDialog,QMessageBox
from PySide6.QtCore import Qt,QPointF
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import example,clone,digest,load_project
from icstudio.catalog import link_technology
from icstudio.pdks import PDKRegistry
from icstudio.layout import rect
errors=[]
def report_exception(t,v,tb):
 import traceback
 errors.append(str(v));traceback.print_exception(t,v,tb)
sys.excepthook=report_exception
app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.error=lambda text:errors.append(text);w.show();QTest.qWait(100)
# Use actual locally indexed SKY130 when the integration asset tree is present.
registry=PDKRegistry(ROOT/'build/pdk-registry');entry=next((e for e in registry.entries() if e['id']=='sky130A'),None)
if entry:
 tech=registry.technology(entry['id']+'@'+entry['revision']);w.set_project(example('empty'));w.commit(lambda p:link_technology(p,tech));w.sync_technology();w.library_category.setCurrentText('NMOS');w.library_search.setText('nfet_01v8');QTest.qWait(20)
 available=[w.library_list.item(i) for i in range(w.library_list.count()) if not w.library_list.item(i).isHidden() and not w.library_list.item(i).data(Qt.UserRole+3)];assert len(available)>=2
 w.begin_placement('sky130_fd_pr/nfet_01v8.sym');w.rotate();w.place_device_at(300,250);first=w.cell['devices'][-1];assert first['rotation']==90 and first['model_ref']['device'].endswith('nfet_01v8.sym')
 w.begin_placement('sky130_fd_pr/nfet_01v8_lvt.sym');w.place_device_at(600,250);second=w.cell['devices'][-1];assert second['model_ref']!=first['model_ref'];assert 'param:kp' not in w.form_fields
 w.duplicate();assert len(w.cell['devices'])==3;w.undo();assert len(w.cell['devices'])==2;w.redo();w.undo()
 w.select([first['id']]);w.edit_selected_symbol();dlg=w._symbol_dialog;QTest.qWait(30);old=clone(dlg.pad.symbol);dlg.pad.selection=0;dlg.pad.delete();assert dlg.pad.symbol!=old;dlg.pad.undo();assert dlg.pad.symbol==old;dlg.pad.redo();dlg.pad.undo();dlg.reject()
# Layout isolation, lock, fit and hierarchy controls.
w.set_project(example('empty'));w.add_shape(rect('metal1',0,0,1000,1000));w.add_shape(rect('metal2',1500,0,1000,1000));w.mode_combo.setCurrentIndex(1);w.layer_combo.setCurrentText('metal1');w.show_layers('solo');assert w.layout.visible_layers=={'metal1'};w.layout.locked_layers={'metal1'};assert w.layout.hit(QPointF(500,500)) is None;w.layout.locked_layers=set();assert w.layout.hit(QPointF(500,500)) is not None;w.show_layers('all');w.select([w.cell['shapes'][0]['id']],'layout');w.fit_selection();assert not w.layout.auto_fit
# Project file save/index and recoverable deletion through the controller.
with tempfile.TemporaryDirectory() as td:
 path=Path(td)/'managed.icproj';old_dialog=QFileDialog.getSaveFileName;QFileDialog.getSaveFileName=lambda *a,**k:(str(path),'');assert w.save();QFileDialog.getSaveFileName=old_dialog;assert w.project_index.entries()[0]['path']==str(path)
 old_question=QMessageBox.question;QMessageBox.question=lambda *a,**k:QMessageBox.Yes;w.delete_project_dialog();QMessageBox.question=old_question;assert not path.exists();record=next(r for r in w.project_index.deleted() if r['original']==str(path));w.project_index.restore(record);assert load_project(path)['name']=='Untitled circuit'
# All new views open using their actual Qt controls.
w.project_manager();QTest.qWait(30);w._projects_dialog.close();w.project_settings();QTest.qWait(30);w._settings_dialog.close();w.pdk_manager();QTest.qWait(30);w._pdk_dialog.close();w.symbol_dialog();QTest.qWait(30);w._symbol_dialog.close()
assert not errors,errors
w.saved_hash=digest(w.project);w.close();print('PASS: real PDK filtering and distinct placement, rotation, duplication/history, symbol editing, layer isolation/locking, project save/delete/restore and workspace dialogs.')
