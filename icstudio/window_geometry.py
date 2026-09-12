"""Keep restored window title bars reachable when display arrangements change."""
from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication


def reachable_geometry(rect, screens):
    if not screens:return QRect(rect)
    title=QRect(rect.x(),rect.y(),rect.width(),min(32,rect.height()))
    if any(title.intersected(screen).width()>=min(100,rect.width()) and
           title.intersected(screen).height()>=min(20,title.height()) for screen in screens):
        return QRect(rect)
    center=rect.center()
    target=min(screens,key=lambda s:abs(s.center().x()-center.x())+abs(s.center().y()-center.y()))
    width=min(rect.width(),target.width());height=min(rect.height(),target.height())
    x=max(target.left(),min(rect.x(),target.right()-width+1))
    y=max(target.top(),min(rect.y(),target.bottom()-height+1))
    return QRect(x,y,width,height)


def keep_visible(window):
    if not window.isWindow() or window.isMaximized() or window.isFullScreen():return
    rect=window.geometry();screens=[screen.availableGeometry() for screen in QGuiApplication.screens()]
    restored=reachable_geometry(rect,screens)
    if restored!=rect:window.setGeometry(restored)
