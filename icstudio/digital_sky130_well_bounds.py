"""Sufficient drawn-well bounds for three published SKY130 error records.

Whole drawn operands deliberately overapproximate the selected UHV operands.
A failed bound needs review; it is not reported as a foundry rule violation.
"""
from pathlib import Path
from .model import file_digest

RECIPE='sky130-drawn-well-bounds-v1'
SOURCE=dict(revision='7198cf647113f56041e02abf3eb623692820c5e1',files={
    'docs/rules/errors.csv':'d613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv':'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5',
    'docs/rules/periphery/p022-pwdem_dotdash.csv':'463bfebfd5b9cf00cc02776b9e73f29e5507b83621c0c78ef3b302ca4b97ae13',
    'docs/rules/periphery/p022-pwbm_dotdash.csv':'783146a0a77fd96e198d31c1ff5775f093a264510ae03e609d40934fe0416aa2',
    'docs/rules/periphery/p055-uhvi_dotdash_dotdash.csv':'415c36c520c98089eb62a548cd04eecbc21338206bd85da2c0d416df9a90332f'})
LAYERS=dict(pwde=(124,20),pwbm=(19,44),dnwell=(64,18),uhvi=(74,22))
CHECKS={
    'r923':dict(rule='pwde.6',target='pwde',operation='enclosure',limit_nm=1000),
    'r924':dict(rule='pwbm.5',target='pwbm_holes',operation='spacing',limit_nm=840),
    'r931':dict(rule='uhvi.3',target='pwbm',operation='enclosure',limit_nm=0)}
SCOPE=('Three drawn-well sufficient bounds use the finite error-catalog requirements; the manual N/A '
    'entries are not waivers. All drawn PWDE expanded by a 1000 nm square must fit within both DNWELL '
    'and UHVI. Every pair of holes in the fully merged drawn PWBM must be at least 840 nm apart in '
    'the square metric. Holes are collected before any UHVI selection, so clipping cannot manufacture '
    'new holes. Hole hulls include nested islands conservatively. All drawn PWBM must lie within UHVI, '
    'without applying the LOWVTID exception. Equality passes; missing enclosing geometry cannot waive '
    'a nonempty target. A failed stronger bound stays unreviewed, not a foundry violation. Empty targets '
    'and fewer than two holes are separate absent-operand decisions. These checks do not establish '
    'device completeness, full-chip context, generated-mask equivalence or process qualification.')


def require(condition,message):
    if not condition:raise ValueError(message)


def expected(measurements,top,digest):
    require(isinstance(measurements,dict) and set(measurements)=={'layers','holes','bounds'},
            'Missing SKY130 well-bound measurements.')
    layers,holes,bounds=(measurements[n] for n in ('layers','holes','bounds'))
    require(isinstance(layers,dict) and layers.keys()==LAYERS.keys() and
            isinstance(bounds,dict) and bounds.keys()==CHECKS.keys(),'Incomplete SKY130 well-bound census.')
    for values in layers.values():
        require(isinstance(values,dict) and set(values)=={'raw_shapes','components','area_nm2'} and
            all(type(v)is int and v>=0 for v in values.values()) and
            (values['raw_shapes']>0)==(values['components']>0)==(values['area_nm2']>0),
            'Invalid SKY130 well-bound layer census.')
    require(type(holes)is int and holes>=0 and (layers['pwbm']['components'] or not holes),
            'Invalid SKY130 well-bound hole census.')
    rows=[]
    for key,check in CHECKS.items():
        targets=holes*(holes-1)//2 if key=='r924' else layers[check['target']]['components']
        witness=bounds[key]
        require(type(witness)is int and witness>=0 and (targets or witness==0),
                'Invalid SKY130 well-bound witness area.')
        disposition='absent-operand' if not targets else 'unreviewed' if witness else 'executed-reviewed'
        reason='empty-target' if not targets else 'sufficient-bound-not-proven' if witness else 'sufficient-bound-proven'
        rows.append(dict(id=key,**check,target_count=targets,witness_area_nm2=witness,
                         disposition=disposition,reason=reason))
    pending=sum(r['disposition']=='unreviewed' for r in rows)
    return dict(schema=1,recipe=RECIPE,source=SOURCE,scope=SCOPE,qualified=False,chunk_complete=False,
        top=top,gds_sha256=digest,measurements=measurements,rows=rows,unreviewed=pending,
        status='review-required' if pending else 'selected-well-bounds-reviewed')


