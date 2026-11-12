"""Exercise the public IHP material profile through the real desktop editor."""
import argparse
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True, type=Path)
    out = ap.parse_args().out.resolve(); out.mkdir(parents=True, exist_ok=False)
    for key in ('APPDATA', 'LOCALAPPDATA', 'XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
        os.environ[key] = str(out / 'profile' / key)
    from PySide6.QtCore import QSettings, QStandardPaths
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from icstudio.gui import Studio
    from icstudio.em_profile_ui import EMProfileDialog
    from icstudio.model import clone, digest, example, load_project
    from scripts.qualify_standard_mos import load_technology
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(out / 'settings'))
    QStandardPaths.writableLocation = staticmethod(lambda key: str(out / 'profile' / str(key.value)))
    app = QApplication([]); app.setStyle('Fusion'); errors = []
    if sys.platform == 'win32' and os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
        for name in ('segoeui.ttf', 'segoeuib.ttf', 'arial.ttf'):
            font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / name
            assert QFontDatabase.addApplicationFont(str(font)) >= 0
    sys.excepthook = lambda t, value, tb: (errors.append(str(value)), traceback.print_exception(t, value, tb))
    p = example('empty'); p['pdk'] = load_technology('ihp-sg13g2')[0]
    original = clone(p['pdk'])
    w = Studio(recover=False); w.error = lambda text: errors.append(str(text))
    w.maybe_save = lambda: True; w.live_check.setChecked(False)
    w.set_project(p); w.sync_technology(); w.resize(1400, 920); w.show()
    checks = []
    for index, bulk in enumerate((280, 180)):
        dialog = EMProfileDialog(w, w); dialog.show(); QTest.qWait(30)
        dialog.public_ihp_option.setCurrentIndex(index); dialog.public_ihp_load.click()
        stack = dialog.profile()
        assert len(stack['layers']) == 8
        assert next(row for row in stack['layers'] if row['name'] == 'Substrate')['thickness_um'] == bulk
        assert 'SHA256' in dialog.source.text()
        assert w.project['pdk'].get('em_stackup') != stack
        assert dialog.grab().save(str(out / ('profile-' + str(bulk) + '.png')))
        dialog.apply(); app.processEvents()
        assert w.project['pdk']['em_stackup'] == stack
        for field in ('simulation', 'physical', 'package_lock'):
            assert w.project['pdk'][field] == original[field]
        w.undo(); app.processEvents(); assert w.project['pdk'].get('em_stackup') != stack
        w.redo(); app.processEvents(); assert w.project['pdk']['em_stackup'] == stack
        checks.append(dict(bulk_substrate_um=bulk, layers=len(stack['layers']), mapping=stack['layout_map'], undo_redo=True))
    w.path = out / 'public-profile.icproj'; assert w.save()
    restored = load_project(w.path); assert restored['pdk']['em_stackup'] == w.project['pdk']['em_stackup']
    stale = EMProfileDialog(w, w)
    w.project['pdk']['package_lock']['revision'] = 'changed-project'
    stale.load_public_ihp(); assert 'changed' in stale.error.text().lower(); stale.reject()
    w.set_project(restored); w.sync_technology()
    assert not errors, errors
    w.analysis_dirty = False; w.saved_hash = digest(w.project); w.close(); app.processEvents()
    report = dict(status='PASS', scope='Source desktop profile selection, review, apply, undo/redo, save/reopen and stale-project rejection. No installed or solver accuracy qualification.', checks=checks)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
