"""Capture only explicitly saved ngspice operating-point vectors."""
import math,cmath,re
from .model import flatten
from .catalog import binding_for
from .interchange import spice_name


def save_directive(p,cid):
    aliases={};vectors=[]
    for d in flatten(p,cid):
        binding=binding_for(p['pdk'],d);alias=(binding['prefix']+'_'+d['name'].replace('/','_')) if binding else spice_name(d);aliases[alias.casefold()]=d['name']
        if d['kind'] in ('NMOS','PMOS') and (not binding or binding.get('prefix')=='M'):
            vectors.extend('@'+alias+'['+key+']' for key in ('id','gm','vgs','vds','vdsat'))
    return '.save all '+ ' '.join(vectors),aliases


def extras(variables,rows,complex_data=False,aliases=None):
    currents={};phase={};devices={};aliases=aliases or {}
    for j,raw in enumerate(variables):
        n=raw.casefold()
        # Internal device vectors can be wrapped as i(@m1[id]) or v(@m1[gm]).
        internal=n[2:-1] if (n.startswith('i(') or n.startswith('v(')) and n.endswith(')') else n
        match=re.fullmatch(r'@([^\[\]]+)\[(id|gm|vgs|vds|vdsat)\]',internal)
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
