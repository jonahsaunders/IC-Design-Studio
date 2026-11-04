"""Global sufficient size bounds for fourteen drawn-layer scribe restrictions.

Every complete connected feature must have a bounding-box side below 10 um.
This proves that no 10-by-10 um feature exists anywhere, independently of the
unknown junction locations. A larger box is a candidate, not a violation.
"""
from pathlib import Path
from .model import file_digest

RECIPE='sky130-drawn-scribe-size-bounds-v1'
SOURCE=dict(revision='7198cf647113f56041e02abf3eb623692820c5e1',files={
    'docs/rules/errors.csv':'d613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv':'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5'})
LAYERS=dict(diff=(65,20),poly=(66,20),li1=(67,20),met1=(68,20),met2=(69,20),met3=(70,20),
    mcon=(67,44),licon1=(66,44),via=(68,44),via2=(69,44),met4=(71,20),met5=(72,20),via3=(70,44),via4=(71,44))
TEXT_LAYERS=('diff','poly','li1','met1','met2','met3','met4','met5')
LIMIT_NM=10000
CHECKS={'r'+str(i):dict(rule='scribe.5',target=name,limit_nm=LIMIT_NM,junction_distance_nm=150000)
        for i,name in enumerate(LAYERS,1376)}
SCOPE=('Fourteen drawn-layer scribe.5 records use a global sufficient size bound. After flattening '
    'reachable hierarchy and merging all touching/overlapping fragments, every connected feature '
    'must have at least one bounding-box side strictly below 10000 nm. Such a feature cannot contain '
    'a 10-by-10 um region at any location or orientation, so none can occur within 150 um of any scribe '
    'junction. A feature at exactly 10000 nm on both sides is a candidate. Large boxes, including '
    'thin L shapes and rings, stay unreviewed: bounding-box size does not prove a wide region or '
    'a nearby junction. No junction, frame, die or chip boundary is inferred. Empty drawing geometry '
    'is recorded separately. Generated-mask companion records and complete scribe context remain '
    'unreviewed; this report does not establish full physical coverage or process qualification.')


def require(condition,message):
    if not condition:raise ValueError(message)


def expected(measurements,top,digest):
    require(isinstance(measurements,dict) and measurements.keys()==LAYERS.keys(),
            'Missing SKY130 scribe-size measurements.')
    rows=[]
    for key,check in CHECKS.items():
        name=check['target'];v=measurements[name]
        require(isinstance(v,dict) and set(v)=={'raw_shapes','texts','components','area_nm2','candidates','max_short_span_nm'}
            and all(type(n)is int and n>=0 for n in v.values()) and v['texts']<=v['raw_shapes']
            and (v['raw_shapes']>v['texts'])==(v['components']>0)==(v['area_nm2']>0)==(v['max_short_span_nm']>0)
            and (v['texts']==0 or name in TEXT_LAYERS) and v['candidates']<=v['components']
            and (v['candidates']>0)==(v['max_short_span_nm']>=LIMIT_NM),
            'Invalid SKY130 scribe-size census: '+name)
        disposition='absent-operand' if not v['components'] else 'unreviewed' if v['candidates'] else 'executed-reviewed'
        reason='empty-drawing' if not v['components'] else 'wide-candidate-needs-context' if v['candidates'] else 'global-size-bound-proven'
        rows.append(dict(id=key,**check,components=v['components'],candidates=v['candidates'],
            max_short_span_nm=v['max_short_span_nm'],disposition=disposition,reason=reason))
    pending=sum(r['disposition']=='unreviewed' for r in rows)
    return dict(schema=1,recipe=RECIPE,source=SOURCE,scope=SCOPE,qualified=False,chunk_complete=False,
        top=top,gds_sha256=digest,measurements=measurements,rows=rows,unreviewed=pending,
        status='review-required' if pending else 'drawn-scribe-size-bounds-reviewed')


def measure(layout):
    import klayout.db as k
    require(len(layout.top_cells())==1 and abs(layout.dbu-.001)<1e-12,
            'SKY130 scribe-size bounds require one top and a 1 nm database unit.')
    top=layout.top_cell()
    for index in {top.cell_index(),*top.called_cells()}:
        for instance in layout.cell(index).each_inst():
            t=instance.cplx_trans
            require(t.mag==1 and t.angle%90==0,'Unsupported SKY130 scribe-size transform.')
    census={}
    for name,pair in LAYERS.items():
        region=k.Region();raw=texts=0;it=top.begin_shapes_rec(layout.layer(*pair))
        while not it.at_end():
            shape=it.shape();raw+=1
            if shape.is_text() and name in TEXT_LAYERS:texts+=1;it.next();continue
            if shape.is_path():
                path=shape.path;points=list(path.each_point())
                require(path.width>0 and path.width%2==0 and not path.is_round() and len(points)>=2 and
                    all(a!=b and (a.x==b.x or a.y==b.y) for a,b in zip(points,points[1:])),
                    'Inexact SKY130 scribe-size path: '+name)
                polygon=path.polygon()
            else:
                require(shape.is_box() or shape.is_polygon() or shape.is_simple_polygon(),
                        'Unsupported SKY130 scribe-size shape: '+name)
                polygon=shape.polygon
            require(polygon.area()>0 and all(e.p1.x==e.p2.x or e.p1.y==e.p2.y for e in polygon.each_edge()),
                    'SKY130 scribe-size bounds require nonempty Manhattan geometry: '+name)
            region.insert(polygon.transformed(it.trans()));it.next()
        # Maximum coherence conservatively keeps corner-touching fragments in
        # one feature. No per-cell boundary can split a physical feature.
        region.min_coherence=False;region.merge();candidates=maximum=0
        for polygon in region.each():
            box=polygon.bbox();span=min(box.width(),box.height())
            candidates+=int(span>=LIMIT_NM);maximum=max(maximum,span)
        census[name]=dict(raw_shapes=raw,texts=texts,components=region.count(),area_nm2=region.area(),
                          candidates=candidates,max_short_span_nm=maximum)
    return census


def audit(path):
    import klayout.db as k
    path=Path(path);digest=file_digest(path);layout=k.Layout();layout.read(str(path))
    report=expected(measure(layout),layout.top_cell().name,digest)
    require(file_digest(path)==digest,'Layout changed during scribe-size audit.')
    return report


def evaluate(report,digest,top):
    require(isinstance(report,dict),'Missing SKY130 scribe-size evidence. Recheck Finish.')
    require(report==expected(report.get('measurements'),top,digest),'Changed SKY130 scribe-size evidence. Recheck Finish.')
    return report


def validate_saved(report,path):
    actual=audit(path);evaluate(report,actual['gds_sha256'],actual['top'])
    require(report==actual,'SKY130 scribe-size evidence differs from the actual layout. Recheck Finish.')
    return report
