"""Click a named canvas tool through its visible control at either window size."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest


def click_tool(window, name):
    page = window.ribbon.currentWidget()
    button = next(b for b in page.buttons if b.text() == name)
    if button.isVisible():
        QTest.mouseClick(button, Qt.LeftButton)
        return
    menu = page.more.menu()
    action = button.defaultAction()
    assert page.more.isVisible() and action in menu.actions()
    QTimer.singleShot(0, lambda: QTest.mouseClick(menu, Qt.LeftButton, pos=menu.actionGeometry(action).center()))
    QTest.mouseClick(page.more, Qt.LeftButton)
