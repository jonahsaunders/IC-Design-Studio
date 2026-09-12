"""Native floating frames and an explicit diagonal resize grip for dock panels."""
from PySide6.QtCore import QObject, QEvent, QTimer, Qt, QSize
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QSizeGrip, QPushButton, QFrame


class PanelSizeGrip(QSizeGrip):
    """A consistent bottom-right drag without a platform modal resize loop."""
    def mousePressEvent(self, event):
        if event.button()!=Qt.LeftButton:return super().mousePressEvent(event)
        self._resize_origin=(event.globalPosition(),self.window().size());event.accept()

    def mouseMoveEvent(self, event):
        origin=getattr(self,'_resize_origin',None)
        if origin is None or not event.buttons()&Qt.LeftButton:return
        point,size=origin;delta=(event.globalPosition()-point).toPoint();window=self.window()
        minimum=window.minimumSize().expandedTo(window.minimumSizeHint())
        window.resize((size+QSize(delta.x(),delta.y())).expandedTo(minimum).boundedTo(window.maximumSize()))
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button()==Qt.LeftButton:self._resize_origin=None;event.accept()
        else:super().mouseReleaseEvent(event)

    def hideEvent(self, event):
        self._resize_origin=None;super().hideEvent(event)


class FloatingPanel(QObject):
    def __init__(self, dock, header):
        super().__init__(dock)
        self.dock = dock; self.header = header
        # X11/Wayland intentionally use Qt-drawn dock decorations. A separate
        # frame also paints reliably on platforms where QDockWidget skips its
        # own styled border in favor of the operating system's title bar.
        self.border = QFrame(dock); self.border.setObjectName('floatingPanelBorder')
        self.border.setAttribute(Qt.WA_TransparentForMouseEvents); self.border.hide()
        self.grip = PanelSizeGrip(dock); self.grip.setFixedSize(20, 20)
        self.grip.setAccessibleName('Resize floating panel')
        self.grip.setToolTip('Drag diagonally to resize this panel')
        self.grip.hide()
        self.dock_button = QPushButton('Dock', dock); self.dock_button.setFixedSize(58, 26)
        self.dock_button.setToolTip('Return this panel to the main window')
        self.dock_button.clicked.connect(lambda: dock.setFloating(False)); self.dock_button.hide()
        dock.installEventFilter(self)
        dock.topLevelChanged.connect(self.update_frame)
        QGuiApplication.instance().screenRemoved.connect(self.screen_removed)

    def screen_removed(self, *_):
        QTimer.singleShot(0,self.keep_visible)

    def keep_visible(self):
        from .window_geometry import keep_visible
        if self.dock.isFloating():keep_visible(self.dock)

    def update_frame(self, floating):
        if floating:
            self.header.hide(); self.dock.setTitleBarWidget(None)
        else:
            self.dock.setTitleBarWidget(self.header); self.header.show()
        self.dock.setProperty('floatingPanel', floating)
        self.dock.setContentsMargins(0, 0, 0, 30 if floating else 0)
        self.dock.style().unpolish(self.dock); self.dock.style().polish(self.dock)
        self.border.setVisible(floating)
        self.grip.setVisible(floating); self.dock_button.setVisible(floating); self.position_grip()

    def position_grip(self):
        self.border.setGeometry(self.dock.rect()); self.border.raise_()
        self.grip.move(self.dock.width()-self.grip.width()-2, self.dock.height()-self.grip.height()-2)
        self.grip.raise_()
        self.dock_button.move(self.dock.width()-self.grip.width()-self.dock_button.width()-6, self.dock.height()-28)
        self.dock_button.raise_()

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Resize, QEvent.Show): self.position_grip()
        if event.type()==QEvent.Show:QTimer.singleShot(0,self.keep_visible)
        return False
