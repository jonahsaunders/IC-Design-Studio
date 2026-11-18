"""Exercise 0.6 lifecycle actions using actual Qt dialog controls."""
import os,sys,tempfile,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
profile=ROOT/'build/gui-lifecycle-profile';profile.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(profile/'data');os.environ['XDG_CONFIG_HOME']=str(profile/'config')
from PySide6.QtCore import Qt, QSettings, QStandardPaths
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QFileDialog,QComboBox,QPlainTextEdit
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import example,clone,digest,device,uid,flatten
from icstudio.catalog import create_device
from icstudio.interchange import pin_positions
from icstudio.layout import rect
import test_project_pdk

errors=[]
def exception(t,v,tb):
    import traceback
    errors.append(str(v));traceback.print_exception(t,v,tb)
sys.excepthook=exception
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(profile/'config'))
QStandardPaths.writableLocation = staticmethod(lambda kind: str(profile/'data'/str(kind.value)))
app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.error=lambda e:errors.append(str(e));w.show();QTest.qWait(80)

def wait_for_review(dlg):
    for _ in range(100):
        if dlg.worker is None:
            return
        QTest.qWait(20)
    raise AssertionError('PDK verification did not finish')

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
    dlg=w.migrate_pdk_dialog();QTest.qWait(20);dlg.review.click();wait_for_review(dlg)
    assert dlg.apply_button.isEnabled(),dlg.status.text()
    dlg.apply_button.click()
    assert w.project['pdk']['package_lock']['revision']=='r2';w.undo();assert w.project['pdk']['package_lock']['revision']=='r1'
    manifest.update(id='alternate_kit', revision='r3')
    entry=manifest['technology']['simulation']['catalog']['nmos_b']
    entry['parameters']['l'].update(default='.25', minimum=.2)
    (root/'package.json').write_text(json.dumps(manifest));w.pdk_registry.install(root/'package.json')
    w.commit(lambda p:p['cells'][0]['shapes'].append(rect('metal1',0,0,100,100)))
    original=digest(w.project)
    dlg=w.switch_pdk_dialog();dlg.search.setText('alternate r3')
    QTest.keyClick(dlg.search, Qt.Key_Return);wait_for_review(dlg)
    combo=next(iter(dlg.models.values()));assert not dlg.apply_button.isEnabled()
    combo.setCurrentIndex(combo.findData('nmos_b'));dlg.review.click()
    assert 'outside its PDK minimum' in dlg.status.text() and not dlg.apply_button.isEnabled()
    dlg.defaults.setChecked(True);dlg.review.click()
    assert dlg.apply_button.text()=='Save Project Copy…' and dlg.apply_button.isEnabled(),dlg.status.text()
    assert 'layout objects' in dlg.preview.toPlainText()
    old_save=QFileDialog.getSaveFileName;QFileDialog.getSaveFileName=lambda *a,**kw:(str(root/'process-copy.icproj'),'')
    dlg.apply_button.click();QFileDialog.getSaveFileName=old_save
    from icstudio.model import load_project
    copy=load_project(root/'process-copy.icproj')
    mapped=copy['cells'][0]['devices'][0]
    assert copy['id']!=w.project['id'] and digest(w.project)==original
    assert copy['copied_from']['design_hash']==original and not copy['cells'][0]['shapes']
    assert mapped['params']['l']=='0.25u' and mapped['model_ref']['pdk']=='alternate_kit'
    assert pin_positions(mapped)==before

    w.set_project(example('rc'))
    dlg=w.switch_pdk_dialog(preferred='alternate_kit@r3');dlg.review.click();wait_for_review(dlg)
    assert dlg.apply_button.isEnabled(), dlg.status.text()
    w.commit(lambda p:p.update(name='Changed while reviewing'))
    dlg.apply_button.click()
    assert dlg.isVisible() and 'changed' in dlg.status.text() and not w.project['pdk'].get('package_lock')
    dlg.review.click();assert dlg.apply_button.isEnabled(), dlg.status.text()
    dlg.apply_button.click()
    assert w.project['pdk']['package_lock']['id']=='alternate_kit'
    w.undo();assert not w.project['pdk'].get('package_lock') and len(w.cell['devices'])==3

    from icstudio.layout_collaboration import Session
    folder = root/'shared-folder'
    w.layout_session = Session.create(folder, w.project, 'Alice')
    peer = Session.join(folder, 'Bob')
    peer.claim(w.cid)
    remote = clone(peer.base)
    remote['cells'][0]['devices'][1]['value'] = '15k'
    peer.publish(remote)
    w.commit(lambda p:p['cells'][0]['devices'][2].update(value='9p'))
    before_preview = digest(w.project)
    dashboard = w.collaboration_dashboard(2)
    shared = w.shared_layout_preview()
    report = shared.findChild(QPlainTextEdit).toPlainText()
    assert 'Incoming changes (1)' in report and 'R1' in report
    assert 'Your changes still to publish (1)' in report and 'C1' in report
    assert digest(w.project) == before_preview and w.layout_session.revision == 0
    shared.reject()
    dlg = w.switch_pdk_dialog(preferred='alternate_kit@r3')
    dlg.review.click();wait_for_review(dlg)
    assert dlg.apply_button.isEnabled() and dlg.apply_button.text() == 'Save Project Copy…'
    dlg.reject()
    w.shared_layout_leave()
    dashboard.hide()

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
print('PASS: Qt model replacement, undoable PDK changes, explicit cross-process mapping, dimension review, physical-design safe copy, stale preview rejection, component and runtime workflows.')
