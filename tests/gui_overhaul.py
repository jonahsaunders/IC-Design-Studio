"""Native acceptance for the GUI overhaul. Runs without external EDA engines."""
import argparse, json, os, sys, traceback
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
os.environ['XDG_DATA_HOME']=str(out/'profile/data')
from PySide6.QtCore import Qt,QPoint,QPointF,QSettings,QTimer
from PySide6.QtWidgets import QApplication,QDockWidget,QDialogButtonBox
from PySide6.QtTest import QTest
from icstudio.gui import Studio
from icstudio.model import example,digest,load_project
from icstudio.canvas import Canvas
from icstudio.grid import visible_interval
from icstudio.menu_map import ALIASES,title

errors=[]
sys.excepthook=lambda t,v,tb:(errors.append(str(v)),traceback.print_exception(t,v,tb))
app=QApplication([]);app.setStyle('Fusion');QSettings('ICDesignStudio','Studio').clear()
w=Studio(recover=False);w.error=lambda e:errors.append(str(e));w.show();QTest.qWait(200)
checks=[]
def passed(text):checks.append(text)
def capture(name):QTest.qWait(80);assert w.grab().save(str(out/name))

# No lost commands, no third-level menus, short Design entry point.
def walk(menu,depth=1):
    assert depth<=2,(menu.title(),depth)
    result=[]
    for action in menu.actions():
        if action.isSeparator():continue
        if action.menu():result.extend(walk(action.menu(),depth+1))
        else:result.append(action)
    return result
actions=[]
menu_counts={}
for name,menu in w.task_menus.items():
    actions.extend(walk(menu));menu_counts[name]=len([a for a in menu.actions() if not a.isSeparator()])
assert not w.unmapped_commands,w.unmapped_commands
for name,action in w.command_actions.items():
    assert action in actions or name in ALIASES,name
assert menu_counts['Design']<=10,menu_counts
assert all(a in [item for _,item in w._commands] for a in actions)
passed('Every original command remains reachable; Design has 10 entries; at most one submenu level')

# Grid is generated from snap coordinates, independent of zoom and pan.
for base in (5,10,7):
    for scale in (.00001,.001,.08,.67,1,5,80):
        step=visible_interval(base,scale)
        assert step*scale>=14-1e-8
        assert abs(step/base-round(step/base))<1e-7
        assert step*scale<36 or base*scale>=14
passed('Adaptive grid intervals are integral snap multiples at every tested zoom')
c=Canvas('layout');c.resize(400,300);c.tech={'grid':7};c.scale=2;c.offset=QPointF(-19,31)
c.grid_density=14;c.grid_contrast=100;c.grid_origin=False
for dark in (False,True):
    c.dark=dark;c.grid_style='lines';img=c.grab().toImage();step=c.grid_interval()*c.scale
    x=round(c.offset.x()+5*step);y=87
    assert img.pixelColor(x,y)!=img.pixelColor(x+3,y)
    before=c.snap(QPointF(43.7,-17.3))
    c.grid_style='off';off=c.grab().toImage()
    assert off.pixelColor(x,y)==off.pixelColor(x+3,y)
    assert c.snap(QPointF(43.7,-17.3))==before==QPointF(42,-14)
    c.grid_style='dots';assert c.grab().toImage()!=off
passed('Grids render at negative pan offsets in light/dark; hiding the grid preserves placement snapping')

before=digest(w.project);dlg=w.grid_settings_dialog()
style,contrast,density,origin=dlg.fields['schematic']
style.setCurrentIndex(style.findData('dots'));contrast.setValue(90);density.setValue(12);origin.setChecked(False)
assert w.schematic.grid_style=='dots' and w.layout.grid_style=='lines'
assert digest(w.project)==before
dlg.reject();w.schematic.setFocus();QTest.keyClick(w.schematic,Qt.Key_G,Qt.ControlModifier|Qt.ShiftModifier)
assert w.schematic.grid_style=='off';w.grid_toggle_action.trigger();assert w.schematic.grid_style=='dots'
passed('Grid dialog and keyboard visibility toggle act on the active editor without changing the project')

