"""Actual Qt placement/review/undo/resize/reopen for all five straight resistors."""
import argparse
import json
from pathlib import Path
import sys
import traceback


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', required=True, type=Path)
    out = ap.parse_args().out.resolve(); out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root))
    from PySide6.QtCore import QSettings, QStandardPaths
    from PySide6.QtWidgets import QApplication, QDialogButtonBox
    from icstudio.gui import Studio
    from icstudio.catalog import create_device
    from icstudio.model import clone, example, save_project, load_project, file_digest
    from icstudio.physical import connectivity
    from icstudio.sky130_metal_resistors import LAYERS, layers
    from icstudio.testbenches import native_subcircuit
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(out/'profile/settings'))
    QStandardPaths.writableLocation = staticmethod(lambda kind: str(out/'profile'/str(kind.value)))
    app = QApplication([]); studio = Studio(recover=False); studio.maybe_save = lambda: True
    studio.live_check.setChecked(False); errors = []; studio.error = lambda text: errors.append(str(text)); studio.show()
    report = dict(status='RUNNING', scope='Source Qt editor workflow only; not installed acceptance.', cases=[])
    def accept_form(dialog):
        if dialog is not None:
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click(); app.processEvents()
    def apply_review():
        review = studio._review_dialog; button = review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply)
        assert button.isEnabled(), errors
        button.click(); app.processEvents(); assert not review.isVisible(), errors
    try:
        package_path = root/'icstudio/assets/pdks/sky130A/package.json'
        package = json.loads(package_path.read_bytes())
        for key in LAYERS:
            p = example('empty'); p['pdk'] = clone(package['technology'])
            p['pdk'].update(package_root=str(package_path.parent), package_lock={k: package[k] for k in ('id','revision','files')})
            symbol = 'li' if key == 'l1' else key
            d = create_device(p['pdk'], 'sky130_fd_pr/res_generic_'+symbol+'.sym', 'R1')
            d['model_params'].update(w=2, l=5, mult=1); d['nets'] = {'m':'A','p':'B'}; p['cells'][0]['devices'] = [d]
            studio.set_project(p); studio.selection = [d['id']]; studio.refresh(); before = clone(studio.project)
            accept_form(studio.mos_layout_dialog()); assert studio.project == before
            # Changing a layer lock after preview must still block application.
            layer = layers(studio.project['pdk'], key)['conductor']; studio.layout.locked_layers.add(layer)
            review = studio._review_dialog; review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click(); app.processEvents()
            assert review.isVisible() and studio.project == before
            studio.layout.locked_layers.discard(layer); apply_review()
            assert not connectivity(studio.project, studio.cid)['issues']
            studio.undo(); assert not studio.cell.get('pdk_layouts'); studio.redo()
            pins = {v['pin']:v['id'] for v in studio.cell['layout_pins']}
            studio.commit(lambda project: project['cells'][0]['devices'][0]['model_params'].update(w=.505,l=2.005), 'Resize resistor')
            studio.selection = [d['id']]; studio.refresh(); accept_form(studio.mos_layout_dialog()); apply_review()
            assert not connectivity(studio.project, studio.cid)['issues']
            assert pins == {v['pin']:v['id'] for v in studio.cell['layout_pins']}
            path = out/(key+'.icproj'); save_project(studio.project, path); reopened = load_project(path)
            assert reopened['cells'] == studio.project['cells']
            circuit = native_subcircuit(reopened, reopened['top'])
            fields = next(line.split() for line in circuit.splitlines() if line.startswith('R_R1 '))
            assert fields[1:4] == ['A', 'B', 'sky130_fd_pr__res_generic_'+key], circuit
            assert dict(value.split('=', 1) for value in fields[4:]) == {'w':'0.505','l':'2.005','m':'1'}, circuit
            (out/(key+'.spice')).write_bytes(circuit.encode())
            report['cases'].append(dict(model=key, status='PASS', project_sha256=file_digest(path),
                checks=['placement-preview','late-layer-lock','apply','undo-redo','resize-regenerate','persistent-pins','save-reopen','model-export']))
        assert not errors, errors
        report.update(status='PASS', platform=app.platformName(), late_lock_rejections=5,
                      simulation_manifest_sha256=file_digest(package_path))
    except Exception:
        report.update(status='FAIL', errors=errors, traceback=traceback.format_exc())
    finally:
        studio.close(); app.processEvents()
    (out/'record.json').write_bytes((json.dumps(report, indent=2)+'\n').encode())
    print(json.dumps(report, indent=2)); return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
