"""Shared desktop design tokens and original, resolution-independent icons."""
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

LIGHT = dict(bg='#f4f5f7', panel='#ffffff', canvas='#fbfcfe', text='#222a38', muted='#606c7e', line='#dde2e9', hover='#edf0f5', accent='#345fd1', tint='#e9efff', grid='#dce3ef', field='#ffffff', disabled='#8b94a3')
DARK = dict(bg='#1a1f27', panel='#21262f', canvas='#131820', text='#e8edf5', muted='#abb6c7', line='#323b49', hover='#2a3341', accent='#91afff', tint='#283a59', grid='#232c3a', field='#191e27', disabled='#7f8b9e')

def palette(dark=False): return DARK if dark else LIGHT

def icon(name, color='#606c7e', size=20):
    pix = QPixmap(size*2, size*2); pix.fill(Qt.transparent)
    p = QPainter(pix); p.setRenderHint(QPainter.Antialiasing); p.scale(size/12, size/12)
    pen = QPen(QColor(color), 1.25 if name in ('resistor','capacitor','voltage','current','inductor') else 1.65); pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen); p.setBrush(Qt.NoBrush)
    def line(*v): p.drawLine(QPointF(*v[:2]), QPointF(*v[2:]))
    def poly(points): p.drawPolyline(QPolygonF([QPointF(*x) for x in points]))
    if name=='select': poly([(5,3),(6,20),(10,15),(14,21),(17,19),(13,13),(20,12),(5,3)])
    elif name=='wire':
        poly([(4,6),(11,6),(11,18),(20,18)]);p.drawEllipse(QPointF(4,6),2,2);p.drawEllipse(QPointF(20,18),2,2)
    elif name in ('chip','cell'):
        p.drawRoundedRect(QRectF(6,6,12,12),2,2)
        for n in (9,15):line(n,2,n,6);line(n,18,n,22);line(2,n,6,n);line(18,n,22,n)
        if name=='chip':p.drawRect(QRectF(10,10,4,4))
    elif name=='plus':line(12,5,12,19);line(5,12,19,12)
    elif name=='close':line(6,6,18,18);line(18,6,6,18)
    elif name=='search':p.drawEllipse(QRectF(4,3,12,12));line(15,14,21,20)
    elif name=='play':p.setBrush(QColor(color));p.drawPolygon(QPolygonF([QPointF(7,4),QPointF(20,12),QPointF(7,20)]))
    elif name=='stop':p.drawRoundedRect(QRectF(6,6,12,12),2,2)
    elif name in ('undo','redo'):
        if name=='redo':p.translate(24,0);p.scale(-1,1)
        poly([(8,5),(3,10),(8,15)]);p.drawArc(QRectF(4,9,16,12),0,170*16)
    elif name=='save':poly([(5,3),(18,3),(21,6),(21,21),(3,21),(3,3),(5,3)]);p.drawRect(QRectF(7,3,9,6));p.drawRect(QRectF(7,14,10,7))
    elif name in ('sidebar','inspector','split'):
        p.drawRoundedRect(QRectF(3,4,18,16),2,2);line(9 if name=='sidebar' else 15 if name=='inspector' else 12,4,9 if name=='sidebar' else 15 if name=='inspector' else 12,20)
    elif name=='fit':
        for points in [[(3,9),(3,3),(9,3)],[(15,3),(21,3),(21,9)],[(21,15),(21,21),(15,21)],[(9,21),(3,21),(3,15)]]:poly(points)
    elif name=='rect':p.drawRect(QRectF(4,5,16,14))
    elif name=='polygon':poly([(4,7),(14,3),(21,11),(17,20),(5,18),(4,7)])
    elif name=='path':poly([(3,18),(9,18),(9,6),(20,6)])
    elif name=='grid':
        p.drawRect(QRectF(3,3,18,18))
        for n in (9,15):line(n,3,n,21);line(3,n,21,n)
    elif name=='label':poly([(3,7),(15,7),(21,12),(15,17),(3,17),(3,7)]);line(7,10,12,10);line(7,14,12,14)
    elif name=='ground':line(12,3,12,11);line(4,11,20,11);line(7,15,17,15);line(10,19,14,19)
    elif name=='move':
        line(12,3,12,21);line(3,12,21,12)
        for points in [[(9,6),(12,3),(15,6)],[(9,18),(12,21),(15,18)],[(6,9),(3,12),(6,15)],[(18,9),(21,12),(18,15)]]:poly(points)
    elif name=='copy':p.drawRoundedRect(QRectF(8,8,13,13),1,1);poly([(16,5),(16,3),(3,3),(3,16),(5,16)])
    elif name=='stretch':p.drawRect(QRectF(5,5,14,14));line(2,12,22,12);poly([(18,9),(22,12),(18,15)])
    elif name=='mirror':
        line(12,2,12,22);poly([(3,6),(9,12),(3,18),(3,6)]);poly([(21,6),(15,12),(21,18),(21,6)])
    elif name=='cut':
        p.drawEllipse(QRectF(3,15,6,6));p.drawEllipse(QRectF(15,15,6,6));line(6,16,18,3);line(18,16,6,3)
    elif name=='via':p.drawRect(QRectF(4,4,16,16));p.drawEllipse(QRectF(8,8,8,8))
    elif name=='vertex':poly([(4,19),(8,6),(20,10)]);p.drawRect(QRectF(5,3,6,6))
    elif name=='align':line(3,3,3,21);p.drawRect(QRectF(6,5,14,5));p.drawRect(QRectF(6,14,9,5))
    elif name=='float':poly([(9,3),(21,3),(21,15)]);line(21,3,10,14);poly([(6,6),(3,6),(3,21),(18,21),(18,18)])
    elif name=='ruler':
        p.drawRect(QRectF(3,7,18,10))
        for x in (7,11,15,19):line(x,7,x,11)
    elif name=='layers':
        poly([(3,9),(12,4),(21,9),(12,14),(3,9)]);poly([(3,13),(12,18),(21,13)]);poly([(3,17),(12,22),(21,17)])
    elif name=='wave':poly([(2,12),(6,12),(9,4),(14,20),(18,10),(22,10)])
    elif name=='check':poly([(4,12),(9,17),(20,6)])
    elif name=='settings':
        for y,x in [(5,8),(12,16),(19,9)]:line(3,y,21,y);p.setBrush(QColor(color));p.drawEllipse(QPointF(x,y),2,2)
    elif name=='folder':poly([(3,7),(3,4),(10,4),(12,7),(21,7),(21,20),(3,20),(3,7)])
    elif name=='document':poly([(5,3),(14,3),(20,9),(20,21),(5,21),(5,3)]);poly([(14,3),(14,9),(20,9)]);line(9,14,16,14);line(9,17,16,17)
    elif name=='chevron':poly([(8,5),(15,12),(8,19)])
    elif name=='resistor':poly([(2,12),(6,12),(7,9),(9,15),(11,9),(13,15),(15,9),(17,15),(18,12),(22,12)])
    elif name=='capacitor':line(2,12,10,12);line(10,7,10,17);line(14,7,14,17);line(14,12,22,12)
    elif name=='voltage':p.drawEllipse(QRectF(6,6,12,12));line(12,2,12,6);line(12,18,12,22);line(10,10,14,10);line(12,8,12,12);line(10,14.5,14,14.5)
    elif name=='inductor':
        from PySide6.QtGui import QPainterPath
        line(2,12,6,12);line(18,12,22,12);path=QPainterPath(QPointF(6,12))
        for x in (6,9,12,15):path.cubicTo(x,7,x+3,7,x+3,12)
        p.drawPath(path)
    elif name=='current':
        p.drawEllipse(QRectF(6,6,12,12));line(12,2,12,6);line(12,18,12,22);line(12,8,12,16);poly([(9.5,13),(12,16),(14.5,13)])
    elif name=='rotate':
        p.drawArc(QRectF(4,4,16,16),30*16,285*16);poly([(17,3),(20,8),(14,8)])
    elif name=='source':p.drawEllipse(QRectF(5,5,14,14));line(12,1,12,5);line(12,19,12,23);line(9,10,15,10);line(12,7,12,13);line(10,16,14,16)
    else:p.drawEllipse(QRectF(5,5,14,14))
    p.end();pix.setDevicePixelRatio(2);return QIcon(pix)

