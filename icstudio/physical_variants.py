"""Reviewed specialization of parameterized schematic cells for physical design."""
from .model import clone, uid, digest, design_digest, flatten, validate
from .design_ops import parameters, value


def clone_master(source):
    mapping = {}
    def scan(obj):
        if isinstance(obj, dict):
            if 'id' in obj:mapping.setdefault(obj['id'], uid())
            for v in obj.values():scan(v)
        elif isinstance(obj, list):
            for v in obj:scan(v)
    scan(source)
    def remap(obj):
        if isinstance(obj, dict):return {k:remap(v) for k,v in obj.items()}
        if isinstance(obj, list):return [remap(v) for v in obj]
        return mapping.get(obj,obj) if isinstance(obj,str) else obj
    return remap(source)


def electrical_signature(project, cid):
    fields = ('name', 'kind', 'nets', 'value', 'params', 'source', 'model_ref', 'model_params', 'native_spice')
    return [{k:d[k] for k in fields if k in d} for d in flatten(project,cid)]


def propose(project, cid):
    """Bind each distinct effective parameter set to one explicit cell master.

    Existing physical geometry is copied with new identities and retained for
    the ordinary ECO review. Specialization itself does not claim regeneration.
    """
    before = electrical_signature(project,cid)
    candidate = clone(project); by = {c['id']:c for c in candidate['cells']}
    globals_ = parameters(candidate.get('parameters',{})); cache = {}; visited = set(); rows = []
    names = {c['name'].casefold() for c in candidate['cells']}

    def walk(ident, depth=0):
        if depth > 12:raise ValueError('Physical specialization exceeds the supported hierarchy depth.')
        if ident in visited:return
        visited.add(ident); cell = by[ident]
        context = parameters(cell.get('parameters',{}),globals_)
        for d in cell['devices']:
            if d['kind'] != 'X':continue
            source = by[d['cell']]
            if d.get('native_spice',{}).get('parameters'):
                raise ValueError(d['name']+': native SPICE parameter overrides need an explicit native implementation before physical specialization.')
            defaults = parameters(source.get('parameters',{}),globals_)
            actual = parameters({**source.get('parameters',{}),
                                 **{k:value(v,context) for k,v in d.get('parameters',{}).items()}},globals_)
            if actual != defaults:
                key = (source['id'],digest(actual))
                if key not in cache:
                    variant = clone_master(source)
                    stem = source['name'][:40]+'_p_'+key[1][:8]; name = stem; suffix = 1
                    while name.casefold() in names:suffix+=1;name=stem+'_'+str(suffix)
                    variant['name']=name; names.add(name.casefold())
                    variant['parameters']={k:str(actual[k]) for k in source.get('parameters',{})}
                    variant['physical_variant']={'source_cell':source['id'],'source_hash':digest(source),
                                                  'parameters':clone(variant['parameters'])}
                    candidate['cells'].append(variant);by[variant['id']]=variant;cache[key]=variant['id']
                target = by[cache[key]]
                rows.append({'cell_id':ident,'device_id':d['id'],'instance':cell['name']+'/'+d['name'],
                             'source':source['name'],'variant':target['name'],'parameters':actual})
                d['cell']=target['id']; d['parameters']={}
                # Keep placement position and identity. The following ECO review
                # detects the new master and updates its recorded signature.
                for inst in cell.get('layout_instances',[]):
                    if inst.get('device_id')==d['id']:inst['cell']=target['id']
                for bench in candidate.get('testbenches',[]):
                    if bench['dut_instance']==d['id']:bench['dut_cell']=target['id']
            walk(d['cell'],depth+1)
    walk(cid)
    if not rows:raise ValueError('This hierarchy has no differing parameter overrides to specialize.')
    validate(candidate)
    if electrical_signature(candidate,cid) != before:
        raise ValueError('Specialization changed the resolved circuit. The candidate was rejected.')
    return candidate, {'design_hash':design_digest(project),'cell_id':cid,'variants':len(cache),'instances':rows}
