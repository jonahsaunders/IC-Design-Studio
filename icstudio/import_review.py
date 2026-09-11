"""Reviewed external layout edits with native schematic identity and hierarchy."""
from collections import defaultdict
from .model import clone,validate,digest
from .layout import kdb,polygon,shape_from_polygon


def propose_layout_change(project,path):
    db=kdb();ly=db.Layout();ly.read(str(path));out=clone(project);report=[]
    if abs(ly.dbu-project['pdk']['dbu_um'])>1e-12:raise ValueError('Import units differ from the project. Convert to the declared database unit before review.')
    claimed=set()
    for source in ly.each_cell():
        marker=source.property(125)
        if marker is None:
            # GDS has no standard cell properties. Drawing and instance
            # properties carry their owning cell identity across a rename.
            owners={s.property(125) for i in ly.layer_indexes() for s in source.shapes(i).each() if s.property(125)}
            owners.update(i.property(125) for i in source.each_inst() if i.property(125))
            if len(owners)==1:marker=next(iter(owners))
        if isinstance(marker,str) and marker.startswith('icstudio:'):
            ident=marker[9:]
            if ident in claimed:raise ValueError('Two external cells claim the same Studio identity.')
            claimed.add(ident)
            original=next((c for c in out['cells'] if c['id']==ident),None)
            if original and original['name']!=source.name:
                report.append(original['name']+': renamed externally to '+source.name);original['name']=source.name
    layers={(l['gds'],l['datatype']):l['name'] for l in project['pdk']['layers']};by={c['name']:c for c in out['cells']}
    for idx in ly.layer_indexes():
        info=ly.get_info(idx)
        if (info.layer,info.datatype) not in layers and any(not c.shapes(idx).is_empty() for c in ly.each_cell()):raise ValueError(f'Import uses unmapped layer {info.layer}/{info.datatype}. Add an explicit technology mapping first.')
    extra=[c.name for c in ly.top_cells() if c.name not in by]
    if extra:raise ValueError('Imported top cells do not match the project: '+', '.join(extra))
    # The normal reader rejects magnification, unsupported rotations, oversized
    # hierarchies, and nonintegral database coordinates before any candidate exists.
    from .layout_import import read_layout
    parsed,_=read_layout(__import__('pathlib').Path(path))
    parsed_by={c.get('source_cell_name',c['name']):c for c in parsed['cells']}
    name_by_id={c['id']:name for name,c in parsed_by.items()}
    for source in ly.each_cell():
        if source.name not in by:
            c={'id':digest([project['id'],'external_cell',source.name])[:16],'name':source.name,'ports':[],'devices':[],'shapes':[]};by[source.name]=c;out['cells'].append(c);report.append(source.name+': add physical cell.')
    changed=0
    for cell in out['cells']:
        source=ly.cell(cell['name'])
        if source is None:report.append(cell['name']+': absent from import; retained.');continue
        prior=clone(cell);incoming=parsed_by[cell['name']];replacements=[]
        old_by_poly=defaultdict(list);old_ids={s['id']:s for s in cell['shapes']};used_shapes=set()
        def signature(layer,poly):return layer,db.Region(poly).merged().to_s()
        for s in cell['shapes']:old_by_poly[signature(s['layer'],polygon(s))].append(s)
        different=False;incoming_texts=[];claims=defaultdict(list)
        for idx in ly.layer_indexes():
            for shape in source.shapes(idx).each():
                if shape.is_text():continue
                marker=shape.property(127) or shape.property('icstudio_id')
                if isinstance(marker,str):claims[marker[9:] if marker.startswith('icstudio:') else marker].append(shape)
        for ident,items in claims.items():
            if ident in old_ids and len(items)>1:
                original=old_ids[ident];layer=next(l for l in project['pdk']['layers'] if l['name']==original['layer'])
                exact=[s for s in items if ly.get_info(s.layer).layer==layer['gds'] and ly.get_info(s.layer).datatype==layer['datatype'] and signature(original['layer'],s.polygon)==signature(original['layer'],polygon(original))]
                if len(exact)!=1:raise ValueError(cell['name']+': copied shape identity is ambiguous. Retain one unchanged original or remove duplicate identity properties before review.')
        for idx in ly.layer_indexes():
            info=ly.get_info(idx);layer=layers.get((info.layer,info.datatype))
            if layer is None:continue
            imported=db.Region();old=db.Region()
            for shape in source.shapes(idx).each():
                if shape.is_text():
                    t=shape.text;incoming_texts.append({'layer':layer,'text':t.string,'x':t.x,'y':t.y,'rotation':t.trans.angle*90,'mirror':t.trans.is_mirror(),
                        'size':t.size,'font':t.font,'halign':int(t.halign),'valign':int(t.valign)})
                    properties=[[k,v] for k,v in shape.properties().items() if k!=125]
                    if properties:incoming_texts[-1]['external_properties']=properties
                    continue
                poly=shape.polygon;imported.insert(poly);matches=old_by_poly[signature(layer,poly)]
                marker=shape.property(127) or shape.property('icstudio_id');ident=marker[9:] if isinstance(marker,str) and marker.startswith('icstudio:') else marker
                original=old_ids.get(ident)
                if original and ident not in used_shapes and (len(claims[ident])==1 or signature(layer,poly)==signature(original['layer'],polygon(original))):
                    if signature(layer,poly)==signature(original['layer'],polygon(original)):replacement=clone(original)
                    else:
                        geometry=shape_from_polygon(poly,layer)
                        replacement={**clone(original),**{k:v for k,v in geometry.items() if k in ('kind','layer','points','holes','width')}};replacement['id']=ident
                        replacement['external_modified']=True
                    if original in old_by_poly[signature(original['layer'],polygon(original))]:old_by_poly[signature(original['layer'],polygon(original))].remove(original)
                elif matches and not marker:
                    if len(matches)>1:raise ValueError(cell['name']+': coincident shapes without identity properties need explicit reconciliation.')
                    replacement=clone(matches.pop(0))
                else:
                    replacement=shape_from_polygon(poly,layer)
                    replacement['id']=digest([project['id'],cell['id'],'external_shape',layer,poly.to_s(),len(replacements)])[:16]
                properties=[[k,v] for k,v in shape.properties().items() if k not in (125,127,'icstudio_id')]
                if properties or 'external_properties' in replacement:replacement['external_properties']=properties
                used_shapes.add(replacement['id']);replacements.append(replacement)
            for s in cell['shapes']:
                if s['layer']==layer:old.insert(polygon(s))
            xor=(old^imported).merged()
            if not xor.is_empty():different=True;report.append(f'{cell["name"]} / {layer}: XOR area {xor.area()*1e-6:.6g} µm²')
        incoming_layers={layers[(ly.get_info(i).layer,ly.get_info(i).datatype)] for i in ly.layer_indexes() if (ly.get_info(i).layer,ly.get_info(i).datatype) in layers}
        if any(s['layer'] not in incoming_layers for s in cell['shapes']):different=True;report.append(cell['name']+': a drawing layer was removed.')
        # Match physical instances by placement/hierarchy to retain IDs and names.
        def instkey(i):return (i['cell'],i['x'],i['y'],i.get('rotation',0),i.get('mirror',False),i.get('nx',1),i.get('ny',1),tuple(i.get('a',[i.get('dx',0),0])),tuple(i.get('b',[0,i.get('dy',0)])))
        old_instances=defaultdict(list)
        for i in cell.get('layout_instances',[]):old_instances[instkey(i)].append(i)
        instances=[];names=set();seen_ids=set();old_ids={i['id']:i for i in cell.get('layout_instances',[])}
        placements=clone(incoming.get('layout_instances',[]));claims=defaultdict(list)
        for i in placements:
            i['cell']=by[name_by_id[i['cell']]]['id']
            if i.get('source_instance_id'):claims[i['source_instance_id']].append(i)
        for ident,items in claims.items():
            if ident in old_ids and len(items)>1 and sum(instkey(i)==instkey(old_ids[ident]) for i in items)!=1:
                raise ValueError(cell['name']+': copied instance identity is ambiguous. Retain one unchanged original or remove duplicate identity properties before review.')
        for i in placements:
            marker=i.pop('source_instance_id',None);original=old_ids.get(marker);same=old_instances[instkey(i)]
            if original and original['cell']==i['cell'] and original['id'] not in seen_ids and (len(claims[marker])==1 or instkey(i)==instkey(original)):
                i={**original,**{k:v for k,v in i.items() if k not in ('id','name')}}
                if original in old_instances[instkey(original)]:old_instances[instkey(original)].remove(original)
            elif same and not marker:
                if len(same)>1:raise ValueError(cell['name']+': coincident instances without identity properties need explicit reconciliation.')
                original=same.pop(0)
                i={**original,**{k:v for k,v in i.items() if k not in ('id','name')}}
            else:
                n=1
                while 'External'+str(n) in {j['name'] for j in cell.get('layout_instances',[])}|names:n+=1
                i['name']='External'+str(n)
                i['id']=digest([project['id'],cell['id'],'external_instance',instkey(i),len(instances)])[:16]
            seen_ids.add(i['id']);names.add(i['name']);instances.append(i)
        hierarchy_changed=sorted(instkey(i) for i in instances)!=sorted(instkey(i) for i in cell.get('layout_instances',[]))
        properties_changed={i['id']:i.get('external_properties',[]) for i in instances}!={i['id']:i.get('external_properties',[]) for i in cell.get('layout_instances',[])}
        if hierarchy_changed:different=True;report.append(cell['name']+': physical placements/arrays changed; hierarchy retained.')
        shape_metadata_changed={s['id']:s for s in replacements}!={s['id']:s for s in cell['shapes']}
        cell_properties=incoming.get('external_properties',[])
        if properties_changed or shape_metadata_changed or cell_properties!=cell.get('external_properties',[]):
            different=True
            report.append(cell['name']+': object identities or external properties changed.')
        def textkey(t):return (t['layer'],t['text'],t['x'],t['y'],t.get('rotation',0),t.get('mirror',False),digest(t.get('external_properties',[])),t.get('size',0),t.get('font',-1),t.get('halign',-1),t.get('valign',-1))
        expected=[textkey(t) for t in cell.get('layout_texts',[])]
        if cell.get('layout_label_mode')!='explicit':expected += [(s['layer'],s['net'],*s['points'][0],0,False,digest([]),0,-1,-1,-1) for s in cell['shapes'] if s.get('net')]
        texts_changed=sorted(expected)!=sorted(textkey(t) for t in incoming_texts)
        if texts_changed:
            different=True;cell['layout_texts']=incoming_texts;cell['layout_label_mode']='explicit';report.append(cell['name']+': apply external text labels. Verify terminal names and extracted LVS before using this layout.')
        if different:
            changed+=1;cell['shapes']=replacements
            if texts_changed and cell.get('layout_ports') is not None:
                from .physical_cells import infer_ports
                cell['layout_ports']=infer_ports(out,cell)
            if hierarchy_changed or properties_changed:cell['layout_instances']=instances
            if cell_properties or 'external_properties' in cell:cell['external_properties']=cell_properties
            cell.pop('generator',None)
            # Source records describe original schematic sizes, not a claim that
            # externally edited geometry still represents those devices.
            cell['external_layout_review']=True
            report.append(cell['name']+': schematic links retained for identified objects; new geometry is unbound. Modified device geometry requires connectivity, DRC and LVS review.')
        else:
            cell.clear();cell.update(prior)
    if not changed:report.append('No layout differences. Existing IDs, hierarchy, labels and recipes retained.')
    validate(out);return out,report
