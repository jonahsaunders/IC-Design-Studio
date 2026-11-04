"""Reject native MOS gate-capacitance redistribution in a flat IHP export.

The raw flat .ext capacitor graph is checked against the exported SPICE graph.
Magic prints capacitances below 1 aF as zero and uses five fractional digits
after its SI scaling; the allowance below follows that captured serialization.
It is a serialization check, not a field-model accuracy tolerance.
"""
from collections import defaultdict
import hashlib
import math
from pathlib import Path
import re
import shlex

try:
    from .ihp_native_capacitance import read_capacitors
except ImportError:
    from ihp_native_capacitance import read_capacitors


def raw_capacitors(path):
    data=Path(path).read_bytes();nodes={};caps=[];ground=[];scale=[]
    for line in data.decode('ascii').splitlines():
        key=line.split(' ',1)[0]
        if key in ('use','equiv','killnode','rnode','resist'):
            raise ValueError('Expected a flat, unreduced, unaliased capacitance extraction.')
        if key not in ('node','substrate','cap','scale'):continue
        t=shlex.split(line)
        if key=='scale':
            if len(t)!=4:raise ValueError('Incomplete extraction scale.')
            scale.append(float(t[2]));continue
        if key in ('node','substrate'):
            if len(t)<7 or t[1] in nodes:raise ValueError('Repeated or incomplete original node.')
            nodes[t[1]]=float(t[3])
            if key=='substrate':ground.append(t[1])
        else:
            if len(t)!=4:raise ValueError('Incomplete original capacitor.')
            caps.append((t[1],t[2],float(t[3])))
    if (len(scale)!=1 or scale[0]!=1 or len(ground)!=1 or not nodes or nodes[ground[0]]!=0 or
            len({n.casefold() for n in nodes})!=len(nodes)):
        raise ValueError('Unsupported native scale, substrate or ambiguous node identities.')
    ground=ground[0]
    edges=caps+[(n,ground,c) for n,c in nodes.items() if n!=ground and c]
    if (any(not math.isfinite(c) or c<0 for c in nodes.values()) or
            any(a not in nodes or b not in nodes or a==b or not math.isfinite(c) or c < -1e-10 for a,b,c in edges)):
        raise ValueError('Invalid original capacitance graph.')
    noise=[c for a,b,c in caps if c<0]
    if -math.fsum(noise)>1e-7:raise ValueError('Cumulative native capacitor roundoff exceeds its bound.')
    # These sub-1e-10 aF residues arise in native overlap subtraction.
    # Count and bound them explicitly; meaningful negative C fails.
    return dict(nodes=sorted(nodes),edges_af=[(a,b,c) for a,b,c in edges if c>0],ground=ground,
                negative_roundoff_count=len(noise),negative_roundoff_total_af=-math.fsum(noise),
                source_sha256=hashlib.sha256(data).hexdigest())


def audit(ext_path,spice_path):
    expected=raw_capacitors(ext_path);exported=read_capacitors(spice_path)
    def aggregate(edges):
        values=defaultdict(list)
        for a,b,c in edges:values[tuple(sorted((a,b)))].append(c)
        return {pair:math.fsum(v) for pair,v in values.items()}
    original=aggregate(expected['edges_af']);actual=aggregate(exported['edges_af'])
    errors=[];maximum=0.
    for pair in original.keys()|actual.keys():
        wanted=original.get(pair,0.);seen=actual.get(pair,0.);error=abs(wanted-seen);maximum=max(maximum,error)
        # Native esSIvalue prints sub-aF values as zero; otherwise five decimal
        # places in fF (<99.99 fF), pF (<100.01 pF), then nF. Include float32
        # conversion roundoff. No allowance is given to an invented capacitor.
        if not wanted:allowance=0.
        elif wanted<1:allowance=1.
        else:allowance=(.005 if wanted<99990 else 5 if wanted<100010000 else 5000)+wanted*2e-7
        if error>allowance+1e-9:errors.append(dict(nodes=pair,expected_af=wanted,actual_af=seen,allowed_af=allowance))
    if errors:raise ValueError('Native flat capacitor graph changed: '+str(errors[:3]))
    return dict(schema=1,passed=True,qualified=False,ground=expected['ground'],pairs=len(original),
                negative_roundoff_count=expected['negative_roundoff_count'],negative_roundoff_total_af=expected['negative_roundoff_total_af'],
                maximum_serialization_error_af=maximum,source_ext_sha256=expected['source_sha256'],
                source_spice_sha256=exported['source_sha256'],
                scope='Flat capacitance conservation within native numeric serialization, not field calibration.')


def write_full_precision(graph,path):
    """Retain sub-aF native extraction values after the flat-export audit."""
    path=Path(path)
    if path.exists():raise ValueError('Use a new full-precision capacitor path.')
    with path.open('w',encoding='ascii',newline='\n') as stream:
        stream.write('* Original flat extraction capacitors in farads, before native display rounding.\n')
        for i,(a,b,c) in enumerate(graph['edges_af']):
            stream.write(f'CP{i} {a} {b} {c*1e-18:.17g}\n')
    return hashlib.sha256(path.read_bytes()).hexdigest()
