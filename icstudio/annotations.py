"""Schematic readouts from saved voltages and explicitly exposed device data."""
import math
from .model import flatten, scalar, design_digest

FIELDS = {
    'volts':'Terminal voltages', 'id':'Drain current', 'gm':'Transconductance',
    'gds':'Output conductance', 'ro':'Incremental output resistance', 'ratio':'gm/ID',
    'vgs':'Gate-to-source voltage', 'vds':'Drain-to-source voltage', 'headroom':'Saturation headroom',
    'region':'Operating region', 'currents':'Branch current', 'dimensions':'MOS dimensions',
    'caps':'Intrinsic capacitance', 'model':'Model name', 'value':'Component value',
}
DEFAULT_FIELDS = frozenset(('volts','id','gm','ratio','headroom','region','currents'))


def design_fields(device, fields):
    parts=[]
    if 'dimensions' in fields:
        params={**device.get('params',{}),**device.get('model_params',{}),
                **device.get('native_spice',{}).get('parameters',{})}
        parts.extend(f'{key.upper()} {params[key]}' for key in ('w','l','nf','m') if key in params)
    if 'model' in fields:
        model=device.get('model_ref',{}).get('model') or device.get('native_spice',{}).get('model')
        if model:parts.append(f'Model {model}')
    if 'value' in fields and device.get('value'):
        parts.append(f'Value {device["value"]}')
    return parts


def region(device):
    if device.get('region'):
        return device['region']
    if not {'id','headroom','vdsat'} <= device.keys():
        return None
    if abs(device['id']) < 1e-12:
        return 'cutoff (estimate)'
    return 'saturation (estimate)' if device['headroom'] >= 0 else 'linear (estimate)'


def builtin_devices(p,cid,voltages):
    from .simulation import mos_current
    out={}
    for d in flatten(p,cid):
        if d['kind'] not in ('NMOS','PMOS'):continue
        vd,vg,vs=[voltages.get(d['nets'][pin],0.) for pin in ('d','g','s')];pol=1 if d['kind']=='NMOS' else -1;vds=pol*(vd-vs);vgs=pol*(vg-vs)
        over=vgs-min(vds,0)-scalar(d['params']['vto']);headroom=abs(vds)-max(over,0)
        gm=(mos_current(d,vd,vg+1e-6,vs)-mos_current(d,vd,vg-1e-6,vs))/2e-6
        out[d['name']]={'id':mos_current(d,vd,vg,vs),'gm':gm,'vgs':vg-vs,'vds':vd-vs,'headroom':headroom,'region':'cutoff' if over<=0 else 'saturation' if headroom>=0 else 'linear','source':'teaching square-law model'}
        out[d['name']]['gds']=(mos_current(d,vd+1e-6,vg,vs)-mos_current(d,vd-1e-6,vg,vs))/2e-6
    return out


def readouts(p,cid,result,x=None,instance_path=None,*,fields=None,selection=None):
    fields = DEFAULT_FIELDS if fields is None else fields
    if result is None or result.get('project_id')!=p['id']:
        cell=next((c for c in p['cells'] if c['id']==cid),{})
        rows={}
        for device in cell.get('devices',()):
            if selection is None or device['id'] in selection:
                if parts:=design_fields(device,fields):
                    rows[device['id']]='\n'.join(parts)
        return rows,'Design values · Select a result for measured annotations.' if rows else 'Select a result for this cell.'
    from .analog_debug import contexts
    root=result.get('cell_id')
    if root not in {c['id'] for c in p['cells']}:return {},'The result cell is absent from this revision.'
    matches=[c for c in contexts(p,root) if c['cell_id']==cid and (instance_path is None or c['path']==instance_path)]
    if len(matches)!=1:return {},'Select the specific hierarchy instance in the saved-run inspector.'
    context=matches[0]
    stale=result.get('design_hash')!=design_digest(p);cell=next(c for c in p['cells'] if c['id']==cid);op=result.get('operating_point',{});volts={k.casefold():v for k,v in op.items()};volts['0']=0.;label='Operating point'
    if result.get('case'):
        label+=' · case '+str(result['case']['index'])
        stale=stale and result['case'].get('base_design_hash')!=design_digest(p)
    if x is not None:
        from .measurements import sample_at
        if result.get('settings',{}).get('type') in ('ac','noise'):return {},'Select an operating-point or time-domain run for annotations.'
        volts={k.casefold():sample_at(result,k,x) for k in result['traces']};volts['0']=0.;label=f'Sample X={x:g}'
    device_points={k.casefold():v for k,v in result.get('device_operating_point',{}).items()} if x is None else {}
    branch_points={k.casefold():v for k,v in result.get('operating_currents',{}).items()} if x is None else {}
    result_rows={}
    for d in cell['devices']:
        if selection is not None and d['id'] not in selection:
            continue
        nets={pin:context['nets'][net] for pin,net in d['nets'].items()}
        parts=[pin+' '+f'{volts[net.casefold()]:.4g} V' for pin,net in nets.items()
               if volts.get(net.casefold()) is not None] if 'volts' in fields else []
        name=context['path']+d['name']
        device=device_points.get(name.casefold(),{})
        for key,unit in (('id','A'),('gm','S'),('gds','S'),('vgs','V'),('vds','V'),('headroom','V')):
            if key in fields and key in device:parts.append(f'{key} {device[key]:.4g} {unit}')
        if 'ro' in fields and device.get('gds',0)>0:parts.append(f'ro {1/device["gds"]:.4g} Ω')
        if 'ratio' in fields and device.get('gm') is not None and abs(device.get('id', 0)) > 1e-18:
            ratio=abs(device['gm']/device['id'])
            if math.isfinite(ratio):parts.append(f'gm/Id {ratio:.4g} 1/V')
        if 'region' in fields and (labelled_region:=region(device)):parts.append(labelled_region)
        if 'caps' in fields:
            parts.extend(f'{key} {device[key]:.4g} F' for key in ('cgg','cgs','cgd','cgb') if key in device)
        parts.extend(design_fields(d,fields))
        current=branch_points.get(name.casefold()) if 'currents' in fields else None
        if current is not None:parts.append(f'I {current:.4g} A')
        if parts:result_rows[d['id']]='\n'.join(parts)
    return result_rows,('STALE · ' if stale else '')+label+' · '+result.get('engine','')
