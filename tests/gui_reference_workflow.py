"""Saved op-amp diagnostics through the desktop, undo and project storage."""
import argparse
import json
import sys
import traceback
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtWidgets import QApplication,QDialogButtonBox,QTabWidget
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import clone,design_digest,load_project,save_project
    from icstudio.two_stage_opamp import reference
    package_root=root/'icstudio/assets/pdks/sky130A'
    package=json.loads((package_root/'package.json').read_text())
    tech=clone(package['technology']);tech.update(package_root=str(package_root),package_lock={key:package[key] for key in ('id','revision','files')})
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'profile/settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);app.setStyle('Fusion');studio=Studio(recover=False)
    studio.maybe_save=lambda:True;studio.live_check.setChecked(False);errors=[];studio.error=lambda msg:errors.append(str(msg))
    studio.show();checks=[]
    try:
        project,cid,key=reference(tech);studio.set_project(project)
        actions={a.text().replace('&','') for a in studio.findChildren(__import__('PySide6.QtGui',fromlist=['QAction']).QAction)}
        assert 'New SKY130 two-stage op-amp' in actions
        assert 'Generate two-stage op-amp layout…' in actions
        before=clone(studio.project)
        for name in ('opamp_op','opamp_ac','opamp_noise','opamp_startup'):
            seed=next(t for t in studio.project['testbenches'] if t['name']==name)
            studio._selected_testbench=seed['id'];dialog=studio.edit_testbench()
            tabs=dialog.findChild(QTabWidget);tabs.setCurrentIndex(2)
            original=clone(seed['analysis']['diagnostic'])
            assert dialog.diagnostics.kind.currentData()==original['kind']
            if original['kind']=='loop':
                dialog.diagnostics.fields['denominator'].setText('missing_net')
                digest=design_digest(studio.project);dialog.buttons.button(QDialogButtonBox.Save).click();app.processEvents()
                assert dialog.isVisible() and dialog.error.text() and design_digest(studio.project)==digest
                dialog.diagnostics.fields['denominator'].setText(original['denominator'])
            dialog.buttons.button(QDialogButtonBox.Save).click();app.processEvents()
            assert not dialog.error.text(),dialog.error.text()
            saved=studio.selected_testbench()
            assert saved['analysis']['diagnostic']['kind']==original['kind']
            assert saved['measurements']==seed['measurements']
            assert saved['analysis']['type']==seed['analysis']['type']
            # One save is one history transaction, with complete diagnostic data.
            studio.undo();assert studio.selected_testbench()['analysis']==seed['analysis']
            studio.redo()
            dialog=studio.edit_testbench();dialog.findChild(QTabWidget).setCurrentIndex(2)
            app.processEvents();dialog.grab().save(str(out/(name+'-diagnostics.png')));dialog.reject()
        checks.append('Bias, AC loop, noise and startup diagnostics survive desktop edit, validation, undo and redo with unchanged measurement limits')
        path=out/'opamp-saved-diagnostics.icproj';save_project(studio.project,path)
        loaded=load_project(path)
        assert loaded['testbenches']==studio.project['testbenches']
        assert loaded['test_plans']==before['test_plans']
        checks.append('All four op-amp fixtures and PVT plan survive save/reopen')
        # Selecting a new noise measurement enables the matching diagnostic.
        noise=next(t for t in studio.project['testbenches'] if t['name']=='opamp_noise')
        studio._selected_testbench=noise['id'];dialog=studio.edit_testbench()
        assert dialog.analysis_type.currentText()=='noise'
        assert dialog.fields['output'].text()=='out' and dialog.fields['noise_source'].text()=='VIN'
        assert dialog.measurements.cellWidget(0,1).currentText()=='input_noise'
        dialog.reject()
        checks.append('Noise editor displays its input source, output spectrum and integrated measurement types')
        assert not errors,errors
        report={'status':'passed','platform':app.platformName(),'checks':checks}
    except Exception:
        report={'status':'failed','checks':checks,'traceback':traceback.format_exc()}
    finally:
        studio.close();app.processEvents()
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
