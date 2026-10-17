"""Known empty module operand for spacing and overlap, never enclosure."""
from pathlib import Path
from .model import file_digest

RECIPE='sky130-empty-module-binary-operand-v1'
SOURCE=dict(revision='7198cf647113f56041e02abf3eb623692820c5e1',files={
    'docs/rules/errors.csv':'d613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv':'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5',
    'docs/rules/layers/table-c4b-layer-description.csv':'dcfeb27a76171a67ca6a905bdc6deab0ca4d801f5970a76b1ce90aebb97bb21f',
    'docs/rules/periphery/p018-x_dotdash.csv':'0efaf5099bc464a782f0c05a2850673ae940272c16fa22ec519057171f2f1567'})
MODULE=(81,10)
TARGETS=(('nwell','0.635'),('diff','0.135'),('dnwell','3.15'),('tap','0.135'),('lvtn','0.19'),
    ('hvtp','0.19'),('hvi','0.35'),('tunm','0.25'),('poly','0.105'),('npc','0.135'),('nsdm','0.19'),
    ('psdm','0.19'),('licon1','0.085'),('li1','0.085'),('mcon','0.095'),('met1','0.07'),('via','0.085'),
    ('met2','0.07'),('via2','0.1'),('met3','0.15'),('via3','0.1'),('met4','0.15'),('via4','0.4'),
    ('met5','0.8'),('nsm','2'),('pad','0.635'),('ldntm','0.35'),('hvntm','0.19'),('ncm','0.19'),
    ('rdl','5'),('hvtr','0.19'))
CHECKS={'r'+str(261+2*i):dict(rule='x.12a',operation='spacing',other_operand='q0'+name+'notBuildSpace',limit_um=limit)
        for i,(name,limit) in enumerate(TARGETS)}
CHECKS.update({key:dict(rule='x.12d',operation='spacing',other_operand='q1'+name+'notBuildSpace',limit_um=limit)
              for key,name,limit in (('r323','met1','0.14'),('r325','met2','0.14'),('r329','met4','0.2'))})
CHECKS['r378']=dict(rule='x.16',operation='overlap',other_operand='extentDie')
SCOPE=('Thirty-four spacing and one overlap record have the explicit module operand areaid.mt on 81:10. '
    'Published periphery x.12a/x.12d and x.16 identify that operand; their catalog messages call it moduleCutAREA. '
    'With no raw shape of any kind on that purpose anywhere in reachable hierarchy, there are no module/other '
    'shape pairs for a spacing violation and no module intersection for an overlap violation. The construction '
    'of q0/q1 and extentDie is not inferred. Any raw module data, including text or malformed geometry, leaves '
    'all these decisions unreviewed. This does not waive enclosure, establish complete-chip context, validate '
    'an omitted required marker or qualify present modules. Enclosure records are never included: an absent '
    'enclosing region cannot establish that its required targets are enclosed.')


def require(condition,message):
    if not condition:raise ValueError(message)


def expected(measurements,top,digest):
    require(isinstance(measurements,dict) and set(measurements)=={'raw_module_shapes','module_texts'} and
        all(type(n)is int and n>=0 for n in measurements.values()) and
        measurements['module_texts']<=measurements['raw_module_shapes'],'Invalid module operand census.')
    absent=measurements['raw_module_shapes']==0
    rows=[dict(id=key,**check,disposition='absent-operand' if absent else 'unreviewed',
        reason='empty-known-module-operand' if absent else 'present-module-needs-other-operand') for key,check in CHECKS.items()]
    return dict(schema=1,recipe=RECIPE,source=SOURCE,scope=SCOPE,qualified=False,chunk_complete=False,
        top=top,gds_sha256=digest,measurements=measurements,rows=rows,unreviewed=0 if absent else len(rows),
        status='module-operand-absent' if absent else 'review-required')


def measure(layout):
    require(len(layout.top_cells())==1,'Module census requires one top cell.')
    # Counting raw presence needs no polygon conversion, snapping or merging.
    # Text and unsupported polygons must prevent an absence claim as well.
    raw=texts=0;it=layout.top_cell().begin_shapes_rec(layout.layer(*MODULE))
    while not it.at_end():
        raw+=1;texts+=int(it.shape().is_text());it.next()
    return dict(raw_module_shapes=raw,module_texts=texts)


def audit(path):
    import klayout.db as k
    path=Path(path);digest=file_digest(path);layout=k.Layout();layout.read(str(path))
    result=expected(measure(layout),layout.top_cell().name,digest)
    require(file_digest(path)==digest,'Layout changed during module census.')
    return result


def evaluate(report,digest,top):
    require(isinstance(report,dict),'Missing module-operand evidence. Recheck Finish.')
    require(report==expected(report.get('measurements'),top,digest),'Changed module-operand evidence. Recheck Finish.')
    return report


def validate_saved(report,path):
    actual=audit(path);evaluate(report,actual['gds_sha256'],actual['top'])
    require(report==actual,'Module evidence differs from actual layout. Recheck Finish.')
    return report
