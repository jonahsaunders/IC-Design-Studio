"""Audit menu entry points and tabs; cancel dialogs and inventory controls.

This smoke sweep reports prerequisite guards separately. Format round trips and
actual simulations are covered by the action-specific acceptance probes.
"""
import argparse,json,os,sys,time,traceback
from pathlib import Path
from unittest.mock import patch
# Windows CI can expose a legacy console encoding even though menu labels and
# prerequisite guidance contain Unicode arrows. Diagnostics must not abort the
# sweep before its final assertions and reports are written.
for stream in (sys.stdout,sys.stderr):
    if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='backslashreplace')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=ROOT/'build/menu-audit')
out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
os.environ.update(XDG_CONFIG_HOME=str(out/'config'),XDG_DATA_HOME=str(out/'data'))
from PySide6.QtWidgets import QApplication,QDialog,QFileDialog,QInputDialog,QMessageBox,QTabWidget,QPushButton,QToolButton
from PySide6.QtCore import QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtTest import QTest
from shiboken6 import isValid
from icstudio.gui import Studio
from icstudio.model import example,digest
app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);w.maybe_save=lambda:True;w.show();current={};report=[];fatal=[]
def hook(t,v,tb):
    current.setdefault('exceptions',[]).append(''.join(traceback.format_exception(t,v,tb)))
    traceback.print_exception(t,v,tb)
sys.excepthook=hook
w.error=lambda text:current.setdefault('messages',[]).append(str(text))
def guard(fn):
    try:return fn()
    except Exception as exc:
        current.setdefault('guarded',[]).append(dict(type=type(exc).__name__,message=str(exc)))
w.guard=guard

def dismiss():
    for d in app.topLevelWidgets():
        if d is not w and isinstance(d,QDialog) and d.isVisible():
            title=d.windowTitle()
            if title not in current.setdefault('dialogs',[]):current['dialogs'].append(title)
            for tab in d.findChildren(QTabWidget):
                for i in range(tab.count()):
                    tab.setCurrentIndex(i)
                    current.setdefault('dialog_tabs',[]).append(tab.tabText(i))
            current.setdefault('dialog_buttons',[]).extend(b.text() for b in d.findChildren(QPushButton) if b.text())
            d.reject()
timer=QTimer();timer.timeout.connect(dismiss);timer.start(30)
def walk(menu,prefix=''):
    for a in menu.actions():
        if a.isSeparator():continue
        name=prefix+a.text().replace('&','')
        if a.menu():yield from walk(a.menu(),name+' / ')
        else:yield name,a
menus=list(walk(w.menuBar()))
patches=[patch.object(QFileDialog,'getOpenFileName',return_value=('','')),patch.object(QFileDialog,'getOpenFileNames',return_value=([],'')),patch.object(QFileDialog,'getSaveFileName',return_value=('','')),patch.object(QFileDialog,'getExistingDirectory',return_value=''),patch.object(QDesktopServices,'openUrl',return_value=True)]
for p in patches:p.start()
for name,a in menus:
    current={'action':name}
    if name.endswith('Quit'):
        current['status']='close tested at end';report.append(current);continue
    if not isValid(a):current['status']='replaced';report.append(current);continue
    if not a.isEnabled():current['status']='disabled for initial project';report.append(current);continue
    try:
        w.set_project(example());w.saved_hash=digest(w.project);w.show()
        a.trigger();QTest.qWait(45);dismiss()
        if w.run_manager.busy:
            w.cancel_job();deadline=time.monotonic()+5
            while w.run_manager.busy and time.monotonic()<deadline:QTest.qWait(20)
        current['status']='invoked'
    except Exception as exc:current['exceptions']=[repr(exc)]
    report.append(current)
    (out/'menus.json').write_text(json.dumps(report,indent=2));print(name, current.get('guarded',current.get('messages','ok')),flush=True)
current={'tabs':[]};w.set_project(example())
for tab in w.findChildren(QTabWidget):
    if not isValid(tab):continue
    for i in range(tab.count()):
        tab.setCurrentIndex(i);QTest.qWait(10);current['tabs'].append(tab.tabText(i))
(out/'tabs.json').write_text(json.dumps(current,indent=2))
w.saved_hash=digest(w.project);w.close();app.processEvents()
for p in patches:p.stop()
unexpected=[r for r in report if r.get('exceptions') or any(e['type'] not in ('ValueError','FileNotFoundError') for e in r.get('guarded',[]))]
summary={'status':'failed' if unexpected or current.get('exceptions') else 'passed','menu_entries':len(report),'invoked':sum(r.get('status')=='invoked' for r in report),'tabs_visited':len(current['tabs']),'prerequisite_guards':sum(bool(r.get('guarded')) for r in report),'limits':['File selections and confirmations cancelled','Disabled commands require selection-specific probes','Dialog buttons inventoried; action-specific probes exercise submissions']}
(out/'checks.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
assert not unexpected and not current.get('exceptions'),unexpected or current
