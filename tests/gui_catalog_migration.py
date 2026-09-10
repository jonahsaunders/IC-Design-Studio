"""Exercise dependency repair, reviewed catalog save and engine persistence."""
import os,sys,tempfile,traceback
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
evidence=ROOT/'build/catalog-migration-evidence';evidence.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(evidence/'profile/data');os.environ['XDG_CONFIG_HOME']=str(evidence/'profile/config')
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QFileDialog
from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import example,load_project,digest
from icstudio.migration_ui import show
from icstudio.pdks import PDKRegistry
from tests.test_catalog_migration import fixture

errors=[]
def exception(t,v,tb):
    errors.append(''.join(traceback.format_exception(t,v,tb)));traceback.print_exception(t,v,tb)
sys.excepthook=exception
app=QApplication([]);QSettings('ICDesignStudio','Studio').clear();w=Studio(recover=False);w.error=lambda text:errors.append(str(text));w.show()
w.saved_hash=digest(w.project)
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);technology,path=fixture(root);w.pdk_registry=PDKRegistry(root/'registry')
    symbol=path.parent/'n.sym';linked=root/'linked.sym';symbol.rename(linked)
    dlg=show(w,source=path);save=dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Save)
    assert not save.isEnabled();assert dlg.locate_button.isEnabled()
    with patch.object(QFileDialog,'getOpenFileName',return_value=(str(linked),'')):dlg.link_file()
    assert save.isEnabled(),dlg.result_data
    dlg.technology.setCurrentIndex(1);assert dlg.result_data['converted']==1,dlg.result_data
    assert save.isEnabled();QTest.qWait(20);assert dlg.grab().save(str(evidence/'migration-review.png'))
    target=root/'native.icproj'
    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'')):save.click()
    assert target.is_file(),errors
    assert w.project['cells'][0]['devices'][0]['model_ref']['device']=='nfet'
    assert w.analysis_engine.currentData()=='ngspice' and not w.analysis_engine.isEnabled()
    assert w.engine_requirement.text()
    w.set_project(example());assert w.analysis_engine.currentData()=='builtin' and w.analysis_engine.isEnabled()
    generic=root/'generic.icproj';w.analysis_engine.setCurrentIndex(w.analysis_engine.findData('ngspice'))
    assert w.analysis_dirty
    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(generic),'')):assert w.save()
    assert load_project(generic)['analysis']['engine']=='ngspice'
    w.set_project(example());assert w.analysis_engine.currentData()=='builtin'
    w.set_project(load_project(generic),generic);assert w.analysis_engine.currentData()=='ngspice' and w.analysis_engine.isEnabled()
    w.analysis_engine.setCurrentIndex(w.analysis_engine.findData('builtin'));assert w.save()
    assert load_project(generic)['analysis']['engine']=='builtin'
    # A file changing while the dialog is open must invalidate its review.
    dlg=show(w,source=path,libraries=[root]);dlg.file_locations[str(path.resolve())+'::n.sym']=str(linked);dlg.rescan()
    save=dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Save);assert save.isEnabled()
    linked.write_text(linked.read_text()+'\n* changed\n');save.click();assert not save.isEnabled();dlg.reject()
    assert not errors,errors
w.analysis_dirty=False;w.saved_hash=digest(w.project);w.close()
print('PASS: link missing symbol, catalog review/save, source-change guard, project-local engine selection and save/reopen.')
