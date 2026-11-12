"""Check five installed package drawing purposes against explicit module cuts."""
from pathlib import Path
from . import digital_sky130_boundary_interactions as geometry
from .model import file_digest

RECIPE = 'sky130-package-boundaries-v1'
SOURCE = dict(geometry.SOURCE, layer_map=dict(
    path='docs/qualification/sky130-layer-purposes.json',
    sha256='3ccb42d63e7bbbe0c793c4541cc51c979c914588089793ab144c36fff3d673fb'),
    installed_map=dict(path='tests/fixtures/sky130-package-layer-map.lyp',
    sha256='bb620355f67b1ccd98a233adaec30e7abe5227ff7b37197da4af05a031006d79'))
LAYERS = dict(pmm=(85,44), pmm2=(77,20), rdl=(74,20), ubm=(127,21), bump=(127,22))
BOUNDARIES = dict(module=(81,10))
CHECKS = {'r'+str(i): dict(rule='scribe.7', target=name, boundary='module', operation='straddle')
          for i,name in zip((1436,1440,1442,1445,1446),LAYERS)}
SCOPE = ('Five package-layer scribe.7 records use the pinned installed SKY130 layer map, '
    'which explicitly supplies their drawing purposes. Each connected drawing region is checked '
    'against every disjoint module-cut polygon on 81:10. A positive-area portion on each side '
    'is a crossing; pure contact or full containment is allowed. Missing module markers do not '
    'establish complete-chip boundaries. These bindings do not establish package availability '
    'or accept any other package, enclosure, spacing or generated-mask requirement.')
require = geometry.require


def expected(measurements, top, digest):
    require(isinstance(measurements,dict) and set(measurements)=={'layers','violations'},
            'Missing SKY130 package-boundary measurements.')
    layers,counts=measurements['layers'],measurements['violations']
    require(isinstance(layers,dict) and layers.keys()==(LAYERS|BOUNDARIES).keys() and
            isinstance(counts,dict) and counts.keys()==CHECKS.keys(), 'Incomplete package-boundary census.')
    for value in layers.values():
        require(isinstance(value,dict) and set(value)=={'raw_shapes','texts','components'} and
                all(type(n)is int and n>=0 for n in value.values()) and value['texts']==0 and
                (value['components']>0)==(value['raw_shapes']>0), 'Invalid package-boundary geometry.')
    rows=[]
    for key,check in CHECKS.items():
        n=counts[key];target=layers[check['target']]['components'];boundary=layers['module']['components']
        require(type(n)is int and 0<=n<=target*boundary, 'Invalid package-boundary findings.')
        rows.append(dict(id=key,**check,target_components=target,boundary_components=boundary,violations=n,
            disposition='failed' if n else 'absent-operand' if not target else 'executed-reviewed'))
    total=sum(counts.values())
    return dict(schema=1,recipe=RECIPE,source=SOURCE,scope=SCOPE,qualified=False,chunk_complete=False,
        top=top,gds_sha256=digest,measurements=measurements,rows=rows,violations=total,
        status='FAIL' if total else 'package-boundary-interactions-pass')


def measure(layout):
    return geometry.measure(layout,LAYERS,BOUNDARIES,CHECKS,frozenset())


def audit(path):
    import klayout.db as k
    path=Path(path);digest=file_digest(path);layout=k.Layout();layout.read(str(path))
    result=expected(measure(layout),layout.top_cell().name,digest)
    require(file_digest(path)==digest,'Layout changed during package-boundary checking.')
    return result


def evaluate(report,digest,top):
    require(isinstance(report,dict),'Missing package-boundary evidence. Recheck Finish.')
    require(report==expected(report.get('measurements'),top,digest),'Changed package-boundary evidence. Recheck Finish.')
    require(report['violations']==0,'SKY130 package-boundary checks failed.')
    return report


def validate_saved(report,path):
    actual=audit(path);evaluate(report,actual['gds_sha256'],actual['top'])
    require(report==actual,'Package-boundary evidence differs from the actual layout. Recheck Finish.')
    return report
