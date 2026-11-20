"""Persistent Design / Student Hub tabs around the circuit and RTL editors."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QDialog, QDockWidget, QMenu, QSizePolicy, QStackedWidget, QTabBar,
                               QToolBar, QToolButton, QVBoxLayout, QWidget)
from shiboken6 import isValid

from .window_geometry import keep_visible


class AppWorkspaces(QStackedWidget):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        self.setObjectName('appWorkspaces')
        self.setAccessibleName('Application workspaces')
        self.addWidget(studio.takeCentralWidget())
        self.student_page = QWidget()
        layout = QVBoxLayout(self.student_page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.addWidget(self.student_page)
        navigation = QToolBar('Application workspaces', studio)
        self.navigation = navigation
        navigation.setObjectName('workspaceNavigation')
        navigation.setMovable(False)
        navigation.setFloatable(False)
        navigation.toggleViewAction().setVisible(False)
        self.place_navigation()
        self.tabs = QTabBar(navigation)
        self.tabs.setAccessibleName('Application workspaces')
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.addTab('Design')
        self.tabs.addTab('Student Hub')
        navigation.addWidget(self.tabs)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        navigation.addWidget(spacer)
        navigation.addWidget(studio.collaboration_button)

        self.menu_button = QToolButton(self.tabs)
        self.menu_button.setObjectName('studentHubMenuButton')
        self.menu_button.setAccessibleName('Student Hub menu')
        self.menu_button.setToolTip('Student Hub menu')
        self.menu_button.setArrowType(Qt.DownArrow)
        self.menu_button.setFocusPolicy(Qt.StrongFocus)
        self.menu_button.setPopupMode(QToolButton.InstantPopup)
        self.hub_menu = QMenu('Student Hub', self.menu_button)
        self.menu_button.setMenu(self.hub_menu)
        self.tabs.setTabButton(1, QTabBar.RightSide, self.menu_button)
        self.hub_menu.aboutToShow.connect(lambda: self.setCurrentIndex(1))
        self.tabs.currentChanged.connect(self.setCurrentIndex)
        self.currentChanged.connect(self.tabs.setCurrentIndex)
        self.panels = []
        self.dialogs = []
        self.currentChanged.connect(self.switched)

    def place_navigation(self):
        # Earlier saved layouts only know the design toolbar. Qt can append
        # unrecognized toolbars beside it, pushing workspace controls offscreen.
        self.studio.insertToolBar(self.studio.toolbar, self.navigation)
        self.studio.insertToolBarBreak(self.studio.toolbar)
        self.navigation.show()

    def take_design(self):
        widget = self.widget(0)
        self.blockSignals(True)
        self.removeWidget(widget)
        self.blockSignals(False)
        widget.hide()
        widget.setParent(self.studio)
        return widget

    def set_design(self, widget):
        self.blockSignals(True)
        self.insertWidget(0, widget)
        self.setCurrentIndex(0)
        self.blockSignals(False)
        self.tabs.setCurrentIndex(0)
        widget.show()

    def hub(self):
        hub = getattr(self.studio, '_student_hub', None)
        if hub is None:
            from .student_hub_ui import StudentHub
            hub = StudentHub(self.studio, menu=self.hub_menu)
            self.studio._student_hub = hub
            self.student_page.layout().addWidget(hub)
            self.studio.task_menus['View'].addAction(hub.guide.toggleViewAction())
        return hub

    def switched(self, index):
        s = self.studio
        if index == 1:
            navigating_tabs = self.tabs.hasFocus()
            hub = self.hub()
            try:
                hub.reload_progress()
            except Exception as exc:
                # A storage failure must retain the reflection draft and still
                # leave both workspace tabs usable.
                from .student_hub_ui import feedback
                feedback(hub.status, str(exc), True)
            hub.fill()
            # Display fitting may clamp the current minimum to a small screen.
            # Preserve the requested Design minimum, and fit the active workspace.
            self.design_minimum = QSize(getattr(s, '_workspace_minimum_size', s.minimumSize()))
            s._workspace_minimum_size = QSize(720, 600)
            self.panels = [(d, not d.isHidden()) for d in s.findChildren(QDockWidget)
                           if d is not getattr(s, '_digital_window', None)]
            self.toolbar_visible = not s.toolbar.isHidden()
            self.project_id = s.project['id']
            self.dialogs = [d for d in s.findChildren(QDialog) if d.isWindow() and d.isVisible() and not d.isModal()]
            for dialog in self.dialogs:
                dialog.hide()
            for panel, _ in self.panels:
                panel.hide()
            s.toolbar.hide()
            keep_visible(s)
            hub.show()
            if navigating_tabs:
                self.tabs.setFocus()
            else:
                hub.search.setFocus()
        else:
            if hasattr(self, 'design_minimum'):
                s._workspace_minimum_size = QSize(self.design_minimum)
            for panel, visible in self.panels:
                if isValid(panel):
                    panel.setVisible(visible)
            self.panels = []
            s.toolbar.setVisible(getattr(self, 'toolbar_visible', True))
            if getattr(self, 'project_id', None) == s.project['id']:
                for dialog in self.dialogs:
                    if isValid(dialog) and dialog is not getattr(s, '_start_dialog', None):
                        dialog.show()
            self.dialogs = []
            keep_visible(s)


def install(studio):
    studio.app_workspaces = AppWorkspaces(studio)
    studio.setCentralWidget(studio.app_workspaces)
