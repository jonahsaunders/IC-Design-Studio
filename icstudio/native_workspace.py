"""Native migration review, device editing and independent program execution."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QDialogButtonBox,
    QFileDialog, QTableWidgetItem, QLineEdit, QFormLayout, QPlainTextEdit,
    QListWidget, QListWidgetItem, QInputDialog, QCheckBox)
from .model import clone, uid, digest, scalar
from .native_spice import native, netlist
from .spice_program import probes, find_ngspice


class NativeWorkspaceMixin:
    def make_actions(self):
        super().make_actions()
        self.action(self.task_menus['File'], 'Import and migrate Xschem project…', self.migrate_xschem_file)
        self.action(self.task_menus['File'], 'Migrate current project to native…', self.migrate_current_project)
        self.action(self.task_menus['Help'], 'Native migration report…', self.show_native_report)
        self.action(self.task_menus['Help'], 'Native workflow guide', lambda:self.open_editor_doc('UPDATE_0.20.md'))
        self.action(self.task_menus['Help'], 'Native catalog migration guide', lambda:self.open_editor_doc('NATIVE_CATALOG_MIGRATION.md'))
        for title,name in [('Native divider and studies','native-divider.icproj'),('Native RC and extracted comparison','native-rc.icproj')]:
            self.action(self._task_submenus['File/Examples'],title,lambda name=name:self.open_engineering_example(name))
        self.action(self.task_menus['Layout'], 'Native device geometry mapping…', self.native_binding_dialog)
        self.action(self.task_menus['Verify'], 'Run KLayout rule script…', self.klayout_rules_dialog)
        self.action(self.task_menus['Verify'], 'Open KLayout findings…', self.open_klayout_report)
        self.reindex_commands()

    def klayout_rules_dialog(self):
        import shutil
        path,_=QFileDialog.getOpenFileName(self,'Select self-contained KLayout DRC script','','KLayout Ruby DRC (*.drc)')
        if not path:return
        executable=self.settings.value('engine/klayout','') or shutil.which('klayout')
        if not executable or not Path(executable).is_file():
            executable,_=QFileDialog.getOpenFileName(self,'Locate KLayout executable')
            if not executable:return
            self.settings.setValue('engine/klayout',executable)
        if not self.flush_inspector():return
        text=Path(path).read_text(encoding='utf-8')
        if len(text)>2_000_000:raise ValueError('The rule script exceeds 2 MB.')
        from .model import file_digest
        settings={'type':'klayout_drc','runset_text':text,'runset_hash':digest(text),'executable':executable,'executable_sha256':file_digest(executable),'timeout':600}
        job={'project':clone(self.project),'cell':self.cid,'engine':'klayout','settings':settings}
        self.run_manager.enqueue(job,self.jobs_dir,'KLayout rule verification');self.open_engineering_tab(self.simulation_tab)

    def open_klayout_report(self):
        from .klayout_verification import read_report
        path,_=QFileDialog.getOpenFileName(self,'Open KLayout report','','KLayout report database (*.lyrdb)')
        if path:self.show_klayout_report(read_report(path))

    def show_klayout_report(self,report):
        dlg=QDialog(self);dlg.setWindowTitle('KLayout findings');dlg.resize(1050,640);v=QVBoxLayout(dlg)
        v.addWidget(QLabel(str(report['count'])+' findings · double-click a row to locate its cell and geometry'))
        table=self.simulation_table(['Cell','Rule','Details']);table.setRowCount(report['count']);v.addWidget(table)
        for i,row in enumerate(report['findings']):
            for j,key in enumerate(('cell','rule','details')):table.setItem(i,j,QTableWidgetItem(row[key]))
        def locate(i,_):
            from PySide6.QtCore import QPointF
            row=report['findings'][i];cell=next((c for c in self.project['cells'] if c['name']==row['cell']),None)
            if not cell:raise ValueError('This report cell is not in the open project.')
            self.cid=cell['id'];self.refresh();self.mode_combo.setCurrentIndex(1)
            if row['boxes_um']:
                from .layout import polygon,kdb
                boxes=[kdb().Box(*(round(x*1000) for x in b)) for b in row['boxes_um']]
                ids=[s['id'] for s in cell['shapes'] if any(polygon(s).bbox().overlaps(b) for b in boxes)]
                if ids:self.select(ids,'layout')
                self.layout.fit()
        table.cellDoubleClicked.connect(lambda i,j:self.guard(lambda:locate(i,j)));dlg.table=table;self._klayout_report_dialog=dlg;dlg.show();return dlg

    def add_result(self,result):
        super().add_result(result)
        if result.get('klayout_report'):self.show_klayout_report(result['klayout_report'])

    def native_binding_dialog(self, ident=None):
        selected=[d for d in self.cell['devices'] if d['id']==ident or ident is None and d['id'] in self.selection]
        if len(selected)!=1:raise ValueError('Select one native device in the schematic.')
        d=selected[0];cid=self.cid;ident=d['id'];params=d.get('native_spice',{}).get('parameters',{})
        if not params or d['kind']=='X':raise ValueError('Select a native leaf device with editable electrical parameters.')
        from .native_physical import ROLES,bind
        def configure(values):
            kind=values['kind'];old=d.get('physical_binding',{});keys=('value',) if kind in ('R','C') else ('w','l')
            fields=[('pin_'+k,'Geometry '+k+' → electrical terminal',list(d['nets'])) for k in ROLES[kind]]
            for k in keys:
                mapping=old.get('parameters',{}).get(k,{})
                fields.extend([(k,'Native '+k+' parameter',mapping.get('name',k if k in params else next(iter(params)))),(k+'_scale',k+' multiplier to '+('SI units' if k=='value' else 'metres'),str(mapping.get('scale',1)))])
            def save(v):
                binding={'version':1,'kind':kind,'terminals':{k:v['pin_'+k] for k in ROLES[kind]},'parameters':{k:{'name':v[k],'scale':scalar(v[k+'_scale'])} for k in keys}}
                self.commit(lambda p:bind(p,cid,ident,binding),'Map native device to geometry')
                self.statusBar().showMessage('Mapping saved. Use Place / regenerate to create or update geometry.',10000)
            self.workflow_form('Map '+d['name']+' to geometry',fields,save,'Declare terminal roles and model units explicitly. For W/L stored as micrometre numbers use 1u. Available parameters: '+', '.join(params)+'. Geometry uses the active technology recipes and their qualification limits.')
        return self.workflow_form('Native geometry mapping',[('kind','Geometry recipe',list(ROLES))],configure,'This mapping retains the native electrical definition. It does not prove process equivalence; verify generated geometry with the corresponding extraction and rule decks.')

    def migrate_xschem_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Migrate Xschem project', '', 'Xschem schematic (*.sch)')
        if path:
            from .native_migration import review_path
            roots = self.settings.value('xschem/library_paths', []) or []
            if isinstance(roots, str): roots = [roots]
            self.show_migration_review(review_path(path, roots), path, roots)

    def migrate_current_project(self):
        from .native_migration import review
        if not self.flush_inspector() or not self.flush_analysis(): return
        if native(self.project):
            from .migration_ui import show
            return show(self,project=clone(self.project))
        self.show_migration_review(review(self.project))

    def show_native_report(self):
        report = self.project.get('native_migration')
        if not report: raise ValueError('This project has no migration report. Use File → Import and migrate Xschem project.')
        self.show_migration_review({'candidate': None, 'status':report['status'], 'items':report['items']+report.get('catalog',{}).get('items',[])}, readonly=True)

    def show_migration_review(self, result, source=None, roots=None, readonly=False):
        if not readonly:
            from .migration_ui import show
            return show(self,source=source,libraries=roots,project=None if source else clone(self.project),initial=result)
        dlg = QDialog(self); dlg.setWindowTitle('Native project migration'); dlg.resize(1050, 720)
        layout = QVBoxLayout(dlg)
        title = QLabel('Migration ' + ('complete' if result['status'] == 'Complete' else 'needs attention'))
        title.setStyleSheet('font-size:22px;font-weight:600'); layout.addWidget(title)
        text = QLabel('Native devices, symbols and model files are stored in the project. Original sources remain in its recovery archive. Complete describes conversion; simulation validation is a separate step. Review every item marked Needs attention or Fixed representation.')
        text.setWordWrap(True); layout.addWidget(text)
        table = self.simulation_table(['Object', 'Migration', 'Details']); table.setRowCount(len(result['items']))
        table.setColumnWidth(0, 160); table.setColumnWidth(1, 165); table.horizontalHeader().setStretchLastSection(True)
        for i, item in enumerate(result['items']):
            for j, key in enumerate(('subject', 'status', 'detail')):
                cell = QTableWidgetItem(item[key]); cell.setToolTip(item['detail']); table.setItem(i, j, cell)
        layout.addWidget(table, 1)
        table.cellDoubleClicked.connect(lambda row, _: self._select_migration_object(result['items'][row]))
        if source:
            def add_folder():
                folder = QFileDialog.getExistingDirectory(dlg, 'Locate a custom library')
                if folder:
                    from .native_migration import review_path
                    paths = list(roots or []) + [folder]; self.settings.setValue('xschem/library_paths', paths)
                    updated = review_path(source, paths); dlg.close(); self.show_migration_review(updated, source, paths)
            layout.addWidget(self.button('Add library folder and review again…', fn=lambda: self.guard(add_folder)))
        buttons = QDialogButtonBox(QDialogButtonBox.Close if readonly else QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        if not readonly:
            save = buttons.button(QDialogButtonBox.Save)
            save.setText('Save native project…' if result['status'] == 'Complete' else 'Save migration draft…')
            save.setEnabled(result['candidate'] is not None)
            def accept():
                from .model import save_project
                from .native_migration import export_report
                path, _ = QFileDialog.getSaveFileName(dlg, 'Save independent native project', (result['candidate']['name'] + '-native.icproj'), 'IC Studio project (*.icproj)')
                if not path: return
                if self.path and Path(path).resolve() == Path(self.path).resolve():
                    raise ValueError('Choose a new filename to preserve the source project.')
                if not self.maybe_save(): return
                save_project(result['candidate'], path)
                export_report(result['candidate'], Path(path).with_suffix('.migration.json'))
                self.set_project(result['candidate'], path); self.schematic.fit(); dlg.accept()
            buttons.accepted.connect(lambda: self.guard(accept))
        buttons.rejected.connect(dlg.reject)
        dlg.table = table; dlg.result_data = result; self._migration_dialog = dlg; dlg.show(); return dlg

    def _select_migration_object(self, item):
        if item.get('cell') in {c['id'] for c in self.project['cells']} and item.get('object'):
            self.cid = item['cell']; self.refresh(); self.select([item['object']], 'schematic'); self.reveal_properties()

    def set_project(self, p, path=None):
        super().set_project(p, path)
        if native(p) and hasattr(self, 'xschem_probes'):
            self.xschem_probes.setText(p['analysis'].get('probes') or probes(p))
            self.analysis_dirty = False
            self.statusBar().showMessage('Native project opened · embedded models · independent netlister', 10000)

    def refresh(self, fit=False):
        super().refresh(fit)
        if native(self.project):
            variant = self.project['spice'].get('library_lock', {}).get('variant', '')
            self.tech_name.setText((variant or 'Native circuit') + ' · embedded models')
            self.tech_detail.setText('Native device definitions · portable simulation program')
            self.analysis_visibility()
            if hasattr(self, 'corner_combo'):
                from .native_analysis import corner_sections
                self.corner_combo.blockSignals(True); self.corner_combo.clear()
                self.corner_combo.addItems(['nominal'] + [s for s in corner_sections(self.project) if s != 'nominal'])
                self.corner_combo.setCurrentText(self.project['analysis'].get('corner', 'nominal'))
                self.corner_combo.setToolTip('Nominal retains the saved library sections. Other entries exist in every referenced library.')
                self.corner_combo.setEnabled(self.analysis_type.currentData() != 'program')
                self.corner_combo.blockSignals(False)

    def make_analysis_panel(self):
        panel = super().make_analysis_panel()
        self.native_noise_output = QLineEdit(); self.native_noise_output.setAccessibleName('Noise output net')
        self.native_noise_output.setPlaceholderText('out'); self.native_noise_output.textChanged.connect(self.analysis_changed)
        self.analysis_form.addRow('Noise output net', self.native_noise_output)
        self.native_noise_output.hide(); self.analysis_form.labelForField(self.native_noise_output).hide()
        self.native_dc_startup = QCheckBox('Use first-point voltage guesses')
        self.native_dc_startup.setToolTip('Solve the first DC point once and use its voltages as convergence hints. Hints are released before each final solution; accuracy limits stay unchanged.')
        self.native_dc_startup.toggled.connect(self.analysis_changed)
        self.analysis_form.addRow('DC startup', self.native_dc_startup)
        self.native_dc_startup.hide(); self.analysis_form.labelForField(self.native_dc_startup).hide()
        return panel

    def load_analysis(self):
        super().load_analysis()
        for i in range(self.analysis_type.count()):
            self.analysis_type.model().item(i).setEnabled(not native(self.project) or self.analysis_type.itemData(i) in ('program','op','tran','dc','ac','noise'))
        if native(self.project):
            self._loading_analysis = True
            from .native_analysis import sources
            typ = self.project['analysis'].get('type', 'program')
            self.analysis_type.setCurrentIndex(self.analysis_type.findData(typ))
            self.analysis_engine.setCurrentIndex(self.analysis_engine.findData('ngspice'))
            self.analysis_source.clear(); self.analysis_source.addItems([v[0] for v in sources(self.project, self.cid)])
            self.analysis_source.setCurrentText(self.project['analysis'].get('source', ''))
            self.native_noise_output.setText(self.project['analysis'].get('output', 'out'))
            self.native_dc_startup.setChecked(self.project['analysis'].get('dc_startup', False))
            self._loading_analysis = False; self.analysis_dirty = False
            self.analysis_visibility()

    def analysis_visibility(self, *args):
        super().analysis_visibility(*args)
        if hasattr(self, 'native_noise_output'):
            visible = native(self.project) and self.analysis_type.currentData() == 'noise'
            self.native_noise_output.setVisible(visible); self.analysis_form.labelForField(self.native_noise_output).setVisible(visible)
        if hasattr(self, 'native_dc_startup'):
            visible = native(self.project) and self.analysis_type.currentData() == 'dc'
            self.native_dc_startup.setVisible(visible); self.analysis_form.labelForField(self.native_dc_startup).setVisible(visible)
        if native(self.project) and hasattr(self, 'xschem_controls'):
            program = self.analysis_type.currentData() == 'program'
            self.xschem_controls.setVisible(program); self.analysis_engine.setEnabled(False); self.analysis_type.setEnabled(True)
            if hasattr(self, 'corner_combo'): self.corner_combo.setEnabled(not program)
            for typ in ('temperature',):
                self.analysis_fields[typ].setVisible(not program); self.analysis_form.labelForField(self.analysis_fields[typ]).setVisible(not program)
            self.analysis_source.setVisible(self.analysis_type.currentData() in ('dc', 'noise'))
            self.analysis_form.labelForField(self.analysis_source).setVisible(self.analysis_type.currentData() in ('dc','noise'))
            self.analysis_caption.setText('Saved program: preserves loops and commands.' if program else 'Runs this analysis using embedded models. Saved control commands are excluded from this run. Use Variation cases for sweeps and tolerances.')

    def current_analysis_settings(self):
        if native(self.project):
            if self.analysis_type.currentData() == 'program':
                return {**clone(self.project['analysis']), 'type': 'program', 'probes': self.xschem_probes.text().strip() or probes(self.project), 'timeout': self.xschem_timeout.value() * 60}
            from .native_analysis import validate_settings
            a = super().current_analysis_settings()
            a.update(temperature=self.analysis_fields['temperature'].text().strip(), corner=self.corner_combo.currentText() or 'nominal', output=self.native_noise_output.text().strip())
            a['dc_startup'] = self.native_dc_startup.isChecked()
            a.pop('noise_source', None)
            validate_settings(self.project, self.cid, a); return a
        return super().current_analysis_settings()

    def prepare_simulation(self, settings, engine='builtin', project=None, cid=None):
        p = project or self.project
        if not native(p): return super().prepare_simulation(settings, engine, project, cid)
        from .native_analysis import ANALYSES, validate_settings
        typ = settings.get('type'); cid = p['top'] if typ == 'program' else (cid or self.cid)
        if typ in ANALYSES: validate_settings(p, cid, settings)
        elif typ != 'program': return super().prepare_simulation(settings, 'ngspice', p, cid)
        executable = find_ngspice(self.settings.value('engine/ngspice', ''))
        if not executable: raise ValueError('Choose ngspice in Analysis → Engine setup, or extract the complete desktop package.')
        job = {'project': clone(p), 'cell': cid, 'settings': clone(settings), 'engine': 'ngspice', 'executable': executable}
        # Recovery text is not a simulation dependency and need not be copied for every run.
        job['project'].get('native_migration', {}).pop('archive', None)
        from .run_environment import stamp
        job['environment'] = stamp(job); return job

    def export_spice(self):
        if not native(self.project): return super().export_spice()
        if not self.flush_inspector(): return
        directory = QFileDialog.getExistingDirectory(self, 'Export native SPICE circuit and models')
        if not directory: return
        target = Path(directory) / (self.project['name'] + '-spice')
        if target.exists() and any(target.iterdir()): raise ValueError('Choose an empty export destination.')
        netlist(self.project, target); self.statusBar().showMessage('Exported native circuit and model files to ' + str(target), 10000)

    def export_sch(self):
        if not self.flush_inspector():return
        return super().export_sch()

    def edit_xschem_program(self):
        if not native(self.project): return super().edit_xschem_program()
        programs = [d for c in self.project['cells'] for d in c['devices'] if d.get('native_spice', {}).get('type') == 'program']
        if not programs: raise ValueError('Place a native simulation program first.')
        d = programs[0]
        if len(programs) > 1:
            name, ok = QInputDialog.getItem(self, 'Simulation program', 'Program', [d['name'] for d in programs], 0, False)
            if not ok: return
            d = next(d for d in programs if d['name'] == name)
        return self.edit_native_properties(d['id'])

    def edit_native_properties(self, ident):
        if not self.flush_inspector(): return
        d = next(d for c in self.project['cells'] for d in c['devices'] if d['id'] == ident)
        definition = d['native_spice']; program = definition['type'] == 'program'
        dlg = QDialog(self); dlg.setWindowTitle(('Simulation program · ' if program else 'Device parameters · ') + d['name']); dlg.resize(760, 620)
        layout = QVBoxLayout(dlg); form = QFormLayout(); layout.addLayout(form)
        name = QLineEdit(d['name']); form.addRow('Designator', name); fields = {}
        if program:
            editor = QPlainTextEdit(definition['text']); editor.setLineWrapMode(QPlainTextEdit.NoWrap); editor.setAccessibleName('Native ngspice simulation program'); layout.addWidget(editor, 1)
        else:
            for key, value in definition['parameters'].items():
                field = QLineEdit(value); field.setAccessibleName('Native parameter ' + key)
                field.setToolTip('SPICE value or expression. Bare numbers retain the device model’s unit convention.')
                fields[key] = field; form.addRow(key, field)
            layout.addWidget(QLabel('Values retain their original model units. SPICE expressions remain editable.'))
            layout.addStretch()
        error = QLabel(); error.setWordWrap(True); layout.addWidget(error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); layout.addWidget(buttons)
        def save():
            try:
                def change(p):
                    obj = next(d for c in p['cells'] for d in c['devices'] if d['id'] == ident)
                    obj['name'] = name.text().strip(); info = obj['native_spice']
                    if program: info['text'] = editor.toPlainText()
                    else:
                        info['parameters'] = {k: field.text().strip() for k, field in fields.items()}
                        obj['symbol_context'].update(info['parameters'])
                    obj.setdefault('symbol_context', {})['name'] = obj['name']
                self.commit(change, 'Edit native program' if program else 'Edit native device parameters'); dlg.accept()
            except Exception as exc: error.setText(str(exc))
        buttons.accepted.connect(save); buttons.rejected.connect(dlg.reject)
        dlg.editor = editor if program else fields; dlg.name_field = name; dlg.buttons = buttons
        self._native_property_dialog = dlg; dlg.show(); return dlg

    def show_library(self):
        if not native(self.project): return super().show_library()
        from .component_browser import ComponentBrowser
        from .model import digest
        entries = []; seen = set()
        for c in self.project['cells']:
            for d in c['devices']:
                definition = d.get('native_spice', {})
                if definition.get('type') != 'device': continue
                source = d.get('component_source')
                if not source:
                    # Older native projects retained the original symbol files.
                    files = self.project.get('native_migration', {}).get('archive', {}).get('source_files', {})
                    from pathlib import PurePosixPath
                    paths=[PurePosixPath(path.replace('\\','/')) for path in files]
                    sources={path.parent.name for path in paths if path.suffix=='.sym' and path.stem==definition['label']}
                    source = next(iter(sources)) if len(sources) == 1 else 'Project definitions'
                identity = digest([source, definition['label'], definition.get('tokens'), definition.get('definition'), d.get('symbol')])
                if identity in seen: continue
                seen.add(identity); entries.append(dict(label=definition['label'], source=source, device=d))
        def preview(entry):
            d = entry['device']
            return d['symbol'], {**d.get('symbol_context', {}), 'name':'Preview', 'symname':entry['label']}
        def place(entry):
            if not self.flush_inspector(): return False
            d = clone(entry['device']); prefix = ''.join(ch for ch in d['name'] if not ch.isdigit()) or 'X'
            used = {d['name'].casefold() for d in self.cell['devices']}; number = 1
            while (prefix + str(number)).casefold() in used: number += 1
            d.update(id=uid(), name=prefix + str(number)); d.setdefault('symbol_context', {})['name'] = d['name']
            d.pop('net_labels', None); d.pop('terminal_ids', None); d.pop('net_ids', None)
            self.mode_combo.setCurrentIndex(0); self.cancel_tool(); self.schematic.placement = d; self.schematic.tool = 'place'
            self.schematic.drag = self.schematic.snap(self.schematic.model(self.schematic.rect().center()))
            self.schematic.setFocus(); self.schematic.update(); self.sync_tools()
        dlg = ComponentBrowser(self, 'Project device library', entries, preview, place)
        def standard():
            dlg.accept(); super(NativeWorkspaceMixin, self).show_library()
        dlg.add_button('Standard components and hierarchical cells…', standard)
        self._native_library_dialog = dlg; dlg.show(); return dlg

    def place_device_at(self, x, y):
        seed = self.schematic.placement
        if not native(self.project) or not seed or not seed.get('native_spice'):
            return super().place_device_at(x, y)
        seed = clone(seed); d = clone(seed); d.update(id=uid(), x=x, y=y)
        self.cancel_tool()
        self.commit(lambda p: next(c for c in p['cells'] if c['id'] == self.cid)['devices'].append(d), 'Place ' + d['name'])
        self.select([d['id']], 'schematic'); self.reveal_properties()
        if self.capture_repeat.isChecked():
            import re
            prefix = re.sub(r'\d+$', '', seed['name']) or 'X'; used = {d['name'].casefold() for d in self.cell['devices']}; number = 1
            while (prefix + str(number)).casefold() in used: number += 1
            seed['name'] = prefix + str(number); seed['symbol_context']['name'] = seed['name']
            self.schematic.placement = seed; self.schematic.tool = 'place'
            from PySide6.QtCore import QPointF
            self.schematic.drag = QPointF(x, y)
        self.schematic.setFocus(); self.schematic.update()
