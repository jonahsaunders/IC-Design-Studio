"""Reviewed external layout edits with native schematic identity and hierarchy."""
from collections import defaultdict
from .model import clone,validate,uid
from .layout import kdb,polygon,shape_from_polygon


def propose_layout_change(project,path):
    db=kdb();ly=db.Layout();ly.read(str(path));out=clone(project);report=[]
    if abs(ly.dbu-project['pdk']['dbu_um'])>1e-12:raise ValueError('Import units differ from the project. Convert to the declared database unit before review.')
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
            c={'id':uid(),'name':source.name,'ports':[],'devices':[],'shapes':[]};by[source.name]=c;out['cells'].append(c);report.append(source.name+': add physical cell.')
    changed=0
    for cell in out['cells']:
        source=ly.cell(cell['name'])
        if source is None:report.append(cell['name']+': absent from import; retained.');continue
        prior=clone(cell);incoming=parsed_by[cell['name']];replacements=[]
        old_by_poly=defaultdict(list)
        def signature(layer,poly):return layer,db.Region(poly).merged().to_s()
        for s in cell['shapes']:old_by_poly[signature(s['layer'],polygon(s))].append(s)
        different=False;incoming_texts=[]
        for idx in ly.layer_indexes():
            info=ly.get_info(idx);layer=layers.get((info.layer,info.datatype))
            if layer is None:continue
            imported=db.Region();old=db.Region()
            for shape in source.shapes(idx).each():
                if shape.is_text():
                    t=shape.text;incoming_texts.append({'layer':layer,'text':t.string,'x':t.x,'y':t.y,'rotation':t.trans.angle*90,'mirror':t.trans.is_mirror()});continue
                poly=shape.polygon;imported.insert(poly);matches=old_by_poly[signature(layer,poly)]
                if matches:replacements.append(matches.pop(0))
                else:replacements.append(shape_from_polygon(poly,layer))
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
        for i in incoming.get('layout_instances',[]):
            i=clone(i);i['cell']=by[name_by_id[i['cell']]]['id'];same=old_instances[instkey(i)]
            original=old_ids.get(i.pop('source_instance_id',None))
            if original and original['cell']==i['cell'] and original['id'] not in seen_ids:
                i={**original,**{k:v for k,v in i.items() if k not in ('id','name')}}
                if original in old_instances[instkey(original)]:old_instances[instkey(original)].remove(original)
            elif same:i=same.pop(0)
            else:
                n=1
                while 'External'+str(n) in {j['name'] for j in cell.get('layout_instances',[])}|names:n+=1
                i['name']='External'+str(n)
            seen_ids.add(i['id']);names.add(i['name']);instances.append(i)
        hierarchy_changed=sorted(instkey(i) for i in instances)!=sorted(instkey(i) for i in cell.get('layout_instances',[]))
        if hierarchy_changed:different=True;report.append(cell['name']+': physical placements/arrays changed; hierarchy retained.')
        def textkey(t):return (t['layer'],t['text'],t['x'],t['y'],t.get('rotation',0),t.get('mirror',False))
        expected=[textkey(t) for t in cell.get('layout_texts',[])]
        if cell.get('layout_label_mode')!='explicit':expected += [(s['layer'],s['net'],*s['points'][0],0,False) for s in cell['shapes'] if s.get('net')]
        texts_changed=sorted(expected)!=sorted(textkey(t) for t in incoming_texts)
        if texts_changed:
            different=True;cell['layout_texts']=incoming_texts;cell['layout_label_mode']='explicit';report.append(cell['name']+': apply external text labels. Verify terminal names and extracted LVS before using this layout.')
        if different:
            changed+=1;cell['shapes']=replacements
            if texts_changed and cell.get('layout_ports') is not None:
                from .physical_cells import infer_ports
                cell['layout_ports']=infer_ports(out,cell)
            if hierarchy_changed:cell['layout_instances']=instances
            cell.pop('generator',None)
            # Source records describe original schematic sizes, not a claim that
            # externally edited geometry still represents those devices.
            cell['external_layout_review']=True
            report.append(cell['name']+': schematic and assigned terminal locations retained; changed polygons lose their device/net links. Run connectivity, DRC and LVS again.')
        else:
            cell.clear();cell.update(prior)
    if not changed:report.append('No layout differences. Existing IDs, hierarchy, labels and recipes retained.')
    validate(out);return out,report
