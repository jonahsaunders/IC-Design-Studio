"""Cell views and revision-bound digital/analog interfaces, independent of Qt."""
from __future__ import annotations

import json
from pathlib import Path

from .model import clone, digest, uid


def cell(project, cid):
    return next(c for c in project['cells'] if c['id'] == cid)


def config(project, cid=None):
    cid = cid or project['top']
    return cell(project, cid).get('digital') or (project.get('digital') if cid == project.get('digital_cell', project['top']) else None)


def set_config(project, cid, value):
    """Preserve the first format while allowing independent RTL for other cells."""
    if 'digital' in project and cid == project.get('digital_cell', project['top']):
        project['digital_cell'] = cid
        project['digital'] = clone(value)
    else:
        cell(project, cid)['digital'] = clone(value)


def identity(project, cid):
    from .digital import source_hash
    value = config(project, cid)
    return source_hash(value) if value else None


def views(project, cid):
    c = cell(project, cid); source = identity(project, cid)
    out = [{'name': 'RTL', 'state': 'Available' if source else 'Absent'},
           {'name': 'Symbol', 'state': 'Available' if c.get('symbol') else 'Absent'},
           {'name': 'Schematic', 'state': 'Available' if c['devices'] else 'Absent'},
           {'name': 'Layout', 'state': 'Available' if c['shapes'] or c.get('layout_instances') else 'Absent'}]
    for name, record in c.get('digital_views', {}).items():
        from .digital_identity import stage_key
        fresh=record['input_key']==stage_key(config(project,cid),record['stage']) if record.get('input_key') and source else record['source_hash']==source
        out.append({'name': name, 'state': 'Current' if fresh else 'Stale', **record})
    return out


def bind_result(project, cid, result, directory, view):
    from .digital_flow import validate_result
    validate_result(result, directory)
    if result['project_id'] != project['id'] or result['cell_id'] != cid:
        raise ValueError('Choose a result for this project and cell.')
    record = {'source_hash': result['digital_result']['source_hash'],
              'directory': str(Path(directory).resolve()), 'stage': result['digital_result']['stage'],
              'artifacts': clone(result['digital_result']['artifacts'])}
    if result['digital_result'].get('input_key'):record['input_key']=result['digital_result']['input_key']
    cell(project, cid).setdefault('digital_views', {})[view] = record


def interface_proposal(project, cid, result, directory):
    """Use the compiler's elaborated ports, never a regular-expression HDL parser."""
    from .digital_identity import current
    if not current(result['digital_result'],config(project,cid)):
        raise ValueError('The RTL changed. Compile the current sources before publishing the symbol.')
    from .digital_flow import validate_result
    validate_result(result, directory)
    record = result['digital_result']['artifacts'].get('hierarchy')
    if not record: raise ValueError('Choose an elaboration or synthesis result with a JSON netlist.')
    data = json.loads((Path(directory)/record['path']).read_text())
    module = data['modules'][config(project,cid)['top']]
    ports = []; metadata = {}; left = []; right = []
    for name, info in module.get('ports', {}).items():
        count = len(info['bits']); offset = info.get('offset', 0)
        names = [name] if count == 1 and not info.get('upto') and not offset else [f'{name}[{i}]' for i in range(offset,offset+count)]
        if count > 1: names = [f'{name}[{i}]' for i in range(offset,offset+count)]
        for pin in names:
            ports.append(pin); (right if info['direction'] == 'output' else left).append(pin)
            metadata[pin] = {'direction': {'input':'in','output':'out','inout':'inout'}[info['direction']],
                             'role': 'clock' if name in ('clk','clock') else 'signal', 'required': True,
                             'bus': f'{name}[{offset+count-1}:{offset}]' if count>1 else ''}
    if len(ports) > 128: raise ValueError('The schematic symbol supports at most 128 scalar pins; publish a smaller block.')
    c = cell(project,cid)
    pins = {}
    for side, names in ((-1,left),(1,right)):
        pitch = min(20, 850/max(1,len(names)))
        for i, name in enumerate(names): pins[name] = [side*120, (i-(len(names)-1)/2)*pitch]
    height = max(40,min(450,max(len(left),len(right))*10+10))
    symbol = {'pins': pins, 'pin_order': ports, 'pin_meta': metadata,
                   'primitives': [{'kind':'rect','points':[[-100,-height],[100,height]]},
                                  {'kind':'text','points':[[-85,-10],[85,10]],'text':c['name'][:100]}]}
    return symbol, {'source_hash':identity(project,cid), 'ports':clone(module['ports'])}


def publish_interface(project, cid, result, directory):
    symbol, interface = interface_proposal(project,cid,result,directory)
    c=cell(project,cid);ports=symbol['pin_order']
    if c['ports'] and c['ports']!=ports and (c['devices'] or any(d.get('cell')==cid for q in project['cells'] for d in q['devices'])):
        raise ValueError('Review the changed interface and its instance connections before publishing.')
    c.update(ports=ports,symbol=symbol,digital_interface=interface)
    bind_result(project,cid,result,directory,'Netlist')
    return ports


def new_cell(project, name, source_config):
    from .model import NAME
    if not NAME.fullmatch(name) or any(c['name'].casefold() == name.casefold() for c in project['cells']):
        raise ValueError('Choose a unique native cell name.')
    cid = uid(); project['cells'].append({'id':cid,'name':name,'ports':[],'devices':[], 'shapes':[], 'digital':clone(source_config)})
    return cid


def require_analog_implementations(project, cid):
    """A graphical RTL symbol is not an analog simulation model."""
    visited = set()
    def walk(key):
        if key in visited:return
        visited.add(key); c = cell(project,key)
        if config(project,key) and not c['devices']:
            raise ValueError(c['name']+': this RTL block has no analog circuit implementation. '
                             'Use the digital testbench, or provide a schematic model before analog simulation.')
        for d in c['devices']:
            if d['kind'] == 'X':walk(d['cell'])
    walk(cid)


def validate_views(project):
    ids = {c['id'] for c in project['cells']}
    if project.get('digital_cell',project['top']) not in ids:raise ValueError('The digital cell binding is missing.')
    for c in project['cells']:
        records = c.get('digital_views', {})
        if not isinstance(records,dict) or len(records)>8:raise ValueError('Invalid digital cell views.')
        for name, record in records.items():
            if name not in ('Netlist','Mapped netlist','Physical','Extracted') or not isinstance(record,dict):raise ValueError('Invalid digital cell view.')
            if not isinstance(record.get('source_hash'),str) or len(record['source_hash']) != 64:raise ValueError('Missing digital view revision.')
