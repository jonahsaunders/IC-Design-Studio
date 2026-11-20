"""Dockable, opt-in Studio assistant. Only Send makes an outbound request."""
import json
import os

from PySide6.QtCore import Qt, QEvent, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDockWidget, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMenu, QPlainTextEdit, QPushButton, QTabWidget, QToolButton,
                               QVBoxLayout, QWidget)

from . import ai_context, ai_providers as providers, ai_testbench
from .ai_investigation import solver
from .model import clone, design_digest
from .ai_review_ui import ReviewTools
from .analog_widgets import FlowActions, scroll


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


class Assistant(ReviewTools, QDockWidget):
    def __init__(self, studio):
        super().__init__('AI Assistant', studio)
        self.setObjectName('aiAssistant')
        self.setMinimumWidth(320)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.studio = studio
        self.windows = []
        self.change = self.change_window = None
        self.reset_context()
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
        shell = QWidget()
        self.setWidget(shell)
        outer = QVBoxLayout(shell)
        outer.setContentsMargins(0,0,0,0)
        outer.setSpacing(0)
        body = QWidget()
        outer.addWidget(scroll(body),1)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12,10,12,10)
        layout.setSpacing(8)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.account = label()
        self.account.setProperty('role','subtitle')
        row.addWidget(self.account, 1)
        self.setup_button = QPushButton('Set Up…')
        self.setup_button.setAccessibleName('Set up AI connection')
        self.setup_button.clicked.connect(lambda: Connection(self).exec())
        row.addWidget(self.setup_button)
        self.connection = QToolButton()
        self.connection.setText('Options')
        self.connection.setAccessibleName('Investigation options')
        self.connection.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.connection)
        menu.addAction('Refresh Preview', self.refresh_request)
        menu.addAction('New Investigation', self.new_investigation)
        menu.addSeparator()
        menu.addAction('Connection Settings…', lambda: Connection(self).exec())
        self.connection.setMenu(menu)
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
        self.note.setAccessibleName('Question or expected limits')
        self.note.setPlaceholderText('Ask a question or set a goal…')
        self.pins_widget = QWidget()
        self.attachments = FlowActions(self.pins_widget)
        layout.addWidget(self.pins_widget)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.preview, self.answer, self.review = QPlainTextEdit(), QPlainTextEdit(), QPlainTextEdit()
        for title, editor in [('Request', self.preview), ('Answer', self.answer), ('Testbench preview', self.review)]:
            editor.setReadOnly(True)
            editor.setAccessibleName(title)
            if editor == self.answer:
                page = QWidget()
                content = QVBoxLayout(page)
                content.setContentsMargins(0,4,0,0)
                self.evidence_widget = QWidget()
                self.evidence_widget.setObjectName('investigationEvidence')
                evidence_layout = QVBoxLayout(self.evidence_widget)
                evidence_layout.setContentsMargins(8,6,8,6)
                evidence_layout.setSpacing(4)
                self.evidence_note = label()
                evidence_layout.addWidget(self.evidence_note)
                evidence_actions = FlowActions()
                evidence_layout.addLayout(evidence_actions)
                self.wave_button = QPushButton('Waveform')
                self.wave_button.setAccessibleName('Open waveform')
                self.wave_button.setToolTip('Open the waveform for the saved measurement or probe')
                self.wave_button.clicked.connect(lambda:self.call_local(self.inspect_evidence))
                self.device_button = QPushButton('Device…')
                self.device_button.setAccessibleName('Show device operating point')
                self.device_button.clicked.connect(lambda:self.call_local(lambda:self.inspect_evidence(True)))
                self.compare_button = QToolButton()
                self.compare_button.setText('Compare')
                self.compare_button.setAccessibleName('Compare simulation results')
                self.compare_button.setPopupMode(QToolButton.InstantPopup)
                menu = QMenu(self.compare_button)
                self.pass_button = menu.addAction('Compare with Passing Run…',lambda:self.call_local(self.compare_passing))
                self.experiment_button = menu.addAction('Compare One Change…',lambda:self.call_local(self.experiment))
                self.compare_button.setMenu(menu)
                for button in (self.wave_button,self.device_button,self.compare_button):
                    button.setProperty('evidenceAction',True)
                    evidence_actions.addWidget(button)
                content.addWidget(self.evidence_widget)
                content.addWidget(editor,1)
                self.tabs.addTab(page,title)
            elif editor == self.review:
                from .ai_fixture_ui import FixtureView
                page = QWidget()
                content = QVBoxLayout(page)
                content.setContentsMargins(0,4,0,0)
                self.fixture_schematic = FixtureView(studio.dark)
                self.fixture_view = self.fixture_schematic.canvas
                self.fixture_view.setMinimumHeight(135)
                self.fixture_view.picked.connect(self.choose_output)
                content.addWidget(self.fixture_schematic,2)
                content.addWidget(editor,1)
                self.tabs.addTab(page,'Fixture')
            else:
                page = QWidget()
                content = QVBoxLayout(page)
                content.setContentsMargins(8,12,8,4)
                self.scope_title = label()
                self.scope_title.setProperty('role','subtitle')
                self.scope_detail = label()
                self.scope_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
                content.addWidget(self.scope_title)
                content.addWidget(self.scope_detail)
                self.disclosure = QToolButton()
                self.disclosure.setText('Full request')
                self.disclosure.setCheckable(True)
                self.disclosure.setArrowType(Qt.RightArrow)
                self.disclosure.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                self.disclosure.setAccessibleName('Show full request')
                self.disclosure.toggled.connect(self.show_full_request)
                content.addWidget(self.disclosure, 0, Qt.AlignLeft)
                content.addWidget(editor, 1)
                editor.hide()
                content.addStretch()
                self.tabs.addTab(page, title)
        footer = QWidget()
        footer.setObjectName('investigationComposer')
        outer.addWidget(footer)
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(10,8,10,8)
        footer_layout.setSpacing(4)
        row = QHBoxLayout()
        footer_layout.addLayout(row)
        row.addWidget(self.note,1)
        self.send_button = QPushButton('Send')
        self.send_button.setProperty('role','primary')
        self.cancel_button = QPushButton('Cancel')
        for button, fn in [(self.send_button, self.send), (self.cancel_button, self.cancel)]:
            button.clicked.connect(fn)
            row.addWidget(button)
        row = FlowActions()
        layout.addLayout(row)
        self.validate_button = QPushButton('Preview')
        self.review_change = QPushButton('Review Changes…')
        self.review_change.clicked.connect(self.open_change_review)
        row.addWidget(self.review_change)
        self.add_button = QPushButton('Save Testbench')
        self.edit_button = QPushButton('Edit Fixture…')
        self.draft_button = QPushButton('Run Draft…')
        for button, fn in [(self.edit_button, lambda:self.call_local(self.edit_fixture)),
                           (self.validate_button, self.validate_draft), (self.draft_button,lambda:self.call_local(self.run_draft)),
                           (self.add_button, self.apply)]:
            row.addWidget(button)
            button.clicked.connect(fn)
        self.status = label()
        self.status.setProperty('role','muted')
        footer_layout.addWidget(self.status)
        self.action.currentIndexChanged.connect(self.new_investigation)
        self.run.currentIndexChanged.connect(self.run_selected)
        self.note.textChanged.connect(self.update_preview)
        self.note.returnPressed.connect(self.send)
        self.answer.textChanged.connect(self.invalidate_draft)
        self.apply_theme()
        self.update_connection()
        self.refresh()

    def apply_theme(self):
        from .ui_style import palette
        self.setStyleSheet('''
            QToolButton[attachment="true"] { color: %(accent)s; background: %(tint)s; border-radius: 8px; padding: 2px 6px; font-size: 12px; }
            QToolButton[attachment="true"]:focus { border: 1px solid %(accent)s; }
            QWidget#investigationEvidence { background: %(bg)s; border-radius: 6px; }
            QWidget[evidenceAction="true"] { background: %(panel)s; border: 1px solid %(line)s; padding: 3px 7px; }
            QWidget[evidenceAction="true"]:focus { border-color: %(accent)s; }
            QWidget[evidenceAction="true"]:hover { background: %(hover)s; }
            QToolButton[evidenceAction="true"] { padding-right: 17px; }
            QWidget#investigationComposer { background: %(bg)s; }
        ''' % palette(self.studio.dark))

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
        self.account.setText(providers.PROVIDERS[self.provider].name + (' · ' + model if model else ''))
        self.account.setToolTip(base)
        self.setup_button.setVisible(not model)

    def controls(self):
        busy = self.reply is not None
        bench = self.action.currentData() == 'bench'
        for w in (self.connection, self.action, self.note, self.run):
            w.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.send_button.setEnabled(bool(self.profile(self.provider)[1] and self.preview.toPlainText()) and not busy)
        has_draft = bench and bool(self.answer.toPlainText()) and self.origin is not None
        self.validate_button.setVisible(has_draft)
        self.add_button.setVisible(bench and self.proposal is not None)
        self.validate_button.setEnabled(not busy and has_draft)
        self.add_button.setEnabled(not busy and self.proposal is not None)
        self.edit_button.setVisible(has_draft)
        self.draft_button.setVisible(bench and self.proposal is not None)
        self.edit_button.setEnabled(self.validate_button.isEnabled())
        self.draft_button.setEnabled(self.add_button.isEnabled())
        self.pins_widget.setEnabled(not busy)
        self.tabs.setTabVisible(2, bench)
        editing = self.action.currentData() == 'edit'
        self.review_change.setVisible(editing and self.change is not None)
        self.review_change.setEnabled(self.change is not None and not busy)
        self.note.setPlaceholderText('Describe the schematic change…' if editing else 'Ask a question or set a goal…')
        if editing and not self.note.text().strip():
            self.send_button.setEnabled(False)

    def refresh_request(self):
        if self.action.currentData() == 'edit':
            self.reset_context()
        self.refresh()

    def refresh(self):
        self.cancel()
        failure = self.action.currentData() == 'failure'
        self.run_label.setVisible(failure)
        self.run.setVisible(failure)
        self.run.blockSignals(True)
        self.run.clear()
        if failure:
            selected = {self.row['id']} if self.row else {r['id'] for r in self.studio.selected_simulation_runs()}
            for r in ai_context.failed_runs(self.studio):
                self.run.addItem(r['name'] + ' · r' + str(r['job']['project']['revision']), r['id'])
            self.run.setCurrentIndex(next((i for i in range(self.run.count()) if self.run.itemData(i) in selected), 0))
        self.run.blockSignals(False)
        if failure and not self.row and self.run.currentIndex() >= 0:
            self.run_selected()
            return
        self.prepare()

    def run_selected(self):
        self.reset_context()
        self.row = self.current_row()
        if self.row:
            from .ai_investigation import checks
            self.check = next((c for c in checks(self.row) if str(c['actual'].get('status')).lower() in ('fail','failed','error')),None)
        self.prepare()

    def prepare(self):
        self.clear_change()
        self.origin = self.proposal = None
        self.answer.clear()
        self.answer.setReadOnly(self.action.currentData() != 'bench')
        self.review.clear()
        self.tabs.setCurrentIndex(0)
        self.attachment_bar()
        self.call_local(self.update_evidence)
        self.update_preview()

    def show_full_request(self, expanded):
        self.disclosure.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.disclosure.setAccessibleName('Hide full request' if expanded else 'Show full request')
        self.preview.setVisible(expanded)
        layout = self.disclosure.parentWidget().layout()
        layout.setStretch(layout.count()-1, 0 if expanded else 1)

    def describe_scope(self):
        def listed(items):
            suffix = f' (+{len(items)-8} more)' if len(items) > 8 else ''
            return ', '.join(items[:8]) + suffix

        row = self.current_row()
        if row:
            job = row['job']
            self.scope_title.setText(row['name'] + ' · revision ' + str(job['project']['revision']))
            lines = [f"{row['state']} · {solver(job)} · {job['settings']['type']}"]
            if self.check:
                lines.append('Measurement: ' + self.check['definition']['name'])
            if self.probe_ref:
                lines.append('Waveform: ' + self.probe_ref[1])
            if self.device_ref:
                lines.append('Device: ' + self.device_ref)
        else:
            ctx = self.pinned or self.studio
            bench = self.action.currentData() == 'bench'
            cell = self.bench_cell() if bench else ctx.cell
            self.scope_title.setText(f"{cell['name']} · revision {ctx.project['revision']}")
            ids = set(ctx.selection)
            if bench or not (ids or ctx.net):
                count = len(cell['devices'])
                lines = [f"Whole circuit · {count} component" + ('' if count == 1 else 's')]
                if cell['ports']:
                    lines.append('Ports: ' + listed(cell['ports']))
            else:
                parts = [d for d in cell['devices'] if d['id'] in ids]
                nets = ([ctx.net] if ctx.net else []) + [w['net'] for w in cell['wires'] if w['id'] in ids]
                nets.extend(l['name'] for l in cell.get('labels',[]) if l['id'] in ids)
                nets.extend(n for d in parts for n in d['nets'].values() if n)
                nets = list(dict.fromkeys(nets))
                lines = []
                names = [f"{d['name']} ({d['value']})" if d['kind'] in ('R','C','L') and d.get('value')
                         else d['name'] for d in parts]
                for caption, items in [('Components', names), ('Nets', nets)]:
                    if items:
                        lines.append(caption + ': ' + listed(items))
        self.scope_detail.setText('\n'.join(lines))

    def update_preview(self, text=None):
        update_scope = text is None or not self.preview.toPlainText()
        try:
            self.preview.setPlainText(self.prompt_text(typing=text is not None))
            if update_scope:
                self.describe_scope()
            self.disclosure.show()
            if not self.profile(self.provider)[1]:
                self.status.setText('Set up a connection to send a request.')
            elif self.action.currentData() == 'edit' and not self.note.text().strip():
                self.status.setText('Describe the change you want to preview.')
            else:
                self.status.setText('Ready to send to ' + providers.PROVIDERS[self.provider].name + '.')
        except ValueError as exc:
            self.preview.clear()
            self.scope_title.setText('Request needs context')
            self.scope_detail.setText(str(exc))
            self.disclosure.setChecked(False)
            self.disclosure.hide()
            self.status.setText('Set up a connection to send a request.' if not self.profile(self.provider)[1] else '')
        self.controls()

    def current_prompt(self):
        return self.prompt_text()

    def send(self):
        if self.reply is not None or not self.studio.flush_inspector():
            return
        if self.action.currentData()=='edit' and not self.note.text().strip():
            self.status.setText('Describe the change you want to preview.')
            return
        try:
            prompt = self.current_prompt()
            if prompt != self.preview.toPlainText():
                self.update_preview()
                self.tabs.setCurrentIndex(0)
                self.disclosure.setChecked(True)
                self.status.setText('The selection or run changed. Review the updated request before sending.')
                return
            key = self.provider
            base, model = self.profile(key)
            if not model:
                self.status.setText('Choose a provider and model in Options → Connection Settings.')
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
            self.clear_change()
            self.answer.clear()
            self.proposal = None
            self.remember_send()
            self.origin = self.bench_origin(self.pinned.project) if self.action.currentData() == 'bench' else None
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
            self.tabs.setCurrentIndex(1)
            self.status.setText('Answer received.')
            if self.action.currentData() == 'bench':
                self.answer.setPlainText(answer)
                self.validate_draft()
            elif self.action.currentData() == 'edit':
                from .ai_schematic_edits import propose
                summary, self.change = propose(self.pinned,answer)
                reviewed = [e.name+' · '+e.field+' · '+e.before+' → '+e.after for e in self.change.edits] if self.change else []
                self.turns.append((self.pending_question,'\n'.join([summary,*reviewed])))
                self.turns = self.turns[-4:]
                self.answer.setPlainText(summary)
                if self.change:
                    self.status.setText('Review the proposed changes before applying.')
                    self.open_change_review()
                else:
                    self.status.setText('No edits proposed. Add details and send a follow-up.')
            else:
                self.receive_explanation(answer)
        except (ValueError, RecursionError) as exc:
            self.status.setText(str(exc))
        finally:
            self.buffer.clear()
            self.controls()

    def invalidate_draft(self):
        self.proposal = None
        self.review.clear()
        self.fixture_schematic.cell_picker.hide()
        self.fixture_view.candidates = set()
        self.fixture_view.cell = None
        self.fixture_view.update()
        self.edit_button.setText('Edit Fixture…')
        self.controls()

    def clear_change(self):
        self.change = None
        if self.change_window:
            self.change_window.close()
            self.change_window = None

    def open_change_review(self):
        if not self.change:
            return
        if not self.change_window:
            from .ai_schematic_review_ui import ChangeReview
            window = ChangeReview(self,self.change)
            self.change_window = window
            window.finished.connect(lambda *_:setattr(self,'change_window',None) if self.change_window is window else None)
            self.open_window(window)
        else:
            self.change_window.raise_()
            self.change_window.activateWindow()

    def discard_change(self):
        self.clear_change()
        self.status.setText('Proposal discarded.')
        self.controls()

    def change_applied(self):
        count = len(self.change.edits)
        self.new_investigation()
        self.status.setText(f'Applied {count} schematic edit' + ('.' if count==1 else 's.') + ' Edit → Undo reverses this change.')

    def choose_output(self, name):
        spec = ai_testbench.decode(self.answer.toPlainText())
        if name not in spec.get('output_candidates',[]):
            return
        spec.pop('output_candidates')
        spec['probes'] = list(dict.fromkeys(name if n=='@output' else n for n in spec['probes']))
        if name not in spec['probes']:
            spec['probes'].append(name)
        for m in spec['measurements']:
            if m.get('node')=='@output':
                m['node'] = name
        self.answer.setPlainText(json.dumps(spec,ensure_ascii=False,indent=2))
        self.validate_draft()

    def bench_origin(self, project=None):
        project = project if project is not None else self.studio.project
        return project['id'], self.bench_cell()['id'], design_digest(project)

    def verify_origin(self):
        if self.bench_origin() != self.origin:
            raise ValueError('The circuit changed. Choose New Investigation and generate a testbench for the current revision.')

    def validate_draft(self):
        self.proposal = None
        try:
            self.verify_origin()
            cells, bench, description = ai_testbench.propose(self.studio.project, self.bench_cell(), self.answer.toPlainText())
            self.proposal = cells, bench
            self.review.setPlainText(description)
            self.fixture_schematic.show_fixture(cells,self.bench_cell(),self.studio.project['pdk'])
            self.tabs.setCurrentIndex(2)
            self.fixture_view.fit()
            self.status.setText('Edit the fixture, run a draft, or save this testbench.')
        except (ValueError, RecursionError) as exc:
            self.tabs.setCurrentIndex(1)
            self.status.setText(str(exc))
            try:
                candidates = ai_testbench.decode(self.answer.toPlainText()).get('output_candidates')
            except ValueError:
                candidates = None
            if self.origin and self.bench_origin()==self.origin and candidates:
                cell = self.bench_cell()
                if not set(candidates) <= (set(cell['ports']) or ai_testbench.circuit_nets(cell)) - {'0'}:
                    self.status.setText('The proposed output pins must be existing non-ground pins on this circuit.')
                    self.controls()
                    return
                self.fixture_schematic.show_candidates(cell,self.studio.project['pdk'],candidates)
                self.review.setPlainText('Choose an output pin in the schematic or in Edit Fixture.\n' + ', '.join(candidates))
                self.edit_button.setText('Choose Output…')
                self.tabs.setCurrentIndex(2)
                self.fixture_view.fit()
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

    def changeEvent(self, event):
        if event.type() == QEvent.PaletteChange and hasattr(self,'fixture_view'):
            self.fixture_view.dark = self.studio.dark
            self.fixture_view.update()
        super().changeEvent(event)


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
        return panel
    studio.action(studio.task_menus['Tools'], 'AI Assistant…', show)
    from . import ai_entry_points
    ai_entry_points.install(studio,show)
