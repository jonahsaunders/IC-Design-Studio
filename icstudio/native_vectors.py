"""Declarative native buses, slices and instance arrays.

Capture retains compact, editable expressions. Only electrical consumers expand
them; no Tcl or implicit name-based array inference is performed. Range order is
significant. For an N-member array and W-bit terminal, N*W signals are consumed
in contiguous W-bit chunks; W signals broadcast to every member. A scalar only
broadcasts to scalar terminals, never shorts a multi-bit interface.
"""
import re
from .model import NAME, NET, clone, digest

MAX_SIGNALS = 128
_INDEX = re.compile(r'([A-Za-z_][A-Za-z0-9_.$/!-]*)\[(\d+)(?::(\d+))?\]')


def display_name(device):
    spec=device.get('array')
    return device['name'] if spec is None else f'{device["name"]}[{spec["start"]}:{spec["end"]}]'


def signals(expression):
    """Return ordered scalar names from e.g. ``data[7:4],data[1:0]``."""
    if not isinstance(expression, str) or not expression or len(expression) > 2048:
        raise ValueError('A net expression requires a scalar name, index or bounded bus slice.')
    result = []
    for term in expression.split(','):
        term = term.strip()
        match = _INDEX.fullmatch(term)
        if match:
            start = int(match[2]); end = int(match[3] or match[2])
            if max(start, end) > 2147483647 or abs(end-start)+1 > MAX_SIGNALS:
                raise ValueError('A native bus supports at most 128 signals and signed 32-bit nonnegative indices.')
            step = 1 if end >= start else -1
            values = [f'{match[1]}[{i}]' for i in range(start, end+step, step)]
        elif NET.fullmatch(term) and '[' not in term and ']' not in term:
            values = [term]
        else:
            raise ValueError('Unsupported native net expression: '+term+'. Use data[7:0], data[2], or comma-separated slices; executable expressions require the external engine.')
        if any(not NET.fullmatch(name) for name in values):
            raise ValueError('Expanded net name exceeds the native 128-character limit.')
        result.extend(values)
        if len(result) > MAX_SIGNALS:
            raise ValueError('A native bus expression supports at most 128 signals.')
    return result


def valid_expression(expression):
    try:
        signals(expression)
        return True
    except (ValueError, TypeError):
        return False


def ports(expressions):
    """Expand an ordered interface; overlapping/aliased terminals are errors."""
    if not isinstance(expressions, list):
        raise ValueError('Cell ports must be an ordered list.')
    result = [name for expression in expressions for name in signals(expression)]
    if len(result) > MAX_SIGNALS or '0' in result or len({n.casefold() for n in result}) != len(result):
        raise ValueError('Cell ports require at most 128 unique non-ground scalar terminals after bus expansion.')
    return result


def indices(device):
    spec = device.get('array')
    if spec is None:
        return [None]
    if (not isinstance(spec, dict) or set(spec) != {'start', 'end'}
            or any(type(spec.get(k)) is not int or not 0 <= spec[k] <= 2147483647 for k in ('start', 'end'))):
        raise ValueError(device['name']+': an instance array requires explicit nonnegative integer start/end indices.')
    start, end = spec['start'], spec['end']
    if abs(end-start)+1 > MAX_SIGNALS:
        raise ValueError(device['name']+': an instance array supports at most 128 members.')
    step = 1 if end >= start else -1
    return list(range(start, end+step, step))


def expand_device(device, project=None):
    """Produce scalar electrical instances, without mutating the capture master.

    ``array_source_id`` and ``array_index`` track deterministic member identity
    through flattening and explicit physical materialization.
    """
    members = indices(device)
    if device.get('native_spice', {}).get('type') == 'program' and device.get('array') is not None:
        raise ValueError(device['name']+': simulation programs cannot be instance arrays.')
    mapped = {}
    for pin, expression in device['nets'].items():
        terminal_names = signals(pin) if device['kind'] in ('X', 'SPICE', 'XS') else [pin]
        nets = signals(expression); width = len(terminal_names)
        if len(nets) not in (width, width*len(members)):
            raise ValueError(f'{device["name"]}.{pin}: connection width {len(nets)} does not match terminal width {width} or array width {width*len(members)}.')
        mapped[pin] = (terminal_names, nets)
    if members == [None] and all(names == [pin] and nets == [device['nets'][pin]] for pin,(names,nets) in mapped.items()):
        return [device]
    result = []
    for position, index in enumerate(members):
        item = clone(device); item.pop('array', None)
        if index is not None:
            item['name'] = device['name']+'__'+str(index)
            if not NAME.fullmatch(item['name']):
                raise ValueError('Expanded instance name exceeds the native name limit: '+item['name'])
            item['id'] = 'array_'+digest([device['id'], index])[:24]
            item['array_source_id'] = device['id']; item['array_index'] = index
        item['nets'] = {}
        for names, nets in mapped.values():
            offset = 0 if len(nets) == len(names) else position*len(names)
            for pin, net in zip(names, nets[offset:offset+len(names)]):
                if pin in item['nets']:
                    raise ValueError(device['name']+': overlapping vector terminal names.')
                item['nets'][pin] = net
        # These are electrical views. Drawing anchors stay on the compact
        # source instance and must not accidentally rebuild the expanded view.
        item.pop('net_labels', None); item.pop('net_ids', None); item.pop('terminal_ids', None)
        result.append(item)
    return result


def devices(cell, project=None):
    from .layout_limits import MAX_MASTER_DEVICES
    result = []; names = set()
    for original in cell['devices']:
        for item in expand_device(original, project):
            name = item['name'].casefold()
            if name in names:
                raise ValueError('Expanded instance name collides: '+item['name'])
            names.add(name); result.append(item)
            if len(result) > MAX_MASTER_DEVICES:
                raise ValueError('Expanded native arrays exceed the per-cell device limit.')
    return result


def global_nets(project):
    return [name for expression in project.get('global_nets', []) for name in signals(expression)]


def configure_array(project, cell_id, device_id, start=None, end=None):
    """Set/remove array bounds; caller's history transaction validates widths."""
    cell = next(c for c in project['cells'] if c['id'] == cell_id)
    item = next(d for d in cell['devices'] if d['id'] == device_id)
    if start is not None and (any(s.get('device_id')==device_id or s.get('generated_device')==device_id for s in cell['shapes'])
                              or any(pin.get('device_id')==device_id for pin in cell.get('layout_pins',[]))):
        raise ValueError('Remove the generated primitive footprint before configuring an instance array; member geometry must be generated separately.')
    if start is None and end is None:
        item.pop('array', None)
    else:
        item['array'] = {'start': start, 'end': end}
    devices(cell, project)
