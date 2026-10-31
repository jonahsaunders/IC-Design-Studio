"""Prove explicit pad/inductor and two implant targets absent, conservatively.

These are empty-target proofs, not implementations of nonempty pad or implant
rules. Missing enclosing metal or implant never establishes an empty target.
"""
from pathlib import Path
import re
from .digital_sky130_catalog_labels import normalized
from .model import file_digest

RECIPE = 'sky130-selected-empty-targets-v2'
SOURCE = dict(revision='7198cf647113f56041e02abf3eb623692820c5e1', files={
    'docs/rules/errors.csv':'d613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv':'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5',
    'docs/rules/layers/table-c3-device-lvs-other.csv':'e56b7c0570f4ce5e4c0a002ddd0cc82f4c0e0d12d98a7634d419e0abd6a1fd98',
    'docs/rules/layers/table-f2a-lvs-key.rst':'0eec9055cef67032ddfc197a5c2cc754098956174340dcc1e82c82275a3dc760'},
    device_table=dict(path='docs/qualification/sky130-device-tables/table-f2a-lvs.tsv',
        sha256='c19398018c0f45674c7162077af48c57f5113617691cb985b7985f7e362de3e3'))
LAYERS = dict(pad=(76,20), pad_pin=(76,16), pad_label=(76,5), pad_legacy_pin=(76,0),
    cpdm=(37,0), pad_center=(81,20), pad_frame=(81,3),
    inductor=(82,24), inductor_label=(82,25), inductor_terminal1=(82,26),
    inductor_terminal2=(82,27), inductor_terminal3=(82,28),
    cp1m=(28,0), cfom=(23,0), cfom_drawing=(22,20),
    hvi=(75,20), hvntm=(125,20), chvntm=(39,0), chvntm_drawing=(38,20),
    clvom=(46,0), clvom_drawing=(45,20), uhvi=(74,22), vhvi=(74,21),
    areaid_hl=(81,63), diff_hv=(65,8))
HINTS = dict(bond_pad=('pad','padpl','padcenter','padframe','padcell','padring','pads','padopening','bond'), inductor=('inductor','xind','balun'),
             varactor=('varactor','varac','varn','varp'), high_voltage=('hv','highvoltage'))
GROUPS = dict(
    bond_pad=dict(ids=tuple('r'+str(n) for n in (*range(1326,1332),1362)),
        raw=('pad','pad_pin','pad_label','pad_legacy_pin','cpdm','pad_center','pad_frame'), hints='bond_pad'),
    inductor=dict(ids=tuple('r'+str(n) for n in range(1369,1376)),
        raw=('inductor','inductor_label','inductor_terminal1','inductor_terminal2','inductor_terminal3'), hints='inductor'),
    varactor_well=dict(ids=('r1476',), raw=('cp1m','cfom','cfom_drawing'), hints='varactor'),
    high_voltage_diff=dict(ids=('r1493',),
        raw=('hvi','hvntm','chvntm','chvntm_drawing','clvom','clvom_drawing','uhvi','vhvi','areaid_hl','diff_hv'), hints='high_voltage'))
SCOPE = ('Sixteen exact catalog targets have conservative absence proofs. BondPad is a subset of '
    'pad:drawing under the published C3 definition; the complete drawing and additional pad/mask/intent '
    'guards must be empty. The generic pad name must end before another ASCII letter; explicit '
    'pad compounds and bond names retain substring matching. These name hints supplement the '
    'mandatory raw drawing checks and do not recognize devices by name alone. '
    'Every captured inductor family requires the inductor drawing identifier; '
    'all identifier/terminal/label data and candidate names must be absent. For r1476, empty poly AND '
    'tap implies empty Var_channel and therefore an empty selected well target. For r1493, an absent '
    'HVI region makes ndiff inside HVI empty, with additional voltage/mask/intent guards. Missing '
    'enclosing metal or implant is never an absence proof. Nonempty or ambiguous targets remain '
    'unreviewed. ViaTop, hugePad, other pad variants, generated-mask recipes and device qualification '
    'remain separate; no nonempty numerical rule execution is claimed.')


def require(condition, message):
    if not condition: raise ValueError(message)


def hint_matches(text, tokens):
    value=normalized(text)
    # A bus such as paddr is not a pad token. Preserve embedded, numbered and
    # separated pad names, plus the explicitly listed compound pad names.
    return any(bool(re.search(r'pad(?![a-z])',value)) if token=='pad' else token in value
               for token in tokens)


