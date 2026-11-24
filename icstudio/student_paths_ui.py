"""Student Hub picker for evidence-linked paths across existing worlds."""

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QPushButton, QTextBrowser, QVBoxLayout)

from .student_paths import ROUTES, milestones


def handoff_html(item):
    if not item:
        return ''
    reading = item['reading'] or 'Earn the previous checkpoint to carry its measured result into this lesson.'
    return (f'<h3>{escape(item["route"])}</h3><p><b>From {escape(item["source"])}</b><br>'
            f'{escape(reading)}</p><p>{escape(item["task"])}</p>')


class CrossWorldPaths(QDialog):
    def __init__(self, hub):
        super().__init__(hub)
        self.hub = hub
        self.setWindowTitle('Cross-world paths')
        self.setWindowModality(Qt.WindowModal)
        self.resize(680, 515)
        layout = QVBoxLayout(self)
        self.paths = QComboBox()
        self.paths.setAccessibleName('Cross-world path')
        for key, route in ROUTES.items():
            self.paths.addItem(route.title,key)
        self.paths.setCurrentIndex(max(0,self.paths.findData(hub.active_path())))
        form = QFormLayout()
        form.addRow('&Path',self.paths)
        layout.addLayout(form)
        self.overview = QTextBrowser()
        self.overview.setAccessibleName('Path checkpoints and evidence handoffs')
        self.overview.setOpenLinks(False)
        self.overview.anchorClicked.connect(lambda url:self.open_stage(url.toString()))
        layout.addWidget(self.overview,1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.resume = QPushButton()
        buttons.addButton(self.resume,QDialogButtonBox.ActionRole)
        buttons.rejected.connect(self.reject)
        self.resume.clicked.connect(lambda:self.open_stage(self.next_stage))
        layout.addWidget(buttons)
        self.paths.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        route = ROUTES[self.paths.currentData()]
        readings = milestones(route,self.hub.portfolio.state,self.hub.by_id)
        self.next_stage = next((stage.lesson for stage,reading in zip(route.milestones,readings) if reading is None),None)
        self.resume.setText('Continue path' if self.next_stage else 'Path complete')
        self.resume.setEnabled(self.next_stage is not None)
        rows = []
        for stage, reading in zip(route.milestones,readings):
            lesson = self.hub.by_id[stage.lesson]
            world = self.hub.path_titles[lesson['path']]
            rows.append(f'<li><a href="{stage.lesson}">{escape(lesson["title"])}</a> · {escape(world)}'
                        f'<p>{escape(stage.task)}</p><p>{escape(reading or "Checkpoint evidence pending")}</p></li>')
        self.overview.setHtml(f'<h2>{escape(route.title)}</h2><p>{escape(route.goal)}</p>'
                              f'<p>{sum(reading is not None for reading in readings)} of {len(readings)} checkpoints earned</p>'
                              f'<ol>{"".join(rows)}</ol>')

    def open_stage(self, key):
        route_id = self.paths.currentData()
        if key not in {stage.lesson for stage in ROUTES[route_id].milestones}:
            return
        self.hub.studio.settings.setValue('student/crossWorldPath',route_id)
        self.accept()
        self.hub.select_lesson(key)
        self.hub.start.setFocus()
