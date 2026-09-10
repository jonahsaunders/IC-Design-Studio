"""Exercise neutral menu entry points and conflict resolution in real Qt."""
import os,sys,re,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
profile=ROOT/'build/gui-interoperability';profile.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(profile/'data');os.environ['XDG_CONFIG_HOME']=str(profile/'config')
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QComboBox,QMessageBox
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import example,digest
from icstudio.layout import rect,kdb
from icstudio.interchange import export_layout
from tests.test_pdk_templates import install_fixture
errors=[]
def exception(t,v,tb):
    import traceback
    errors.append(str(v));traceback.print_exception(t,v,tb)
sys.excepthook=exception
app=QApplication([]);app.setStyle('Fusion');window=Studio(recover=False);window.error=lambda text:errors.append(text)
def unexpected_dialog():
    for widget in app.topLevelWidgets():
        if isinstance(widget,QMessageBox) and widget.isVisible():
            errors.append('Unexpected dialog: '+widget.text());widget.reject()
timer=QTimer();timer.timeout.connect(unexpected_dialog);timer.start(200)
window.dark=False;window.apply_theme();window.show();QTest.qWait(50)
with tempfile.TemporaryDirectory() as folder:
    root=Path(folder)
    for identifier in ('sky130A','gf180mcuC','gf180mcuD','ihp-sg13g2','future-process'):
        window.pdk_registry.install(install_fixture(root/identifier,identifier))
    for action in window.menuBar().actions():
        menu=action.menu()
        if menu:
            for entry in menu.actions():assert not re.search(r'sky130|gf180|\bihp\b',entry.text(),re.I),entry.text()
    dlg=window.new_project();QTest.qWait(30)
    assert len(dlg.rows)>=6
    assert all(not re.search(r'sky130|gf180|\bihp\b',dlg.template.itemText(i),re.I) for i in range(dlg.template.count()))
    dlg.template.setCurrentIndex(dlg.template.findData('inverter'));assert dlg.select_pdk('ihp-sg13g2@fixture')
    assert dlg.nmos.count()==1 and dlg.pmos.count()==1
    dlg.supply.setText('1.2');QTest.qWait(30);assert dlg.grab().save(str(profile/'new-circuit.png'))
    window.saved_hash=digest(window.project)
    buttons=dlg.findChild(QDialogButtonBox);buttons.button(QDialogButtonBox.Ok).click()
    import time
    deadline=time.monotonic()+30
    while dlg.worker.isRunning() and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert not dlg.worker.isRunning();QTest.qWait(60)
    assert not dlg.isVisible();assert window.project['pdk']['package_lock']['id']=='ihp-sg13g2';assert window.cell['ports']==['A','Y','VPWR','VGND']
    p=example();p['cells'][0]['shapes']=[rect('metal1',0,0,1000,1000)];window.set_project(p)
    path=root/'exchange.gds';export_layout(window.project,path)
    ly=kdb().Layout();ly.read(str(path));shape=next(ly.top_cell().shapes(ly.layer(4,0)).each());shape.transform(kdb().Trans(100,0));ly.write(str(path))
    window.commit(lambda p:p['cells'][0]['shapes'][0].update(points=[[200,0],[1200,1000]]),'Local move')
    dlg=window.show_layout_exchange(path);QTest.qWait(30);assert dlg.table.rowCount()>0
    assert not dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).isEnabled()
    assert dlg.grab().save(str(profile/'layout-conflict.png'))
    while dlg.table.rowCount():
        selector=dlg.table.cellWidget(0,3);selector.setCurrentIndex(selector.findData('external'));QTest.qWait(10)
    dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click();QTest.qWait(30)
    assert window.cell['shapes'][0]['points'][0][0]==100
    window.undo();assert window.cell['shapes'][0]['points'][0][0]==200
    assert not errors,errors
window.saved_hash=digest(window.project);window.close();app.processEvents()
print('PASS: neutral menus, extensible secondary PDK/model selection, reviewed layout conflicts and undo.')
