"""Desktop access to the same Tiny Tapeout archive used by the CLI."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel, QLineEdit, QVBoxLayout

from . import digital_design, tapeout
from .model import clone


def export_source_dialog(studio):
    project = studio.project
    window = getattr(studio, '_digital_window', None)
    cell_id = studio.cid
    uses_draft = bool(window and window.dirty and window.project_id == project['id'] and window.cell_id == cell_id)
    if uses_draft:
        if digital_design.config(project, cell_id) != window.base:
            raise ValueError('The project’s RTL changed after you started editing. Resolve the source draft before exporting.')
        window.sync_file()
        config = clone(window.config)
        config.update(top=window.top.text().strip(), testbench=window.testbench.text().strip())
        project = clone(project)
        digital_design.set_config(project, cell_id, config)
    tapeout.uart_inputs(project, cell_id)
    dialog = TapeoutSourceDialog(project, cell_id, uses_draft, studio)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        message = f'Saved {dialog.destination.name}. Official hardening and stream precheck are pending.'
        studio.statusBar().showMessage(message)
        if window and window.project_id == project['id'] and window.cell_id == cell_id:
            window.message.setText(message)


class TapeoutSourceDialog(QDialog):
    def __init__(self, project, cell_id, uses_draft, parent):
        super().__init__(parent)
        self.project, self.cell_id = project, cell_id
        self.destination = None
        self.setWindowTitle('Export Tiny Tapeout Source')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        scope = QLabel(f'{tapeout.PROFILE_NAME} · SKY130A / HD · 1 × 1 tile · 10 ns clock target')
        scope.setWordWrap(True)
        layout.addWidget(scope)
        detail = 'The ZIP includes the UART sources and the official hardening workflow. Hardening and stream precheck are pending.'
        if uses_draft:
            detail += ' This export uses the unapplied RTL edits shown in the editor.'
        instructions = QLabel(detail)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        form = QFormLayout()
        self.title = self._field(form, '&Title', project['name'])
        self.author = self._field(form, '&Author', '')
        self.description = self._field(form, '&Description', tapeout.DEFAULT_DESCRIPTION)
        self.top = self._field(form, 'Top &module', tapeout.DEFAULT_TOP)
        layout.addLayout(form)

        self.message = QLabel()
        self.message.setAccessibleName('Export status')
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        self.message.setMinimumHeight(self.message.fontMetrics().lineSpacing())
        layout.addWidget(self.message)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.export = buttons.addButton('Export Source &ZIP…', QDialogButtonBox.ButtonRole.AcceptRole)
        self.export.setDefault(True)
        buttons.accepted.connect(self.save_source)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.author.setFocus()

    @staticmethod
    def _field(form, label, text):
        field = QLineEdit()
        field.setAccessibleName(label.replace('&', ''))
        field.setText(text)
        form.addRow(label, field)
        return field

    def save_source(self):
        self.message.clear()
        if not self.author.text().strip():
            self.message.setText('Enter the author to include in the shuttle metadata.')
            self.author.setFocus()
            return
        try:
            package = tapeout.prepare(
                self.project, cell_id=self.cell_id, title=self.title.text(), author=self.author.text(),
                description=self.description.text(), top=self.top.text(),
            )
            path, _ = QFileDialog.getSaveFileName(
                self, 'Save Tiny Tapeout Source', f'{self.top.text().strip()}.zip', 'ZIP archive (*.zip)',
            )
            if path:
                self.destination = tapeout.write_package(path, package)
                self.accept()
        except (OSError, ValueError) as exc:
            self.message.setText(str(exc))
