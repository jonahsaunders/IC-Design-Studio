"""Source desktop action, real form/review, layer locks, undo/redo and reopen."""
import argparse
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--out', type=Path, required=True)
    output = parser.parse_args().out.resolve(); output.mkdir(parents=True, exist_ok=False)
    for name in ('APPDATA', 'LOCALAPPDATA', 'XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
        os.environ[name] = str(output/'profile'/name)
    from PySide6.QtCore import QSettings, QStandardPaths
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QApplication, QDialogButtonBox
    from icstudio.gui import Studio
    from icstudio.interchange import export_layout
    from icstudio.model import clone, digest, example, file_digest, load_project, save_project
    from scripts.qualify_ihp_bondpad import check_stream, technology
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(output/'settings'))
    QStandardPaths.writableLocation = staticmethod(lambda kind: str(output/'profile'/str(kind.value)))
    app = QApplication([]); studio = Studio(recover=False); studio.maybe_save = lambda: True
    studio.live_check.setChecked(False); errors = []; studio.error = lambda text: errors.append(str(text))
    report = dict(schema=1, status='RUNNING', mode='source-qt', installed_acceptance=False, qualified=False)
    try:
        p = example('empty'); p['pdk'] = technology(); p['cells'][0]['ports'] = ['PAD']
        studio.set_project(p); studio.show(); studio.refresh(True); app.processEvents()
        assert not studio.unmapped_commands, studio.unmapped_commands
        action = next(a for a in studio.findChildren(QAction) if a.text() == 'Generate IHP bondpad…')
        before = clone(studio.project); action.trigger(); app.processEvents(); form = studio._workflow_dialog
        for key, value in dict(diameter='80', quota='0.5', x='0.125', y='-0.325').items():
            form.fields[key].setText(value)
        form.fields['rotation'].setCurrentText('90')
        form.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click(); app.processEvents()
        assert studio.project == before, 'A preview changed the project.'
        review = studio._review_dialog; button = review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply)
        assert button.isEnabled(), errors
        studio.layout.locked_layers.add('Passiv.drawing'); button.click(); app.processEvents()
        assert review.isVisible() and studio.project == before, 'A late layer lock did not preserve the project.'
        studio.layout.locked_layers.discard('Passiv.drawing'); button.click(); app.processEvents()
        assert not review.isVisible(), errors
        applied = clone(studio.project); assert len(studio.cell['ihp_bondpads']) == 1
        studio.undo(); app.processEvents(); assert studio.project['cells'] == before['cells']
        studio.redo(); app.processEvents(); assert studio.project['cells'] == applied['cells']
        save_project(studio.project, output/'pad.icproj'); reopened = load_project(output/'pad.icproj')
        assert reopened['cells'] == studio.project['cells']
        parameters = dict(diameter_nm=80000, hwquota=.5, x_nm=125, y_nm=-325, rotation=90)
        for extension in ('gds', 'oas'):
            path = output/('pad.'+extension); export_layout(reopened, path); check_stream(path, parameters)
        assert not errors, errors
        studio.grab().save(str(output/'desktop.png'))
        report.update(status='PASS', platform=app.platformName(), late_layer_lock_rejected=True,
                      electrical_binding_unavailable=bool(studio.project['pdk']['simulation']['catalog']['sg13g2_pr/bondpad.sym']['unavailable']),
                      undo_redo=True, save_reopen=True, stream_formats=['gds', 'oas'])
    except Exception:
        report.update(status='FAIL', errors=errors, error=traceback.format_exc())
    finally:
        studio.saved_hash = digest(studio.project); studio.analysis_dirty = False; studio.close(); app.processEvents()
    (output/'report.json').write_bytes((json.dumps(report, indent=2)+'\n').encode())
    files = {p.relative_to(output).as_posix(): file_digest(p) for p in sorted(output.rglob('*')) if p.is_file()}
    (output/'files.json').write_bytes((json.dumps(files, indent=2)+'\n').encode())
    print(json.dumps(report, indent=2)); return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
