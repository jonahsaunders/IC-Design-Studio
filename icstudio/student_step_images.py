"""Render visual instructions from the current lesson and Studio's native widgets."""

import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QFontDatabase, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QPlainTextEdit,
                               QScrollArea, QVBoxLayout, QWidget)

from .canvas import Canvas
from .model import design_digest
from .student_projects import lesson_workspace


@dataclass(frozen=True)
class StepImage:
    title: str
    caption: str
    pixels: QPixmap


def _mentioned(text, name):
    return bool(name and re.search(r'(?<![\w])' + re.escape(name) + r'(?![\w])', text, re.IGNORECASE))


def _capture(widget, guide, width, height=None, extra_style=''):
    widget.setStyleSheet(guide.styleSheet() + extra_style)
    widget.ensurePolished()
    widget.resize(width, height or widget.sizeHint().height())
    image = widget.grab()
    widget.deleteLater()
    return image


def _control_image(guide):
    from .analog_widgets import FlowActions

    keys = guide.controls
    step = guide.active_step['kind']
    actions = [action for action in (guide.analog_action, guide.layout_action, guide.signal_action)
               if not action.isHidden()]
    if guide.lesson['path'] == 'inverter':
        stage = guide.lesson.get('inverter_stage')
        names = {'layout': ('Build layout',), 'drc': ('Add DRC fault', 'Repair lesson fault'),
                 'lvs': ('Add LVS fault', 'Repair lesson fault')}.get(stage, ())
        actions.extend(b for b in guide.inverter_buttons if b.text() in ('Open inverter', *names))
    if step == 'quiz':
        controls = [guide.answer, *actions, guide.check_button]
        caption = 'Choose a response in Your answer, then use Check this step.'
    elif step == 'reflection':
        controls = [guide.notes, guide.check_button]
        caption = 'Write your observations in Your reflection, then use Record reflection.'
    else:
        controls = [keys['Open workspace'], keys['Open RTL'], *actions, keys['Run lesson'],
                    guide.qualify, keys['Results'], keys['Save work'], guide.check_button]
        caption = 'These are the Lesson Guide controls for this checkpoint. Use the numbered instructions to see when to open the editor, run, or check.'
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(14, 14, 14, 14)
    row = FlowActions()
    for control in controls:
        if control.isHidden():
            continue
        sample = QLabel()
        sample.setPixmap(control.grab())
        row.addWidget(sample)
    layout.addLayout(row)
    height = row.heightForWidth(792) + 28
    return StepImage('Lesson Guide controls', caption, _capture(panel, guide, 820, height))


INTRO_SHAPES = {'layout-width': 'lab_shape_0', 'layout-spacing': 'lab_shape_1', 'layout-via': 'lab_shape_2'}
NAMED_SHAPES = {
    'l-dac': ('bit2_stub',), 'l-match': ('inp_route', 'inn_route'),
    'l-settle': ('outp_stub', 'outn_stub'), 'l-supply': ('supply_route',),
    'l-floorplan': ('channel_blockage',), 'l-access': ('channel_blockage',),
}


def _targets(cell, mode, lesson, step, instructions):
    if mode == 'schematic':
        rule = step.get('rule', {})
        names = [rule.get('device'), *rule.get('devices', [])]
        choices = [d for d in cell['devices'] if d['name'] in names or _mentioned(instructions, d['name'])]
        return choices[:8]
    shape_id = INTRO_SHAPES.get(lesson['starter'])
    if shape_id:
        return [s for s in cell['shapes'] if s['id'] == shape_id]
    names = NAMED_SHAPES.get(lesson['id'], ())
    choices = [s for s in cell['shapes']
               if s['id'] in names or (s['kind'] == 'path' and _mentioned(instructions, s.get('net')))]
    return choices[:6]


def _workspace_images(guide, project, cell, mode, selected):
    if mode == 'layout' and not (cell['shapes'] or cell.get('layout_instances')):
        return []
    if mode == 'schematic' and not cell['devices']:
        return []
    if mode == 'layout' and cell.get('layout_instances'):
        from .layout_scene import LayoutScene
        scene = LayoutScene().update(project, cell['id'])
        cell = {**cell, '_layout_scene': scene}
    elif mode == 'schematic':
        by_id = {c['id']: c for c in project['cells']}
        devices = []
        for part in cell['devices']:
            child = by_id.get(part.get('cell'), {}) if part['kind'] == 'X' else {}
            symbol = child.get('symbol')
            devices.append({**part, 'symbol': symbol, 'symbol_context': {
                'symname': child['name'], **child.get('parameters', {}), **part.get('parameters', {})}}
                if symbol else part)
        cell = {**cell, 'devices': devices}
    canvas = Canvas(mode)
    canvas.dark = guide.studio.dark
    canvas.ensurePolished()
    canvas.resize(900, 520)
    ids = {obj['id'] for obj in selected}
    canvas.set_data(cell, project['pdk'], sorted(ids))
    canvas.fit()
    canvas.auto_fit = False
    names = ', '.join(dict.fromkeys(obj.get('name') or obj.get('net') for obj in selected
                                    if obj.get('name') or obj.get('net')))
    highlight = f' Highlighted targets are {names}.' if names else (' The selected geometry is highlighted.' if selected else '')
    images = [StepImage(mode.title(), f'Current {mode} of {cell["name"]}.' + highlight, canvas.grab())]
    objects = cell['devices' if mode == 'schematic' else 'shapes']
    bounds = [canvas.fit_bounds(obj) for obj in objects if obj['id'] in ids]
    if bounds:
        box = bounds[0]
        for other in bounds[1:]:
            box = box.united(other)
        margin = 55 if mode == 'schematic' else 500
        box = box.adjusted(-margin, -margin, margin, margin)
        detail = min(900 / box.width(), 520 / box.height(), 3 * canvas.scale)
        if detail >= 1.4 * canvas.scale:
            canvas.scale = detail
            canvas.offset = QPointF(450, 260) - box.center() * detail
            images.append(StepImage(mode.title() + ' close-up', 'Zoomed view of the edit area.' + highlight,
                                    canvas.grab()))
    canvas.deleteLater()
    return images


