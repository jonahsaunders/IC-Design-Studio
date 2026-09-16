"""Lazy, offline VGA preview beside Studio's project-owned RTL editor."""
from __future__ import annotations

import json
import time

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QApplication

from . import digital_design
from .digital_vga import AssetServer, preview_inputs, preset_config


class VGAPlayground(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.server = None
        self.view = None
        self.ready = False
        self.loaded_ok = False
        self.closed = False
        self.last_inputs = None
        self.presets = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout(); root.addLayout(bar)
        self.preset = QComboBox(); self.preset.setAccessibleName('VGA preset'); bar.addWidget(self.preset, 1)
        self.create = QPushButton('Create RTL cell'); self.create.setEnabled(False)
        self.create.clicked.connect(lambda: window.attempt(self.create_cell)); bar.addWidget(self.create)
        self.retry = QPushButton('Reload preview'); self.retry.clicked.connect(self.reload); bar.addWidget(self.retry)
        self.note = QLabel('Preview the working copy, or create a cell from a Tiny Tapeout preset.'); self.note.setWordWrap(True); root.addWidget(self.note)
        self.content = QVBoxLayout(); root.addLayout(self.content, 1)
        credit = QLabel('Powered by Tiny Tapeout VGA Playground · GPL-3.0 · 25.175 MHz VGA')
        credit.setProperty('role', 'muted'); root.addWidget(credit)
        self.debounce = QTimer(self); self.debounce.setSingleShot(True); self.debounce.setInterval(600)
        self.debounce.timeout.connect(self.update_preview)
        self.poll = QTimer(self); self.poll.setInterval(300); self.poll.timeout.connect(self.poll_status)
        for signal in (window.editor.textChanged, window.top.textChanged, window.role.currentIndexChanged):
            signal.connect(self.schedule)
        # All source loads (cell switches, undo, import and project changes) come through this list.
        window.files.model().rowsInserted.connect(self.schedule)
        window.files.model().rowsRemoved.connect(self.schedule)
        window.files.model().modelReset.connect(self.schedule)

    def schedule(self, *_):
        if self.isVisible() and not self.closed: self.debounce.start()

    def showEvent(self, event):
        super().showEvent(event)
        self.start()
        if self.ready: self.view.page().runJavaScript('window.icstudioVga.setActive(true)')
        self.poll.start(); self.schedule()

    def hideEvent(self, event):
        self.poll.stop(); self.debounce.stop()
        if self.ready and not self.closed:
            self.view.page().runJavaScript('window.icstudioVga.setActive(false)')
        super().hideEvent(event)

    def start(self):
        if self.view or self.closed: return
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor
            from PySide6.QtWebEngineWidgets import QWebEngineView
            self.server = AssetServer()
            origin = self.server.url

            class LocalRequests(QWebEngineUrlRequestInterceptor):
                def interceptRequest(self, info):
                    url = info.requestUrl()
                    info.block(not (url.toString().startswith(origin) or url.scheme() in ('data', 'blob')))

            class LocalPage(QWebEnginePage):
                def acceptNavigationRequest(self, url, kind, main_frame):
                    return url.toString() == origin

            self.view = QWebEngineView(self)
            self.view.setAccessibleName('Interactive VGA display and inputs')
            self.view.setContextMenuPolicy(Qt.NoContextMenu)
            self.profile = QWebEngineProfile(self.view)  # Off the record: no browsing state on disk.
            self.interceptor = LocalRequests(self.profile); self.profile.setUrlRequestInterceptor(self.interceptor)
            self.page = LocalPage(self.profile, self.view); self.view.setPage(self.page)
            self.page.renderProcessTerminated.connect(self.renderer_stopped)
            self.view.loadFinished.connect(self.loaded)
            self.content.addWidget(self.view)
            self.deadline = time.monotonic() + 30
            self.view.setUrl(QUrl(origin))
            # A project switch deletes this widget; release its private HTTP listener too.
            self.destroyed.connect(self.server.close)
            QApplication.instance().aboutToQuit.connect(self.shutdown)
        except (ImportError, OSError, ValueError) as exc:
            if self.server: self.server.close(); self.server = None
            self.note.setText(str(exc) + '\nSee docs/VGA_PLAYGROUND.md for setup; the other digital tools remain available.')
            self.poll.stop()

    def loaded(self, success):
        if self.closed: return
        self.loaded_ok = success
        if not success:
            self.note.setText('VGA Playground could not load. Reload the preview to try again.')
            self.poll.stop(); return
        self.poll_status()

    def poll_status(self):
        if not self.view or self.closed or not self.loaded_ok: return
        expression = 'window.icstudioVga && JSON.stringify(window.icstudioVga.' + ('status' if self.ready else 'presets') + ')'
        self.view.page().runJavaScript(expression, self.receive_status)

    def receive_status(self, raw):
        if self.closed: return
        if not raw:
            if time.monotonic() > self.deadline:
                self.note.setText('VGA Playground did not start. Reload the preview to try again.'); self.poll.stop()
            return
        try:
            value = json.loads(raw)
            if not self.ready:
                self.presets = value
                self.preset.clear()
                for preset in value: self.preset.addItem(preset['name'])
                self.ready = True; self.create.setEnabled(True)
                self.view.page().runJavaScript('window.icstudioVga.setActive(' + str(self.isVisible()).lower() + ')')
                self.update_preview()
            else:
                label = {'running': 'Live preview', 'compiling': 'Compiling', 'error': 'Preview unavailable', 'ready': 'Ready'}[value['state']]
                self.note.setText(label + ' · ' + value['message'][:2000])
        except (TypeError, ValueError, KeyError):
            self.note.setText('Unexpected VGA Playground response. Rebuild the assets and reload the preview.')

    def update_preview(self):
        if not self.ready or self.closed or not self.isVisible(): return
        w = self.window
        try:
            w.check_project(); w.sync_file()
            value = dict(w.config or {}, top=w.top.text().strip())
            payload = preview_inputs(value)
            serialized = json.dumps(payload)
            if serialized == self.last_inputs: return
            self.last_inputs = serialized
            self.view.page().runJavaScript('window.icstudioVga.setProject(' + serialized + ')')
        except (ValueError, KeyError) as exc:
            self.last_inputs = None
            self.view.page().runJavaScript('window.icstudioVga.invalidate(' + json.dumps(str(exc)) + ')')

    def create_cell(self):
        w = self.window; w.check_project()
        if not self.ready or not self.presets: return
        if w.dirty and not w.apply(): return
        if not w.studio.idle_edit() or not w.studio.flush_inspector(): return
        preset = self.presets[self.preset.currentIndex()]
        value = preset_config(preset)
        # The platform selection remains available to the normal synthesis flow.
        if w.config and w.config.get('platform'): value['platform'] = w.config['platform']
        base = 'VGA_' + preset['id']; name = base; index = 2
        names = {cell['name'].casefold() for cell in w.studio.project['cells']}
        while name.casefold() in names: name = base + '_' + str(index); index += 1
        created = []
        w.studio.commit(lambda p: created.append(digital_design.new_cell(p, name, value)), 'Create VGA preset cell')
        if created:
            w.workspace.switch_cell(created[0]); self.last_inputs = None; self.schedule()

    def renderer_stopped(self, *_):
        if self.closed: return
        self.ready = False; self.create.setEnabled(False); self.poll.stop()
        self.note.setText('The VGA renderer stopped. Your sources are still in Studio. Reload the preview to continue.')

    def reload(self):
        self.last_inputs = None; self.ready = False; self.loaded_ok = False; self.create.setEnabled(False)
        self.deadline = time.monotonic() + 30
        if self.view: self.view.reload()
        else: self.start()
        if self.view: self.poll.start()

    def shutdown(self):
        if self.closed: return
        self.closed = True; self.poll.stop(); self.debounce.stop()
        if self.view:
            self.view.stop(); self.view.page().setAudioMuted(True)
        if self.server: self.server.close()