# Click the new command strip, place a component, then undo the transaction.
w.capture_repeat.setChecked(False);w.ribbon.setCurrentIndex(0)
button=next(b for b,_ in w.ribbon_buttons if b.text()=='Component')
QTest.mouseClick(button,Qt.LeftButton);assert w.navtabs.currentIndex()==1
w.begin_placement(1);point=QPoint(170,160);snap=w.schematic.snap(w.schematic.model(QPointF(point)))
count=len(w.cell['devices']);QTest.mouseClick(w.schematic,Qt.LeftButton,pos=point)
assert len(w.cell['devices'])==count+1
assert (w.cell['devices'][-1]['x'],w.cell['devices'][-1]['y'])==(snap.x(),snap.y())
w.undo();assert len(w.cell['devices'])==count
passed('Labeled component command opens the device library; pointer placement snaps and undoes atomically')

w.set_project(example('empty'));w.apply_workspace_preset('Layout');QTest.qWait(70)
button=next(b for b,_ in w.ribbon_buttons if b.text()=='Rectangle')
QTest.mouseClick(button,Qt.LeftButton);assert w.layout.tool=='rect'
QTest.mousePress(w.layout,Qt.LeftButton,pos=QPoint(110,110))
QTest.mouseMove(w.layout,QPoint(200,170));QTest.mouseRelease(w.layout,Qt.LeftButton,pos=QPoint(200,170))
assert len(w.cell['shapes'])==1
assert all(v%w.project['pdk']['grid']==0 for pt in w.cell['shapes'][0]['points'] for v in pt)
w.undo();assert not w.cell['shapes'];w.cancel_tool()
passed('Labeled rectangle command draws actual PDK-grid geometry and preserves Undo')

# Window controls: float, redock, hide, lock, presets, orientation and save/restore.
dlg=w.configure_windows();dock,show,position=dlg.fields[1]
position.setCurrentText('Floating');QTest.qWait(30);assert dock.isFloating()
position.setCurrentText('Left');QTest.qWait(30);assert not dock.isFloating() and w.dockWidgetArea(dock)==Qt.LeftDockWidgetArea
show.setChecked(False);assert dock.isHidden();show.setChecked(True);assert not dock.isHidden()
dlg.reject();w.set_panel_lock(True)
assert not (w.inspector.features() & QDockWidget.DockWidgetMovable)
w.reset_workspace();assert not w._layout_locked and w.inspector.isVisible()
assert w.dockWidgetArea(w.inspector)==Qt.RightDockWidgetArea
passed('Window controls float, redock, hide and restore panels; locking and reset work')
QTest.mouseDClick(w.inspector.titleBarWidget(),Qt.LeftButton,pos=QPoint(30,14));QTest.qWait(30)
assert w.inspector.isFloating()
QTest.mouseClick(w.panel_float_buttons[1],Qt.LeftButton);assert not w.inspector.isFloating()
passed('Panel title double-click and visible float button both change native docking')

w.arrange_linked(Qt.Vertical);QTest.qWait(50)
assert w.mode_combo.currentIndex()==2 and w.canvases.orientation()==Qt.Vertical
w.activateWindow();w.layout.setFocus();QTest.qWait(30);assert w.current_mode=='layout' and w._ribbon_mode=='layout'
w.schematic.setFocus();QTest.qWait(10);assert w.current_mode=='schematic'
passed('Stacked linked views select the correct contextual ribbon when focus changes')
w.results_dock.show();w.results_tabs.setCurrentIndex(1);w.inspector.hide();w.schematic.grid_style='dots'
w.set_panel_lock(True);w.save_editor_workspace('Review custom')
w.reset_workspace();w.load_editor_workspace('Review custom');QTest.qWait(80)
assert w.canvases.orientation()==Qt.Vertical and w.mode_combo.currentIndex()==2
assert w.inspector.isHidden() and w.results_dock.isVisible() and w.results_tabs.currentIndex()==1
assert w.schematic.grid_style=='dots' and w._layout_locked
passed('Saved workspaces restore orientation, visibility, selected result, grid appearance and panel lock')

