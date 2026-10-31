"""Prove routed connectivity without using block pins as endpoints.

Every drawn conductor must reach actual gate or diffusion/tap geometry. This is
a sufficient condition for the selected floating-net messages, not device/body
LVS. A pin-only feedthrough can be legal at IP level; it remains unreviewed here
rather than being labelled a foundry violation. Exceptions and edits are refused
as proof inputs, not silently applied.
"""
from pathlib import Path

from .digital_sky130_catalog_labels import normalized
from .model import file_digest

RECIPE='sky130-physical-device-roots-v1'
SOURCE=dict(revision='7198cf647113f56041e02abf3eb623692820c5e1',files={
    'docs/rules/errors.csv':'d613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv':'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5',
    'docs/rules/periphery/p018-x_dotdash.csv':'0efaf5099bc464a782f0c05a2850673ae940272c16fa22ec519057171f2f1567',
    'docs/rules/layers/table-c3-device-lvs-other.csv':'e56b7c0570f4ce5e4c0a002ddd0cc82f4c0e0d12d98a7634d419e0abd6a1fd98'})
CONDUCTORS=dict(poly=(66,20),licon=(66,44),li1=(67,20),mcon=(67,44),
    m1=(68,20),via=(68,44),m2=(69,20),via2=(69,44),m3=(70,20),via3=(70,44),m4=(71,20),via4=(71,44),m5=(72,20))
WIRES=('poly','li1','m1','m2','m3','m4','m5')
LAYERS=CONDUCTORS|dict(diff=(65,20),tap=(65,44),poly_short=(66,15))
ABSENT=((89,44),(97,44),(74,20),(65,14),(66,14),(67,14),(68,14),(69,14),(70,14),(71,14),(72,14),
        (67,15),(68,15),(69,15),(70,15),(71,15),(72,15))
LABELS=tuple(prefix+'_'+suffix for prefix in WIRES for suffix in ('float','tie'))
CHECKS={'s'+str(11+5*i):name for i,name in enumerate(WIRES)}
GRAPH_NAMES=tuple(CONDUCTORS)+('sd_root','gate_root')
SCOPE=('Every merged routed poly/LI/metal component is traced through every contact level to gate '
       '(poly AND diff) or diffusion/tap outside poly. Pin shapes, text, standard-cell markers and '
       'exception labels cannot supply endpoints or connectivity. Every submitted conductor/root area '
       'must be accounted for. Unrooted components leave the selected catalog messages unreviewed; '
       'a legal IP feedthrough is not automatically a foundry violation. Capacitor/RDL/cut/short edits '
       'and float/tie declarations prevent this proof. Dummy-fill purposes, device/body correctness, '
       'electrical behavior and complete physical qualification remain separate.')


def require(condition,message):
    if not condition:raise ValueError(message)


