"""Native entry points for RF network runs and locally installed simulator decks."""

import cmath
import math
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel, QVBoxLayout

from . import external_simulation, rf_network
from .model import atomic_write, scalar


def queue(studio, job, title):
    if studio.process and studio.process not in studio.run_manager.processes:
        raise ValueError('Wait for the active external command before starting another run.')
    row = studio.run_manager.enqueue(job, studio.jobs_dir, title)
    studio.open_simulation_explorer()
    studio.simulation_runs.selectRow(studio.run_manager.rows.index(row))
    return row


def rf_dialog(studio):
    project_id, cell_id = studio.project['id'], studio.cid
    analysis = studio.project['analysis']
    fields = [('ports', 'Ports in order', ('',)), ('impedance', 'Reference impedance (Ω)', '50'),
              ('start', 'Start frequency (Hz)', '1Meg'), ('stop', 'Stop frequency (Hz)', '1G'),
              ('points', 'Linear frequency points', 201),
              ('corner', 'Model corner', analysis.get('corner', 'nominal')),
              ('temperature', 'Temperature (°C)', analysis.get('temperature', 27))]

    def submit(values):
        if studio.project['id'] != project_id or studio.cid != cell_id:
            raise ValueError('Reopen RF network analysis for the current fixture schematic.')
        settings = {name: scalar(values[name]) for name in ('impedance', 'start', 'stop', 'temperature')}
        settings.update(ports=rf_network.port_lines(values['ports']), points=int(values['points']),
                        corner=values['corner'].strip() or 'nominal')
        job = rf_network.prepare(studio.project, cell_id, settings, studio.settings.value('engine/ngspice', ''))
        queue(studio, job, 'RF network analysis')

    dialog = studio.workflow_form('RF network analysis', fields, submit,
        'Enter one port per line as signal net, return net, and optional DC volts. '
        'Example: in 0 and out 0 on separate lines. The ports place the reference impedance in series '
        'with their voltage sources, which can change the DC bias. Use the fixture to provide bias and coupling.')
    dialog.fields['ports'].setPlaceholderText('in 0\nout 0')
    return dialog


def export_touchstone(studio):
    result = studio.result
    if not result or 'rf_network' not in result:
        raise ValueError('Select an RF network result before exporting Touchstone.')
    suffix = f'.s{len(result["settings"]["ports"])}p'
    path, _ = QFileDialog.getSaveFileName(studio, 'Export RF Touchstone', 'network'+suffix,
                                          'Touchstone (*'+suffix+')')
    if path:
        target = Path(path)
        if target.suffix.lower() != suffix:
            target = target.with_suffix(suffix)
        atomic_write(target, rf_network.touchstone(result))
        studio.statusBar().showMessage('Exported scattering parameters to '+str(target), 10000)


