"""Bounded MOS readouts for the actual DUT included by a saved OP fixture.

Schematic aliases are used only for our generated schematic implementation.
Extracted readouts retain the implementation's instance names; LVS matching
does not establish a device-by-device name mapping.
"""
import hashlib
import re

from .model import flatten, digest
from .catalog import binding_for
from .interchange import spice_name
from .operating_data import mos_vectors
from .process_mos import readout_binding


FIELDS = ('id', 'gm', 'gds', 'vgs', 'vds', 'vdsat')
IDENTIFIER = re.compile(r'[A-Za-z][A-Za-z0-9_$-]*\Z')


def capture(project, testbench, text, schematic=False):
    """Request only primitive paths supported by explicit model metadata."""
    from .sky130_flow import subcircuit
    cells = {c['id']: c for c in project['cells']}
    fixture = cells[testbench['bench_cell']]
    instance = next(d for d in fixture['devices'] if d['id'] == testbench['dut_instance'])
    outer = spice_name(instance)
    if not IDENTIFIER.fullmatch(outer):
        raise ValueError('Saved bias readouts require a simple DUT instance name.')
    dut = cells[testbench['dut_cell']]
    _, body, _ = subcircuit(text, dut['name'])
    expected = {}; models = {}; checked = {}; passive_models = set()
    for d in flatten(project, dut['id']):
        binding = binding_for(project['pdk'], d)
        if binding and d.get('model_ref'):
            from .catalog_migration import instance_name
            emitted = instance_name(d, binding)
        else:
            emitted = binding['prefix'] + '_' + d['name'].replace('/', '_') if binding else spice_name(d)
        if d['kind'] not in ('NMOS', 'PMOS'):
            if binding and len(binding.get('pin_order', [])) <= 2:
                passive_models.add(binding.get('model', '').casefold())
            continue
        binding = readout_binding(project['pdk'], d, binding, checked)
        model = binding['model'] if binding else 'model_' + d['id'] + '_' + digest(d['params'])[:10]
        expected[emitted.casefold()] = {'device': instance['name'] + '/' + d['name'], 'model': model.casefold()}
        # An X model needs a declared internal path. Primitive MOS bindings
        # use ngspice's MOS OP fields without inventing subcircuit internals.
        supported = not binding or binding.get('prefix') == 'M' or binding.get('operating_point_device')
        if supported: models[model.casefold()] = binding
    aliases = {}; vectors = []; devices = []; found = set()
    for line in body.splitlines():
        parts = line.strip().split()
        if not parts or parts[0][0].upper() not in ('M', 'X'):
            continue
        local = parts[0]; key = local.casefold()
        positional = []
        for token in parts:
            if '=' in token or token.casefold() == 'params:': break
            positional.append(token)
        model = positional[-1].casefold() if len(positional) >= 2 else ''
        logical = expected.get(key) if schematic else None
        if model in passive_models:
            continue
        name = logical['device'] if logical else outer + '/' + local
        row = {'device': name, 'implementation_instance': outer + '.' + local,
               'model': model, 'requested': [], 'unavailable_reason': ''}
        if not IDENTIFIER.fullmatch(local):
            row['unavailable_reason'] = 'This implementation instance name is outside the bounded readout adapter.'
        elif len(positional) != 6:
            row['unavailable_reason'] = 'This readout adapter requires a four-terminal MOS instance.'
        elif logical and logical['model'] != model:
            row['unavailable_reason'] = 'The implementation model differs from the schematic alias.'
        elif model not in models:
            row['unavailable_reason'] = 'No explicit internal MOS readout path for this model.'
        else:
            binding = models[model]
            if local[0].upper() == 'X' and not (binding or {}).get('operating_point_device'):
                row['unavailable_reason'] = 'A subcircuit readout requires an explicit internal MOS path.'
            elif local[0].upper() == 'M' and (binding or {}).get('operating_point_device'):
                row['unavailable_reason'] = 'Primitive and subcircuit model readout paths differ.'
            else:
                alias = outer + '.' + local
                if local[0].upper() == 'M': alias = 'm.' + alias
                requested = mos_vectors(alias, name, binding, aliases)
                row['requested'] = list(FIELDS); vectors.extend(requested)
        devices.append(row); found.add(key)
    if schematic:
        for key, row in expected.items():
            if key not in found:
                devices.append({**row, 'implementation_instance': outer + '.' + key,
                                'requested': [], 'unavailable_reason': 'MOS instance not found in the included implementation.'})
    if len(devices) > 512:
        raise ValueError('Saved bias diagnostics support at most 512 implementation MOS instances.')
    return {'directive': '.save all ' + ' '.join(vectors), 'aliases': aliases, 'devices': devices,
            'implementation_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'scope': ('Generated schematic device names.' if schematic else
                      'Included implementation instance names; no schematic device-name correspondence is inferred.')}


def annotate(result, evidence):
    """Expose absent/partial vectors explicitly, never manufacture model values."""
    from .analog_diagnostics import bias_report
    diagnostic = bias_report(result)
    rows = {row['device']: row for row in diagnostic['devices']}
    devices = result.get('device_operating_point', {})
    availability = []
    for source in evidence['devices']:
        name = source['device']; values = devices.get(name, {})
        observed = [key for key in FIELDS if key in values]
        status = 'available' if len(observed) == len(FIELDS) else 'partial' if observed else 'unavailable'
        reason = source['unavailable_reason'] or ('Simulator did not return every requested MOS field.' if status != 'available' else '')
        availability.append({**source, 'status': status, 'observed': observed, 'unavailable_reason': reason})
        if name not in rows:
            diagnostic['devices'].append({'device': name, 'region': None, 'headroom_V': None,
                'gm_Id_per_V': None, 'bias_status': 'Readouts unavailable', 'evidence': reason})
    diagnostic['scope'] += ' ' + evidence['scope']
    result['diagnostics'] = diagnostic
    result['bias_capture'] = {key: evidence[key] for key in ('implementation_sha256', 'scope')}
    result['bias_capture']['devices'] = availability
