"""The Student Hub's illustrated world map and playable lesson routes."""
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QButtonGroup, QGridLayout, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from .ui_style import palette


# Color, map caption, and the shape traced into each world's circuit board.
WORLDS = {
    'foundations': ('#5989e4', 'First circuits & measurements', 'resistor'),
    'analog': ('#29ad91', 'Bias, gain & frequency response', 'wave'),
    'digital': ('#9376e6', 'Logic, timing & RTL', 'pulse'),
    'mixed': ('#e68b51', 'Sampling, conversion & timing', 'stairs'),
    'layout': ('#d86a94', 'Geometry, matching & verification', 'layout'),
    'career': ('#c1973f', 'Design briefs & interviews', 'portfolio'),
    'analog-projects': ('#3e9cbc', 'Amplifiers, references & debug', 'amp'),
    'testbenches': ('#578f79', 'Fixtures, simulation & measurements', 'wave'),
    'inverter': ('#779d45', 'Process models, DRC & LVS', 'inverter'),
    'capstone': ('#5b86c5', 'Sensor acquisition & calibration', 'system'),
}

TOPICS = {
    'foundations': (
        ('First circuits', 'f-first f-connect f-edit'),
        ('Design workflow', 'f-hierarchy f-debug f-portfolio'),
    ),
    'analog': (
        ('Signals & bandwidth', 'a-load a-bandwidth a-lc-bode'),
        ('Building amplifiers', 'a-bias a-differential a-amplifier a-layout'),
        ('Transistor sizing', 'a-gmid-bias a-gmid-size a-gmid-headroom a-gmid-tradeoff'),
    ),
    'digital': (
        ('Logic & state', 'd-logic d-counter d-pulse'),
        ('Arithmetic & interfaces', 'd-pwm d-average d-serial'),
        ('RTL debugging', 'd-latch d-saturation d-pipeline'),
    ),
    'mixed': (
        ('Sampling & quantization', 'm-bridge m-hold m-codes'),
        ('SAR converter debug', 'm-settling m-weight m-repeat'),
    ),
    'layout': (
        ('Geometry & routing', 'l-width l-spacing l-via'),
        ('Matching & parasitics', 'l-centroid l-layout-decisions'),
    ),
    'career': (('Design communication', 'p-spec p-review'),),
    'analog-projects': (
        ('Amplifiers & compensation', 'project-opamp project-tia project-miller project-ahuja'),
        ('Bias & voltage references', 'project-bias-reference project-cascode project-bandgap-widlar '
                                     'project-bandgap-brokaw project-bandgap-kuijk project-bandgap-banba'),
        ('Transistor design labs', 'interview-differential interview-input-pairs interview-gain '
                                   'interview-slew interview-noise interview-mismatch'),
        ('System design labs', 'interview-comparator interview-sar interview-ldo interview-post-layout-debug'),
    ),
    'inverter': (
        ('Process & simulation', 'process schematic dc transient'),
        ('Layout & handoff', 'layout drc lvs handoff'),
    ),
    'capstone': (
        ('Filter & conversion', 'c-filter c-sar'),
        ('Digital integration & signoff', 'c-average c-qualify'),
    ),
}

STATUS_MARKS = {
    'Ready to start': '◇', 'In progress': '◐', 'Completed': '✓',
    'Prerequisites needed': '–', 'PDK setup needed': '!',
}


def _label(text='', role='muted'):
    caption = QLabel(text)
    caption.setProperty('role', role)
    caption.setTextFormat(Qt.PlainText)
    caption.setWordWrap(True)
    caption.setAttribute(Qt.WA_TransparentForMouseEvents)
    return caption


def _poly(points):
    return QPolygonF([QPointF(x, y) for x, y in points])


def _trace(painter, points):
    painter.drawPolyline(_poly(points))


