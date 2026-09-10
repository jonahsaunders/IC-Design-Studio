"""Map retained engine findings to native cells, objects and nets without guessing."""
import json, re
from pathlib import Path
from .model import digest, design_digest, flatten, file_digest
from .layout import polygon, kdb


def device_map(p, cid):
    from .catalog import binding_for
    from .interchange import spice_name
    owner={d['id']:c['id'] for c in p['cells'] for d in c['devices']};names={}
    for d in flatten(p,cid):
        b=binding_for(p['pdk'],d);name=d['name'].replace('/','_')
        aliases={spice_name(d)}
        if b:aliases|={b['prefix']+'_'+name,b['model']+'_'+name}
        for alias in aliases:names.setdefault(alias.casefold(),[]).append({'cell_id':owner[d['id']], 'object':d['id'], 'instance_path':d['name']})
    return {name:values[0] for name,values in names.items() if len(values)==1}


def collect(p, cid, directory):
    out=Path(directory);by={c['id']:c for c in p['cells']};byname={c['name']:c['id'] for c in p['cells']};issues=[]
    def add(code,message,source,**location):
        item={'severity':'error','code':code,'cell_id':cid,'object':'','message':message,'source':source,
              'source_design_hash':design_digest(p),**location};item['fingerprint']=digest(item);issues.append(item)
    for file in ('link-findings.json','connection-findings.json'):
        path=out/file
        if path.is_file():
            for i in json.loads(path.read_text()):
                row={**i,'cell_id':i.get('cell_id',cid),'source':file,'source_design_hash':design_digest(p)};issues.append(row)
    nav=out/'drc/navigation.tsv';legacy=out/'drc/findings.tsv';log=out/'drc/console.log'
    if nav.is_file() or (legacy.is_file() and log.is_file()):
        scales=re.findall(r'^STUDIO_MAGIC_SCALE ([0-9.eE+-]+)$',log.read_text(),re.M) if log.is_file() else []
        factor=float(scales[0])*1000 if len(scales)==1 else None
        path=nav if nav.is_file() else legacy
        for line in path.read_text().splitlines()[:4000]:
            parts=line.split('\t')
            if len(parts)==4:
                name,reason,raw,scale=parts;key=byname.get(name);unit=float(scale)*1000
            elif len(parts)==2 and factor is not None:reason,raw=parts;key=cid;unit=factor
            else:continue
            if key is None:continue
            box=[round(float(v)*unit) for v in raw.split(',')]
            if len(box)!=4:continue
            region=kdb().Region(kdb().Box(*box));objects=[]
            for s in by[key]['shapes']:
                if not kdb().Region(polygon(s)).interacting(region).is_empty():objects.append(s['id'])
            add('MAGIC.DRC',reason,str(path.relative_to(out)),cell_id=key,bbox=box,objects=objects,object=objects[0] if objects else '')
    mapping=device_map(p,cid);path=out/'lvs/lvs.json'
    if path.is_file():
        try:data=json.loads(path.read_text())
        except (ValueError,TypeError):data=[]
        for cell in data:
            pins=cell.get('pins',[]);names=cell.get('name',[])
            key=byname.get(names[0]) if names else None
            if key is not None and len(pins)==2:
                for left,right in zip(*pins):
                    if left!=right and ('(no matching pin)' in (left,right)):
                        net=left if left in by[key]['ports'] else right if right in by[key]['ports'] else None
                        location={'cell_id':key}
                        if net:location['net']=net
                        add('NETGEN.PIN','Port '+str(net or left)+': extracted and schematic pin lists differ.','lvs/lvs.json',**location)
            for pair in cell.get('properties',[]):
                if len(pair)!=2 or not pair[0]:continue
                name=pair[0][0];location=mapping.get(name.casefold(),{})
                add('NETGEN.PROPERTY',name+': schematic '+str(pair[0][1])+'; layout '+str(pair[1][1]),'lvs/lvs.json',**location)
            for group in cell.get('badelements',[]):
                for element in group[0]:
                    name=element[0];add('NETGEN.DEVICE',name+': device connectivity differs from the extracted circuit.','lvs/lvs.json',**mapping.get(name.casefold(),{}))
            # Circuit 1 is the exact native schematic reference. Map only exact native net names.
            for group in cell.get('badnets',[]):
                for element in group[0]:
                    net=element[0];known={n for d in by[cid]['devices'] for n in d['nets'].values()}
                    if net in known:add('NETGEN.NET','Net '+net+': extracted connectivity does not match.','lvs/lvs.json',net=net)
                    else:add('NETGEN.NET','Unmapped schematic net '+net+': inspect the retained netlist comparison.','lvs/lvs.json')
    else:
        path=out/'lvs/lvs.log'
        if path.is_file():
            text=path.read_text()
            for match in re.finditer(r'^([^\s]+) vs\. (.+):\n([^\n]+)',text,re.M):
                name=match[1];add('NETGEN.PROPERTY',name+': '+match[3].strip(),'lvs/lvs.log',**mapping.get(name.casefold(),{}))
    return issues


def waveform(result, stage):
    if stage not in ('schematic','post-layout'):raise ValueError('Choose a saved simulation implementation.')
    name='schematic_simulation' if stage=='schematic' else 'post_layout_simulation'
    ev=next((s.get('evidence',{}) for s in result['silicon_report']['stages'] if s['name']==name),{})
    base=Path(result['evidence_directory']).resolve();path=(base/ev.get('waveform_file','missing')).resolve()
    if not path.is_relative_to(base) or not path.is_file() or file_digest(path)!=ev.get('waveform_sha256'):
        raise ValueError('Saved waveform is missing, changed or has no recorded checksum. Run physical verification again.')
    r=json.loads(path.read_text());bench=result['silicon_report']['testbench']
    if r['project_id']!=result['project_id'] or r['design_hash']!=result['design_hash'] or r['cell_id']!=bench['bench_cell']:
        raise ValueError('Saved waveform does not match this physical verification input.')
    return r
