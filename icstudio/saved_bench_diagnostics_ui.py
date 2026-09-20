"""Native controls for diagnostics that travel with a saved testbench."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QComboBox, QLineEdit, QLabel
from .model import clone


def editor(seed, analysis_type, analysis_fields):
    page = QWidget(); layout = QVBoxLayout(page); form = QFormLayout(); layout.addLayout(form)
    config = clone(seed.get('analysis', {}).get('diagnostic', {}))
    kind = QComboBox(); kind.setAccessibleName('Saved diagnostic')
    for title, key in [('None', ''), ('Integrated input/output noise', 'noise'),
                       ('Loop return ratio', 'loop'), ('Supply startup and settling', 'startup'),
                       ('Device operating-point data', 'bias')]: kind.addItem(title, key)
    kind.setCurrentIndex(max(0, kind.findData(config.get('kind', '')))); form.addRow('Diagnostic', kind)
    fields = {}
    output = seed.get('probes', ['out'])[0]
    definitions = [('numerator', 'Return voltage net', output), ('denominator', 'Injection voltage net', 'input'),
                   ('source', 'Supply voltage source', 'VDD'), ('output', 'Startup output net', output),
                   ('ramp', 'Supply ramp time', '1u'), ('minimum', 'Settled minimum (V)', '.8'),
                   ('maximum', 'Settled maximum (V)', '1'), ('initial_node', 'Initial-condition net', output),
                   ('initial_voltage', 'Initial voltage (V)', '0'), ('tail_fraction', 'Final observation fraction', '.2')]
    for key, title, default in definitions:
        field = QLineEdit(str(config.get(key, default))); field.setAccessibleName(title)
        fields[key] = field; form.addRow(title, field)
    sign = QComboBox(); sign.setAccessibleName('Loop return-ratio polarity')
    sign.addItem('T = return / injection', 1); sign.addItem('T = −return / injection', -1)
    sign.setCurrentIndex(max(0, sign.findData(config.get('sign', 1)))); form.addRow('Return-ratio convention', sign)
    note = QLabel(); note.setWordWrap(True); layout.addWidget(note); layout.addStretch()
    groups = {'': (), 'bias': (), 'noise': (), 'loop': ('numerator', 'denominator'),
              'startup': ('source', 'output', 'ramp', 'minimum', 'maximum', 'initial_node', 'initial_voltage', 'tail_fraction')}
    analyses = {'noise': 'noise', 'loop': 'ac', 'startup': 'tran', 'bias': 'op'}
    notes = {'': 'Choose a diagnostic to save its settings and measured requirements with this fixture.',
             'noise': 'Uses the noise source, output and frequency band on the Analysis tab. Input/output noise measurements are integrated RMS volts over that band.',
             'loop': 'Use an explicit injection fixture whose return ratio has characteristic 1 + T. Every sampled unity crossing is checked; a missing crossing is a failed margin measurement.',
             'startup': 'Ramps the selected DC supply from zero to its saved value, including each PVT supply override. Settling must remain within these limits through the final observation window.',
             'bias': 'Captures available device operating-point data. Missing model data remains unavailable.'}
    def changed():
        selected = kind.currentData()
        for key, field in fields.items(): form.setRowVisible(field, key in groups[selected])
        form.setRowVisible(sign, selected == 'loop'); note.setText(notes[selected])
        if selected: analysis_type.setCurrentText(analyses[selected])
    def value():
        selected = kind.currentData()
        if not selected: return None
        result = {'kind': selected, **{key: fields[key].text().strip() for key in groups[selected]}}
        if selected == 'loop': result['sign'] = sign.currentData()
        elif selected == 'noise':
            result.update(source=analysis_fields['noise_source'].text().strip(), output=analysis_fields['output'].text().strip())
        elif selected == 'startup':
            result.update(stop=analysis_fields['stop'].text().strip(), supply_from_source=True)
        return result
    kind.currentIndexChanged.connect(changed); changed()
    page.kind = kind; page.fields = fields; page.sign = sign; page.value = value
    return page
