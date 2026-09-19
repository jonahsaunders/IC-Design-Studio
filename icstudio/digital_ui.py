"""Digital source editing and result inspection within the native Qt app."""
from __future__ import annotations

import json
import re
from bisect import bisect_left
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFontDatabase, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QPlainTextEdit, QListWidget, QListWidgetItem,
    QTabWidget, QSplitter, QFormLayout, QFileDialog, QInputDialog, QScrollArea,
    QDialogButtonBox, QMessageBox, QDockWidget, QMenu)

from . import digital, digital_flow
from .digital_waveform import value_at, format_value
from .model import clone, digest, design_digest
from .digital_design import config as cell_config, set_config


class RTLHighlighter(QSyntaxHighlighter):
    def __init__(self,document,dark=True):
        super().__init__(document);self.dark=dark

    def highlightBlock(self, text):
        for pattern, color in [(r'\b(module|endmodule|input|output|wire|reg|logic|integer|always|always_ff|always_comb|begin|end|if|else|initial|for|parameter|localparam|assign|posedge|negedge)\b', '#91a9ff'),
                               (r'\$[a-zA-Z_]+|`[a-zA-Z_]+', '#d7a8e8'),
                               (r'"(?:\\.|[^"\\])*"', '#dfba7b'), (r'//.*$', '#7c9388')]:
            if not self.dark:color={'#91a9ff':'#3156b5','#d7a8e8':'#834492','#dfba7b':'#815b14','#7c9388':'#47745a'}[color]
            style = QTextCharFormat(); style.setForeground(QColor(color))
            for match in re.finditer(pattern,text): self.setFormat(match.start(),match.end()-match.start(),style)


class DigitalWaveform(QWidget):
    def __init__(self):
        super().__init__(); self.data = None; self.signals = []; self.zoom = 1; self.cursor = 0; self.cursor_b = 0; self.radix = 'hex'
        self.setAccessibleName('Digital waveforms; click to inspect exact simulation ticks')
        self.setMinimumSize(280, 220)

    def set_data(self, data, signals=None):
        self.data = data
        self.signals = (signals if signals is not None else data['signals'][:12]) if data else []
        self.setMinimumSize(280 if self.zoom == 1 else min(50000, 900*self.zoom), max(220, 88+len(self.signals)*38))
        self.update()

    def plot_geometry(self):
        left = min(260, max(100, round(self.width()*.36)))
        return left, max(1, self.width()-left-20)

    def paintEvent(self, event):
        painter = QPainter(self); painter.fillRect(event.rect(), self.palette().base())
        if not self.data:
            painter.setPen(self.palette().text().color())
            painter.drawText(self.rect(), Qt.AlignCenter, 'Run a digital testbench to inspect its waveform')
            return
        left, width = self.plot_geometry(); end = max(1, self.data['end_tick'])
        x = lambda tick: left + tick/end*width
        painter.setPen(self.palette().text().color())
        painter.drawText(12, 22, f"A {self.cursor} · B {self.cursor_b} · Δ {abs(self.cursor_b-self.cursor)} × {self.data['timescale']}")
        intervals = max(1, min(8, int(width/80)))
        for i in range(intervals+1):
            tick = round(end*i/intervals); xpos = x(tick)
            painter.setPen(QColor('#758595')); painter.drawLine(QPointF(xpos, 53), QPointF(xpos, self.height()))
            label_x = min(self.width()-70, max(left, xpos-35))
            painter.drawText(QRectF(label_x, 33, 70, 20), Qt.AlignCenter, str(tick))
        # Paint only visible lanes and transitions; the scroll area clips large traces.
        for i, signal in enumerate(self.signals):
            y = 83+i*38
            if y+20 < event.rect().top() or y-25 > event.rect().bottom(): continue
            events = self.data['changes'][signal['code']]
            value = format_value(value_at(events, self.cursor, signal['width']), self.radix)
            painter.setPen(self.palette().text().color())
            label = signal['name']+' = '+value
            painter.drawText(QRectF(8, y-19, left-16, 28), Qt.AlignVCenter,
                             painter.fontMetrics().elidedText(label, Qt.ElideMiddle, left-16))
            visible_tick = max(0, int((event.rect().left()-left)/width*end))
            start = max(0, bisect_left(events, visible_tick, key=lambda e: e[0])-1)
            prev = None
            for j in range(start, len(events)):
                tick, bits = events[j]; a = x(tick)
                if a > event.rect().right(): break
                b = x(events[j+1][0] if j+1 < len(events) else end)
                unknown = any(c in bits for c in 'xz')
                painter.setPen(QPen(QColor('#e39c58' if unknown else '#43bfa0'), 1.6))
                if signal['width'] == 1 and not unknown:
                    level = y-15 if bits == '1' else y
                    if prev is not None: painter.drawLine(QPointF(a, prev), QPointF(a, level))
                    painter.drawLine(QPointF(a, level), QPointF(b, level)); prev = level
                else:
                    painter.drawRect(QRectF(a, y-17, max(1,b-a), 20))
                    if b-a > 22:
                        painter.drawText(QRectF(a+2, y-18, b-a-4, 22), Qt.AlignCenter,
                                         painter.fontMetrics().elidedText(format_value(bits, self.radix), Qt.ElideRight, int(b-a-4)))
                    prev = None
        for tick,color in ((self.cursor,'#e87886'),(self.cursor_b,'#8dadf7')):
            painter.setPen(QPen(QColor(color), 1.5)); painter.drawLine(QPointF(x(tick), 52), QPointF(x(tick), self.height()))

    def mousePressEvent(self, event):
        if self.data:
            left, width = self.plot_geometry()
            tick = max(0, min(self.data['end_tick'], round((event.position().x()-left)/width*self.data['end_tick'])))
            if event.modifiers() & Qt.ShiftModifier: self.cursor_b = tick
            else: self.cursor = tick
            self.update()