def inspect_rf(studio):
    from .plot import WavePlot
    result = studio.result
    if not result or 'rf_network' not in result:
        raise ValueError('Select an RF network result before inspecting its parameters.')
    matrices = result['rf_network']['matrices']
    dialog = QDialog(studio)
    dialog.setWindowTitle('RF network parameters')
    dialog.resize(760, 490)
    layout = QVBoxLayout(dialog)
    ports = ' · '.join(f'{i}: {row[0]} / {row[1]}' for i, row in enumerate(result['settings']['ports'], 1))
    note = QLabel(f'Revision {result["revision"]} · {result["settings"]["impedance"]:g} Ω reference\n'+ports)
    note.setWordWrap(True)
    layout.addWidget(note)
    missing = ', '.join(name for name in ('Y', 'Z') if name not in matrices)
    if missing:
        warning = QLabel(missing+' matrix unavailable because its conversion is singular or ill-conditioned in the sweep.')
        warning.setWordWrap(True)
        layout.addWidget(warning)
    controls = QFormLayout()
    parameter, view = QComboBox(), QComboBox()
    parameter.setAccessibleName('Network parameter')
    view.setAccessibleName('Parameter display')
    for values in matrices.values():
        parameter.addItems(list(values))
    view.addItems(['Magnitude', 'Phase', 'Real', 'Imaginary'])
    controls.addRow('Parameter', parameter)
    controls.addRow('Display', view)
    layout.addLayout(controls)
    plot = WavePlot()
    plot.dark = studio.dark
    layout.addWidget(plot, 1)
    cursor = QLabel('')
    cursor.setWordWrap(True)
    plot.cursor_changed.connect(cursor.setText)
    layout.addWidget(cursor)

    def refresh():
        name = parameter.currentText()
        values = [complex(*value) for value in matrices[name[0]][name]]
        operation = view.currentText()
        transform = {'Magnitude': abs, 'Phase': lambda value: math.degrees(cmath.phase(value)),
                     'Real': lambda value: value.real, 'Imaginary': lambda value: value.imag}[operation]
        unit = '°' if operation == 'Phase' else {'S': '', 'Y': 'S', 'Z': 'Ω'}[name[0]]
        plot.set_result({**result, 'traces': {name: [transform(value) for value in values]}, 'plot_unit': unit})

    parameter.currentIndexChanged.connect(refresh)
    view.currentIndexChanged.connect(refresh)
    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.rejected.connect(dialog.close)
    layout.addWidget(buttons)
    dialog.setAttribute(Qt.WA_DeleteOnClose)
    refresh()
    dialog.show()
    return dialog


def external_dialog(studio):
    project_id, cell_id = studio.project['id'], studio.cid
    entry, _ = QFileDialog.getOpenFileName(studio, 'Choose simulator deck or argument file', '',
                                          'Simulation inputs (*.cir *.sp *.scs *.f);;All files (*)')
    if not entry:
        return None

    def items(value):
        return [line.strip() for line in value.splitlines() if line.strip()]

    def submit(values):
        if studio.project['id'] != project_id or studio.cid != cell_id:
            raise ValueError('Reopen the simulator setup for the current project.')
        job = external_simulation.prepare(studio.project, cell_id, values['executable'],
              items(values['arguments']), entry, items(values['dependencies']), items(values['outputs']),
              values['csv'].strip(), int(values['timeout']))
        queue(studio, job, 'External simulation · '+Path(job['executable']).name)
        studio.settings.setValue('engine/externalSimulator', job['executable'])

    return studio.workflow_form('Run external simulator', [
        ('executable', 'Simulator executable', studio.settings.value('engine/externalSimulator', '')),
        ('arguments', 'Arguments, one per line', ('{input}',)),
        ('dependencies', 'Additional input files', ('',)),
        ('outputs', 'Required output files or folders', ('',)),
        ('csv', 'CSV result to plot (optional)', ''),
        ('timeout', 'Timeout (seconds)', 180),
    ], submit, 'Selected input: '+Path(entry).name+'. Use {input} as one argument. '
        'Enter each dependency and output on its own line, using paths relative to the selected input. '
        'Use the installed engine’s own deck syntax and ensure the engine writes its files into the run folder.')


def open_external_outputs(studio):
    rows = studio.selected_simulation_runs()
    if len(rows) != 1 or rows[0]['job']['settings'].get('type') != 'external_simulator':
        raise ValueError('Select one external simulation in Simulation Explorer first.')
    path = Path(rows[0]['path'])/'external'
    if not path.is_dir() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
        raise ValueError('The simulator output folder is not available yet.')


def install(studio):
    menu = studio.task_menus['Simulate'].addMenu('Advanced simulation')
    for title, handler in [('RF network analysis…', rf_dialog), ('Inspect RF parameters…', inspect_rf),
                           ('Export RF Touchstone…', export_touchstone),
                           ('Run external simulator…', external_dialog), ('Open external run folder', open_external_outputs)]:
        studio.action(menu, title, lambda handler=handler: handler(studio))
