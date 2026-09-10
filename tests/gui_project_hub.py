"""Real Qt acceptance for new projects, version inventory and offline installation."""
import os,sys,tempfile,json,time,traceback
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
OUT=ROOT/'build/project-hub-evidence';OUT.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(OUT/'profile/data');os.environ['XDG_CONFIG_HOME']=str(OUT/'profile/config')
from PySide6.QtCore import Qt,QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QFileDialog
from icstudio.gui import Studio
from icstudio.pdks import PDKRegistry
from icstudio.project_manager import ProjectIndex
from icstudio.model import digest,save_project
from tests.test_pdk_templates import install_fixture

errors=[]
def exception(t,v,tb):errors.append(str(v));traceback.print_exception(t,v,tb)
sys.excepthook=exception
app=QApplication([]);QSettings('ICDesignStudio','Studio').clear();w=Studio(recover=False);w.error=errors.append;w.show()
def wait(worker):
    deadline=time.monotonic()+30
    while worker and worker.isRunning() and time.monotonic()<deadline:
        app.processEvents();time.sleep(.01)  # Let Python PDK workers acquire the GIL.
    assert not worker.isRunning(),'PDK operation timed out'
    QTest.qWait(30);assert not errors,errors

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);w.pdk_registry=PDKRegistry(root/'registry');w.project_index=ProjectIndex(root/'projects')
    # Fresh New Project shows both included PDKs immediately, before registration.
    dlg=w.new_project();assert len([r for r in dlg.rows if r['status']=='Available offline'])==2
    dlg.show_page('pdks');key=next(r['key'] for r in dlg.rows if r['id']=='sky130A');assert dlg.select_pdk(key)
    assert dlg.revision.text().endswith(key.split('@')[1]);assert dlg.install_button.isEnabled()
    QTest.qWait(40);assert dlg.grab().save(str(OUT/'pdks-available.png'))
    old=digest(w.project);dlg.install_button.click();wait(dlg.worker);assert digest(w.project)==old
    assert dlg.current_pdk()['status']=='Installed';assert sum(r['key']==key for r in dlg.rows)==1
    dlg.verify_button.click();wait(dlg.worker);assert 'Verified' in dlg.state.text()
    assert dlg.grab().save(str(OUT/'pdks-installed.png'))
    dlg.search.setText('no-matching-technology');assert dlg.pdks.currentRow()==-1 and not dlg.create_button.isEnabled()
    dlg.search.clear();dlg.filter.setCurrentText('Installed');assert all(dlg.pdks.item(i).isHidden() or dlg.pdks.item(i).data(Qt.UserRole)['status']=='Installed' for i in range(dlg.pdks.count()))
    # Different revisions and a future family appear without adding menu entries.
    manifest=install_fixture(root/'future','future-process');one=w.pdk_registry.install(manifest)
    data=json.loads(manifest.read_text());data['revision']='second';manifest.write_text(json.dumps(data));two=w.pdk_registry.install(manifest)
    dlg.refresh();dlg.select_pdk(one);dlg.show_page('new');dlg.name.setText('Hub inverter');dlg.template.setCurrentIndex(dlg.template.findData('inverter'));dlg.supply.setText('1.2')
    assert dlg.nmos.count()==1 and dlg.pmos.count()==1;assert dlg.create_button.isEnabled()
    dlg.create_button.click();wait(dlg.worker);assert not dlg.isVisible(),dlg.state.text()
    assert w.project['pdk']['package_lock']['revision']=='fixture';assert w.project['name']=='Hub inverter'
    assert w.analysis_engine.currentData()=='ngspice';assert w.cell['ports']==['A','Y','VPWR','VGND']
    path=root/'project.icproj';save_project(w.project,path);w.set_project(w.project,path)
    dlg=w.project_manager();assert dlg.pages.currentIndex()==0 and dlg.projects.count()==1
    assert 'future-process' in dlg.projects.item(0).text() and 'fixture' in dlg.projects.item(0).text()
    dlg.grab().save(str(OUT/'projects.png'));dlg.open_button.click();assert not dlg.isVisible()
    # Model selections survive page navigation. Unknown/new packages use the same UI.
    dlg=w.new_project();dlg.select_pdk(key);dlg.template.setCurrentIndex(dlg.template.findData('inverter'))
    assert dlg.nmos.count()>1;dlg.nmos.setCurrentIndex(1);selected=dlg.nmos.currentData();dlg.show_page('pdks');dlg.show_page('new');assert dlg.nmos.currentData()==selected
    QTest.qWait(40);dlg.grab().save(str(OUT/'new-project.png'))
    # Opening local setup and closing it refreshes the hub without changing technology.
    dlg.open_setup();setup=w._setup_dialog
    source=install_fixture(root/'added','added-locally');setup.start_operation('register',[{'name':'added-locally','kind':'package','path':str(source.parent)}]);wait(setup.worker)
    setup.close();QTest.qWait(20);assert any(r['id']=='added-locally' for r in dlg.rows)
    # Offline create performs installation in the worker, before opening the project.
    gf=next(r['key'] for r in dlg.rows if r['id']=='gf180mcuD');dlg.select_pdk(gf);dlg.template.setCurrentIndex(dlg.template.findData('empty'));dlg.name.setText('Offline GF180 project')
    assert dlg.create_button.text()=='Install PDK & create project'
    before=digest(w.project)
    with patch.object(w,'_replace_document',return_value=False):
        dlg.create_button.click();wait(dlg.worker)
    assert dlg.isVisible() and digest(w.project)==before
    assert dlg.current_pdk()['status']=='Installed' and dlg.create_button.text()=='Create project'
    dlg.create_button.click();wait(dlg.worker);assert not dlg.isVisible(),dlg.state.text()
    assert w.project['pdk']['package_lock']['id']=='gf180mcuD'
    # Integrity errors leave the current project untouched; missing folders can be located.
    dlg=w.new_project();dlg.select_pdk(two);model=w.pdk_registry.root/two/'models.spice';original=model.read_bytes();model.write_text('damaged')
    before=digest(w.project);dlg.create_button.click();wait(dlg.worker);assert dlg.isVisible() and digest(w.project)==before
    assert 'missing or changed' in dlg.state.text();model.write_bytes(original)
    dlg.show_page('pdks');row=dlg.current_pdk();m=w.pdk_registry.manifest(two);m['source_root']=str(root/'missing-folder')
    (w.pdk_registry.root/two/'package.json').write_text(json.dumps(m));dlg.refresh();assert dlg.current_pdk()['status']=='Folder missing'
    with patch.object(QFileDialog,'getExistingDirectory',return_value=str(model.parent)):dlg.locate_button.click()
    wait(dlg.worker);assert dlg.current_pdk()['status']=='Installed';dlg.reject()
    # The window cannot destroy a running PDK worker.
    import threading
    gate=threading.Event();dlg=w.new_project();dlg.run_operation(lambda:gate.wait(10),lambda _:None,'Testing worker close guard')
    dlg.reject();assert dlg.isVisible();w.close();assert w.isVisible();gate.set();wait(dlg.worker);dlg.reject()
    assert not errors,errors
w.saved_hash=digest(w.project);w.close()
(OUT/'result.json').write_text(json.dumps({'status':'passed','checks':['Fresh bundled visibility','Offline install and verify','Multiple exact revisions','PDK search/filter','Native model project creation','Recent projects','Model choice retention','Setup refresh','Offline install-and-create','Cancelled project replacement','Tampered models blocked','Locate missing installation','Worker close guard']},indent=2))
print('PASS: project hub inventory, offline setup, exact-revision creation, recent projects, integrity and worker lifecycle.')
