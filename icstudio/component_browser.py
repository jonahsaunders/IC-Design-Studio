"""Source-filtered component choices with the same vector artwork as the canvas."""
from PySide6.QtCore import Qt, QPointF, QRectF, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QFormLayout, QComboBox, QLineEdit, QListWidget, QListWidgetItem, QLabel,
    QPushButton, QDialogButtonBox, QSplitter)

from .ui_style import palette




class SymbolPreview(QWidget):
    def __init__(self, dark=False, parent=None):
        super().__init__(parent)
        self.dark = dark; self.symbol = None; self.context = {}
        self.setMinimumSize(180, 120)
        self.setAccessibleName('Selected component symbol preview')

    def set_symbol(self, symbol=None, context=None):
        self.symbol = symbol; self.context = context or {}; self.update()

    def paintEvent(self, event):
        from .symbol_geometry import draw
        colors = palette(self.dark); painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.fillRect(self.rect(), QColor(colors['canvas']))
            painter.setPen(QColor(colors['line']))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
            if not self.symbol:
                painter.setPen(QColor(colors['muted']))
                painter.drawText(self.rect().adjusted(10, 10, -10, -10), Qt.AlignCenter | Qt.TextWordWrap, 'Select a component to preview its symbol')
                return
            # Instance annotations (names, net voltages, Xschem pin expressions)
            # are not part of the symbol geometry and often require a live run.
            # Keep them out of the placement preview without editing the symbol.
            primitives = [item for item in self.symbol.get('primitives', [])
                          if item['kind'] != 'text' or '@' not in item.get('text', '')]
            artwork = {**self.symbol, 'primitives': primitives}
            points = list(self.symbol.get('pins', {}).values())
            points += [p for item in primitives for p in item['points']]
            if not points: return
            xs, ys = zip(*points)
            width, height = max(40, max(xs)-min(xs)), max(40, max(ys)-min(ys))
            box = QRectF((min(xs)+max(xs)-width)/2, (min(ys)+max(ys)-height)/2, width, height)
            scale = min((self.width()-70)/box.width(), (self.height()-50)/box.height(), 3)
            painter.translate(self.width()/2, self.height()/2)
            painter.scale(scale, scale); painter.translate(-box.center())
            draw(painter, artwork, colors['text'], self.context)
            pen = QPen(QColor(colors['accent']), 1); pen.setCosmetic(True); painter.setPen(pen)
            for point in self.symbol.get('pins', {}).values():
                painter.drawEllipse(QPointF(*point), 2.5/scale, 2.5/scale)
        finally:
            painter.end()


