"""PDK device identities, safe symbol metadata, and numeric model parameters.

Upstream Xschem scripts are never executed. Formula defaults use a small
arithmetic interpreter; unsupported symbols remain visible with a reason.
"""
from __future__ import annotations
import ast, math, operator, re
from .model import clone, device, scalar, PINS

IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_.$-]{0,127}$')


def binding_for(technology, instance):
    simulation = technology.get('simulation', {})
    ref = instance.get('model_ref')
    if ref:
        lock = technology.get('package_lock', {})
        if ref.get('pdk') != lock.get('id') or ref.get('revision') != lock.get('revision'):
            raise ValueError(instance['name'] + ': model belongs to a different PDK revision. Relink or replace this device explicitly.')
        binding = simulation.get('catalog', {}).get(ref.get('device'))
        if not binding:
            raise ValueError(instance['name'] + ': model is absent from the linked PDK catalog.')
        if binding.get('kind') != instance['kind']:
            raise ValueError('Device kind does not match its PDK model.')
        if binding.get('unavailable'):
            raise ValueError(binding['unavailable'])
        return binding
    if instance['kind'] == 'PDK':
        raise ValueError('A PDK device requires a stable model reference.')
    if instance.get('model_mode') == 'generic':
        return None
    return simulation.get('devices', {}).get(instance['kind'])


def numeric_formula(text, context):
    text = str(text).strip().strip('\\\"\'{}').strip()
    try:
        return scalar(text)
    except ValueError:
        pass
    if len(text) > 1000:
        raise ValueError('Model expression is too long.')
    text = re.sub(r'(?<![\w.])(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?:meg|[tgkmunpf])\b',lambda m:repr(scalar(m[0])),text,flags=re.I)
    tree = ast.parse(text, mode='eval')
    if len(list(ast.walk(tree))) > 150:
        raise ValueError('Model expression is too complex.')
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
    functions = {'int': int, 'abs': abs, 'min': min, 'max': max, 'sqrt': math.sqrt}
    def visit(n):
        if isinstance(n, ast.Constant) and type(n.value) in (int, float): return n.value
        if isinstance(n, ast.Name) and n.id.lower() in context: return context[n.id.lower()]
        if isinstance(n, ast.BinOp) and type(n.op) in ops: return ops[type(n.op)](visit(n.left), visit(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)): return visit(n.operand) * (-1 if isinstance(n.op, ast.USub) else 1)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in functions and not n.keywords and 1 <= len(n.args) <= 4: return functions[n.func.id](*[visit(a) for a in n.args])
        raise ValueError('Unsupported or unresolved model expression: ' + text)
    value = float(visit(tree.body))
    if not math.isfinite(value): raise ValueError('Nonfinite model parameter.')
    return value


def parameter_values(binding, instance):
    definitions = binding.get('parameters', {})
    overrides = instance.get('model_params', {})
    if set(overrides) - set(definitions):
        raise ValueError('Unknown PDK parameter: ' + ', '.join(sorted(set(overrides) - set(definitions))))
    pending = {k: overrides.get(k, v['default']) for k, v in definitions.items()}
    resolved = {}
    if instance['kind'] in ('NMOS', 'PMOS'):
        for key in ('w', 'l'):
            resolved[key] = scalar(instance['params'][key]) * binding.get('parameter_scale', {}).get(key, 1)
            pending.pop(key, None)
    for _ in range(len(pending) + 1):
        for key, raw in list(pending.items()):
            rule = definitions[key]
            raw = rule.get('choices',{}).get(str(raw),raw)
            try: val = numeric_formula(raw, resolved)
            except (ValueError, SyntaxError, ZeroDivisionError): continue
            if rule.get('choices') and val not in rule['choices'].values():raise ValueError(key+' must be one of '+', '.join(rule['choices']))
            if rule.get('positive') and val <= 0: raise ValueError(key + ' must be positive.')
            if rule.get('integer') and val != int(val): raise ValueError(key + ' must be a whole number.')
            resolved[key] = val; del pending[key]
        if not pending: return resolved
    raise ValueError('Cannot resolve PDK parameters: ' + ', '.join(pending))


