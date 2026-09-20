"""Capture only explicitly saved ngspice operating-point vectors."""
import math,cmath,re
from .model import flatten
from .catalog import binding_for
from .interchange import spice_name


def mos_vectors(alias, name, binding, aliases):
    """Subcircuit internals are opt-in metadata tied to the model definition."""
    internal=(binding or {}).get('operating_point_device')
    if internal:
        if not isinstance(internal,str) or not re.fullmatch(r'(?:x[A-Za-z0-9_$-]+\.)*m[A-Za-z0-9_$-]+',internal,re.I):
            raise ValueError('operating_point_device must be an explicit relative MOS instance path.')
        alias='m.'+alias+'.'+internal
    elif alias[0].upper()!='M':return []
    aliases[alias.casefold()]=name
    keys=['id','gm','gds','vgs','vds','vdsat']
    # Intrinsic charge derivatives are only requested by the pinned BSIM4
    # characterization adapter, never guessed for arbitrary imported models.
    if (binding or {}).get('characterization_capacitances'):
        keys += ['cgg','cgs','cgd','cgb']
    return ['@'+alias+'['+k+']' for k in keys]


def characterization_binding(project, cid, instance, binding, checked=None):
    fixture = project.get('gmid_fixture', {})
    if fixture.get('cell') != cid or fixture.get('device') != instance['id']:
        from .process_mos import readout_binding
        return readout_binding(project['pdk'], instance, binding, checked)
    # Recheck the pinned adapter at execution; the embedded catalog signature
    # and model-closure proof remain untouched by readout metadata.
    from .analog_characterization import contract
    adapter = contract(project, cid, instance['name'])
    return {**(binding or {}), 'operating_point_device': adapter['internal'],
            'characterization_capacitances':bool(adapter['internal'])}


def native_save(project,cid):
    from .native_spice import render
    from .catalog_migration import instance_name
    from .analog_debug import contexts
    from .design_ops import parameters, resolved_device, value
    by={c['id']:c for c in project['cells']};aliases={};vectors=[];checked={}
    context_by={c['path']:c for c in contexts(project,cid)}
    global_parameters=parameters(project.get('parameters',{}))
    def walk(key,path,spice_path,overrides=None):
        cell=by[key];context=context_by[path]
        values=parameters({**cell.get('parameters',{}),**(overrides or {})},global_parameters)
        for net,flat in context['nets'].items():
            if flat==path+net:aliases['v:'+('.'.join(spice_path+[net])).casefold()]=flat
        for d in cell['devices']:
            native=d.get('native_spice',{})
            if native.get('type')=='program':continue
            binding=binding_for(project['pdk'],d) if d.get('model_ref') else None
            # Resolve parameter overrides in this hierarchy instance before
            # checking its dimension contract; readout aliases retain its path.
            resolved=resolved_device(d,values) if binding else d
            binding=characterization_binding(project,cid,resolved,binding,checked)
            local=instance_name(d,binding) if d.get('model_ref') else render(d,by.get(d.get('cell'))).split()[0] if native else d['name'] if d['kind']=='X' else spice_name(d)
            if d['kind']=='X':walk(d['cell'],path+d['name']+'/',spice_path+[local],{k:value(v,values) for k,v in d.get('parameters',{}).items()});continue
            alias=local[0]+'.'+'.'.join(spice_path+[local]) if spice_path else local
            name=path+d['name'];aliases[alias.casefold()]=name
            metadata=binding or native
            if metadata.get('operating_point_device'):
                # Subcircuit calls carry no extra primitive prefix inside the path.
                alias='.'.join(spice_path+[local])
            if d['kind'] in ('NMOS','PMOS') or local[0].upper()=='M' or binding or metadata.get('operating_point_device'):
                vectors.extend(mos_vectors(alias,name,metadata,aliases))
    walk(cid,'',[])
    return '.save all '+' '.join(vectors),aliases


def save_directive(p,cid):
    aliases={};vectors=[];checked={}
    for d in flatten(p,cid):
        binding=characterization_binding(p,cid,d,binding_for(p['pdk'],d),checked);alias=(binding['prefix']+'_'+d['name'].replace('/','_')) if binding else spice_name(d);aliases[alias.casefold()]=d['name']
        if d['kind'] in ('NMOS','PMOS'):
            vectors.extend(mos_vectors(alias,d['name'],binding,aliases))
    return '.save all '+ ' '.join(vectors),aliases


def extras(variables,rows,complex_data=False,aliases=None):
    currents={};phase={};devices={};aliases=aliases or {}
    for j,raw in enumerate(variables):
        n=raw.casefold()
        # Internal device vectors can be wrapped as i(@m1[id]) or v(@m1[gm]).
        internal=n[2:-1] if (n.startswith('i(') or n.startswith('v(')) and n.endswith(')') else n
        match=re.fullmatch(r'@([^\[\]]+)\[(id|gm|gds|cgg|cgs|cgd|cgb|vgs|vds|vdsat)\]',internal)
        if match and not complex_data and len(rows)==1:
            alias,key=match.groups();value=float(rows[0][j])
            if math.isfinite(value):devices.setdefault(aliases.get(alias,alias),{})[key]=value
        elif n.startswith('i(') and n.endswith(')') or n.endswith('#branch'):
            alias=n[2:-1] if n.startswith('i(') else n[:-7];name=aliases.get(alias,alias);currents[name]=[abs(r[j]) if complex_data else float(r[j]) for r in rows]
            if complex_data:phase[name]=[math.degrees(cmath.phase(r[j])) for r in rows]
    for values in devices.values():
        if 'vds' in values and 'vdsat' in values:values['headroom']=abs(values['vds'])-abs(values['vdsat'])
        values['source']='saved ngspice device vectors'
    return currents,phase,devices
