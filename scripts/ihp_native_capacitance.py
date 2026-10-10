"""Reduce the native SPICE capacitance network for experimental IHP probes.

Use the full-precision capacitor file from the grid-aware, flat native export.
The export must first pass check_ihp_flat_capacitance: the hierarchical native
exporter can incorrectly redistribute MOS gate capacitance. This module retains
active-fill junction terminals and eliminates only floating metal. It does not
produce a distributed RC timing model or qualify a process.
NumPy and SciPy are optional dependencies of this research script.
"""
from collections import defaultdict
import argparse
import hashlib
import json
import math
from pathlib import Path
import re


NUMBER=re.compile(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([fpn]?)\Z')


def read_capacitors(path):
    """Return the actual exported capacitor graph in attofarads, including zeros."""
    data=Path(path).read_bytes()
    if len(data)>256*1024*1024:raise ValueError('Native capacitor source exceeds 256 MiB.')
    names=set();nodes=set();edges=[];zeros=0
    for line in data.decode('ascii').splitlines():
        line=line.strip()
        if re.match(r'^\.(include|inc|lib)\b',line,re.I):
            raise ValueError('The native capacitor source must be self-contained.')
        if not line or line[0].upper()!='C':continue
        tokens=line.split()
        if len(tokens)!=4 and tokens[4:]!=[';','**FLOATING']:
            raise ValueError('Unsupported native capacitor record.')
        name,a,b,value=tokens[:4];m=NUMBER.fullmatch(value)
        if name.casefold() in names or a==b or not m:
            raise ValueError('Repeated, self-connected or nonnumeric native capacitor.')
        # All native aliases are case-sensitive before SPICE parsing. Refuse a
        # collision instead of silently merging two extracted physical nodes.
        names.add(name.casefold());nodes.update((a,b))
        c=float(m[1])*{'':1e18,'f':1e3,'p':1e6,'n':1e9}[m[2]]
        if not math.isfinite(c) or c<0:raise ValueError('Invalid native capacitance.')
        if c:edges.append((a,b,c))
        else:zeros+=1
    if not names or len({n.casefold() for n in nodes})!=len(nodes):
        raise ValueError('Empty capacitor network or ambiguous node identities.')
    return dict(nodes=sorted(nodes),edges_af=edges,zero_capacitors=zeros,
                source_sha256=hashlib.sha256(data).hexdigest())


def reduce_capacitors(graph, ground, *, relative_charge_error=1e-4):
    """Passive Schur complement; charge-row error is not a timing-error bound."""
    import numpy as np
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.sparse.linalg import splu
    if not 0<=relative_charge_error<=1e-4 or not math.isfinite(relative_charge_error):
        raise ValueError('Charge error budget must be between zero and 1e-4.')
    nodes=set(graph['nodes'])
    if ground not in nodes or ground.startswith('FILL'):
        raise ValueError('The physical ground alias is missing or names floating fill.')
    floating=sorted(n for n in nodes if n.startswith('FILL') and not n.startswith('FILL001_'))
    retained=sorted(nodes-set(floating)-{ground})
    if len(floating)>100000 or len(retained)>4096:
        raise ValueError('Network exceeds the bounded reference solver scope.')
    fi={n:i for i,n in enumerate(floating)};ki={n:i for i,n in enumerate(retained)}
    diagonal=np.zeros(len(floating));direct=np.zeros((len(retained),len(retained)))
    ri=[];ci=[];values=[];boundary=defaultdict(float)
    for x,y,c in graph['edges_af']:
        if x not in nodes or y not in nodes or x==y or not math.isfinite(c) or c<=0:
            raise ValueError('Invalid capacitor graph.')
        for n in (x,y):
            if n in fi:diagonal[fi[n]]+=c
            elif n in ki:direct[ki[n],ki[n]]+=c
        if x in fi and y in fi:
            ri.extend((fi[x],fi[y]));ci.extend((fi[y],fi[x]));values.extend((-c,-c))
        elif x in fi and y in ki:boundary[fi[x],ki[y]]+=c
        elif y in fi and x in ki:boundary[fi[y],ki[x]]+=c
        elif x in ki and y in ki:direct[ki[x],ki[y]]-=c;direct[ki[y],ki[x]]-=c
    residual=0.;observable_count=0
    if floating:
        adjacent=coo_matrix((values,(ri,ci)),shape=(len(fi),len(fi))).tocsr()
        _,component=connected_components(adjacent,directed=False)
        observable={component[i] for i,j in boundary}
        use=np.array([i for i in range(len(fi)) if component[i] in observable],dtype=int)
        observable_count=len(use)
        if len(use):
            index={int(i):j for j,i in enumerate(use)}
            matrix=(adjacent+coo_matrix((diagonal,(range(len(fi)),range(len(fi)))),shape=(len(fi),len(fi)))).tocsc()[use,:][:,use]
            ports=sorted({j for i,j in boundary});port_index={j:i for i,j in enumerate(ports)}
            coupling=coo_matrix(([v for v in boundary.values()],([index[i] for i,j in boundary],[port_index[j] for i,j in boundary])),shape=(len(use),len(ports))).tocsc()
            factor=splu(matrix)
            for start in range(0,len(ports),16):
                rhs=coupling[:,start:start+16].toarray();solution=factor.solve(rhs)
                residual=max(residual,float(np.max(np.abs(matrix@solution-rhs)))/max(1,float(np.max(np.abs(rhs)))))
                direct[np.ix_(ports,ports[start:start+16])]-=coupling.T@solution
    magnitude=max(1,float(np.max(np.abs(direct),initial=0)))
    if (residual>1e-10 or np.max(np.abs(direct-direct.T),initial=0)>magnitude*1e-11 or
            np.min(np.diag(direct),initial=0)<0 or np.min(direct.sum(axis=1),initial=0)<-1e-7):
        raise ValueError('Reduced capacitance failed residual, symmetry or passivity checks.')
    candidates=[]
    for i in range(len(retained)):
        for j in range(i+1,len(retained)):
            v=float((direct[i,j]+direct[j,i])/2)
            if v>magnitude*1e-11:raise ValueError('Reduced network has a nonpassive mutual.')
            if v<0:candidates.append((-v,i,j))
    spent=np.zeros(len(retained));kept=[];budget=relative_charge_error*np.diag(direct)
    for c,i,j in sorted(candidates):
        if spent[i]+c<=budget[i] and spent[j]+c<=budget[j]:spent[i]+=c;spent[j]+=c
        else:kept.append((retained[i],retained[j],c))
    # Preserve each diagonal while replacing omitted mutuals by endpoint shunts.
    shunts={n:math.fsum(float(v) for v in direct[i,:])+float(spent[i]) for i,n in enumerate(retained)}
    if any(c<-1e-7 for c in shunts.values()):raise ValueError('Negative reduced ground capacitance.')
    return dict(ground=ground,couplings_af=kept,ground_af={n:max(0,c) for n,c in shunts.items()},
                floating_metal_nodes=len(floating),observable_metal_nodes=observable_count,
                active_junction_nodes=sum(n.startswith('FILL001_') for n in retained),retained_nodes=len(retained),
                residual=residual,relative_charge_error=relative_charge_error,source_sha256=graph['source_sha256'])


def write_capacitors(result, path):
    path=Path(path)
    if path.exists():raise ValueError('Use a new capacitor network output path.')
    with path.open('w',encoding='ascii',newline='\n') as stream:
        stream.write('* Native SPICE capacitance; active junctions remain explicit.\n')
        for i,(a,b,c) in enumerate(result['couplings_af']):stream.write(f'CKM{i} {a} {b} {c*1e-18:.17g}\n')
        for i,(n,c) in enumerate(sorted(result['ground_af'].items())):
            if c:stream.write(f'CKG{i} {n} {result["ground"]} {c*1e-18:.17g}\n')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spice',type=Path,required=True)
    parser.add_argument('--ground',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a new reference-model directory.')
    graph=read_capacitors(args.spice);result=reduce_capacitors(graph,args.ground)
    args.output.mkdir(parents=True,exist_ok=False)
    digest=write_capacitors(result,args.output/'capacitance.spice')
    record={k:v for k,v in result.items() if k not in ('couplings_af','ground_af')}
    record.update(schema=1,qualified=False,status='prepared',capacitance_sha256=digest,
                  retained_mutuals=len(result['couplings_af']),native_zero_capacitors=graph['zero_capacitors'],
                  source_capacitors=len(graph['edges_af']),
                  scope='Native capacitor network only. Requires device/port, junction-model and waveform checks; no distributed RC acceptance.')
    (args.output/'record.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record))


if __name__=='__main__':main()
