"""Persistent Design / Student Hub tabs around the circuit and RTL editors."""
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QTabWidget, QWidget, QVBoxLayout, QDockWidget, QDialog
from shiboken6 import isValid

from .window_geometry import keep_visible


class AppWorkspaces(QTabWidget):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        self.setObjectName('appWorkspaces')
        self.setAccessibleName('Application workspaces')
        self.setDocumentMode(True)
        self.addTab(studio.takeCentralWidget(), 'Design')
        self.student_page = QWidget()
        layout = QVBoxLayout(self.student_page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.addTab(self.student_page, 'Student Hub')
        self.panels = []
        self.dialogs = []
        self.currentChanged.connect(self.switched)

    def take_design(self):
        widget = self.widget(0)
        self.blockSignals(True)
        self.removeTab(0)
        self.blockSignals(False)
        widget.hide()
        widget.setParent(self.studio)
        return widget

    def set_design(self, widget):
        self.blockSignals(True)
        self.insertTab(0, widget, 'Design')
        self.setCurrentIndex(0)
        self.blockSignals(False)
        widget.show()

    def hub(self):
        hub = getattr(self.studio, '_student_hub', None)
        if hub is None:
            from .student_hub_ui import StudentHub
            hub = StudentHub(self.studio)
            self.studio._student_hub = hub
            self.student_page.layout().addWidget(hub)
            self.studio.task_menus['View'].addAction(hub.guide.toggleViewAction())
        return hub

    def switched(self, index):
        s = self.studio
        if index == 1:
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