class WorldArtwork(QWidget):
    """An original isometric circuit tile, drawn at the display's native scale."""

    def __init__(self, accent, motif):
        super().__init__()
        self.accent = QColor(accent)
        self.motif = motif
        self.setFixedSize(104, 88)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(self.width() / 124, self.height() / 104)
        a = self.accent
        glow = QColor(a)
        glow.setAlpha(37)
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QRectF(6, 18, 112, 77))
        p.drawPolygon(_poly([(62, 17), (118, 47), (118, 62), (62, 92), (6, 62), (6, 47)]))
        p.setBrush(a.darker(245))
        p.drawPolygon(_poly([(10, 48), (62, 76), (62, 86), (10, 58)]))
        p.setBrush(a.darker(171))
        p.drawPolygon(_poly([(62, 76), (114, 48), (114, 58), (62, 86)]))
        ceramic = QLinearGradient(28, 13, 94, 78)
        ceramic.setColorAt(0, a.lighter(153))
        ceramic.setColorAt(0.52, a)
        ceramic.setColorAt(1, a.darker(148))
        p.setBrush(ceramic)
        p.setPen(QPen(a.lighter(164), 1))
        p.drawPolygon(_poly([(62, 20), (114, 48), (62, 76), (10, 48)]))

        # The face is a flat circuit board viewed in an isometric projection.
        p.translate(62, 20)
        p.shear(-1 / 0.54, 0.54)
        p.setPen(QPen(a.darker(138), 0.8))
        p.setBrush(Qt.NoBrush)
        for offset in (7, 13, 19, 25, 31, 37, 43):
            _trace(p, [(3, offset * 0.54), (49, offset * 0.54)])
            _trace(p, [(offset, 1.6), (offset, 26.4)])
        p.setPen(QPen(a.lighter(164), 1.2))
        for route in ([(2, 8), (10, 8), (10, 12), (14, 12)],
                      [(2, 20), (9, 20), (9, 17), (14, 17)],
                      [(38, 12), (43, 12), (43, 8), (50, 8)],
                      [(38, 17), (46, 17), (46, 20), (50, 20)]):
            _trace(p, route)
            x, y = route[0] if route[0][0] == 2 else route[-1]
            p.drawEllipse(QPointF(x, y), 1.4, 1.1)

        p.setPen(QPen(a.lighter(154), 1))
        p.setBrush(a.darker(222))
        p.drawRoundedRect(QRectF(12, 6, 28, 16), 2, 2)
        p.setPen(QPen(a.lighter(187), 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        motif = {
            'resistor': [(15, 14), (19, 14), (21, 10), (24, 18), (27, 10), (30, 18), (33, 14), (37, 14)],
            'wave': [(15, 14), (18, 12), (21, 9), (24, 11), (27, 16), (30, 19), (33, 17), (37, 14)],
            'pulse': [(15, 17), (19, 17), (19, 11), (26, 11), (26, 17), (32, 17), (32, 11), (37, 11)],
            'stairs': [(15, 18), (20, 18), (20, 15), (26, 15), (26, 12), (32, 12), (32, 9), (37, 9)],
            'layout': [(16, 17), (16, 10), (32, 10), (32, 17), (21, 17), (21, 13), (37, 13), (37, 18)],
            'portfolio': [(19, 9), (32, 9), (32, 19), (19, 19), (19, 9), (19, 12), (32, 12)],
            'amp': [(16, 14), (21, 14), (21, 9), (32, 14), (21, 19), (21, 14), (32, 14), (37, 14)],
            'inverter': [(16, 14), (20, 14), (20, 9), (30, 14), (20, 19), (20, 14)],
            'system': [(15, 14), (20, 14), (20, 10), (26, 10), (26, 18), (32, 18), (32, 14), (37, 14)],
        }[self.motif]
        _trace(p, motif)
        if self.motif == 'inverter':
            p.drawEllipse(QPointF(32, 14), 1.7, 1.5)
            _trace(p, [(34, 14), (37, 14)])
        p.end()


class _Tile(QPushButton):
    """A native button whose wrapped caption participates in Qt layout."""

    def __init__(self):
        super().__init__()
        self.setAutoDefault(False)
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def sizeHint(self):
        layout = self.layout()
        return layout.sizeHint() if layout else super().sizeHint()

    def minimumSizeHint(self):
        layout = self.layout()
        return layout.minimumSize() if layout else super().minimumSizeHint()

    def heightForWidth(self, width):
        layout = self.layout()
        return layout.totalHeightForWidth(width) if layout else -1


class WorldCard(_Tile):
    def __init__(self, key, title):
        super().__init__()
        self.title = title
        self.accent, description, motif = WORLDS.get(key, ('#5989e4', '', 'system'))
        self.setProperty('role', 'worldCard')
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 10, 14, 10)
        row.setSpacing(8)
        row.addWidget(WorldArtwork(self.accent, motif))
        column = QVBoxLayout()
        column.setSpacing(4)
        row.addLayout(column, 1)
        column.addWidget(_label(title, 'worldTitle'))
        if description:
            column.addWidget(_label(description))
        self.count = _label('', 'worldCount')
        column.addWidget(self.count)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setAccessibleName(f'{title} completion')
        self.progress.setAttribute(Qt.WA_TransparentForMouseEvents)
        column.addWidget(self.progress)

    def set_progress(self, done, total, status):
        count = f'{done} / {total} complete' if total else status
        if total and done == total:
            count = f'✓ {count}'
        elif total and status in ('Prerequisites needed', 'PDK setup needed'):
            count = f'{count} · {status}'
        self.count.setText(count)
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self.progress.setFormat(f'{done} of {total} lessons complete')
        self.setAccessibleName(self.title)
        self.setAccessibleDescription(count)
        self.setToolTip(status)

    def set_theme(self, dark):
        t = palette(dark)
        self.setStyleSheet(f'QPushButton[role="worldCard"] {{background:{t["panel"]};}}'
                           f'QPushButton[role="worldCard"]:hover {{background:{t["hover"]};}}'
                           f'QPushButton[role="worldCard"]:pressed {{background:{t["tint"]};}}'
                           f'QProgressBar::chunk {{background:{self.accent};}}')


class WorldMap(QWidget):
    world_opened = Signal(str)
    card_focused = Signal(QWidget)

    def __init__(self, titles):
        super().__init__()
        self.setAccessibleName('Circuit design world map')
        self.cards = {}
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(18, 18, 18, 18)
        self.grid.setSpacing(18)
        self.grid.setAlignment(Qt.AlignTop)
        for key, title in titles.items():
            card = WorldCard(key, title)
            card.clicked.connect(lambda checked=False, key=key: self.world_opened.emit(key))
            card.installEventFilter(self)
            self.cards[key] = card
        self.columns = 0
        self.set_theme(False, 100)

    def set_theme(self, dark, scale):
        self.dark, self.scale = dark, scale
        for card in self.cards.values():
            card.set_theme(dark)
        self.reflow()
        self.update()

    def reflow(self):
        # This uses the viewport width and grows with the Hub's text-size setting.
        preferred = 142 + round(128 * self.scale / 100)
        columns = max(1, min(3, (self.width() - 18) // (preferred + 18)))
        if columns == self.columns:
            return
        self.columns = columns
        for column in range(3):
            self.grid.setColumnStretch(column, int(column < columns))
        for i, card in enumerate(self.cards.values()):
            self.grid.removeWidget(card)
            self.grid.addWidget(card, *divmod(i, columns))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def eventFilter(self, card, event):
        if event.type() == QEvent.FocusIn:
            self.card_focused.emit(card)
        if event.type() != QEvent.KeyPress or event.modifiers() & ~Qt.KeypadModifier:
            return super().eventFilter(card, event)
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            card.click()
            return True
        if key not in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_Home, Qt.Key_End):
            return super().eventFilter(card, event)
        cards = list(self.cards.values())
        index = cards.index(card)
        column = index % self.columns
        if key == Qt.Key_Home:
            target = 0
        elif key == Qt.Key_End:
            target = len(cards) - 1
        elif key in (Qt.Key_Up, Qt.Key_Down):
            target = index + (self.columns if key == Qt.Key_Down else -self.columns)
        else:
            move = 1 if key == Qt.Key_Right else -1
            if self.layoutDirection() == Qt.RightToLeft:
                move = -move
            target = index + move if 0 <= column + move < self.columns else index
        if 0 <= target < len(cards):
            cards[target].setFocus(Qt.ShortcutFocusReason)
        return True

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        surface = QLinearGradient(0, 0, self.width(), self.height())
        surface.setColorAt(0, QColor('#101b2a' if self.dark else '#eaf0f9'))
        surface.setColorAt(1, QColor('#17202d' if self.dark else '#f4f7fc'))
        p.setBrush(surface)
        p.setPen(QPen(QColor('#314156' if self.dark else '#d9e3f0'), 1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 15, 15)
        p.setPen(QColor('#2a3a50' if self.dark else '#cfdbec'))
        for y in range(14, self.height() - 8, 16):
            for x in range(14, self.width() - 8, 16):
                p.drawPoint(x, y)
        neutral = QColor('#4b6586' if self.dark else '#a6bad7')
        cards = list(self.cards.values())
        for i, card in enumerate(cards[:-1]):
            rect = card.geometry()
            lit = card.progress.value() == card.progress.maximum()
            signal = QColor(card.accent) if lit else neutral
            p.setPen(QPen(signal, 1.4))
            p.setBrush(surface)
            if (i + 1) % self.columns:
                y = rect.center().y()
                end = cards[i + 1].x()
                p.drawLine(rect.right(), y, end, y)
                p.drawEllipse(QPointF((rect.right() + end) / 2, y), 2.5, 2.5)
            if i + self.columns < len(cards):
                x = rect.center().x()
                end = cards[i + self.columns].y()
                p.drawLine(x, rect.bottom(), x, end)
                p.drawEllipse(QPointF(x, (rect.bottom() + end) / 2), 2.5, 2.5)
        p.end()


class LessonTrail(QScrollArea):
    lesson_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setAccessibleName('World topics and lessons')
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMinimumHeight(195)
        self.snapshot = None
        self.rows = {}

    def set_lessons(self, world, lessons, status_filter):
        snapshot = world, status_filter, tuple((lesson['id'], status, count) for lesson, status, count in lessons)
        if snapshot == self.snapshot:
            return
        same_world = self.snapshot is not None and world == self.snapshot[0]
        focused = next((key for key, row in self.rows.items() if row.hasFocus()), None)
        scroll = self.verticalScrollBar().value() if same_world else 0
        self.snapshot = snapshot
        self.rows = {}
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(12)
        group = QButtonGroup(body)
        topics = TOPICS.get(world, ())
        groups = {title: [] for title, _ in topics}
        names = {key: title for title, ids in topics for key in ids.split()}
        for lesson, status, count in lessons:
            topic = lesson.get('layout_topic') or lesson.get('topic') or names.get(lesson.get('inverter_stage', lesson['id']),
                                                            'More lessons' if topics else 'Lessons')
            groups.setdefault(topic, []).append((lesson, status, count))
        for topic, items in groups.items():
            visible = [item for item in items if not status_filter or item[1] == status_filter]
            if not visible:
                continue
            done = sum(status == 'Completed' for _, status, _ in items)
            layout.addWidget(_label(f'{topic}  ·  {done}/{len(items)}', 'subtitle'))
            route = QWidget()
            route.setProperty('role', 'lessonRoute')
            route_layout = QVBoxLayout(route)
            route_layout.setContentsMargins(10, 0, 0, 0)
            route_layout.setSpacing(6)
            layout.addWidget(route)
            for lesson, status, count in visible:
                key = lesson['id']
                row = _Tile()
                row.setCheckable(True)
                row.setProperty('role', 'trailLesson')
                row.setAccessibleName(lesson['title'])
                description = f'{status} · {count}/{len(lesson["steps"])} steps · {lesson["minutes"]} min'
                row.setAccessibleDescription(description)
                row.clicked.connect(lambda checked=False, key=key: self.lesson_selected.emit(key))
                group.addButton(row)
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(10, 8, 10, 8)
                marker = _label(STATUS_MARKS[status], 'trailMark')
                marker.setProperty('done', status == 'Completed')
                marker.setAlignment(Qt.AlignCenter)
                row_layout.addWidget(marker, 0, Qt.AlignVCenter)
                text = QVBoxLayout()
                text.setSpacing(2)
                text.addWidget(_label(lesson['title'], 'trailTitle'))
                text.addWidget(_label(description))
                row_layout.addLayout(text, 1)
                route_layout.addWidget(row)
                self.rows[key] = row
        if not self.rows:
            layout.addWidget(_label('No matching lessons.' if status_filter else
                                    'No lessons are available for this selection.'))
        layout.addStretch()
        self.setWidget(body)
        self.verticalScrollBar().setValue(scroll)
        if focused in self.rows:
            self.rows[focused].setFocus()

    def select(self, key):
        row = self.rows.get(key)
        if row and not row.isChecked():
            row.setChecked(True)
            self.ensureWidgetVisible(row, 0, 8)
