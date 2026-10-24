"""Prove selected catalog limits with stricter all-geometry bounds.

A failed sufficient bound is unreviewed, not a claimed foundry-rule violation.
Present IP blockage layers also remain unreviewed; their derived routing and
hierarchy semantics are not replaced by arbitrary raw-metal comparisons.
"""
from pathlib import Path

from .model import file_digest

RECIPE='sky130-conservative-catalog-bounds-v1'
SOURCE=dict(revision='7198cf647113f56041e02abf3eb623692820c5e1',files={
    'docs/rules/errors.csv':'d613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv':'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5',
    'docs/rules/layers/table-c4b-layer-description.csv':'dcfeb27a76171a67ca6a905bdc6deab0ca4d801f5970a76b1ce90aebb97bb21f',
    'docs/rules/periphery/p028-poly_dotdash.csv':'fb9fef64f61ae37352e06f35be256735f50550325f54707d331975294824bc24',
    'docs/rules/periphery/p032-n_psd_dotdash.csv':'b3fdc0a63960d680f398d6fc43684f782b7518bd683a98f450a1d21c9c45bf58'})
LAYERS=dict(nsdm=(93,44),psdm=(94,20),poly=(66,20))
BOUNDS=dict(nsdm=dict(operation='width',nm=380),psdm=dict(operation='width',nm=380),
            poly=dict(operation='space',nm=210))
CHECKS=dict(r471=dict(rule='nsd.c1a',layer='nsdm',required_nm=380),
            r487=dict(rule='psd.c1a',layer='psdm',required_nm=380),
            r520=dict(rule='poly.c3',layer='poly',required_nm=175),
            r521=dict(rule='poly.c2',layer='poly',required_nm=160))
BLOCKS={name:dict(pair=(68+i,10),ids=tuple('r'+str(1234+3*i+j) for j in range(3)))
        for i,name in enumerate(('met1','met2','met3','met4','met5'))}
BLOCKS['li1']=dict(pair=(67,10),ids=('r1249','r1250','r1251'))
SCOPE=('Four catalog limits are satisfied only when broader drawn-geometry checks pass: all merged NSDM '
       'and PSDM widths at least 380 nm, and all merged poly spacing/notches at least 210 nm. '
       'No core-gap or opposite-parallel exception is used. A failed sufficient bound is unreviewed, '
       'not a claimed violation of the narrower foundry rule. Eighteen IP blockage obligations are '
       'absent only when their exact published block purposes contain no raw data. Present blockages '
       'remain unreviewed; generated routing operands and hierarchy semantics are not implemented. '
       'Generated masks, global grid/density and complete physical coverage remain separate.')


def require(condition,message):
    if not condition:raise ValueError(message)


def expected(measurements,top,digest):
    require(isinstance(measurements,dict) and set(measurements)=={'layers','bound_findings','blockages'},
            'Missing SKY130 conservative-bound measurements.')
    layers,findings,blocks=(measurements[k] for k in ('layers','bound_findings','blockages'))
    require(isinstance(layers,dict) and layers.keys()==LAYERS.keys() and
            isinstance(findings,dict) and findings.keys()==BOUNDS.keys() and
            isinstance(blocks,dict) and blocks.keys()==BLOCKS.keys(), 'Incomplete SKY130 conservative-bound census.')
    for name,entry in layers.items():
        require(isinstance(entry,dict) and set(entry)=={'raw_shapes','texts','components'} and
                all(type(v)is int and v>=0 for v in entry.values()) and entry['texts']<=entry['raw_shapes'] and
                (entry['components']>0)==(entry['raw_shapes']>entry['texts']) and
                (not entry['texts'] or name=='poly'), 'Invalid SKY130 conservative-bound layer counts.')
    require(all(type(n)is int and n>=0 for n in (*findings.values(),*blocks.values())),
            'Invalid SKY130 conservative-bound counts.')
    require(all(layers[name]['components'] or not findings[name] for name in findings),
            'Bound finding without geometry.')
    rows=[]
    for key,check in CHECKS.items():
        name=check['layer'];targets=layers[name]['components']
        rows.append(dict(id=key,**check,bound=BOUNDS[name],bound_findings=findings[name],
            disposition='unreviewed' if findings[name] else 'executed-reviewed' if targets else 'absent-operand'))
    for name,selection in BLOCKS.items():
        for key in selection['ids']:
            rows.append(dict(id=key,subject=name+'_block',raw_shapes=blocks[name],
                disposition='unreviewed' if blocks[name] else 'absent-operand'))
    unresolved=sum(row['disposition']=='unreviewed' for row in rows)
    return dict(schema=1,recipe=RECIPE,source=SOURCE,scope=SCOPE,qualified=False,chunk_complete=False,
                top=top,gds_sha256=digest,measurements=measurements,rows=rows,unreviewed=unresolved,
                status='review-required' if unresolved else 'conservative-bounds-and-absence-pass')


