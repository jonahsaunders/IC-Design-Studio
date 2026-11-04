"""Remove only the independently identified DEF die outline from SKY130 GDS.

The pinned catalog forbids prBoundary.boundary and the poly/diff/tap boundary
purposes in delivered layout. A single top-level prBoundary box matching the
OpenDB die is a known stream annotation. Other forbidden input is rejected,
never silently deleted. Manufacturing geometry and pin annotations are outside
this correction's scope.
"""
from pathlib import Path

RECIPE='sky130-declared-die-outline-v1'
OUTLINE=(235,4)
FORBIDDEN={OUTLINE:('r1252','s68'),(66,4):('r1253','s69'),
           (65,4):('r1254','s70'),(65,60):('r1255','s71')}
SOURCE=dict(revision='7198cf647113f56041e02abf3eb623692820c5e1',
            path='docs/rules/errors.csv',
            sha256='d613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed')


def require(condition,message):
    if not condition:raise ValueError(message)


def counts(layout):
    require(len(layout.top_cells())==1,'SKY130 boundary checks require one top cell.')
    top=layout.top_cell();result={}
    for pair in FORBIDDEN:
        iterator=top.begin_shapes_rec(layout.layer(*pair));count=0
        while not iterator.at_end():count+=1;iterator.next()
        result[pair]=count
    return result


def require_clean(layout):
    measured=counts(layout)
    require(not any(measured.values()),
            'Forbidden SKY130 boundary-purpose data remains in the delivered GDS. Recheck Finish/export.')
    return [dict(pair=list(pair),records=list(FORBIDDEN[pair]),raw_shapes=measured[pair]) for pair in FORBIDDEN]


def review(layout,inventory):
    import klayout.db as k
    measured=counts(layout);top=layout.top_cell();die=inventory.get('die_nm')
    require(inventory.get('schema')==1 and top.name==inventory.get('top') and abs(layout.dbu-.001)<1e-12,
            'SKY130 outline removal requires matching OpenDB intent and a 1 nm database unit.')
    require(isinstance(die,list) and len(die)==4 and all(type(v)is int for v in die) and
            die[0]<die[2] and die[1]<die[3],'Invalid independently captured SKY130 die bounds.')
    require(all(measured[pair]==0 for pair in FORBIDDEN if pair!=OUTLINE),
            'Unexpected poly/diff/tap boundary-purpose input; automatic removal is not permitted.')
    shapes=list(top.shapes(layout.layer(*OUTLINE)).each())
    require(len(shapes)==measured[OUTLINE] and len(shapes)<=1,
            'Unexpected nested or multiple SKY130 die outlines; automatic removal is not permitted.')
    if shapes:
        require(shapes[0].is_box() and shapes[0].box==k.Box(*die),
                'SKY130 stream outline differs from the independently captured OpenDB die.')
    return dict(recipe=RECIPE,source=dict(SOURCE),top=top.name,die_nm=list(die),
                removed_top_die_outlines=len(shapes),
                rules=[dict(pair=list(pair),records=list(ids)) for pair,ids in FORBIDDEN.items()],
                scope='Remove only the single top-level prBoundary box equal to the OpenDB die, if present. '
                      'All other forbidden boundary-purpose input is rejected; manufacturing shapes and annotations are preserved.')


def remove_outline(layout,inventory):
    report=review(layout,inventory)
    layout.top_cell().shapes(layout.layer(*OUTLINE)).clear()
    require_clean(layout)
    return report


def validate_delivery(path):
    import klayout.db as k
    layout=k.Layout();layout.read(str(Path(path)))
    return require_clean(layout)
