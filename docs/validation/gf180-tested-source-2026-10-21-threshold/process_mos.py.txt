"""Explicit width and readout contracts for the supported open-process MOS models.

These contracts describe model emission, not physical or manufacturing signoff.
No arbitrary subcircuit is inspected to guess a current or a width convention.
"""
import math
import re
from pathlib import Path

from .catalog import binding_for, parameter_values
from .model import scalar, file_digest


def dimensions(technology, instance, binding=None):
    """Resolve symbol W, emitted total W, nf and parallel multiplicity in SI.

    SKY130's ordinary symbols expose total W; its *_nf symbols expose W per
    finger. The only accepted transform is the catalog's explicit w * nf.
    Multiplicity is taken from emitted m once, never multiplied by mult again.
    """
    binding = binding if binding is not None else binding_for(technology, instance)
    model = (binding or {}).get('model', '')
    kind = instance.get('kind')
    family = technology.get('package_lock', {}).get('id', '')
    if family == 'sky130A' and model == {'NMOS':'sky130_fd_pr__nfet_01v8', 'PMOS':'sky130_fd_pr__pfet_01v8'}.get(kind):
        scale, process = 1e6, 'SKY130'
    elif family in ('gf180mcuC', 'gf180mcuD') and model == {'NMOS':'nfet_03v3', 'PMOS':'pfet_03v3'}.get(kind):
        scale, process = 1., 'GF180'
    else:
        raise ValueError('This process model has no supported width/current adapter. Use explicit model-vector metadata for other devices.')
    if binding.get('prefix') != 'X' or binding.get('pin_order') != ['d','g','s','b']:
        raise ValueError('Use the standard four-terminal process MOS catalog binding.')
    if binding.get('parameter_scale') != {'w':scale, 'l':scale}:
        unit = 'micrometre' if scale == 1e6 else 'metre'
        raise ValueError(f'The {process} adapter requires {unit} W/L model parameters.')
    values = parameter_values(binding, instance)
    # Kind-only legacy netlisting emits W/L, regardless of catalog defaults.
    if not instance.get('model_ref') and any(values.get(k, 1) != 1 for k in ('nf','m','mult')):
        raise ValueError('A legacy binding supports a single finger and multiplicity one. Use a catalog device for nf/m sizing.')
    emit = binding.get('emit_parameters', {'w':'w', 'l':'l'})
    if emit.get('l') != 'l':
        raise ValueError('The process adapter requires direct length emission.')
    if 'nf' in emit and emit['nf'] != 'nf':
        raise ValueError('The process adapter requires direct finger-count emission.')
    nf = values.get(emit.get('nf', 'nf'), 1)
    if not math.isfinite(nf) or nf != int(nf) or not 1 <= nf <= 64:
        raise ValueError('Use an integer finger count from 1 to 64; physical recipe limits are checked separately.')
    if nf != 1 and 'nf' not in emit:
        raise ValueError('Nonunit finger count requires an explicit emitted nf parameter.')
    source = emit.get('w')
    factor = 1
    if source != 'w':
        definition = binding.get('parameters', {}).get(source, {})
        expression = re.sub(r'\s+', '', str(definition.get('default', ''))).lower()
        if process != 'SKY130' or source in instance.get('model_params', {}) or not definition.get('derived') or expression not in ('w*nf', 'nf*w'):
            raise ValueError('Unsupported width transformation. Use total W or the unmodified SKY130 per-finger symbol.')
        factor = nf
    width = scalar(instance['params']['w'])
    length = scalar(instance['params']['l'])
    total = values[source] / scale
    if min(width, length, total) <= 0 or not math.isclose(total, width * factor, rel_tol=1e-12):
        raise ValueError('Emitted process width does not match the symbol width convention.')
    multiplicity = values.get(emit.get('m', 'm'), 1)
    if not math.isfinite(multiplicity) or multiplicity != int(multiplicity) or not 1 <= multiplicity <= 64:
        raise ValueError('Use an integer parallel multiplicity from 1 to 64.')
    if any(values.get(k, 1) != 1 for k in ('m','mult')) and 'm' not in emit:
        raise ValueError('Nonunit multiplicity requires an explicit emitted m parameter.')
    return dict(process=process, model=model, width=width, length=length,
                width_factor=factor, total_width=total, effective_width=total*multiplicity,
                fingers=int(nf), multiplicity=int(multiplicity), values=values,
                convention=('W is per finger' if source != 'w' else 'W is total across fingers') +
                '; nf is finger count; m is parallel copies; density uses total W × m')


