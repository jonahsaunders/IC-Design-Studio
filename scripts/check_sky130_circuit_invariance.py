"""Require exact nominal native circuit invariance after remote SKY130 fill.

Compare every original non-supply capacitor row and node resistance, and every
original device record. Added devices must be rail-only native decaps.
This does not calibrate the extractor, check supply-network performance, produce
a distributed RC model, or accept a process/application by itself.
"""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import shlex


def require(value, message):
    if not value:raise ValueError(message)


def number(text):
    try:value=Decimal(text)
    except InvalidOperation as exc:raise ValueError('Invalid native numeric value.') from exc
    require(value.is_finite(),'Non-finite native numeric value.')
    return Fraction(value)


def headers(path):
    nodes={};devices=[];grounds=[];scales=[]
    with Path(path).open(encoding='ascii') as stream:
        for line in stream:
            key=line.split(' ',1)[0]
            require(key not in ('use','equiv','killnode','rnode','resist'),
                    'Expected a flat, unreduced, unaliased native extraction.')
            if key not in ('node','substrate','device','scale'):continue
            t=shlex.split(line)
            if key=='scale':
                require(len(t)==4 and all(number(v)>0 for v in t[1:]),'Invalid native scale.')
                scales.append(tuple(number(v) for v in t[1:]));continue
            if key=='device':
                formats={('msubckt','sky130_fd_pr__nfet_01v8'):19,
                    ('msubckt','sky130_fd_pr__pfet_01v8_hvt'):19,
                    ('ndiode','sky130_fd_pr__diode_pw2nd_05v5'):16,
                    ('devres','sky130_fd_pr__res_generic_po'):18}
                require(len(t)>=3 and len(t)==formats.get(tuple(t[1:3])),
                    'Unsupported native device in the low-voltage HD profile.')
                devices.append(tuple(t));continue
            require(len(t)>=7 and t[1] not in nodes and number(t[2])>=0 and number(t[3])>=0,
                    'Duplicate, incomplete or negative native node.')
            nodes[t[1]]=tuple(t)
            if key=='substrate':grounds.append(t[1])
    require(nodes and len(grounds)==1 and len(scales)==1 and scales[0][1]==1 and
            number(nodes[grounds[0]][3])==0 and len({n.casefold() for n in nodes})==len(nodes),
            'Unsupported native substrate, capacitance scale or ambiguous node names.')
    return dict(nodes=nodes,devices=devices,ground=grounds[0],scale=scales[0])


CAP=re.compile(r'^cap "([^"\n]+)" "([^"\n]+)" (\S+)\s*$')


def capacitor_rows(path, native, protected):
    """Stream all native edges; retain exactly rows incident to original nodes."""
    graph=defaultdict(Fraction);nodes=native['nodes'];ground=native['ground']
    for name in protected:
        require(name in nodes,'An original circuit node disappeared: '+name)
        value=number(nodes[name][3])
        if value:graph[tuple(sorted((name,ground)))]+=value
    with Path(path).open(encoding='ascii') as stream:
        for line in stream:
            if not line.startswith('cap '):continue
            m=CAP.fullmatch(line);require(m is not None,'Unrecognized native capacitor record.')
            a,b,text=m.groups()
            if a not in protected and b not in protected:continue
            require(a in nodes and b in nodes and a!=b,'A circuit capacitor has an invalid endpoint.')
            graph[tuple(sorted((a,b)))]+=number(text)
    return {pair:c for pair,c in graph.items() if c}


WARNING=re.compile(r'box (-?\d+) (-?\d+) (-?\d+) (-?\d+)\nfeedback add "device missing 1 terminal;\n connecting remainder to node ([^"\n]+)" pale\n')


