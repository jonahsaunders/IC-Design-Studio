"""Dockable, opt-in Studio assistant. Only Send makes an outbound request."""
import json
import os

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDockWidget, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from . import ai_context, ai_providers as providers, ai_testbench
from .model import clone, design_digest


def label(text=''):
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    widget.setWordWrap(True)
    return widget


class Connection(QDialog):
    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.setWindowTitle('AI connection')
        self.setMinimumWidth(390)
        form = QFormLayout(self)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.provider = QComboBox()
        for key, profile in providers.PROVIDERS.items():
            self.provider.addItem(profile.name, key)
        self.provider.setCurrentIndex(self.provider.findData(panel.provider))
        self.base, self.model, self.key = QLineEdit(), QLineEdit(), QLineEdit()
        self.model.setPlaceholderText('Model ID from your provider')
        self.key.setEchoMode(QLineEdit.Password)
        self.note = label()
        self.error = label()
        for title, widget in [('Provider', self.provider), ('API base URL', self.base), ('Model or deployment', self.model),
                              ('API key or access token', self.key)]:
            form.addRow(title, widget)
        form.addRow(self.note)
        form.addRow(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.provider.currentIndexChanged.connect(self.load)
        self.base.textEdited.connect(self.key.clear)
        self.load()

    def load(self):
        key = self.provider.currentData()
        profile = providers.PROVIDERS[key]
        base, model = self.panel.profile(key)
        self.base.setText(base)
        self.base.setReadOnly(not profile.configurable)
        self.base.setPlaceholderText(profile.hint)
        self.model.setText(model)
        self.key.setText(self.panel.credentials.get((key, base), ''))
        self.note.setText('Entered credentials last until Studio closes.' + (' You can also set ' + profile.env + '.' if profile.env else ' A local server can run without a key.'))
        self.error.clear()

    def save(self):
        key = self.provider.currentData()
        try:
            base = providers.endpoint(key, self.base.text())
            model = self.model.text().strip()
            # Validate model and any explicit credential without reading environment secrets.
            providers.request_parts(key, base, model, self.key.text().strip() or 'test', '')
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.panel.configure(key, base, model, self.key.text().strip())
        self.accept()


class Assistant(QDockWidget):
    def __init__(self, studio):
        super().__init__('AI Assistant', studio)
        self.setObjectName('aiAssistant')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.studio = studio
        self.provider = str(studio.settings.value('assistant/provider', 'openai'))
        if self.provider not in providers.PROVIDERS:
            self.provider = 'openai'
        self.credentials = {}
        self.network = QNetworkAccessManager(self)
        self.network.finished.connect(self.finished)
        self.reply = self.proposal = self.origin = None
        self.deadline = QTimer(self, singleShot=True, interval=150000)
        self.deadline.timeout.connect(self.timeout)
        self.buffer = bytearray()
        body = QWidget()
        self.setWidget(body)
        layout = QVBoxLayout(body)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.account = label()
        row.addWidget(self.account, 1)
        self.connection = QPushButton('Connection…')
        self.connection.clicked.connect(lambda: Connection(self).exec())
        row.addWidget(self.connection)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        layout.addLayout(form)
        self.action = QComboBox()
        for key, title in ai_context.ACTIONS.items():
            self.action.addItem(title, key)
        form.addRow('Task', self.action)
        self.run = QComboBox()
        form.addRow('Failed run', self.run)
        self.run_label = form.labelForField(self.run)
        self.note = QLineEdit()
        self.note.setMaxLength(4000)
        self.note.setPlaceholderText('Optional goal, question, or expected limits')
        form.addRow('Instructions', self.note)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.preview, self.answer, self.review = QPlainTextEdit(), QPlainTextEdit(), QPlainTextEdit()
        for title, editor in [('Request', self.preview), ('Answer', self.answer), ('Testbench preview', self.review)]:
            editor.setReadOnly(True)
            editor.setAccessibleName(title)
            self.tabs.addTab(editor, title)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.refresh_button = QPushButton('Refresh preview')
        self.send_button = QPushButton('Send')
        self.cancel_button = QPushButton('Cancel')
        for button, fn in [(self.refresh_button, self.refresh), (self.send_button, self.send), (self.cancel_button, self.cancel)]:
            button.clicked.connect(fn)
            row.addWidget(button)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.validate_button = QPushButton('Preview testbench')
        self.add_button = QPushButton('Add testbench')
        for button, fn in [(self.validate_button, self.validate_draft), (self.add_button, self.apply)]:
            row.addWidget(button)
            button.clicked.connect(fn)
        self.status = label()
        layout.addWidget(self.status)
        self.action.currentIndexChanged.connect(self.refresh)
        self.run.currentIndexChanged.connect(self.prepare)
        self.note.textChanged.connect(self.prepare)
        self.answer.textChanged.connect(self.invalidate_draft)
        self.update_connection()
        self.refresh()

    def profile(self, key):
        settings = self.studio.settings
        return (str(settings.value('assistant/' + key + '/base', providers.PROVIDERS[key].base)),
                str(settings.value('assistant/' + key + '/model', '')))

    def configure(self, key, base, model, token):
        self.provider = key
        self.credentials[key, base] = token
        for name, value in [('provider', key), (key + '/base', base), (key + '/model', model)]:
            self.studio.settings.setValue('assistant/' + name, value)
        self.update_connection()
        self.prepare()

    def update_connection(self):
        base, model = self.profile(self.provider)
        self.account.setText(providers.PROVIDERS[self.provider].name + ' · ' + (model or 'Choose a model in Connection'))
        self.account.setToolTip(base)

    def controls(self):
        busy = self.reply is not None
        bench = self.action.currentData() == 'bench'
        for w in (self.connection, self.action, self.note, self.run, self.refresh_button):
            w.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.send_button.setEnabled(bool(self.preview.toPlainText()) and not busy)
        self.validate_button.setVisible(bench)
        self.add_button.setVisible(bench)
        self.validate_button.setEnabled(not busy and bool(self.answer.toPlainText()) and self.origin is not None)
        self.add_button.setEnabled(not busy and self.proposal is not None)
        self.tabs.setTabVisible(2, bench)

    def refresh(self):
        self.cancel()
        failure = self.action.currentData() == 'failure'
        self.run_label.setVisible(failure)
        self.run.setVisible(failure)
        self.run.blockSignals(True)
        self.run.clear()
        if failure:
            selected = {r['id'] for r in self.studio.selected_simulation_runs()}
            for r in ai_context.failed_runs(self.studio):
                self.run.addItem(r['name'] + ' · r' + str(r['job']['project']['revision']), r['id'])
            self.run.setCurrentIndex(next((i for i in range(self.run.count()) if self.run.itemData(i) in selected), 0))
        self.run.blockSignals(False)
        self.prepare()

    def prepare(self):
        self.origin = self.proposal = None
        self.answer.clear()
        self.answer.setReadOnly(self.action.currentData() != 'bench')
        self.review.clear()
        self.tabs.setCurrentIndex(0)
        try:
            self.preview.setPlainText(self.current_prompt())
            self.status.setText('Review the text above before sending it to ' + providers.PROVIDERS[self.provider].name + '.')
        except ValueError as exc:
            self.preview.clear()
            self.status.setText(str(exc))
        self.controls()

    def current_prompt(self):
        return ai_context.prompt(self.studio, self.action.currentData(), self.note.text(), self.run.currentData())

    def send(self):
        if self.reply is not None or not self.studio.flush_inspector():
            return
        try:
            prompt = self.current_prompt()
            if prompt != self.preview.toPlainText():
                self.refresh()
                self.status.setText('The selection or run changed. Review the updated request before sending.')
                return
            key = self.provider
            base, model = self.profile(key)
            if not model:
                self.status.setText('Open Connection and choose a provider and model first.')
                return
            token = self.credentials.get((key, base)) or os.environ.get(providers.PROVIDERS[key].env, '')
            url, headers, payload = providers.request_parts(key, base, model, token, prompt)
            req = QNetworkRequest(QUrl(url))
            req.setTransferTimeout(120000)
            req.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.ManualRedirectPolicy)
            for attr in (QNetworkRequest.CookieLoadControlAttribute, QNetworkRequest.CookieSaveControlAttribute,
                         QNetworkRequest.AuthenticationReuseAttribute):
                req.setAttribute(attr, QNetworkRequest.Manual)
            for name, value in headers.items():
                req.setRawHeader(name.encode('ascii'), value.encode('ascii'))
            self.answer.clear()
            self.proposal = None
            self.origin = self.bench_origin() if self.action.currentData() == 'bench' else None
            self.reply = self.network.post(req, json.dumps(payload, ensure_ascii=False).encode('utf-8'))
            self.buffer.clear()
            self.reply.setReadBufferSize(1024 * 1024)
            self.reply.readyRead.connect(self.read)
            self.deadline.start()
            self.status.setText('Waiting for ' + providers.PROVIDERS[key].name + '…')
            self.controls()
        except (ValueError, RuntimeError) as exc:
            self.status.setText(str(exc))

    def read(self):
        if self.sender() != self.reply or self.reply is None:
            return
        self.buffer.extend(bytes(self.reply.readAll()))
        if len(self.buffer) > 1024 * 1024:
            self.cancel()
            self.status.setText('The response exceeded the 1 MB limit. Request a shorter answer.')

    def cancel(self):
        if self.reply is not None:
            reply, self.reply = self.reply, None
            self.deadline.stop()
            self.origin = None
            reply.abort()
            self.buffer.clear()
            self.status.setText('Request cancelled.')
            self.controls()

    def timeout(self):
        self.cancel()
        self.status.setText('The provider timed out. Retry or choose another model.')

    def finished(self, reply):
        reply.deleteLater()
        if self.reply != reply:
            return
        self.reply = None
        self.deadline.stop()
        try:
            code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            if code in (401, 403):
                raise ValueError('The provider denied access. Check the credential and model permissions in Connection.')
            if code == 429:
                raise ValueError('The provider reached a rate or account limit. Check your quota and retry.')
            if code and not 200 <= code < 300:
                raise ValueError(f'Provider returned HTTP {code}. Check the endpoint and model ID in Connection.')
            if reply.error() != QNetworkReply.NoError:
                raise ValueError('Could not reach the provider. ' + reply.errorString())
            self.buffer.extend(bytes(reply.readAll()))
            if len(self.buffer) > 1024 * 1024:
                raise ValueError('The response exceeded the 1 MB limit.')
            answer = providers.response_text(self.provider, json.loads(self.buffer))
            self.answer.setPlainText(answer)
            self.tabs.setCurrentIndex(1)
            self.status.setText('Answer received.')
            if self.action.currentData() == 'bench':
                self.validate_draft()
        except (ValueError, RecursionError) as exc:
            self.status.setText(str(exc))
        finally:
            self.buffer.clear()
            self.controls()

    def invalidate_draft(self):
        self.proposal = None
        self.review.clear()
        self.controls()

    def bench_origin(self):
        studio = self.studio
        return studio.project['id'], ai_context.target(studio)['id'], design_digest(studio.project)

    def verify_origin(self):
        if self.bench_origin() != self.origin:
            raise ValueError('The circuit changed. Refresh the request and generate a new testbench.')

    def validate_draft(self):
        self.proposal = None
        try:
            self.verify_origin()
            cells, bench, description = ai_testbench.propose(self.studio.project, ai_context.target(self.studio), self.answer.toPlainText())
            self.proposal = cells, bench
            self.review.setPlainText(description)
            self.tabs.setCurrentIndex(2)
            self.status.setText('Review the generated fixture and measurements. Edit the Answer to adjust the draft.')
        except (ValueError, RecursionError) as exc:
            self.tabs.setCurrentIndex(1)
            self.status.setText(str(exc))
        self.controls()

    def apply(self):
        if not self.proposal or not self.studio.flush_inspector():
            return
        try:
            self.verify_origin()
            cells, bench = self.proposal
            def edit(p):
                p['cells'].extend(clone(cells))
                p.setdefault('testbenches', []).append(clone(bench))
            if not self.studio.capture_commit(edit, 'Add AI-assisted testbench'):
                return
            self.proposal = self.origin = None
            combo = self.studio.testbench_combo
            combo.setCurrentIndex(combo.findData(bench['id']))
            self.status.setText('Added ' + bench['name'] + '. Use Run saved testbench in Analysis, or Undo to remove it.')
        except (ValueError, RuntimeError) as exc:
            self.status.setText(str(exc))
        self.controls()

    def closeEvent(self, event):
        self.cancel()
        super().closeEvent(event)


def install(studio):
    def show():
        studio.show_design_workspace()
        panel = getattr(studio, '_ai_assistant', None)
        if panel is None:
            panel = Assistant(studio)
            studio._ai_assistant = panel
            studio.addDockWidget(Qt.RightDockWidgetArea, panel)
            studio.tabifyDockWidget(studio.inspector, panel)
        elif panel.reply is None and not panel.answer.toPlainText():
            panel.refresh()
        panel.show()
        panel.raise_()
    studio.action(studio.task_menus['Tools'], 'AI Assistant…', show)
