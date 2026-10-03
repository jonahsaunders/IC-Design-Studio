"""Workflow-specific setup and safe deferred lessons, without EDA engines.

Real package/engine execution is qualified separately. This probe exercises the
desktop controls with a simulated Included install and real native path files.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')


def main():
    from PySide6.QtCore import QSettings
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialogButtonBox
    from icstudio import digital_runtime, digital_setup_ui, digital_flow, mixed_signal
    from icstudio.digital_platform import read_manifest
    from icstudio.gui import Studio
    from icstudio.model import digest
    from icstudio.mixed_signal_ui import show as show_experiment
    from icstudio.student_hub_ui import show as show_hub
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
    checks=[];errors=[]
    with tempfile.TemporaryDirectory() as td, patch.dict(os.environ,{
            'XDG_DATA_HOME':td+'/data','XDG_CONFIG_HOME':td+'/config',
            'ICSTUDIO_DIGITAL_PAYLOAD':td+'/payload','ICSTUDIO_DIGITAL_STATE':td+'/state'}):
        settings=QSettings(td+'/settings.ini',QSettings.IniFormat);settings.setFallbacksEnabled(False)
        settings.setValue('onboarding/show',False)
        with patch('icstudio.gui.QSettings',return_value=settings), \
             patch('icstudio.gui.QStandardPaths.writableLocation',return_value=td+'/data'):
            studio=Studio(recover=False)
        studio.error=errors.append;studio.maybe_save=lambda:True;studio.resize(1280,900);studio.show()
        hub=show_hub(studio);guide=hub.guide
        # Existing native path settings must not silently change Included mode.
        settings.setValue('student/tools/iverilog','/stale/iverilog')
        hub.select_lesson('d-counter');hub.start_selected()
        platform_root=Path(td)/'platform';platform_root.mkdir()
        (platform_root/'cells.lib').write_text('library(test) {}')
        (platform_root/'platform.json').write_text(json.dumps({'version':1,'name':'test','revision':'fixture',
            'corner':'tt','corners':{'tt':['cells.lib']},'files':['cells.lib']}))
        platform=read_manifest(platform_root/'platform.json')
        info={'state':'setup','message':'Included tools need setup.'};runtime={'kind':'fixture'};queued=[]
        with patch.object(digital_runtime,'status',side_effect=lambda:dict(info)), \
             patch.object(digital_runtime,'installed',side_effect=lambda:runtime if info['state']=='ready' else None), \
             patch.object(digital_runtime,'platform',return_value=platform), \
             patch.object(digital_setup_ui.DigitalSetupDialog,'setup') as setup, \
             patch.object(digital_flow,'environment',return_value={}), \
             patch.object(studio.run_manager,'enqueue',side_effect=lambda job,*args:queued.append(job)):
            guide.run();dialog=studio._digital_setup_dialog
            assert dialog.isVisible() and dialog.pending and not queued
            setup.assert_called_once()
            info['state']='ready';dialog.process=Mock()
            with patch.object(dialog,'read'):dialog.process_finished(0)
            QTest.qWait(30)
            assert len(queued)==1 and queued[0]['settings']['runtime']==runtime
            assert queued[0]['settings']['tools']['iverilog']=='opt/icstudio/bin/iverilog'
            checks.append('Student digital lesson honors Included selection and resumes once after setup')
            info['state']='setup';guide.run();assert dialog.pending
            studio.commit(lambda p:p.update(name=p['name']+' edited'),'Change lesson during setup')
            info['state']='ready';dialog.process=Mock()
            with patch.object(dialog,'read'):dialog.process_finished(0)
            QTest.qWait(30)
            assert len(queued)==1 and 'changed during setup' in guide.feedback.text()
            info['state']='setup';guide.run();dialog.cancel_pending()
            assert not dialog.pending and 'cancelled' in guide.feedback.text()
            checks.append('Changed or cancelled lesson requests cannot run automatically')
        dialog.close()
        settings.setValue('student/tools/iverilog','');settings.setValue('student/tools/vvp','')
        settings.setValue('student/tools/ngspice',sys.executable)
        with patch.object(mixed_signal.shutil,'which',return_value=None):
            hub.select_lesson('m-bridge');hub.start_selected();guide.run()
            native=hub._engine_setup_dialog
            assert native.isVisible() and 'iverilog, vvp' in native.native_status.text()
            assert 'Student Hub → Engine setup' in guide.feedback.text()
            assert native.focusWidget() is native.paths['iverilog']
            checks.append('Missing native engines open Student setup with all prerequisites and correct focus')
            experiment=show_experiment(studio);experiment.call(experiment.run)
            assert experiment.tabs.tabText(experiment.tabs.currentIndex())=='Local engines'
            assert 'iverilog, vvp' in experiment.engine_status.text()
            assert experiment.focusWidget() is experiment.paths['iverilog']
            checks.append('SAR failure opens Local engines with workflow-specific installation guidance')
            for edit in native.paths.values():edit.setText('"'+sys.executable+'"')
            native.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
            assert settings.value('student/tools/iverilog')==sys.executable
            for edit in experiment.paths.values():edit.setText('"'+sys.executable+'"')
            assert experiment.apply() and experiment.check_engines()
            assert settings.value('mixed_signal/iverilog')==sys.executable
            assert 'executables found' in experiment.engine_status.text().lower()
            checks.append('Quoted native paths save unquoted and prerequisite checks accept the same files')
        experiment.close();native.close();studio.saved_hash=digest(studio.project);studio.close();app.processEvents()
        assert not errors,errors
    out=ROOT/'build/engine-setup-ui';out.mkdir(parents=True,exist_ok=True)
    report={'status':'PASS','scope':'Desktop setup controls; simulated Included installation; no EDA engines executed',
            'qt_platform':app.platformName(),'checks':checks}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