def create_device(technology, key, name, x=0, y=0):
    entry = technology.get('simulation', {}).get('catalog', {}).get(key)
    if entry is None: raise ValueError('Unknown PDK catalog device.')
    if entry.get('unavailable'): raise ValueError(entry['unavailable'])
    lock = technology.get('package_lock', {})
    d = device(entry['kind'], name, x, y, nets={pin: 'open_' + name + '_' + pin for pin in entry['pin_order']},
               model_ref={'pdk': lock['id'], 'revision': lock['revision'], 'device': key}, model_params={})
    if entry.get('symbol'): d['symbol'] = clone(entry['symbol'])
    if d['kind'] in ('NMOS', 'PMOS'):
        for param in ('w', 'l'):
            d['params'][param] = f"{scalar(entry['parameters'][param]['default']) / entry.get('parameter_scale', {}).get(param, 1) * 1e6:.12g}u"
    parameter_values(entry, d)
    return d


def import_emitted_parameters(binding, instance, values):
    """Retain live defaults on unchanged round trips; record real external edits."""
    mapping=binding.get('emit_parameters',{});derived={}
    for key,raw in values.items():
        key=key.lower()
        if key not in mapping:raise ValueError('Unknown PDK parameter '+key)
        source=mapping[key]
        if binding['parameters'][source].get('derived'):derived[source]=raw
        elif source in ('w','l') and instance['kind'] in ('NMOS','PMOS'):
            instance['params'][source]=str(scalar(raw)/binding.get('parameter_scale',{}).get(source,1))
        else:instance.setdefault('model_params',{})[source]=raw
    for source,raw in derived.items():
        current=parameter_values(binding,instance)[source]
        if not math.isclose(scalar(raw),current,rel_tol=1e-10,abs_tol=0):
            instance.setdefault('model_params',{})[source]=raw


def validate_catalog(tech):
    catalog = tech.get('simulation', {}).get('catalog', {})
    if not isinstance(catalog, dict) or len(catalog) > 10000: raise ValueError('Invalid PDK catalog.')
    for key, entry in catalog.items():
        if not isinstance(key, str) or len(key) > 256: raise ValueError('Invalid catalog identity.')
        if entry.get('unavailable'): continue
        if entry.get('kind') not in ('PDK', 'NMOS', 'PMOS', 'R', 'C', 'L'): raise ValueError('Unsupported catalog kind.')
        if not IDENT.fullmatch(entry.get('model', '')): raise ValueError('Invalid PDK model name.')
        if entry.get('prefix') not in ('X', 'M', 'R', 'C', 'L', 'D', 'Q'): raise ValueError('Invalid model prefix.')
        pins = entry.get('pin_order', [])
        if not pins or len(pins) > 128 or len(set(pins)) != len(pins) or any(not IDENT.fullmatch(p) for p in pins): raise ValueError('Invalid model terminals.')
        if entry['kind'] in PINS and set(pins) != set(PINS[entry['kind']]): raise ValueError('Model terminal mismatch.')
        for k in entry.get('parameters', {}):
            if not IDENT.fullmatch(k): raise ValueError('Invalid model parameter.')
        for key, source in entry.get('emit_parameters', {}).items():
            if not IDENT.fullmatch(key) or source not in entry.get('parameters', {}): raise ValueError('Invalid netlist parameter mapping.')


def link_technology(project, technology):
    """Transactional caller supplies a clone; never silently remap existing devices."""
    for cell in project['cells']:
        for d in cell['devices']:
            if d.get('model_ref'): binding_for(technology, d)
            elif binding_for(project['pdk'], d):
                if binding_for(technology, d) != binding_for(project['pdk'], d):
                    raise ValueError('Existing legacy PDK devices use a different binding. Convert or replace them before changing PDK.')
    used = {s['layer'] for c in project['cells'] for s in c['shapes']} | {s['layer'] for c in project['cells'] for s in c.get('layout_pins', [])+c.get('layout_texts', [])}
    old = {l['name']: l for l in project['pdk']['layers']}; new = {l['name']: l for l in technology['layers']}
    mapping={}
    for name in used:
        pair=(old[name]['gds'],old[name]['datatype']);matches=[l['name'] for l in technology['layers'] if (l['gds'],l['datatype'])==pair]
        if not matches or (name in new and (new[name]['gds'],new[name]['datatype'])!=pair):
            raise ValueError('Layout layer ' + name + ' needs an explicit technology mapping before changing PDK.')
        mapping[name]=name if name in matches else matches[0]
    for cell in project['cells']:
        for shape in cell['shapes']+cell.get('layout_pins',[])+cell.get('layout_texts',[]):
            if shape['layer'] in mapping:shape['layer']=mapping[shape['layer']]
    project['pdk'] = clone(technology)
    project['analysis']['corner'] = 'nominal'