class DigitalFlowWindow(QDockWidget):
    def __init__(self, studio):
        super().__init__(studio); self.studio = studio; self.project_id = studio.project['id']
        self.cell_id = studio.cid; self.setObjectName('digital_flow')
        self.base = None; self.config = None; self.dirty = False; self.loading = False; self.file_index = -1; self.display_key = None
        self.setWindowTitle('Digital flow'); self.resize(1200, 800)
        host=QWidget();self.setWidget(host);root = QVBoxLayout(host); toolbar = QHBoxLayout(); root.addLayout(toolbar)
        for text, callback in [('Import sources…', self.import_sources), ('Counter example', studio.new_digital_counter),
                               ('Tools…', self.configure_tools), ('Export flow bundle…', self.export)]:
            button = QPushButton(text); button.clicked.connect(lambda checked=False, fn=callback: self.attempt(fn)); toolbar.addWidget(button)
        toolbar.addStretch()
        self.stage = QComboBox()
        for label, key in [('Simulate', 'simulate'), ('Lint', 'lint'), ('Elaborate','elaborate'),('Generic synthesis', 'synth'),
                ('Mapped synthesis','mapped'),('Timing','timing'),('Equivalence','equivalence'),('Floorplan','floorplan'),
                ('Place','place'),('Clock tree','cts'),('Route','route'),('Finish / GDS','finish'),('Regression','regression')]: self.stage.addItem(label, key)
        self.stage.setAccessibleName('Digital stage'); toolbar.addWidget(self.stage)
        self.simulator = QComboBox(); self.simulator.addItem('Icarus', 'icarus'); self.simulator.addItem('Verilator', 'verilator')
        self.simulator.setAccessibleName('Digital simulator'); toolbar.addWidget(self.simulator)
        self.run_button = QPushButton('Run'); self.run_button.clicked.connect(lambda: self.attempt(self.run)); toolbar.addWidget(self.run_button)
        self.tabs = QTabWidget(); root.addWidget(self.tabs, 1)
        source_page = QWidget(); source_layout = QVBoxLayout(source_page)
        form = QHBoxLayout(); self.top = QLineEdit(); self.testbench = QLineEdit(); self.top.setAccessibleName('Digital top module'); self.testbench.setAccessibleName('Digital testbench top')
        form.addWidget(QLabel('Top module')); form.addWidget(self.top); form.addWidget(QLabel('Testbench top')); form.addWidget(self.testbench)
        source_layout.addLayout(form)
        splitter = QSplitter(); source_layout.addWidget(splitter, 1)
        left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(0,0,0,0)
        self.files = QListWidget(); self.files.setAccessibleName('Embedded digital files'); lv.addWidget(self.files)
        file_buttons = QHBoxLayout(); lv.addLayout(file_buttons)
        for text, callback in [('Add…', self.add_file), ('Remove', self.remove_file)]:
            button = QPushButton(text); button.clicked.connect(lambda checked=False, fn=callback: self.attempt(fn)); file_buttons.addWidget(button)
        splitter.addWidget(left); editor_host = QWidget(); ev = QVBoxLayout(editor_host); ev.setContentsMargins(0,0,0,0)
        self.role = QComboBox()
        for role in digital.ROLES: self.role.addItem(role.title(), role)
        self.role.setAccessibleName('Digital file role'); ev.addWidget(self.role)
        from .digital_editor import SourceEditor
        self.editor = SourceEditor(); self.editor.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont)); self.editor.setAccessibleName('RTL source editor'); ev.addWidget(self.editor)
        self.editor.setStyleSheet('QPlainTextEdit { font-family: monospace; font-size: 13px; }')
        self.highlighter = RTLHighlighter(self.editor.document(),studio.dark)
        splitter.addWidget(editor_host); splitter.setSizes([230, 850])
        actions = QHBoxLayout(); source_layout.addLayout(actions)
        self.apply_button = QPushButton('Apply sources'); self.apply_button.clicked.connect(lambda: self.attempt(self.apply)); actions.addWidget(self.apply_button)
        reset = QPushButton('Reload saved sources'); reset.clicked.connect(self.reload_sources); actions.addWidget(reset)
        settings_button = QPushButton('Source settings…'); settings_button.clicked.connect(lambda: self.attempt(self.source_settings)); actions.addWidget(settings_button); actions.addStretch()
        self.tabs.addTab(source_page, 'Sources')
        result_page = QWidget(); rv = QVBoxLayout(result_page); bar = QHBoxLayout(); rv.addLayout(bar)
        self.runs = QComboBox(); self.runs.setAccessibleName('Digital run history'); bar.addWidget(self.runs, 1)
        for text, callback in [('Stop', self.stop), ('Rerun saved inputs', self.replay)]:
            button = QPushButton(text); button.clicked.connect(lambda checked=False, fn=callback: self.attempt(fn)); bar.addWidget(button)
        self.summary = QLabel('No digital run yet'); self.summary.setWordWrap(True); rv.addWidget(self.summary)
        self.result_tabs = QTabWidget(); rv.addWidget(self.result_tabs, 1)
        wave_page = QWidget(); wv = QVBoxLayout(wave_page); wave_controls = QHBoxLayout(); wv.addLayout(wave_controls)
        self.radix = QComboBox(); self.radix.addItems(['hex', 'binary', 'unsigned', 'signed']); wave_controls.addWidget(QLabel('Bus display')); wave_controls.addWidget(self.radix)
        for text, factor in [('Zoom in', 2), ('Zoom out', .5)]:
            button = QPushButton(text); button.clicked.connect(lambda checked=False, f=factor: self.zoom(f)); wave_controls.addWidget(button)
        wave_controls.addStretch(); self.wave_controls = wave_controls; self.wave_layout = wv; split = QSplitter(); wv.addWidget(split)
        self.signals = QListWidget(); self.signals.setMaximumWidth(260); self.signals.setAccessibleName('Visible digital signals'); split.addWidget(self.signals)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); self.wave = DigitalWaveform(); scroll.setWidget(self.wave); split.addWidget(scroll)
        self.result_tabs.addTab(wave_page, 'Waveforms')
        self.report = QPlainTextEdit(); self.report.setReadOnly(True); self.result_tabs.addTab(self.report, 'Report and log')
        self.netlist_view = QPlainTextEdit(); self.netlist_view.setReadOnly(True)
        self.netlist_view.setStyleSheet('QPlainTextEdit { font-family: monospace; }')
        self.netlist_highlighter = RTLHighlighter(self.netlist_view.document(),studio.dark)
        self.result_tabs.addTab(self.netlist_view, 'Synthesized Verilog')
        self.tabs.addTab(result_page, 'Runs and results')
        self.message = QLabel(); self.message.setWordWrap(True); root.addWidget(self.message)
        self.files.currentRowChanged.connect(self.select_file); self.editor.textChanged.connect(self.edited)
        self.top.textEdited.connect(self.edited); self.testbench.textEdited.connect(self.edited); self.role.currentIndexChanged.connect(self.edited)
        self.runs.currentIndexChanged.connect(lambda: self.attempt(self.show_run)); self.signals.itemChanged.connect(self.signal_selection)
        self.radix.currentTextChanged.connect(self.change_radix)
        self.stage.currentIndexChanged.connect(lambda: self.simulator.setEnabled(self.stage.currentData() == 'simulate'))
        from .digital_workspace import Workspace
        self.workspace=Workspace(self,root)
        studio.run_manager.changed.connect(self.refresh_runs)
        self.load_sources(); self.refresh_runs()
        from .digital_vga_ui import VGAPlayground
        self.vga = VGAPlayground(self)
        self.result_tabs.addTab(self.vga, 'VGA Playground')
        from .digital_shell import rebuild
        rebuild(self)
        from .digital_wave_tools import WaveTools
        self.wave_tools = WaveTools(self)
        from .digital_lsp import LanguageClient
        self.language = LanguageClient(self)

    def show_vga(self):
        self.shell.mode(1)
        self.shell.source_mode.setCurrentIndex(0)
        self.result_tabs.setCurrentWidget(self.vga)

    def reveal_source(self):
        if hasattr(self, 'shell'):
            self.shell.reveal_source()
        else:
            self.tabs.setCurrentIndex(0)

    def reveal_results(self):
        if hasattr(self, 'shell'):
            self.shell.analysis.show()
        else:
            self.tabs.setCurrentIndex(1)

    def attempt(self, function):
        try:
            self.message.clear(); return function()
        except Exception as exc:
            self.message.setText(str(exc)); return False

    def check_project(self):
        if self.studio.project['id'] != self.project_id:
            raise ValueError('The project changed. Reopen Digital flow.')

    def load_sources(self):
        self.check_project(); self.loading = True
        self.base = clone(cell_config(self.studio.project,self.cell_id)); self.config = clone(self.base)
        self.file_index = -1; self.files.clear(); self.editor.clear()
        self.top.setText((self.config or {}).get('top', '')); self.testbench.setText((self.config or {}).get('testbench', ''))
        if self.config:
            self.files.addItems([f['path'] for f in self.config['files']])
        self.loading = False; self.dirty = False
        if self.files.count(): self.files.setCurrentRow(0)
        self.apply_button.setEnabled(False)
        if hasattr(self,'workspace'):self.workspace.refresh_design()

    def reload_sources(self):
        if self.dirty and QMessageBox.question(self, 'Reload sources', 'Discard the unapplied source edits?') != QMessageBox.Yes: return
        self.attempt(self.load_sources)

    def sync_file(self):
        if self.config and 0 <= self.file_index < len(self.config['files']):
            self.config['files'][self.file_index].update(text=self.editor.toPlainText(), role=self.role.currentData())

    def select_file(self, index):
        if self.loading: return
        self.sync_file(); self.file_index = index; self.loading = True
        if self.config and 0 <= index < len(self.config['files']):
            item = self.config['files'][index]; self.editor.setPlainText(item['text']); self.role.setCurrentIndex(self.role.findData(item['role']))
        else: self.editor.clear()
        self.loading = False

    def edited(self, *args):
        if not self.loading:
            self.dirty = True; self.apply_button.setEnabled(True)
            self.message.setText('Source edits will be saved to the project when applied or run.')
            if hasattr(self, 'vga'): self.vga.schedule()

    def apply(self):
        self.check_project()
        if not self.config: raise ValueError('Import a digital manifest or open the counter example first.')
        if cell_config(self.studio.project,self.cell_id) != self.base:
            raise ValueError('Saved digital sources changed. Reload them before applying this draft.')
        self.sync_file(); self.config.update(top=self.top.text().strip(), testbench=self.testbench.text().strip())
        if 'platform' not in self.config:
            from .digital_runtime import installed, platform
            runtime=installed()
            if runtime: self.config['platform']=platform(runtime)
        digital.validate_config(self.config)
        if not self.studio.flush_inspector(): return False
        candidate = clone(self.config)
        if candidate != self.base:
            self.studio.commit(lambda p: set_config(p,self.cell_id,candidate), 'Edit digital sources')
            if cell_config(self.studio.project,self.cell_id) != candidate: return False
        self.base = clone(candidate); self.dirty = False; self.apply_button.setEnabled(False)
        self.refresh_runs(); return True

    def import_sources(self):
        self.check_project()
        path, _ = QFileDialog.getOpenFileName(self, 'Import digital manifest', '', 'Digital manifest (*.json)')
        if not path: return
        config = digital.read_manifest(path)
        if self.dirty and not self.apply(): return
        if not self.studio.idle_edit(): return
        self.studio.commit(lambda p: set_config(p,self.cell_id,config), 'Import digital sources'); self.load_sources()

    def add_file(self):
        if not self.config: raise ValueError('Import a manifest or open the counter example first.')
        path, ok = QInputDialog.getText(self, 'New digital source', 'Relative filename, such as rtl/control.sv')
        if not ok: return
        digital.relative_path(path); self.sync_file()
        candidate = clone(self.config); candidate['files'].append({'path': path, 'role': 'rtl', 'text': ''}); digital.validate_config(candidate)
        self.config = candidate; self.files.addItem(path); self.files.setCurrentRow(self.files.count()-1); self.edited()

    def remove_file(self):
        if self.config and self.file_index >= 0:
            index = self.file_index; self.file_index = -1; self.config['files'].pop(index)
            self.files.takeItem(index); self.select_file(self.files.currentRow()); self.edited()

    def source_settings(self):
        if not self.config: raise ValueError('Open a digital project first.')
        text = json.dumps({key: self.config.get(key, default) for key, default in
                          [('include_dirs',['.']), ('defines',{}), ('waveform','wave.vcd'), ('timeout',60)]}, indent=2)
        dialog = QDialog(self); dialog.setWindowTitle('Digital source settings'); layout = QVBoxLayout(dialog)
        note = QLabel('Edit include directories, preprocessor definitions, VCD filename and timeout in seconds.'); note.setWordWrap(True); layout.addWidget(note)
        editor = QPlainTextEdit(text); layout.addWidget(editor); buttons = QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
        if dialog.exec():
            values = json.loads(editor.toPlainText())
            if not isinstance(values, dict) or set(values)-{'include_dirs','defines','waveform','timeout'}: raise ValueError('Unknown digital source setting.')
            candidate = {**self.config, **values}; digital.validate_config(candidate); self.config = candidate; self.edited()

    def configure_tools(self):
        from .digital_setup_ui import show
        return show(self.studio,custom=self.configure_custom_tools)

    def ensure_tools(self, continuation, description='your run'):
        from .digital_setup_ui import ensure
        return ensure(self,continuation,description)

    def configure_custom_tools(self):
        from .digital_setup_ui import configure_custom_tools
        return configure_custom_tools(self.studio,self)

    def run(self):
        if not self.apply(): return
        if self.studio.process and self.studio.process not in self.studio.run_manager.processes:
            raise ValueError('Wait for the external job to finish first.')
        if not self.ensure_tools(self.run,'the selected stage'): return
        from .digital_tools import selection
        from .digital_planning import latest_upstream
        upstream = self.selected_run() if self.workspace.use_selected.isChecked() else latest_upstream(
            self.studio.run_manager.rows, self.studio.project, self.cell_id, self.stage.currentData())
        job = digital_flow.prepare(self.studio.project, self.stage.currentData(), self.simulator.currentData(),
            cell_id=self.cell_id,upstream=upstream['path'] if upstream else None,**selection(self.studio.settings))
        row = self.studio.run_manager.enqueue(job, self.studio.jobs_dir, 'Digital '+self.stage.currentText().lower())
        self.refresh_runs(); self.runs.setCurrentIndex(self.runs.findData(row['id'])); self.reveal_results()
        return row

    def refresh_runs(self):
        if self.studio.project['id'] != self.project_id: return
        selected = self.runs.currentData(); self.runs.blockSignals(True); self.runs.clear()
        for row in self.studio.run_manager.rows:
            if row['job']['settings'].get('type') == 'digital' and row['job']['project']['id'] == self.project_id and row['job']['cell']==self.cell_id:
                self.runs.addItem(f"{row['name']} · {row['state']} · r{row['job']['project']['revision']}", row['id'])
        index = self.runs.findData(selected); self.runs.setCurrentIndex(index if index >= 0 else self.runs.count()-1); self.runs.blockSignals(False)
        self.attempt(self.show_run)
        if hasattr(self,'workspace'):self.workspace.refresh_comparison()
        if hasattr(self,'shell'):self.shell.refresh()

    def selected_run(self):
        return next((r for r in self.studio.run_manager.rows if r['id'] == self.runs.currentData()), None)

    def show_run(self):
        row = self.selected_run()
        if not row:
            self.summary.setText('No digital run yet'); self.wave.set_data(None); self.signals.clear(); self.report.clear(); self.netlist_view.clear()
            if hasattr(self,'workspace'):self.workspace.show_result(None)
            return
        result = row.get('result'); data = result.get('digital_result') if result else None
        from .digital_identity import current
        state = 'Current inputs' if data and current(data,cell_config(self.studio.project,self.cell_id),row['job']['settings'].get('simulator','icarus')) else 'Captured earlier inputs'
        self.summary.setText((data['summary']+' · '+state) if data else row['state']+f" · {row['progress']}%")
        self.report.setPlainText((json.dumps(data, indent=2) if data else '')+'\n'+row['log'][-30000:])
        if hasattr(self,'workspace'):self.workspace.show_diagnostics(row)
        key = (row['id'], row['state'])
        if key == self.display_key: return
        self.display_key = key; self.signals.blockSignals(True); self.signals.clear(); self.wave.set_data(None); self.netlist_view.clear()
        try:
            if data:
                digital_flow.validate_result(result, row['path'])
                if 'netlist' in data['artifacts']:
                    path = row['path']/data['artifacts']['netlist']['path']
                    with path.open(encoding='utf-8') as source:
                        text = source.read(4*1024*1024)
                    self.netlist_view.setPlainText(text+('\n// Preview limited to 4 MiB; full netlist retained in the run folder.' if path.stat().st_size > 4*1024*1024 else ''))
                if 'waveform' in data['artifacts']:
                    from .digital_trace_store import open_waveform
                    waveform = open_waveform(row['path']/data['artifacts']['waveform']['path'])
                    self.wave.cursor = 0; self.wave.cursor_b = 0; self.wave.zoom = 1; self.wave.set_data(waveform)
                    for index, signal in enumerate(waveform['signals']):
                        item = QListWidgetItem(signal['name']); item.setToolTip(signal['name']); item.setFlags(item.flags()|Qt.ItemIsUserCheckable); item.setData(Qt.UserRole,index)
                        item.setCheckState(Qt.Checked if index < 12 else Qt.Unchecked); self.signals.addItem(item)
                    self.result_tabs.setCurrentIndex(0)
                else: self.result_tabs.setCurrentIndex(1)
            else: self.result_tabs.setCurrentIndex(1)
            if hasattr(self,'workspace'):self.workspace.show_result(row)
        finally: self.signals.blockSignals(False)
        if hasattr(self,'wave_tools'): self.wave_tools.restore()
        if hasattr(self,'shell'): self.shell.refresh()

    def signal_selection(self):
        if self.wave.data:
            indices = [self.signals.item(i).data(Qt.UserRole) for i in range(self.signals.count()) if self.signals.item(i).checkState() == Qt.Checked]
            self.wave.set_data(self.wave.data, [self.wave.data['signals'][i] for i in indices])

    def change_radix(self, radix): self.wave.radix = radix; self.wave.update()
    def zoom(self, factor): self.wave.zoom = max(1,min(32,int(self.wave.zoom*factor))); self.wave.set_data(self.wave.data,self.wave.signals)
    def stop(self):
        row = self.selected_run()
        if row: self.studio.run_manager.cancel([row])
    def replay(self):
        row = self.selected_run()
        if row:
            new = self.studio.run_manager.enqueue(clone(row['job']),self.studio.jobs_dir,row['name']+' · rerun')
            self.refresh_runs(); self.runs.setCurrentIndex(self.runs.findData(new['id']))
    def export(self):
        if not self.apply(): return
        directory = QFileDialog.getExistingDirectory(self, 'Choose an empty flow bundle folder')
        if directory:
            digital_flow.export_flow(self.config,directory); self.message.setText('Exported Yosys/EQY inputs and SKY130 ORFS starting configuration. Physical flow has not run.')
    def closeEvent(self,event):
        if self.dirty:
            answer = QMessageBox.question(self,'Unapplied source edits','Apply the source edits before closing?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel)
            if answer == QMessageBox.Cancel or answer == QMessageBox.Save and not self.attempt(self.apply):event.ignore();return
        if hasattr(self, 'shell'):self.shell.save_layout()
        if hasattr(self,'language'):self.language.stop()
        if hasattr(self,'vga'):self.vga.shutdown()
        self.dirty = False; super().closeEvent(event)


class DigitalMixin:
    def enter_digital_workspace(self, window):
        if self.centralWidget() is window:
            return
        self._circuit_center = self.takeCentralWidget();self._circuit_center.hide()
        self._digital_panels = [(d, d.isVisible()) for d in self.findChildren(QDockWidget) if d is not window]
        for dock, visible in self._digital_panels:
            dock.hide()
        self._digital_toolbar_visible = self.toolbar.isVisible(); self.toolbar.hide()
        self.removeDockWidget(window); self.setCentralWidget(window); window.show();self.statusBar().showMessage('Digital workspace')

    def leave_digital_workspace(self):
        window = getattr(self, '_digital_window', None)
        if not window or self.centralWidget() is not window:
            return
        if window.dirty and not window.attempt(window.apply):
            return
        window.shell.save_layout(); self.takeCentralWidget()
        self.setCentralWidget(self._circuit_center);self._circuit_center.show(); self._circuit_center = None
        window.setParent(self); window.hide()
        for dock, visible in getattr(self, '_digital_panels', []):
            dock.setVisible(visible)
        self.toolbar.setVisible(getattr(self, '_digital_toolbar_visible', True))
        if getattr(self,'_deferred_editor_restore',False):
            self._deferred_editor_restore=False;super().restore_last_editor_workspace()

    def restore_last_editor_workspace(self):
        window=getattr(self,'_digital_window',None)
        if window and self.centralWidget() is window:
            self._deferred_editor_restore=True;return
        return super().restore_last_editor_workspace()

    def apply_theme(self):
        super().apply_theme()
        window=getattr(self,'_digital_window',None)
        if window and hasattr(window,'shell'):
            window.shell.style();window.shell.refresh()
            for highlighter in (window.highlighter,window.netlist_highlighter,window.shell.captured_highlighter):
                highlighter.dark=self.dark;highlighter.rehighlight()

    def closeEvent(self,event):
        window=getattr(self,'_digital_window',None)
        active=window and self.centralWidget() is window
        if active:
            if window.dirty and not window.attempt(window.apply):event.ignore();return
            self.leave_digital_workspace()
        super().closeEvent(event)
        if window:
            if event.isAccepted():
                window.language.stop(); window.vga.shutdown()
            elif active:self.enter_digital_workspace(window)

    def quick_run(self):
        window = getattr(self, '_digital_window', None)
        if window and self.centralWidget() is window:
            return window.attempt(window.run)
        return super().quick_run()

    def prepare_simulation(self,settings,engine='builtin',project=None,cid=None):
        if engine!='digital':return super().prepare_simulation(settings,engine,project,cid)
        from .digital_tools import selection
        p=clone(project or self.project);cid=cid or self.cid;case=settings.get('digital_case',{})
        config=clone(cell_config(p,cid));config.pop('tests',None)
        config.update(testbench=case['testbench'],defines={**config.get('defines',{}),**case.get('defines',{})},coverage=case.get('coverage',False))
        set_config(p,cid,config)
        job=digital_flow.prepare(p,'simulate',case.get('simulator','icarus'),cell_id=cid,**selection(self.settings))
        job['settings']['digital_case']=clone(case)
        return job

    def digital_window(self):
        from .digital_setup_ui import apply_defaults
        apply_defaults(self)
        window = getattr(self, '_digital_window', None)
        if window is None or window.project_id != self.project['id']:
            if window:
                self.leave_digital_workspace()
                window.dirty = False; window.close(); window.deleteLater()
            window = self._digital_window = DigitalFlowWindow(self)
        elif not window.dirty: window.load_sources(); window.refresh_runs()
        self.enter_digital_workspace(window); window.show(); window.raise_(); return window

    def new_digital_counter(self):
        if not self.idle_edit() or not self.maybe_save(): return
        from .digital_runtime import defaults
        project=digital.counter_project(); defaults(project)
        self.set_project(project); return self.digital_window()

    def new_digital_uart(self):
        if not self.idle_edit() or not self.maybe_save():return
        from .digital_examples import uart_project
        from .digital_runtime import defaults
        project=uart_project(); defaults(project)
        self.set_project(project);return self.digital_window()

    def new_digital_apb(self):
        if not self.idle_edit() or not self.maybe_save():return
        from .digital_apb_example import apb_project
        from .digital_runtime import defaults
        project=apb_project();defaults(project);self.set_project(project);return self.digital_window()

    def save(self, *args, **kwargs):
        window = getattr(self, '_digital_window', None)
        if window and window.dirty and not window.attempt(window.apply): return False
        return super().save(*args, **kwargs)

    def undo(self):
        window=getattr(self,'_digital_window',None)
        if window and window.dirty and not window.attempt(window.apply):return
        return super().undo()

    def maybe_save(self):
        window = getattr(self, '_digital_window', None)
        if window and window.dirty and not window.attempt(window.apply): return False
        return super().maybe_save()

    def set_project(self, p, path=None):
        window = getattr(self, '_digital_window', None)
        if window:
            if window.dirty and not window.attempt(window.apply):return False
            self.leave_digital_workspace()
        super().set_project(p, path)
        if window:
            window.dirty = False; window.close(); window.deleteLater(); self._digital_window = None

    def refresh(self, fit=False):
        super().refresh(fit)
        window = getattr(self, '_digital_window', None)
        if window and window.project_id == self.project['id']:
            if window.cell_id not in {c['id'] for c in self.project['cells']}:
                window.cell_id=self.cid;window.load_sources()
            if not window.dirty and window.base != cell_config(self.project,window.cell_id): window.load_sources()
            window.workspace.refresh_design()
            window.refresh_runs()

    def add_result(self, result):
        if result.get('result_type') != 'digital': return super().add_result(result)

    def simulation_finished(self, row, result):
        if row['job']['settings'].get('type') != 'digital': return super().simulation_finished(row, result)
        self.sync_runs(); self.console.appendPlainText(row['name']+' · '+row['state']+'\n'+row['log'])
        window = getattr(self,'_digital_window',None)
        if window and window.project_id==row['job']['project']['id'] and window.cell_id==row['job']['cell']:window.runs.setCurrentIndex(window.runs.findData(row['id'])); window.reveal_results()

    def open_selected_run(self):
        rows = self.selected_simulation_runs()
        if rows and rows[0]['job']['settings'].get('type') == 'digital':
            window = self.digital_window();window.workspace.switch_cell(rows[0]['job']['cell']); window.runs.setCurrentIndex(window.runs.findData(rows[0]['id'])); window.reveal_results(); return
        return super().open_selected_run()


def install(studio):
    menu = QMenu('D&igital',studio)
    studio.menuBar().insertMenu(studio.task_menus['Tools'].menuAction(),menu)
    studio.task_menus['Digital']=menu
    studio.action(menu, 'Digital flow…', studio.digital_window)
    studio.action(menu, 'New digital counter example', studio.new_digital_counter)
    studio.action(menu, 'New UART regression example', studio.new_digital_uart)
    studio.action(menu, 'New APB FIFO peripheral', studio.new_digital_apb)
    menu.addSeparator()
    for label,target in (('Verify digital block','verify'),('Run digital block to placement','place'),('Run digital block to GDS','finish')):
        studio.action(menu,label,lambda t=target:studio.digital_window().flow.start(t))
