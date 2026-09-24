"""Exercise clean schematic/layout export through the desktop Screenshot button."""
import argparse
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
out = parser.parse_args().out.resolve(); out.mkdir(parents=True, exist_ok=True)
os.environ['XDG_CONFIG_HOME'] = str(out / 'profile/config')
os.environ['XDG_DATA_HOME'] = str(out / 'profile/data')

from PySide6.QtCore import QPointF, QSettings, QStandardPaths, QTimer, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from icstudio.gui import Studio
from icstudio.model import clone, digest, example
from icstudio.ui_style import palette
from icstudio.view_screenshot import canvas_image, screenshot_size
from icstudio import wiring
from test_layout_3d import fixture

QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(out / 'profile/settings'))
QStandardPaths.writableLocation = staticmethod(lambda kind: str(out / 'profile' / str(kind.value)))
app = QApplication([]); app.setStyle('Fusion')
errors = []; sys.excepthook = lambda typ, value, tb: errors.append(str(value))
studio = Studio(recover=False); studio.maybe_save = lambda: True
studio.live_check.setChecked(False); studio.show(); QTest.qWait(200)

try:
    project = example('rc'); cell = project['cells'][0]
    wiring.migrate(cell, project)
    cell['shapes'] = fixture()['cells'][0]['shapes']
    studio.set_project(project)
    before = digest(studio.project); history = clone((studio.history.undo_stack, studio.history.redo_stack))
    for mode, canvas in enumerate((studio.schematic, studio.layout)):
        studio.mode_combo.setCurrentIndex(mode); QTest.qWait(50); canvas.fit(); canvas.auto_fit = False
        framing = (canvas.scale, QPointF(canvas.offset), canvas.size())
        clean = canvas_image(canvas)
        assert clean.size() == screenshot_size(canvas.width(), canvas.height())
        blank = QImage(clean.size(), clean.format()); blank.fill(QColor(palette(canvas.dark)['canvas']))
        assert clean != blank, 'Screenshot contains no design'
        canvas.selection = [cell['devices'][0]['id'] if mode == 0 else cell['shapes'][0]['id']]
        canvas.net = 'ring'; canvas.anchor = QPointF(10, 10); canvas.drag = QPointF(30, 30); canvas.moving = True
        canvas.ruler = (QPointF(0, 0), QPointF(100, 100)); canvas.finding_box = [0, 0, 2000, 2000]
        canvas.connection_guides = [{'start': [0, 0], 'end': [1000, 1000]}]
        if mode == 0: canvas.capture_preview = {**canvas.cell, 'devices': []}
        assert canvas_image(canvas) == clean, 'Selection or draft overlays leaked into screenshot'
        target = out / (canvas.mode + '.png')
        with patch('icstudio.view_screenshot.QFileDialog.getSaveFileName', return_value=(str(target), '')):
            QTest.mouseClick(studio.screenshot_button, Qt.LeftButton)
        assert QImage(str(target)).convertToFormat(clean.format()) == clean
        assert (canvas.scale, canvas.offset, canvas.size()) == framing
        assert canvas.moving and canvas.selection and canvas.ruler
        assert digest(studio.project) == before
        canvas.moving = False; canvas.anchor = canvas.drag = canvas.ruler = None
        canvas.finding_box = None; canvas.connection_guides = []; canvas.selection = []; canvas.net = ''
        if mode == 0: canvas.capture_preview = None
        if mode == 1:
            visible = set(canvas.visible_layers); canvas.visible_layers.clear()
            assert canvas_image(canvas) == blank, 'Hidden layers leaked into screenshot'
            canvas.visible_layers = visible
            canvas.layer_styles = {'metal2': {'color': '#ff6633', 'pattern': 'Hatch'}}
            assert canvas_image(canvas) != clean, 'Layer styling was not preserved'
        canvas.offset += QPointF(29, 11)
        assert canvas_image(canvas) != clean, 'Current viewport pan was ignored'
    assert (studio.history.undo_stack, studio.history.redo_stack) == history

    # Linked views ask which image to export, rather than capturing both panes.
    studio.mode_combo.setCurrentIndex(2); QTest.qWait(50)
    for index, target in enumerate((studio.schematic, studio.layout)):
        def choose():
            menu = app.activePopupWidget()
            try:
                assert [a.text() for a in menu.actions()] == ['Schematic screenshot…', 'Layout screenshot…']
                menu.actions()[index].trigger()
            finally:
                if menu is not None: menu.close()
        with patch.object(studio, 'save_canvas_screenshot') as save:
            QTimer.singleShot(0, choose)
            studio.screenshot_active(); save.assert_called_once_with(target)

    studio.mode_combo.setCurrentIndex(0); QTest.qWait(50)
    studio.schematic.fit(); studio.resize(1000, 680); QTest.qWait(80)
    assert studio.screenshot_button.isVisible() and studio.screenshot_button.width() > 20
    assert studio.screenshot_button.visibleRegion().boundingRect() == studio.screenshot_button.rect()
    assert studio.screenshot_button.text() == '' and studio.screenshot_button.accessibleName() == 'Screenshot'
    studio.statusBar().clearMessage()
    assert studio.grab().save(str(out / 'screenshot-button-compact.png'))
    studio.resize(1440, 900); QTest.qWait(80); studio.schematic.fit()
    assert studio.screenshot_button.text() == 'Screenshot'
    assert studio.screenshot_button.width() >= studio.screenshot_button.sizeHint().width()
    assert studio.grab().save(str(out / 'screenshot-button.png'))
    assert not errors, errors
    print('PASS: screenshot buttons, linked views, high-resolution PNGs, framing/layers/styles, clean overlays and document/view isolation.')
finally:
    studio.saved_hash = digest(studio.project); studio.close(); app.processEvents()