def expected(measurements,top,digest):
    require(isinstance(measurements,dict) and set(measurements)=={'layers','unsupported','exception_labels','poly_short_outside','graph'},
            'Missing SKY130 device-root measurements.')
    layers=measurements['layers'];unsupported=measurements['unsupported'];graph=measurements['graph']
    require(isinstance(layers,dict) and layers.keys()==LAYERS.keys() and isinstance(unsupported,dict) and
            set(unsupported)=={'%s:%s'%p for p in ABSENT},'Incomplete SKY130 device-root census.')
    for name,row in layers.items():
        require(isinstance(row,dict) and set(row)=={'raw_shapes','texts','components','area_nm2'} and
                all(type(v)is int and v>=0 for v in row.values()) and row['texts']<=row['raw_shapes'] and
                (row['components']>0)==(row['area_nm2']>0)==(row['raw_shapes']>row['texts']) and
                (not row['texts'] or name in (*WIRES,'diff')), 'Invalid SKY130 device-root layer counts.')
    require(all(type(n)is int and n>=0 for n in (*unsupported.values(),measurements['exception_labels'],measurements['poly_short_outside'])),
            'Invalid SKY130 device-root guard counts.')
    guarded=any(unsupported.values()) or measurements['exception_labels'] or measurements['poly_short_outside']
    unrooted={name:0 for name in WIRES}
    if guarded:require(graph is None,'Unsupported device-root operands cannot claim graph execution.')
    else:
        require(isinstance(graph,dict) and set(graph)=={'nets','rooted_nets','contact_only_nets','area_nm2','covered_area_nm2','unrooted'},
                'Missing SKY130 device-root graph.')
        require(all(type(graph[k])is int and graph[k]>=0 for k in ('nets','rooted_nets','contact_only_nets')) and
                graph['rooted_nets']<=graph['nets'],'Invalid SKY130 device-root net counts.')
        areas=graph['area_nm2'];covered=graph['covered_area_nm2']
        require(isinstance(areas,dict) and set(areas)==set(GRAPH_NAMES) and isinstance(covered,dict) and
                set(covered)==set(areas) and all(type(n)is int and n>=0 for n in (*areas.values(),*covered.values())) and
                covered==areas and all(areas[name]==layers[name]['area_nm2'] for name in CONDUCTORS),
                'Incomplete SKY130 device-root area accounting.')
        require(isinstance(graph['unrooted'],list) and
                len(graph['unrooted'])+graph['rooted_nets']+graph['contact_only_nets']==graph['nets'] and
                bool(graph['nets'])==any(areas.values()) and
                bool(graph['rooted_nets'])==bool(areas['sd_root'] or areas['gate_root']),
                'Invalid SKY130 unrooted-net accounting.')
        for net in graph['unrooted']:
            require(isinstance(net,dict) and set(net)=={'layers','bounds'} and isinstance(net['layers'],list) and
                    net['layers'] and net['layers']==sorted(set(net['layers'])) and set(net['layers'])<=set(WIRES) and
                    isinstance(net['bounds'],dict) and set(net['bounds'])==set(net['layers']) and
                    all(isinstance(v,str) and v for v in net['bounds'].values()),'Invalid SKY130 unrooted conductor record.')
            for name in net['layers']:unrooted[name]+=1
    rows=[dict(id=key,rule='x.22',layer=name,area_nm2=layers[name]['area_nm2'],
        unrooted_components=None if guarded else unrooted[name],
        disposition='unreviewed' if guarded or unrooted[name] else
        'executed-reviewed' if layers[name]['area_nm2'] else 'absent-operand') for key,name in CHECKS.items()]
    unresolved=sum(row['disposition']=='unreviewed' for row in rows)
    return dict(schema=1,recipe=RECIPE,source=SOURCE,scope=SCOPE,qualified=False,chunk_complete=False,
        top=top,gds_sha256=digest,pin_roots_used=False,measurements=measurements,rows=rows,unreviewed=unresolved,
        status='review-required' if unresolved else 'physical-device-roots-pass')


