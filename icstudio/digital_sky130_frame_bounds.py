"""Conservative 3 um bounds for nine drawn layers at explicit frame/die markers.

A failed sufficient bound is unresolved, not a foundry violation: no blanking
or named-cell exemption is applied, and the square distance metric is stronger
than Euclidean distance at corners. Missing context cannot prove enclosure.
"""
from pathlib import Path
from .model import file_digest

RECIPE='sky130-drawn-frame-bounds-v1'
SOURCE=dict(revision='7198cf647113f56041e02abf3eb623692820c5e1',files={
    'docs/rules/errors.csv':'d613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv':'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5',
    'docs/rules/periphery/p043-nsm_dotdash.csv':'232fb1afb91d400f6bbaea0ee52b39a22e831e0668b87b439edef759d1c6942c',
    'docs/rules/layers/table-c4b-layer-description.csv':'dcfeb27a76171a67ca6a905bdc6deab0ca4d801f5970a76b1ce90aebb97bb21f'})
LAYERS=dict(diff=(65,20),tap=(65,44),poly=(66,20),li1=(67,20),met1=(68,20),
            met2=(69,20),met3=(70,20),met4=(71,20),met5=(72,20))
BOUNDARIES=dict(frame=(81,12),die=(81,11))
IDS=(988,989,992,994,996,998,1000,1002,1004)
CHECKS={}
for name,index in zip(LAYERS,IDS):
    CHECKS['r'+str(index)]=dict(rule='nsm.3a',target=name,boundary='frame',operation='enclosure',limit_nm=3000)
    CHECKS['r'+str(index+18)]=dict(rule='nsm.3b',target=name,boundary='die',operation='spacing',limit_nm=3000)
SCOPE=('Eighteen exact drawn-layer frame records use a sufficient 3000 nm square-margin proof. '
    'The complete target union expanded by [-3000,3000] in both coordinates must fit within supplied '
    'areaid.ft for enclosure, or have zero positive-area overlap with supplied areaid.dt for spacing. '
    'Equality passes. No blanking or named-cell exception is applied. A failed square bound is unreviewed, '
    'not a foundry violation. Missing boundary context leaves a nonempty target unreviewed. Empty targets '
    'are recorded separately. Supplied markers do not establish complete-chip context. Generated masks, '
    'dummy diffusion, frame completeness and all other requirements remain separate.')


def require(condition,message):
    if not condition:raise ValueError(message)


def expected(measurements,top,digest):
    require(isinstance(measurements,dict) and set(measurements)=={'layers','bounds'},'Missing SKY130 frame-bound measurements.')
    layers,bounds=measurements['layers'],measurements['bounds']
    require(isinstance(layers,dict) and layers.keys()==(LAYERS|BOUNDARIES).keys() and
            isinstance(bounds,dict) and bounds.keys()==CHECKS.keys(),'Incomplete SKY130 frame-bound census.')
    for name,values in layers.items():
        require(isinstance(values,dict) and set(values)=={'raw_shapes','texts','components','area_nm2'} and
            all(type(v)is int and v>=0 for v in values.values()) and values['texts']<=values['raw_shapes'] and
            (values['raw_shapes']>values['texts'])==(values['components']>0)==(values['area_nm2']>0) and
            (values['texts']==0 or name in LAYERS and name!='tap'),'Invalid SKY130 frame-bound geometry census.')
    rows=[]
    for key,check in CHECKS.items():
        value=bounds[key];target=layers[check['target']]['components'];context=layers[check['boundary']]['components']
        require(isinstance(value,dict) and set(value)=={'evaluated','witness_area_nm2'} and
            type(value['evaluated'])is bool and value['evaluated']==bool(context),'Changed frame-bound execution state.')
        witness=value['witness_area_nm2']
        require((not context and witness is None) or
                (bool(context) and type(witness)is int and witness>=0 and (target>0 or witness==0)),
                'Invalid frame-bound witness area.')
        disposition=('absent-operand' if not target else 'unreviewed' if not context or witness else 'executed-reviewed')
        reason=('empty-target' if not target else 'missing-boundary-context' if not context else
                'sufficient-bound-not-proven' if witness else 'sufficient-bound-proven')
        rows.append(dict(id=key,**check,target_components=target,boundary_components=context,
            **value,disposition=disposition,reason=reason))
    pending=sum(r['disposition']=='unreviewed' for r in rows)
    return dict(schema=1,recipe=RECIPE,source=SOURCE,scope=SCOPE,qualified=False,chunk_complete=False,
        top=top,gds_sha256=digest,measurements=measurements,rows=rows,unreviewed=pending,
        status='review-required' if pending else 'selected-frame-bounds-reviewed')


