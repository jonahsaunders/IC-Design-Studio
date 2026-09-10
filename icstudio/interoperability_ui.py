"""Technology-neutral entry points and reviewed external-tool handoffs."""
import json
from pathlib import Path
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QLabel, QDialogButtonBox, QPlainTextEdit, QFileDialog, QTableWidgetItem, QHeaderView)
from .model import example, clone
from .project_templates import TEMPLATES, model_choices


class InteroperabilityMixin:
    def make_actions(self):
        super().make_actions()
        menu = self.task_menus['Tools'].addMenu('External tool exchange')
        self._new_submenus.append(menu)
        self.action(menu, 'Export tool technology package…', self.export_tool_technology)
        self.action(menu, 'Netlist with Xschem…', self.external_xschem_dialog)
        self.action(menu, 'Open Magic workspace…', self.magic_workspace_dialog)
        self.action(menu, 'Review Magic workspace edits…', self.magic_review_dialog)
        self.action(menu, 'Run KLayout LVS…', self.klayout_lvs_dialog)
        self.action(menu, 'Open KLayout LVS database…', self.klayout_lvs_import_dialog)
        self.action(menu, 'Restore original layout file…', self.restore_layout_source)
        self.reindex_commands()

    def new_project(self):
        return self.new_pdk_template(None)

    def new_silicon_example(self): return self.new_pdk_template('inverter')
    def new_gf180_inverter(self): return self.new_pdk_template('inverter')
    def new_ring(self): return self.new_pdk_template('ring')
    def new_analog(self, kind): return self.new_pdk_template(kind)

    def sky130_reference_dialog(self):
        # Reference creation and verification now share the selected PDK/model path.
        return self.new_pdk_template('inverter')

    def new_pdk_template(self, initial_kind=None):
        if self.process: raise ValueError('Stop the active job before creating a project.')
        dlg = QDialog(self); dlg.setWindowTitle('New circuit project'); dlg.resize(680, 470)
        outer = QVBoxLayout(dlg); form = QFormLayout(); outer.addLayout(form)
        name = QLineEdit('Untitled circuit'); form.addRow('Project name', name)
        template = QComboBox(); template.setAccessibleName('Circuit template')
        for key, label in {'empty':'Empty circuit','rc':'RC low-pass',**TEMPLATES}.items(): template.addItem(label, key)
        template.setCurrentIndex(max(0, template.findData(initial_kind))); form.addRow('Circuit', template)
        pdk = QComboBox(); pdk.setAccessibleName('Circuit technology'); self.fill_pdk_choices(pdk); form.addRow('Technology / revision', pdk)
        nmos = QComboBox(); pmos = QComboBox(); supply = QLineEdit('1.8')
        nmos.setAccessibleName('NMOS model'); pmos.setAccessibleName('PMOS model'); supply.setAccessibleName('Supply voltage')
        form.addRow('NMOS model', nmos); form.addRow('PMOS model', pmos); form.addRow('Supply (V)', supply)
        note = QLabel('Choose models and a supply appropriate for the selected process. Templates are editable starting circuits; configure measurement limits before qualification.')
        note.setWordWrap(True); outer.addWidget(note)
        error = QLabel(); error.setWordWrap(True); outer.addWidget(error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); outer.addWidget(buttons)
        def technology():
            key = pdk.currentData()
            return self.project['pdk'] if key == 'current' else self.pdk_registry.technology(key) if key else example('empty')['pdk']
        def refresh():
            try:
                tech = technology(); kind = template.currentData()
                for combo, polarity in ((nmos,'NMOS'),(pmos,'PMOS')):
                    previous = combo.currentData(); combo.clear()
                    if not tech.get('package_lock'): combo.addItem('Generic teaching model', None)
                    for key, entry in model_choices(tech, polarity): combo.addItem(entry['model'] + ' · ' + key, key)
                    idx = combo.findData(previous)
                    if idx >= 0: combo.setCurrentIndex(idx)
                form.setRowVisible(nmos, kind in TEMPLATES)
                form.setRowVisible(pmos, kind in ('inverter','ring'))
                form.setRowVisible(supply, kind in TEMPLATES)
                ready = kind not in TEMPLATES or nmos.count() > 0 and (kind not in ('inverter','ring') or pmos.count() > 0)
                buttons.button(QDialogButtonBox.Ok).setEnabled(ready)
                error.setText('' if ready else 'This revision has no required four-terminal MOS models. Register its model catalog or choose another revision.')
            except (ValueError, OSError) as exc: error.setText(str(exc)); buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        def accept():
            try:
                tech = technology(); kind = template.currentData(); cid = key = None
                if kind in TEMPLATES:
                    from .project_templates import create
                    project, cid, key = create(tech, kind, supply.text(), nmos.currentData(), pmos.currentData())
                else:
                    from .catalog import link_technology
                    project = example(kind); link_technology(project, tech)
                project['name'] = name.text().strip()
                from .model import validate
                validate(project)
                if self.maybe_save():
                    self.set_project(project)
                    if cid: self.cid = cid; self._selected_testbench = key; self.refresh(True)
                    dlg.accept()
            except (ValueError, OSError) as exc: error.setText(str(exc))
        pdk.currentIndexChanged.connect(refresh); template.currentIndexChanged.connect(refresh)
        buttons.accepted.connect(accept); buttons.rejected.connect(dlg.reject)
        dlg.technology = pdk; dlg.template = template; dlg.nmos = nmos; dlg.pmos = pmos; dlg.supply = supply
        self._template_dialog = dlg; refresh(); dlg.show(); return dlg

    def export_tool_technology(self):
        directory = QFileDialog.getExistingDirectory(self, 'Export tool technology package')
        if directory:
            from .interchange import export_technology
            export_technology(self.project, directory)
            self.statusBar().showMessage('Exported technology, layer styles and interoperability contract.')

    def import_gds(self):
        from .interchange import import_layout
        from .layout_source import inspect,convert
        path,_=QFileDialog.getOpenFileName(self,'Import physical layout','','Layout (*.gds *.gds2 *.oas)')
        if not path:return
        report=inspect(path)
        try:
            project,notes=import_layout(path)
        except ValueError as exc:
            # An exchange identity/lock failure must never be converted around.
            if Path(str(path)+'.icstudio.json').is_file():raise
            explanation=str(exc)
            def submit(values):
                p,warnings=convert(path,values['top'],flatten=True,round_to_nm=True)
                if self.maybe_save():self.set_project(p);self.mode_combo.setCurrentIndex(1);self.console.appendPlainText('\n'.join(warnings))
            return self.workflow_form('Convert layout for native editing',[
                ('top','Top cell',report['tops'])],submit,
                explanation+'\nApplying this conversion flattens the selected hierarchy and rounds coordinates to 1 nm. Exact source bytes remain attached and can be restored from External tool exchange.')
        if self.maybe_save():self.set_project(project);self.mode_combo.setCurrentIndex(1);self.console.appendPlainText('\n'.join(notes))

    def restore_layout_source(self):
        from .layout_source import restore
        source=self.project.get('layout_source')
        if not source:raise ValueError('This project has no retained original layout.')
        path,_=QFileDialog.getSaveFileName(self,'Restore original layout',source['name'],'Layout files (*)')
        if path:restore(self.project,path);self.statusBar().showMessage('Restored the original layout bytes.')

    def review_import(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Review external layout edits', '', 'Layout (*.gds *.oas)')
        if not path: return
        if not Path(str(path)+'.exchange.json').is_file():
            # Legacy imports retain the existing explicit geometry review.
            return self.show_layout_geometry_review(path)
        return self.show_layout_exchange(path)

    def show_layout_geometry_review(self, path):
        from .import_review import propose_layout_change
        from .model import digest, file_digest
        candidate, notes = propose_layout_change(self.project, path)
        before, source_hash = digest(self.project), file_digest(path)
        def build():
            if digest(self.project) != before or file_digest(path) != source_hash:
                raise ValueError('The project or external layout changed. Review again.')
            return candidate, '\n'.join(notes)
        return self.review_dialog('Review external geometry', build)

    def show_layout_exchange(self, path):
        from .layout_exchange import review, apply
        dlg = QDialog(self); dlg.setWindowTitle('Review external layout edits'); dlg.resize(1100, 650)
        outer = QVBoxLayout(dlg); notes = QPlainTextEdit(); notes.setReadOnly(True); outer.addWidget(notes)
        table = self.simulation_table(['Object / field','Studio value','External value','Resolution']); outer.addWidget(table,1)
        table.setWordWrap(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(3,QHeaderView.Fixed); table.setColumnWidth(3,210)
        table.verticalHeader().setDefaultSectionSize(84)
        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel); outer.addWidget(buttons)
        choices = {}; selectors = []
        def object_label(location, candidate):
            parts=location.strip('/').split('/'); cell=next((c for c in candidate['cells'] if len(parts)>1 and c['id']==parts[1]),None)
            if not cell:return location
            labels=[cell['name']]
            if len(parts)>3:
                obj=next((o for o in cell.get(parts[2],[]) if isinstance(o,dict) and o.get('id')==parts[3]),{})
                labels.append(obj.get('name') or ' '.join(filter(None,(obj.get('layer'),obj.get('kind')))) or parts[2].replace('_',' '))
                labels.extend(p.replace('_',' ') for p in parts[4:])
            else:labels.extend(p.replace('_',' ') for p in parts[2:])
            return ' / '.join(labels)
        def update():
            record = review(self.project, path, choices); dlg.record = record
            notes.setPlainText('\n'.join(record['notes']+record['errors']))
            table.setRowCount(len(record['conflicts'])); selectors.clear()
            for row, conflict in enumerate(record['conflicts']):
                for col, key in enumerate(('path','current','external')):
                    value=object_label(conflict[key],record['candidate']) if key=='path' else json.dumps(conflict[key],ensure_ascii=False)
                    item=QTableWidgetItem(value); item.setToolTip(str(conflict[key])); table.setItem(row,col,item)
                combo = QComboBox(); combo.addItem('Choose resolution',None); combo.addItem('Keep Studio edit','current'); combo.addItem('Use external edit','external')
                combo.setAccessibleName('Resolution for '+object_label(conflict['path'],record['candidate']))
                table.setCellWidget(row,3,combo); selectors.append(combo)
                def choose(index, combo=combo, location=conflict['path']):
                    if combo.currentData(): choices[location] = combo.currentData(); update()
                combo.currentIndexChanged.connect(choose)
            buttons.button(QDialogButtonBox.Apply).setEnabled(not record['conflicts'] and not record['errors'])
        def accept():
            self.commit(lambda project: apply(project, dlg.record), 'Merge external layout edits'); dlg.accept()
        buttons.button(QDialogButtonBox.Apply).clicked.connect(lambda:self.guard(accept)); buttons.rejected.connect(dlg.reject)
        dlg.table = table; dlg.choices = choices; self._import_dialog = dlg; update(); dlg.show(); return dlg

    def external_xschem_dialog(self):
        import shutil
        def submit(values):
            args=['xschem-netlist','--source',values['source'],'--output',values['output'],
                  '--executable',values['executable'],'--mode',values['mode']]
            for root in values['libraries'].splitlines():
                if root.strip():args+=['--library',root.strip()]
            if values['rcfile'].strip():args+=['--rcfile',values['rcfile']]
            self.start_cli_job(args,'External Xschem netlisting')
        return self.workflow_form('Netlist with Xschem',[
            ('source','Schematic (.sch)',''),('output','New workspace folder',''),
            ('executable','Xschem executable',self.settings.value('engine/xschem','') or shutil.which('xschem') or 'xschem'),
            ('mode','Netlist purpose',['simulation','lvs']),('libraries','Library folder (optional)',''),
            ('rcfile','Explicit startup file (optional)','')],submit,
            'Runs Xschem for buses, generated symbols and Tcl templates. The selected startup file executes in Xschem. Project and declared library folders are captured with the resulting netlist and logs.')

    def magic_workspace_dialog(self):
        import shutil
        def submit(values):
            from .model import save_project,uid
            snapshot=self.data_dir/'exchange-inputs'/(uid()+'.icproj');save_project(self.project,snapshot)
            args=['magic-workspace',str(snapshot),'--cell',self.cid,'--output',values['output'],
                  '--executable',values['executable'],'--profile',values['profile']]
            if values['technology'].strip():args+=['--technology',values['technology']]
            self.start_cli_job(args,'Magic workspace')
        return self.workflow_form('Open Magic workspace',[
            ('output','New workspace folder',''),('executable','Magic executable',self.settings.value('engine/magic','') or shutil.which('magic') or 'magic'),
            ('technology','Matching technology file (optional)',''),('profile','Extraction purpose',['lvs','capacitance','rc'])],submit,
            'Uses the active project and its ordered physical ports. Leave the technology field empty to use the locked PDK binding. Retains native cells, technology files, extraction settings and SPICE output.')

    def magic_review_dialog(self):
        import shutil
        def submit(values):
            self.start_cli_job(['magic-workspace-export',values['workspace'],'--output',values['output'],
                '--executable',values['executable']],'Export Magic edits for review')
        return self.workflow_form('Review Magic workspace edits',[
            ('workspace','Managed Magic workspace',''),('output','New review folder',''),
            ('executable','Magic executable',self.settings.value('engine/magic','') or shutil.which('magic') or 'magic')],submit,
            'Save edits in Magic first. This captures native cells and exports edited.gds with its original baseline. Then choose File → Review external layout edits to merge it. Native instance names carry stable identities; copied placements receive new identities.')

    def klayout_lvs_dialog(self):
        import shutil
        from .rule_bundle import capture
        from .model import file_digest
        script,_=QFileDialog.getOpenFileName(self,'Choose KLayout LVS script','','LVS script (*.lvs)')
        if not script:return
        folder=QFileDialog.getExistingDirectory(self,'Choose rule dependency folder',str(Path(script).parent))
        if not folder:return
        executable=self.settings.value('engine/klayout','') or shutil.which('klayout')
        if not executable:
            executable,_=QFileDialog.getOpenFileName(self,'Choose KLayout executable')
            if not executable:return
        if not self.flush_inspector():return
        bundle=capture(script,folder)
        from .model import digest
        bundle_hash=digest(bundle)
        settings={'type':'klayout_lvs','rule_bundle':bundle,'bundle_hash':bundle_hash,
                  'executable':executable,'executable_sha256':file_digest(executable),'timeout':600}
        self.run_manager.enqueue({'project':clone(self.project),'cell':self.cid,'engine':'klayout','settings':settings},self.jobs_dir,'KLayout LVS')
        self.open_engineering_tab(self.simulation_tab)

    def klayout_lvs_import_dialog(self):
        from .klayout_lvs import read_database
        path,_=QFileDialog.getOpenFileName(self,'Open KLayout LVS database','','LVS database (*.lvsdb)')
        if path:return self.show_lvs_database(read_database(path))

    def show_lvs_database(self,data,source_hash=None):
        from .model import design_digest
        from .klayout_lvs import locations
        dlg=QDialog(self);dlg.setWindowTitle('KLayout LVS cross-probe');dlg.resize(1080,650)
        outer=QVBoxLayout(dlg);outer.addWidget(QLabel('Double-click a row to choose a physical occurrence. '+('This result records the verified design revision.' if source_hash else 'External report: no Studio revision association; open its matching project.')))
        table=self.simulation_table(['Cell','Object','Layout','Schematic','Status']);outer.addWidget(table)
        table.setRowCount(len(data['rows']));baseline=source_hash or design_digest(self.project)
        for i,row in enumerate(data['rows']):
            for j,key in enumerate(('cell','kind','layout','schematic','status')):table.setItem(i,j,QTableWidgetItem(row[key]))
        def locate(i,j):
            if design_digest(self.project)!=baseline:raise ValueError('The design changed since this report. Rerun LVS before cross-probing.')
            row=data['rows'][i];options=locations(self.project,row)
            if not options:raise ValueError('This report cell has no matching physical cell in the project.')
            option=options[0]
            if len(options)>1:
                from PySide6.QtWidgets import QInputDialog
                labels=[' / '.join(o['instance_path']) or '(top)' for o in options]
                label,ok=QInputDialog.getItem(dlg,'Physical occurrence','Instance',labels,0,False)
                if not ok:return
                option=options[labels.index(label)]
            self.cid=option['cell_id'];self.mode_combo.setCurrentIndex(1);self.refresh(True)
            if row['boxes_um']:
                from .layout import kdb,polygon
                b=row['boxes_um'][0];box=kdb().Box(*[round(v*1000) for v in b])
                ids=[s['id'] for s in self.cell['shapes'] if polygon(s).bbox().overlaps(box)]
                if ids:self.select(ids,'layout')
                self.layout.fit()
            if row['kind']=='device':
                location=data.get('schematic_objects',{}).get(row['schematic_cell'].casefold()+'/'+row['schematic'].casefold())
                if location:
                    self.cid=location['cell_id'];self.mode_combo.setCurrentIndex(0);self.refresh(True);self.select([location['object']],'schematic')
            self.statusBar().showMessage(' / '.join(option['instance_path']) or row['cell'])
        table.cellDoubleClicked.connect(lambda i,j:self.guard(lambda:locate(i,j)))
        dlg.table=table;self._lvs_dialog=dlg;dlg.show();return dlg

    def add_result(self,result):
        super().add_result(result)
        if result.get('klayout_lvs'):self.show_lvs_database(result['klayout_lvs'],result['design_hash'])
