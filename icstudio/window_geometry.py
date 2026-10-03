"""Keep restored windows reachable on the current logical display size."""
from PySide6.QtCore import QRect, QSize, QObject, QTimer, QEvent
from PySide6.QtGui import QGuiApplication


def reachable_geometry(rect, screens):
    if not screens:return QRect(rect)
    title=QRect(rect.x(),rect.y(),rect.width(),min(32,rect.height()))
    visible=[screen for screen in screens if title.intersected(screen).width()>=min(100,rect.width()) and
             title.intersected(screen).height()>=min(20,title.height())]
    if visible:
        target=max(visible,key=lambda screen:title.intersected(screen).width())
        # A reachable title does not make an oversized high-DPI window usable.
        if rect.width()<=target.width() and rect.height()<=target.height():return QRect(rect)
    else:
        center=rect.center()
        target=min(screens,key=lambda s:abs(s.center().x()-center.x())+abs(s.center().y()-center.y()))
    width=min(rect.width(),target.width());height=min(rect.height(),target.height())
    x=max(target.left(),min(rect.x(),target.right()-width+1))
    y=max(target.top(),min(rect.y(),target.bottom()-height+1))
    return QRect(x,y,width,height)


class DisplayGeometryObserver(QObject):
    """Re-fit a workspace when DPI or the monitor's available area changes."""
    def __init__(self,window):
        super().__init__(window);self.window=window;self.handle=None
        window.installEventFilter(self)
        app=QGuiApplication.instance()
        for screen in app.screens():self.watch(screen)
        app.screenAdded.connect(self.watch)

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Show:
            handle=self.window.windowHandle()
            if handle is not None and handle is not self.handle:
                handle.screenChanged.connect(self.schedule);self.handle=handle
            self.schedule()
        return False

    def watch(self,screen):
        screen.availableGeometryChanged.connect(self.schedule)

    def schedule(self,*_):
        QTimer.singleShot(0,self.fit)

    def fit(self):keep_visible(self.window)


def initialize_workspace_geometry(window, minimum=QSize(1000,680), size=QSize(1440,900)):
    """Use logical screen dimensions, including the taskbar and window frame."""
    window._workspace_minimum_size=QSize(minimum)
    window.setMinimumSize(minimum);window.resize(size)
    keep_visible(window)
    window._display_geometry_observer=DisplayGeometryObserver(window)


def keep_visible(window):
    if not window.isWindow() or window.isMaximized() or window.isFullScreen():return
    rect=window.frameGeometry();screens=[screen.availableGeometry() for screen in QGuiApplication.screens()]
    restored=reachable_geometry(rect,screens)
    content=window.geometry();left=content.x()-rect.x();top=content.y()-rect.y()
    frame_width=rect.width()-content.width();frame_height=rect.height()-content.height()
    if hasattr(window,'_workspace_minimum_size') and screens:
        target=max(screens,key=lambda screen:restored.intersected(screen).width()*restored.intersected(screen).height())
        minimum=window._workspace_minimum_size
        window.setMinimumSize(min(minimum.width(),max(1,target.width()-frame_width)),
                              min(minimum.height(),max(1,target.height()-frame_height)))
    if restored!=rect:
        window.setGeometry(restored.x()+left,restored.y()+top,
                           max(1,restored.width()-frame_width),max(1,restored.height()-frame_height))
