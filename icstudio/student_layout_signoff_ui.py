"""Layout guide forms and independent stream inspection results."""

import math
from pathlib import Path

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout

from . import student_layout_signoff as lab, student_layout_passives as passives


ACTIONS = {
    ('floorplan', 'compact'): 'Adjust macro placement',
    ('access', 'route'): 'Plan pin route',
    ('pad-ring', 'repair'): 'Assign perimeter pad',
    ('density', 'close-fill'): 'Configure window fill',
    ('density', 'repair'): 'Configure window fill',
    ('antenna', 'jumper'): 'Add antenna repair',
    ('antenna', 'diode'): 'Add antenna repair',
    ('via-current', 'repair'): 'Configure via array',
    ('isolation', 'ring'): 'Add guard segment',
    ('isolation', 'taps'): 'Place guard contacts',
    ('spiral', 'candidate'): 'Tune candidate coil',
    ('mim-plate','repair'): 'Route MIM sense plate',
    ('decoupling','repair'): 'Place decoupling capacitor',
    ('handoff', 'verify'): 'Assign stream pin label',
}

SITES = {
    'North supply pad': 'PWR', 'South supply pad': 'GND',
    'West upper pad': 'INA', 'West lower pad': 'INB', 'East output pad': 'Y',
}
REPAIRS = {'Jump to metal2': 'jumper', 'Connect protection diode': 'diode'}
DIMENSIONS = {'Turns': 'turns', 'Width (µm)': 'width', 'Spacing (µm)': 'spacing'}


def _nm(text, minimum, maximum, grid):
    size = float(text)
    if not math.isfinite(size) or not minimum <= size <= maximum:
        raise ValueError(f'Enter a dimension from {minimum:g} to {maximum:g} µm.')
    value = round(size * 1000 / grid) * grid
    if not math.isclose(size * 1000, value, abs_tol=1e-7):
        raise ValueError(f'Use a multiple of {grid / 1000:g} µm.')
    return value


def open_form(guide, key, step, cid):
    s = guide.studio
    title = ACTIONS[key, step]
    initial_project, lesson_id, active = s.project['id'], guide.lesson['id'], guide.active_step['id']
    initial_revision = s.project['revision']
    grid = s.project['pdk']['grid']

    def apply(p, values):
        locked = s.layout.locked_layers
        if key in ('floorplan', 'access'):
            pitch = _nm(values['pitch'], 12, 42, grid)
            offset = _nm(values['offset'], -12, 12, grid)
            if (pitch, offset) != lab.current_placement(p):
                lab.place_macro(p, pitch, offset, locked)
            if key == 'access':
                lab.plan_macro(p, values['layers'] == 'Metal1 and metal2', locked)
        elif key == 'pad-ring':
            lab.assign_ring_port(p, values['port'], SITES[values['site']])
        elif key == 'density':
            lab.add_fill(p, _nm(values['keepout'], .25, 4, grid), locked)
        elif key == 'antenna':
            lab.repair_antenna(p, cid, REPAIRS[values['method']], locked)
        elif key == 'via-current':
            lab.set_via_array(p, int(values['rows']), int(values['columns']), locked)
        elif key == 'isolation':
            if step == 'ring':
                lab.add_guard_side(p, values['side'].lower(), locked)
            else:
                lab.set_taps(p, int(values['count']), locked)
        elif key == 'spiral':
            field = DIMENSIONS[values['field']]
            value = (int(values['number']) if field == 'turns' else
                     _nm(values['number'], 2, 30, 2 * grid))
            lab.tune_spiral(p, cid, field, value, locked)
        elif key=='mim-plate':
            passives.route_mim(p,_nm(values['dimension'],0,40,grid),locked)
        elif key=='decoupling':
            passives.place_decap(p,_nm(values['dimension'],2,60,grid),locked)
        else:
            lab.add_stream_label(p, values['port'])

    def same_context():
        if (initial_project != s.project['id'] or not guide.lesson or guide.lesson['id'] != lesson_id
                or not guide.active_step or guide.active_step['id'] != active
                or s.project['revision'] != initial_revision):
            raise ValueError('The active project or lesson step changed. Reopen this control.')
        guide.require_idle()

    def submit(values):
        s.commit(lambda p: apply(p, values), title)
        guide.workspace()

    fields, note = form_fields(s.project, key, step)
    return s.workflow_form(title, fields, submit, note, context_guard=same_context)


def form_fields(p, key, step):
    if key in ('floorplan', 'access'):
        pitch, offset = lab.current_placement(p)
        fields = [('pitch', 'Second device pitch (µm)', f'{pitch/1000:g}'),
                  ('offset', 'Second device row offset (µm)', f'{offset/1000:g}')]
        if key == 'access':
            fields.append(('layers', 'Allowed layers', ['Metal1 only', 'Metal1 and metal2']))
        return fields, 'The physical instance and attached external ports move together. The fixed route obstruction stays in place.'
    if key in passives.LABS:
        label, note = (
            ('Sense route detour height (µm)', 'Changing height keeps the two terminals and external pins fixed.')
            if key=='mim-plate' else
            ('Distance from load (µm)', 'Move the same 200 pF capacitor and shorten its supply and return routes.'))
        return ([('dimension',label,f'{passives.dimension(p,key):g}')],note)
    if key == 'isolation':
        return ([('side', 'Missing side', ['Bottom', 'Left', 'Right', 'Top'])], 'Add the matching active and metal segment.') if step == 'ring' else (
            [('count', 'Number of contacts', ['2', '4', '8'])], 'Compare the maximum distance along the perimeter between adjacent contacts.')
    return {
        'pad-ring': ([('port', 'Schematic port', list(lab.PAD_SITES)), ('site', 'Physical landing', list(SITES))],
                     'Assign one port at a time. Check this step to see unassigned or incorrect landings.'),
        'density': ([('keepout', 'Fill keepout (µm)', '0.50')],
                    'Regenerate the right window using 2.4 µm squares on a fixed 3.2 µm pitch. The prior lesson fill is replaced.'),
        'antenna': ([('method', 'Repair method', list(REPAIRS))],
                    'Apply to this comparison cell. Undo this edit to try the other option here.'),
        'via-current': ([('rows', 'Rows', ['1', '2', '3', '4']), ('columns', 'Columns', ['1', '2', '3', '4'])],
                        'Keep the same load, landing pads and route geometry.'),
        'spiral': ([('field', 'Dimension', list(DIMENSIONS)), ('number', 'New value', '3')],
                   'Change one dimension at a time. The reference coil and material assumptions stay fixed.'),
        'handoff': ([('port', 'Port to write as a GDS label', list(lab.MACRO_PORTS))],
                    'The stream label uses the existing physical port location and process pin-purpose layer.'),
    }[key]


def show_report(parent, row):
    data = row['result']['student_stream']
    path = Path(row['path']) / data['file']
    panel = QDialog(parent)
    panel.setWindowTitle('Independent GDS readback')
    panel.resize(660, 370)
    layout = QVBoxLayout(panel)
    layout.addWidget(QLabel('KLayout stream inspection'))
    report = QPlainTextEdit()
    report.setAccessibleName('GDS readback report')
    report.setReadOnly(True)
    lines = [f'{key}  {", ".join(value) or "None" if isinstance(value, list) else value}'
             for key, value in data['inspection'].items()]
    report.setPlainText('\n'.join(lines) + f'\n\nGDS file\n{path}\n\nSHA-256\n{data["sha256"]}')
    layout.addWidget(report)
    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.rejected.connect(panel.reject)
    layout.addWidget(buttons)
    panel.show()
    return panel