def stylesheet(dark=False):
    t=dict(palette(dark));t['error']='#ff929f' if dark else '#bc2940';t['arrow']=(Path(__file__).parent/'assets'/('chevron-dark.svg' if dark else 'chevron-light.svg')).as_posix();t['check']=(Path(__file__).parent/'assets'/'check.svg').as_posix()
    return '''
    QWidget { color: %(text)s; font-family: "Inter", "Segoe UI", "DejaVu Sans"; font-size: 13px; }
    QMainWindow, QDialog { background: %(panel)s; }
    QLabel { background: transparent; }
    QLabel[role="muted"] { color: %(muted)s; }
    QLabel[role="section"] { color: %(muted)s; font-size: 11px; font-weight: 600; padding: 8px 0px; }
    QLabel[role="title"] { font-size: 20px; font-weight: 600; }
    QLabel[role="subtitle"] { font-size: 14px; font-weight: 600; }
    QLabel[role="error"] { color: %(error)s; padding: 6px 0; }
    QLabel[role="badge"] { color: %(accent)s; background: %(tint)s; padding: 4px 8px; border-radius: 4px; font-size: 11px; }
    QWidget#sidebarBody, QWidget#toolStrip, QWidget#documentBar, QWidget#canvasFooter { background: %(bg)s; }
    QWidget#documentBar { border-bottom: 1px solid %(line)s; }
    QWidget#toolStrip { border-bottom: 1px solid %(line)s; }
    QWidget#panelHeader { background: %(panel)s; border-bottom: 1px solid %(line)s; }
    QToolBar { background: %(panel)s; border: 0; border-bottom: 1px solid %(line)s; spacing: 6px; padding: 8px 12px; }
    QMenuBar { background: %(panel)s; padding: 3px 8px; border: 0; }
    QMenuBar::item { padding: 3px 9px; background: transparent; }
    QMenuBar::item:selected { background: %(hover)s; border-radius: 4px; }
    QMenu { background: %(panel)s; padding: 5px; border: 1px solid %(line)s; }
    QMenu::item { padding: 8px 30px 8px 12px; border-radius: 4px; }
    QMenu::item:selected { background: %(tint)s; color: %(accent)s; }
    QMenu::separator { height: 1px; background: %(line)s; margin: 5px; }
    QTabWidget#taskRibbon { background: %(bg)s; }
    QTabWidget#taskRibbon::pane { background: %(bg)s; border-bottom: 1px solid %(line)s; }
    QTabWidget#taskRibbon QTabBar::tab { padding: 5px 18px; font-size: 12px; }
    QToolButton#taskButton { padding: 5px 8px; border: 1px solid transparent; border-radius: 5px; font-size: 12px; }
    QToolButton#taskButton:hover { border-color: %(line)s; background: %(hover)s; }
    QToolButton#taskButton:checked { border-color: %(accent)s; background: %(tint)s; color: %(accent)s; }
    QToolButton#taskButton:focus { border-color: %(accent)s; }
    QDockWidget::title { padding: 8px 10px; background: %(bg)s; font-weight: 600; border-bottom: 1px solid %(line)s; }
    QDockWidget::close-button, QDockWidget::float-button { padding: 3px; border-radius: 3px; }
    QDockWidget::close-button:hover, QDockWidget::float-button:hover { background: %(tint)s; }
    QPushButton, QToolButton { background: transparent; border: 1px solid transparent; padding: 6px 10px; border-radius: 5px; min-height: 18px; }
    QPushButton:hover, QToolButton:hover { background: %(hover)s; }
    QPushButton:pressed, QToolButton:pressed { background: %(tint)s; }
    QPushButton:focus, QToolButton:focus { border: 1px solid %(accent)s; }
    QPushButton:checked, QToolButton:checked { color: %(accent)s; background: %(tint)s; }
    QPushButton[role="primary"] { background: #345fd1; color: white; padding: 7px 14px; border: 1px solid #345fd1; font-weight: 600; }
    QPushButton[role="primary"]:hover { background: #294fb9; }
    QPushButton[role="secondary"] { background: %(panel)s; border: 1px solid %(line)s; }
    QPushButton[role="search"] { text-align: left; color: %(muted)s; border: 1px solid %(line)s; background: %(bg)s; }
    QPushButton:disabled, QToolButton:disabled { color: %(disabled)s; background: transparent; border-color: transparent; }
    QPushButton[role="primary"]:disabled { background: %(tint)s; color: %(muted)s; border: 1px solid %(line)s; }
    QPushButton[role="danger"] { color: %(error)s; }
    QToolButton::menu-indicator { subcontrol-position: right center; }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: %(field)s; border: 1px solid %(line)s; border-radius: 5px; padding: 6px 8px; min-height: 18px; selection-background-color: %(accent)s; }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: %(accent)s; }
    QLineEdit[invalid="true"] { border-color: %(error)s; }
    QToolButton#sectionHeader, QToolButton#sectionHeader:checked { background: transparent; color: %(text)s; font-weight: 600; border: 0; border-bottom: 1px solid %(line)s; border-radius: 0; text-align: left; padding: 5px 0 8px 0; }
    QToolButton#sectionHeader:hover { background: %(hover)s; }
    QToolButton#sectionHeader:focus { border-bottom-color: %(accent)s; }
    QComboBox::down-arrow { image: url("%(arrow)s"); width: 12px; height: 12px; }
    QComboBox::drop-down { border: 0; width: 22px; }
    QComboBox QAbstractItemView { background: %(panel)s; color: %(text)s; selection-background-color: %(tint)s; selection-color: %(accent)s; padding: 4px; }
    QTreeWidget, QListWidget, QTableWidget { background: %(panel)s; border: 0; outline: 0; selection-background-color: %(tint)s; selection-color: %(accent)s; }
    QTreeWidget::item, QListWidget::item { padding: 6px; border: 1px solid transparent; border-radius: 4px; }
    QTreeWidget::item:hover, QListWidget::item:hover { background: %(hover)s; }
    QTreeWidget::item:selected, QListWidget::item:selected { background: %(tint)s; color: %(accent)s; }
    QTreeWidget::item:focus, QListWidget::item:focus { border: 1px solid %(accent)s; }
    QTreeWidget#projectTree, QListWidget#outline { background: %(bg)s; }
    QPlainTextEdit { background: %(field)s; color: %(text)s; border: 1px solid %(line)s; border-radius: 4px; }
    QTabWidget::pane { border: 0; background: %(panel)s; }
    QTabBar::tab { background: transparent; color: %(muted)s; padding: 10px 14px; border-bottom: 2px solid transparent; }
    QTabBar::tab:selected { color: %(accent)s; border-bottom-color: %(accent)s; }
    QTabBar::tab:hover { background: %(hover)s; }
    QTabBar::tab:disabled { color: %(disabled)s; }
    QScrollArea { background: %(panel)s; border: 0; }
    QScrollArea > QWidget > QWidget { background: %(panel)s; }
    QSplitter::handle { background: %(line)s; width: 1px; height: 1px; }
    QDockWidget { background: %(panel)s; border: 0; }
    QDockWidget[floatingPanel="true"] { border: 2px solid %(muted)s; }
    QDockWidget::separator { width: 1px; height: 1px; background: %(line)s; }
    QHeaderView::section { background: %(bg)s; color: %(muted)s; border: 0; border-bottom: 1px solid %(line)s; padding: 8px; text-align: left; }
    QTableWidget { gridline-color: %(line)s; alternate-background-color: %(bg)s; }
    QTableCornerButton::section { background: %(bg)s; border: 0; }
    QStatusBar { background: %(panel)s; border-top: 1px solid %(line)s; color: %(muted)s; font-size: 11px; }
    QStatusBar::item { border: 0; }
    QProgressBar { background: %(hover)s; border: 0; border-radius: 3px; max-height: 6px; }
    QProgressBar::chunk { background: %(accent)s; border-radius: 3px; }
    QCheckBox { spacing: 7px; }
    QCheckBox::indicator, QAbstractItemView::indicator { width: 14px; height: 14px; border: 1px solid %(muted)s; border-radius: 3px; background: %(field)s; }
    QCheckBox::indicator:checked, QAbstractItemView::indicator:checked { background: #345fd1; border-color: #345fd1; image: url("%(check)s"); }
    QCheckBox:focus { color: %(accent)s; }
    QScrollBar:vertical { width: 9px; background: transparent; margin: 2px; }
    QScrollBar::handle:vertical { background: %(line)s; border-radius: 3px; min-height: 30px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
    QScrollBar:horizontal { height: 9px; background: transparent; margin: 2px; }
    QScrollBar::handle:horizontal { background: %(line)s; border-radius: 3px; min-width: 30px; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
    QToolTip { background: %(panel)s; color: %(text)s; border: 1px solid %(line)s; padding: 6px; }
    ''' % t


def apply_native_window_theme(widget, dark):
    """Use the supported Windows 11 title-bar attributes; retain native controls.

    https://learn.microsoft.com/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute
    Unsupported hosts retain their normal window-manager decoration.
    """
    import sys
    if sys.platform != 'win32':
        return
    import ctypes
    try:
        fn = ctypes.WinDLL('dwmapi').DwmSetWindowAttribute
        fn.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        fn.restype = ctypes.c_long
        handle = ctypes.c_void_p(int(widget.winId()))
        enabled = ctypes.c_int(bool(dark))
        fn(handle, 20, ctypes.byref(enabled), ctypes.sizeof(enabled))
        # Explicit caption/text colors also support an app-selected dark theme
        # when the system appearance itself is light. Windows 11 build 22000+.
        for attribute, key in ((35, 'panel'), (36, 'text')):
            color = QColor(palette(dark)[key])
            value = ctypes.c_uint(color.red() | color.green() << 8 | color.blue() << 16) if dark else ctypes.c_uint(0xffffffff)
            fn(handle, attribute, ctypes.byref(value), ctypes.sizeof(value))
    except (OSError, AttributeError, RuntimeError):
        pass
