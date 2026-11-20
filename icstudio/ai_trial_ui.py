"""Preview, execute and compare isolated Studio simulation jobs."""
from pathlib import Path
from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget)
from . import ai_investigation as investigation
from .analog_widgets import table, fill, actions
from .model import clone, save_project, uid
from .plot import WavePlot, engineering


def draft_job(studio, cells, bench):
    project = clone(studio.project)
    project['cells'].extend(clone(cells))
    project.setdefault('testbenches', []).append(clone(bench))
    from .spice_program import find_ngspice
    exe = find_ngspice(studio.settings.value('engine/ngspice', ''))
    if not exe:
        raise ValueError('Set up ngspice in Tools to simulate a saved testbench.')
    return studio.prepare_simulation(dict(type='testbench', testbench=bench['id'], executable=str(exe)),
                                     'ngspice', project, bench['bench_cell'])


class Overlay(QWidget):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        layout = QVBoxLayout(self)
        self.caption = QLabel()
        self.caption.setWordWrap(True)
        self.caption.setTextFormat(Qt.PlainText)
        layout.addWidget(self.caption)
        self.trace = QComboBox()
        self.trace.setAccessibleName('Waveform to compare')
        layout.addWidget(self.trace)
        self.plot = WavePlot()
        self.plot.dark = studio.dark
        layout.addWidget(self.plot, 1)
        self.metrics = table(['Measurement', 'Baseline', 'Comparison', 'Change', 'Unit'])
        layout.addWidget(self.metrics)
        self.trace.currentIndexChanged.connect(self.plot_trace)
        self.before = self.after = None

    def changeEvent(self, event):
        if event.type() == QEvent.PaletteChange and hasattr(self,'plot'):
            self.plot.dark = self.studio.dark
            self.plot.update()
        super().changeEvent(event)

    def display(self, first, second=None, definition=None, probe=None):
        def view(row):
            result = row.get('result') or {}
            return (investigation.trace_view(result, definition or {}, probe) if definition or probe else result) or {}
        self.before = view(first)
        self.after = view(second) if second else None
        self.trace.clear()
        compatible = not second or (self.before.get('x_label'), self.before.get('plot_unit','V')) == (
            self.after.get('x_label'), self.after.get('plot_unit','V'))
        names = [n for n in self.before.get('traces', {}) if not second or n in self.after.get('traces', {})]
        self.trace.addItems(names if compatible else [])
        self.plot_trace()
        def describe(row):
            return row['name'] + ' · r' + str(row['job']['project']['revision']) + ' · ' + ', '.join(
                f'{k} {v}' for k,v in investigation.conditions(row['job']).items())
        self.caption.setText(('Dashed — ' if second else '') + describe(first) +
                             ('\nSolid — ' + describe(second) if second else '') +
                             ('\nNo matching saved waveform.' if not self.trace.count() else ''))
        other = {c['identity']: c['actual'] for c in investigation.checks(second)} if second else {}
        rows = []
        for check in investigation.checks(first):
            a = check['actual']
            b = other.get(check['identity'], {})
            left, right = a.get('value'), b.get('value')
            delta = right-left if isinstance(left,(float,int)) and isinstance(right,(float,int)) else None
            def reading(actual):
                value = actual.get('value')
                return (f'{value:.6g} · ' if isinstance(value, (float,int)) else '') + str(actual.get('status','—'))
            rows.append([a.get('name'), reading(a), reading(b), delta, check['definition'].get('unit','')])
        fill(self.metrics, rows)
        self.metrics.setVisible(bool(rows))

    def plot_trace(self):
        name = self.trace.currentText()
        primary = self.after or self.before
        self.plot.set_result(primary if name else None, [name] if name else [], self.before if self.after and name else None)


