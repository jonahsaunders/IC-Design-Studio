"""First-run UI and deferred requests, using simulated installation outcomes.

Real engines are qualified separately through the packaged application.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio import digital, digital_runtime, digital_setup_ui, digital_tools
    from icstudio.model import digest
    app=QApplication.instance() or QApplication([]); app.setStyle('Fusion')
    errors=[]
    def exception(kind,value,traceback):
        errors.append(str(value)); sys.__excepthook__(kind,value,traceback)
    sys.excepthook=exception
    out=ROOT/'build/digital-first-run-ui'; out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as td, patch.dict(os.environ,{
            'XDG_DATA_HOME':td+'/data','XDG_CONFIG_HOME':td+'/config',
            'ICSTUDIO_DIGITAL_PAYLOAD':td+'/payload','ICSTUDIO_DIGITAL_STATE':td+'/state'}):
        settings=QSettings(td+'/settings.ini',QSettings.IniFormat);settings.setFallbacksEnabled(False)
        settings.setValue('onboarding/show',False)
        with patch('icstudio.gui.QSettings',return_value=settings), \
                patch('icstudio.gui.QStandardPaths.writableLocation',return_value=td+'/data'):
            studio=Studio(recover=False)
        studio.settings.setValue('engine/yosys','/old/machine/yosys')
        studio.set_project(digital.counter_project()); studio.resize(1280,850); studio.show()
        window=studio.digital_window(); QTest.qWait(50)
        assert window.workspace.tools()=={}, 'Old executable paths changed the default backend'
        assert window.run() is None
        dialog=studio._digital_setup_dialog
        assert dialog.isVisible() and not dialog.start.isEnabled()
        assert 'source checkout' in dialog.status.text()
        assert dialog.download.isVisible() and dialog.preview.isVisible()
        dialog.grab().save(str(out/'source-download.png'))
        # A dialog first shown at startup can acquire custom configuration later.
        assert dialog.custom is not None
        dialog.mode.setCurrentIndex(1)
        assert digital_tools.selection(studio.settings)['toolchain']=='custom'
        assert window.workspace.tools()['yosys']=='/old/machine/yosys'
        assert dialog.pending is None and dialog.custom_button.isVisible()
        dialog.mode.setCurrentIndex(0)
        assert studio.settings.value('engine/yosys')=='/old/machine/yosys'
        assert window.shell.tools_button.text()=='Included tools'
        calls=[]
        info={'state':'setup','message':'The included tools are ready to set up.'}
        from icstudio.digital_platform import read_manifest
        platform_root=Path(td)/'platform'; platform_root.mkdir()
        (platform_root/'cells.lib').write_text('library(test) {}')
        (platform_root/'platform.json').write_text(json.dumps({'version':1,'name':'test','revision':'fixture',
            'corner':'tt','corners':{'tt':['cells.lib']},'files':['cells.lib']}))
        included_platform=read_manifest(platform_root/'platform.json')
        def finish():
            info.update(state='ready',message='Ready · simulation, synthesis and chip layout verified')
            dialog.process=Mock()
            with patch.object(dialog,'read'):
                dialog.process_finished(0)
            QTest.qWait(20)
        with patch.object(digital_runtime,'status',side_effect=lambda:dict(info)), \
             patch.object(digital_runtime,'installed',side_effect=lambda:{'kind':'fixture'} if info['state']=='ready' else None), \
             patch.object(digital_runtime,'platform',return_value=included_platform), \
             patch.object(dialog,'setup') as setup:
            assert not window.ensure_tools(lambda:calls.append('run'))
            setup.assert_called_once()
            assert dialog.pending is not None and 'continue' in dialog.start.text()
            dialog.grab().save(str(out/'included-setup.png'))
            finish(); assert calls==['run'], calls
            assert window.config['platform']==included_platform, 'Included platform was not applied before continuation'
            QTest.qWait(20); assert calls==['run'], 'Request was executed twice'
            # Stopping an active setup is cancellation, even if success races
            # with the kill. It must clear the queued run and its visible promise.
            info['state']='setup'
            window.ensure_tools(lambda:calls.append('cancelled'))
            worker=Mock(); dialog.process=worker
            ready_calls=[]; dialog.ready.connect(lambda:ready_calls.append('ready'))
            assert not dialog.close()
            worker.kill.assert_called_once()
            assert dialog.pending is None and dialog.pending_cancelled is None
            assert 'cancelled' in window.message.text() and 'will continue' not in window.message.text()
            # The dialog is modeless; another Run can arrive while the worker
            # is still stopping. Its promise must be cleared when cancellation finishes.
            window.ensure_tools(lambda:calls.append('during-stop'))
            assert dialog.pending is not None
            info['state']='ready'
            with patch.object(dialog,'read'): dialog.process_finished(0)
            QTest.qWait(20)
            assert calls==['run'] and ready_calls==[]
            assert dialog.pending is None and dialog.pending_cancelled is None
            assert 'cancelled' in window.message.text() and 'will continue' not in window.message.text()
            assert 'Setup cancelled' in dialog.status.text()
            assert 'enable Windows Linux support' not in dialog.status.text()
            assert 'Setup cancelled' in dialog.log.toPlainText()
            assert 'Setup cancelled' in (Path(td)/'state/last-setup.log').read_text()
            # A new explicit setup clears the cancellation flag. The previously
            # cancelled request remains cleared; a new Run can then continue once.
            info['state']='setup'
            with patch.object(digital_setup_ui,'QProcess'):
                digital_setup_ui.DigitalSetupDialog.setup(dialog)
                assert not dialog.cancel_requested
                window.ensure_tools(lambda:calls.append('new-run'))
                finish()
            assert calls==['run','new-run'] and ready_calls==['ready']
            calls.pop()
            info['state']='setup'
            window.ensure_tools(lambda:calls.append('changed'))
            window.editor.insertPlainText('// changed during setup\n')
            finish(); assert calls==['run']
            assert 'changed during setup' in window.message.text()
            window.apply(); info['state']='setup'
            window.ensure_tools(lambda:calls.append('closed'))
            dialog.close(); finish(); assert calls==['run']
            # Escape uses QDialog.reject rather than closeEvent. It must cancel
            # both idle requests and an active worker before hiding the dialog.
            info['state']='setup'
            window.ensure_tools(lambda:calls.append('escaped-idle'))
            QTest.keyClick(dialog,Qt.Key_Escape)
            assert not dialog.isVisible() and dialog.pending is None
            assert dialog.pending_cancelled is None and not dialog.next_action.text()
            assert 'cancelled' in window.message.text()
            finish(); assert calls==['run']
            info['state']='setup'
            window.ensure_tools(lambda:calls.append('escaped-active'))
            worker=Mock();dialog.process=worker;before_ready=len(ready_calls)
            QTest.keyClick(dialog,Qt.Key_Escape)
            worker.kill.assert_called_once()
            assert dialog.isVisible() and dialog.cancel_requested
            assert dialog.pending is None and dialog.pending_cancelled is None
            finish(); assert calls==['run'] and len(ready_calls)==before_ready
            assert 'Setup cancelled' in dialog.status.text()
            QTest.keyClick(dialog,Qt.Key_Escape);assert not dialog.isVisible()
            # Model a fresh explicit setup before exercising genuine failure.
            with patch.object(digital_setup_ui,'QProcess'):
                digital_setup_ui.DigitalSetupDialog.setup(dialog)
            dialog.process=None
            info['state']='setup'
            window.ensure_tools(lambda:calls.append('failed'))
            dialog.process=Mock()
            with patch.object(dialog,'read'): dialog.process_finished(1)
            assert calls==['run'] and dialog.start.isEnabled() and dialog.details.isChecked()
            assert 'did not complete' in dialog.status.text()
            # Retry retains the original request, but only success can run it.
            finish(); assert calls==['run','failed']
            info['state']='setup'
            window.ensure_tools(lambda:calls.append('other-project'))
            studio.set_project(digital.counter_project())
            finish(); assert calls==['run','failed']
        studio.saved_hash=digest(studio.project); dialog.close(); studio.close()
        assert not errors, errors
    (out/'report.json').write_text(json.dumps({'status':'PASS','scope':'UI with simulated installation outcomes; no engine qualification',
        'checks':['Included default despite old paths','Source download guidance','Explicit reversible custom mode',
                  'Automatic setup from Run','Continue once after success','Changed design blocks continuation',
                  'Close cancels continuation','Active cancellation clears visible queued run',
                  'Run requested while stopping is cleared on cancellation',
                  'Cancellation wins over late success','Explicit setup retry clears cancellation',
                  'Escape cancels idle continuation','Escape stops active setup without a late run',
                  'Failure retains request for retry','Project switch cancels continuation']},indent=2))
    print('Digital first-run GUI passed')


if __name__=='__main__': main()
