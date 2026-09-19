"""Exercise the real embedded VGA renderer in source and packaged applications."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback


def main(output):
    from . import __version__
    from .build_identity import identity
    from .digital_vga import assets, REVISION, PRESET_IDS
    from .model import digest, save_project, load_project

    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = dict(status='failed', version=__version__, build=identity(),
                  frozen=bool(getattr(sys, 'frozen', False)), os=platform.platform(),
                  checks=[], presets=[], limitations=['Audio device quality and physical display acceptance remain manual.'])
    errors = []
    app = studio = preview = None
    previous_hook = sys.excepthook
    sys.excepthook = lambda kind, value, tb: errors.append(''.join(traceback.format_exception(kind, value, tb)))
    for key in ('XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'APPDATA', 'LOCALAPPDATA'):
        os.environ[key] = str(out / 'profile' / key)
    try:
        from PySide6.QtCore import QPoint, QSettings, QStandardPaths, Qt
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from .gui import Studio
        from .digital import counter_project
        from .digital_design import config

        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
        QStandardPaths.setTestModeEnabled(True)
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(out / 'profile/settings'))
        app = QApplication([])
        app.setStyle('Fusion')
        report['display'] = app.platformName()
        report['assets'] = str(assets())
        manifest = json.loads((assets() / 'icstudio-build.json').read_text())
        assert manifest['revision'] == REVISION
        if report['frozen']:
            assert report['build']['commit'] != 'unknown' and report['build']['dirty'] is False
            assert assets() == Path(__file__).parent / 'assets/vga-playground', 'Frozen app fell back to source assets'
        studio = Studio(recover=False)
        studio.error = errors.append
        studio.set_project(counter_project())
        studio.resize(1440, 1000)
        studio.show()
        window = studio.digital_window()
        window.show_vga()
        preview = window.vga

        def wait(condition, seconds=60):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                QTest.qWait(30)
                assert not errors, errors
                if condition():
                    return
            raise AssertionError('VGA timed out: ' + preview.note.text())

        def js(expression):
            values = []
            preview.view.page().runJavaScript(expression, values.append)
            wait(lambda: bool(values), 15)
            return values[0]

        def state():
            return json.loads(js('JSON.stringify(window.icstudioVga.status)'))

        def click(selector):
            # Native pointer input supplies the user gesture required by Web Audio.
            point = json.loads(js('JSON.stringify((()=>{const r=document.querySelector(' +
                                 json.dumps(selector) + ').getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})())'))
            target = preview.view.focusProxy() or preview.view
            QTest.mouseClick(target, Qt.LeftButton, pos=QPoint(round(point[0]), round(point[1])))
            QTest.qWait(50)

        def active(selector):
            return js('document.querySelector(' + json.dumps(selector) + ').classList.contains("active")')

        wait(lambda: preview.ready)
        assert preview.profile.isOffTheRecord()
        assert preview.server.url.startswith('http://127.0.0.1:')
        assert len(preview.presets) == 8
        assert {preset['id'] for preset in preview.presets} == set(PRESET_IDS)
        report['checks'].append('Offline loopback startup with private Qt WebEngine profile and pinned assets')
        original_cell = window.cell_id
        created_cells = []
        for index, preset in enumerate(preview.presets):
            revision = state()['revision']
            frames = state()['frames']
            preview.preset.setCurrentIndex(index)
            preview.create_cell()
            wait(lambda: state()['state'] == 'running' and state()['revision'] > revision)
            wait(lambda: state()['frames'] > frames + 1)
            assert config(studio.project, window.cell_id)['testbench'] == 'tb_vga'
            assert js('(()=>{const c=document.querySelector("canvas");return Array.from(c.getContext("2d").getImageData(0,0,c.width,c.height).data).some((v,i)=>i%4===3&&v===255)})()')
            created_cells.append(window.cell_id)
            assert studio.grab().save(str(out / (preset['id'] + '.png')))
            report['presets'].append(dict(id=preset['id'], name=preset['name'], status='passed'))
        assert len(set(created_cells)) == 8
        studio.toggle_theme()
        QTest.qWait(100)
        assert studio.grab().save(str(out / 'vga-light.png'))
        studio.toggle_theme()
        report['checks'].append('All eight project-owned presets compile and produce frames in the embedded renderer')

        input_button = '#input-values button:first-child'
        click(input_button)
        wait(lambda: active(input_button))
        click(input_button)
        wait(lambda: not active(input_button))
        gamepad = '#input-values button[data-role="gamepad"]'
        click(gamepad)
        wait(lambda: active(gamepad))
        target = preview.view.focusProxy() or preview.view
        QTest.keyPress(target, Qt.Key_A)
        wait(lambda: active('#gamepad-pmod-inputs button[data-index="8"]'))
        QTest.keyRelease(target, Qt.Key_A)
        wait(lambda: not active('#gamepad-pmod-inputs button[data-index="8"]'))
        click(gamepad)
        click('#input-values button[data-role="reset"]')
        frames = state()['frames']
        wait(lambda: state()['frames'] > frames)
        report['checks'].append('Native pointer input, keyboard Gamepad controls and reset')

        music = next(i for i, p in enumerate(preview.presets) if p['name'].lower() == 'music')
        revision = state()['revision']
        window.workspace.switch_cell(created_cells[music])
        wait(lambda: state()['state'] == 'running' and state()['revision'] > revision)
        audio = '#input-values button[data-role="audio"]'
        assert not active(audio), 'Audio started without opt-in'
        click(audio)
        wait(lambda: active(audio))
        window.result_tabs.setCurrentIndex(0)
        QTest.qWait(200)
        wait(lambda: not active(audio))
        frames = state()['frames']
        QTest.qWait(250)
        assert state()['frames'] == frames
        window.show_vga()
        wait(lambda: state()['frames'] > frames)
        assert not active(audio), 'Returning to the preview resumed audio without opt-in'
        report['checks'].append('Opt-in Web Audio starts; hiding pauses audio/rendering; returning resumes rendering only')

        source = window.editor.toPlainText()
        window.editor.setPlainText(source + '\nthis is invalid Verilog !!!\n')
        wait(lambda: state()['state'] == 'error')
        frames = state()['frames']
        QTest.qWait(200)
        assert state()['frames'] == frames
        window.editor.setPlainText(source)
        wait(lambda: state()['state'] == 'running')
        assert window.apply()
        preview.reload()
        wait(lambda: preview.ready and state()['state'] == 'running')
        report['checks'].append('Invalid RTL stops the old simulation; correction and renderer reload recover the working copy')

        vga_cell = window.cell_id
        window.workspace.switch_cell(original_cell)
        wait(lambda: state()['state'] == 'error')
        window.workspace.switch_cell(vga_cell)
        wait(lambda: state()['state'] == 'running')
        path = out / 'VGA project with spaces.icproj'
        save_project(studio.project, path)
        reopened = load_project(path)
        assert config(reopened, vga_cell) == config(studio.project, vga_cell)
        server = preview.server
        studio.saved_hash = digest(studio.project)
        studio.set_project(reopened, path)
        QTest.qWait(100)
        assert not server.thread.is_alive(), 'Project replacement left an asset server running'
        window = studio.digital_window()
        window.workspace.switch_cell(vga_cell)
        window.show_vga()
        preview = window.vga
        wait(lambda: preview.ready and state()['state'] == 'running')
        report['checks'].append('Cell switching, save/reopen with sources and memory data, and old-project server teardown')
        server = preview.server
        studio.saved_hash = digest(studio.project)
        studio.close()
        app.aboutToQuit.emit()
        QTest.qWait(100)
        assert not server.thread.is_alive(), 'Application shutdown left an asset server running'
        assert not errors, errors
        report['checks'].append('Application shutdown closes the loopback listener')
        report['status'] = 'passed'
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        try:
            if preview is not None:
                preview.shutdown()
            if studio is not None:
                studio.saved_hash = digest(studio.project)
                studio.close()
        except Exception:
            errors.append(traceback.format_exc())
        report['errors'] = errors
        if errors:
            report['status'] = 'failed'
        (out / 'vga-test.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        sys.excepthook = previous_hook
    return 0 if report['status'] == 'passed' else 1