class Trial(QDialog):
    def __init__(self, studio, job, name, *, single=False, suggestion=None, definition=None):
        super().__init__(studio)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.studio, self.job, self.name = studio, job, name
        self.single, self.definition = single, definition
        self.rows = []
        self.variant = None
        self.setWindowTitle('Run Draft' if single else 'Compare One Change')
        self.resize(750, 650)
        root = QVBoxLayout(self)
        self.params = {} if single else investigation.parameters(job)
        if not single and not self.params:
            raise ValueError('Choose an analog analysis or saved testbench for this experiment.')
        self.target, self.value = QComboBox(), QLineEdit()
        self.base = QLabel()
        if not single:
            form = QFormLayout()
            root.addLayout(form)
            for key in self.params:
                self.target.addItem('Temperature (°C)' if key == 'temperature' else key, key)
            form.addRow('Change', self.target)
            form.addRow('Baseline value', self.base)
            form.addRow('Variant value', self.value)
        self.overlay = Overlay(studio)
        root.addWidget(self.overlay, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        root.addWidget(self.status)
        self.start, self.stop, self.keep, close = actions(root, [
            ('Run Draft' if single else 'Run Both', self.run), ('Stop', self.stop_runs),
            ('Keep Variant…', self.save_variant), ('Close' if single else 'Discard Variant', self.close)], self.call)
        self.start.setProperty('role','primary')
        self.stop.setEnabled(False)
        self.keep.setVisible(not single)
        self.keep.setEnabled(False)
        self.target.currentIndexChanged.connect(self.target_changed)
        self.value.textChanged.connect(self.invalidate)
        self.target_changed()
        if suggestion and suggestion[0] in self.params:
            self.target.setCurrentIndex(self.target.findData(suggestion[0]))
            self.value.setText(suggestion[1])
        studio.run_manager.completed.connect(self.completed)

    def call(self, fn):
        try:
            fn()
        except (ValueError, OSError, RuntimeError) as exc:
            self.status.setText(str(exc))

    def target_changed(self):
        value = self.params.get(self.target.currentData(), '')
        self.base.setText(str(value) if self.target.currentData()=='temperature' else engineering(value) if value != '' else '')
        self.value.clear()
        self.invalidate()

    def invalidate(self):
        self.variant = None
        self.keep.setEnabled(False)
        self.overlay.hide()
        self.start.setEnabled(self.single or bool(self.value.text().strip()))
        self.status.setText(f"{self.name} · {self.job['engine']} · revision {self.job['project']['revision']}")

    def run(self):
        if any(r['state'] in ('Running','Queued','Stopping') for r in self.rows):
            return
        jobs = [clone(self.job)]
        names = [self.name + (' · draft' if self.single else ' · baseline')]
        if not self.single:
            key = self.target.currentData()
            self.variant = investigation.variant_job(self.job, key, self.value.text().strip())
            jobs.append(self.variant)
            names.append(self.name + ' · ' + key + ' = ' + self.value.text().strip())
        # Preserve actual conditions without re-entering the original plan's matrix.
        for job in jobs:
            labels = investigation.conditions(job)
            case = job.pop('case', {})
            supply = job.get('comparison_supply')
            supply_cell = job.get('comparison_supply_cell',job['cell'])
            if not supply and 'voltage' in labels:
                plan = next((p for p in job['project'].get('test_plans',[]) if p['id']==case.get('plan_id')), {})
                entry = next((e for e in plan.get('entries',[]) if e['id']==case.get('entry_id')), {})
                supply, supply_cell = entry.get('supply'), entry.get('cell',supply_cell)
            if supply:
                job['comparison_supply'] = supply
                job['comparison_supply_cell'] = supply_cell
                from .studies import get_target
                labels['voltage'] = get_target(job['project'],supply_cell,supply)
            job['comparison_conditions'] = labels
        self.overlay.hide()
        self.keep.setEnabled(False)
        self.rows = self.studio.run_manager.enqueue_many(jobs, self.studio.jobs_dir, names)
        self.update_results()

    def stop_runs(self):
        self.studio.run_manager.cancel(self.rows)
        self.update_results()

    def completed(self, row, result):
        if any(row['id'] == r['id'] for r in self.rows):
            self.update_results()

    def update_results(self):
        busy = any(r['state'] in ('Running','Queued','Stopping') for r in self.rows)
        for widget in (self.start, self.target, self.value):
            widget.setEnabled(not busy)
        self.stop.setEnabled(busy)
        self.keep.setEnabled(False)
        self.status.setText('  ·  '.join(r['name'] + ' — ' + r['state'] for r in self.rows))
        if not busy and all(r.get('result') for r in self.rows):
            self.overlay.display(self.rows[0], self.rows[1] if len(self.rows)>1 else None, self.definition)
            self.overlay.show()
            self.keep.setEnabled(not self.single)
        elif not busy:
            self.status.setText(self.status.text() + '\n' + '\n'.join(r.get('log','')[-500:] for r in self.rows if not r.get('result')))

    def save_variant(self):
        if not self.variant or not self.keep.isEnabled():
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Keep Variant as Project', 'comparison-variant.icproj', 'Studio projects (*.icproj)')
        if not path:
            return
        if self.studio.path and Path(path).resolve() == Path(self.studio.path).resolve():
            raise ValueError('Choose a separate project file for this variant.')
        p = clone(self.variant['project'])
        p.update(id=uid(), name=(p['name'][:110] + ' variant'), top=self.variant['cell'])
        analysis = (investigation.bench_for(self.variant) or {}).get('analysis', self.variant['settings'])
        for key in (*p['analysis'], 'type','temperature','corner'):
            if key in analysis:
                p['analysis'][key] = clone(analysis[key])
        save_project(p, path)
        self.status.setText('Saved editable variant to ' + path)

    def closeEvent(self, event):
        if any(r['state'] in ('Running','Queued') for r in self.rows):
            self.stop_runs()
        super().closeEvent(event)

    def reject(self):
        if any(r['state'] in ('Running','Queued') for r in self.rows):
            self.stop_runs()
        super().reject()
