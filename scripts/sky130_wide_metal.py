"""Selected Manhattan wide-metal and attached-feature spacing checks.

C3 defines huge metal as geometry wider and longer than 3 um. For this
Manhattan profile a square morphological opening identifies those regions;
the erosion removes exactly-3-um widths as well as smaller ones. The manual's
larger spacing applies to their physical edges and to attached features out
to the same distance. Actual clipped spacing-error edges are used, so touching
the wide region at one end does not reclassify an entire long narrow wire.
"""
import hashlib
from pathlib import Path
import klayout.db as k

LAYERS={'m1':((68,20),(36,28),280),'m2':((69,20),(41,28),280),
        'm3':((70,20),(34,28),400),'m4':((71,20),(51,28),400)}


def check(regions):
    get=lambda pair:regions.get(pair,k.Region()).merged()
    checks=[]
    for name,(drawn,fill,distance) in LAYERS.items():
        metal=(get(drawn)|get(fill)).merged()
        non_manhattan=sum(e.dx()!=0 and e.dy()!=0 for e in metal.edges().each())
        huge=(metal.sized(-1500).sized(1500)&metal).merged()
        influence=huge.sized(distance)
        pairs=metal.space_check(distance)
        relevant=((pairs.first_edges()|pairs.second_edges())&influence)
        checks.append(dict(rule='profile.manhattan.'+name,violations=non_manhattan,
            description='The selected square-opening huge-metal construction requires Manhattan conductors.'))
        checks.append(dict(rule=name+'.wide_spacing',violations=relevant.count(),
            description='Minimum '+str(distance)+' nm spacing at huge metal and its nearby attached physical edges.',
            huge_regions=huge.count(),huge_area_nm2=huge.area()))
    violations=sum(c['violations'] for c in checks)
    return dict(schema=1,status='PASS' if not violations else 'FAIL',qualified=False,
        violations=violations,checks=checks,
        scope='Selected Manhattan drawn-plus-fill huge metal and attached-feature spacing only. Other rule profiles and chunk acceptance remain separate.')


def audit(path):
    path=Path(path);layout=k.Layout();layout.read(str(path))
    if len(layout.top_cells())!=1 or abs(layout.dbu-.001)>1e-12:
        raise ValueError('Expected one top cell and a 1 nm database grid.')
    regions={}
    for index in layout.layer_indexes():
        info=layout.get_info(index)
        regions[(info.layer,info.datatype)]=k.Region(layout.top_cell().begin_shapes_rec(index)).merged()
    result=check(regions)
    result.update(gds_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),top=layout.top_cell().name,
        checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result
