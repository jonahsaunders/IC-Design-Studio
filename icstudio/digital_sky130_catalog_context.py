"""Explicit catalog subjects: memory-core selection, LDNTM and forbidden boundaries.

Only complete raw absence resolves the core/implant subjects. Present data needs
the applicable numerical checks or approval; no core geometry is waived. These
45 literal messages supplement, rather than replace, the full catalog ledger.
"""
from collections import Counter
from pathlib import Path

from .digital_sky130_boundaries import FORBIDDEN, SOURCE as BOUNDARY_SOURCE
from .model import file_digest

RECIPE='sky130-explicit-catalog-context-v1'
CORE_IDS=tuple('r'+i for i in '''429 432 444 445 446 447 448 449 450 461
472 473 474 477 488 489 490 513 535 536 753 754 760 761 762 765 775 776
785 786 799 827 828'''.split())
SUBJECTS={'memory_core':dict(pair=(81,2),ids=CORE_IDS+('r1132',)),
          'ldntm':dict(pair=(11,44),ids=('r1037','r1485','r1486'))}
SOURCE=dict(revision=BOUNDARY_SOURCE['revision'],files={
    'docs/rules/errors.csv':BOUNDARY_SOURCE['sha256'],
    'docs/rules/gds_layers.csv':'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5',
    'docs/rules/layers/table-c4b-layer-description.csv':'dcfeb27a76171a67ca6a905bdc6deab0ca4d801f5970a76b1ce90aebb97bb21f',
    'docs/rules/periphery/p018-x_dotdash.csv':'0efaf5099bc464a782f0c05a2850673ae940272c16fa22ec519057171f2f1567'})
SCOPE=('Thirty-three explicitly core-selected geometry messages and one core-approval message require '
       'absence of all raw areaid.ce data; three LDNTM messages require absence of the actual implant subject. '
       'Present subjects stay unreviewed. Eight boundary prohibitions are checked directly. '
       'This is not complete catalog coverage or memory-device qualification.')


def require(condition,message):
    if not condition:raise ValueError(message)


def expected(raw,top,gds_sha256):
    pairs={name:entry['pair'] for name,entry in SUBJECTS.items()}
    pairs.update({'boundary_'+str(pair[0])+'_'+str(pair[1]):pair for pair in FORBIDDEN})
    require(isinstance(raw,dict) and raw.keys()==pairs.keys() and
            all(type(n)is int and n>=0 for n in raw.values()),'Incomplete or invalid SKY130 catalog subject census.')
    rows=[]
    for name,entry in SUBJECTS.items():
        for key in entry['ids']:
            rows.append(dict(id=key,subject=name,pair=list(entry['pair']),raw_shapes=raw[name],
                disposition='absent-operand' if raw[name]==0 else 'unreviewed'))
    for pair,ids in FORBIDDEN.items():
        name='boundary_'+str(pair[0])+'_'+str(pair[1])
        require(raw[name]==0,'Forbidden SKY130 boundary-purpose data in catalog context.')
        rows.extend(dict(id=key,subject=name,pair=list(pair),raw_shapes=0,disposition='executed-reviewed') for key in ids)
    counts=dict(Counter(row['disposition'] for row in rows))
    return dict(schema=1,recipe=RECIPE,qualified=False,chunk_complete=False,source=SOURCE,scope=SCOPE,
        top=top,gds_sha256=gds_sha256,raw_counts=dict(raw),rows=rows,counts=counts,
        status='review-required' if counts.get('unreviewed',0) else 'selected-subjects-reviewed')


def measure(layout):
    require(len(layout.top_cells())==1 and abs(layout.dbu-.001)<1e-12,
            'SKY130 catalog context requires one top cell and a 1 nm database unit.')
    top=layout.top_cell();pairs={name:entry['pair'] for name,entry in SUBJECTS.items()}
    pairs.update({'boundary_'+str(pair[0])+'_'+str(pair[1]):pair for pair in FORBIDDEN})
    raw={}
    for name,pair in pairs.items():
        iterator=top.begin_shapes_rec(layout.layer(*pair));count=0
        while not iterator.at_end():count+=1;iterator.next()
        raw[name]=count
    return raw


def audit(path):
    import klayout.db as k
    path=Path(path);digest=file_digest(path);layout=k.Layout();layout.read(str(path))
    raw=measure(layout);report=expected(raw,layout.top_cell().name,digest)
    require(file_digest(path)==digest,'SKY130 GDS changed during catalog context review.')
    return report


def evaluate(report,gds_sha256,top):
    require(isinstance(report,dict),'Missing SKY130 catalog context evidence. Recheck Finish.')
    require(report==expected(report.get('raw_counts'),top,gds_sha256),
            'Changed or incomplete SKY130 catalog context evidence. Recheck Finish.')
    return report


def validate_saved(report,path):
    actual=audit(path)
    require(report==actual,'SKY130 catalog subject census differs from the actual layout. Recheck Finish.')
    return report
