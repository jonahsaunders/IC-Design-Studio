"""Global sufficient bounds for three under-pad metal maximum-width records."""
from pathlib import Path
from .model import file_digest

RECIPE='sky130-metal-maximum-width-bounds-v1'
SOURCE=dict(revision='7198cf647113f56041e02abf3eb623692820c5e1',files={
    'docs/rules/errors.csv':'d613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv':'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5'},
    layer_map=dict(path='docs/qualification/sky130-layer-purposes.json',
        sha256='3ccb42d63e7bbbe0c793c4541cc51c979c914588089793ab144c36fff3d673fb'),
    native=dict(path='tests/fixtures/sky130-metal-width-native.tech',
        sha256='5ee53b96094fe144145bf1216627672747366ec9bef9f2f848304a9a0c77427e'))
ANNOTATIONS=(0,5,16)
OTHER_METAL_PURPOSES=(4,10,13,14,15,23,25,*range(32,40),*range(88,94))
LAYERS=dict(
    met1=dict(drawing=(68,20),fill=(36,28),guards=((36,0),(62,20),(62,21),(62,22),(62,24))),
    met2=dict(drawing=(69,20),fill=(41,28),guards=((41,0),(105,42),(105,43),(105,44),(105,52))),
    met3=dict(drawing=(70,20),fill=(34,28),guards=((34,0),(107,20),(107,21),(107,22),(107,24))))
for name,layer in LAYERS.items():
    extra=((70,17),) if name=='met3' else ()
    layer['guards']=tuple(sorted(layer['guards']+tuple((layer['drawing'][0],d) for d in OTHER_METAL_PURPOSES)+extra))
CHECKS={key:dict(rule='pad.19',target=name,limit_nm=limit) for key,name,limit in
        (('r1340','met1',25000),('r1341','met2',25000),('r1342','met3',6000))}
SCOPE=('Three pad.19 records use a stronger global maximum-width bound. Each complete connected '
    'drawn-plus-native-fill metal component must fit in a strip no wider than 25 um for met1/met2 '
    'or 6 um for met3, measured as the shorter side of its axis-aligned bounding box. '
    'A subset selected beneath a pad cannot have greater local thickness than its containing strip. '
    'No pad selector, clipping boundary or local feature exemption is needed for a passing bound. '
    'Drawing and fill are unioned across the full reachable hierarchy before measuring; touching '
    'fragments cannot be checked separately. Explicit mask/edit and alternate metal-purpose data '
    'prevent promotion because their effect on the final conductor is not established here. '
    'At the exact maximum the bound passes. A larger box, including a thin L or ring, remains '
    'unreviewed rather than being called a pad-rule violation. Other under-pad spacing, minimum '
    'width, pad construction and generated-mask requirements remain separate.')


def require(condition,message):
    if not condition:raise ValueError(message)


def expected(measurements,top,digest):
    require(isinstance(measurements,dict) and measurements.keys()==LAYERS.keys(),'Missing metal-width measurements.')
    rows=[]
    for key,check in CHECKS.items():
        name=check['target'];value=measurements[name];layer=LAYERS[name]
        require(isinstance(value,dict) and set(value)=={'inputs','guards','components','area_nm2','candidates','max_short_span_nm'},
                'Incomplete metal-width census.')
        inputs=value['inputs'];guards=value['guards']
        require(isinstance(inputs,dict) and set(inputs)=={'drawing','fill'} and isinstance(guards,dict) and
                set(guards)=={'%s:%s'%p for p in layer['guards']} and
                all(type(n)is int and n>=0 for n in guards.values()),'Invalid metal-width input census.')
        for data in inputs.values():
            require(isinstance(data,dict) and set(data)=={'raw_shapes','texts','area_nm2'} and
                all(type(n)is int and n>=0 for n in data.values()) and data['texts']<=data['raw_shapes'] and
                (data['raw_shapes']>data['texts'])==(data['area_nm2']>0),'Invalid drawn/fill census.')
        require(all(type(value[n])is int and value[n]>=0 for n in ('components','area_nm2','candidates','max_short_span_nm')) and
                value['candidates']<=value['components'] and
                (value['candidates']>0)==(value['max_short_span_nm']>check['limit_nm']) and
                (value['components']>0)==(value['area_nm2']>0)==(value['max_short_span_nm']>0)==any(d['area_nm2'] for d in inputs.values()) and
                max(d['area_nm2'] for d in inputs.values())<=value['area_nm2']<=sum(d['area_nm2'] for d in inputs.values()),
                'Inconsistent global metal-width measurements.')
        unsupported=sum(guards.values())
        disposition=('unreviewed' if unsupported or value['candidates'] else
                     'executed-reviewed' if value['components'] else 'absent-operand')
        reason=('unsupported-metal-purpose' if unsupported else 'bound-needs-pad-context' if value['candidates'] else
                'global-maximum-width-proven' if value['components'] else 'empty-metal')
        rows.append(dict(id=key,**check,disposition=disposition,reason=reason,unsupported_raw_shapes=unsupported,
            components=value['components'],candidates=value['candidates'],max_short_span_nm=value['max_short_span_nm']))
    pending=sum(r['disposition']=='unreviewed' for r in rows)
    return dict(schema=1,recipe=RECIPE,source=SOURCE,scope=SCOPE,qualified=False,chunk_complete=False,
        top=top,gds_sha256=digest,measurements=measurements,rows=rows,unreviewed=pending,
        status='review-required' if pending else 'global-metal-maximum-width-reviewed')


