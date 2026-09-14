"""Document-first digital workspace with linked panes and a quiet native chrome.

The layout borrows navigation/inspector separation from Apple's HIG and
side-by-side cross-selection from CAD tools. It uses Studio's own Qt palette,
icons, commands and document lifecycle on every supported desktop.
"""
from __future__ import annotations

import difflib
import json

from PySide6.QtCore import Qt, QTimer, QObject, QEvent
from PySide6.QtGui import QColor, QTextCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QToolButton, QMenu, QSplitter, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QComboBox, QPlainTextEdit, QStackedWidget, QFormLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QButtonGroup,
    QToolBox, QSizePolicy, QDialog, QDialogButtonBox)

from .model import clone
from .ui_style import icon, palette
from .digital_planning import LABELS, PHYSICAL, usable, data_of


def panel(name, margins=(12, 10, 12, 10)):
    widget = QWidget(); widget.setObjectName(name)
    layout = QVBoxLayout(widget); layout.setContentsMargins(*margins); layout.setSpacing(8)
    return widget, layout


class DigitalShell(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.w = window; self.key = None; self.source_key = None; self.loading = False
        self.icon_buttons=[];self.selection = None; self.legacy = window.widget()
        # Extract the useful editors from the former nested dock layout.
        source_page = window.tabs.widget(0)
        source_split = source_page.findChild(QSplitter)
        source_split.widget(0).hide()
        editor_host = source_split.widget(1)
        result_page = window.tabs.widget(1)
        self.legacy.hide()
        host, root = panel('digitalStudio', (0, 0, 0, 0))
        self.host = host;host.installEventFilter(self)
        head = QWidget(); head.setObjectName('digitalHeader'); bar = QHBoxLayout(head)
        bar.setContentsMargins(16, 12, 16, 12); bar.setSpacing(10)
        self.button(bar, 'Circuit workspace', window.studio.leave_digital_workspace, 'sidebar')
        title = QWidget(); tv = QVBoxLayout(title); tv.setContentsMargins(4, 0, 8, 0); tv.setSpacing(2)
        self.title = QLabel('Digital design'); self.title.setProperty('role', 'title'); tv.addWidget(self.title)
        self.subtitle = QLabel('RTL · verification · implementation'); self.subtitle.setProperty('role', 'muted'); tv.addWidget(self.subtitle)
        bar.addWidget(title); bar.addStretch()
        self.mode_group = QButtonGroup(host); self.mode_group.setExclusive(True)
        for i, text in enumerate(('Design', 'Debug', 'Implement')):
            button = QPushButton(text); button.setCheckable(True); button.setAccessibleName(text+' workspace')
            self.mode_group.addButton(button, i); bar.addWidget(button)
        self.mode_group.idClicked.connect(self.mode); self.mode_group.button(0).setChecked(True)
        self.button(bar, '', self.toggle_navigator, 'sidebar', 'Show or hide digital navigator')
        self.button(bar, '', self.toggle_inspector, 'inspector', 'Show or hide digital inspector')
        self.target_button = QToolButton(); self.target_button.setText('Run to placement'); self.target_button.setProperty('role', 'primary')
        self.target_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon); self.target_button.setIcon(icon('play', '#ffffff'))
        self.target_button.setPopupMode(QToolButton.MenuButtonPopup); self.target = 'place'
        menu = QMenu(self.target_button)
        for title, target in (('Verify block', 'verify'), ('Run to placement', 'place'), ('Run to routing', 'route'), ('Run to GDS', 'finish')):
            action = menu.addAction(title); action.triggered.connect(lambda checked=False, t=target, label=title:self.choose_target(t,label))
        self.target_button.setMenu(menu); self.target_button.clicked.connect(lambda:window.attempt(lambda:window.flow.start(self.target)))
        self.target_button.setAccessibleName('Run digital flow target'); bar.addWidget(self.target_button); root.addWidget(head)
        self.outer = QSplitter(); self.outer.setObjectName('digitalColumns'); self.outer.setHandleWidth(1); root.addWidget(self.outer, 1)
        self.navigator, nv = panel('digitalNavigator')
        label = QLabel('PROJECT'); label.setProperty('role', 'section'); nv.addWidget(label); nv.addWidget(window.workspace.cells)
        self.search = QLineEdit(); self.search.setPlaceholderText('Find a source or object…'); self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('Search digital project'); nv.addWidget(self.search)
        self.navigation = QTabWidget(); self.navigation.setDocumentMode(True); nv.addWidget(self.navigation, 1)
        files, fv = panel('digitalFiles', (0, 0, 0, 0)); fv.addWidget(window.files)
        actions = QHBoxLayout(); fv.addLayout(actions)
        self.button(actions, 'Add', window.add_file, 'plus'); self.button(actions, 'Import', window.import_sources, 'folder')
        self.navigation.addTab(files, 'Sources')
        self.hierarchy = QTreeWidget(); self.hierarchy.setHeaderHidden(True); self.hierarchy.setUniformRowHeights(True)
        self.hierarchy.setAccessibleName('Elaborated digital hierarchy'); self.navigation.addTab(self.hierarchy, 'Hierarchy')
        self.hierarchy.itemActivated.connect(self.probe_tree); self.hierarchy.itemClicked.connect(self.probe_tree)
        self.search.textChanged.connect(self.filter)
        self.button(nv, 'New RTL cell', window.workspace.new_cell, 'plus')
        self.navigator.setMinimumWidth(205); self.outer.addWidget(self.navigator)
        center, cv = panel('digitalDocuments', (10, 10, 10, 6)); self.outer.addWidget(center)
        controls = QHBoxLayout(); cv.addLayout(controls)
        controls.addWidget(QLabel('Stage')); controls.addWidget(window.stage); controls.addWidget(window.simulator)
        window.run_button.setText('Run stage'); controls.addWidget(window.run_button)
        self.tools_button=self.button(controls, 'Included tools', window.configure_tools)
        self.tools_button.setAccessibleName('Digital tools and setup')
        controls.addStretch(); self.button(controls, 'Constraints', window.workspace.constraints, 'settings')
        more = QToolButton(); more.setText('More'); more.setPopupMode(QToolButton.InstantPopup); menu = QMenu(more)
        for text, callback in (('Language server…', lambda:window.language.start()), ('Stop language server', lambda:window.language.stop()), ('Remove source', window.remove_file), ('Reload saved sources', window.reload_sources), ('Physical settings…', window.workspace.physical_settings), ('Regression cases…', window.workspace.test_cases),
                               ('Tools and setup…', window.configure_tools), ('Jobs folder…', window.workspace.jobs_folder),
                               ('Publish symbol', window.workspace.publish), ('Attach implemented macro', window.workspace.attach_layout),
                               ('Export implemented macro…', window.workspace.export_macro), ('Export flow bundle…', window.export), ('Reset digital layout', self.reset_layout)):
            menu.addAction(text).triggered.connect(lambda checked=False, fn=callback:window.attempt(fn))
        more.setMenu(menu); controls.addWidget(more)
        self.documents = QSplitter(); self.documents.setHandleWidth(4); cv.addWidget(self.documents, 1)
        self.source, sv = panel('digitalSource', (0, 0, 0, 0)); self.source.setMinimumWidth(200);self.source.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Expanding);self.documents.addWidget(self.source)
        source_header = QHBoxLayout(); sv.addLayout(source_header)
        self.filename = QLabel('Source'); self.filename.setProperty('role', 'subtitle'); source_header.addWidget(self.filename, 1)
        self.source_mode = QComboBox(); self.source_mode.addItems(['Working copy', 'Run snapshot']); self.source_mode.setAccessibleName('Source revision')
        source_header.addWidget(self.source_mode); self.button(source_header, '', self.diff, 'split', 'Compare captured source with working copy')
        self.source_stack = QStackedWidget(); sv.addWidget(self.source_stack, 1); self.source_stack.addWidget(editor_host)
        captured, cap = panel('capturedSource', (0, 0, 0, 0)); self.captured_label = QLabel(); self.captured_label.setWordWrap(True); cap.addWidget(self.captured_label)
        self.captured_files = QComboBox(); self.captured_files.setAccessibleName('Captured source file'); cap.addWidget(self.captured_files)
        from .digital_editor import SourceEditor
        self.captured_editor = SourceEditor(); self.captured_editor.setReadOnly(True); self.captured_editor.setFont(window.editor.font())
        self.captured_editor.setAccessibleName('Read-only source from selected run'); cap.addWidget(self.captured_editor, 1)
        from .digital_ui import RTLHighlighter
        self.captured_highlighter = RTLHighlighter(self.captured_editor.document(),window.studio.dark); self.source_stack.addWidget(captured)
        self.source_mode.currentIndexChanged.connect(self.change_source_mode)
        self.captured_files.currentIndexChanged.connect(self.load_captured_file)
        source_actions = QHBoxLayout(); sv.addLayout(source_actions); source_actions.addWidget(window.apply_button)
        self.button(source_actions, 'Source settings', window.source_settings); source_actions.addStretch()
        self.analysis, av = panel('digitalAnalysis', (4, 0, 0, 0));self.analysis.setMinimumWidth(400);self.analysis.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Expanding);self.documents.addWidget(self.analysis)
        runbar = QHBoxLayout(); av.addLayout(runbar); window.runs.setMinimumWidth(120); runbar.addWidget(window.runs, 1)
        self.button(runbar, '', window.replay, 'undo', 'Rerun captured inputs')
        self.stop_button = self.button(runbar, '', self.stop, 'stop', 'Stop selected run or active flow')
        av.addWidget(window.summary)
        self.metrics = QLabel('Run a stage to inspect its results.'); self.metrics.setWordWrap(True); self.metrics.setObjectName('digitalMetrics'); av.addWidget(self.metrics)
        categories = QHBoxLayout(); av.addLayout(categories)
        self.result_choice = QComboBox(); self.result_choice.setAccessibleName('Digital result view')
        for i in range(window.result_tabs.count()):
            self.result_choice.addItem(window.result_tabs.tabText(i), i)
        categories.addWidget(self.result_choice); categories.addStretch()
        self.button(categories, 'Logic cone', self.open_cone, 'chip')
        self.button(categories, 'Split', lambda:self.mode(1), 'split', 'Show source and results together')
        window.result_tabs.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Ignored);window.result_tabs.setMinimumSize(0,0);window.result_tabs.setDocumentMode(True); window.result_tabs.tabBar().hide(); av.addWidget(window.result_tabs, 1)
        self.result_choice.currentIndexChanged.connect(lambda i:window.result_tabs.setCurrentIndex(i))
        window.result_tabs.currentChanged.connect(self.result_choice.setCurrentIndex)
        self.flow_table = QTableWidget(1, 7); self.flow_table.setObjectName('digitalFlowStages')
        self.flow_stages = ['mapped', *PHYSICAL, 'timing']
        self.flow_table.setHorizontalHeaderLabels([LABELS[s] for s in self.flow_stages]); self.flow_table.verticalHeader().hide()
        self.flow_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.flow_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.flow_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.flow_table.setShowGrid(False)
        self.flow_table.setFixedHeight(76); self.flow_table.setAccessibleName('Digital implementation progress')
        self.flow_table.cellClicked.connect(self.select_stage); cv.addWidget(self.flow_table)
        progress = QHBoxLayout(); cv.addLayout(progress); self.flow_label = QLabel('Choose a target to build its dependencies.'); self.flow_label.setProperty('role', 'muted')
        progress.addWidget(self.flow_label, 1); self.resume_button = self.button(progress, 'Resume', lambda:window.flow.resume(), 'play')
        self.inspector, iv = panel('digitalInspector')
        heading = QLabel('INSPECTOR'); heading.setProperty('role', 'section'); iv.addWidget(heading)
        self.selection_title = QLabel('Design context'); self.selection_title.setProperty('role', 'subtitle'); self.selection_title.setWordWrap(True); iv.addWidget(self.selection_title)
        self.selection_details = QPlainTextEdit(); self.selection_details.setReadOnly(True); self.selection_details.setFixedHeight(110)
        self.selection_details.setAccessibleName('Selected object details'); iv.addWidget(self.selection_details)
        self.setup = QToolBox(); iv.addWidget(self.setup, 1)
        settings, settings_layout = panel('digitalSetup', (2, 8, 2, 8)); form = QFormLayout(); settings_layout.addLayout(form)
        form.addRow('Top module', window.top); form.addRow('Testbench', window.testbench)
        settings_layout.addWidget(window.workspace.platform)
        self.button(settings_layout, 'Choose platform', window.workspace.import_platform, 'chip')
        self.button(settings_layout, 'Timing constraints', window.workspace.constraints, 'settings')
        self.button(settings_layout, 'Floorplan and routing', window.workspace.physical_settings, 'rect')
        settings_layout.addWidget(window.workspace.coverage); settings_layout.addWidget(window.workspace.use_selected)
        window.workspace.use_selected.setText('Pin selected upstream run')
        window.workspace.use_selected.setToolTip('Advanced: use the explicitly selected run instead of automatic dependency selection.')
        settings_layout.addStretch(); self.setup.addItem(settings, 'Design setup')
        self.setup.addItem(window.workspace.views, 'Cell views')
        self.inspector.setMinimumWidth(200); self.inspector.setMaximumWidth(320); self.outer.addWidget(self.inspector)
        status = QWidget(); status.setObjectName('digitalStatus'); status_row = QHBoxLayout(status); status_row.setContentsMargins(14, 5, 14, 5)
        window.message.setWordWrap(True); status_row.addWidget(window.message, 1)
        self.status_hint = QLabel('F5 Run stage · Ctrl+Alt+1 Design · Ctrl+Alt+2 Debug · Ctrl+Alt+3 Implement')
        self.status_hint.setProperty('role', 'muted'); status_row.addWidget(self.status_hint); root.addWidget(status)
        window.setWidget(host); window.setTitleBarWidget(QWidget()); self.legacy.setParent(window); self.legacy.hide()
        self.documents.setSizes([500, 650]); self.outer.setSizes([220, 1050, 250])
        self.documents.setChildrenCollapsible(False); self.outer.setChildrenCollapsible(False)
        for i in range(3):
            QShortcut(QKeySequence('Ctrl+Alt+'+str(i+1)), host, activated=lambda value=i:self.mode(value))
        window.files.currentRowChanged.connect(self.source_changed)
        window.studio.run_manager.changed.connect(self.refresh)
        window.flow.changed.connect(self.refresh)
        self.style(); self.restore_layout(); self.refresh()

    def eventFilter(self,obj,event):
        if obj is self.host and event.type()==QEvent.Resize and hasattr(self,'inspector'):
            self.status_hint.setVisible(event.size().width()>1400)
        return False

    def style(self):
        p = palette(self.w.studio.dark)
        for button,name in self.icon_buttons:button.setIcon(icon(name,p['muted']))
        self.host.setStyleSheet('''
            QWidget#digitalHeader { border-bottom: 1px solid %(line)s; }
            QWidget#digitalNavigator, QWidget#digitalInspector { background: %(panel)s; }
            QToolButton[role="primary"] { background: #345fd1; color: white; border: 0; border-radius: 6px; padding: 7px 14px; }
            QToolButton[role="primary"]:disabled { background: %(line)s; }
            QToolBox::tab { border: 0; padding: 8px; text-align: left; background: %(panel)s; }
            QToolBox::tab:selected { color: %(accent)s; font-weight: 600; }
            QLabel#digitalMetrics { padding: 9px; background: %(panel)s; border-radius: 6px; }
            QTableWidget { gridline-color: transparent; }
            QWidget#digitalStatus { border-top: 1px solid %(line)s; }
        ''' % p)

    def button(self, layout, text, callback, image=None, tip=None):
        button = QPushButton(text); button.setAccessibleName(tip or text)
        if image:
            self.icon_buttons.append((button,image))
            button.setIcon(icon(image, palette(self.w.studio.dark)['muted']))
        if tip:
            button.setToolTip(tip)
        button.clicked.connect(lambda checked=False:self.w.attempt(callback)); layout.addWidget(button)
        return button

    def choose_target(self, target, label):
        self.target = target; self.target_button.setText(label)
        self.w.attempt(lambda:self.w.flow.start(target))

    def mode(self, mode):
        self.mode_group.button(mode).setChecked(True)
        self.source.setVisible(mode != 2); self.analysis.setVisible(mode != 0)
        if mode == 0:
            self.source_mode.setCurrentIndex(0); self.source.show(); self.documents.setSizes([650, 500])
        elif mode == 1:
            self.documents.setSizes([500, 650])
        else:
            widget = self.w.workspace.physical.parentWidget()
            self.w.result_tabs.setCurrentWidget(widget)
        self.save_layout()

    def toggle_navigator(self):
        self.navigator.setVisible(not self.navigator.isVisible()); self.save_layout()

    def toggle_inspector(self):
        self.inspector.setVisible(not self.inspector.isVisible()); self.save_layout()

    def reset_layout(self):
        self.navigator.show(); self.inspector.show(); self.outer.setSizes([220, 1050, 250]); self.mode(1)

    def save_layout(self):
        settings = self.w.studio.settings
        settings.setValue('digital/workspace/columns', self.outer.saveState())
        settings.setValue('digital/workspace/documents', self.documents.saveState())
        settings.setValue('digital/workspace/mode', self.mode_group.checkedId())
        settings.setValue('digital/workspace/navigator', not self.navigator.isHidden())
        settings.setValue('digital/workspace/inspector', not self.inspector.isHidden())

    def restore_layout(self):
        settings = self.w.studio.settings
        for name, splitter in (('columns', self.outer), ('documents', self.documents)):
            state = settings.value('digital/workspace/'+name)
            if state:
                splitter.restoreState(state)
        mode = int(settings.value('digital/workspace/mode', 1))
        self.mode_group.button(mode if mode in (0,1,2) else 1).setChecked(True)
        self.source.setVisible(mode != 2);self.analysis.setVisible(mode != 0)
        for name, widget in (('navigator',self.navigator),('inspector',self.inspector)):
            widget.setVisible(settings.value('digital/workspace/'+name, name!='inspector' or self.w.studio.width()>=1400, type=bool))
        self.outer.splitterMoved.connect(self.save_layout); self.documents.splitterMoved.connect(self.save_layout)

    def reveal_source(self):
        self.source.show(); self.analysis.show(); self.mode_group.button(1).setChecked(True)

    def source_changed(self, *_):
        item = self.w.files.currentItem(); self.filename.setText(item.text() if item else 'Source')

    def change_source_mode(self, index):
        self.source_stack.setCurrentIndex(index)
        if index == 1:
            row = self.w.selected_run()
            if row and self.source_key != row['id']:
                self.show_captured({'path': self.w.files.currentItem().text() if self.w.files.currentItem() else ''}, row)

    def show_captured(self, location, row=None):
        from .digital_design import config
        row = row or self.w.selected_run()
        if not row:
            return
        self.source_key = row['id']
        self.captured_config = config(row['job']['project'], row['job']['cell'])
        self.captured_label.setText(row['name'] + ' · revision ' + str(row['job']['project']['revision']) + ' · read only')
        self.captured_files.blockSignals(True); self.captured_files.clear()
        for file in self.captured_config['files']:
            self.captured_files.addItem(file['path'])
        path = location.get('path', '')
        index = next((i for i,f in enumerate(self.captured_config['files']) if path == f['path'] or path.endswith('/'+f['path'])), -1)
        self.captured_files.setCurrentIndex(max(0,index)); self.captured_files.blockSignals(False)
        self.load_captured_file(); self.source_mode.setCurrentIndex(1); self.reveal_source()
        block = self.captured_editor.document().findBlockByLineNumber(max(0, int(location.get('line',1))-1))
        if block.isValid():
            self.captured_editor.setTextCursor(QTextCursor(block)); self.captured_editor.centerCursor()

    def load_captured_file(self, *_):
        config = getattr(self, 'captured_config', None); i = self.captured_files.currentIndex()
        self.captured_editor.setPlainText(config['files'][i]['text'] if config and i >= 0 else '')

    def diff(self):
        row = self.w.selected_run()
        if not row:
            raise ValueError('Select a captured run to compare its source.')
        from .digital_design import config
        old = config(row['job']['project'], row['job']['cell']); self.w.sync_file()
        previous = {f['path']:f['text'] for f in old['files']}; current = {f['path']:f['text'] for f in self.w.config['files']}
        text = ''.join(''.join(difflib.unified_diff(previous.get(p,'').splitlines(True),current.get(p,'').splitlines(True),fromfile='Captured/'+p,tofile='Working/'+p)) for p in sorted(previous.keys() | current.keys()))
        dialog = QDialog(self.w); dialog.setWindowTitle('Captured source changes'); dialog.resize(950, 650); layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit(); editor.setReadOnly(True); editor.setFont(self.w.editor.font()); editor.setPlainText(text or 'The captured sources match the working copy.'); layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons); dialog.exec()

    def filter(self, text):
        text = text.casefold()
        for i in range(self.w.files.count()):
            item = self.w.files.item(i); item.setHidden(text not in item.text().casefold())
        for i in range(self.hierarchy.topLevelItemCount()):
            parent = self.hierarchy.topLevelItem(i); visible = False
            for j in range(parent.childCount()):
                item = parent.child(j); show = text in item.text(0).casefold() or text in parent.text(0).casefold()
                item.setHidden(not show); visible |= show
            parent.setHidden(not visible and text not in parent.text(0).casefold())

    def probe_tree(self, item, *_):
        data = item.data(0, Qt.UserRole)
        if data:
            self.w.workspace.probe(data)

    def inspect(self, item, selection=None):
        self.selection = selection; self.selected_item = item
        self.selection_title.setText(item.get('name', 'Selection'))
        lines = [item.get('module', ''), item.get('type', item.get('kind', ''))]
        if item.get('mapping'):
            lines.append('Source mapping: ' + item['mapping'])
        lines.extend(f'{p}: {len(bits)} bit(s)' for p,bits in item.get('connections',{}).items())
        self.selection_details.setPlainText('\n'.join(lines))

    def open_cone(self):
        from .digital_logic_ui import LogicView
        item = getattr(self, 'selected_item', None)
        if not item:
            item = next((i for i in self.w.workspace.index if i['kind']=='cell'), None)
        if not item:
            raise ValueError('Run elaboration or synthesis, then select a net or instance.')
        if not hasattr(self, 'logic'):
            self.logic = LogicView(self.w.workspace)
            self.w.result_tabs.addTab(self.logic, 'Logic cone'); self.result_choice.addItem('Logic cone')
        self.logic.load(self.w.workspace.index, item); self.w.result_tabs.setCurrentWidget(self.logic); self.reveal_source()

    def select_stage(self, row, column):
        stage = self.flow_stages[column]; self.w.stage.setCurrentIndex(self.w.stage.findData(stage))
        candidates = [r for r in self.w.studio.run_manager.rows if r['job']['cell']==self.w.cell_id and data_of(r).get('stage')==stage]
        if candidates:
            self.w.runs.setCurrentIndex(self.w.runs.findData(candidates[-1]['id']))

    def stop(self):
        if self.w.flow.active:
            self.w.flow.stop()
        else:
            self.w.stop()

    def refresh(self, *_):
        w = self.w
        if w.studio.project['id'] != w.project_id: return
        from .digital_tools import selection
        self.tools_button.setText('Custom tools' if selection(w.studio.settings)['toolchain']=='custom' else 'Included tools')
        from .digital_design import cell
        self.title.setText(cell(w.studio.project, w.cell_id)['name'])
        self.source_changed()
        row = w.selected_run(); data = data_of(row) if row else {}; key = (row['id'],row['state']) if row else None
        if key != self.key:
            self.key = key; self.hierarchy.clear(); modules = {}
            for item in w.workspace.index[:20000]:
                if item['module'] not in modules:
                    parent = QTreeWidgetItem([item['module']]); self.hierarchy.addTopLevelItem(parent); modules[item['module']] = parent
                child = QTreeWidgetItem([item['name'] + (' · '+item['type'] if item.get('type') else '')]); child.setData(0, Qt.UserRole, item); modules[item['module']].addChild(child)
            for item in modules.values():
                item.setExpanded(True)
            self.filter(self.search.text())
        stats = data.get('statistics', {}); timing = data.get('timing', {}).get('summary', {}); metrics = []
        for label, value, unit in (('Cells',stats.get('cells'),''),('Area',stats.get('area_um2'),' µm²'),
                                  ('Setup',timing.get('setup_worst_slack_ns'),' ns'),('Hold',timing.get('hold_worst_slack_ns'),' ns')):
            if value is not None:
                metrics.append(label+'  '+(f'{value:.3g}' if isinstance(value,float) else str(value))+unit)
        self.metrics.setText('     ·     '.join(metrics) or 'Results retain their source revision and tool settings.')
        rows = w.studio.run_manager.rows
        for column, stage in enumerate(self.flow_stages):
            candidates = [r for r in rows if r['job']['project']['id']==w.project_id and r['job']['cell']==w.cell_id and r['job']['settings']['stage']==stage]
            current_rows = [r for r in candidates if usable(r,w.studio.project,w.cell_id)]
            latest = candidates[-1] if candidates else None
            state = 'Current' if current_rows else 'Stale' if latest and latest['state']=='Complete' else latest['state'] if latest else 'Not run'
            verdict=data_of(latest).get('verdict') if latest else None
            if verdict in ('FAIL','UNKNOWN','ERROR','INCOMPLETE'):state=verdict.title()
            if latest and latest['state'] in ('Running','Queued','Stopping'):
                state = latest['state']
            item = QTableWidgetItem(state); item.setTextAlignment(Qt.AlignCenter)
            color = '#3fba91' if state=='Current' else '#d58a3d' if state in ('Stale','Failed') else palette(w.studio.dark)['muted']
            item.setForeground(QColor(color)); self.flow_table.setItem(0,column,item)
        record = w.flow.record
        self.target_button.setEnabled(not w.flow.active)
        self.resume_button.setVisible(bool(record and record['state'] in ('Failed','Cancelled','Interrupted')))
        if record:
            complete = sum(s['state'] in ('Complete','Reused') for s in record['steps'])
            active = next((s for s in record['steps'] if s['state'] in ('Running','Failed')),None)
            self.flow_label.setText(f'{record["state"]} · {complete}/{len(record["steps"])} stages' + (' · '+LABELS[active['stage']] if active else '') )


def rebuild(window):
    from .digital_planning import controller_type
    window.flow = controller_type()(window)
    window.shell = DigitalShell(window)
    window.flow.restore()
