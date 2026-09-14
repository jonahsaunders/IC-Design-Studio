"""Declared DC resistance and opt-in, simulation-only series RL expansion."""
import math

from .model import clone, digest, scalar, device
from .layout_routing import via_recipes


def resistance(tech, geometry, corner='nominal'):
    from .rc_calibration import coefficients
    s=geometry['spec'];recipe=next(v for v in via_recipes(tech) if v['name']==s['via'])
    other=recipe['lower'] if s['metal']==recipe['upper'] else recipe['upper']
    result=dict(total_ohm=None,reason='',corner=corner,components=[],
                qualification='Uniform-current DC estimate; excludes spreading, skin/proximity effects, substrate loss and temperature extrapolation.')
    try:
        coeff,calibration=coefficients(tech,corner)
        values={layer:scalar(coeff.get(layer,{}).get('sheet_ohm',0)) for layer in (s['metal'],other)}
        missing=[layer+' sheet_ohm' for layer,value in values.items() if not math.isfinite(value) or value<=0]
        via=tech.get('via_resistance_ohm',{}).get(recipe['name'],recipe.get('resistance_ohm'))
        if via is None:missing.append(recipe['name']+' resistance per cut')
        else:
            via=scalar(via)
            if not math.isfinite(via) or via<=0:missing.append(recipe['name']+' positive resistance per cut')
        if missing:
            result['reason']='Missing '+', '.join(missing)+'.'
            return result
        parts=[dict(name='Winding and P lead',layer=s['metal'],ohm=values[s['metal']]*geometry['winding_length_nm']/s['width']),
               dict(name='Underpass',layer=other,ohm=values[other]*geometry['underpass_length_nm']/s['width']),
               dict(name='Two parallel via arrays',layer=recipe['cut'],ohm=2*via/(s['via_rows']*s['via_columns']))]
        source=dict(sheet_ohm=values,via_ohm=via,corner=corner,calibration=calibration,
                    winding_nm=geometry['winding_length_nm'],underpass_nm=geometry['underpass_length_nm'],
                    width_nm=s['width'],rows=s['via_rows'],columns=s['via_columns'])
        result.update(total_ohm=sum(v['ohm'] for v in parts),components=parts,source_hash=digest(source),source=source)
    except (ValueError,TypeError,KeyError) as exc:
        result['reason']=str(exc)
    return result


def expand_series_rl(project,cid=None,corner=None):
    """Return a simulation copy, preserving the editable schematic and layout.

    Both the teaching solver and SPICE writer use this function. Stale geometry,
    coefficient changes and later manual L changes require explicit regeneration.
    Internal nodes/names are unique within the cell and hierarchy flattening
    subsequently gives each instance its own copy.
    """
    if not any(d.get('inductor_rl') for c in project['cells'] for d in c['devices']):
        return project
    from . import inductor
    from .layout_vias import technology
    from .wiring import rebuild
    q=clone(project);_,invalid=inductor._recognized(q)
    ids={d['id'] for c in q['cells'] for d in c['devices']}
    by={c['id']:c for c in q['cells']};reached=set()
    def visit(key):
        if key in reached:return
        reached.add(key)
        for d in by[key]['devices']:
            if d['kind']=='X':visit(d['cell'])
    visit(cid or q['top'])
    stale={v['object'] for v in invalid}
    for c in q['cells']:
        if c['id'] not in reached:continue
        linked=[d for d in c['devices'] if d.get('inductor_rl')]
        if not linked:continue
        if 'wires' in c:rebuild(c,q)
        records={r['device_id']:r for r in c.get('parametric_devices',[])}
        names={d['name'].casefold() for d in c['devices']}
        nets={n for d in c['devices'] for n in d['nets'].values()}|set(c['ports'])|set(q.get('global_nets',[]))
        for d in linked:
            config=d['inductor_rl'];r=records.get(d['id'])
            if d['kind']!='L' or d['id'] in stale or not r:
                raise ValueError(d['name']+': series RL geometry is stale. Regenerate the inductor.')
            geometry=inductor.geometry(technology(q),inductor.current_spec(c,r))
            estimate=resistance(technology(q),geometry,corner or q.get('analysis',{}).get('corner','nominal'))
            if (estimate['total_ohm'] is None or config.get('source_hash')!=estimate.get('source_hash') or
                    config.get('resistance_ohm')!=estimate['total_ohm'] or config.get('value_h')!=scalar(d['value'])):
                raise ValueError(d['name']+': series RL estimate changed. Regenerate and opt in again.')
            name='R_'+d['name']+'_dc';node='inductor_'+d['id']+'_series'
            while name.casefold() in names:name+='x'
            while node in nets:node+='x'
            names.add(name.casefold());nets.add(node);positive=d['nets']['p']
            rid=digest(['inductor-dc-resistor',c['id'],d['id']])[:16]
            while rid in ids:rid=digest([rid,'series'])[:16]
            ids.add(rid)
            c['devices'].append(device('R',name,id=rid,value=format(estimate['total_ohm'],'.12g'),nets={'p':positive,'n':node}))
            d['nets']['p']=node
            if 'net_labels' in d:d['net_labels']['p']=node
            d.pop('inductor_rl')
        # Connections are resolved above. Wires are presentation/source topology;
        # they must not overwrite the simulation-only internal series node.
        for key in ('wires','labels','junctions'):c.pop(key,None)
    return q