def measure(layout):
    import klayout.db as k
    require(len(layout.top_cells())==1 and abs(layout.dbu-.001)<1e-12,
            'SKY130 frame bounds require one top and a 1 nm database unit.')
    top=layout.top_cell()
    for index in {top.cell_index(),*top.called_cells()}:
        for instance in layout.cell(index).each_inst():
            t=instance.cplx_trans
            require(t.mag==1 and t.angle%90==0,'Unsupported SKY130 frame-bound transform.')
    regions={};census={}
    for name,pair in (LAYERS|BOUNDARIES).items():
        region=k.Region();raw=texts=0;it=top.begin_shapes_rec(layout.layer(*pair))
        while not it.at_end():
            shape=it.shape();raw+=1
            if shape.is_text() and name in LAYERS and name!='tap':texts+=1;it.next();continue
            if shape.is_path():
                path=shape.path;points=list(path.each_point())
                require(path.width>0 and path.width%2==0 and not path.is_round() and len(points)>=2 and
                    all(a!=b and (a.x==b.x or a.y==b.y) for a,b in zip(points,points[1:])),
                    'Inexact SKY130 frame-bound path: '+name)
                polygon=path.polygon()
            else:
                require(shape.is_box() or shape.is_polygon() or shape.is_simple_polygon(),
                        'Unsupported SKY130 frame-bound shape: '+name)
                polygon=shape.polygon
            require(polygon.area()>0 and all(e.p1.x==e.p2.x or e.p1.y==e.p2.y for e in polygon.each_edge()),
                    'SKY130 frame bounds require nonempty Manhattan geometry: '+name)
            polygon=polygon.transformed(it.trans())
            if name in BOUNDARIES:
                require(region.interacting(k.Region(polygon)).is_empty(),
                        'Touching or overlapping SKY130 frame/die markers require review: '+name)
            region.insert(polygon);it.next()
        region.merge();regions[name]=region
        census[name]=dict(raw_shapes=raw,texts=texts,components=region.count(),area_nm2=region.area())
    # Minkowski sum with a square is explicit L-infinity dilation; it does not
    # depend on corner-cutoff or default-distance settings in a DRC operation.
    expanded={name:region.minkowski_sum(k.Box(-3000,-3000,3000,3000)).merged()
              for name,region in regions.items() if name in LAYERS} if any(not regions[n].is_empty() for n in BOUNDARIES) else {}
    bounds={}
    for key,check in CHECKS.items():
        boundary=regions[check['boundary']];evaluated=not boundary.is_empty();area=None
        if evaluated:
            target=expanded[check['target']]
            area=(target-boundary if check['operation']=='enclosure' else target&boundary).area()
        bounds[key]=dict(evaluated=evaluated,witness_area_nm2=area)
    return dict(layers=census,bounds=bounds)


def audit(path):
    import klayout.db as k
    path=Path(path);digest=file_digest(path);layout=k.Layout();layout.read(str(path))
    report=expected(measure(layout),layout.top_cell().name,digest)
    require(file_digest(path)==digest,'Layout changed during frame-bound audit.')
    return report


def evaluate(report,digest,top):
    require(isinstance(report,dict),'Missing SKY130 frame-bound evidence. Recheck Finish.')
    require(report==expected(report.get('measurements'),top,digest),'Changed SKY130 frame-bound evidence. Recheck Finish.')
    return report


def validate_saved(report,path):
    actual=audit(path);evaluate(report,actual['gds_sha256'],actual['top'])
    require(report==actual,'SKY130 frame-bound evidence differs from the actual layout. Recheck Finish.')
    return report
