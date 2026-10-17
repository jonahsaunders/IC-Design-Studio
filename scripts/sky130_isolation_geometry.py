"""Packaged x.29 geometry worker; explicit modes never erase measurements."""
import klayout.db as k
from scripts.sky130_grid_geometry import check as geometry_guard


def require(condition,message):
    if not condition:raise ValueError(message)


def check(layout, enabled):
    require(type(enabled) is bool,'An explicit Boolean isolation option is required.')
    guard=geometry_guard(layout)
    require(not any(r['violations'] for r in guard['checks'] if r['rule'].startswith('profile.')),
            'Unsupported geometry for isolation checking.')
    top=layout.top_cell()
    region=lambda pair:k.Region(top.begin_shapes_rec(layout.layer(*pair))).merged()
    gates=(region((65,20))&region((66,20))).merged();well=region((64,20));deep=region((64,18))
    nfet=(gates-well).merged();pfet=(gates&well).merged()
    require(not any(not (k.Region(g)&well).is_empty() and not (k.Region(g)-well).is_empty() for g in gates.each()),
            'A gate straddles nwell; its device classification needs review.')
    outside=[]
    for gate in nfet.each():
        if not (k.Region(gate)-deep).is_empty():
            box=gate.bbox();outside.append([box.left,box.bottom,box.right,box.top])
    raw=top.begin_shapes_rec(layout.layer(64,18));shapes=texts=0
    while not raw.at_end():shapes+=1;texts+=int(raw.shape().is_text());raw.next()
    measured=dict(top=top.name,nfet_gates=nfet.count(),pfet_gates=pfet.count(),dnwell_polygons=deep.count(),
        raw_dnwell_shapes=shapes,raw_dnwell_texts=texts,nfet_not_contained=len(outside),outside_examples_nm=sorted(outside)[:20])
    return dict(status=('FAIL' if outside else 'PASS') if enabled else 'NOT_REQUESTED',
                enforced=enabled,measurement=measured)
