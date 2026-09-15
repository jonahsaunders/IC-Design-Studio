"""Small, accessible desktop controls shared by the analog workspace."""
from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtWidgets import (QLayout, QWidgetItem, QPushButton, QLabel, QScrollArea,
                              QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem)


class FlowActions(QLayout):
    """Keep descriptive button labels intact when a window becomes narrower."""
    def __init__(self, parent=None):
        super().__init__(parent); self.items = []; self.setContentsMargins(0, 0, 0, 0); self.setSpacing(6)

    def addItem(self, item): self.items.append(item)
    def count(self): return len(self.items)
    def itemAt(self, index): return self.items[index] if 0 <= index < len(self.items) else None
    def takeAt(self, index): return self.items.pop(index) if 0 <= index < len(self.items) else None
    def expandingDirections(self): return Qt.Orientations()
    def hasHeightForWidth(self): return True
    def heightForWidth(self, width): return self.arrange(QRect(0, 0, width, 0), False)
    def sizeHint(self): return self.minimumSize()
    def minimumSize(self):
        return QSize(max((i.sizeHint().width() for i in self.items), default=0), max((i.sizeHint().height() for i in self.items), default=0))
    def setGeometry(self, rect): super().setGeometry(rect); self.arrange(rect, True)
    def arrange(self, rect, place):
        x, y, height = rect.x(), rect.y(), 0
        for item in self.items:
            if item.isEmpty(): continue
            size = item.sizeHint()
            if x > rect.x() and x + size.width() > rect.right() + 1:
                x = rect.x(); y += height + self.spacing(); height = 0
            if place: item.setGeometry(QRect(x, y, size.width(), size.height()))
            x += size.width() + self.spacing(); height = max(height, size.height())
        return y + height - rect.y()


def actions(layout, items, call, primary=None):
    row = FlowActions(); buttons = []
    for title, fn in items:
        button = QPushButton(title); button.setAutoDefault(False); button.setAccessibleName(title.replace('&', ''))
        button.setProperty('role', 'primary' if title == primary else 'secondary')
        button.clicked.connect(lambda _=False, fn=fn: call(fn)); row.addWidget(button); buttons.append(button)
    layout.addLayout(row)
    return buttons


def label(text, widget=None):
    item = QLabel(text); item.setWordWrap(True)
    if widget is not None:
        item.setBuddy(widget); widget.setAccessibleName(text.replace('&', ''))
    return item


def scroll(widget):
    area = QScrollArea(); area.setWidgetResizable(True); area.setFrameShape(QScrollArea.NoFrame)
    area.setWidget(widget); return area


def table(headers, editable=False):
    widget = QTableWidget(0, len(headers)); widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed if editable else QAbstractItemView.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows); widget.setSelectionMode(QAbstractItemView.SingleSelection)
    widget.verticalHeader().hide()
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    widget.horizontalHeader().setDefaultSectionSize(150); widget.horizontalHeader().setStretchLastSection(True)
    widget.setMinimumHeight(120); widget.setAccessibleName(' · '.join(headers))
    return widget


def fill(widget, rows):
    widget.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            text = '—' if value is None else f'{value:.6g}' if isinstance(value, float) else str(value)
            item = QTableWidgetItem(text); item.setToolTip(text); widget.setItem(i, j, item)


def selection_actions(widget, buttons):
    def update():
        for button in buttons: button.setEnabled(bool(widget.selectedItems()))
    widget.itemSelectionChanged.connect(update); update()
