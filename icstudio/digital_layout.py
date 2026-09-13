"""Attach an implemented block to its native cell without replacing its RTL."""
from .model import clone, digest
from .digital_design import bind_result,cell


def attach(project,cid,result,directory):
    from pathlib import Path
    import json
    from .digital_flow import validate_result
    from .digital_design import identity
    from .interchange import import_layout
    from .layout_attach import attach as attach_cells
    validate_result(result,directory)
    if result['project_id']!=project['id'] or result['cell_id']!=cid or result['digital_result']['source_hash']!=identity(project,cid):
        raise ValueError('Choose a current physical result for this digital cell.')
    record=result['digital_result']['artifacts'].get('gds')
    if not record:raise ValueError('The physical run has no completed GDS artifact.')
    imported,notes=import_layout(Path(directory)/record['path'])
    existing={c['name'].casefold() for c in project['cells']}
    # Keep physical library masters distinct from logical project cells.
    for incoming in imported['cells']:
        if incoming['id']==imported['top']:continue
        base=incoming['name'][:48];name=base;i=1
        while name.casefold() in existing:name=base+'_physical_'+str(i);i+=1
        incoming['name']=name;existing.add(name.casefold())
    temporary=clone(project);top=temporary['top']
    if 'digital' in temporary:temporary.setdefault('digital_cell',top)
    temporary['top']=cid
    candidate=attach_cells(temporary,imported,{imported['top']:cid});candidate['top']=top
    preview_record=result['digital_result']['artifacts'].get('layout_preview')
    if not preview_record:raise ValueError('The physical run is missing its terminal map.')
    preview=json.loads((Path(directory)/preview_record['path']).read_text())
    target=cell(candidate,cid);ports=[];power=[]
    for pin in preview.get('pins',[]):
        pair=pin.get('gds_layer');layer=next((l['name'] for l in candidate['pdk']['layers'] if [l['gds'],l['datatype']]==pair),None)
        if not layer:continue
        terminal={'name':pin['name'],'layer':layer,'point':[round(x*1000) for x in pin['point']]}
        if pin['name'] in target['ports']:ports.append(terminal)
        elif pin['use'] in ('POWER','GROUND'):power.append(terminal)
    if {p['name'] for p in ports}!=set(target['ports']):
        raise ValueError('Publish the RTL symbol first. Every signal terminal must have a captured DEF/GDS layer mapping before macro attachment.')
    target['layout_ports']=ports
    bind_result(candidate,cid,result,directory,'Physical')
    if 'spef' in result['digital_result']['artifacts']:bind_result(candidate,cid,result,directory,'Extracted')
    cell(candidate,cid)['digital_layout']={'source_hash':result['digital_result']['source_hash'],
        'gds_sha256':record['sha256'],'power_terminals':power,
        'scope':'Generated macro with mapped signal terminals. Power terminals are recorded separately; add them to the circuit interface before supply routing. DRC/LVS remain separate checks.','notes':notes}
    project.clear();project.update(candidate)
    return digest(candidate)