def measure(layout):
    import klayout.db as k
    require(len(layout.top_cells())==1 and abs(layout.dbu-.001)<1e-12,'Metal-width bounds require one top and a 1 nm database unit.')
    top=layout.top_cell()
    for index in {top.cell_index(),*top.called_cells()}:
        for instance in layout.cell(index).each_inst():
            t=instance.cplx_trans
            require(t.mag==1 and t.angle%90==0,'Unsupported metal-width transform.')
    result={}
    for name,layer in LAYERS.items():
        combined=k.Region();inputs={};guards={}
        for source in ('drawing','fill'):
            region=k.Region();raw=texts=0;it=top.begin_shapes_rec(layout.layer(*layer[source]))
            while not it.at_end():
                shape=it.shape();raw+=1
                if shape.is_text():texts+=1;it.next();continue
                if shape.is_path():
                    path=shape.path;points=list(path.each_point())
                    require(path.width>0 and path.width%2==0 and not path.is_round() and len(points)>=2 and
                        all(a!=b and (a.x==b.x or a.y==b.y) for a,b in zip(points,points[1:])), 'Inexact metal-width path.')
                    polygon=path.polygon()
                else:
                    require(shape.is_box() or shape.is_polygon() or shape.is_simple_polygon(),'Unsupported metal-width shape.')
                    polygon=shape.polygon
                require(polygon.area()>0 and all(e.p1.x==e.p2.x or e.p1.y==e.p2.y for e in polygon.each_edge()),
                        'Metal-width bounds require nonempty Manhattan geometry.')
                region.insert(polygon.transformed(it.trans()));it.next()
            region.merge();inputs[source]=dict(raw_shapes=raw,texts=texts,area_nm2=region.area());combined+=region
        for pair in layer['guards']:
            count=0;it=top.begin_shapes_rec(layout.layer(*pair))
            while not it.at_end():count+=1;it.next()
            guards['%s:%s'%pair]=count
        combined.min_coherence=False;combined.merge()
        limit=next(r['limit_nm'] for r in CHECKS.values() if r['target']==name)
        spans=[min(p.bbox().width(),p.bbox().height()) for p in combined.each()]
        result[name]=dict(inputs=inputs,guards=guards,components=combined.count(),area_nm2=combined.area(),
            candidates=sum(n>limit for n in spans),max_short_span_nm=max(spans,default=0))
    return result


def audit(path):
    import klayout.db as k
    path=Path(path);digest=file_digest(path);layout=k.Layout();layout.read(str(path))
    result=expected(measure(layout),layout.top_cell().name,digest)
    require(file_digest(path)==digest,'Layout changed during metal-width checking.')
    return result


def evaluate(report,digest,top):
    require(isinstance(report,dict),'Missing metal-width evidence. Recheck Finish.')
    require(report==expected(report.get('measurements'),top,digest),'Changed metal-width evidence. Recheck Finish.')
    return report


def validate_saved(report,path):
    actual=audit(path);evaluate(report,actual['gds_sha256'],actual['top'])
    require(report==actual,'Metal-width evidence differs from the actual layout. Recheck Finish.')
    return report
