"""Native electrical definitions and portable SPICE generation.

No Xschem parser, source records, installation or template evaluator is used.
Device programs contain explicit literal, parameter, terminal and instance
tokens. SPICE expressions remain expressions for the selected simulator.
"""
import hashlib
import json
import re
from pathlib import Path
from .model import clone, validate, atomic_write, scalar


def native(project):
    return project.get('spice', {}).get('version') == 1


def render(device, child=None, mode='simulation'):
    definition = device['native_spice']
    if definition['type'] == 'program':
        return definition['text']
    output = []
    if mode not in ('simulation','lvs'):raise ValueError('Choose simulation or LVS emission.')
    for token in definition.get('lvs_tokens',definition['tokens']) if mode=='lvs' else definition['tokens']:
        kind, value = token['kind'], token.get('value', '')
        if kind == 'literal': output.append(value)
        elif kind == 'instance': output.append(device['name'])
        elif kind == 'terminal': output.append(device['nets'][value])
        elif kind == 'terminals': output.append(' '.join(device['nets'][p] for p in device['symbol']['pin_order']))
        elif kind == 'cell': output.append(child['name'] if child else definition['model_name'])
        elif kind == 'parameter':
            if value not in definition['parameters']:
                raise ValueError(device['name'] + ': missing native parameter ' + value)
            output.append(str(definition['parameters'][value]))
        else: raise ValueError('Unknown native device token: ' + kind)
    return ''.join(output)


def validate_device(device):
    definition = device.get('native_spice', {})
    if definition.get('version') != 1 or definition.get('type') not in ('device', 'program'):
        raise ValueError('Invalid native electrical definition for ' + device['name'])
    if not device.get('symbol'):
        raise ValueError('Native electrical definitions require an explicit symbol and terminal order.')
    if definition['type'] == 'program':
        if device['nets'] or not isinstance(definition.get('text'), str):
            raise ValueError('A simulation program has text and no electrical terminals.')
    else:
        if not isinstance(definition.get('parameters'), dict) or not definition.get('tokens'):
            raise ValueError('A native device needs parameters and an emission program.')
        for key, value in definition['parameters'].items():
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) or not isinstance(value, str) or '\n' in value or '\r' in value:
                raise ValueError('Invalid native device parameter: ' + str(key))
            if 'tcleval' in value:
                raise ValueError('Executable Xschem expressions must be migrated before editing this parameter.')
        render(device, {'name': 'child'})
        if 'lvs_tokens' in definition:render(device, {'name':'child'}, 'lvs')


def asset_path(ident):
    if not re.fullmatch(r'[a-f0-9]{24}', ident):
        raise ValueError('Invalid native model asset identity.')
    return 'models/' + ident + '.spice'


def netlist(project, directory, mode='simulation'):
    from .wiring import rebuild
    from .interchange import source_spec, spice_name
    from .design_ops import parameters, resolved_device
    p = clone(project); validate(p)
    root = Path(directory).resolve(); root.mkdir(parents=True, exist_ok=True)
    assets = p['spice']['assets']
    from .catalog_migration import check_embedded_catalog, emit
    check_embedded_catalog(p)
    for ident, asset in assets.items():
        if hashlib.sha256(asset['text'].encode()).hexdigest() != asset['sha256']:
            raise ValueError('Model checksum mismatch: ' + asset.get('name', ident))
        atomic_write(root / asset_path(ident), asset['text'])
    atomic_write(root / 'model-files.json', json.dumps({asset_path(k): v['name'] for k, v in assets.items()}, indent=2))
    atomic_write(root / 'library-lock.json', json.dumps(p['spice'].get('library_lock', {}), indent=2))
    by = {c['id']: c for c in p['cells']}; top = by[p['top']]
    lines = ['* IC Design Studio native circuit: ' + p['name']]; definitions = set()
    if p.get('global_nets'):lines.append('.global '+' '.join(p['global_nets']))
    if p.get('parameters'):
        lines.append('.param ' + ' '.join(k + '=' + str(v) for k, v in p['parameters'].items()))
    for c in [top] + [c for c in p['cells'] if c is not top]:
        rebuild(c, p)
        defaults = {**c.get('spice_parameters', {}), **c.get('parameters', {})}
        if c is not top or mode=='lvs':
            lines.append('.subckt ' + c['name'] + ' ' + ' '.join(c['ports']) + ''.join(' ' + k + '=' + str(v) for k, v in defaults.items()))
        elif defaults:
            lines.append('.param ' + ' '.join(k + '=' + str(v) for k, v in defaults.items()))
        context = parameters(c.get('parameters', {}), parameters(p.get('parameters', {})))
        lines.extend(c.get('spice_statements', [])); commands = []
        for original in c['devices']:
            d = original; definition = d.get('native_spice')
            if d.get('model_ref'):
                lines.append(emit(d,p['pdk'],mode));continue
            if definition:
                if definition['type'] == 'program':
                    if c is top or not definition.get('only_toplevel'):
                        commands.append(definition['text'])
                else:
                    lines.append(render(d, by.get(d.get('cell')), mode))
                    if definition.get('definition'): definitions.add(definition['definition'])
                continue
            d = resolved_device(d, context); kind = d['kind']
            if kind == 'X':
                lines.append(d['name'] + ' ' + ' '.join(d['nets'][pin] for pin in by[d['cell']]['ports']) + ' ' + by[d['cell']]['name'] + ''.join(' ' + k + '=' + str(v) for k, v in d.get('parameters', {}).items()))
                continue
            name = spice_name(d); nets = ' '.join(d['nets'].values())
            if kind in ('R', 'C', 'L'): suffix = str(scalar(d['value']))
            elif kind in ('V', 'I'): suffix = source_spec(d)
            elif kind in ('NMOS', 'PMOS'):
                pa = d['params']; model = 'studio_' + d['id']; polarity = -1 if kind == 'PMOS' else 1
                definitions.add(f'.model {model} {kind} (LEVEL=1 VTO={polarity*scalar(pa["vto"])} KP={scalar(pa["kp"])} LAMBDA={scalar(pa["lambda"])})')
                suffix = f'{model} W={scalar(pa["w"])} L={scalar(pa["l"])}'
            else: raise ValueError(d['name'] + ': migrate or bind this device before native SPICE generation.')
            lines.append(name + ' ' + nets + ' ' + suffix)
        lines.extend(commands)
        if c is not top or mode=='lvs': lines.append('.ends ' + c['name'])
    lines.extend(sorted(definitions)); lines.append('.end')
    text = '\n'.join(lines) + '\n'
    if mode=='lvs':
        from .native_analysis import circuit_text
        text=circuit_text(text)+'.end\n'
    atomic_write(root / 'source.cir', text)
    return text


def run(project, cid, settings, executable, directory, progress=lambda *_: None):
    from .spice_program import run_program
    return run_program(project, cid, settings, executable, directory, progress, netlist,
                       'ngspice · native program', project['spice'].get('library_lock', {}), 'analysis_cases')