def measure(layout):
    import klayout.db as k
    require(len(layout.top_cells())==1 and abs(layout.dbu-.001)<1e-12,
            'SKY130 well bounds require one top and a 1 nm database unit.')
    top=layout.top_cell()
    for index in {top.cell_index(),*top.called_cells()}:
        for instance in layout.cell(index).each_inst():
            t=instance.cplx_trans
            require(t.mag==1 and t.angle%90==0,'Unsupported SKY130 well-bound transform.')
    regions={};census={}
    for name,pair in LAYERS.items():
        region=k.Region();raw=0;it=top.begin_shapes_rec(layout.layer(*pair))
        while not it.at_end():
            shape=it.shape();raw+=1
            if shape.is_path():
                path=shape.path;points=list(path.each_point())
                require(path.width>0 and path.width%2==0 and not path.is_round() and len(points)>=2 and
                    all(a!=b and (a.x==b.x or a.y==b.y) for a,b in zip(points,points[1:])),
                    'Inexact SKY130 well-bound path: '+name)
                polygon=path.polygon()
            else:
                require(shape.is_box() or shape.is_polygon() or shape.is_simple_polygon(),
                        'Unsupported SKY130 well-bound shape: '+name)
                polygon=shape.polygon
            require(polygon.area()>0 and all(e.p1.x==e.p2.x or e.p1.y==e.p2.y for e in polygon.each_edge()),
                    'SKY130 well bounds require nonempty Manhattan geometry: '+name)
            region.insert(polygon.transformed(it.trans()));it.next()
        region.merge();regions[name]=region
        census[name]=dict(raw_shapes=raw,components=region.count(),area_nm2=region.area())
    # Each original hole is a connected absent region. Filling islands inside a
    # hole enlarges that operand and can only make the spacing bound stricter.
    holes=[k.Region(k.Polygon(list(p.each_point_hole(i))))
           for p in regions['pwbm'].each() for i in range(p.holes())]
    expanded=k.Region();spacing=0
    for hole in holes:
        grown=hole.minkowski_sum(k.Box(-420,-420,420,420)).merged()
        spacing+=(grown&expanded).area()
        expanded=(expanded|grown).merged()
    pwde=regions['pwde'].minkowski_sum(k.Box(-1000,-1000,1000,1000)).merged()
    return dict(layers=census,holes=len(holes),bounds={
        'r923':(pwde-(regions['dnwell']&regions['uhvi'])).area(),
        'r924':spacing,'r931':(regions['pwbm']-regions['uhvi']).area()})


def audit(path):
    import klayout.db as k
    path=Path(path);digest=file_digest(path);layout=k.Layout();layout.read(str(path))
    report=expected(measure(layout),layout.top_cell().name,digest)
    require(file_digest(path)==digest,'Layout changed during well-bound audit.')
    return report


def evaluate(report,digest,top):
    require(isinstance(report,dict),'Missing SKY130 well-bound evidence. Recheck Finish.')
    require(report==expected(report.get('measurements'),top,digest),'Changed SKY130 well-bound evidence. Recheck Finish.')
    return report


def validate_saved(report,path):
    actual=audit(path);evaluate(report,actual['gds_sha256'],actual['top'])
    require(report==actual,'SKY130 well-bound evidence differs from the actual layout. Recheck Finish.')
    return report
