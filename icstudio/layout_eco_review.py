"""Human-readable device impact shared by change inspection and previews."""


def device_impact(project, cid, did):
    cell=next(c for c in project['cells'] if c['id']==cid)
    device=next((d for d in cell['devices'] if d['id']==did),None)
    pcells={r['id'] for r in cell.get('parametric_devices',[]) if r.get('device_id')==did}
    shapes=[s for s in cell['shapes'] if s.get('device_id')==did or s.get('generated_device')==did or s.get('pcell_id') in pcells]
    instances=[i for i in cell.get('layout_instances',[]) if i.get('device_id')==did]
    pins=[v for v in cell.get('layout_pins',[]) if v.get('device_id')==did]
    nets=sorted(set(device.get('nets',{}).values()) if device else {v.get('net','') for v in pins})
    parameters={**device.get('params',{}),**device.get('parameters',{})} if device else {}
    if device and 'value' in device:parameters['value']=device['value']
    values=', '.join(str(k)+'='+str(v) for k,v in parameters.items())
    name=device['name'] if device else 'Deleted schematic device'
    summary=cell['name']+' / '+name+(' · '+values if values else '')
    summary+='\nConnected nets: '+(', '.join(nets) or 'None')
    summary+=f'\nPhysical implementation: {len(shapes)} shapes, {len(instances)} instances, {len(pins)} terminals.'
    if not shapes and not instances:summary+=' Preview placement to create an implementation.'
    return dict(device=device,layout_objects=[s['id'] for s in shapes]+[i['id'] for i in instances],nets=nets,summary=summary)


def proposal_summary(before, after, report):
    lines=['Device and connection impact:']
    for row in report['changes']:
        old=device_impact(before,row['cell_id'],row['device_id']);new=device_impact(after,row['cell_id'],row['device_id'])
        lines.append(row['cell']+' / '+row['name']+': '+str(len(old['layout_objects']))+' → '+str(len(new['layout_objects']))+' physical objects; nets '+(', '.join(new['nets'] or old['nets']) or 'none'))
    lines.append('Existing verification results keep their original inputs. Re-run checks for the applied design revision.')
    return '\n'.join(lines)
