"""Capture real desktop views for the README with an isolated local profile.

Run with QT_QPA_PLATFORM=offscreen for reproducible software rendering. An
optional --project accepts the generated overvoltage-bench.icproj described in
docs/OPEN_PROJECTS.md. Source projects are never saved or modified by this script.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/readme-captures')
    parser.add_argument('--project', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['XDG_CONFIG_HOME'] = str(out / 'profile/config')
    os.environ['XDG_DATA_HOME'] = str(out / 'profile/data')
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from icstudio import __version__
    from icstudio.getting_started import examples
    from icstudio.gui import Studio
    from icstudio.model import digest, load_project

    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(out / 'profile/settings'))
    app = QApplication([])
    app.setStyle('Fusion')
    studio = Studio(recover=False)
    errors = []
    studio.error = lambda message: errors.append(str(message))
    studio.maybe_save = lambda: True
    studio.live_check.setChecked(False)
    studio.jobs_dir = out / 'runs'
    studio.resize(1600, 1000)
    studio.show()
    if not studio.dark:
        studio.toggle_theme()
    captures = []

    def capture(widget, name, description):
        QTest.qWait(250)
        path = out / name
        if not widget.grab().save(str(path)):
            raise RuntimeError('Could not save ' + str(path))
        captures.append(dict(file=name, description=description,
                             width=widget.width(), height=widget.height(),
                             sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        print('Captured ' + name, flush=True)

    try:
        entry = next(item for item in examples() if item['id'] == 'rc')
        studio.open_gallery_example(entry)
        studio.quick_run()
        deadline = time.monotonic() + 60
        while studio.run_manager.busy and time.monotonic() < deadline:
            QTest.qWait(25)
        if studio.run_manager.busy or not studio.run_manager.rows:
            raise RuntimeError('Example simulation did not finish')
        run = studio.run_manager.rows[-1]
        if run['state'] != 'Complete':
            raise RuntimeError(str(run.get('log', run['state'])))
        studio.results_tabs.setCurrentIndex(0)
        studio.resizeDocks([studio.results_dock], [480], Qt.Vertical)
        QTest.qWait(150)
        studio.schematic.fit()
        capture(studio, 'simulation-dark.png', 'RC gallery example after an actual built-in transient simulation; dark theme.')
        studio.toggle_theme()
        capture(studio, 'simulation-light.png', 'The same completed RC simulation in the light theme.')
        studio.toggle_theme()
        gallery = studio.start_here()
        capture(gallery, 'example-gallery.png', 'The nine built-in guided examples.')
        gallery.close()

        if args.project:
            project = args.project.resolve()
            source_hash = hashlib.sha256(project.read_bytes()).hexdigest()
            studio.set_project(load_project(project))
            QTest.qWait(300)
            unchanged = digest(studio.project)
            child = next(cell for cell in studio.project['cells'] if cell['name'] == 'level_shifter')
            studio.cell_combo.setCurrentIndex(studio.cell_combo.findData(child['id']))
            studio.mode_combo.setCurrentIndex(0)
            studio.inspector.show()
            studio.mode_combo.setCurrentIndex(2)
            studio.inspector_tabs.setCurrentIndex(0)
            studio.results_dock.hide()
            studio.resize(1600, 940)
            QTest.qWait(200)
            studio.schematic.fit()
            studio.layout.fit()
            capture(studio, 'overvoltage-linked.png', 'Unmodified imported SKY130 level_shifter schematic and attached layout.')
            studio.mode_combo.setCurrentIndex(1)
            studio.inspector.hide()
            QTest.qWait(200)
            studio.layout.fit()
            capture(studio, 'overvoltage-layout.png', 'The same imported cell in the layout editor; inspector hidden for more drawing space.')
            dialog = studio.layout_3d_dialog()
            dialog.resize(1600, 940)
            dialog.split.setSizes([1040, 520])
            QTest.qWait(250)
            if not dialog.mesh:
                raise RuntimeError(dialog.status.text())
            dialog.view.preset('Isometric')
            dialog.z_scale_spin.setValue(.6)
            dialog.view.fit()
            capture(dialog, 'overvoltage-3d.png', 'Read-only 3D extrusion of the imported cell, with illustrative display heights and software rendering.')
            dialog.close()
            if digest(studio.project) != unchanged:
                raise RuntimeError('Read-only captures changed the project')
            if hashlib.sha256(project.read_bytes()).hexdigest() != source_hash:
                raise RuntimeError('Source project changed')
        if errors:
            raise RuntimeError('; '.join(errors))
        (out / 'captures.json').write_text(json.dumps(dict(
            app_version=__version__, qt_platform=app.platformName(), captures=captures,
            detector_project_sha256=source_hash if args.project else None,
        ), indent=2) + '\n', encoding='utf-8')
    finally:
        studio.saved_hash = digest(studio.project)
        studio.close()
        app.processEvents()


if __name__ == '__main__':
    main()
