"""Clean, bounded view exports without changing the editor or its document."""
import math
import re
from copy import copy
from pathlib import Path

from PySide6.QtCore import QIODevice, QPointF, QRectF, QSaveFile, QSize
from PySide6.QtGui import QColor, QFont, QImage, QImageWriter, QPainter
from PySide6.QtWidgets import QFileDialog, QMessageBox

from .ui_style import palette


def screenshot_size(width, height, scale=2):
    if width <= 0 or height <= 0 or not math.isfinite(scale) or scale <= 0:
        raise ValueError('The view must have a positive size.')
    factor = min(scale, 4096 / max(width, height))
    return QSize(max(1, round(width * factor)), max(1, round(height * factor)))


def screenshot_name(cell_name, view):
    name = re.sub(r'[^\w.-]+', '-', cell_name).strip('.-_')[:100] or 'view'
    return name + '-' + view + '.png'


def canvas_image(canvas, scale=2):
    """Render the current framing through a separate, interaction-free canvas."""
    from .canvas import Canvas

    if canvas.cell is None:
        raise ValueError('Open a design before taking a screenshot.')
    size = screenshot_size(canvas.width(), canvas.height(), scale)
    image = QImage(size, QImage.Format_ARGB32_Premultiplied)
    if image.isNull():
        raise ValueError('There is not enough memory to render this screenshot.')
    image.setDevicePixelRatio(size.width() / canvas.width())
    image.fill(QColor(palette(canvas.dark)['canvas']))
    view = Canvas(canvas.mode)
    painter = None
    try:
        view.auto_fit = False
        view.resize(canvas.size())
        cell = canvas.cell
        if cell.get('_layout_scene') is not None:
            scene = copy(cell['_layout_scene'])
            scene.stats = dict(scene.stats)
            scene._bounds_cache = dict(scene._bounds_cache)
            cell = {**cell, '_layout_scene': scene}
        view.set_data(cell, canvas.tech)
        view.scale = canvas.scale
        view.offset = QPointF(canvas.offset)
        view.dark = canvas.dark
        view.visible_layers = set(canvas.visible_layers)
        view.layer_styles = dict(getattr(canvas, 'layer_styles', {}))
        view.context_shapes = list(getattr(canvas, 'context_shapes', []))
        view.simulation_annotations = dict(getattr(canvas, 'simulation_annotations', {}))
        view.cache_layout_pictures = False
        painter = QPainter(image)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        painter.translate(view.offset)
        painter.scale(view.scale, view.scale)
        bounds = QRectF(view.model(QPointF(0, 0)), view.model(QPointF(canvas.width(), canvas.height())))
        if view.cell is not None:
            if canvas.mode == 'schematic':
                view.draw_schematic(painter, bounds, force_detail=True)
            else:
                view.editor_background(painter, bounds)
                view.draw_layout(painter, bounds)
        # Keep the provenance warning when operating-point annotations are shown.
        annotation = getattr(canvas, 'simulation_annotation_label', '') if canvas.mode == 'schematic' else ''
        scene = view.cell.get('_layout_scene') if canvas.mode == 'layout' else None
        if scene is not None and scene.stats.get('detail_reduced'):
            annotation = f'Hierarchy outline · {scene.expanded_count:,} expanded shapes · zoom in for geometry'
        if annotation:
            painter.resetTransform()
            painter.setPen(QColor('#e3a851' if annotation.startswith('STALE') else palette(canvas.dark)['muted']))
            painter.setFont(QFont('Sans Serif', 9))
            painter.drawText(QPointF(12, 23), annotation)
    finally:
        if painter is not None:
            painter.end()
        view.deleteLater()
    image.setDevicePixelRatio(1)
    return image


def write_png(image, path):
    """Publish a complete PNG, preserving an existing file if writing fails."""
    if image.isNull():
        raise ValueError('The view could not be rendered.')
    output = QSaveFile(str(path))
    if not output.open(QIODevice.WriteOnly):
        raise OSError('Could not open the screenshot file. ' + output.errorString())
    try:
        writer = QImageWriter(output, b'png')
        if not writer.write(image):
            raise OSError('Could not write the screenshot. ' + writer.errorString())
        if not output.commit():
            raise OSError('Could not save the screenshot. ' + output.errorString())
    finally:
        if output.isOpen():
            output.cancelWriting()
            # Cancellation only marks the write as failed. Commit discards the
            # temporary file and closes its handle even if a writer retains it.
            output.commit()


def save_view_screenshot(parent, renderer, suggested_name, title='Save screenshot'):
    path, _ = QFileDialog.getSaveFileName(parent, title, suggested_name, 'PNG image (*.png)')
    if not path:
        return None
    if Path(path).suffix.lower() != '.png':
        path += '.png'
        # The native dialog confirmed the typed name, not this appended name.
        if Path(path).exists() and QMessageBox.question(
                parent, 'Replace screenshot?', Path(path).name + ' already exists. Replace it?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return None
    try:
        write_png(renderer(), path)
    except (OSError, ValueError, RuntimeError) as exc:
        QMessageBox.warning(parent, 'Screenshot not saved', str(exc))
        return None
    return path
