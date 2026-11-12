"""Resolve only explicitly absent labels, named cells and raw catalog targets.

Present targets remain unreviewed. This census does not infer device recognition,
frame geometry, a routing graph, or permission to suppress a numerical rule.
"""
from collections import Counter
from pathlib import Path
import unicodedata

from .digital_sky130_catalog_context import SOURCE
from .model import file_digest

RECIPE='sky130-explicit-label-subjects-v1'
RAW={
    'low_tap_density':dict(pair=(81,14),ids=('s72',)),
    'injection':dict(pair=(81,17),ids=('s73',)),
    'prune':dict(pair=(84,44),ids=('r380',)),
    'capm':dict(pair=(89,44),ids=('r326',)),
    'cap2m':dict(pair=(97,44),ids=('r327','r328')),
    'pad':dict(pair=(76,20),ids=('r1404',))}
LABELS={prefix:dict(tokens=(prefix+'_float',prefix+'_tie'),
    ids=tuple('s'+str(9+5*i+j) for j in (0,1,3,4)))
    for i,prefix in enumerate(('poly','li1','m1','m2','m3','m4','m5'))}
LABELS['condiode']=dict(tokens=('condiode',),ids=('r1207',))
CELLS={'partnum':dict(tokens=('partnum',),ids=('s7',))}
GROUPS={'raw':RAW,'labels':LABELS,'cells':CELLS}
SCOPE=('Thirty-seven literal catalog messages are resolved only by complete absence of their selected '
       'label, named-cell or raw-layer subject. Labels are searched on every purpose and through the hierarchy; '
       'case, Unicode compatibility, whitespace and embedded-token variants conservatively prevent absence. '
       'Present subjects stay unreviewed. Unmarked floating nets, redundant vias, chip part-number requirements '
       'and the construction of module/frame regions remain separate.')


def require(condition,message):
    if not condition:raise ValueError(message)


def normalized(text):
    return ''.join(unicodedata.normalize('NFKC',text).casefold().split())


def matches(text,selection):
    value=normalized(text)
    return any(token in value for token in selection['tokens'])


def expected(census,top,gds_sha256):
    require(isinstance(census,dict) and census.keys()==GROUPS.keys(),'Missing SKY130 label subject census.')
    rows=[]
    for kind,selections in GROUPS.items():
        counts=census[kind]
        require(isinstance(counts,dict) and counts.keys()==selections.keys() and
                all(type(n)is int and n>=0 for n in counts.values()),'Incomplete or invalid SKY130 label subject counts.')
        for name,selection in selections.items():
            for key in selection['ids']:
                rows.append(dict(id=key,kind=kind,subject=name,occurrences=counts[name],
                    disposition='absent-operand' if counts[name]==0 else 'unreviewed'))
    counts=dict(Counter(row['disposition'] for row in rows))
    return dict(schema=1,recipe=RECIPE,qualified=False,chunk_complete=False,source=SOURCE,scope=SCOPE,
        top=top,gds_sha256=gds_sha256,census=census,rows=rows,counts=counts,
        status='review-required' if counts.get('unreviewed',0) else 'selected-subjects-reviewed')


def measure(layout):
    import klayout.db as k
    require(len(layout.top_cells())==1 and abs(layout.dbu-.001)<1e-12,
            'SKY130 label subjects require one top cell and a 1 nm database unit.')
    top=layout.top_cell();census={kind:{name:0 for name in selections} for kind,selections in GROUPS.items()}
    for name,selection in RAW.items():
        iterator=top.begin_shapes_rec(layout.layer(*selection['pair']))
        while not iterator.at_end():census['raw'][name]+=1;iterator.next()
    for index in layout.layer_indexes():
        iterator=top.begin_shapes_rec(index);iterator.shape_flags=k.Shapes.STexts
        while not iterator.at_end():
            text=iterator.shape().text.string
            for name,selection in LABELS.items():census['labels'][name]+=int(matches(text,selection))
            iterator.next()
    for index in {top.cell_index(),*top.called_cells()}:
        for name,selection in CELLS.items():census['cells'][name]+=int(matches(layout.cell(index).name,selection))
    return census


def audit(path):
    import klayout.db as k
    path=Path(path);digest=file_digest(path);layout=k.Layout();layout.read(str(path))
    report=expected(measure(layout),layout.top_cell().name,digest)
    require(file_digest(path)==digest,'SKY130 layout changed during label subject review.')
    return report


def evaluate(report,gds_sha256,top):
    require(isinstance(report,dict),'Missing SKY130 label subject evidence. Recheck Finish.')
    require(report==expected(report.get('census'),top,gds_sha256),
            'Changed or incomplete SKY130 label subject evidence. Recheck Finish.')
    return report


def validate_saved(report,path):
    require(report==audit(path),'SKY130 label subject census differs from the actual layout. Recheck Finish.')
    return report
