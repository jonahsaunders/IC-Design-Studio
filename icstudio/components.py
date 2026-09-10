"""Reusable electrical cells: ordered terminals, defaults, and imported bodies."""
from .model import clone, uid, validate, file_digest, flatten
from .symbol_io import default_symbol


def configure_component(project, cid, name, ports, defaults):
    cell = next(c for c in project['cells'] if c['id'] == cid)
    users = [d for c in project['cells'] for d in c['devices'] if d.get('cell') == cid]
    if users and set(ports) != set(cell['ports']):
        raise ValueError('Referenced components may reorder terminals. Remove instances before adding or deleting terminals.')
    if len(ports) != len(set(ports)) or len({p.casefold() for p in ports}) != len(ports):
        raise ValueError('Terminal names must be unique, including in SPICE case folding.')
    for d in users:
        unknown = set(d.get('parameters', {})) - set(defaults)
        if unknown: raise ValueError(d['name']+' overrides removed parameter(s): '+', '.join(sorted(unknown)))
    cell.update(name=name, ports=list(ports), parameters=clone(defaults))
    symbol = cell.get('symbol') or default_symbol(ports)
    seed = default_symbol(ports)
    symbol['pins'] = {p: symbol['pins'].get(p, seed['pins'][p]) for p in ports}
    if 'pin_order' in symbol:symbol['pin_order']=list(ports)
    if 'pin_meta' in symbol:symbol['pin_meta']={pin:symbol['pin_meta'].get(pin,{}) for pin in ports}
    cell['symbol'] = symbol
    for d in users:
        d['nets'] = {pin:d['nets'][pin] for pin in ports}
        d['symbol'] = clone(symbol)


def import_component(project, path, selected):
    """Copy the selected subcircuit and dependencies as editable native cells."""
    from .spice_import import import_spice
    imported, _ = import_spice(path, project['pdk'] if project['pdk'].get('package_lock') else None)
    by = {c['id']: c for c in imported['cells']}
    source = next(c for c in imported['cells'] if c['name'] == selected)
    if not source['ports']: raise ValueError('Choose a subcircuit with explicit terminals.')
    needed = set()
    def walk(cid):
        if cid in needed: return
        needed.add(cid)
        for d in by[cid]['devices']:
            if d['kind']=='X': walk(d['cell'])
    walk(source['id'])
    # Re-key all object IDs (including wire/physical references) in one traversal.
    mapping = {}
    def collect(value):
        if isinstance(value, dict):
            if 'id' in value: mapping[value['id']] = uid()
            for v in value.values(): collect(v)
        elif isinstance(value,list):
            for v in value: collect(v)
    cells = [clone(c) for c in imported['cells'] if c['id'] in needed]
    collect(cells)
    def remap(value):
        if isinstance(value, dict): return {k:remap(v) for k,v in value.items()}
        if isinstance(value, list): return [remap(v) for v in value]
        return mapping.get(value,value) if isinstance(value,str) else value
    cells = remap(cells); names = {c['name'].casefold() for c in project['cells']}
    for c in cells:
        c['parameters']={**imported.get('parameters',{}),**c.get('parameters',{})}
        base=c['name'];n=2
        while c['name'].casefold() in names: c['name']=base[:54]+'_'+str(n);n+=1
        names.add(c['name'].casefold())
        c['symbol']=default_symbol(c['ports'])
        c['component_source']={'type':'spice','filename':__import__('pathlib').Path(path).name,'sha256':file_digest(path),'subcircuit':by[next(k for k,v in mapping.items() if v==c['id'])]['name']}
    project['cells'].extend(cells)
    validate(project)
    return mapping[source['id']]


def require_implementations(project, cid):
    by = {c['id']:c for c in project['cells']}; seen=set()
    def walk(key):
        if key in seen:return
        seen.add(key)
        for d in by[key]['devices']:
            if d['kind']=='X':
                child=by[d['cell']]
                if not child['devices']:raise ValueError(child['name']+': symbol has no electrical implementation. Draw its schematic or import a SPICE component before netlisting.')
                walk(child['id'])
    walk(cid)
