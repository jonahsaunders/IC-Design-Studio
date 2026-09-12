"""Local component shortcuts; identities include the originating library."""
import json
from hashlib import sha256
from PySide6.QtCore import QObject, QEvent, Qt


class ComponentPreferences:
    def __init__(self, settings, scope):
        self.settings = settings
        self.key = 'components/' + sha256(scope.encode()).hexdigest()
        try:
            state = json.loads(settings.value(self.key, '{}'))
            self.favorites = set(state.get('favorites', []))
            self.recent = list(dict.fromkeys(state.get('recent', [])))[:30]
            self.source = state.get('source')
        except (ValueError, TypeError, AttributeError):
            self.favorites, self.recent, self.source = set(), [], None

    @staticmethod
    def identity(source, key):
        return sha256(json.dumps([source, key], sort_keys=True).encode()).hexdigest()

    def save(self):
        self.settings.setValue(self.key, json.dumps(dict(
            favorites=sorted(self.favorites), recent=self.recent, source=self.source)))

    def toggle(self, key):
        if key in self.favorites: self.favorites.remove(key)
        else: self.favorites.add(key)
        self.save()

    def used(self, key):
        self.recent = [key] + [item for item in self.recent if item != key][:29]
        self.save()

    def matches(self, key, mode):
        return mode == 'All components' or key in (self.favorites if mode == 'Favorites' else self.recent)


class ComponentKeys(QObject):
    """Keep focus in search while moving through visible, selectable results."""
    def __init__(self, search, listing, place, prepare=lambda:None):
        super().__init__(search)
        self.listing, self.place = listing, place
        self.prepare=prepare
        search.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Down, Qt.Key_Up):
                self.prepare()
                items = [self.listing.item(i) for i in range(self.listing.count())
                         if not self.listing.item(i).isHidden()]
                current = self.listing.currentItem()
                if items:
                    index = items.index(current) if current in items else -1
                    index = max(0, min(len(items)-1, index + (1 if key == Qt.Key_Down else -1)))
                    self.listing.setCurrentItem(items[index]); self.listing.scrollToItem(items[index])
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self.place(); return True
        return super().eventFilter(obj, event)
