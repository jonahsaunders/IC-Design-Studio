"""Schematic readouts from saved voltages and explicitly exposed device data."""
import math
from .model import flatten, scalar, design_digest


def builtin_devices(p,cid,voltages):
    from .simulation import mos_current
    out={}
    for d in flatten(p,cid):
        if d['kind'] not in ('NMOS','PMOS'):continue
        vd,vg,vs=[voltages.get(d['nets'][pin],0.) for pin in ('d','g','s')];pol=1 if d['kind']=='NMOS' else -1;vds=pol*(vd-vs);vgs=pol*(vg-vs)
        over=vgs-min(vds,0)-scalar(d['params']['vto']);headroom=abs(vds)-max(over,0)
        gm=(mos_current(d,vd,vg+1e-6,vs)-mos_current(d,vd,vg-1e-6,vs))/2e-6
        out[d['name']]={'id':mos_current(d,vd,vg,vs),'gm':gm,'vgs':vg-vs,'vds':vd-vs,'headroom':headroom,'region':'cutoff' if over<=0 else 'saturation' if headroom>=0 else 'linear','source':'teaching square-law model'}
    return out


def readouts(p,cid,result,x=None):
    if result is None or result.get('project_id')!=p['id'] or result.get('cell_id')!=cid:return {},'Select a result for this cell.'
    stale=result.get('design_hash')!=design_digest(p);cell=next(c for c in p['cells'] if c['id']==cid);op=result.get('operating_point',{});volts={k.casefold():v for k,v in op.items()};volts['0']=0.;label='Operating point'
    if result.get('case'):
        label+=' · case '+str(result['case']['index'])
        stale=result['case'].get('base_design_hash')!=design_digest(p)
    if x is not None:
        from .measurements import sample_at
        if result.get('settings',{}).get('type') in ('ac','noise'):return {},'Select an operating-point or time-domain run for annotations.'
        volts={k.casefold():sample_at(result,k,x) for k in result['traces']};volts['0']=0.;label=f'Sample X={x:g}'
    result_rows={}
    for d in cell['devices']:
        parts=[pin+' '+f'{volts[net.casefold()]:.4g} V' for pin,net in d['nets'].items() if volts.get(net.casefold()) is not None]
        device=result.get('device_operating_point',{}).get(d['name'],{}) if x is None else {}
        for key,unit in (('id','A'),('gm','S'),('headroom','V')):
            if key in device:parts.append(f'{key} {device[key]:.4g} {unit}')
        if 'region' in device:parts.append(device['region'])
        current=result.get('operating_currents',{}).get(d['name']) if x is None else None
        if current is not None:parts.append(f'I {current:.4g} A')
        if parts:result_rows[d['id']]='\n'.join(parts)
    return result_rows,('STALE · ' if stale else '')+label+' · '+result.get('engine','')
