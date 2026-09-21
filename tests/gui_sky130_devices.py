"""Real Qt process-device generation, locked layers, review, undo and reopen."""
import argparse,json,sys,traceback
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);out=ap.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtWidgets import QApplication,QDialogButtonBox
    from icstudio.gui import Studio
    from icstudio.model import example,clone,design_digest,save_project,load_project
    from icstudio.catalog import create_device
    from icstudio.sky130_devices import layers
    from icstudio.physical import connectivity
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'profile/settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);app.setStyle('Fusion');studio=Studio(recover=False);studio.maybe_save=lambda:True;studio.live_check.setChecked(False)
    errors=[];studio.error=lambda text:errors.append(str(text));studio.show();checks=[]
    def accept_form(dialog):dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click();app.processEvents()
    def apply_preview():
        dialog=studio._review_dialog;button=dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply)
        assert button.isEnabled(),[w.text() for w in dialog.findChildren(__import__('PySide6.QtWidgets',fromlist=['QLabel']).QLabel)]
        button.click();app.processEvents();assert not dialog.isVisible()
    try:
        m=json.loads((root/'icstudio/assets/pdks/sky130A/package.json').read_text());p=example('empty');p['pdk']=m['technology']
        p['pdk'].update(package_root=str(root/'icstudio/assets/pdks/sky130A'),package_lock={k:m[k] for k in ('id','revision','files')})
        c=p['cells'][0];d=create_device(p['pdk'],'sky130_fd_pr/cap_mim_m3_1.sym','C1');d['nets']={'c0':'P','c1':'N'};d['model_params'].update(w=2,l=2);c['devices']=[d]
        studio.set_project(p);studio.selection=[d['id']];studio.refresh();before=design_digest(studio.project)
        form=studio.mos_layout_dialog();form.fields['x'].setText('30');accept_form(form)
        assert design_digest(studio.project)==before
        apply_preview();assert len(studio.cell['layout_pins'])==2;assert not connectivity(studio.project,studio.cid)['issues']
        studio.undo();assert not studio.cell.get('pdk_layouts');studio.redo()
        checks.append('Selected catalog MiM uses the native generate/review/apply workflow and one undo restores its unplaced schematic')
        before=clone(studio.project);form=studio.process_dummy_dialog();form.fields['net'].setCurrentText('N');form.fields['x'].setText('5');form.fields['y'].setText('5');form.fields['w'].setText('2')
        accept_form(form);assert studio.project==before
        m1=layers(studio.project['pdk'])['m1'];studio.layout.locked_layers.add(m1)
        preview=studio._review_dialog;preview.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click();app.processEvents()
        assert preview.isVisible() and studio.project==before
        studio.layout.locked_layers.discard(m1);apply_preview()
        dummy=next(v for v in studio.cell['devices'] if v.get('physical_dummy'));assert set(dummy['nets'].values())=={'N'}
        assert len([v for v in studio.cell['layout_pins'] if v['device_id']==dummy['id']])==4
        studio.undo();assert studio.cell['devices']==before['cells'][0]['devices'];studio.redo()
        checks.append('Tied dummy adds schematic MOS, contacted footprint and four persistent straps atomically; undo/redo preserves device identity')
        complete=clone(studio.project);unplaced=create_device(studio.project['pdk'],'sky130_fd_pr/cap_mim_m3_1.sym','CUNPLACED',700,0)
        studio.cell['devices'].append(unplaced);studio.selection=[dummy['id'],unplaced['id']]
        try:studio.process_guard_dialog()
        except ValueError as exc:assert 'every selected device' in str(exc)
        else:raise AssertionError('Guard accepted a selected device without physical geometry')
        studio.set_project(complete)
        studio.selection=[dummy['id']];studio.refresh();m1=layers(studio.project['pdk'])['m1'];before=design_digest(studio.project)
        studio.layout.locked_layers.add(m1);form=studio.process_guard_dialog();accept_form(form)
        preview=studio._review_dialog;assert not preview.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).isEnabled();assert design_digest(studio.project)==before;preview.reject()
        studio.layout.locked_layers.discard(m1);form=studio.process_guard_dialog();accept_form(form);apply_preview()
        assert len(studio.cell['process_guards'])==1;assert len(studio.cell['analog_constraints'])==1
        assert studio.cell['process_guards'][0]['route_ids']
        # The capacitor N terminal remains separately placed; connectivity must
        # expose that unfinished net instead of treating net names as a wire.
        assert any(v['code']=='LVS.OPEN' and v.get('net')=='N' for v in connectivity(studio.project,studio.cid)['issues'])
        studio.undo();assert not studio.cell.get('process_guards');studio.redo()
        checks.append('Locked metal blocks guard review without mutation; unlocked review adds contacted guard, physical tie and selected-device constraint in one history transaction')
        path=out/'sky130-devices.icproj';save_project(studio.project,path);loaded=load_project(path)
        assert loaded['cells']==studio.project['cells'];assert loaded['pdk']['connectivity']['via_blockers']==studio.project['pdk']['connectivity']['via_blockers']
        studio.mode_combo.setCurrentIndex(1);studio.refresh(True);app.processEvents();studio.grab().save(str(out/'sky130-devices.png'))
        checks.append('Save/reopen retains guard, dummy, process footprint and insulated MiM connectivity records')
        assert not errors,errors
        report=dict(status='passed',platform=app.platformName(),checks=checks)
    except Exception:report=dict(status='failed',checks=checks,traceback=traceback.format_exc())
    finally:studio.close();app.processEvents()
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
