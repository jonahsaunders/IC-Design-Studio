"""Keep selected device obligations visible and execute two implant checks.

Absence requires both empty mandatory drawn purposes and no candidate device
names or labels. Present or incompletely marked devices remain unreviewed.
This is not complete SONOS, HV, VPP, resistor or PNP qualification.
"""
from pathlib import Path

from .digital_sky130_catalog_labels import normalized
from .model import file_digest

RECIPE = 'sky130-selected-device-requirements-v1'
SOURCE = dict(revision='7198cf647113f56041e02abf3eb623692820c5e1', files={
    'docs/rules/errors.csv': 'd613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv': 'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5',
    'docs/rules/layers/table-f2a-lvs-key.rst': '0eec9055cef67032ddfc197a5c2cc754098956174340dcc1e82c82275a3dc760',
    'docs/rules/periphery/p018-x_dotdash.csv': '0efaf5099bc464a782f0c05a2850673ae940272c16fa22ec519057171f2f1567',
    'docs/rules/periphery/p027-tunm_dotdash.csv': '2688b772386cbcbbadab4cfee5d63dc3332f5a8cb1db3f5ce34c4f8ddc9791e1',
    'docs/rules/periphery/p037-vpp_dotdash.csv': '1836055617d1b99c5d84028dfa6ff43555aaf7b9249c6747415ef5e6c0be9ef6',
    'docs/rules/periphery/p049-hvntm_dotdash.csv': '90cf8049337b0f707283e37dfd83fe6c0e9918d561f2ae6b04389cf037bdd6f6',
    'docs/rules/periphery/p056-pwres_dotdash_dotdash.csv': '271003a67977988edf7ae5939f4f3edda643c881e3bb68fe5e46c6ace7555639'},
    device_table=dict(path='docs/qualification/sky130-device-tables/table-f2a-lvs.tsv',
                      sha256='c19398018c0f45674c7162077af48c57f5113617691cb985b7985f7e362de3e3'))
SUBJECTS = dict(
    vpp=dict(pair=(82,64), tokens=('vpp',), ids=tuple('r'+str(i) for i in (*range(1133,1145),*range(1146,1151),1154))),
    pwell_resistor=dict(pair=(64,13), tokens=('pwres','respw'), ids=tuple('r'+str(i) for i in range(932,947))),
    pnp=dict(pair=(82,44), tokens=('pnp',), ids=('r391',)))
LAYERS = dict(poly=(66,20),diff=(65,20),tunm=(80,20),hvntm=(125,20),hvi=(75,20))
CHECKS = {'r453':'tunm.3','r1061':'hvntm.x.1'}
SCOPE = ('Thirty-four VPP, pwell-resistor and PNP catalog records are absent only when their mandatory '
         'drawn purpose has no raw shapes and no reachable cell name or label suggests the device. '
         'Present candidates remain unreviewed. Separately, each gate (poly AND diff) overlapping tunm '
         'must be enclosed by tunm by 95 nm, and every drawn hvntm region must be inside hvi. '
         'Gates outside tunm are not selected by this enclosure check; their spacing and device intent '
         'remain separate. A SONOS name or label with no gate or with unselected gates keeps r453 unreviewed. '
         'Generated implants and complete device/density qualification are not established.')


def require(condition,message):
    if not condition: raise ValueError(message)


def expected(measurements,top,digest):
    require(isinstance(measurements,dict) and set(measurements)=={'subjects','layers','gates','selected_gates','violations','sonos_intent'},
            'Missing SKY130 selected-device measurements.')
    subjects,layers,counts=(measurements[key] for key in ('subjects','layers','violations'))
    require(isinstance(subjects,dict) and subjects.keys()==SUBJECTS.keys() and
            isinstance(layers,dict) and layers.keys()==LAYERS.keys() and
            isinstance(counts,dict) and counts.keys()==CHECKS.keys(), 'Incomplete SKY130 selected-device census.')
    for entry in subjects.values():
        require(isinstance(entry,dict) and set(entry)=={'raw_shapes','candidate_cells','candidate_labels'} and
                all(type(v) is int and v>=0 for v in entry.values()), 'Invalid SKY130 selected-device subject counts.')
    for name,entry in layers.items():
        require(isinstance(entry,dict) and set(entry)=={'raw_shapes','texts','components'} and
                all(type(v) is int and v>=0 for v in entry.values()) and entry['texts']<=entry['raw_shapes'] and
                (entry['components']>0)==(entry['raw_shapes']>entry['texts']) and
                (not entry['texts'] or name in ('poly','diff')), 'Invalid SKY130 implant census.')
    require(all(type(v) is int and v>=0 for v in [measurements['gates'],measurements['selected_gates'],*counts.values()]) and
            measurements['selected_gates']<=measurements['gates'], 'Invalid SKY130 implant geometry counts.')
    intent=measurements['sonos_intent']
    require(isinstance(intent,dict) and set(intent)=={'candidate_cells','candidate_labels'} and
            all(type(v) is int and v>=0 for v in intent.values()), 'Invalid SKY130 SONOS intent census.')
    require(not measurements['gates'] or (layers['poly']['components'] and layers['diff']['components']),
            'Gate count without gate operands.')
    require(not measurements['selected_gates'] or layers['tunm']['components'], 'Selected gate without tunm.')
    require(measurements['selected_gates'] or not counts['r453'], 'Tunm finding without a selected gate.')
    require(layers['hvntm']['components'] or not counts['r1061'], 'Hvntm finding without drawn hvntm.')
    rows=[]
    for name,selection in SUBJECTS.items():
        for key in selection['ids']:
            rows.append(dict(id=key,subject=name,disposition='unreviewed' if any(subjects[name].values()) else 'absent-operand'))
    for key,rule in CHECKS.items():
        targets=measurements['selected_gates'] if key=='r453' else layers['hvntm']['components']
        unresolved=(key=='r453' and any(intent.values()) and
                    (not measurements['gates'] or measurements['selected_gates']!=measurements['gates']))
        rows.append(dict(id=key,rule=rule,targets=targets,violations=counts[key],
                         disposition='failed' if counts[key] else 'unreviewed' if unresolved else
                         'executed-reviewed' if targets else 'absent-operand'))
    total=sum(counts.values())
    return dict(schema=1,recipe=RECIPE,source=SOURCE,scope=SCOPE,qualified=False,chunk_complete=False,
                top=top,gds_sha256=digest,measurements=measurements,rows=rows,violations=total,
                status='FAIL' if total else 'review-required' if any(r['disposition']=='unreviewed' for r in rows)
                else 'selected-device-requirements-pass')