def definition(technology, instance, binding=None, checked=None):
    """Check locked model bytes and the supported primitive's actual wiring."""
    binding = binding if binding is not None else binding_for(technology, instance)
    spec = dimensions(technology, instance, binding)
    model = spec['model']
    rel = ('libs.ref/sky130_fd_pr/spice/' + model + '.pm3.spice' if spec['process'] == 'SKY130'
           else 'libs.tech/ngspice/sm141064.ngspice')
    root = Path(technology.get('package_root', '')).resolve()
    path = (root / rel).resolve()
    checksum = technology.get('package_lock', {}).get('files', {}).get(rel)
    cache_key = (str(path), checksum, model)
    if checked is not None and cache_key in checked:
        return {**spec, **checked[cache_key]}
    if not path.is_relative_to(root) or not checksum or not path.is_file() or file_digest(path) != checksum:
        raise ValueError('The locked ' + spec['process'] + ' model definition is missing or changed. Repair the PDK package first.')
    text = path.read_text(encoding='utf-8')
    blocks = re.findall(r'^\s*\.subckt\s+' + re.escape(model) + r'\s+d\s+g\s+s\s+b\b(.*?)^\s*\.ends(?:\s+' + re.escape(model) + r')?\s*$', text, re.M | re.I | re.S)
    if len(blocks) != 1:
        raise ValueError('The pinned model subcircuit differs from this adapter.')
    internal = 'm' + model if spec['process'] == 'SKY130' else 'm0'
    mos = re.findall(r'^\s*(m\S+)\s+d\s+g\s+s\s+b\s+(\S+)\s+([^\n]+)', blocks[0], re.M | re.I)
    expected_model = model + '__model' if spec['process'] == 'SKY130' else model
    primitives = re.findall(r'^\s*([mMxX]\S+)\s+', blocks[0], re.M)
    if len(primitives) != 1 or len(mos) != 1 or mos[0][0].lower() != internal.lower() or mos[0][1].lower() != expected_model.lower():
        raise ValueError('The pinned model internal device differs from this adapter.')
    parameters = {k.lower():v.strip("{}'\"").lower() for k,v in re.findall(r'(\w+)\s*=\s*(\{[^}]+\}|\S+)', mos[0][2])}
    required = {'w':'w', 'l':'l', 'nf':'nf'}
    if spec['process'] == 'GF180': required['m'] = 'm'
    if any(parameters.get(k) != v for k,v in required.items()):
        raise ValueError('The pinned model primitive dimensions differ from this adapter.')
    result = dict(internal=internal, model_definition_sha256=checksum, model_definition_path=rel)
    if checked is not None: checked[cache_key] = result
    return {**spec, **result}


def readout_binding(technology, instance, binding, checked=None):
    """Add readouts only when a recognized locked definition proves the path."""
    if not binding or binding.get('operating_point_device'):
        return binding
    try:
        spec = dimensions(technology, instance, binding)
    except ValueError:
        return binding
    rel = ('libs.ref/sky130_fd_pr/spice/' + spec['model'] + '.pm3.spice' if spec['process'] == 'SKY130'
           else 'libs.tech/ngspice/sm141064.ngspice')
    if rel not in technology.get('package_lock', {}).get('files', {}):
        return binding
    proof = definition(technology, instance, binding, checked)
    return {**binding, 'operating_point_device':proof['internal']}


def corners(technology):
    """Deterministic corner aliases actually shared by the installed includes."""
    choices = [set(row['sections']) for row in technology.get('simulation', {}).get('includes', []) if row.get('sections')]
    deterministic = {'nominal','typical','tt','ff','ss','sf','fs','ll','hh','hl','lh'}
    return sorted(set.intersection(*choices) & deterministic) if choices else ['nominal']
