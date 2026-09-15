"""gm/Id exploration and reviewable parameter searches in the analog workspace."""
import csv
import io
import json
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox,
    QLineEdit, QSpinBox, QLabel, QTabWidget, QSplitter, QPlainTextEdit, QCheckBox, QFileDialog)
from PySide6.QtWidgets import QProgressBar
from .model import clone, scalar, design_digest, atomic_write
from . import analog_optimizer as optimizer, variation_runs, test_plans
from .analog_widgets import actions, label, scroll, table, fill, selection_actions
from .plot import WavePlot


def combo(name):
    widget = QComboBox(); widget.setAccessibleName(name)
    widget.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon); widget.setMinimumContentsLength(12)
    return widget


def edit(text, name):
    widget = QLineEdit(text); widget.setAccessibleName(name); return widget


def condition_text(labels):
    values=[labels.get('corner','nominal')]
    if labels.get('temperature') is not None:values.append(f"{labels['temperature']:g} °C")
    if labels.get('voltage') is not None:values.append(f"{labels['voltage']:g} V")
    return ' · '.join(values)


class OptimizerPage(QWidget):
    def __init__(self, workspace):
        super().__init__(); self.workspace = workspace; self.studio = workspace.studio; self.manifests = []; self.report = None
        self.project_id = self.studio.project['id']; self.setAccessibleName('Analog optimizer')
        root = QVBoxLayout(self); root.addWidget(label('Explore device bias, then search circuit parameters against your saved measurement limits.'))
        self.split = QSplitter(); self.split.setChildrenCollapsible(False); root.addWidget(self.split,1)
        self.modes = QTabWidget(); self.split.addWidget(self.modes)
        self.search = QWidget(); self.explorer = QWidget(); self.modes.addTab(scroll(self.search), 'Circuit search'); self.modes.addTab(scroll(self.explorer), 'gm/Id explorer')
        self.build_search(); self.build_explorer()
        evidence=QWidget();self.split.addWidget(evidence);root=QVBoxLayout(evidence);root.setContentsMargins(8,0,0,0)
        self.split.setSizes([460,660])
        bar = QHBoxLayout(); self.history = combo('Saved optimizer experiment'); bar.addWidget(label('&Experiment', self.history)); bar.addWidget(self.history, 1); root.addLayout(bar)
        self.progress = QProgressBar(); self.progress.setAccessibleName('Completed optimizer simulations'); self.progress.setRange(0, 1); self.progress.setValue(0);self.progress.setTextVisible(False);root.addWidget(self.progress)
        self.summary = label('Choose an analysis or PVT plan to begin.'); self.summary.setAccessibleName('Optimizer status'); root.addWidget(self.summary)
        self.results = table(['Candidate', 'State', 'Worst objective', 'Parameters / conditions']); self.results.setAccessibleName('Optimizer candidates and gm/Id samples'); root.addWidget(self.results, 1)
        self.details = QPlainTextEdit(); self.details.setReadOnly(True); self.details.setMaximumHeight(95); self.details.setAccessibleName('Selected candidate review and failures'); root.addWidget(self.details)
        self.review_buttons = actions(root, [('Inspect saved run…', self.inspect), ('Apply selected candidate', self.apply), ('Cancel remaining', self.cancel), ('Resume incomplete', self.resume), ('Export CSV…', self.export)], self.call)
        self.inspect_button, self.apply_button, self.cancel_button, self.resume_button, self.export_button = self.review_buttons
        self.run_choice = combo('Saved condition to inspect'); root.insertWidget(root.count() - 1, self.run_choice)
        self.results.itemSelectionChanged.connect(self.selection_changed); self.results.cellDoubleClicked.connect(lambda *_: self.call(self.inspect))
        self.history.currentIndexChanged.connect(self.history_changed)
        self.timer = QTimer(self); self.timer.setInterval(200); self.timer.setSingleShot(True); self.timer.timeout.connect(self.render)
        self.studio.run_manager.changed.connect(self.schedule)
        self.run_shortcut = QShortcut(QKeySequence('Ctrl+Return'), self); self.run_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.run_shortcut.activated.connect(lambda: self.call(self.start_search if self.modes.currentIndex() == 0 else self.start_gmid))
        self.refresh_sources(); self.load_history()

    def call(self, fn):
        try:
            if self.studio.project['id'] != self.project_id: raise ValueError('The project changed. Reopen the analog workspace.')
            return fn()
        except Exception as exc:
            self.summary.setText('Could not complete this action: ' + str(exc))
            self.summary.setAccessibleDescription(str(exc))

    def changeEvent(self,event):
        if event.type()==QEvent.PaletteChange and hasattr(self,'plot'):
            self.plot.dark=self.studio.dark;self.plot.update()
        super().changeEvent(event)

    def form(self, layout):
        form = QFormLayout(); form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow); form.setRowWrapPolicy(QFormLayout.WrapLongRows); layout.addLayout(form); return form

    def field(self, form, title, widget): form.addRow(label(title, widget), widget)

    def build_search(self):
        layout = QVBoxLayout(self.search); form = self.form(layout)
        self.source = combo('Analysis or PVT plan'); self.field(form, '&Test or PVT plan', self.source)
        self.parameter_cell = combo('Cell containing adjustable parameters'); self.field(form, 'Parameter &cell', self.parameter_cell)
        self.objective_test = combo('Objective test'); self.field(form, 'Objective test', self.objective_test)
        self.goal = combo('Optimization direction')
        for text, key in [('Minimize', 'minimize'), ('Maximize', 'maximize'), ('Target', 'target')]: self.goal.addItem(text, key)
        self.expression = edit('final(V("out"))', 'Objective scalar expression'); self.unit = combo('Objective unit')
        from .wavecalc import UNITS
        self.unit.addItems(list(UNITS)); self.unit.setCurrentText('V'); self.target = edit('0', 'Target objective value')
        for title,w in [('Goal',self.goal),('Expression',self.expression),('Unit',self.unit),('Target value',self.target)]:self.field(form,title,w)
        def target_visibility():
            visible=self.goal.currentData()=='target';self.target.setVisible(visible);form.labelForField(self.target).setVisible(visible)
        self.goal.currentIndexChanged.connect(target_visibility);target_visibility()
        self.limits_note = label('All saved scalar limits and testbench measurements are hard constraints.'); layout.addWidget(self.limits_note)
        self.axes = table(['Parameter', 'Lower', 'Upper', 'Samples', 'Linked target = ratio'], True); self.axes.setAccessibleName('Adjustable parameters and matching ratios'); layout.addWidget(self.axes)
        self.axes.setMaximumHeight(155)
        for column,width in enumerate((145,70,70,65,200)):self.axes.setColumnWidth(column,width)
        self.axis_buttons = actions(layout, [('Add parameter', self.add_axis), ('Remove parameter', lambda: self.axes.removeRow(self.axes.currentRow()))], self.call)
        selection_actions(self.axes, [self.axis_buttons[1]])
        self.gm_limit = QCheckBox('Add gm/Id and bias limits'); layout.addWidget(self.gm_limit)
        self.gm_fields = QWidget(); gm_form = self.form(QVBoxLayout(self.gm_fields)); self.gm_test = combo('gm/Id constraint test'); self.gm_device = combo('gm/Id constrained instance')
        self.gm_min = edit('', 'Minimum gm/Id (1/V)'); self.gm_max = edit('', 'Maximum gm/Id (1/V)'); self.gm_margin = edit('', 'Minimum bias margin (V)')
        for title, w in [('Operating-point test', self.gm_test), ('MOS instance', self.gm_device), ('Minimum gm/Id (1/V)', self.gm_min), ('Maximum gm/Id (1/V)', self.gm_max), ('Minimum bias margin (V)', self.gm_margin)]: self.field(gm_form, title, w)
        layout.addWidget(self.gm_fields); self.gm_fields.hide(); self.gm_limit.toggled.connect(self.gm_fields.setVisible)
        self.budget = QSpinBox(); self.budget.setRange(1, 500); self.budget.setValue(100); self.field(form, 'Simulation budget', self.budget)
        self.start_button, self.refresh_button = actions(layout, [('Run search', self.start_search), ('Refresh saved setup', self.refresh_sources)], self.call, 'Run search')
        self.start_button.setToolTip('Run the bounded grid across every selected condition (Ctrl/Command+Return).')
        layout.addStretch(1)
        self.source.currentIndexChanged.connect(self.source_changed); self.parameter_cell.currentIndexChanged.connect(self.reset_axes)
        self.objective_test.currentIndexChanged.connect(self.objective_changed); self.gm_test.currentIndexChanged.connect(self.gm_test_changed)

    def build_explorer(self):
        layout = QVBoxLayout(self.explorer); layout.addWidget(label('Sweep one bias or sizing parameter in the saved circuit. Other parameters retain their saved values.'))
        form = self.form(layout); self.gm_source = combo('Saved operating-point analysis'); self.device = combo('MOS instance for gm/Id exploration')
        self.bias = combo('Bias parameter to sweep'); self.bias_lower = edit('0.5', 'Lower bias value'); self.bias_upper = edit('1.2', 'Upper bias value')
        self.samples = QSpinBox(); self.samples.setRange(2, 100); self.samples.setValue(15)
        self.gm_cell = combo('Cell containing bias parameter'); self.desired_current = edit('10u', 'Desired drain current (A)')
        for title, w in [('Operating-point test', self.gm_source), ('MOS instance', self.device), ('Parameter cell', self.gm_cell), ('Sweep parameter', self.bias), ('Lower value (SI)', self.bias_lower), ('Upper value (SI)', self.bias_upper), ('Samples', self.samples), ('Desired drain current (A)', self.desired_current)]: self.field(form, title, w)
        self.plot = WavePlot(); self.plot.dark = self.studio.dark; self.plot.setAccessibleName('gm/Id versus bias; exact values also appear in the results table'); layout.addWidget(self.plot)
        self.gm_run_button, self.estimate_button = actions(layout, [('Run gm/Id sweep', self.start_gmid), ('Estimate width from selected point', self.estimate)], self.call, 'Run gm/Id sweep')
        layout.addStretch(1)
        self.gm_source.currentIndexChanged.connect(self.gm_source_changed); self.gm_cell.currentIndexChanged.connect(self.bias_targets)

    def refresh_sources(self):
        p = self.studio.project; old = self.source.currentData(); self.source.blockSignals(True); self.source.clear()
        for plan in p.get('test_plans', []):
            if not plan.get('compare_layout') and all(e['engine'] != 'digital' for e in plan['entries']): self.source.addItem('PVT plan · ' + plan['name'], clone(plan))
        entries = [e for e in test_plans.sources(p) if e['engine'] != 'digital']
        for entry in entries: self.source.addItem(entry['name'], optimizer.source_plan(entry))
        index = next((i for i in range(self.source.count()) if self.source.itemData(i).get('id') == (old or {}).get('id') and self.source.itemData(i).get('name') == (old or {}).get('name')), 0)
        self.source.setCurrentIndex(index); self.source.blockSignals(False)
        for box in (self.parameter_cell, self.gm_cell):
            selected = box.currentData() or self.studio.cid; box.blockSignals(True); box.clear()
            for cell in p['cells']: box.addItem(cell['name'], cell['id'])
            box.setCurrentIndex(max(0, box.findData(selected))); box.blockSignals(False)
        old = self.gm_source.currentData(); self.gm_source.blockSignals(True); self.gm_source.clear()
        for e in entries:
            if optimizer.is_op(p, e): self.gm_source.addItem(e['name'], e)
        self.gm_source.setCurrentIndex(next((i for i in range(self.gm_source.count()) if self.gm_source.itemData(i)['id'] == (old or {}).get('id')), 0)); self.gm_source.blockSignals(False)
        self.source_changed(); self.gm_source_changed(); self.bias_targets()
        if not self.axes.rowCount(): self.add_axis()

    def source_changed(self):
        plan = self.source.currentData(); self.objective_test.clear(); self.gm_test.clear()
        if plan:
            for e in plan['entries']:
                self.objective_test.addItem(e['name'], e)
                if optimizer.is_op(self.studio.project, e): self.gm_test.addItem(e['name'], e)
            conditions = len(plan['corners']) * len(plan['temperatures']) * max(1, len(plan.get('voltages', [])))
            self.limits_note.setText(f"{len(plan['entries'])} tests × {conditions} PVT conditions per candidate. Saved limits are required; ranking uses the worst objective condition.")
        else: self.limits_note.setText('Save an analysis in Setup to start a search. Add scalar limits there to constrain performance.')
        self.start_button.setEnabled(bool(plan)); self.gm_limit.setEnabled(self.gm_test.count() > 0)
        if not self.gm_test.count(): self.gm_limit.setChecked(False)

    def objective_changed(self):
        entry = self.objective_test.currentData()
        if not entry: return
        from .specifications import for_job
        specs = for_job(dict(project=self.studio.project, cell=entry['cell'], settings=entry['settings']))
        if specs: self.expression.setText(specs[0]['expression']); self.unit.setCurrentText(specs[0].get('unit', ''))

    def gm_test_changed(self):
        self.gm_device.clear(); entry = self.gm_test.currentData()
        if entry: self.gm_device.addItems(optimizer.device_names(self.studio.project, entry['cell']))

    def gm_source_changed(self):
        self.device.clear(); entry = self.gm_source.currentData()
        if entry: self.device.addItems(optimizer.device_names(self.studio.project, entry['cell']))
        self.gm_run_button.setEnabled(bool(entry and self.device.count()))
        self.plot.empty_message = 'Save an operating-point analysis in Setup to explore gm/Id' if not entry else 'Run a bias sweep to plot captured gm/Id'; self.plot.update()

    def bias_targets(self):
        selected = self.bias.currentText(); self.bias.clear(); cid = self.gm_cell.currentData()
        if cid: self.bias.addItems(optimizer.targets(self.studio.project, cid))
        i = self.bias.findText(selected)
        if i >= 0: self.bias.setCurrentIndex(i)

    def reset_axes(self): self.axes.setRowCount(0); self.add_axis()

    def add_axis(self):
        cid = self.parameter_cell.currentData()
        if not cid or self.axes.rowCount() >= 3: return
        available = optimizer.targets(self.studio.project, cid)
        if not available: return
        i = self.axes.rowCount(); self.axes.insertRow(i); choice = combo('Adjustable parameter ' + str(i + 1)); choice.addItems(available); choice.setCurrentIndex(min(i, len(available) - 1)); self.axes.setCellWidget(i, 0, choice)
        from PySide6.QtWidgets import QTableWidgetItem
        def defaults():
            row=next((r for r in range(self.axes.rowCount()) if self.axes.cellWidget(r,0) is choice),None)
            if row is None:return
            value = optimizer.get_target(self.studio.project, cid, choice.currentText()); lo, hi = sorted((value * .5, value * 1.5)) if value else (-1., 1.)
            for j, text in enumerate((f'{lo:.6g}', f'{hi:.6g}', '5', ''), 1): self.axes.setItem(row, j, QTableWidgetItem(text))
        choice.currentTextChanged.connect(defaults); defaults()

    def axes_spec(self):
        out = []
        for i in range(self.axes.rowCount()):
            values = [self.axes.item(i, j).text().strip() if self.axes.item(i, j) else '' for j in range(1, 5)]
            links = []
            for pair in values[3].split(','):
                if not pair.strip(): continue
                parts = pair.split('=')
                if len(parts) != 2: raise ValueError('Use linked target = ratio, for example M2.params.w = 1.')
                links.append(dict(target=parts[0].strip(), ratio=parts[1].strip()))
            out.append(dict(target=self.axes.cellWidget(i, 0).currentText(), lower=values[0], upper=values[1], count=values[2], links=links))
        return out

    def start_search(self):
        if not self.studio.flush_inspector(): return
        self.workspace.require_saved_setup()
        plan = self.source.currentData()
        if not plan: raise ValueError('Save an analysis or testbench in Setup first.')
        self.verify_source(plan)
        spec = dict(kind='analog_optimizer', name='Search · ' + plan['name'], axes=self.axes_spec(), budget=self.budget.value(),
                    objective=dict(entry_id=self.objective_test.currentData()['id'], expression=self.expression.text(), unit=self.unit.currentText(), goal=self.goal.currentData(), target=self.target.text()))
        if self.gm_limit.isChecked(): spec['gmid'] = dict(entry_id=self.gm_test.currentData()['id'], device=self.gm_device.currentText(), min=self.gm_min.text(), max=self.gm_max.text(), headroom=self.gm_margin.text())
        self.queue(optimizer.prepare(self.studio.project, self.parameter_cell.currentData(), plan, spec, self.studio.prepare_simulation))

    def start_gmid(self):
        if not self.studio.flush_inspector(): return
        self.workspace.require_saved_setup(); entry = self.gm_source.currentData()
        if not entry or not self.device.currentText(): raise ValueError('Save an operating-point analysis with a MOS instance in Setup.')
        self.verify_source(optimizer.source_plan(entry))
        spec = dict(kind='analog_gmid', name='gm/Id · ' + self.device.currentText(), budget=100,
                    axes=[dict(target=self.bias.currentText(), lower=self.bias_lower.text(), upper=self.bias_upper.text(), count=self.samples.value())],
                    gmid=dict(entry_id=entry['id'], device=self.device.currentText()))
        self.queue(optimizer.prepare(self.studio.project, self.gm_cell.currentData(), optimizer.source_plan(entry), spec, self.studio.prepare_simulation))

    def queue(self, manifest):
        variation_runs.save(manifest, self.studio.jobs_dir); self.manifests.append(manifest); self.fill_history(manifest['id'])
        self.enqueue(manifest, manifest['jobs']); self.render()

    def verify_source(self, plan):
        if plan['id']=='optimizer-source':
            current=[optimizer.source_plan(e) for e in test_plans.sources(self.studio.project) if e['engine']!='digital']
        else:current=self.studio.project.get('test_plans',[])
        if plan not in current:raise ValueError('This saved test or plan changed. Refresh saved setup before running.')

    def enqueue(self, manifest, jobs):
        names = [manifest['name'] + ' · candidate ' + str(j['case']['candidate']) + ' · ' + j['case']['test_name'] + ' · ' + condition_text(j['case']['labels']) for j in jobs]
        self.studio.run_manager.enqueue_many(jobs, self.studio.jobs_dir, names)

    def load_history(self):
        self.manifests = [m for m in variation_runs.load(self.studio.jobs_dir, self.project_id) if m.get('spec', {}).get('kind') in optimizer.KINDS]
        self.fill_history()

    def fill_history(self, selected=None):
        selected = selected or self.history.currentData(); self.history.blockSignals(True); self.history.clear()
        for m in self.manifests: self.history.addItem(m['name'] + ' · ' + m['created'], m['id'])
        i = self.history.findData(selected); self.history.setCurrentIndex(i if i >= 0 else self.history.count() - 1); self.history.blockSignals(False); self.render()

    def manifest(self): return next((m for m in self.manifests if m['id'] == self.history.currentData()), None)
    def history_changed(self):
        m=self.manifest()
        if m:self.modes.setCurrentIndex(1 if m['spec']['kind']=='analog_gmid' else 0)
        self.render()
    def schedule(self):
        if self.isVisible() and not self.timer.isActive(): self.timer.start()

    def render(self):
        m = self.manifest()
        if not m:
            self.report = None; self.results.setRowCount(0)
            for b in self.review_buttons: b.setEnabled(False)
            self.estimate_button.setEnabled(False); return
        previous = self.results.currentRow(); self.report = optimizer.evaluate(m, self.studio.run_manager.rows); report = self.report
        self.progress.setRange(0, report['total']); self.progress.setValue(report['terminal']); self.progress.setFormat('%v / %m simulations finished')
        self.experiment_gmid = m['spec']['kind'] == 'analog_gmid'; candidates = report['candidates']
        self.results.blockSignals(True)
        if self.experiment_gmid:
            headers = ['Sample', 'State', 'Sweep value', 'gm/Id (1/V)', 'Id (A)', 'gm (S)', 'VGS (V)', 'VDS (V)', 'Id/W (A/m)', 'Bias margin (V)']
            self.results.setColumnCount(len(headers)); self.results.setHorizontalHeaderLabels(headers)
            for column,width in enumerate((65,75,105,110,110,110,110,110,130,140)):self.results.setColumnWidth(column,width)
            data = []
            for c in candidates:
                point = (c['points'] or [{}])[0]
                data.append([c['candidate'], c['state'], next(iter(c['changes'].values())), *[point.get(k) for k in ('gmid', 'id', 'gm', 'vgs', 'vds', 'current_density', 'headroom')]])
            fill(self.results, data); self.plot_points(m, candidates)
        else:
            self.results.setColumnCount(4); self.results.setHorizontalHeaderLabels(['Candidate', 'State', 'Worst value (' + (m['spec']['objective']['unit'] or '1') + ')', 'Parameters'])
            fill(self.results, [[c['candidate'], c['state'], c['worst_value'], ', '.join(k + '=' + f'{v:.6g}' for k, v in c['changes'].items())] for c in candidates])
            for column,width in enumerate((92,80,150,250)):self.results.setColumnWidth(column,width)
        if 0 <= previous < len(candidates): self.results.selectRow(previous)
        self.results.blockSignals(False)
        passed = sum(c['state'] == 'Passed' for c in candidates); failed = sum(c['state'] == 'Failed' for c in candidates)
        best = report['best']; status = f"{report['terminal']}/{report['total']} simulations finished. {passed} passed · {failed} failed · {len(candidates) - passed - failed} pending."
        if best: status += f" Best {'tested ' if not report['complete'] else ''}candidate: {best['candidate']}."
        if self.experiment_gmid: status += ' gm/Id uses |gm/Id|; teaching models omit subthreshold current and capacitances.'
        if design_digest(self.studio.project) != m['base_design_hash']: status += ' Current design differs; applying is disabled.'
        self.summary.setText(status)
        self.cancel_button.setEnabled(any(r['state'] in optimizer.ACTIVE for r in report['current'].values()))
        self.resume_button.setEnabled(bool(variation_runs.pending(m, self.studio.run_manager.rows)))
        self.export_button.setEnabled(True); self.selection_changed()

    def plot_points(self, manifest, candidates):
        # Keep missing points as gaps: separate contiguous segments instead of
        # drawing an invented curve through failed or zero-current samples.
        segments, current = [], []
        for c in candidates:
            if c['points']: current.append((next(iter(c['changes'].values())), c['points'][0]['gmid']))
            elif current: segments.append(current); current = []
        if current: segments.append(current)
        datasets = [dict(x=[p[0] for p in s], traces={'gm/Id': [p[1] for p in s]}, settings={'type': 'dc'}, x_label=manifest['spec']['axes'][0]['target'], plot_unit='1/V') for s in segments]
        self.plot.set_result(datasets[0] if datasets else None, ['gm/Id'], overlays=datasets[1:])

    def selected(self):
        i = self.results.currentRow()
        return self.report['candidates'][i] if self.report and 0 <= i < len(self.report['candidates']) else None

    def selection_changed(self):
        c = self.selected(); self.run_choice.clear(); self.details.clear(); m = self.manifest()
        if c:
            for row in self.report['current'].values():
                if row['id'] in c['runs']:
                    self.run_choice.addItem(row['job']['case']['test_name'] + ' · ' + condition_text(row['job']['case']['labels']) + ' · ' + row['state'], row['id'])
            cell = next((v for v in self.studio.project['cells'] if v['id'] == m['cell_id']),{'name':'Deleted cell'})
            before = []
            for k, v in c['changes'].items():
                try: old = optimizer.get_target(self.studio.project, m['cell_id'], k); before.append(f'{k}: {old:.6g} → {v:.6g}')
                except (ValueError, KeyError, StopIteration): before.append(f'{k}: unavailable → {v:.6g}')
            self.details.setPlainText('Parameter cell: ' + cell['name'] + ' (shared master parameters affect every instance).\n' + '\n'.join(before) + '\n' + ('\n'.join(c['failures']) if c['failures'] else f"{c['complete']}/{c['total']} simulations complete; all captured checks pass.") + ('\n' + '; '.join(dict.fromkeys(p['source'] for p in c['points'])) if c['points'] else ''))
        self.inspect_button.setEnabled(bool(c and c['runs']))
        self.apply_button.setEnabled(bool(c and not self.experiment_gmid and c['state'] == 'Passed' and self.report['complete'] and design_digest(self.studio.project) == m['base_design_hash']))
        self.estimate_button.setEnabled(bool(c and self.experiment_gmid and c['points'] and c['points'][0].get('current_density')))

    def inspect(self):
        from .analog_run_ui import RunInspector
        row = next((r for r in self.studio.run_manager.rows if r['id'] == self.run_choice.currentData()), None)
        if not row: raise ValueError('Select a candidate and condition to inspect.')
        self.inspector = RunInspector(self.studio, row); self.inspector.show()

    def apply(self):
        c = self.selected(); m = self.manifest()
        if not c: raise ValueError('Select a passing candidate to review and apply.')
        self.workspace.require_saved_setup()
        self.studio.commit(lambda p: optimizer.apply_candidate(p, m, self.studio.run_manager.rows, c['candidate']), 'Apply analog optimizer candidate ' + str(c['candidate']))
        self.workspace.reload_setup(); self.render(); self.summary.setText('Candidate applied. Undo restores the prior parameters. Rerun layout and extracted verification for the updated design.')

    def cancel(self):
        if self.report: self.studio.run_manager.cancel(list(self.report['current'].values()))

    def resume(self):
        m = self.manifest()
        if m: self.enqueue(m, variation_runs.pending(m, self.studio.run_manager.rows))

    def estimate(self):
        c = self.selected()
        if not c or not c['points']: raise ValueError('Select a measured gm/Id point.')
        value = optimizer.width_estimate(c['points'][0], self.desired_current.text())
        self.details.appendPlainText(f'Estimated total W = {value:.6g} m at the selected L and bias. Width scaling is an initial estimate; validate the new circuit in Circuit search before applying.')

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export optimizer results', 'analog-optimizer.csv', 'CSV (*.csv)')
        if not path: return
        output = io.StringIO(); writer = csv.writer(output)
        m=self.manifest();report=optimizer.evaluate(m,self.studio.run_manager.rows)
        writer.writerow(['Experiment','Base design hash','Candidate','State','Worst objective','Objective unit','Parameters','gm/Id (1/V)','Id (A)','gm (S)','VGS (V)','VDS (V)','Id/W (A/m)','Bias margin (V)','Condition','Source','Failures'])
        for candidate in report['candidates']:
            for point in candidate['points'] or [{}]:
                writer.writerow([m['id'],m['base_design_hash'],candidate['candidate'],candidate['state'],candidate['worst_value'],m['spec'].get('objective',{}).get('unit',''),json.dumps(candidate['changes'],sort_keys=True),
                    *[point.get(key) for key in ('gmid','id','gm','vgs','vds','current_density','headroom')],condition_text(point['labels']) if point.get('labels') else '',point.get('source',''),' | '.join(candidate['failures'])])
        atomic_write(path, output.getvalue())
