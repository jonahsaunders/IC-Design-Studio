"""Native analog recipes, saved characterization controls and case overlays."""
import json, shutil
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QFileDialog)
from .model import clone, design_digest, atomic_write
from .testbenches import get
from .characterization import prepared_cases, read_case, csv_text
from .plot import WavePlot, trace_colors


class AnalogMixin:
    def make_ui(self):
        super().make_ui()
        self._characterization_result = None
        page = QWidget(); v = QVBoxLayout(page)
        self.characterization_note = QLabel('Choose a saved testbench, configure a study, then characterize its fixture.'); self.characterization_note.setWordWrap(True); v.addWidget(self.characterization_note)
        row = QHBoxLayout()
        for title, fn in [('Configure…', self.characterization_dialog), ('Run saved study', self.run_characterization), ('Show waveforms', self.characterization_waveforms), ('Export CSV…', self.export_characterization)]: row.addWidget(self.button(title, fn=fn))
        self.characterization_probe = QComboBox(); self.characterization_probe.setAccessibleName('Characterization waveform probe'); row.addWidget(self.characterization_probe, 1)
        self.characterization_stage = QComboBox(); self.characterization_stage.addItems(['Both implementations', 'Schematic', 'Post-layout']); self.characterization_stage.setAccessibleName('Waveform implementation'); row.addWidget(self.characterization_stage); self.characterization_stage.hide(); v.addLayout(row)
        self.characterization_table = QTableWidget(); table = self.characterization_table; table.verticalHeader().hide()
        table.setEditTriggers(QAbstractItemView.NoEditTriggers); table.setSelectionBehavior(QAbstractItemView.SelectRows); table.setSelectionMode(QAbstractItemView.ExtendedSelection); table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents); v.addWidget(table, 1)
        self.characterization_plot = WavePlot(); v.addWidget(self.characterization_plot, 1)
        self.characterization_legend = QLabel('Select up to eight rows to overlay one voltage or current probe.'); self.characterization_legend.setWordWrap(True); v.addWidget(self.characterization_legend)
        self.characterization_tab = self.results_tabs.addTab(page, 'Characterization')
        self.characterization_probe.currentIndexChanged.connect(lambda *_: self.guard(self.characterization_waveforms) if self._characterization_result else None)
        self.characterization_stage.currentIndexChanged.connect(lambda *_: self.guard(self.characterization_waveforms) if self._characterization_result else None)

    def make_actions(self):
        super().make_actions()
        menus = {a.text().replace('&', ''): a.menu() for a in self.menuBar().actions() if a.menu()}
        self.action(menus['File'], 'New PDK current mirror', lambda: self.new_analog('current_mirror'))
        self.action(menus['File'], 'New PDK differential pair', lambda: self.new_analog('differential_pair'))
        self.action(menus['Analysis'], 'Configure saved-bench characterization…', self.characterization_dialog)
        self.action(menus['Analysis'], 'Run saved-bench characterization', self.run_characterization)
        self.action(menus['Design'], 'Generate current mirror layout…', self.mirror_layout_dialog)

    def mirror_layout_dialog(self):
        if not self.idle_edit(): return
        from .analog_layout import generate_mirror
        cid = self.cid
        def build():
            p = clone(self.project); c = next(c for c in p['cells'] if c['id']==cid)
            generate_mirror(p, cid, bool(c.get('mirror_layout')))
            return p, 'Generate an editable equal-device SKY130 mirror with explicit source/body contacts and three ports. Equal W/L, footprint orientation and terminal alignment are checked after edits. Regeneration replaces this recipe’s geometry and routing; undo restores the prior layout. Run the saved bench and physical verification after applying.'
        return self.review_dialog('Generate current mirror layout', build)

    def inverter_layout_dialog(self):
        c = self.cell
        if c.get('mirror_layout') or (len(c['devices'])==2 and all(d['kind']=='NMOS' for d in c['devices'])):
            return self.mirror_layout_dialog()
        return super().inverter_layout_dialog()

    def new_analog(self, kind):
        from .analog import reference
        p, cid, key = reference(self.project['pdk'], kind)
        if not self.maybe_save(): return
        self.set_project(p); self._selected_testbench = key; self.cid = p['top']; self.mode_combo.setCurrentIndex(0); self.refresh(True); self.open_testbenches()

    def characterization_dialog(self):
        if not self.idle_edit(): return
        t = clone(self.selected_testbench()); spec = t.get('characterization', {})
        kinds = {'Parameter sweep': 'sweep', 'PVT corners': 'pvt', 'Tolerance Monte Carlo': 'monte_carlo'}
        def submit(v):
            study = {'kind': kinds[v['kind']], 'target': v['target'].strip(), 'compare_layout': v['implementation']=='Schematic and post-layout'}
            split = lambda key: [part.strip() for part in v[key].split(',') if part.strip()]
            if study['kind'] == 'sweep': study['values'] = split('values')
            elif study['kind'] == 'pvt': study.update(corners=split('corners'), voltages=split('voltages'), temperatures=split('temperatures'))
            else:
                from .model import scalar
                study.update(count=int(v['count']), seed=int(v['seed']), variations=[{'target': study['target'], 'relative_sigma': scalar(v['sigma'])/100, 'distribution': 'normal'}])
            prepared_cases(self.project, get(self.project, t['id']), study)
            self.commit(lambda p: get(p, t['id']).update(characterization=study), 'Save bench characterization')
            self.results_dock.show(); self.results_tabs.setCurrentIndex(self.characterization_tab)
        variation = spec.get('variations', [{}])[0]
        dlg = self.workflow_form('Saved-bench characterization', [
            ('kind', 'Study', list(kinds)), ('implementation', 'Implementations', ['Schematic only', 'Schematic and post-layout']), ('target', 'Fixture target', spec.get('target', variation.get('target', 'VDD.value'))),
            ('values', 'Sweep values', ', '.join(map(str, spec.get('values', ['1.6', '1.8'])))),
            ('corners', 'Model corners', ', '.join(spec.get('corners', ['nominal']))),
            ('voltages', 'Supply voltages', ', '.join(map(str, spec.get('voltages', [1.8])))),
            ('temperatures', 'Temperatures (°C)', ', '.join(map(str, spec.get('temperatures', [0, 27, 85])))),
            ('sigma', 'Tolerance sigma (%)', str(float(variation.get('relative_sigma', .05))*100)),
            ('count', 'Trials', str(spec.get('count', 20))), ('seed', 'Random seed', str(spec.get('seed', 1)))], submit,
            'Bench: ' + t['name'] + '. Uses its saved analysis, probes and every measurement limit. Targets refer to source/load names in the fixture. Simulation runs through ngspice.')
        def visible():
            from PySide6.QtWidgets import QFormLayout
            form = dlg.findChild(QFormLayout); kind = kinds[dlg.fields['kind'].currentText()]
            keys = {'sweep': {'values'}, 'pvt': {'corners', 'voltages', 'temperatures'}, 'monte_carlo': {'sigma', 'count', 'seed'}}[kind]
            for key in ('values', 'corners', 'voltages', 'temperatures', 'sigma', 'count', 'seed'): form.setRowVisible(dlg.fields[key], key in keys)
        dlg.fields['kind'].currentTextChanged.connect(visible)
        dlg.fields['implementation'].setCurrentText('Schematic and post-layout' if spec.get('compare_layout') else 'Schematic only')
        dlg.fields['kind'].setCurrentText(next(k for k, val in kinds.items() if val == spec.get('kind', 'sweep'))); visible()
        return dlg

    def run_characterization(self):
        if not self.flush_inspector(): return
        t = self.selected_testbench()
        if not t.get('characterization'): raise ValueError('Configure a characterization study for this saved bench first.')
        prepared_cases(self.project, t, t['characterization'])
        settings = {'type': 'characterization', 'testbench': t['id'], 'study': clone(t['characterization'])}
        if t['characterization'].get('compare_layout'):
            settings['tools'] = {n: self.settings.value('engine/'+n, '') or shutil.which(n) or '' for n in ('magic','netgen','ngspice')}
        self.start_job(settings, 'ngspice')
        self.results_tabs.setCurrentIndex(self.characterization_tab)

    def add_result(self, r):
        super().add_result(r)
        if 'characterization_rows' in r: self.show_characterization(r)

    def select_run(self, index):
        super().select_run(index)
        if self.result and 'characterization_rows' in self.result: self.show_characterization(self.result)

    def job_finished(self, code, status):
        super().job_finished(code, status)
        if self.result and 'characterization_rows' in self.result: self.results_tabs.setCurrentIndex(self.characterization_tab)

    def refresh(self, fit=False):
        super().refresh(fit)
        if not hasattr(self, 'characterization_note'): return
        r = self._characterization_result
        if r and r['project_id'] != self.project['id']:
            self._characterization_result = None; self.characterization_table.setRowCount(0); self.characterization_probe.clear(); self.characterization_plot.set_result(None); self.characterization_note.setText('Choose a saved testbench and run its characterization.'); self.characterization_legend.clear()
        elif r: self.characterization_status()

    def characterization_status(self):
        r = self._characterization_result
        stale = r['design_hash'] != design_digest(self.project)
        s = r['summary']; self.characterization_note.setText(('STALE — design or bench changed. ' if stale else '') + r['testbench']['name'] + f" · {r['status'].upper()} · {s['passed']}/{s['runs']} cases passed · {s['failed']} failed. " + ('Measurements: schematic → post-layout (delta). Every case includes DRC and LVS.' if r.get('layout_comparison') else 'Select rows to compare waveforms.'))

    def show_characterization(self, r):
        self._characterization_result = r; self.characterization_stage.setVisible(bool(r.get('layout_comparison'))); rows = r['characterization_rows']; measures = r['testbench']['measurements']; labels = [key for key in ('value', 'corner', 'voltage', 'temperature', 'trial') if any(key in row for row in rows)]
        table = self.characterization_table; table.setColumnCount(3+len(labels)+len(measures)); table.setHorizontalHeaderLabels(['Run', *[r['settings']['study'].get('target','Value') if key=='value' else key.title() for key in labels], 'Status', *[m['name'] for m in measures], 'Detail']); table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            by = {m['name']: m for m in row['measurements']}
            values = [row['index'], *[row.get(key, '') for key in labels], row['status']]
            values += [(f"{by[m['name']]['value']:.6g} {by[m['name']].get('unit','')} · {by[m['name']]['status']}" if 'value' in by.get(m['name'], {}) else 'failed') for m in measures]
            if r.get('layout_comparison'):
                before = {m['name']:m for m in row.get('before_measurements',[])}
                comparison = {m['name']:m for m in row.get('comparison',[])}
                for j,m in enumerate(measures):
                    a = before.get(m['name'],{}); b = by.get(m['name'],{}); delta = comparison.get(m['name'],{}).get('delta')
                    values[2+len(labels)+j] = (f"{a['value']:.6g}" if 'value' in a else 'unavailable')+' → '+(f"{b['value']:.6g} {b.get('unit','')}" if 'value' in b else 'unavailable')+(f" (Δ {delta:+.4g})" if delta is not None else '')
            values += ['; '.join([row.get('error', '')]+[m.get('error', '') for m in row['measurements']]).strip('; ')]
            for col, value in enumerate(values): table.setItem(i, col, QTableWidgetItem(f'{value:.6g}' if isinstance(value,float) else str(value)))
        probe = self.characterization_probe; probe.blockSignals(True); probe.clear()
        for n in r['testbench']['probes']: probe.addItem('V(' + n + ')', ('voltage', n.lower()))
        for n in sorted({m['source'] for m in measures if m['kind']=='current'}): probe.addItem('I(' + n + ')', ('current', n.lower()))
        probe.blockSignals(False)
        if rows: table.selectRow(0)
        self.characterization_plot.set_result(None); self.characterization_status()

    def characterization_waveforms(self):
        r = self._characterization_result
        if not r: raise ValueError('Run characterization first.')
        indices = sorted({i.row() for i in self.characterization_table.selectionModel().selectedRows()})
        if not 1 <= len(indices) <= 8: raise ValueError('Select one to eight characterization rows.')
        kind, probe = self.characterization_probe.currentData(); samples = []; legend = []
        stages = ['schematic']
        if r.get('layout_comparison'):
            stages = [['schematic','post-layout'], ['schematic'], ['post-layout']][self.characterization_stage.currentIndex()]
        if len(indices)*len(stages)>8: raise ValueError('Select at most four rows for both implementations, or eight for one implementation.')
        for index in indices:
            for stage in stages:
                wave = clone(read_case(r, index, stage))
                wave['traces'] = {probe: wave['currents' if kind=='current' else 'traces'][probe]}
                wave['plot_unit'] = 'A' if kind=='current' else 'V'
                samples.append(wave); legend.append(f'Run {index+1}'+(' · '+stage if r.get('layout_comparison') else ''))
        plot = self.characterization_plot; plot.dark = self.layout.dark; plot.set_result(samples[0], [probe], overlays=samples[1:])
        self.characterization_legend.setText(' · '.join(f'<span style="color:{trace_colors(plot.dark)[i%6]}">{label}</span>' for i,label in enumerate(legend)) + (' · STALE' if r['design_hash'] != design_digest(self.project) else ''))

    def export_characterization(self):
        if not self._characterization_result: raise ValueError('Run characterization first.')
        path, _ = QFileDialog.getSaveFileName(self, 'Export characterization', 'characterization.csv', 'CSV (*.csv)')
        if path: atomic_write(path, csv_text(self._characterization_result))
