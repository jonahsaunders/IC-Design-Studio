"""Physical editor checks run in a process with its own QApplication."""
import unittest

from PySide6.QtWidgets import QApplication
from icstudio.digital_physical_ui import PhysicalEditor


class PhysicalSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication([])

    def test_isolation_modes(self):
        for settings, index in (({}, 0), ({'nfet_in_dnwell': False}, 1),
                                ({'nfet_in_dnwell': True}, 2)):
            editor = PhysicalEditor(None, settings)
            self.assertEqual(editor.isolation.currentIndex(), index)
            editor.apply()
            self.assertIsNotNone(editor.value)
            self.assertEqual(editor.value.get('nfet_in_dnwell'), settings.get('nfet_in_dnwell'))
            editor.isolation.setCurrentIndex(0)
            editor.apply()
            self.assertNotIn('nfet_in_dnwell', editor.value)
            editor.close()
        self.app.processEvents()

    def test_fill_choice(self):
        dialog = PhysicalEditor(None, {})
        dialog.sky130_fill.setChecked(True)
        dialog.apply()
        self.assertTrue(dialog.value['sky130_fill'])
        second = PhysicalEditor(None, dialog.value)
        self.assertTrue(second.sky130_fill.isChecked())
        second.sky130_fill.setChecked(False)
        second.apply()
        self.assertNotIn('sky130_fill', second.value)
        dialog.close()
        second.close()
        self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