def measure(layout):
    import klayout.db as k
    require(len(layout.top_cells())==1 and abs(layout.dbu-.001)<1e-12,
            'SKY130 conservative bounds require one top and a 1 nm database unit.')
    top=layout.top_cell()
    for index in {top.cell_index(),*top.called_cells()}:
        for instance in layout.cell(index).each_inst():
            t=instance.cplx_trans
            require(t.mag==1 and t.angle%90==0, 'Unsupported SKY130 conservative-bound transform.')
    regions,census={},{}
    for name,pair in LAYERS.items():
        region=k.Region();raw=texts=0;iterator=top.begin_shapes_rec(layout.layer(*pair))
        while not iterator.at_end():
            shape=iterator.shape();raw+=1
            if shape.is_text() and name=='poly':texts+=1;iterator.next();continue
            if shape.is_path():
                path=shape.path;points=list(path.each_point())
                require(path.width>0 and path.width%2==0 and not path.is_round() and len(points)>=2 and
                        all(a!=b and (a.x==b.x or a.y==b.y) for a,b in zip(points,points[1:])),
                        'Inexact SKY130 conservative-bound path: '+name)
                polygon=path.polygon()
            else:
                require(shape.is_box() or shape.is_polygon() or shape.is_simple_polygon(),
                        'Unsupported SKY130 conservative-bound shape: '+name)
                polygon=shape.polygon
            require(polygon.area()>0 and all(e.p1.x==e.p2.x or e.p1.y==e.p2.y for e in polygon.each_edge()),
                    'SKY130 conservative bounds require nonempty Manhattan polygons: '+name)
            region.insert(polygon.transformed(iterator.trans()));iterator.next()
        regions[name]=region.merged();census[name]=dict(raw_shapes=raw,texts=texts,components=regions[name].count())
    findings={name:getattr(regions[name],bound['operation']+'_check')(bound['nm']).count() for name,bound in BOUNDS.items()}
    blocks={name:0 for name in BLOCKS}
    for name,selection in BLOCKS.items():
        iterator=top.begin_shapes_rec(layout.layer(*selection['pair']))
        while not iterator.at_end():blocks[name]+=1;iterator.next()
    return dict(layers=census,bound_findings=findings,blockages=blocks)


def audit(path):
    import klayout.db as k
    path=Path(path);digest=file_digest(path);layout=k.Layout();layout.read(str(path))
    report=expected(measure(layout),layout.top_cell().name,digest)
    require(file_digest(path)==digest,'SKY130 layout changed during conservative-bound checking.')
    return report


def evaluate(report,digest,top):
    require(isinstance(report,dict),'Missing SKY130 conservative-bound evidence. Recheck Finish.')
    require(report==expected(report.get('measurements'),top,digest),
            'Changed or incomplete SKY130 conservative-bound evidence. Recheck Finish.')
    return report


def validate_saved(report,path):
    actual=audit(path);evaluate(report,actual['gds_sha256'],actual['top'])
    require(report==actual,'SKY130 conservative-bound evidence differs from the actual layout. Recheck Finish.')
    return report
