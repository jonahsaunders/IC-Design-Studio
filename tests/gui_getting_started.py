"""Exercise the release's new-user flow through Qt and real short worker runs."""
import argparse
import json
import os
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, default=ROOT / 'build/getting-started-evidence')
    parser.add_argument('--pdk-packages', type=Path)
    args = parser.parse_args(); out = args.evidence.resolve(); out.mkdir(parents=True, exist_ok=True)
    os.environ['XDG_DATA_HOME'] = str(out / 'profile/data')
    os.environ['XDG_CONFIG_HOME'] = str(out / 'profile/config')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import digest, file_digest
    from icstudio.getting_started import examples
    from icstudio.spice_program import find_ngspice
    from icstudio import __version__
    errors = []
    def exception(t, v, tb):
        errors.append(str(v)); sys.__excepthook__(t, v, tb)
    sys.excepthook = exception
    app = QApplication([]); app.setStyle('Fusion')
    w = Studio(recover=False); w.error = errors.append; w.resize(1500, 960); w.show()
    exe = find_ngspice(os.environ.get('ICSTUDIO_TEST_NGSPICE', ''))
    if not exe: raise RuntimeError('Set ICSTUDIO_TEST_NGSPICE to a real simulator.')
    w.settings.setValue('engine/ngspice', exe)
    w.jobs_dir = out / 'runs with spaces'
    def wait(predicate, timeout=90):
        deadline = time.monotonic() + timeout
        while predicate() and time.monotonic() < deadline:
            app.processEvents(); time.sleep(.01)
        assert not predicate(), 'Operation timed out'
        assert not errors, errors
    dlg = w.start_here(); QTest.qWait(80)
    assert dlg.example_list.count() == len(examples())
    dlg.grab().save(str(out / 'start-here.png'))
    dlg.search.setText('nothing matches this phrase'); assert dlg.example_list.count() == 0; assert not dlg.open_button.isEnabled()
    dlg.search.setText('01 ·'); assert dlg.example_list.count() == 1
    dlg.open_button.click(); assert not dlg.isVisible(); assert w.path is None
    outcomes = []
    for entry in examples():
        w.saved_hash = digest(w.project)
        assert w.open_gallery_example(entry)
        original = ROOT / 'examples' / entry['file']; before = file_digest(original)
        if entry['engine'] != 'none':
            count = len(w.run_manager.rows); w.quick_run()
            assert len(w.run_manager.rows) == count + 1, (entry['id'], w.analysis_error.text())
            wait(lambda: w.run_manager.busy)
            row = w.run_manager.rows[-1]
            assert row['state'] == 'Complete', (entry['id'], row['log'])
            result = row['result']; assert result['traces']
            if entry['id'] == 'native-divider': assert abs(result['traces']['out'][-1] - .5) < 1e-8
            outcomes.append({'example': entry['id'], 'engine': entry['engine'], 'samples': len(result['x']), 'status': row['state']})
            if entry['id'] == 'inverter':
                w.mode_combo.setCurrentIndex(2); w.schematic.fit(); w.layout.fit(); QTest.qWait(100)
                w.grab().save(str(out / 'workspace.png'))
        else: outcomes.append({'example': entry['id'], 'status': 'Opened and validated; placement exercise'})
        assert file_digest(original) == before
    setup = w.pdk_manager(); setup.start_operation('discover', [ROOT / 'examples/pdk-educational'])
    wait(lambda: setup.worker.isRunning()); QTest.qWait(30)
    assert setup.candidates.count() == 1
    setup.register_selected(); wait(lambda: setup.worker.isRunning()); QTest.qWait(30)
    assert setup.last_result['registered'] and not setup.last_result['errors']
    w.saved_hash = digest(w.project); setup.link_revision(True)
    assert w.project['pdk']['package_lock']['id'] == 'icstudio-educational'
    if args.pdk_packages:
        setup.start_operation('discover', [args.pdk_packages]); wait(lambda: setup.worker.isRunning()); QTest.qWait(30)
        setup.tabs.setCurrentIndex(0); setup.grab().save(str(out / 'pdk-setup.png'))
        setup.register_selected(); wait(lambda: setup.worker.isRunning(), 600); QTest.qWait(30)
        assert not setup.last_result['errors'], setup.last_result
        assert len(setup.last_result['registered']) >= 4
    else:
        setup.grab().save(str(out / 'pdk-setup.png'))
    package_results = setup.last_result
    bad = out / 'damaged-package'; bad.mkdir(exist_ok=True); (bad / 'package.json').write_text('{')
    setup.start_operation('register', [{'name': 'Damaged package', 'kind': 'package', 'path': str(bad)},
                                      {'name': 'Teaching package', 'kind': 'package', 'path': str(ROOT / 'examples/pdk-educational')}])
    wait(lambda: setup.worker.isRunning()); QTest.qWait(30)
    assert len(setup.last_result['errors']) == 1 and len(setup.last_result['registered']) == 1
    setup.close(); w.saved_hash = digest(w.project); w.close()
    report = {'version': __version__, 'status': 'passed', 'platform': sys.platform, 'examples': outcomes,
              'checks': ['Search and empty gallery state', 'Independent example copies', 'Five short real worker runs',
                         'Expected divider voltage', 'Background PDK discovery and registration', 'New project linked to checksummed PDK'],
              'pdk_results': package_results, 'partial_failure_recovery': 'Valid package registered after a damaged package', 'errors': errors}
    (out / 'getting-started.json').write_text(json.dumps(report, indent=2)); print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
