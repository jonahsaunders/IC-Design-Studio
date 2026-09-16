"""Real embedded WASM preview, project lifecycle and invalid-RTL regression.

Build assets with scripts/build_vga_playground.py before running this test.
"""
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
OUT = ROOT / 'build/digital-vga-ui'
os.environ['XDG_DATA_HOME'] = str(OUT / 'profile/data')
os.environ['XDG_CONFIG_HOME'] = str(OUT / 'profile/config')


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.digital import counter_project
    from icstudio.digital_design import config
    from icstudio.model import digest, save_project, load_project

    OUT.mkdir(parents=True, exist_ok=True)
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication([]); app.setStyle('Fusion')
    errors = []
    def exception(kind, value, tb):
        errors.append(str(value)); sys.__excepthook__(kind, value, tb)
    sys.excepthook = exception
    studio = Studio(recover=False); studio.error = errors.append
    studio.set_project(counter_project()); studio.resize(1440, 960); studio.show()
    window = studio.digital_window(); window.show_vga(); preview = window.vga

    def wait(condition, seconds=45):
        end = time.monotonic() + seconds
        while not condition() and time.monotonic() < end:
            QTest.qWait(30)
        assert condition(), preview.note.text()
        assert not errors, errors

    def js(expression):
        result = []
        preview.view.page().runJavaScript(expression, result.append)
        wait(lambda: bool(result))
        return result[0]

    def state():
        return json.loads(js('JSON.stringify(window.icstudioVga.status)'))

    wait(lambda: preview.ready)
    assert len(preview.presets) == 8
    original_cell = window.cell_id
    cells = len(studio.project['cells'])
    preview.create_cell()
    wait(lambda: state()['state'] == 'running')
    wait(lambda: state()['frames'] > 1)
    assert window.cell_id != original_cell and len(studio.project['cells']) == cells + 1
    vga_cell = window.cell_id
    assert config(studio.project, vga_cell)['testbench'] == 'tb_vga'
    assert js("Array.from(document.querySelector('canvas').getContext('2d').getImageData(0,0,736,520).data).some((v,i)=>i%4!==3 && v>0)")
    js("document.querySelector('#input-values button').click()")
    assert js("document.querySelector('#input-values button').classList.contains('active')")
    studio.grab().save(str(OUT / 'vga-stripes-dark.png'))
    studio.toggle_theme(); QTest.qWait(100); studio.grab().save(str(OUT / 'vga-stripes-light.png'))
    source = window.editor.toPlainText()
    window.editor.setPlainText(source + '\nthis is invalid Verilog !!!\n')
    wait(lambda: state()['state'] == 'error')
    old_frames = state()['frames']; QTest.qWait(150)
    assert state()['frames'] == old_frames
    window.editor.setPlainText(source)
    wait(lambda: state()['state'] == 'running')
    assert window.apply()
    save_project(studio.project, OUT / 'vga.icproj')
    assert config(load_project(OUT / 'vga.icproj'), vga_cell) == config(studio.project, vga_cell)
    window.result_tabs.setCurrentIndex(0); QTest.qWait(100)
    old_frames = state()['frames']; QTest.qWait(200)
    assert state()['frames'] == old_frames
    window.show_vga(); wait(lambda: state()['frames'] > old_frames)
    window.workspace.switch_cell(original_cell)
    wait(lambda: state()['state'] == 'error')
    window.workspace.switch_cell(vga_cell)
    wait(lambda: state()['state'] == 'running')
    server = preview.server
    studio.saved_hash = digest(studio.project)
    studio.set_project(counter_project()); QTest.qWait(100)
    assert not server.thread.is_alive()
    studio.saved_hash = digest(studio.project); studio.close(); QTest.qWait(100)
    assert not errors, errors
    print(json.dumps({'status': 'passed', 'checks': ['Embedded WASM rendering', 'Eight presets', 'Project-owned RTL',
        'Input controls', 'Invalid source stops old simulation', 'Project round trip', 'Pause on hide',
        'Cell switching', 'Light/dark screenshots', 'Project teardown']}))


if __name__ == '__main__': main()
