"""Source desktop generation, gate-finger/width/copy editing, regeneration and save/reopen."""
import argparse
import json
from pathlib import Path
import sys
import traceback


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True); a = ap.parse_args()
    out = a.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root))
    from PySide6.QtCore import QSettings, QStandardPaths
    from PySide6.QtWidgets import QApplication, QDialogButtonBox
    from icstudio.gui import Studio
    from icstudio.model import clone, digest, load_project
    from icstudio.process_adapters import ADAPTERS
    from scripts.qualify_standard_mos import load_technology
    from scripts.qualify_mos_finger_layouts import TARGETS, fixture
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(out/'profile/settings'))
    QStandardPaths.writableLocation = staticmethod(lambda kind: str(out/'profile'/str(kind.value)))
    app = QApplication([]); studio = Studio(recover=False); studio.maybe_save = lambda: True
    studio.live_check.setChecked(False); errors = []; studio.error = lambda text: errors.append(str(text)); studio.show(); rows = []

    def accept(dialog):
        if dialog is not None:
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click(); app.processEvents()
        review = studio._review_dialog; button = review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply)
        assert button.isEnabled(), errors
        button.click(); app.processEvents(); assert not review.isVisible(), errors

    try:
        for target in TARGETS:
            tech, identity = load_technology(target)
            for polarity in ('n', 'p'):
                p = fixture(tech, target, polarity, (3, 1, 3, 3)); cell = p['cells'][0]; did = cell['devices'][0]['id']
                for key in ('shapes', 'layout_pins', 'layout_ports', 'pdk_layouts'): cell[key] = []
                studio.set_project(p); studio.select([did]); studio.refresh()
                accept(studio.mos_layout_dialog())
                assert studio.cell['pdk_layouts'][0]['parallel_units']['count'] == 3
                assert studio.cell['pdk_layouts'][0]['fingers']['count'] == 3
                pins = {pin['pin']: pin['id'] for pin in studio.cell['layout_pins']}
                studio.undo(); assert not studio.cell.get('pdk_layouts'); studio.redo()
                studio.select([did]); studio.refresh()
                studio.form_fields['param:w'].setText('8u')
                studio.form_fields['modelparam:'+('ng' if target=='ihp-sg13g2' else 'nf')].setText('8')
                studio.form_fields['modelparam:m'].setText('16'); studio.apply_inspector(True)
                assert not errors, errors
                assert ADAPTERS[target].implementation().audit(studio.project, studio.cid)
                studio.select([did]); studio.refresh(); accept(studio.mos_layout_dialog())
                assert studio.cell['pdk_layouts'][0]['parallel_units']['count'] == 16
                assert studio.cell['pdk_layouts'][0]['fingers']['count'] == 8
                assert studio.cell['pdk_layouts'][0]['fingers']['width_nm'] == 1000
                assert {pin['pin']:pin['id'] for pin in studio.cell['layout_pins']} == pins
                assert not ADAPTERS[target].implementation().audit(studio.project, studio.cid)
                path = out/(target+'-'+polarity+'.icproj'); studio.path = path; assert studio.save()
                reopened = load_project(path); assert reopened['cells'] == studio.project['cells']
                rows.append(dict(target=target, polarity=polarity, status='PASS', package=identity, saved=str(path)))
        assert not errors, errors
        studio.mode_combo.setCurrentIndex(1); studio.layout.fit(); app.processEvents()
        assert studio.grab().save(str(out/'mos-fingers.png'))
        result = dict(status='PASS', cases=rows, platform=app.platformName(), scope=__doc__+' Source desktop only; installed release acceptance remains separate.')
    except Exception:
        result = dict(status='FAIL', cases=rows, errors=errors, traceback=traceback.format_exc())
    finally:
        studio.analysis_dirty = False; studio.saved_hash = digest(studio.project); studio.close(); app.processEvents()
    (out/'record.json').write_bytes((json.dumps(result, indent=2)+'\n').encode()); print(json.dumps(result, indent=2))
    return int(result['status'] != 'PASS')


if __name__ == '__main__': raise SystemExit(main())
