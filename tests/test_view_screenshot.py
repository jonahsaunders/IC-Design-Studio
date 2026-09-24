import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QMessageBox
from icstudio.view_screenshot import save_view_screenshot, screenshot_name, screenshot_size, write_png


class ScreenshotTests(unittest.TestCase):
    def test_resolution_is_bounded_and_preserves_view_aspect(self):
        self.assertEqual(screenshot_size(800, 600), QSize(1600, 1200))
        self.assertEqual(screenshot_size(3000, 1500), QSize(4096, 2048))
        self.assertEqual(screenshot_size(1, 10000), QSize(1, 4096))
        for scale in (0, -1, float('inf'), float('nan')):
            with self.assertRaises(ValueError): screenshot_size(800, 600, scale)

    def test_default_name_cannot_escape_the_save_directory(self):
        self.assertEqual(screenshot_name('../my circuit/top', 'schematic'), 'my-circuit-top-schematic.png')
        self.assertEqual(screenshot_name('...', 'layout'), 'view-layout.png')

    def test_cancel_does_not_render_and_failures_are_visible(self):
        render = Mock()
        with patch('icstudio.view_screenshot.QFileDialog.getSaveFileName', return_value=('', '')):
            self.assertIsNone(save_view_screenshot(None, render, 'view.png'))
        render.assert_not_called()
        render.side_effect = ValueError('No view')
        with patch('icstudio.view_screenshot.QFileDialog.getSaveFileName', return_value=('view.png', '')), \
             patch('icstudio.view_screenshot.QMessageBox.warning') as warning:
            self.assertIsNone(save_view_screenshot(None, render, 'view.png'))
            warning.assert_called_once_with(None, 'Screenshot not saved', 'No view')

    def test_png_extension_encoding_and_failed_write_preserve_existing_file(self):
        image = QImage(80, 40, QImage.Format_ARGB32_Premultiplied); image.fill(QColor('#3485a5'))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'export'
            with patch('icstudio.view_screenshot.QFileDialog.getSaveFileName', return_value=(str(path), '')):
                saved = save_view_screenshot(None, lambda: image, 'view.png')
            target = path.with_suffix('.png')
            self.assertEqual(saved, str(target)); self.assertEqual(QImage(saved).convertToFormat(image.format()), image)
            original = target.read_bytes()
            with patch('icstudio.view_screenshot.QImageWriter') as writer:
                writer.return_value.write.return_value = False
                writer.return_value.errorString.return_value = 'write failed'
                with self.assertRaisesRegex(OSError, 'write failed'): write_png(image, target)
                # Retain the device as a writer or traceback can, so cleanup
                # cannot rely on garbage collection to release a Windows lock.
                output = writer.call_args.args[0]
                self.assertFalse(output.isOpen(), 'Failed export left its temporary file open')
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(list(Path(folder).iterdir()), [target])

    def test_appended_extension_never_silently_replaces_an_existing_image(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'export.png'; path.write_bytes(b'existing image')
            render = Mock()
            with patch('icstudio.view_screenshot.QFileDialog.getSaveFileName', return_value=(str(path.with_suffix('')), '')), \
                 patch('icstudio.view_screenshot.QMessageBox.question', return_value=QMessageBox.No) as question:
                self.assertIsNone(save_view_screenshot(None, render, 'view.png'))
            question.assert_called_once(); render.assert_not_called()
            self.assertEqual(path.read_bytes(), b'existing image')


if __name__ == '__main__': unittest.main()
