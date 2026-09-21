"""Desktop integration of saved extraction models and layout intent controls."""
import argparse
import json
import sys
import traceback
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtWidgets import QApplication,QDialogButtonBox,QTabWidget
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import clone,design_digest,load_project,save_project
    from test_physical_extraction import resistive_bench
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'profile/settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False)
    w.maybe_save=lambda:True;w.live_check.setChecked(False);errors=[];w.error=lambda text:errors.append(str(text))
    w.show();checks=[]
    try:
        p,cid,t=resistive_bench();w.set_project(p);initial=design_digest(w.project)
        dialog=w.edit_testbench();dialog.findChild(QTabWidget).setCurrentIndex(1)
        assert dialog.extraction.value()==t['physical_extraction']
        dialog.extraction.fields['section_nm'].setText('50')
        dialog.buttons.button(QDialogButtonBox.Save).click();app.processEvents()
        assert dialog.isVisible() and 'section_nm' in dialog.error.text()
        assert design_digest(w.project)==initial
        dialog.extraction.fields['section_nm'].setText('4000')
        dialog.extraction.fields['corner'].setText('slow_rc')
        dialog.buttons.button(QDialogButtonBox.Save).click();app.processEvents()
        saved=w.selected_testbench()['physical_extraction']
        assert saved==dict(mode='calibrated_rc',section_nm=4000,coupling_distance_nm=5000,corner='slow_rc')
        assert design_digest(w.project)!=initial
        w.undo();assert w.selected_testbench()['physical_extraction']==t['physical_extraction']
        w.redo();assert w.selected_testbench()['physical_extraction']==saved
        path=out/'saved-extraction.icproj';save_project(w.project,path)
        assert load_project(path)['testbenches'][0]['physical_extraction']==saved
        dialog=w.edit_testbench();dialog.findChild(QTabWidget).setCurrentIndex(1)
        app.processEvents();dialog.grab().save(str(out/'extraction-settings.png'));dialog.reject()
        checks.append('Extraction settings reject invalid dimensions, change revision identity, undo/redo and save/reopen exactly')

        ws=w.open_analog_workspace();ws.tabs.setCurrentIndex(3);ws.refresh_verification()
        assert 'Calibrated interconnect RC' in ws.verify_extraction.text() and 'slow_rc' in ws.verify_extraction.text()
        ws.edit_verification_bench();dialog=w._testbench_dialog
        dialog.extraction.mode.setCurrentIndex(dialog.extraction.mode.findData('rc'))
        assert dialog.extraction.value()=={'mode':'rc'}
        dialog.buttons.button(QDialogButtonBox.Save).click();app.processEvents();ws.refresh_verification()
        assert w.selected_testbench()['physical_extraction']=={'mode':'rc'}
        assert 'Process distributed RC' in ws.verify_extraction.text()
        checks.append('Verification workspace opens the selected fixture and displays its saved extraction mode')
        for dark in (False,True):
            w.dark=dark;w.apply_theme();ws.resize(900,720);app.processEvents();QTest.qWait(50)
            ws.grab().save(str(out/('verification-'+('dark' if dark else 'light')+'.png')))
        ws.close()

        w.cid=cid;w.mode_combo.setCurrentIndex(1);w.refresh(True)
        from icstudio.layout_eco_ui import show
        eco=show(w);assert not eco.strict_constraints.isChecked();eco.strict_constraints.setChecked(True)
        assert 'existing findings' in eco.strict_constraints.toolTip();eco.reject()
        captured=[];w.enqueue_layout=lambda cell,settings,title:captured.append((cell,settings,title))
        route=w.matched_route_dialog();assert route.fields['match_layers'].currentText()=='Match each layer'
        route.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click();app.processEvents()
        assert captured[-1][1]['arguments']['match_layers'] is True
        route=w.matched_route_dialog();route.fields['match_layers'].setCurrentText('Match total length')
        route.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click();app.processEvents()
        assert captured[-1][1]['arguments']['match_layers'] is False
        checks.append('Native layout review exposes strict constraint enforcement and explicit per-layer route matching')
        assert not errors,errors
        report=dict(status='passed',platform=app.platformName(),checks=checks)
    except Exception:
        report=dict(status='failed',checks=checks,traceback=traceback.format_exc())
    finally:
        w.run_manager.cancel([r for r in w.run_manager.rows if r['state'] in ('Queued','Running')])
        w.close();app.processEvents()
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
