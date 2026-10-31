"""Conservative empty-subject proofs for seven special-device records.

This report does not implement nonempty UHV or resistor rules. It also does not
substitute an absent enclosing region for an absent enclosed target. All raw
shape types and candidate names/labels prevent the relevant absence proof.
"""
from pathlib import Path

from .digital_sky130_catalog_labels import normalized
from .model import file_digest

RECIPE='sky130-special-empty-subjects-v1'
SOURCE=dict(revision='7198cf647113f56041e02abf3eb623692820c5e1',files={
    'docs/rules/errors.csv':'d613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv':'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5',
    'docs/rules/layers/table-c3-device-lvs-other.csv':'e56b7c0570f4ce5e4c0a002ddd0cc82f4c0e0d12d98a7634d419e0abd6a1fd98',
    'docs/rules/periphery/p055-uhvi_dotdash_dotdash.csv':'415c36c520c98089eb62a548cd04eecbc21338206bd85da2c0d416df9a90332f',
    'docs/rules/periphery/p055-ulvt-_dotdash.csv':'0ea62d9009cbe454ea9fc6fee57de4fb32bd26bc5bf4a5d3e492f7c2e4ee8bf5',
    'docs/rules/periphery/p029-rpm_dotdash.csv':'96f394adf42b2f023ab2a4448783b0372c97d9a05072aa41ad3a5f6b7b38491a',
    'docs/rules/periphery/p051-depmos_dotdash.csv':'5bd0eee503fee3700223eeb079d92c8b94066fd4f9f172cf2395ec1fce3ed1fc'})
LAYERS=dict(uhvi=(74,22),dnwell=(64,18),cdnm=(48,0),rpm=(86,20),urpm=(79,20),crpm=(96,0),
            poly_resistor=(66,13),areaid_en=(81,57),areaid_en20=(81,58),cnwm=(21,0))
HINTS=dict(uhvi=('uhvi','lowvtid','uhv','ulvt'),dnwell=('dnwell','dnw','deepnwell'),
           resistor=('precresistor','xhrpoly','res_high_po','res_xhigh_po','urpm','rpm'),
           extended_drain=('denmos','depmos','defet','extendeddrain'))
GROUPS=dict(
    uhvi=dict(ids=('r396','r929'),raw=('uhvi',),hints='uhvi',holes=False),
    deep_well=dict(ids=('r928',),raw=('dnwell','cdnm'),hints='dnwell',holes=False),
    resistor=dict(ids=('r1047','r1059','r1060'),raw=('rpm','urpm','crpm','poly_resistor'),hints='resistor',holes=False),
    nwell_hole=dict(ids=('r922',),raw=('cnwm','areaid_en','areaid_en20'),hints='extended_drain',holes=True))
SCOPE=('Seven catalog obligations have conservative empty-subject proofs only. An entirely absent UHVI '
       'region cannot be straddled by any selected geometry. Deep-well enclosure requires the deep-well '
       'target itself absent, including explicit mask data. Precision-resistor and RPM-selected subjects '
       'require empty RPM, URPM, CRPM and poly-resistor purposes. The nwell-hole angle subject requires '
       'no holes in the merged nwell and no explicit nwell mask or extended-drain markers. Candidate '
       'cell names or labels prevent the associated proof. Nonempty subjects stay unreviewed; source '
       'N/A values are not used as waivers. Nonempty rule meanings and complete device qualification '
       'remain separate, including the catalog/manual depmos.8 and urpm.3 naming differences.')


def require(condition,message):
    if not condition:raise ValueError(message)


