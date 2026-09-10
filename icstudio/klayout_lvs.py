"""KLayout LVS execution and retained net/geometry cross-references."""
import json
from pathlib import Path
from .model import atomic_write, file_digest, digest, design_digest, now, clone


def read_database(path, limit=100000):
    import klayout.db as kdb
    path=Path(path); database=kdb.LayoutVsSchematic(); database.read(str(path))
    xref=database.xref()
    if xref is None: raise ValueError('This database has no schematic comparison. Open an LVS database with a cross-reference.')
    rows=[]; circuits=[]
    def name(obj):
        if obj is None:return ''
        value=obj.name() if callable(obj.name) else obj.name
        if not value and hasattr(obj,'id'):
            ident=obj.id() if callable(obj.id) else obj.id
            value='$'+str(ident)
        return str(value)
    for pair in xref.each_circuit_pair():
        left,right=pair.first(),pair.second()
        circuits.append({'layout':name(left),'schematic':name(right),'status':str(pair.status())})
        circuit=left if left is not None else right
        for kind, iterator in [('net',xref.each_net_pair),('device',xref.each_device_pair),('pin',xref.each_pin_pair),('instance',xref.each_subcircuit_pair)]:
            for item in iterator(circuit):
                if len(rows)>=limit:raise ValueError('The LVS database exceeds the finding budget. Select a smaller hierarchy.')
                row={'cell':name(left),'schematic_cell':name(right),'kind':kind,'layout':name(item.first()),
                     'schematic':name(item.second()),'status':str(item.status()),'boxes_um':[]}
                if kind=='net' and item.first() is not None:
                    for layer in database.layer_indexes():
                        region=database.polygons_of_net(item.first(),layer,True)
                        if not region.is_empty():
                            box=region.bbox();unit=database.internal_layout().dbu
                            row['boxes_um'].append([v*unit for v in (box.left,box.bottom,box.right,box.top)])
                rows.append(row)
    return {'version':1,'source':str(path.resolve()),'sha256':file_digest(path),'circuits':circuits,'rows':rows,
            'matched':bool(circuits) and all(c['status']=='Match' for c in circuits)}


def locations(project, row):
    """Return every physical occurrence; repeated cells are never silently collapsed."""
    by={c['id']:c for c in project['cells']}; root=project['top']; matches=[];visited=0
    from .layout import kdb
    from .physical_cells import transform
    def walk(cid,path,tr,seen):
        nonlocal visited
        visited+=1
        if cid in seen:raise ValueError('Recursive physical hierarchy.')
        if visited>10000:raise ValueError('Too many physical occurrences to cross-probe.')
        cell=by[cid]
        if cell['name']==row['cell']:
            boxes=[]
            for box in row['boxes_um']:
                b=kdb().Box(*[round(v*1000) for v in box]).transformed(tr)
                boxes.append([b.left,b.bottom,b.right,b.top])
            matches.append({'cell_id':cid,'instance_path':path,'boxes_nm':boxes,'local_boxes_um':row['boxes_um']})
        for inst in cell.get('layout_instances',[]):
            a=inst.get('a',[inst.get('dx',0),0]);b=inst.get('b',[0,inst.get('dy',0)])
            if inst.get('nx',1)*inst.get('ny',1)>10000:raise ValueError('Select a smaller physical array to cross-probe.')
            for x in range(inst.get('nx',1)):
                for y in range(inst.get('ny',1)):
                    offset=kdb().ICplxTrans(1,0,False,x*a[0]+y*b[0],x*a[1]+y*b[1])
                    walk(inst['cell'],path+[inst['name']+f'[{x},{y}]'],tr*offset*transform(inst),seen|{cid})
    walk(root,[],kdb().ICplxTrans(),set())
    if not matches:
        for cell in project['cells']:
            if cell['name']==row['cell']:matches.append({'cell_id':cell['id'],'instance_path':[], 'boxes_nm':[[round(v*1000) for v in b] for b in row['boxes_um']],'local_boxes_um':row['boxes_um']})
    return matches


def run(project,cid,settings,directory,progress=lambda *_:None):
    from .interchange import export_layout
    from .engines import execute
    from .rule_bundle import materialize
    from .testbenches import native_subcircuit
    from .native_spice import native,netlist
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True)
    if file_digest(settings['executable'])!=settings['executable_sha256']:raise ValueError('KLayout executable changed after planning.')
    bundle=settings['rule_bundle'];script=materialize(bundle,settings['bundle_hash'],root/'rules')
    layout=root/'input.gds';reference=root/'schematic.spice';report=root/'comparison.lvsdb'
    export_layout(project,layout)
    if native(project):
        p=clone(project);p['top']=cid;text=netlist(p,root,mode='lvs')
    else:text=native_subcircuit(project,cid)
    atomic_write(reference,text)
    top=next(c['name'] for c in project['cells'] if c['id']==cid)
    args=[settings['executable'],'-b','-r',str(script),'-rd','input='+str(layout),'-rd','top='+top,
          '-rd','schematic='+str(reference),'-rd','report='+str(report)]
    atomic_write(root/'command.json',json.dumps(args,indent=2));progress(.1,'Running KLayout LVS')
    try:log=execute(args,root/'rules',timeout=settings.get('timeout',600),on_line=lambda line:progress(.5,line))
    except Exception as exc:atomic_write(root/'engine.log',str(exc));raise
    atomic_write(root/'engine.log',log)
    if not report.is_file():raise ValueError('LVS script must save its database to $report using report_lvs.')
    data=read_database(report)
    data['schematic_objects']=schematic_objects(project,cid,native(project))
    progress(1,'LVS comparison loaded')
    result={'schema':1,'created':now(),'project_id':project['id'],'revision':project['revision'],
            'design_hash':design_digest(project),'pdk_hash':digest(project['pdk']),'rule_hash':settings['bundle_hash'],
            'engine':'KLayout LVS','engine_hash':settings['executable_sha256'],'cell_id':cid,'settings':settings,
            'klayout_lvs':data,'x':[],'x_label':'','y_label':'','traces':{},'phase':{},'operating_point':{},
            'log':log,'warnings':[] if data['matched'] else ['LVS contains unmatched or unverified circuits.'],
            'inputs':{'layout':file_digest(layout),'schematic':file_digest(reference)}}
    atomic_write(root/'lvs-evidence.json',json.dumps(result,indent=2));return result


def schematic_objects(project,cid,hierarchical):
    """Index emitted names and SPICE-reader names without ambiguous guesses."""
    from .interchange import spice_name
    candidates={}
    if hierarchical:
        for cell in project['cells']:
            for d in cell['devices']:
                emitted=d['name'] if d.get('native_spice') else spice_name(d)
                location={'cell_id':cell['id'],'object':d['id'],'instance_path':d['name']}
                for name in (emitted,emitted[1:]):candidates.setdefault(cell['name'].casefold()+'/'+name.casefold(),[]).append(location)
    else:
        from .verification_navigation import device_map
        top=next(c['name'] for c in project['cells'] if c['id']==cid)
        for emitted,location in device_map(project,cid).items():
            for name in (emitted,emitted[1:]):candidates.setdefault(top.casefold()+'/'+name.casefold(),[]).append(location)
    return {key:values[0] for key,values in candidates.items() if len({(v['cell_id'],v['object'],v['instance_path']) for v in values})==1}