def _rtl_image(guide, project, instructions):
    from .digital_design import config
    from .digital_ui import RTLHighlighter

    cid = project.get('mixed_signal', {}).get('digital_cell', project['top'])
    source = (config(project, cid) or {}).get('files', [])
    if not source:
        return None
    match = next((file for file in source if file['path'].casefold() in instructions.casefold()), source[0])
    editor = QPlainTextEdit()
    editor.setReadOnly(True)
    family = QFontDatabase.systemFont(QFontDatabase.FixedFont).family().replace('"', '')
    editor.setPlainText(match['text'])
    highlighter = RTLHighlighter(editor.document(), guide.studio.dark)
    highlighter.rehighlight()
    return StepImage('RTL source', f'{match["path"]} from the current project. Open RTL to inspect and edit the file.',
                     _capture(editor, guide, 900, 440, f'\nQPlainTextEdit {{font-family:"{family}";}}'))


def _fields_image(guide, project, cell, mode, selected):
    from .feature_ui import build_workflow_form
    from . import student_layout_signoff_ui as layout_forms, student_signal_ui as signal_forms

    step = guide.active_step['id']
    signal = guide.lesson.get('signal_lab'), step
    layout = guide.lesson.get('layout_lab'), step
    if signal in signal_forms.ACTIONS:
        title = signal_forms.ACTIONS[signal]
        fields, note = signal_forms.form_fields(project, *signal, cell['id'])
    elif layout in layout_forms.ACTIONS:
        title = layout_forms.ACTIONS[layout]
        fields, note = layout_forms.form_fields(project, *layout)
    elif mode == 'schematic' and len(selected) == 1:
        part = selected[0]
        title = 'Properties for ' + part['name']
        fields = [('name', 'Designator', part['name'])]
        if part['kind'] in ('NMOS', 'PMOS'):
            fields.extend([('w', 'Width', part['params']['w']), ('l', 'Length', part['params']['l'])])
        elif part['kind'] not in ('X', 'PDK', 'SPICE', 'XS'):
            fields.append(('value', 'Value', part['value']))
        from .terminal_labels import connection_label
        fields.extend((pin, connection_label(project['pdk'], part, pin), net) for pin, net in part['nets'].items())
        note = 'Select the component in Schematic, then find these fields in Properties.'
    elif mode == 'layout' and len(selected) == 1 and selected[0]['kind'] in ('rect', 'path'):
        shape = selected[0]
        title = 'Geometry (µm)'
        if shape['kind'] == 'rect':
            xs, ys = zip(*shape['points'])
            dimensions = [('Left', min(xs)), ('Top', min(ys)), ('Width', max(xs)-min(xs)), ('Height', max(ys)-min(ys))]
        else:
            dimensions = [('Width', shape['width'])]
        fields = [(name.lower(), name, f'{value/1000:g}') for name, value in dimensions]
        note = f'Select the highlighted {shape["layer"]} {shape["kind"]} in Layout, then open Geometry in Properties.'
    else:
        return None
    if signal in signal_forms.ACTIONS or layout in layout_forms.ACTIONS:
        note = 'Choose ' + title + ' in the Lesson Guide. ' + note
    dialog, buttons = build_workflow_form(None, title, fields, note)
    if title.startswith('Properties') or title == 'Geometry (µm)':
        buttons.button(QDialogButtonBox.Ok).setText('Apply changes')
        buttons.button(QDialogButtonBox.Cancel).setText('Reset')
    pixels = _capture(dialog, guide, 650)
    fields_text = ', '.join(name for _, name, _ in fields)
    return StepImage(title, f'{note} Fields shown are {fields_text}.', pixels)


