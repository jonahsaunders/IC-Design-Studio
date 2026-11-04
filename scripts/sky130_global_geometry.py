"""Layout-wide SKY130 angle and pin-polygon checks for a bounded profile.

Every input polygon edge, including hierarchy, holes and fill, is checked.
The strict angle profile does not invoke seal, anchor, HV or WLCSP exceptions.
Pins must be covered by drawn conductors: dummy fill cannot supply coverage.
Pwell and isolated pwell use the explicit C3 complementary-well definitions.
"""
import hashlib
import json
from pathlib import Path
import klayout.db as k

LAYER_MAP_SHA256='3ccb42d63e7bbbe0c793c4541cc51c979c914588089793ab144c36fff3d673fb'
LAYER_MAP_PATH=Path(__file__).resolve().parents[1]/'docs/qualification/sky130-layer-purposes.json'
ANGLE_GROUPS={
    'x.2.diff':((65,20),),
    'x.2.active_interconnect':((65,44),(66,20),(67,20),(66,44),(89,44),(67,44),(68,44),(69,44)),
    'x.2.upper_via':((70,44),(71,44)),
}


def layer_metadata():
    raw=LAYER_MAP_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=LAYER_MAP_SHA256:
        raise ValueError('Changed captured SKY130 layer-purpose map.')
    entries=json.loads(raw)['layers'];known={tuple(row['pair']) for row in entries}
    drawings={};pins={}
    for row in entries:
        pair=tuple(row['pair'])
        for alias in row['aliases']:
            if 'drawing' in alias['purpose'].split(', '):
                drawings.setdefault(alias['name'],set()).add(pair)
            if alias['purpose']=='pin':pins.setdefault(pair,set()).add(alias['name'])
    resolved={}
    for pair,names in pins.items():
        if names & {'pwell','pwelliso'}:
            if len(names)!=1:raise ValueError('Ambiguous implicit-well pin purpose.')
            resolved[pair]='iso_pwell' if 'pwelliso' in names else 'pwell'
        else:
            targets=set().union(*(drawings.get(name,set()) for name in names))
            if len(targets)!=1:raise ValueError('Ambiguous or missing drawn counterpart for pin '+str(pair))
            resolved[pair]=next(iter(targets))
    return known,resolved


def mask_purposes():
    # Use the same hash-locked map as the angle/pin profile. Published aliases
    # and installed camel-case purposes have identical physical meanings.
    layer_metadata()
    entries=json.loads(LAYER_MAP_PATH.read_bytes())['layers']
    normalize=lambda purpose:purpose.replace(' ','').lower()
    mask_names={alias['name'] for row in entries for alias in row['aliases']
                if normalize(alias['purpose'])=='mask'}
    edits=set();restricted=set()
    for row in entries:
        pair=tuple(row['pair'])
        for alias in row['aliases']:
            purpose=normalize(alias['purpose']);name=alias['name']
            if purpose in ('maskadd','maskdrop'):edits.add(pair)
            if (purpose in ('mask','waffledrop') or
                    (purpose=='drawing' and (name in mask_names or name=='cpmm'))):
                restricted.add(pair)
    return edits,restricted


def edge_errors(region,angle):
    # Do not merge: an illegal edge completely hidden inside another polygon
    # is still illegal input data under the published angle requirement.
    raw=region.dup();raw.merged_semantics=False
    return sum(e.dx()!=0 and e.dy()!=0 and
               (angle==90 or abs(e.dx())!=abs(e.dy())) for e in raw.edges().each())


def check(regions):
    known,pins=layer_metadata();get=lambda pair:regions.get(pair,k.Region())
    checks=[];details=[]
    def add(rule,count,description):
        checks.append(dict(rule=rule,violations=count,description=description))
    add('profile.known_purposes',sum(r.count() for pair,r in regions.items() if pair not in known),
        'Unmapped polygon purposes are refused rather than assumed not to contain pins.')
    for name,pairs in ANGLE_GROUPS.items():
        add(name,sum(edge_errors(get(pair),90) for pair in pairs),
            'Every unmerged edge must be orthogonal; no special angle exception is invoked.')
    orthogonal={pair for pairs in ANGLE_GROUPS.values() for pair in pairs}
    add('x.3a',sum(edge_errors(r,45) for pair,r in regions.items() if pair not in orthogonal),
        'All remaining polygon edges must be at integer multiples of 45 degrees, including holes and fill.')
    violations=0
    for pair,drawing in sorted(pins.items()):
        region=get(pair)
        if drawing=='pwell':
            # pin - (NOT nwell) == pin AND nwell: no arbitrary finite box is
            # introduced as a surrogate for the default substrate.
            count=(region&get((64,20))).count()
        elif drawing=='iso_pwell':
            count=(region-(get((64,18))-get((64,20)))).count()
        else:count=(region-get(drawing)).count()
        violations+=count
        details.append(dict(pin=list(pair),drawing=drawing if isinstance(drawing,str) else list(drawing),
                            polygons=region.count(),violations=count))
    add('x.5',violations,'All documented pin polygons must be covered by their drawn layer or the C3-defined implicit well.')
    edits,restricted=mask_purposes();core=get((81,2));allowed=get((81,10))|get((81,1))|get((81,12))
    add('x.9',sum((get(pair)-core).count() for pair in edits),
        'Every documented maskAdd/maskDrop polygon must be in core; no seal/diff-ring/PMM exception is invoked.')
    add('x.15a',sum((get(pair)-allowed).count() for pair in restricted),
        'Mask, drawn-compatible and waffleDrop data must be contained in drawn module/seal/frame identifiers; no die-waffle exception is invoked.')
    total=sum(row['violations'] for row in checks)
    return dict(schema=1,status='PASS' if not total else 'FAIL',qualified=False,violations=total,checks=checks,
        layer_map_sha256=LAYER_MAP_SHA256,pins=details,
        mask_purposes=dict(edits=[list(pair) for pair in sorted(edits)],restricted=[list(pair) for pair in sorted(restricted)]),
        layers=[dict(pair=list(pair),polygons=r.count()) for pair,r in sorted(regions.items()) if not r.is_empty()],
        scope='Strict layout-wide angle and pin-polygon coverage, including the published C3 implicit wells. No angle exceptions are used. Remaining requirements and chunk acceptance stay separate.')


def audit(path):
    path=Path(path);layout=k.Layout();layout.read(str(path))
    if len(layout.top_cells())!=1 or abs(layout.dbu-.001)>1e-12:
        raise ValueError('Expected one top cell and a 1 nm database grid.')
    regions={}
    for index in layout.layer_indexes():
        info=layout.get_info(index)
        regions[(info.layer,info.datatype)]=k.Region(layout.top_cell().begin_shapes_rec(index))
    result=check(regions)
    result.update(gds_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),top=layout.top_cell().name,
                  checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result