def expected(measurements,top,digest):
    require(isinstance(measurements,dict) and set(measurements)=={'raw','hints','nwell'},'Missing SKY130 special-subject measurements.')
    raw,hints,nwell=(measurements[k] for k in ('raw','hints','nwell'))
    require(isinstance(raw,dict) and raw.keys()==LAYERS.keys() and all(type(v)is int and v>=0 for v in raw.values()),
            'Incomplete SKY130 special-subject raw census.')
    require(isinstance(hints,dict) and hints.keys()==HINTS.keys(),'Incomplete SKY130 special-subject intent census.')
    for row in hints.values():
        require(isinstance(row,dict) and set(row)=={'cells','labels'} and all(type(v)is int and v>=0 for v in row.values()),
                'Invalid SKY130 special-subject intent counts.')
    require(isinstance(nwell,dict) and set(nwell)=={'raw_shapes','components','area_nm2','holes'} and
            all(type(v)is int and v>=0 for v in nwell.values()) and
            (nwell['raw_shapes']>0)==(nwell['components']>0)==(nwell['area_nm2']>0) and
            (nwell['components'] or not nwell['holes']), 'Invalid SKY130 nwell-hole census.')
    rows=[]
    for subject,group in GROUPS.items():
        witnesses={name:raw[name] for name in group['raw']}
        witnesses.update({group['hints']+'_'+key:value for key,value in hints[group['hints']].items()})
        if group['holes']:witnesses['nwell_holes']=nwell['holes']
        for key in group['ids']:
            rows.append(dict(id=key,subject=subject,witnesses=witnesses,
                disposition='unreviewed' if any(witnesses.values()) else 'absent-operand'))
    unreviewed=sum(r['disposition']=='unreviewed' for r in rows)
    return dict(schema=1,recipe=RECIPE,source=SOURCE,scope=SCOPE,qualified=False,chunk_complete=False,
        top=top,gds_sha256=digest,measurements=measurements,rows=rows,unreviewed=unreviewed,
        status='review-required' if unreviewed else 'special-subject-absence-reviewed')


def measure(layout):
    import klayout.db as k
    require(len(layout.top_cells())==1 and abs(layout.dbu-.001)<1e-12,
            'SKY130 special-subject checks require one top and a 1 nm database unit.')
    top=layout.top_cell();cells={top.cell_index(),*top.called_cells()};hints={key:dict(cells=0,labels=0) for key in HINTS}
    for index in cells:
        cell=layout.cell(index)
        for key,tokens in HINTS.items():hints[key]['cells']+=int(any(t in normalized(cell.name) for t in tokens))
        for instance in cell.each_inst():
            t=instance.cplx_trans;require(t.mag==1 and t.angle%90==0,'Unsupported SKY130 special-subject transform.')
    raw={}
    for name,pair in LAYERS.items():
        count=0;iterator=top.begin_shapes_rec(layout.layer(*pair))
        while not iterator.at_end():count+=1;iterator.next()
        raw[name]=count
    for index in layout.layer_indexes():
        iterator=top.begin_shapes_rec(index);iterator.shape_flags=k.Shapes.STexts
        while not iterator.at_end():
            value=normalized(iterator.shape().text.string)
            for key,tokens in HINTS.items():hints[key]['labels']+=int(any(t in value for t in tokens))
            iterator.next()
    region=k.Region();count=0;iterator=top.begin_shapes_rec(layout.layer(64,20))
    while not iterator.at_end():
        shape=iterator.shape();count+=1
        if shape.is_path():
            path=shape.path;points=list(path.each_point())
            require(path.width>0 and path.width%2==0 and not path.is_round() and len(points)>=2 and
                    all(a!=b and (a.x==b.x or a.y==b.y) for a,b in zip(points,points[1:])), 'Inexact SKY130 nwell path.')
            polygon=path.polygon()
        else:
            require(shape.is_box() or shape.is_polygon() or shape.is_simple_polygon(),'Unsupported SKY130 nwell-hole shape.')
            polygon=shape.polygon
        require(polygon.area()>0 and all(e.p1.x==e.p2.x or e.p1.y==e.p2.y for e in polygon.each_edge()),
                'SKY130 nwell-hole checks require nonempty Manhattan polygons.')
        region.insert(polygon.transformed(iterator.trans()));iterator.next()
    region.merge()
    return dict(raw=raw,hints=hints,nwell=dict(raw_shapes=count,components=region.count(),area_nm2=region.area(),holes=region.holes().count()))


def audit(path):
    import klayout.db as k
    path=Path(path);digest=file_digest(path);layout=k.Layout();layout.read(str(path))
    report=expected(measure(layout),layout.top_cell().name,digest)
    require(file_digest(path)==digest,'SKY130 layout changed during special-subject checking.')
    return report


def evaluate(report,digest,top):
    require(isinstance(report,dict),'Missing SKY130 special-subject evidence. Recheck Finish.')
    require(report==expected(report.get('measurements'),top,digest),'Changed or incomplete SKY130 special-subject evidence. Recheck Finish.')
    return report


def validate_saved(report,path):
    actual=audit(path);evaluate(report,actual['gds_sha256'],actual['top'])
    require(report==actual,'SKY130 special-subject evidence differs from the actual layout. Recheck Finish.')
    return report
