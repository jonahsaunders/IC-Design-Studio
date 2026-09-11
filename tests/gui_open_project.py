"""Exercise the real imported project through attachment, editing and persistence."""
import argparse
import json
import sys
import traceback
import time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    ap=argparse.ArgumentParser()
    for name in ('schematic','layout','out'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--bench', type=Path)
    ap.add_argument('--ngspice')
    a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtWidgets import QApplication,QMessageBox
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import load_project,save_project,clone
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);app.setStyle('Fusion');w=Studio(recover=False);errors=[];checks=[]
    w.error=lambda message:errors.append(str(message));w.maybe_save=lambda:True
    result=dict(status='failed',checks=checks)
    try:
        w.live_check.setChecked(False);w.resize(1680,1050);w.show();QTest.qWait(100)
        schematic=load_project(a.schematic);w.set_project(schematic);before=clone(w.project['cells'])
        old_layers={l['name'] for l in w.project['pdk']['layers']}
        hidden=sorted(old_layers)[0];w.layout.visible_layers.discard(hidden);w.save_layer_profile()
        with patch('icstudio.interoperability_ui.QFileDialog.getOpenFileName',return_value=(str(a.layout),'')),patch('PySide6.QtWidgets.QMessageBox.question',return_value=QMessageBox.Yes):
            w.attach_layout_dialog()
        linked=clone(w.project['cells'])
        assert w.project['layout_attachment']['cells']
        for cell in before:
            actual=next(c for c in linked if c['id']==cell['id'])['devices']
            # The UI canonicalizes empty optional label dictionaries on commit.
            def canonical(devices):
                return [{k:v for k,v in d.items() if k!='net_labels' or v} for d in devices]
            assert canonical(actual)==canonical(cell['devices']),cell['name']
        w.undo();assert w.project['cells']==before;w.redo();assert w.project['cells']==linked
        checks.append('Reviewed attachment preserves schematic identities and applies as one undoable transaction')
        key=w.cell['devices'][0]['id'];w.mode_combo.setCurrentIndex(0)
        w.move([key],20,0,'schematic');assert w.project['cells']!=linked
        w.undo();assert w.project['cells']==linked
        checks.append('An imported hierarchical schematic instance moves and undoes exactly')
        save_project(w.project,out/'saved.icproj');w.set_project(load_project(out/'saved.icproj'))
        assert w.project['cells']==linked
        w.mode_combo.setCurrentIndex(2);w.refresh(True);QTest.qWait(300)
        # The top-level overview is deliberately bounded at 53k expanded shapes.
        # Inspect a matched child to show actual geometry at useful detail.
        child=next(c['id'] for c in w.project['cells'] if c['name']=='level_shifter')
        w.cell_combo.setCurrentIndex(w.cell_combo.findData(child));QTest.qWait(300)
        assert w.cid==child and w.layout.cell['shapes']
        new_layers={l['name'] for l in w.project['pdk']['layers']}-old_layers
        assert new_layers and new_layers<=w.layout.visible_layers
        assert hidden not in w.layout.visible_layers
        assert any(s['layer'] in w.layout.visible_layers for s in w.layout.cell['shapes'])
        assert w.grab().save(str(out/'overvoltage-workspace.png'))
        checks.append('Combined native project saves, reopens and renders both views')
        if a.bench:
            w.set_project(load_project(a.bench))
            assert w.cell['name']=='detector_dc_bench' and w.native_dc_startup.isChecked()
            w.native_dc_startup.setChecked(False)
            assert w.flush_analysis() and not w.project['analysis']['dc_startup']
            w.undo(); assert w.project['analysis']['dc_startup'] and w.native_dc_startup.isChecked()
            save_project(w.project,out/'bench-reopened.icproj');w.set_project(load_project(out/'bench-reopened.icproj'))
            assert w.current_analysis_settings()['dc_startup']
            checks.append('DC startup setting survives editing, undo and project reopening')
            if a.ngspice: w.settings.setValue('engine/ngspice', a.ngspice)
            w.quick_run()
            deadline=time.monotonic()+180
            while w.run_manager.busy and time.monotonic()<deadline: QTest.qWait(100)
            assert w.run_manager.rows,errors
            run=w.run_manager.rows[-1]
            assert run['state']=='Complete',(run['state'],run.get('log'),errors)
            wave=run['result']['traces']['ovout']
            assert len(wave)==301 and wave[0]<.2 and wave[-1]>1.6
            assert (run['path']/'dc-startup.nodeset').exists()
            checks.append('F5 analysis action executes the saved detector bench in HSA and displays all 301 DC points')
        assert not errors,errors
        result['status']='passed'
    except Exception:result.update(error=traceback.format_exc(),errors=errors)
    finally:w.close();app.processEvents()
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
