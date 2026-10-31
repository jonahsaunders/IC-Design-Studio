"""Exercise the proposed bundled ESD binding without claiming installed acceptance."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import QApplication
from icstudio.bundled_pdks import packages
from icstudio.esd_desktop_probe import place_esd, KEY, MODEL
from icstudio.mim_desktop_probe import selected_file
from icstudio.interchange import spice
from icstudio.model import file_digest, load_project, save_project
from icstudio.pdks import stage_model_deck
from scripts import sky130_esd_revision_bridge as bridge

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'icstudio/assets/pdks/sky130A'
PREDECESSOR = ROOT/'icstudio/assets/qualification/sky130-esd-predecessor-v1/package.json'
CURRENT = '0c19e0ea5718a841045b597022d13f2dcb57e35cf8be9757b254fb465f2a35c4'
REVISION = '47dbd4fe43bfa7e4'


class DefaultCandidateTests(unittest.TestCase):
    def test_predecessor_rejects_linked_source_and_wrong_manifest(self):
        from scripts.prepare_sky130_esd_nvt import predecessor
        with tempfile.TemporaryDirectory(prefix='esd-links-') as tmp:
            folder=Path(tmp); bad=folder/'wrong.json'; bad.write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'manifest identity'):
                with predecessor(BASE, bad): pass
            linked=folder/'linked'
            try: linked.symlink_to(BASE, target_is_directory=True)
            except OSError: return  # Ordinary Windows users may not create symlinks.
            with self.assertRaisesRegex(ValueError, 'symlink or junction'):
                with predecessor(linked): pass

    def test_actual_hub_old_lock_esd_placement_and_model_staging(self):
        # Other tests may own a QCoreApplication; widgets require a fresh GUI
        # application. Keep the real Hub assertions and profile overrides in
        # their own process so discovery order cannot change either result.
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
        env.update(QT_QPA_PLATFORM='offscreen', PYTHONPATH=os.pathsep.join((str(ROOT), str(ROOT/'tests'))))
        method = 'DefaultCandidateTests._exercise_actual_hub_old_lock_esd_placement_and_model_staging'
        run = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), method, '-v'],
                             cwd=ROOT, env=env, capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=120)
        self.assertEqual(run.returncode, 0, run.stdout[-6000:]+run.stderr[-6000:])
        self.assertIn('Ran 1 test', run.stderr)

    def _exercise_actual_hub_old_lock_esd_placement_and_model_staging(self):
        self.assertEqual(file_digest(PREDECESSOR), bridge.BASE)
        self.assertEqual(file_digest(BASE/'package.json'), CURRENT)
        included = packages(verify=True)
        row = next(x for x in included if x['name'] == 'sky130A')
        self.assertEqual((row['revision'], Path(row['path'])), (REVISION, BASE))
        old = json.loads(PREDECESSOR.read_bytes())
        new = json.loads((BASE/'package.json').read_bytes())
        self.assertTrue(all(new['files'].get(k) == v for k, v in old['files'].items()))
        with tempfile.TemporaryDirectory(prefix='esd-default-') as tmp:
            root = Path(tmp); previous = root/'previous'; previous.mkdir()
            for name, sha in old['files'].items():
                src = BASE/name; dest = previous/name
                self.assertEqual(file_digest(src), sha)
                dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dest)
            shutil.copyfile(PREDECESSOR, previous/'package.json')
            os.environ['XDG_DATA_HOME'] = str(root/'profile/data')
            os.environ['XDG_CONFIG_HOME'] = str(root/'profile/config')
            QSettings.setDefaultFormat(QSettings.IniFormat)
            QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(root/'settings'))
            QStandardPaths.writableLocation = staticmethod(lambda kind: str(root/'profile'/str(kind.value)))
            app = QApplication.instance() or QApplication([])
            from icstudio.gui import Studio
            from icstudio.model import example, clone
            studio = Studio(recover=False); studio.maybe_save = lambda: True
            try:
                oldkey = studio.pdk_registry.install(previous/'package.json')
                p = example('empty'); p['pdk'] = clone(studio.pdk_registry.technology(oldkey))
                oldpath = root/'old.icproj'; save_project(p, oldpath)
                before = load_project(oldpath)
                hub = studio.project_hub(); app.processEvents()
                key = 'sky130A@'+REVISION
                self.assertTrue(hub.select_pdk(key)); self.assertEqual(hub.current_pdk()['status'], 'Available offline')
                hub.show_page('new'); hub.name.setText('Default ESD candidate'); hub.create_button.click()
                deadline = time.monotonic()+60
                while hub.busy() and time.monotonic() < deadline:
                    app.processEvents(); time.sleep(.02)
                app.processEvents()
                self.assertFalse(hub.busy()); self.assertEqual(studio.project['pdk']['revision'], REVISION, hub.state.text())
                current_project = clone(studio.project)
                with selected_file('getOpenFileName', oldpath): studio.open_project()
                app.processEvents()
                self.assertEqual(studio.project['pdk'], before['pdk'])
                self.assertEqual(load_project(oldpath), before)
                self.assertEqual(before['pdk']['revision'], old['revision'])
                studio.set_project(current_project)
                selected = studio.project['pdk']; place_esd(app, studio, selected)
                selected_path = root/'selected.icproj'; save_project(studio.project, selected_path)
                saved = load_project(selected_path)
                self.assertEqual(saved['pdk']['revision'], REVISION)
                deck = spice(saved); self.assertEqual(deck.count(MODEL+' '), 6)
                staged = stage_model_deck(selected, deck, root/'staged')
                mapping = json.loads((root/'staged/pdk-model-files.json').read_bytes())
                model = bridge.PREFIX+MODEL+'.pm3.spice'
                matches = [name for name, source in mapping.items() if source == model]
                self.assertEqual(len(matches), 1)
                self.assertIn(matches[0], staged)
                self.assertEqual(file_digest(root/'staged'/matches[0]), new['files'][model])
                self.assertFalse(before['pdk']['simulation']['catalog'][KEY]['unavailable'] == '')
            finally:
                studio.close(); app.processEvents()


if __name__ == '__main__': unittest.main()
