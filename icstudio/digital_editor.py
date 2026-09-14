"""Native RTL editor with line numbers, a current-line guide and local search."""
from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QPainter, QTextFormat, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit, QInputDialog


class Gutter(QWidget):
    def __init__(self, editor):
        super().__init__(editor); self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_gutter(event)


class SourceEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent); self.gutter = Gutter(self); self.query = ''
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)
        self.blockCountChanged.connect(self.update_margin)
        self.updateRequest.connect(self.update_gutter)
        self.cursorPositionChanged.connect(self.current_line)
        QShortcut(QKeySequence.Find, self, activated=self.find_text)
        QShortcut(QKeySequence.FindNext, self, activated=self.find_next)
        QShortcut(QKeySequence('Ctrl+L'), self, activated=self.go_to_line)
        self.update_margin(); self.current_line()

    def gutter_width(self):
        return 18 + self.fontMetrics().horizontalAdvance('9') * len(str(max(1, self.blockCount())))

    def update_margin(self, *_):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def update_gutter(self, rect, dy):
        if dy: self.gutter.scroll(0, dy)
        else: self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()): self.update_margin()

    def resizeEvent(self, event):
        super().resizeEvent(event); rect = self.contentsRect()
        self.gutter.setGeometry(QRect(rect.left(), rect.top(), self.gutter_width(), rect.height()))

    def paint_gutter(self, event):
        painter = QPainter(self.gutter); painter.fillRect(event.rect(), self.palette().alternateBase())
        block = self.firstVisibleBlock(); number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = round(self.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                painter.setPen(self.palette().text().color() if number == self.textCursor().blockNumber() else self.palette().placeholderText().color())
                painter.drawText(0, top, self.gutter.width()-8, self.fontMetrics().height(), Qt.AlignRight, str(number+1))
            block = block.next(); top += height; number += 1

    def current_line(self):
        selection = QTextEdit.ExtraSelection(); color = QColor(self.palette().highlight().color()); color.setAlpha(24)
        selection.format.setBackground(color); selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = self.textCursor(); selection.cursor.clearSelection()
        self.setExtraSelections([selection]); self.gutter.update()

    def find_text(self):
        value, ok = QInputDialog.getText(self, 'Find in source', 'Text', text=self.textCursor().selectedText() or self.query)
        if ok and value: self.query = value; self.find_next()

    def find_next(self):
        if not self.query: return self.find_text()
        if not self.find(self.query):
            cursor = self.textCursor(); cursor.movePosition(cursor.Start); self.setTextCursor(cursor); self.find(self.query)

    def go_to_line(self):
        number, ok = QInputDialog.getInt(self, 'Go to line', 'Line', self.textCursor().blockNumber()+1, 1, self.blockCount())
        if ok:
            cursor = self.textCursor(); cursor.setPosition(self.document().findBlockByNumber(number-1).position())
            self.setTextCursor(cursor); self.centerCursor()