def expected(measurements, top, digest):
    require(isinstance(measurements,dict) and set(measurements)=={'raw','hints','poly_tap'},
            'Missing SKY130 selected-target measurements.')
    raw,hints,geometry=(measurements[key] for key in ('raw','hints','poly_tap'))
    require(isinstance(raw,dict) and raw.keys()==LAYERS.keys() and
            all(type(n)is int and n>=0 for n in raw.values()), 'Incomplete selected-target raw census.')
    require(isinstance(hints,dict) and hints.keys()==HINTS.keys(), 'Incomplete selected-target intent census.')
    for row in hints.values():
        require(isinstance(row,dict) and set(row)=={'cells','labels'} and
                all(type(n)is int and n>=0 for n in row.values()), 'Invalid selected-target intent census.')
    require(isinstance(geometry,dict) and set(geometry)=={'poly','tap','intersection_components','intersection_area_nm2'},
            'Incomplete poly/tap target census.')
    for name in ('poly','tap'):
        row=geometry[name]
        require(isinstance(row,dict) and set(row)=={'raw_shapes','texts','components','area_nm2'} and
                all(type(n)is int and n>=0 for n in row.values()) and row['texts']<=row['raw_shapes'] and
                (row['raw_shapes']>row['texts'])==(row['components']>0)==(row['area_nm2']>0) and
                (name=='poly' or row['texts']==0), 'Invalid poly/tap target geometry.')
    require(all(type(geometry[key])is int and geometry[key]>=0 for key in ('intersection_components','intersection_area_nm2')) and
            (geometry['intersection_components']>0)==(geometry['intersection_area_nm2']>0) and
            geometry['intersection_area_nm2']<=min(geometry['poly']['area_nm2'],geometry['tap']['area_nm2']),
            'Invalid selected poly/tap intersection.')
    rows=[]
    for subject,group in GROUPS.items():
        witnesses={key:raw[key] for key in group['raw']}
        witnesses.update({group['hints']+'_'+key:value for key,value in hints[group['hints']].items()})
        if subject=='varactor_well': witnesses['poly_tap_area_nm2']=geometry['intersection_area_nm2']
        for key in group['ids']:
            rows.append(dict(id=key,subject=subject,witnesses=witnesses,
                disposition='unreviewed' if any(witnesses.values()) else 'absent-operand'))
    pending=sum(row['disposition']=='unreviewed' for row in rows)
    return dict(schema=1,recipe=RECIPE,source=SOURCE,scope=SCOPE,qualified=False,chunk_complete=False,
                top=top,gds_sha256=digest,measurements=measurements,rows=rows,unreviewed=pending,
                status='review-required' if pending else 'selected-target-absence-reviewed')


def measure(layout):
    import klayout.db as k
    require(len(layout.top_cells())==1 and abs(layout.dbu-.001)<1e-12,
            'Selected-target checks require one top and a 1 nm database unit.')
    top=layout.top_cell();hints={key:dict(cells=0,labels=0) for key in HINTS}
    for index in {top.cell_index(),*top.called_cells()}:
        cell=layout.cell(index)
        for key,tokens in HINTS.items(): hints[key]['cells']+=int(hint_matches(cell.name,tokens))
        for instance in cell.each_inst():
            transform=instance.cplx_trans
            require(transform.mag==1 and transform.angle%90==0, 'Unsupported selected-target transform.')
    raw={}
    for name,pair in LAYERS.items():
        count=0;it=top.begin_shapes_rec(layout.layer(*pair))
        while not it.at_end():count+=1;it.next()
        raw[name]=count
    for index in layout.layer_indexes():
        it=top.begin_shapes_rec(index);it.shape_flags=k.Shapes.STexts
        while not it.at_end():
            value=it.shape().text.string
            for key,tokens in HINTS.items():hints[key]['labels']+=int(hint_matches(value,tokens))
            it.next()
    regions={};geometry={}
    for name,pair in (('poly',(66,20)),('tap',(65,44))):
        region=k.Region();count=texts=0;it=top.begin_shapes_rec(layout.layer(*pair))
        while not it.at_end():
            shape=it.shape();count+=1
            if shape.is_text() and name=='poly':texts+=1;it.next();continue
            if shape.is_path():
                path=shape.path;points=list(path.each_point())
                require(path.width>0 and path.width%2==0 and not path.is_round() and len(points)>=2 and
                        all(a!=b and (a.x==b.x or a.y==b.y) for a,b in zip(points,points[1:])), 'Inexact poly/tap path.')
                polygon=path.polygon()
            else:
                require(shape.is_box() or shape.is_polygon() or shape.is_simple_polygon(), 'Unsupported poly/tap shape.')
                polygon=shape.polygon
            require(polygon.area()>0 and all(e.p1.x==e.p2.x or e.p1.y==e.p2.y for e in polygon.each_edge()),
                    'Selected-target poly/tap geometry must be nonempty and Manhattan.')
            region.insert(polygon.transformed(it.trans()));it.next()
        region.merge();regions[name]=region
        geometry[name]=dict(raw_shapes=count,texts=texts,components=region.count(),area_nm2=region.area())
    overlap=(regions['poly']&regions['tap']).merged()
    geometry.update(intersection_components=overlap.count(),intersection_area_nm2=overlap.area())
    return dict(raw=raw,hints=hints,poly_tap=geometry)


def audit(path):
    import klayout.db as k
    path=Path(path);digest=file_digest(path);layout=k.Layout();layout.read(str(path))
    result=expected(measure(layout),layout.top_cell().name,digest)
    require(file_digest(path)==digest, 'Layout changed during selected-target audit.')
    return result


def evaluate(report,digest,top):
    require(isinstance(report,dict), 'Missing selected-target evidence. Recheck Finish.')
    require(report==expected(report.get('measurements'),top,digest), 'Changed selected-target evidence. Recheck Finish.')
    return report


def validate_saved(report,path):
    actual=audit(path);evaluate(report,actual['gds_sha256'],actual['top'])
    require(report==actual, 'Selected-target evidence differs from the actual layout. Recheck Finish.')
    return report