def measure(layout):
    import klayout.db as k
    require(len(layout.top_cells())==1 and abs(layout.dbu-.001)<1e-12,
            'SKY130 selected-device checks require one top and a 1 nm database unit.')
    top=layout.top_cell();cells={top.cell_index(),*top.called_cells()}
    intent=dict(candidate_cells=0,candidate_labels=0)
    subjects={name:dict(raw_shapes=0,candidate_cells=0,candidate_labels=0) for name in SUBJECTS}
    for name,selection in SUBJECTS.items():
        iterator=top.begin_shapes_rec(layout.layer(*selection['pair']))
        while not iterator.at_end(): subjects[name]['raw_shapes']+=1;iterator.next()
    for index in cells:
        cell=layout.cell(index)
        intent['candidate_cells']+=int('sonos' in normalized(cell.name))
        for name,selection in SUBJECTS.items():
            subjects[name]['candidate_cells']+=int(any(token in normalized(cell.name) for token in selection['tokens']))
        for instance in cell.each_inst():
            t=instance.cplx_trans
            require(t.mag==1 and t.angle%90==0, 'Unsupported SKY130 selected-device transform.')
    for index in layout.layer_indexes():
        iterator=top.begin_shapes_rec(index);iterator.shape_flags=k.Shapes.STexts
        while not iterator.at_end():
            value=normalized(iterator.shape().text.string)
            intent['candidate_labels']+=int('sonos' in value)
            for name,selection in SUBJECTS.items():
                subjects[name]['candidate_labels']+=int(any(token in value for token in selection['tokens']))
            iterator.next()
    regions,census={},{}
    for name,pair in LAYERS.items():
        region=k.Region();raw=texts=0;iterator=top.begin_shapes_rec(layout.layer(*pair))
        while not iterator.at_end():
            shape=iterator.shape();raw+=1
            if shape.is_text() and name in ('poly','diff'):
                texts+=1;iterator.next();continue
            if shape.is_path():
                path=shape.path;points=list(path.each_point())
                require(path.width>0 and path.width%2==0 and not path.is_round() and len(points)>=2 and
                        all(a!=b and (a.x==b.x or a.y==b.y) for a,b in zip(points,points[1:])),
                        'Inexact SKY130 implant path: '+name)
                polygon=path.polygon()
            else:
                require(shape.is_box() or shape.is_polygon() or shape.is_simple_polygon(), 'Unsupported SKY130 implant shape: '+name)
                polygon=shape.polygon
            require(polygon.area()>0 and all(e.p1.x==e.p2.x or e.p1.y==e.p2.y for e in polygon.each_edge()),
                    'SKY130 implant checks require nonempty Manhattan polygons: '+name)
            region.insert(polygon.transformed(iterator.trans()));iterator.next()
        regions[name]=region.merged();census[name]=dict(raw_shapes=raw,texts=texts,components=regions[name].count())
    gates=(regions['poly'] & regions['diff']).merged();selected=k.Region()
    for polygon in gates.each():
        if not (k.Region(polygon)&regions['tunm']).is_empty(): selected.insert(polygon)
    counts=dict(r453=(selected-regions['tunm']).count()+regions['tunm'].enclosing_check(selected,95).count(),
                r1061=(regions['hvntm']-regions['hvi']).count())
    return dict(subjects=subjects,layers=census,gates=gates.count(),selected_gates=selected.count(),violations=counts,sonos_intent=intent)


def audit(path):
    import klayout.db as k
    path=Path(path);digest=file_digest(path);layout=k.Layout();layout.read(str(path))
    report=expected(measure(layout),layout.top_cell().name,digest)
    require(file_digest(path)==digest, 'SKY130 layout changed during selected-device checking.')
    return report


def evaluate(report,digest,top):
    require(isinstance(report,dict), 'Missing SKY130 selected-device evidence. Recheck Finish.')
    require(report==expected(report.get('measurements'),top,digest), 'Changed or incomplete SKY130 selected-device evidence. Recheck Finish.')
    require(report['violations']==0, 'SKY130 selected-device geometry checks failed.')
    return report


def validate_saved(report,path):
    actual=audit(path);evaluate(report,actual['gds_sha256'],actual['top'])
    require(report==actual, 'SKY130 selected-device evidence differs from the actual layout. Recheck Finish.')
    return report