def decap_warnings(path, devices):
    """Explain each missing-terminal warning by an independently checked decap.

    The native extractor makes the missing terminal equal to the remaining
    terminal. Both must be the expected supply; all original devices are exact.
    Final physical connectivity still requires the separate strict GDS/CDL LVS.
    """
    text=Path(path).read_text(encoding='ascii');matches=list(WARNING.finditer(text))
    require(''.join(m.group(0) for m in matches)==text,'Unexplained native extraction feedback.')
    expected=Counter((int(d[3]),int(d[4]),d[13]) for d in devices)
    actual=Counter()
    for m in matches:
        x0,y0,x1,y1=map(int,m.groups()[:4]);require(x0<x1 and y0<y1,'Empty extraction feedback box.')
        actual[(x0,y0,m[5])]+=1
    require(actual==expected,'Extraction warnings do not exactly identify the added decap terminals.')
    return len(matches)


def audit(original, filled, inventory, original_feedback, filled_feedback):
    original,filled=Path(original),Path(filled)
    digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    before_hash,after_hash=digest(original),digest(filled)
    nets=inventory['nets'];aliases={n['alias'] for n in nets}
    powers={n['alias'] for n in nets if n['sig_type']=='POWER'}
    grounds={n['alias'] for n in nets if n['sig_type']=='GROUND'}
    require(len(aliases)==len(nets) and len(powers)==len(grounds)==1 and not powers&grounds,
            'Expected unique checkpoint aliases and one supply pair.')
    vdd,vss=next(iter(powers)),next(iter(grounds));rails={vdd,vss}
    before,after=headers(original),headers(filled)
    require(before['ground']==after['ground']==vss and before['scale']==after['scale'],
            'Native extraction scale or physical ground changed.')
    require(aliases<=before['nodes'].keys() and aliases<=after['nodes'].keys(),
            'A checkpoint net is absent from native extraction.')
    protected=set(before['nodes'])-rails
    require(protected and before['devices'],'An empty circuit cannot establish invariance.')
    require(all(n in after['nodes'] and before['nodes'][n][2]==after['nodes'][n][2] for n in protected),
            'Native original-node resistance or identity changed.')
    old,new=Counter(before['devices']),Counter(after['devices'])
    require(not old-new,'An original device record changed or disappeared.')
    added=list((new-old).elements())
    for t in added:
        require(len(t)==19 and t[1]=='msubckt' and t[2] in
                ('sky130_fd_pr__nfet_01v8','sky130_fd_pr__pfet_01v8_hvt'),
                'An added device is not a supported rail-only decap.')
        expected=(vss,vdd,vss,vss) if t[2]=='sky130_fd_pr__nfet_01v8' else (vdd,vss,vdd,vdd)
        require(tuple(t[i] for i in (9,10,13,16))==expected,
                'An added device is not a correctly connected rail-only decap.')
    require(not Path(original_feedback).read_text(encoding='ascii'),'Original extraction has unexplained feedback.')
    warnings=decap_warnings(filled_feedback,added)
    left=capacitor_rows(original,before,protected);right=capacitor_rows(filled,after,protected)
    differences=[pair for pair in left.keys()|right.keys() if left.get(pair,Fraction(0))!=right.get(pair,Fraction(0))]
    require(not differences,'Native circuit capacitance changed: '+str(sorted(differences)[:3]))
    require(digest(original)==before_hash and digest(filled)==after_hash,'Native source changed during comparison.')
    return dict(schema=1,status='native-circuit-identical',qualified=False,chunk_complete=False,
        protected_nodes=len(protected),protected_capacitor_pairs=len(left),original_devices=len(before['devices']),
        added_rail_decaps=len(added),explained_decap_warnings=warnings,
        original_ext_sha256=before_hash,filled_ext_sha256=after_hash,
        original_feedback_sha256=digest(original_feedback),filled_feedback_sha256=digest(filled_feedback),
        checker_sha256=digest(__file__),
        scope='Exact nominal native non-supply circuit capacitance, device records and node resistance. Added decaps require ideal supplies. Independent geometry/connectivity, distributed RC timing, supply integrity, field calibration and application acceptance remain separate.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('original','filled','inventory','original-feedback','filled-feedback','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();result=audit(a.original,a.filled,json.loads(a.inventory.read_text()),a.original_feedback,a.filled_feedback)
    a.output.write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result))
