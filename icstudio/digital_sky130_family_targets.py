"""Conservative absence proofs for low-Vt RF and explicitly named bondpad targets."""
from pathlib import Path
from . import digital_sky130_selected_targets as selected
from .model import file_digest

RECIPE = 'sky130-family-targets-v1'
SOURCE = selected.SOURCE
LAYERS = {name:selected.LAYERS[name] for name in selected.GROUPS['bond_pad']['raw']}
LAYERS.update(lvtn=(125,44), clvtnm=(25,0), clvtnm_drawing=(25,44),
    clvtnm_add=(25,43), clvtnm_drop=(25,42), low_vt_id=(81,108))
HINTS = dict(bond_pad=selected.HINTS['bond_pad'], low_vt_rf=(
    'nlowvt','lowvt','lvt','sky130rf','s8rf','rfnmos','rfnfet','rfmos','rffet'))
GROUPS = dict(
    bond_pad=dict(ids=('r1312','r1313','r1333'), raw=selected.GROUPS['bond_pad']['raw']),
    low_vt_rf=dict(ids=tuple('r'+str(n) for n in range(645,680)),
        raw=('lvtn','clvtnm','clvtnm_drawing','clvtnm_add','clvtnm_drop','low_vt_id')))
SCOPE = ('Thirty-five diff.13 messages explicitly name sky130rf_nlowvt devices. '
    'The published F2a nlowvt family requires drawn lvtn; the GDS table identifies 125:44 '
    'as the low-Vt NMOS device purpose. Empty lvtn, all published CLVTNM mask/edit purposes, '
    'low-Vt identifier, and no low-Vt/RF cell or text hints establish this family absent. '
    'This is not a numerical RF geometry pass, recognition of present RF devices, or a substitute '
    'for the missing fixed-layout model map and Table H5. Three messages explicitly target '
    'bondpad existence or opening: C3 defines bondPad as pad:dg OUTSIDE areaid:ft. '
    'All pad drawing, mask, pin, label, center and frame guards and intent hints must be empty. '
    'Present or ambiguous subjects remain unreviewed, even when enclosure layers are missing. '
    'Other RF families and pad variants are not covered.')
require=selected.require


def expected(measurements,top,digest):
    require(isinstance(measurements,dict) and set(measurements)=={'raw','hints'},'Missing SKY130 family measurements.')
    raw,hints=measurements['raw'],measurements['hints']
    require(isinstance(raw,dict) and raw.keys()==LAYERS.keys() and all(type(n)is int and n>=0 for n in raw.values()),
            'Incomplete family raw census.')
    require(isinstance(hints,dict) and hints.keys()==HINTS.keys(),'Incomplete family intent census.')
    for row in hints.values():
        require(isinstance(row,dict) and set(row)=={'cells','labels'} and
                all(type(n)is int and n>=0 for n in row.values()),'Invalid family intent census.')
    rows=[]
    for subject,group in GROUPS.items():
        witnesses={key:raw[key] for key in group['raw']}
        witnesses.update({subject+'_'+key:value for key,value in hints[subject].items()})
        for key in group['ids']:
            rows.append(dict(id=key,subject=subject,witnesses=witnesses,
                disposition='unreviewed' if any(witnesses.values()) else 'absent-operand'))
    pending=sum(r['disposition']=='unreviewed' for r in rows)
    return dict(schema=1,recipe=RECIPE,source=SOURCE,scope=SCOPE,qualified=False,chunk_complete=False,
        top=top,gds_sha256=digest,measurements=measurements,rows=rows,unreviewed=pending,
        status='review-required' if pending else 'family-target-absence-reviewed')


def measure(layout):
    import klayout.db as k
    require(len(layout.top_cells())==1 and abs(layout.dbu-.001)<1e-12,'Family checks require one top and a 1 nm database unit.')
    top=layout.top_cell();hints={key:dict(cells=0,labels=0) for key in HINTS}
    for index in {top.cell_index(),*top.called_cells()}:
        cell=layout.cell(index)
        for key,tokens in HINTS.items():hints[key]['cells']+=int(selected.hint_matches(cell.name,tokens))
        for instance in cell.each_inst():
            t=instance.cplx_trans
            require(t.mag==1 and t.angle%90==0,'Unsupported family-target transform.')
    raw={}
    for name,pair in LAYERS.items():
        count=0;it=top.begin_shapes_rec(layout.layer(*pair))
        while not it.at_end():count+=1;it.next()
        raw[name]=count
    for index in layout.layer_indexes():
        it=top.begin_shapes_rec(index);it.shape_flags=k.Shapes.STexts
        while not it.at_end():
            for key,tokens in HINTS.items():hints[key]['labels']+=int(selected.hint_matches(it.shape().text.string,tokens))
            it.next()
    return dict(raw=raw,hints=hints)


def audit(path):
    import klayout.db as k
    path=Path(path);digest=file_digest(path);layout=k.Layout();layout.read(str(path))
    result=expected(measure(layout),layout.top_cell().name,digest)
    require(file_digest(path)==digest,'Layout changed during family-target checking.')
    return result


def evaluate(report,digest,top):
    require(isinstance(report,dict),'Missing family-target evidence. Recheck Finish.')
    require(report==expected(report.get('measurements'),top,digest),'Changed family-target evidence. Recheck Finish.')
    return report


def validate_saved(report,path):
    actual=audit(path);evaluate(report,actual['gds_sha256'],actual['top'])
    require(report==actual,'Family-target evidence differs from the actual layout. Recheck Finish.')
    return report
