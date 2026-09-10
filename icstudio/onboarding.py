"""A shared starting point for examples, local engines and PDK setup."""
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QTextBrowser, QPushButton,
    QSplitter, QWidget, QCheckBox, QTabWidget, QFileDialog, QComboBox)
from .getting_started import examples, example_copy, default_pdk_roots, discover_pdks, readiness
from .model import digest, example
from .spice_program import find_ngspice


class SetupWorker(QThread):
    progress = Signal(str)
    completed = Signal(object)

    def __init__(self, registry, operation, entries, parent=None):
        super().__init__(parent)
        self.registry, self.operation, self.entries = registry, operation, entries

    def run(self):
        result = {'registered': [], 'errors': []}
        try:
            if self.operation == 'discover':
                result['found'], result['errors'] = discover_pdks(self.entries)
            else:
                for entry in self.entries:
                    if self.isInterruptionRequested():
                        result['errors'].append('Stopped before the next item. Completed registrations are retained.')
                        break
                    self.progress.emit('Checking ' + entry.get('name', entry['path']) + '…')
                    try:
                        key = (self.registry.install(Path(entry['path']) / 'package.json')
                               if entry['kind'] == 'package' else
                               self.registry.register_local(entry['path'], self.progress.emit))
                        self.registry.verify(key)
                        result['registered'].append(key)
                    except Exception as exc:
                        result['errors'].append(entry['path'] + ': ' + str(exc))
        except Exception as exc:
            result['errors'].append(str(exc))
        self.completed.emit(result)


class SetupDialog(QDialog):
    def pending(self):
        if not self.property('scanning'):return False
        self.state.setText('Finishing the current item before closing. Completed registrations are retained.')
        self.worker.requestInterruption();return True

    def reject(self):
        if not self.pending():super().reject()

    def closeEvent(self,event):
        if self.pending():event.ignore()
        else:super().closeEvent(event)


def label(text, large=False):
    widget = QLabel(text)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.PlainText)
    if large:
        widget.setStyleSheet('font-size:24px;font-weight:600;padding:6px 0;')
    return widget


class OnboardingMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initial_document = digest(self.project)

    def make_actions(self):
        super().make_actions()
        action = self.action(self.task_menus['File'], 'Start here / example gallery…', self.start_here)
        self.task_menus['File'].insertAction(self.task_menus['File'].actions()[0], action)
        self.action(self.task_menus['Help'], 'Getting started', lambda: self.open_editor_doc('GETTING_STARTED.md'))
        self.action(self.task_menus['Help'], 'Project roadmap', lambda: self.open_editor_doc('ROADMAP.md'))
        self.action(self.task_menus['Tools'], 'Set up an open PDK…', self.pdk_manager)
        self.reindex_commands()

    def set_project(self, project, path=None):
        super().set_project(project, path)
        gallery = getattr(self, '_start_dialog', None)
        if gallery and gallery.isVisible():
            gallery.accept()

    def _replace_document(self):
        if self.process or self.run_manager.busy:
            raise ValueError('Wait for active runs to finish before opening another project.')
        if not self.flush_inspector():
            return False
        if self.path is None and digest(self.project) == self._initial_document:
            return True
        return self.maybe_save()

    def open_gallery_example(self, entry):
        project = example_copy(entry)
        if not self._replace_document():
            return False
        self.set_project(project)
        self.mode_combo.setCurrentIndex(entry['mode'])
        engine = entry['engine']
        if engine != 'none':
            self.analysis_engine.setCurrentIndex(self.analysis_engine.findData(engine))
        self.inspector_tabs.setCurrentIndex(1 if engine != 'none' else 0)
        self.results_dock.hide()
        self.statusBar().showMessage('Example copy opened · ' + entry['expected'], 20000)
        QTimer.singleShot(80, lambda: (self.schematic.fit(), self.layout.fit()))
        return True

    def start_here(self):
        existing = getattr(self, '_start_dialog', None)
        if existing and existing.isVisible():
            existing.raise_()
            return existing
        dlg = QDialog(self); dlg.setWindowTitle('Start here · IC Design Studio'); dlg.resize(1080, 740)
        outer = QVBoxLayout(dlg); outer.setContentsMargins(24, 20, 24, 20)
        outer.addWidget(label('From first circuit to a reusable design.', True))
        outer.addWidget(label('Choose a short example. Each opens as an independent copy with its analysis already configured.'))
        actions = QHBoxLayout(); outer.addLayout(actions)
        for title, fn in [('New project…', self.new_project), ('Open project…', self.open_project),
                          ('Import Xschem…', self.migrate_xschem_file), ('Set up a PDK…', self.pdk_manager)]:
            button = QPushButton(title); button.clicked.connect(lambda checked=False, fn=fn: self.guard(fn)); actions.addWidget(button)
        split = QSplitter(); outer.addWidget(split, 1)
        left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(0, 14, 12, 0)
        search = QLineEdit(); search.setPlaceholderText('Find an example: waveform, layout, hierarchy…'); search.setAccessibleName('Find an example'); lv.addWidget(search)
        items = QListWidget(); items.setAccessibleName('Example gallery'); lv.addWidget(items); split.addWidget(left)
        right = QWidget(); rv = QVBoxLayout(right); rv.setContentsMargins(12, 14, 0, 0)
        details = QTextBrowser(); details.setOpenExternalLinks(False)
        font = details.font(); font.setPointSize(11); details.setFont(font)
        details.document().setDefaultStyleSheet('h2 { margin-bottom: 20px; } p { margin-top: 14px; margin-bottom: 14px; } li { margin-bottom: 12px; }')
        rv.addWidget(details, 1)
        engine_status = label(''); rv.addWidget(engine_status)
        open_button = QPushButton('Open a copy'); open_button.setDefault(True); open_button.setStyleSheet('QPushButton { background: #315ed4; color: white; border: none; border-radius: 6px; padding: 11px; font-weight: 600; } QPushButton:disabled { background: #475367; color: #b0b6c2; }'); rv.addWidget(open_button)
        setup = QPushButton('Engine setup…'); setup.clicked.connect(self.engine_dialog); rv.addWidget(setup)
        guide = QPushButton('Read the getting-started guide'); guide.clicked.connect(lambda: self.open_editor_doc('GETTING_STARTED.md')); rv.addWidget(guide)
        split.addWidget(right); split.setSizes([420, 570])
        def selected():
            item = items.currentItem(); entry = item.data(Qt.UserRole) if item else None
            open_button.setEnabled(entry is not None)
            if entry is None:
                details.setPlainText('No matching examples. Try a broader search.'); engine_status.clear(); return
            details.setMarkdown('## ' + entry['title'] + '\n\n' + entry['summary'] + '\n\n**What to expect**\n\n' + entry['expected'] +
                                '\n\n**Try it**\n\n' + '\n'.join(f'{i}. {s}' for i, s in enumerate(entry['steps'], 1)))
            needs = entry['engine'] == 'ngspice'
            available = find_ngspice(self.settings.value('engine/ngspice', ''))
            engine_status.setText(('ngspice found · no external PDK needed' if available else 'ngspice needed · open Engine setup to select it') if needs else
                                  ('Ready to explore · no simulator needed' if entry['engine'] == 'none' else 'Ready to run · included educational solver'))
        def fill(text=''):
            items.clear()
            for entry in examples():
                if text.casefold() in ' '.join(str(v) for v in entry.values()).casefold():
                    item = QListWidgetItem(entry['title'] + '\n' + entry['category']); item.setData(Qt.UserRole, entry); items.addItem(item)
            items.setCurrentRow(0); selected()
        def open_copy():
            item = items.currentItem()
            if item and self.open_gallery_example(item.data(Qt.UserRole)):
                dlg.accept()
        items.currentItemChanged.connect(selected); search.textChanged.connect(fill)
        items.itemActivated.connect(lambda _: self.guard(open_copy)); open_button.clicked.connect(lambda: self.guard(open_copy))
        bottom = QHBoxLayout(); outer.addLayout(bottom)
        show = QCheckBox('Show on startup'); show.setChecked(self.settings.value('onboarding/show', True, type=bool))
        show.toggled.connect(lambda checked: self.settings.setValue('onboarding/show', checked)); bottom.addWidget(show); bottom.addStretch()
        close = QPushButton('Continue to workspace'); close.clicked.connect(dlg.close); bottom.addWidget(close)
        dlg.example_list, dlg.search, dlg.open_button = items, search, open_button
        dlg.details, dlg.engine_status = details, engine_status
        self._start_dialog = dlg; fill(); dlg.show(); return dlg

    def pdk_manager(self, initial_folder=None):
        existing = getattr(self, '_pdk_dialog', None)
        if existing and existing.isVisible():
            existing.raise_(); return existing
        dlg = SetupDialog(self); dlg.setWindowTitle('Open PDK setup'); dlg.resize(1080, 790)
        outer = QVBoxLayout(dlg); outer.setContentsMargins(24, 20, 24, 20)
        outer.addWidget(label('Bring your process into the workspace.', True))
        outer.addWidget(label('1  Find local PDKs     →     2  Check and register     →     3  Start a linked project'))
        tabs = QTabWidget(); outer.addWidget(tabs, 1)
        discover_page = QWidget(); dv = QVBoxLayout(discover_page); tabs.addTab(discover_page, 'Find and install')
        dv.addWidget(label('Use included PDKs installs the bundled GF180MCU and SKY130 simulation packages offline. You can also add another installed PDK or an extracted package collection.'))
        candidates = QListWidget(); candidates.setAccessibleName('Discovered PDKs'); dv.addWidget(candidates, 1)
        buttons = []; row = QHBoxLayout(); dv.addLayout(row)
        registered_page = QWidget(); pv = QVBoxLayout(registered_page); tabs.addTab(registered_page, 'Registered revisions')
        registered = QListWidget(); registered.setAccessibleName('Registered PDK revisions'); pv.addWidget(registered, 1)
        detail = label(''); detail.setTextInteractionFlags(Qt.TextSelectableByMouse); pv.addWidget(detail)
        project_row = QHBoxLayout(); pv.addLayout(project_row)
        state = label('Choose Use included PDKs to start with GF180MCU or SKY130. Gallery examples already include their model setup.'); outer.addWidget(state)
        log = QTextBrowser(); log.setMaximumHeight(95); log.hide(); outer.addWidget(log)
        def selected():
            it = registered.currentItem()
            if not it: detail.setText('No registered revisions yet. Use Find & install.'); return
            try:
                m = self.pdk_registry.manifest(it.data(Qt.UserRole))
                info = readiness(m['technology'], find_ngspice(self.settings.value('engine/ngspice', '')),
                                 self.project.get('simulation_runtime', {}).get('osdi', []))
                from .process_adapters import capability_text
                from .model import clone
                technology = clone(m['technology'])
                technology['package_lock'] = {key: m[key] for key in ('id', 'revision', 'files')}
                detail.setText(f"{info['placeable']} placeable / {info['indexed']} indexed symbols · corners: {', '.join(info['corners'])}\n" +
                               info['runtime'] + '\n' + capability_text(technology, True))
            except Exception as exc: detail.setText(str(exc))
        def refresh(keys=()):
            old = registered.currentItem().data(Qt.UserRole) if registered.currentItem() else None
            registered.clear()
            for entry in self.pdk_registry.entries():
                key = entry['id'] + '@' + entry['revision']
                it = QListWidgetItem(entry.get('technology', {}).get('name', entry['id']) + '\n' + key)
                it.setData(Qt.UserRole, key); registered.addItem(it)
                if key in keys or key == old: registered.setCurrentItem(it)
            if registered.currentRow() < 0: registered.setCurrentRow(0)
            selected()
        registered.currentItemChanged.connect(selected)
        def busy(value):
            for button in buttons: button.setEnabled(not value)
            candidates.setEnabled(not value); registered.setEnabled(not value)
            dlg.setProperty('scanning', value)
        def complete(result):
            dlg.last_result = result
            if 'found' in result:
                known = {candidates.item(i).data(Qt.UserRole)['path'] for i in range(candidates.count())}
                for entry in result['found']:
                    if entry['path'] in known: continue
                    item = QListWidgetItem(entry['name'] + ' · ' + entry['kind'] + '\n' + entry['path'])
                    item.setData(Qt.UserRole, entry); item.setCheckState(Qt.Checked); candidates.addItem(item)
                state.setText(f'{candidates.count()} PDK candidates. Review the selection, then Check and register.' if candidates.count() else
                              'No supported installation found. Add its folder, or open the installation guide below. A raw SKY130/GF180 source checkout must first be built with open_pdks or installed through Ciel.')
            else:
                keys = result['registered']; refresh(keys)
                state.setText(f'{len(keys)} revisions registered and checksummed. Select a revision to start a project.' if keys else 'No revisions registered. Review the details below.')
                if keys: tabs.setCurrentIndex(1)
            log.setPlainText('\n\n'.join(result['errors'])); log.setVisible(bool(result['errors']))
        def start(operation, entries):
            if dlg.property('scanning'): return
            if not entries: state.setText('Select at least one PDK.'); return
            busy(True); log.hide(); state.setText('Finding PDKs…' if operation == 'discover' else 'Checking model dependencies and registering revisions…')
            worker = SetupWorker(self.pdk_registry, operation, entries, dlg); dlg.worker = worker; self._setup_worker = worker
            worker.progress.connect(state.setText); worker.completed.connect(complete); worker.finished.connect(lambda: busy(False)); worker.start()
        def browse():
            path = QFileDialog.getExistingDirectory(dlg, 'Select PDK installation or extracted package collection')
            if path: start('discover', [path])
        def register():
            entries = [candidates.item(i).data(Qt.UserRole) for i in range(candidates.count()) if candidates.item(i).checkState() == Qt.Checked]
            start('register', entries)
        def link(new=False):
            try:
                it = registered.currentItem()
                if not it: state.setText('Select a registered revision first.'); return
                if self.process or self.run_manager.busy: raise ValueError('Wait for active runs to finish before linking a PDK.')
                from .catalog import link_technology
                tech = self.pdk_registry.technology(it.data(Qt.UserRole))
                if new:
                    project = example('empty'); link_technology(project, tech)
                    if not self._replace_document(): return
                    self.set_project(project); self.sync_technology()
                else:
                    if not self.flush_inspector(): return
                    self.commit(lambda p: link_technology(p, tech), 'Link project to PDK'); self.sync_technology()
                state.setText('Linked. Open Devices to choose a model; select a corner in the Analysis inspector. Save your project to retain the revision link.')
            except Exception as exc: state.setText(str(exc))
        def use_bundled():
            from .bundled_pdks import packages
            start('register', packages())
        for text, fn in [('Use included PDKs', lambda: self.guard(use_bundled)), ('Find installed PDKs', lambda: start('discover', default_pdk_roots())), ('Add folder…', browse), ('Check and register', register)]:
            b = QPushButton(text); b.clicked.connect(fn); row.addWidget(b); buttons.append(b)
            if text == 'Check and register': b.setStyleSheet('background: #315ed4; color: white; padding: 9px; border-radius: 6px;')
        for text, fn in [('New project with this PDK', lambda: link(True)), ('Link current project', link),
                         ('Manage / verify revisions…', lambda: super(OnboardingMixin, self).pdk_manager())]:
            b = QPushButton(text); b.clicked.connect(fn); project_row.addWidget(b); buttons.append(b)
            if text == 'New project with this PDK': b.setStyleSheet('background: #315ed4; color: white; padding: 9px; border-radius: 6px;')
        help_row = QHBoxLayout(); outer.addLayout(help_row)
        for text, fn in [('PDK installation guide', lambda: self.open_editor_doc('PDK_GUIDE.md')),
                         ('Engine setup…', self.engine_dialog), ('OSDI runtime…', self.runtime_dialog)]:
            b = QPushButton(text); b.clicked.connect(lambda checked=False, fn=fn: self.guard(fn)); help_row.addWidget(b); buttons.append(b)
        guide_row = QHBoxLayout(); outer.addLayout(guide_row)
        guide_row.addWidget(label('Upstream installation:'))
        family = QComboBox(); family.addItem('SKY130 / GF180MCU · Ciel', 'https://github.com/fossi-foundation/ciel')
        family.addItem('IHP SG13G2', 'https://ihp-open-pdk-docs.readthedocs.io/en/latest/install/installation.html')
        family.addItem('Build SKY130 / GF180MCU · open_pdks', 'https://github.com/fossi-foundation/open-pdks')
        guide_row.addWidget(family, 1); upstream = QPushButton('Open official guide'); upstream.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(family.currentData()))); guide_row.addWidget(upstream)
        close = QPushButton('Done'); close.clicked.connect(dlg.close); guide_row.addWidget(close)
        dlg.candidates, dlg.registered, dlg.state, dlg.tabs = candidates, registered, state, tabs
        dlg.start_operation, dlg.register_selected, dlg.link_revision = start, register, link
        self._pdk_dialog = dlg; self._setup_dialog = dlg; refresh(); dlg.show()
        if initial_folder: start('discover', [initial_folder])
        return dlg

    def closeEvent(self, event):
        worker = getattr(self, '_setup_worker', None)
        if worker and worker.isRunning():
            worker.requestInterruption()
            self.statusBar().showMessage('PDK setup is finishing its current item. Close the app after it finishes.', 15000)
            event.ignore(); return
        super().closeEvent(event)