# Legacy sessions without the new metadata still restore.
data=json.loads(w.settings.value('editor/workspaces/Review custom'));data.pop('human')
w.settings.setValue('editor/workspaces/Legacy',json.dumps(data));w.load_editor_workspace('Legacy')
assert w.mode_combo.currentIndex()==2
passed('Existing 0.13 named workspaces remain readable')

w.reset_workspace();w.set_project(example());w.select([w.cell['devices'][1]['id']])
w.form_fields['Value'].setText('invalid');state=bytes(w.saveState(3))
w.apply_workspace_preset('Layout');assert w.current_mode=='schematic' and bytes(w.saveState(3))==state
w.form_fields['Value'].setText('10k');w.flush_inspector();w.select([])
passed('Invalid property drafts block workspace changes without discarding edits')

# Inspect every ribbon page and all result tabs at compact size, checking actual bounds.
w.resize(1100,760);w.reset_workspace();QTest.qWait(80)
for mode in (0,1):
    w.mode_combo.setCurrentIndex(mode);QTest.qWait(50)
    for i in range(3):
        w.ribbon.setCurrentIndex(i);QTest.qWait(30)
        page=w.ribbon.currentWidget()
        for b,_ in w.ribbon_buttons:
            if b.parentWidget()==page:
                assert page.rect().contains(b.geometry()),(mode,i,b.text(),page.rect(),b.geometry())
    w.ribbon.setCurrentIndex(0)
    for i in range(w.results_tabs.count()):
        w.results_dock.show();w.results_tabs.setCurrentIndex(i);QTest.qWait(30)
        assert w.results_dock.geometry().right()<w.inspector.geometry().left(),(i,w.results_dock.geometry(),w.inspector.geometry())
        assert w.schematic.height()>=220 if mode==0 else w.layout.height()>=220
    w.results_dock.hide()
assert w.width()==1100
passed('All named ribbon controls fit; result tabs stay inside their dock without overlapping Inspector at 1100×760')

# Deliverable screenshots, showing real example designs.
w.resize(1440,900);w.set_project(example());w.reset_workspace();w.dark=False;w.apply_theme()
w.schematic.grid_style='lines';w.schematic.grid_contrast=65;w.schematic.grid_density=14;w.schematic.grid_origin=True
w.fit_active();capture('schematic-light.png');w.dark=True;w.apply_theme();capture('schematic-dark.png')
w.set_project(load_project(ROOT/'examples/inverter_layout.icproj'));w.apply_workspace_preset('Layout')
w.fit_active();capture('layout-dark.png');w.dark=False;w.apply_theme();capture('layout-light.png')
w.resize(1100,760);capture('layout-compact.png')
w.resize(1440,900);dlg=w.configure_windows();QTest.qWait(70);assert dlg.grab().save(str(out/'configure-windows.png'));dlg.reject()
w.arrange_linked(Qt.Horizontal);w.inspector.hide();w.fit_active();capture('linked-views.png')
w.focus_canvas();assert all(d.isHidden() for d in w.workspace_docks());w.focus_canvas();assert w.nav.isVisible()
passed('Focus mode restores the previous panel visibility')
assert not errors,errors
w.saved_hash=digest(w.project);w.close();QTest.qWait(50)
second=Studio(recover=False);second.show();QTest.qWait(220)
assert second.mode_combo.currentIndex()==2 and second.inspector.isHidden()
second.saved_hash=digest(second.project);second.close()
passed('Closing and reopening restores the last session workspace')
(out/'report.json').write_text(json.dumps({'status':'passed','checks':checks,'menu_entries':menu_counts,
    'errors':errors,'qualification':'Automated native Qt offscreen tests; physical display and human user studies were not run.'},indent=2))
print(json.dumps({'status':'passed','checks':len(checks),'menu_entries':menu_counts}))
