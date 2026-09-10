"""Exercise 3D controls, rendering, snapshot lifecycle and a million-instance crop."""
import argparse
import json
import os
from pathlib import Path
import sys
import traceback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--require-opengl', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve();out.mkdir(parents=True, exist_ok=True)
    os.environ['XDG_CONFIG_HOME'] = str(out/'profile/config')
    os.environ['XDG_DATA_HOME'] = str(out/'profile/data')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QPoint, QPointF, QSettings, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFileDialog
    from unittest.mock import patch
    from icstudio.gui import Studio
    from icstudio.layout import rect
    from icstudio.layout_3d_view import OpenGLView, BACKGROUND
    from icstudio.model import digest, example
    from test_layout_3d import fixture
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(out/'profile/settings'))
    app = QApplication([]);app.setStyle('Fusion')
    errors = []
    sys.excepthook = lambda kind, value, tb: errors.append(''.join(traceback.format_exception(kind, value, tb)))
    studio = Studio(recover=False);studio.maybe_save = lambda: True
    studio.live_check.setChecked(False);studio.show()
    checks = []
    try:
        p = fixture();studio.set_project(p)
        before = digest(studio.project)
        actions = [a for a in studio.task_menus['Layout'].actions() if a.text() == '3D layout viewer…']
        assert len(actions) == 1
        actions[0].trigger();QTest.qWait(350)
        dialog = studio._layout_3d_dialog
        assert dialog is studio.layout_3d_dialog()
        view = dialog.view
        if args.require_opengl:
            assert isinstance(view, OpenGLView), dialog.backend.text() + ': ' + dialog.backend.toolTip()
            assert view.isValid() and not view.error, view.error
        view.preset('Top');QTest.qWait(60)
        image = view.grabFramebuffer() if isinstance(view, OpenGLView) else view.grab().toImage()
        # The ring's hole must remain background at its center in a top view.
        matrix = view.matrix()
        from PySide6.QtGui import QVector3D, QColor
        origin = dialog.mesh.origin_um
        pt = matrix.map(QVector3D(5-origin[0], 4-origin[1], 0))
        x, y = round((pt.x()+1)*image.width()/2), round((1-pt.y())*image.height()/2)
        assert image.pixelColor(x,y).name() == BACKGROUND.name(), image.pixelColor(x,y).name()
        # Verify actual colored geometry, not only the canvas and text.
        pt = matrix.map(QVector3D(5-origin[0], 1-origin[1], 0))
        x, y = round((pt.x()+1)*image.width()/2), round((1-pt.y())*image.height()/2)
        assert image.pixelColor(x,y).name() != BACKGROUND.name()
        # Draw the higher solid first, then the lower solid: occlusion must
        # follow Z rather than layer submission order, including after repaint.
        from icstudio.layout_3d_view import shade
        metal1 = next(l for l in dialog.mesh.layers if l.name == 'metal1')
        original_z = metal1.z_um;metal1.z_um = 10;view.fit();QTest.qWait(50)
        image = view.grabFramebuffer() if isinstance(view, OpenGLView) else view.grab().toImage()
        pt = view.matrix().map(QVector3D(5-origin[0], 1-origin[1], 10))
        x, y = round((pt.x()+1)*image.width()/2), round((1-pt.y())*image.height()/2)
        expected = shade(QColor(metal1.color), (0,0,1));actual = image.pixelColor(x,y)
        assert max(abs(a-b) for a,b in zip(actual.getRgb()[:3], expected.getRgb()[:3])) <= 2, (actual.name(),expected.name())
        metal1.z_um=original_z;view.fit()
        checks.append('rendered material and open hole')
        view.preset('Isometric');view.setFocus();QTest.qWait(30)
        yaw = view.yaw
        QTest.mousePress(view, Qt.LeftButton, pos=QPoint(200,200))
        QTest.mouseMove(view, QPoint(260,230), delay=30)
        QTest.mouseRelease(view, Qt.LeftButton, pos=QPoint(260,230))
        assert view.yaw != yaw
        QTest.mousePress(view, Qt.RightButton, pos=QPoint(200,200))
        QTest.mouseMove(view, QPoint(240,220), delay=30)
        QTest.mouseRelease(view, Qt.RightButton, pos=QPoint(240,220))
        assert view.pan != QPointF()
        wheel = QWheelEvent(QPointF(200,200), QPointF(200,200), QPoint(), QPoint(0,120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        QApplication.sendEvent(view, wheel);assert view.zoom > 1
        QTest.keyClick(view, Qt.Key_F);assert view.zoom == 1 and view.pan == QPointF()
        checks.append('orbit pan zoom and keyboard fit')
        metal_row = next(i for i,l in enumerate(dialog.mesh.layers) if l.name == 'metal2')
        dialog.table.item(metal_row,0).setCheckState(Qt.Unchecked)
        assert not dialog.mesh.layers[metal_row].visible
        dialog.table.item(metal_row,0).setCheckState(Qt.Checked)
        dialog.table.cellWidget(metal_row,1).setValue(4.25)
        dialog.table.cellWidget(metal_row,2).setValue(.55)
        dialog.z_scale_spin.setValue(1.5);dialog.explode_spin.setValue(.2)
        assert dialog.mesh.layers[metal_row].z_um == 4.25
        assert digest(studio.project) == before and not studio.history.undo_stack
        QTest.qWait(40);dialog.grab().save(str(out/'layout-3d.png'))
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(out/'saved-view'), 'PNG')):
            dialog.save_button.click()
        assert (out/'saved-view.png').is_file()
        studio.commit(lambda p:p['cells'][0]['shapes'].append(rect('metal1',12000,0,1000,1000)), '3D refresh fixture')
        dialog.check_stale();assert 'changed' in dialog.status.text()
        dialog.refresh_button.click()
        assert dialog.mesh.shape_count == 6 and dialog.mesh.layers[metal_row].z_um == 4.25
        assert dialog.table.item(metal_row,3).text() == 'Custom'
        dialog.reset_stack();assert dialog.mesh.layers[metal_row].z_um != 4.25
        checks.append('layer controls PNG export read-only snapshot and refresh')
        # Reuse a mirrored/rotated cell as an array, then exercise the same window
        # on a million-instance design without retaining an old successful view.
        p = fixture();tile = p['cells'][0]
        top = dict(id='top3d',name='array_top',ports=[],devices=[],shapes=[],layout_instances=[
            dict(id='array',name='array',cell=tile['id'],x=0,y=0,rotation=90,mirror=True,
                 nx=2,ny=2,a=[16000,0],b=[0,16000])])
        p['cells'].append(top);p['top']=top['id'];studio.set_project(p)
        dialog.refresh_button.click();assert dialog.mesh.shape_count == 20
        QTest.qWait(40);dialog.grab().save(str(out/'layout-3d-hierarchy.png'))
        p = example('empty');top=p['cells'][0]
        p['cells'].append(dict(id='tile',name='tile',ports=[],devices=[],shapes=[rect('metal1',0,0,600,600)]))
        top['layout_instances']=[dict(id='array',name='array',cell='tile',x=0,y=0,nx=1000,ny=1000,a=[2000,0],b=[0,2000])]
        studio.set_project(p);dialog.refresh_button.click()
        assert dialog.mesh is None and dialog.view.mesh is None
        assert 'detail budget' in dialog.status.text() and not dialog.save_button.isEnabled()
        studio.layout.auto_fit=False;studio.layout.scale=.5;studio.layout.offset=QPointF(20,20)
        dialog.region.setCurrentIndex(1)
        assert dialog.mesh and dialog.mesh.cropped and dialog.mesh.shape_count < 20
        checks.append('hierarchical transforms and bounded million-instance viewport')
        dialog.close();QTest.qWait(30);assert studio._layout_3d_dialog is None
        # Reopening must allocate a fresh renderer and release the previous GL buffers.
        studio.set_project(fixture());dialog=studio.layout_3d_dialog();QTest.qWait(350)
        assert dialog.mesh.triangle_count > 0
        if args.require_opengl:
            assert isinstance(dialog.view, OpenGLView) and not dialog.view.error
        renderer = type(dialog.view).__name__
        dialog.close();QTest.qWait(30)
        checks.append('close and reopen resource lifecycle')
        assert not errors, errors
        report = dict(status='passed', renderer=renderer, qt_platform=app.platformName(), checks=checks)
        (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
    finally:
        if getattr(studio, '_layout_3d_dialog', None):studio._layout_3d_dialog.close()
        studio.close();app.processEvents()


if __name__ == '__main__':
    main()
