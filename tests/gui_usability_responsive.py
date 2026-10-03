"""Screen-fit and readable workflow acceptance at 100, 150 and 200 percent DPI."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch


def probe(out,scale):
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    os.environ['QT_SCALE_FACTOR']=str(scale)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QRect,QSettings,Qt
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from icstudio.gui import Studio
    from icstudio.model import example,device,digest
    from icstudio.window_geometry import reachable_geometry,keep_visible
    app=QApplication([]);app.setStyle('Fusion')
    if sys.platform=='win32' and app.platformName()=='offscreen':
        fonts=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
        for name in ('segoeui.ttf','segoeuib.ttf','arial.ttf'):
            assert QFontDatabase.addApplicationFont(str(fonts/name))>=0,'Missing GUI measurement font: '+name
    out.mkdir(parents=True,exist_ok=True);percent=round(scale*100)
    available=QRect(0,0,round(1920/scale),round(1040/scale));real_screen=app.primaryScreen()
    class Screen:
        availableGeometryChanged=real_screen.availableGeometryChanged
        def availableGeometry(self):return available
    errors=[];guide=None;w=None
    def wait(predicate,label):
        until=time.monotonic()+10
        while time.monotonic()<until:
            app.processEvents()
            if predicate():return
            QTest.qWait(20)
        raise AssertionError(label+' / '+str(errors))
    with tempfile.TemporaryDirectory() as folder:
        settings=QSettings(str(Path(folder)/'settings.ini'),QSettings.IniFormat)
        settings.setFallbacksEnabled(False);settings.setValue('onboarding/show',False)
        # Restoring a large window must work even when its title is already on screen.
        assert available.contains(reachable_geometry(QRect(10,10,2200,1200),[available]))
        with patch('icstudio.gui.QSettings',return_value=settings), \
                patch('icstudio.gui.QStandardPaths.writableLocation',return_value=folder), \
                patch('icstudio.window_geometry.QGuiApplication.screens',return_value=[Screen()]):
            try:
                w=Studio(recover=False);w.maybe_save=lambda:True;w.error=lambda message:errors.append(str(message))
                w.show();QTest.qWait(150)
                assert available.contains(w.frameGeometry()),(available,w.frameGeometry(),w.minimumSizeHint())
                startup=[w.frameGeometry().x(),w.frameGeometry().y(),w.frameGeometry().width(),w.frameGeometry().height()]
                w.grab().save(str(out/f'workspace-{percent}.png'))
                # Restore a larger-monitor workspace on this logical display.
                w.setGeometry(10,10,2200,1200);keep_visible(w);QTest.qWait(60)
                assert available.contains(w.frameGeometry()),(available,w.frameGeometry())
                # A narrow real display (1920x1080 physical at slightly over 200%)
                # also needs the controls to stay inside the available frame.
                old_available=QRect(available);available=QRect(0,0,911,512)
                real_screen.availableGeometryChanged.emit(available);QTest.qWait(80)
                assert available.contains(w.frameGeometry()),(available,w.frameGeometry())
                available=old_available;keep_visible(w)
                p=example('empty');p['cells'][0]['devices']=[device('R','R1',100,100,value='1k')]
                w.set_project(p);guide=w.design_workflow()
                wait(lambda:guide.analysis is not None,'Automatic workflow checks did not finish')
                assert not guide.analysis.get('error'),guide.analysis
                QTest.qWait(100)
                assert available.contains(w.frameGeometry()),(available,w.frameGeometry())
                area=w.workflow_dock.widget()
                assert area.horizontalScrollBar().maximum()==0,(area.viewport().size(),guide.minimumSizeHint())
                w.grab().save(str(out/f'workflow-docked-{percent}.png'))
                # Match the widths that exposed the packaged Windows clipping.
                # Isolate the panel from the workspace's dock scroll area for the image.
                w.workflow_dock.widget().takeWidget();w.workflow_dock.hide();guide.setParent(None)
                guide.setStyleSheet(w.styleSheet());guide.resize({100:840,150:680,200:404}[percent],{100:455,150:460,200:477}[percent])
                guide.show();guide.tabs.setCurrentIndex(1);QTest.qWait(100)
                # A width change first updates wrapped minimum heights. Apply
                # the requested panel height after that layout has settled.
                guide.resize({100:840,150:680,200:404}[percent],{100:455,150:460,200:477}[percent]);QTest.qWait(50)
                assert guide.width()=={100:840,150:680,200:404}[percent],guide.size()
                for text in (guide.note,guide.summary):
                    assert text.height()>=text.heightForWidth(text.width()),(text.text(),text.geometry(),text.heightForWidth(text.width()))
                    assert guide.rect().contains(text.geometry()),(guide.rect(),text.geometry())
                for index in range(guide.tabs.count()):
                    if guide.section_picker.isVisible():
                        guide.section_picker.setFocus();guide.section_picker.setCurrentIndex(0)
                        for _ in range(index):QTest.keyClick(guide.section_picker,Qt.Key_Down)
                        assert guide.section_picker.currentText()==guide.tabs.tabText(index)
                        assert guide.section_picker.fontMetrics().horizontalAdvance(guide.section_picker.currentText())+30<=guide.section_picker.width()
                    else:
                        bar=guide.tabs.tabBar();QTest.mouseClick(bar,Qt.LeftButton,pos=bar.tabRect(index).center())
                        assert bar.rect().contains(bar.tabRect(index)),(bar.rect(),bar.tabRect(index))
                    assert guide.tabs.currentIndex()==index
                guide.tabs.setCurrentIndex(1);QTest.qWait(50)
                assert guide.tabs.geometry().bottom()<guide.action_host.geometry().top(),(guide.tabs.geometry(),guide.action_host.geometry())
                for button in guide.finding_actions:
                    assert guide.action_host.rect().contains(button.geometry()),(guide.action_host.rect(),button.geometry())
                    assert guide.rect().contains(guide.action_host.geometry())
                    assert button.width()>=button.sizeHint().width(),(button.text(),button.size(),button.sizeHint())
                guide.grab().save(str(out/f'workflow-{percent}.png'))
                assert not errors,errors
                report=dict(status='PASS',scale=scale,qt_platform=app.platformName(),logical_screen=[available.width(),available.height()],startup_frame=startup,
                            workflow_size=[guide.width(),guide.height()],compact_section_picker=guide.section_picker.isVisible(),
                            checks=['Startup and restored workspace fit available logical screen including native frame',
                                    'Available-display change fits a 911x512 logical screen',
                                    'Docked workflow fits the center column without horizontal scrolling',
                                    'Wrapped note and finding summary remain completely visible',
                                    'Every workflow section is reachable by the visible control without eliding its name',
                                    'Finding actions preserve full labels inside the panel'])
                (out/f'report-{percent}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                print(f'{percent}% responsive usability: PASS')
            finally:
                if guide is not None:guide.stop();guide.close()
                if w is not None:w.saved_hash=digest(w.project);w.close()
                app.processEvents()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=Path('build/usability-responsive-evidence'))
    parser.add_argument('--scale',type=float,choices=(1,1.5,2));args=parser.parse_args();out=args.out.resolve()
    if args.scale is not None:return probe(out,args.scale)
    for scale in (1,1.5,2):
        subprocess.run([sys.executable,str(Path(__file__).resolve()),'--out',str(out),'--scale',str(scale)],check=True)
    (out/'report.json').write_text(json.dumps(dict(status='PASS',scales=[json.loads((out/f'report-{p}.json').read_text(encoding='utf-8')) for p in (100,150,200)]),indent=2),encoding='utf-8')


if __name__=='__main__':main()