class ComponentBrowser(QDialog):
    """Entries provide label/source/key plus a lazy symbol loader and a placer."""
    def __init__(self, studio, title, entries, preview, place, scope='symbols'):
        super().__init__(studio)
        self.studio = studio; self.entries = entries; self.preview_loader = preview; self.placer = place
        from .component_preferences import ComponentPreferences, ComponentKeys
        self.preferences = ComponentPreferences(studio.settings, scope)
        self.identities = [ComponentPreferences.identity(e['source'], e.get('key', e['label'])) for e in entries]
        self.search_text = [(e['label']+' '+e['source']).casefold() for e in entries]
        self.preview_cache = {}
        self.setWindowTitle(title); self.resize(820, 560); self.setWindowModality(Qt.WindowModal)
        root = QVBoxLayout(self)
        self.source = QComboBox(); self.source.setAccessibleName('Component source library')
        self.source.addItem('All sources', None)
        for source in sorted({e['source'] for e in entries}, key=str.casefold): self.source.addItem(source, source)
        self.source.setCurrentIndex(max(0, self.source.findData(self.preferences.source)))
        form = QFormLayout(); form.addRow('Source / library', self.source); root.addLayout(form)
        self.search = QLineEdit(); self.search.setPlaceholderText('Search components in this source…')
        self.search.setAccessibleName('Search components'); self.search.setClearButtonEnabled(True); root.addWidget(self.search)
        shortcuts = QHBoxLayout(); root.addLayout(shortcuts)
        self.collection = QComboBox(); self.collection.addItems(['All components', 'Favorites', 'Recently placed'])
        self.collection.setAccessibleName('Component collection'); shortcuts.addWidget(self.collection, 1)
        self.favorite = QPushButton('Add to favorites'); shortcuts.addWidget(self.favorite)
        self.favorite.clicked.connect(self.toggle_favorite)
        split = QSplitter(Qt.Horizontal); root.addWidget(split, 1)
        self.listing = QListWidget(); self.listing.setAccessibleName('Available components'); split.addWidget(self.listing)
        self.listing.setUniformItemSizes(True)
        right = QWidget(); detail = QVBoxLayout(right); detail.setContentsMargins(8, 0, 0, 0)
        self.preview = SymbolPreview(studio.dark); detail.addWidget(self.preview, 1)
        self.detail = QLabel(); self.detail.setWordWrap(True); self.detail.setTextFormat(Qt.PlainText); detail.addWidget(self.detail)
        split.addWidget(right); split.setSizes([410, 330])
        self.status = QLabel(); self.status.setWordWrap(True); root.addWidget(self.status)
        self.extra = QHBoxLayout(); root.addLayout(self.extra)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.place_button = buttons.addButton('Place selected', QDialogButtonBox.AcceptRole)
        self.place_button.setDefault(True); buttons.accepted.connect(self.place_selected); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        for i, entry in enumerate(entries):
            item = QListWidgetItem(entry['label']+'  ·  '+entry['source']); item.setData(Qt.UserRole, i)
            self.listing.addItem(item)
        self.filter_timer = QTimer(self); self.filter_timer.setSingleShot(True); self.filter_timer.setInterval(60)
        self.filter_timer.timeout.connect(self.filter)
        self.source.currentIndexChanged.connect(self.source_changed)
        self.collection.currentIndexChanged.connect(self.filter)
        self.search.textChanged.connect(self.schedule_filter)
        self.keys = ComponentKeys(self.search, self.listing, self.place_selected,
                                  lambda:self.filter() if self.filter_timer.isActive() else None)
        self.listing.currentItemChanged.connect(self.show_preview)
        self.listing.itemDoubleClicked.connect(lambda _: self.place_selected())
        self.filter(); self.search.setFocus()

    def source_changed(self, *_):
        self.preferences.source = self.source.currentData(); self.preferences.save(); self.filter()

    def schedule_filter(self, *_):
        if len(self.entries) < 1000: self.filter()
        else:
            # Do not allow Enter to place a result from the previous query.
            self.place_button.setEnabled(False); self.filter_timer.start()

    def toggle_favorite(self):
        entry = self.selected_entry()
        if entry:
            self.preferences.toggle(self.identities[self.listing.currentItem().data(Qt.UserRole)])
            self.filter()

    def selected_entry(self):
        item = self.listing.currentItem()
        return self.entries[item.data(Qt.UserRole)] if item and not item.isHidden() else None

    def filter(self, *_):
        self.filter_timer.stop()
        query = self.search.text().casefold().split(); source = self.source.currentData(); visible = []
        mode = self.collection.currentText()
        self.listing.setUpdatesEnabled(False)
        for i, entry in enumerate(self.entries):
            item = self.listing.item(i)
            match = ((source is None or entry['source'] == source) and all(word in self.search_text[i] for word in query)
                     and self.preferences.matches(self.identities[i], mode))
            if item.isHidden() == match: item.setHidden(not match)
            if match: visible.append(item)
        self.listing.setUpdatesEnabled(True)
        current = self.listing.currentItem()
        self.listing.setCurrentItem(current if current in visible else visible[0] if visible else None)
        self.status.setText(f'{len(visible)} component'+('s' if len(visible)!=1 else '') if visible else 'No matching components. Choose another source or clear the search.')
        self.show_preview()

    def show_preview(self, *_):
        entry = self.selected_entry(); self.preview.set_symbol(); self.place_button.setEnabled(bool(entry)); self.detail.clear()
        self.favorite.setEnabled(bool(entry))
        if entry:
            key = self.identities[self.listing.currentItem().data(Qt.UserRole)]
            self.favorite.setText('Remove favorite' if key in self.preferences.favorites else 'Add to favorites')
            try:
                if key not in self.preview_cache:
                    self.preview_cache[key] = self.preview_loader(entry)
                    if len(self.preview_cache) > 128: self.preview_cache.pop(next(iter(self.preview_cache)))
                symbol, context = self.preview_cache[key]
                self.preview.set_symbol(symbol, context)
                self.detail.setText(entry['label']+'\n'+entry['source']+'\nTerminals: '+', '.join(symbol.get('pin_order', symbol.get('pins', {}))))
            except (ValueError, KeyError, OSError) as exc:
                self.detail.setText('Preview unavailable: '+str(exc))

    def place_selected(self):
        if self.filter_timer.isActive(): self.filter()
        entry = self.selected_entry()
        if not entry: return
        try:
            if self.placer(entry) is not False:
                self.preferences.used(self.identities[self.listing.currentItem().data(Qt.UserRole)])
                self.accept()
        except (ValueError, KeyError, OSError) as exc: self.status.setText(str(exc))

    def add_button(self, text, callback):
        button = QPushButton(text); button.clicked.connect(callback); self.extra.addWidget(button); return button
