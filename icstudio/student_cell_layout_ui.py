"""Native route entry and paired waveform results for Standard Cells."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHeaderView,
                               QLabel, QLineEdit, QMessageBox, QTabWidget, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from . import student_cell_layout as geometry, student_standard_cells as cells
from . import student_cell_specs as specs
from .model import design_digest, scalar
from .plot import WavePlot


def label(text=''):
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    widget.setWordWrap(True)
    return widget


def design_editor(guide, preview=False):
    studio = guide.studio
    lesson = guide.lesson
    key = lesson['standard_cell']
    project_id = studio.project['id']
    cell, _ = cells.context(studio.project,key)
    existing = bool(cell['shapes'])
    dialog = QDialog(studio)
    dialog.setWindowTitle('Revise design' if existing else 'Size and place')
    dialog.setWindowModality(Qt.WindowModal)
    dialog.resize(590, 310)
    layout = QVBoxLayout(dialog)
    layout.addWidget(label(lesson['goal']))
    note = 'Fit the new dimensions on the 0.005 µm grid. Place the cell, route the gaps, and use Results to measure the targets.'
    if existing:
        note += ' Rebuilding gives you a fresh layout with both gaps open. Undo restores your previous routes.'
    layout.addWidget(label(note))
    form = QFormLayout()
    layout.addLayout(form)
    dialog.fields = {}
    defaults = specs.defaults(cell,key)
    for name, title, minimum, maximum, _ in specs.OPTIONS[key]:
        control = dialog.fields[name] = QLineEdit(f'{defaults[name]:g}')
        control.setAccessibleName(title+' in micrometres')
        control.setToolTip(f'{minimum:g} to {maximum:g} µm')
        form.addRow(title+' (µm)',control)
    error = label()
    error.setProperty('role','error')
    layout.addWidget(error)
    dialog.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    dialog.buttons.button(QDialogButtonBox.Save).setText('Rebuild layout' if existing else 'Place cell rows')
    layout.addWidget(dialog.buttons)

    def save():
        try:
            guide.flush()
            guide.require_idle()
            if studio.project['id'] != project_id or guide.lesson['id'] != lesson['id']:
                raise ValueError('Open the matching lesson before saving the design.')
            current, _ = cells.context(studio.project,key)
            already_placed = bool(current['shapes'])
            if already_placed and QMessageBox.question(dialog,'Rebuild the cell layout?',
                    'Rebuilding replaces the layout and opens both routing gaps. Undo can restore the current layout.',
                    QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel) != QMessageBox.Yes:
                return
            values = {name: field.text().strip() for name,field in dialog.fields.items()}
            studio.commit(lambda p: cells.build_layout(p,key,values,replace=already_placed),
                          'Place revised standard cell' if already_placed else 'Size and place standard cell')
            dialog.accept()
            if already_placed:
                guide.steps.setCurrentIndex(next(i for i,s in enumerate(lesson['steps']) if s['id']=='route'))
            guide.workspace()
            guide.update_run_state()
        except ValueError as exc:
            error.setText(str(exc))

    if not preview:
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.buttons.accepted.connect(save)
        dialog.buttons.rejected.connect(dialog.reject)
        dialog.show()
    return dialog


def route_editor(guide, preview=False):
    studio = guide.studio
    key = guide.lesson['standard_cell']
    project_id = studio.project['id']
    cell, _ = cells.context(studio.project, key)
    geometry.check_placement(studio.project, cell)
    breaks = cell['student_cell_layout']['breaks']
    open_nets = geometry.open_nets(studio.project, cell)
    pending = [net for net in ('VPWR', cells.output_pin(key)) if net in open_nets]
    if not pending:
        if preview:
            return None
        raise ValueError('Both assigned tracks are connected. Choose Check this step.')
    dialog = QDialog(studio)
    dialog.setWindowTitle('Add route')
    dialog.setWindowModality(Qt.WindowModal)
    dialog.resize(560, 385)
    layout = QVBoxLayout(dialog)
    layout.addWidget(label('Bridge one open track with a straight path. Coordinates and width are in micrometres.'))
    guide_note = label()
    layout.addWidget(guide_note)
    form = QFormLayout()
    layout.addLayout(form)
    dialog.net = QComboBox()
    dialog.net.addItems(pending)
    form.addRow('&Net', dialog.net)
    dialog.layer = QComboBox()
    names = geometry.layers(studio.project['pdk'])
    for number in (1,2,3):
        dialog.layer.addItem(f'Metal {number}', names[f'm{number}'])
    dialog.layer.setCurrentIndex(-1)
    form.addRow('&Layer', dialog.layer)
    dialog.fields = {}
    for field, title in [('x0','Start X'), ('y0','Start Y'), ('x1','End X'), ('y1','End Y'), ('width','Width')]:
        control = dialog.fields[field] = QLineEdit()
        control.setAccessibleName(title+' in micrometres')
        form.addRow(title+' (µm)', control)
    error = label()
    error.setProperty('role', 'error')
    layout.addWidget(error)
    dialog.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    layout.addWidget(dialog.buttons)

    def target():
        gap = breaks[dialog.net.currentText()]
        x0,y0 = [value/1000 for value in gap['start']]
        x1,y1 = [value/1000 for value in gap['end']]
        width = gap['width']/1000
        if preview or guide.mode_picker.currentData() == 'guided':
            guide_note.setText(f'Metal 3 · Start ({x0:g}, {y0:g}) · End ({x1:g}, {y1:g}) · Width {width:g} µm')
        if preview:
            dialog.layer.setCurrentIndex(2)
            for edit, value in zip(dialog.fields.values(), (x0,y0,x1,y1,width)):
                edit.setText(f'{value:g}')

    def save():
        try:
            guide.flush()
            guide.require_idle()
            if studio.project['id'] != project_id or guide.lesson['standard_cell'] != key:
                raise ValueError('Open the matching lesson before saving a route.')
            if dialog.layer.currentIndex() < 0 or any(not edit.text().strip() for edit in dialog.fields.values()):
                raise ValueError('Choose a layer and enter both endpoints and the width.')
            x0,y0,x1,y1,width = (geometry.um_to_nm(edit.text()) for edit in dialog.fields.values())
            net, layer = dialog.net.currentText(), dialog.layer.currentData()
            def draw(project):
                current, _ = cells.context(project, key)
                geometry.close_gap(project, current, net, layer, [x0,y0], [x1,y1], width)
            studio.commit(draw, 'Add standard-cell route on '+net)
            dialog.accept()
            guide.update_run_state()
        except ValueError as exc:
            error.setText(str(exc))

    dialog.net.currentIndexChanged.connect(target)
    target()
    if not preview:
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.buttons.accepted.connect(save)
        dialog.buttons.rejected.connect(dialog.reject)
        dialog.show()
        dialog.net.setFocus()
    return dialog


class CellResults(QDialog):
    def __init__(self, studio, result):
        super().__init__(studio)
        self.resize(830, 505)
        self.setWindowTitle('Standard-cell test results')
        layout = QVBoxLayout(self)
        key = result['settings']['cell']
        output = cells.output_pin(key)
        record = result['student_cell_layout']
        cap = sum(row['capacitance'] for row in record['capacitors'] if row['net'] == output)
        load_ff = scalar(cells.fixture_load(key))*1e15
        layout.addWidget(label(f'{output} gained an estimated {cap*1e15:.3g} fF of metal-to-ground capacitance. '
                               f'Both cases use the same 1.8 V stimulus and {load_ff:g} fF fixture load.'))
        if result['design_hash'] != design_digest(studio.project):
            layout.addWidget(label('Saved result from an earlier revision. Run the lesson again to test your current layout.'))
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        self.targets = None
        if record.get('targets'):
            targets = self.targets = QTableWidget(len(record['targets']),4)
            targets.setAccessibleName('Measured standard-cell targets')
            targets.setHorizontalHeaderLabels(['Metric','Measured','Target','Status'])
            targets.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            targets.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeToContents)
            targets.setEditTriggers(QTableWidget.NoEditTriggers)
            for index,row in enumerate(record['targets']):
                value = 'No crossing' if row['value'] is None else f'{row["value"]:.3g} {row["unit"]}'
                readings = (row['metric'], value, f'≤ {row["maximum"]:g} {row["unit"]}',
                            'Passed' if row['passed'] else 'Over target')
                for column,text in enumerate(readings):
                    targets.setItem(index,column,QTableWidgetItem(text))
            tabs.addTab(targets,'Targets')
        plot = self.plot = WavePlot()
        plot.dark = studio.dark
        plot.setAccessibleName('Standard-cell output comparison')
        plot.set_result(result, ['out'], record['schematic'])
        waveforms = QVBoxLayout()
        waveform = QWidget()
        waveform.setLayout(waveforms)
        waveforms.addWidget(label('Solid output trace shows the layout-loaded case. The faint trace shows the schematic.'))
        waveforms.addWidget(plot, 1)
        tabs.addTab(waveform, 'Waveforms')
        nominal, physical = (cells.readings(r, key) for r in (record['schematic'], result))
        table = self.samples = QTableWidget(len(physical), 6)
        table.setAccessibleName('Expected logic and measured voltages at each sample')
        table.setHorizontalHeaderLabels(['Time (ns)', 'Inputs', 'Logic', 'Schematic (V)', 'Layout (V)', 'Check'])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        for row, (reference, drawn) in enumerate(zip(nominal, physical)):
            vector = ', '.join(f'{pin}={bit}' for pin,bit in drawn['inputs'].items())
            values = (str(drawn['time_ns']), vector, str(drawn['expected']),
                      f'{reference["output_V"]:.4g}', f'{drawn["output_V"]:.4g}',
                      'Passed' if drawn['passed'] and reference['passed'] else 'Review')
            for column,value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        tabs.addTab(table, 'Samples')
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