def measure(layout):
    import klayout.db as k
    require(len(layout.top_cells())==1 and abs(layout.dbu-.001)<1e-12,
            'SKY130 device-root checks require one top and a 1 nm database unit.')
    top=layout.top_cell()
    for index in {top.cell_index(),*top.called_cells()}:
        for instance in layout.cell(index).each_inst():
            t=instance.cplx_trans
            require(t.mag==1 and t.angle%90==0,'Unsupported SKY130 device-root transform.')
    regions,census={},{}
    for name,pair in LAYERS.items():
        region=k.Region();raw=texts=0;iterator=top.begin_shapes_rec(layout.layer(*pair))
        while not iterator.at_end():
            shape=iterator.shape();raw+=1
            if shape.is_text() and name in (*WIRES,'diff'):texts+=1;iterator.next();continue
            if shape.is_path():
                path=shape.path;points=list(path.each_point())
                require(path.width>0 and path.width%2==0 and not path.is_round() and len(points)>=2 and
                        all(a!=b and (a.x==b.x or a.y==b.y) for a,b in zip(points,points[1:])),
                        'Inexact SKY130 device-root path: '+name)
                polygon=path.polygon()
            else:
                require(shape.is_box() or shape.is_polygon() or shape.is_simple_polygon(),'Unsupported SKY130 device-root shape: '+name)
                polygon=shape.polygon
            require(polygon.area()>0 and all(e.p1.x==e.p2.x or e.p1.y==e.p2.y for e in polygon.each_edge()),
                    'SKY130 device-root checks require nonempty Manhattan polygons: '+name)
            region.insert(polygon.transformed(iterator.trans()));iterator.next()
        regions[name]=region.merged();census[name]=dict(raw_shapes=raw,texts=texts,components=regions[name].count(),area_nm2=regions[name].area())
    unsupported={}
    for pair in ABSENT:
        count=0;iterator=top.begin_shapes_rec(layout.layer(*pair))
        while not iterator.at_end():count+=1;iterator.next()
        unsupported['%s:%s'%pair]=count
    exceptions=0
    for index in layout.layer_indexes():
        iterator=top.begin_shapes_rec(index);iterator.shape_flags=k.Shapes.STexts
        while not iterator.at_end():
            value=normalized(iterator.shape().text.string);exceptions+=int(any(token in value for token in LABELS));iterator.next()
    short_outside=(regions['poly_short']-regions['poly']).count()
    graph=None
    if not (any(unsupported.values()) or exceptions or short_outside):
        masks={name:regions[name] for name in CONDUCTORS}
        masks['sd_root']=((regions['diff']|regions['tap'])-regions['poly']).merged()
        masks['gate_root']=(regions['diff']&regions['poly']).merged()
        netter=k.LayoutToNetlist('TOP',.001)
        for name,region in masks.items():netter.register(region,name);netter.connect(region)
        names=list(CONDUCTORS)
        for lower,upper in zip(names,names[1:]):netter.connect(masks[lower],masks[upper])
        netter.connect(masks['sd_root'],masks['licon']);netter.connect(masks['gate_root'],masks['poly'])
        netter.extract_netlist();circuit=netter.netlist().circuit_by_name('TOP')
        require(circuit is not None or all(r.is_empty() for r in masks.values()),'Device-root extraction lost nonempty geometry.')
        nets=rooted=contact_only=0;covered={name:0 for name in masks};unrooted=[]
        for net in circuit.each_net() if circuit else ():
            nets+=1;shapes={name:netter.shapes_of_net(net,region,True) for name,region in masks.items()}
            for name,region in shapes.items():covered[name]+=region.area()
            has_root=any(not shapes[name].is_empty() for name in ('sd_root','gate_root'))
            wires={name:shapes[name] for name in WIRES if not shapes[name].is_empty()}
            if has_root:rooted+=1
            elif wires:unrooted.append(dict(layers=sorted(wires),bounds={name:str(region.bbox()) for name,region in sorted(wires.items())}))
            else:contact_only+=1
        areas={name:region.area() for name,region in masks.items()}
        require(covered==areas,'Device-root extraction omitted conductor or endpoint area.')
        graph=dict(nets=nets,rooted_nets=rooted,contact_only_nets=contact_only,area_nm2=areas,covered_area_nm2=covered,unrooted=sorted(unrooted,key=str))
    return dict(layers=census,unsupported=unsupported,exception_labels=exceptions,poly_short_outside=short_outside,graph=graph)


def audit(path):
    import klayout.db as k
    path=Path(path);digest=file_digest(path);layout=k.Layout();layout.read(str(path))
    report=expected(measure(layout),layout.top_cell().name,digest)
    require(file_digest(path)==digest,'SKY130 layout changed during device-root checking.')
    return report


def evaluate(report,digest,top):
    require(isinstance(report,dict),'Missing SKY130 physical-device-root evidence. Recheck Finish.')
    require(report==expected(report.get('measurements'),top,digest),'Changed or incomplete SKY130 device-root evidence. Recheck Finish.')
    return report


def validate_saved(report,path):
    actual=audit(path);evaluate(report,actual['gds_sha256'],actual['top'])
    require(report==actual,'SKY130 device-root evidence differs from the actual layout. Recheck Finish.')
    return report
