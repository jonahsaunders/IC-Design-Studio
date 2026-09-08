"""Exercise 0.6 lifecycle actions using actual Qt dialog controls."""
import os,sys,tempfile,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
profile=ROOT/'build/gui-lifecycle-profile';profile.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(profile/'data');os.environ['XDG_CONFIG_HOME']=str(profile/'config')
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QInputDialog,QFileDialog,QComboBox
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import example,clone,digest,device,uid,flatten
from icstudio.catalog import create_device
from icstudio.interchange import pin_positions
import test_project_pdk

errors=[]
def exception(t,v,tb):
    import traceback
    errors.append(str(v));traceback.print_exception(t,v,tb)
sys.excepthook=exception
app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.error=lambda e:errors.append(str(e));w.show();QTest.qWait(80)
with tempfile.TemporaryDirectory() as td:
    root=Path(td);tech=test_project_pdk.ProjectPDKTests().technology(root)
    p=example('empty');p['pdk']=tech;d=create_device(tech,'nmos_a','M1');p['cells'][0]['devices']=[d];w.set_project(p);w.select([d['id']])
    before=pin_positions(d);w.replace_model_dialog();QTest.qWait(20);dlg=w._review_dialog
    combo=dlg.findChild(QComboBox);combo.setCurrentIndex(combo.findData('nmos_b'))
    next(b for b in dlg.findChildren(__import__('PySide6.QtWidgets',fromlist=['QPushButton']).QPushButton) if b.text()=='Preview changes').click()
    dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click();QTest.qWait(20)
    assert w.cell['devices'][0]['model_ref']['device']=='nmos_b';assert pin_positions(w.cell['devices'][0])==before
    w.undo();assert w.cell['devices'][0]['model_ref']['device']=='nmos_a'
    manifest=json.loads((root/'package.json').read_text());manifest['revision']='r2';(root/'package.json').write_text(json.dumps(manifest));w.pdk_registry.install(root/'package.json')
    old_item=QInputDialog.getItem;QInputDialog.getItem=lambda *a,**kw:('test_pdk@r2',True)
    w.migrate_pdk_dialog();QInputDialog.getItem=old_item;dlg=w._review_dialog;QTest.qWait(20);dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click()
    assert w.project['pdk']['package_lock']['revision']=='r2';w.undo();assert w.project['pdk']['package_lock']['revision']=='r1'
    old_save=QFileDialog.getSaveFileName;QFileDialog.getSaveFileName=lambda *a,**kw:(str(root/'independent.icproj'),'')
    w.duplicate_project_dialog();QFileDialog.getSaveFileName=old_save
    assert json.loads((root/'independent.icproj').read_text())['id']!=w.project['id']
    # A real imported parameterized component can be placed and edited in Inspector.
    path=root/'component.spice';path.write_text('* component\n.subckt resistor a b r=10k\nR1 a b {r}\n.ends\n.end\n')
    from icstudio.components import import_component
    q=example('empty');cid=import_component(q,path,'resistor');w.set_project(q);w.begin_placement({'cell':cid});w.place_device_at(300,200)
    instance=w.cell['devices'][0];assert 'instanceparam:r' in w.form_fields
    edit=w.form_fields['instanceparam:r'];edit.setText('20k');w.inspector_changed();assert w.flush_inspector();assert float(flatten(w.project)[0]['value'])==20000
    w.cid=cid;w.selection=[];w.refresh();w.component_dialog();dlg=w._workflow_dialog;dlg.fields['ports'].setText('b a');dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
    assert w.cell['ports']==['b','a']
    w.runtime_dialog();QTest.qWait(20);w._runtime_dialog.close()
    output=ROOT/'build/verification-0.6.0';output.mkdir(exist_ok=True);w.grab().save(str(output/'component-workspace.png'))
assert not errors,errors
w.saved_hash=digest(w.project);w.close()
print('PASS: Qt replacement preview/apply/undo, PDK migration/apply/undo, independent project copy, component placement/parameter inspector/terminal order, runtime dialog.')