def _result_image(guide, project, instructions):
    from .plot import WavePlot

    step = guide.active_step['id']
    checksum = design_digest(project)
    for row in reversed(guide.lesson_rows()):
        job, result = row['job'], row.get('result')
        if (row['state'] != 'Complete' or not result or result.get('design_hash') != checksum
                or job.get('student_lesson') != guide.lesson['id']):
            continue
        captured_step = (job.get('student_layout_step') or job.get('student_signal_step')
                         or job.get('student_analog', {}).get('stage'))
        if captured_step and captured_step != step:
            continue
        digital = result.get('digital_result', {}).get('artifacts', {}).get('waveform')
        if digital:
            from .digital_flow import validate_result
            from .digital_trace_store import open_waveform
            from .digital_ui import DigitalWaveform
            root = Path(row['path'])
            try:
                validate_result(result, root)
                waveform = open_waveform(root/digital['path'])
            except (ValueError, OSError):
                continue
            plot = DigitalWaveform()
            plot.set_data(waveform, waveform['signals'][:8])
            return StepImage('Saved results', 'Digital waveform from the completed check. Open Results to inspect exact clock ticks.',
                             _capture(plot, guide, 880, 420))
        data = result.get('student_signal', {}).get('measurements', {})
        if guide.lesson.get('signal_lab') == 'adc-ramp' and data.get('Code counts'):
            from .student_signal_ui import adc_wave
            result = adc_wave(data, 'Code counts')
            caption = 'Saved Code counts plot for this ADC step. In Results select Code density and Code counts to inspect the bins.'
        elif guide.lesson.get('signal_lab') == 'temperature' and step == 'validate' and data:
            from .student_signal_ui import temperature_wave
            result = temperature_wave(data, 1.6, 'Error (°C)')
            caption = 'Saved temperature error at 1.6 V. In Results select a calibration plot to compare across supplies.'
        else:
            caption = f'Saved waveform for {row["name"]} at revision {project["revision"]}. Use Results to inspect the measured signals.'
        names = [name for name, values in result.get('traces', {}).items() if len(values) == len(result.get('x', []))]
        names.sort(key=lambda name: not _mentioned(instructions, name))
        if not result.get('x') or not names or not result.get('x_label'):
            continue
        if result.get('settings', {}).get('type') in ('ac', 'noise') and result['x'][0] <= 0:
            continue
        plot = WavePlot()
        plot.dark = guide.studio.dark
        plot.set_result(result, names[:4])
        return StepImage('Saved results', caption + ' Signals shown are ' + ', '.join(names[:4]) + '.',
                         _capture(plot, guide, 880, 420))


def step_images(guide):
    guide.require_project()
    p, lesson, step = guide.studio.project, guide.lesson, guide.active_step
    if step['kind'] != 'check':
        return [_control_image(guide)]
    record = guide.hub.material['practice'][lesson['id']]['tasks'][step['id']]
    instructions = ' '.join(record[1]) + ' ' + step['instructions']
    cid, mode = lesson_workspace(p, lesson, step['id'])
    if lesson['path'] == 'inverter' and lesson.get('inverter_stage') in ('schematic', 'layout', 'drc', 'lvs'):
        cid = p['student_inverter']['cell']
        mode = 'schematic' if lesson['inverter_stage'] == 'schematic' else 'layout'
    cell = next(c for c in p['cells'] if c['id'] == cid)
    if mode == 'layout' and not (cell['shapes'] or cell.get('layout_instances')):
        mode = 'schematic'
    targets = _targets(cell, mode, lesson, step, instructions)
    canvas = _workspace_images(guide, p, cell, mode, targets)
    rtl = _rtl_image(guide, p, instructions) if lesson['path'] == 'digital' or 'Open RTL' in instructions else None
    fields = _fields_image(guide, p, cell, mode, targets)
    results = _result_image(guide, p, instructions)
    return [image for image in (rtl, *canvas, fields, _control_image(guide), results) if image is not None]


class StepImages(QDialog):
    def __init__(self, guide):
        super().__init__(guide.studio)
        self.setWindowTitle('Step images · ' + guide.active_step['title'])
        self.setStyleSheet(guide.styleSheet())
        self.resize(935, 665)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.images = step_images(guide)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.picker = QComboBox()
        self.picker.addItems([image.title for image in self.images])
        self.picker.setAccessibleName('Step image to display')
        form.addRow('Image', self.picker)
        layout.addLayout(form)
        self.caption = QLabel()
        self.caption.setWordWrap(True)
        self.caption.setTextFormat(Qt.PlainText)
        layout.addWidget(self.caption)
        scroller = QScrollArea()
        scroller.setAlignment(Qt.AlignCenter)
        scroller.setFocusPolicy(Qt.StrongFocus)
        self.figure = QLabel()
        self.figure.setAlignment(Qt.AlignCenter)
        scroller.setWidget(self.figure)
        layout.addWidget(scroller, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.picker.currentIndexChanged.connect(self.show_image)
        self.show_image(0)

    def show_image(self, index):
        if index < 0:
            return
        image = self.images[index]
        self.caption.setText(image.caption)
        self.figure.setAccessibleName(image.title)
        self.figure.setAccessibleDescription(image.caption)
        self.figure.setPixmap(image.pixels)
        self.figure.adjustSize()
